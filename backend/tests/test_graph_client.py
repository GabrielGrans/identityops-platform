from urllib.parse import parse_qs
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr

from backend.app.core.config import Settings
from backend.app.services import graph_client
from backend.app.services.graph_client import GRAPH_URL, GraphClient, GraphConfig, GraphError, TokenCache


TENANT = str(UUID(int=1))
APP = str(UUID(int=2))
USER = str(UUID(int=3))
GROUP = str(UUID(int=4))
TOKEN = "unit-test-token"
TOKEN_BODY = {"token_type": "Bearer", "access_token": TOKEN, "expires_in": 3600}
CONFIG = GraphConfig(TENANT, APP, SecretStr("unit-test-placeholder"))


def mock_http(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), trust_env=False, follow_redirects=False)


def test_client_credentials_cached_pagination_and_memberships():
    requests = []

    def respond(request):
        requests.append(request)
        if request.method == "POST":
            assert str(request.url) == f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
            assert parse_qs(request.content.decode()) == {
                "grant_type": ["client_credentials"], "client_id": [APP],
                "client_secret": ["unit-test-placeholder"], "scope": ["https://graph.microsoft.com/.default"],
            }
            return httpx.Response(200, json=TOKEN_BODY)

        assert request.method == "GET"
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        match request.url.path:
            case "/v1.0/users":
                if request.url.params.get("$skiptoken"):
                    return httpx.Response(200, json={"value": [{"id": USER, "displayName": "Fixture", "accountEnabled": False}]})
                assert "userPrincipalName" in request.url.params["$select"]
                return httpx.Response(200, json={"value": [], "@odata.nextLink": f"{GRAPH_URL}/users?$skiptoken=page2"})
            case "/v1.0/groups":
                return httpx.Response(200, json={"value": [{"id": GROUP, "securityEnabled": True}]})
            case _:
                assert request.url.path == f"/v1.0/groups/{GROUP}/members"
                return httpx.Response(200, json={"value": [
                    {"id": USER, "@odata.type": "#microsoft.graph.user"},
                    {"id": APP, "@odata.type": "#microsoft.graph.user"},
                    {"id": TENANT, "@odata.type": "#microsoft.graph.servicePrincipal"},
                ]})

    cache = TokenCache()
    with mock_http(respond) as client:
        first = GraphClient(CONFIG, client, cache)
        snapshot = first.snapshot()
        assert snapshot.users[USER]["account_enabled"] is False
        assert snapshot.groups[GROUP]["security_enabled"] is True
        assert snapshot.memberships == {(GROUP, USER)}
        assert snapshot.skipped_users == 1
        assert GraphClient(CONFIG, client, cache).token() == TOKEN
        assert len([request for request in requests if request.method == "POST"]) == 1
        cache.expires_at = 0
        assert GraphClient(CONFIG, client, cache).token() == TOKEN
        assert len([request for request in requests if request.method == "POST"]) == 2


@pytest.mark.parametrize("url", [
    "https://example.invalid/v1.0/users?cursor=1",
    "https://graph.microsoft.com.evil.invalid/v1.0/users",
    "http://graph.microsoft.com/v1.0/users",
    "https://graph.microsoft.com@evil.invalid/v1.0/users",
    "https://graph.microsoft.com/v1.0/groups",
    "https://graph.microsoft.com/v1.0/users#fragment",
])
def test_rejects_unsafe_next_links(url):
    locations = []

    def respond(request):
        locations.append(request.url.host)
        return httpx.Response(200, json=TOKEN_BODY if request.method == "POST" else {"value": [], "@odata.nextLink": url})

    with mock_http(respond) as http, pytest.raises(GraphError, match="validate"):
        list(GraphClient(CONFIG, http, TokenCache()).pages("/users", "id"))
    assert locations == ["login.microsoftonline.com", "graph.microsoft.com"]


