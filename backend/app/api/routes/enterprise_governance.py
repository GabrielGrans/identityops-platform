from collections import Counter
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import inspect, select

from backend.app.api.routes.entra import Config, DB, migrated
from backend.app.core.authorization import effective_permissions, require_permission
from backend.app.models.employee import Employee
from backend.app.models.group import Group
from backend.app.models.permission import Permission
from backend.app.services.audit_service import record_event
from backend.app.services.enterprise_governance import evaluate, policy_table

router = APIRouter(prefix="/governance", tags=["Enterprise governance"])
Reader = Annotated[Employee, Depends(require_permission("governance:read"))]
Manager = Annotated[Employee, Depends(require_permission("governance:manage"))]
PositiveId = Annotated[int, Field(gt=0, le=2147483647)]
PermissionCode = Annotated[str, Field(min_length=2, max_length=100)]


class PrivilegedGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group_id: PositiveId
    allowed_employee_ids: list[PositiveId] = Field(default_factory=list, max_length=250)


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_permissions: int | None = Field(default=None, ge=1, le=10000)
    privileged_groups: list[PrivilegedGroup] = Field(default_factory=list, max_length=100)
    review_max_age_days: int = Field(default=30, ge=1, le=365)
    conflicts: list[tuple[PermissionCode, PermissionCode]] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_rules(self):
        group_ids = [rule.group_id for rule in self.privileged_groups]
        pairs = {tuple(sorted(pair)) for pair in self.conflicts}
        if len(set(group_ids)) != len(group_ids) or len(pairs) != len(self.conflicts):
            raise ValueError("Policy rules must be unique")
        if any(left == right for left, right in pairs):
            raise ValueError("A conflict requires two different permissions")
        return self



Rule = Literal["inactive_access", "overdue_review", "excessive_permissions",
               "privileged_access", "segregation_of_duties", "entra_mismatch"]


class Finding(BaseModel):
    rule: Rule
    employee_id: int
    evidence: dict[str, int | str | list[int] | list[str]]


class FindingsResponse(BaseModel):
    counts: dict[Rule, int]
    entra_state: Literal["evaluated", "unavailable"]
    evaluated_rules: list[Rule]
    total: int
    items: list[Finding]

def read_policy(db, *, lock=False):
    if not inspect(db.connection()).has_table(policy_table.name):
        raise HTTPException(503, "Run the enterprise governance database migration")
    statement = select(policy_table.c.rules).where(policy_table.c.id == 1)
    rules = db.scalar(statement.with_for_update() if lock else statement)
    if rules is None:
        raise HTTPException(503, "The governance policy has not been initialized")
    return Policy.model_validate(rules)


@router.get("/policy", response_model=Policy)
def get_policy(db: DB, actor: Reader):
    return read_policy(db)


@router.put("/policy", response_model=Policy)
def update_policy(data: Policy, db: DB, actor: Manager):
    old = read_policy(db, lock=True)
    references = (
        (Group.id, {row.group_id for row in data.privileged_groups}),
        (Employee.id, {id_ for row in data.privileged_groups for id_ in row.allowed_employee_ids}),
        (Permission.code, {code for pair in data.conflicts for code in pair}),
    )
    for field, values in references:
        if values and set(db.scalars(select(field).where(field.in_(values)))) != values:
            raise HTTPException(400, "Policy refers to an unknown employee, group or permission")
    before, after = old.model_dump(mode="json"), data.model_dump(mode="json")
    if before != after:
        db.execute(policy_table.update().where(policy_table.c.id == 1).values(rules=after))
        record_event(db, actor.id, "governance.policy.updated", "enterprise_governance_policy", 1,
                     before=before, after=after)
        db.commit()
    return data


@router.get("/findings", response_model=FindingsResponse)
def get_findings(
    db: DB, actor: Reader, config: Config,
    offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 25,
):
    policy = read_policy(db)
    authorized = db.scalar(effective_permissions(actor.id).where(Permission.code == "entra:read")) is not None
    findings, state = evaluate(db, policy, config.entra_tenant, authorized and bool(config.entra_tenant) and migrated(db))
    available = ["inactive_access", "overdue_review"]
    if policy.max_permissions is not None:
        available.append("excessive_permissions")
    if policy.privileged_groups:
        available.append("privileged_access")
    if policy.conflicts:
        available.append("segregation_of_duties")
    if state == "evaluated":
        available.append("entra_mismatch")
    return {"counts": dict(Counter(row["rule"] for row in findings)), "entra_state": state, "evaluated_rules": available,
            "total": len(findings), "items": findings[offset:offset + limit]}
