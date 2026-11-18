from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import math
from threading import Lock
from time import monotonic, sleep
from typing import NotRequired, TypedDict
from uuid import UUID

import httpx
from pydantic import SecretStr

from backend.app.core.config import Settings


GRAPH_URL = "https://graph.microsoft.com/v1.0"
SCOPE = "https://graph.microsoft.com/.default"
SYNC_TIMEOUT_SECONDS = 120
MAX_REQUESTS = 500
MAX_OBJECTS = 10_000
MAX_MEMBERSHIPS = 25_000
MAX_RESPONSE_BYTES = 4 * 1024 * 1024

MESSAGES = {
    "disabled": "The Microsoft Entra integration is disabled.",
    "invalid_configuration": "Configure the backend Entra tenant, application and secret.",
    "token_rejected": "Microsoft rejected the credentials. Verify the tenant, application and active secret.",
    "graph_unauthorized": "Microsoft Graph rejected the application token.",
    "graph_forbidden": "Check administrator consent for the Graph application permissions User.Read.All and Group.Read.All.",
    "membership_forbidden": "Microsoft Graph refused group membership access. Verify application consent and group visibility.",
    "graph_throttled": "Microsoft is throttling requests. Wait before starting another synchronization.",
    "graph_unavailable": "Microsoft did not respond successfully. Try again later.",
    "invalid_response": "Microsoft returned a response the integration could not validate.",
    "sync_limit": "The synchronization reached its directory size, request or time limit.",
    "sync_expired": "The previous synchronization expired before it could finish.",
    "storage_failed": "The snapshot could not be saved. Check database availability and try again.",
    "migration_required": "Apply the IdentityOps database migration before opening the Entra integration.",
    "sync_running": "A Microsoft Entra synchronization is already running.",
}


class GraphError(Exception):
    def __init__(self, code: str, retry_after: int | None = None):
        super().__init__(MESSAGES[code])
        self.code = code
        self.retry_after = retry_after


@dataclass(frozen=True)
class GraphConfig:
    tenant_id: str
    client_id: str
    secret: SecretStr = field(repr=False)
    base_url: str = GRAPH_URL
    timeout: float = 10

    @classmethod
    def from_settings(cls, settings: Settings):
        if not settings.ENTRA_ENABLED:
            raise GraphError("disabled")
        try:
            tenant_id = str(UUID(settings.AZURE_TENANT_ID))
            client_id = str(UUID(settings.AZURE_CLIENT_ID))
        except ValueError:
            raise GraphError("invalid_configuration") from None
        if not settings.AZURE_CLIENT_SECRET.get_secret_value().strip():
            raise GraphError("invalid_configuration")
        # Only the Microsoft public-cloud Graph v1.0 origin can receive this bearer token.
        base_url = settings.ENTRA_GRAPH_BASE_URL.rstrip("/")
        if base_url != GRAPH_URL:
            raise GraphError("invalid_configuration")
        return cls(tenant_id, client_id, settings.AZURE_CLIENT_SECRET, base_url, settings.ENTRA_HTTP_TIMEOUT_SECONDS)


class TokenCache:
    def __init__(self):
        self.lock = Lock()
        self.key: GraphConfig | None = None
        self.value: str | None = None
        self.expires_at = 0.0


class UserRecord(TypedDict):
    object_id: str
    display_name: str | None
    principal_name: str | None
    mail: str | None
    account_enabled: bool | None
    user_type: NotRequired[str | None]
    employee_type: NotRequired[str | None]
    employee_number: NotRequired[str | None]
    given_name: NotRequired[str | None]
    surname: NotRequired[str | None]
    job_title: NotRequired[str | None]


class GroupRecord(TypedDict):
    object_id: str
    display_name: str | None
    security_enabled: bool | None


@dataclass
class DirectorySnapshot:
    users: dict[str, UserRecord]
    groups: dict[str, GroupRecord]
    memberships: set[tuple[str, str]]
    skipped_users: int