def test_retries_and_honors_retry_after(monkeypatch):
    sleeps = []
    responses = iter([httpx.Response(503), httpx.Response(429, headers={"Retry-After": "3"}), httpx.Response(200, json={"value": []})])
    monkeypatch.setattr(graph_client, "sleep", sleeps.append)
    with mock_http(lambda request: httpx.Response(200, json=TOKEN_BODY) if request.method == "POST" else next(responses)) as http:
        assert list(GraphClient(CONFIG, http, TokenCache()).pages("/users", "id")) == []
    assert sleeps == [0.5, 3]


def test_throttling_with_long_delay_fails_without_retry(monkeypatch):
    monkeypatch.setattr(graph_client, "sleep", lambda _: pytest.fail("unexpected retry"))
    with mock_http(lambda request: httpx.Response(200, json=TOKEN_BODY) if request.method == "POST" else
                   httpx.Response(429, headers={"Retry-After": "30"})) as http:
        with pytest.raises(GraphError) as raised:
            list(GraphClient(CONFIG, http, TokenCache()).pages("/users", "id"))
    assert (raised.value.code, raised.value.retry_after) == ("graph_throttled", 30)


@pytest.mark.parametrize(("phase", "status", "code"), [
    ("token", 400, "token_rejected"),
    ("directory", 401, "graph_unauthorized"),
    ("directory", 403, "graph_forbidden"),
    ("membership", 403, "membership_forbidden"),
    ("directory", 302, "invalid_response"),
])
def test_errors_hide_upstream_bodies_and_do_not_follow_redirects(phase, status, code):
    def respond(request):
        if request.method == "POST" and phase != "token":
            return httpx.Response(200, json=TOKEN_BODY)
        return httpx.Response(status, json={"error_description": "private-upstream-message"},
                              headers={"Location": "https://example.invalid"})
    with mock_http(respond) as http, pytest.raises(GraphError) as raised:
        graph = GraphClient(CONFIG, http, TokenCache())
        list(graph.pages("/users" if phase != "membership" else f"/groups/{GROUP}/members", "id", membership=phase == "membership"))
    assert raised.value.code == code
    assert "private-upstream-message" not in str(raised.value)


def test_configuration_disabled_missing_and_untrusted_base():
    base = {"SECRET_KEY": "unit-test-only", "_env_file": None, "ENTRA_ENABLED": True,
            "AZURE_TENANT_ID": TENANT, "AZURE_CLIENT_ID": APP, "AZURE_CLIENT_SECRET": "unit-test-placeholder"}
    assert GraphConfig.from_settings(Settings(**base)).tenant_id == TENANT
    for changes, code in [
        ({"ENTRA_ENABLED": False}, "disabled"),
        ({"AZURE_TENANT_ID": ""}, "invalid_configuration"),
        ({"AZURE_CLIENT_SECRET": ""}, "invalid_configuration"),
        ({"ENTRA_GRAPH_BASE_URL": "https://example.invalid/v1.0"}, "invalid_configuration"),
    ]:
        with pytest.raises(GraphError) as raised:
            GraphConfig.from_settings(Settings(**(base | changes)))
        assert raised.value.code == code


def test_request_budget_bounds_pagination(monkeypatch):
    monkeypatch.setattr(graph_client, "MAX_REQUESTS", 2)
    with mock_http(lambda request: httpx.Response(200, json=TOKEN_BODY if request.method == "POST" else
                   {"value": [], "@odata.nextLink": f"{GRAPH_URL}/users?next=2"})) as http:
        with pytest.raises(GraphError) as raised:
            list(GraphClient(CONFIG, http, TokenCache()).pages("/users", "id"))
    assert raised.value.code == "sync_limit"


def test_transport_failures_retry_only_twice(monkeypatch):
    delays = []
    monkeypatch.setattr(graph_client, "sleep", delays.append)

    def respond(request):
        raise httpx.ReadTimeout("private-error", request=request)

    with mock_http(respond) as http, pytest.raises(GraphError) as raised:
        GraphClient(CONFIG, http, TokenCache()).token()
    assert raised.value.code == "graph_unavailable"
    assert delays == [0.5, 1]
