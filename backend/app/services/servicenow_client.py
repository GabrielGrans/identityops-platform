"""Read approval evidence from a configured ServiceNow instance."""
import re
from typing import Annotated, Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

SysID = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
RITM = Annotated[str, StringConstraints(pattern=r"^RITM[0-9]{1,20}$")]


class ApprovalEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sys_id: SysID
    ritm: RITM
    tenant_id: UUID
    requester_id: SysID
    beneficiary_id: SysID
    approver_id: SysID
    approval_id: SysID
    approval_state: Literal["approved"]
    user_object_id: UUID
    group_object_id: UUID
    operation: Literal["grant", "revoke"]
    justification: Annotated[str, StringConstraints(min_length=8, max_length=1000)]


class ServiceNowError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def instance(config):
    host = config.SERVICENOW_INSTANCE.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}\.service-now\.com", host):
        raise ServiceNowError(503, "ServiceNow integration is not configured.")
    return host


def fetch_approval(config, sys_id: str) -> ApprovalEvidence:
    host = instance(config)
    password = config.SERVICENOW_READ_PASSWORD.get_secret_value()
    if not config.SERVICENOW_READ_USER or not password:
        raise ServiceNowError(503, "ServiceNow integration is not configured.")
    uri = f"https://{host}/api/{config.SERVICENOW_API_NAMESPACE}/approval/v1/ritm/{sys_id}"
    try:
        with httpx.Client(auth=(config.SERVICENOW_READ_USER, password), timeout=8,
                          follow_redirects=False, trust_env=False) as client:
            response = client.get(uri, headers={"Accept": "application/json"})
    except httpx.HTTPError:
        raise ServiceNowError(502, "ServiceNow approval evidence is temporarily unavailable.") from None
    if response.status_code in (404, 409):
        raise ServiceNowError(409, "ServiceNow approval is missing or no longer valid.")
    if response.status_code != 200:
        raise ServiceNowError(502, "ServiceNow approval evidence is temporarily unavailable.")
    try:
        evidence = ApprovalEvidence.model_validate(response.json()["result"])
    except (TypeError, ValueError, KeyError, ValidationError):
        raise ServiceNowError(409, "ServiceNow returned invalid approval evidence.") from None
    if (evidence.sys_id != sys_id or evidence.approver_id in (evidence.requester_id, evidence.beneficiary_id)
            or str(evidence.tenant_id) != config.entra_tenant):
        raise ServiceNowError(409, "ServiceNow approval is missing or no longer valid.")
    return evidence