def retry_after_seconds(value: str | None) -> int | None:
    if not value:
        return None
    try:
        seconds = int(value)
    except ValueError:
        try:
            seconds = math.ceil((parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None
    return min(86_400, max(0, seconds))


def object_id(item: dict) -> str:
    try:
        return str(UUID(item["id"]))
    except (KeyError, ValueError, TypeError, AttributeError):
        raise GraphError("invalid_response") from None


def optional_text(item: dict, name: str, limit: int) -> str | None:
    value = item.get(name)
    if value is not None and (not isinstance(value, str) or len(value) > limit or "\0" in value):
        raise GraphError("invalid_response")
    return value


def optional_bool(item: dict, name: str) -> bool | None:
    value = item.get(name)
    if value is not None and not isinstance(value, bool):
        raise GraphError("invalid_response")
    return value


class GraphClient:
    def __init__(self, config: GraphConfig, http: httpx.Client, cache: TokenCache):
        self.config = config
        self.http = http
        self.cache = cache
        self.deadline = monotonic() + SYNC_TIMEOUT_SECONDS
        self.requests = 0

    def remaining(self) -> float:
        remaining = self.deadline - monotonic()
        if remaining <= 0:
            raise GraphError("sync_limit")
        return remaining

    def request(self, method: str, url: str | httpx.URL, *, token_request=False, membership=False, **kwargs):
        for attempt in range(3):
            self.requests += 1
            if self.requests > MAX_REQUESTS:
                raise GraphError("sync_limit")
            timeout = min(self.config.timeout, self.remaining())
            retry_after = None
            try:
                with self.http.stream(method, url, timeout=timeout, **kwargs) as response:
                    status = response.status_code
                    if status == 200:
                        return self.read_json(response)
                    if status == 429:
                        retry_after = retry_after_seconds(response.headers.get("Retry-After"))
                        code = "graph_throttled"
                    elif 500 <= status <= 599:
                        retry_after = retry_after_seconds(response.headers.get("Retry-After"))
                        code = "graph_unavailable"
                    elif token_request and status in (400, 401, 403):
                        raise GraphError("token_rejected")
                    elif status == 401:
                        raise GraphError("graph_unauthorized")
                    elif status == 403:
                        raise GraphError("membership_forbidden" if membership else "graph_forbidden")
                    else:
                        raise GraphError("invalid_response")
            except httpx.RequestError:
                code = "graph_unavailable"
            delay = max(0.5 * 2**attempt, retry_after or 0)
            if attempt == 2 or delay > 15 or delay >= self.remaining():
                raise GraphError(code, retry_after)
            sleep(delay)

    def read_json(self, response: httpx.Response) -> dict:
        payload = bytearray()
        for chunk in response.iter_bytes(chunk_size=8192):
            self.remaining()
            if len(payload) + len(chunk) > MAX_RESPONSE_BYTES:
                raise GraphError("sync_limit")
            payload.extend(chunk)
        try:
            result = json.loads(payload)
        except (ValueError, RecursionError):
            raise GraphError("invalid_response") from None
        if not isinstance(result, dict):
            raise GraphError("invalid_response")
        return result

    def token(self) -> str:
        if not self.cache.lock.acquire(timeout=self.remaining()):
            raise GraphError("sync_limit")
        try:
            if self.cache.key == self.config and self.cache.value and self.cache.expires_at > monotonic():
                return self.cache.value
            start = monotonic()
            result = self.request(
                "POST", f"https://login.microsoftonline.com/{self.config.tenant_id}/oauth2/v2.0/token",
                token_request=True,
                data={
                    "client_id": self.config.client_id,
                    "client_secret": self.config.secret.get_secret_value(),
                    "grant_type": "client_credentials",
                    "scope": SCOPE,
                },
            )
            value = result.get("access_token")
            duration = result.get("expires_in")
            if (
                not isinstance(value, str) or not value or not value.isascii() or not value.isprintable()
                or " " in value or type(duration) is not int or not 0 < duration <= 86_400
                or str(result.get("token_type", "")).lower() != "bearer"
            ):
                raise GraphError("invalid_response")
            self.cache.key = self.config
            self.cache.value = value
            self.cache.expires_at = start + duration - min(60, duration / 2)
            return value
        finally:
            self.cache.lock.release()

    def pages(self, path: str, fields: str, *, membership=False):
        base = httpx.URL(f"{self.config.base_url}{path}")
        url = base.copy_merge_params({"$select": fields, "$top": "100"})
        visited: set[httpx.URL] = set()
        while True:
            if url in visited:
                raise GraphError("invalid_response")
            visited.add(url)
            token = self.token()
            try:
                data = self.request("GET", url, membership=membership, headers={"Authorization": f"Bearer {token}"})
            except GraphError as error:
                if error.code == "graph_unauthorized":
                    with self.cache.lock:
                        if self.cache.value == token:
                            self.cache.expires_at = 0
                raise
            items = data.get("value")
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise GraphError("invalid_response")
            yield from items
            next_link = data.get("@odata.nextLink")
            if next_link is None:
                break
            if not isinstance(next_link, str) or len(next_link) > 8192:
                raise GraphError("invalid_response")
            try:
                url = httpx.URL(next_link)
            except httpx.InvalidURL:
                raise GraphError("invalid_response") from None
            if (
                url.scheme != base.scheme or url.host != base.host or url.port != base.port
                or url.userinfo or url.fragment or url.raw_path.partition(b"?")[0] != base.raw_path
            ):
                raise GraphError("invalid_response")

    def snapshot(self) -> DirectorySnapshot:
        users: dict[str, UserRecord] = {}
        groups: dict[str, GroupRecord] = {}
        memberships: set[tuple[str, str]] = set()
        skipped = 0
        for count, item in enumerate(self.pages(
            "/users", "id,displayName,userPrincipalName,mail,accountEnabled,userType,employeeType,"
                      "employeeId,givenName,surname,jobTitle"
        ), 1):
            if count > MAX_OBJECTS:
                raise GraphError("sync_limit")
            key = object_id(item)
            users[key] = {
                "object_id": key, "display_name": optional_text(item, "displayName", 256),
                "principal_name": optional_text(item, "userPrincipalName", 320),
                "user_type": optional_text(item, "userType", 32),
                "employee_type": optional_text(item, "employeeType", 120),
                "employee_number": optional_text(item, "employeeId", 64),
                "given_name": optional_text(item, "givenName", 100),
                "surname": optional_text(item, "surname", 100),
                "job_title": optional_text(item, "jobTitle", 120),
                "mail": optional_text(item, "mail", 320), "account_enabled": optional_bool(item, "accountEnabled"),
            }
        for count, item in enumerate(self.pages("/groups", "id,displayName,securityEnabled"), 1):
            if count > MAX_OBJECTS:
                raise GraphError("sync_limit")
            key = object_id(item)
            groups[key] = {
                "object_id": key, "display_name": optional_text(item, "displayName", 256),
                "security_enabled": optional_bool(item, "securityEnabled"),
            }
        members_read = 0
        for group in groups:
            for member in self.pages(f"/groups/{group}/members", "id", membership=True):
                members_read += 1
                if members_read > MAX_MEMBERSHIPS:
                    raise GraphError("sync_limit")
                kind = member.get("@odata.type")
                if kind is not None and kind != "#microsoft.graph.user":
                    continue
                key = object_id(member)
                if key in users:
                    memberships.add((group, key))
                elif kind == "#microsoft.graph.user":
                    skipped += 1
        return DirectorySnapshot(users, groups, memberships, skipped)
