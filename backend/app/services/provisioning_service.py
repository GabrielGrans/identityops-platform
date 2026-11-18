from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.models.department import Department
from backend.app.models.employee import Employee
from backend.app.models.entra import EntraSyncRun, EntraUser
from backend.app.schemas.provisioning import Outcome, Proposal, ReconciliationRequest, ReconciliationResult, valid_employee
from backend.app.services.audit_service import record_event


MAX_AGE = timedelta(hours=24)
EMAIL = TypeAdapter(EmailStr)
ELIGIBLE = {"eligible_for_creation", "eligible_for_link"}


def clean(value: str | None) -> str | None:
    return (value.strip() or None) if value else None


def normalized_email(value: str | None) -> str | None:
    try:
        return str(EMAIL.validate_python(clean(value))).lower()
    except ValidationError:
        return None


def snapshot_is_recent(run: EntraSyncRun | None) -> bool:
    if run is None or run.finished_at is None:
        return False
    end = run.finished_at
    if end.tzinfo is None:  # SQLite development fixtures store UTC without offsets.
        end = end.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - MAX_AGE <= end <= datetime.now(timezone.utc)


def external_projection(user: EntraUser, item) -> Proposal:
    return Proposal(
        email=normalized_email(user.mail),
        employee_number=item.employee_number or clean(user.employee_number),
        first_name=item.first_name or clean(user.given_name),
        last_name=item.last_name or clean(user.surname),
        job_title=item.job_title or clean(user.job_title),
        department_id=item.department_id,
    )


def inspect_batch(db: Session, tenant: str, data: ReconciliationRequest, *, execute: bool = False):
    by_object = {str(item.object_id): item for item in data.items}
    statement = select(EntraUser).where(
        EntraUser.tenant_id == tenant, EntraUser.object_id.in_(by_object),
    ).order_by(EntraUser.object_id)
    if execute:
        statement = statement.with_for_update()
    users = {row.object_id: row for row in db.scalars(statement)}
    run = db.scalar(select(EntraSyncRun).where(
        EntraSyncRun.tenant_id == tenant, EntraSyncRun.status == "completed",
    ).order_by(EntraSyncRun.id.desc()).limit(1))
    recent = snapshot_is_recent(run)
    expected_run = getattr(data, "snapshot_run_id", None)
    proposals = {
        key: external_projection(user, by_object[key]) for key, user in users.items()
    }
    mail_set = {value.email for value in proposals.values() if value.email}
    numbers = {value.employee_number for value in proposals.values() if value.employee_number}
    departments = {value.department_id for value in proposals.values() if value.department_id is not None}
    department_query = select(Department).where(Department.id.in_(departments)).order_by(Department.id)
    if execute:
        department_query = department_query.with_for_update(key_share=True)
    active_departments = {row.id for row in db.scalars(department_query) if row.is_active}
    existing = (
        select(Employee.id, Employee.email, Employee.employee_number)
        .where(or_(func.lower(func.trim(Employee.email)).in_(mail_set), Employee.employee_number.in_(numbers)))
        .order_by(Employee.id)
    )
    if execute:
        existing = existing.with_for_update(key_share=True)
    by_email = defaultdict(list)
    used_numbers = set()
    for local_id, email, number in db.execute(existing):
        by_email[email.strip().lower()].append(local_id)
        used_numbers.add(number)

    selected_matches = {item.local_employee_id for item in data.items if item.local_employee_id is not None}
    linked_targets = set(db.scalars(select(EntraUser.local_employee_id).where(
        EntraUser.tenant_id == tenant, EntraUser.local_employee_id.in_(selected_matches),
    )))
    outcomes = []
    for item in data.items:
        key = str(item.object_id)
        user = users.get(key)
        proposal = proposals.get(key)
        outcome = Outcome(object_id=item.object_id, action=item.action, status="unavailable_snapshot", proposal=proposal)
        outcomes.append(outcome)
        if user is None or not user.present:
            outcome.messages.append("This identity is unavailable in the current tenant snapshot.")
        elif user.local_employee_id is not None:
            outcome.local_employee_id = user.local_employee_id
            if item.action == "link" and item.local_employee_id != user.local_employee_id:
                outcome.status = "validation_conflict"
                outcome.messages.append("Unlink the existing mapping explicitly before choosing another employee.")
            else:
                outcome.status = "already_linked"
                outcome.messages.append("This identity already has a local link. No changes will be made.")
        elif not recent or user.last_seen_run_id != run.id or (execute and expected_run != run.id):
            outcome.messages.append("Refresh the Entra snapshot and preview the batch again.")
        elif (
            (user.user_type or "").strip().lower() != "member"
            or user.account_enabled is not True
            or ((user.employee_type or "").strip().lower() != "employee"
                and (clean(user.employee_type) is not None or not clean(user.employee_number)))
        ):
            outcome.status = "unsupported_identity_type"
            outcome.messages.append("An enabled Member with corroborating employee metadata is required. Guests, non-employees and unclassified accounts are blocked.")
        elif execute and not item.person_verified:
            outcome.status = "validation_conflict"
            outcome.messages.append("Confirm that this identity belongs to a person before applying.")
        elif proposal.email is None or len(proposal.email) > 255:
            outcome.status = "missing_required_data"
            outcome.messages.append("A valid Entra mail address is required. The sign-in name is not used as a substitute.")
        else:
            outcome.matching_employee_ids = by_email[proposal.email]
            if item.action == "link":
                if len(outcome.matching_employee_ids) == 1 and outcome.matching_employee_ids[0] == item.local_employee_id:
                    if item.local_employee_id in linked_targets:
                        outcome.status = "validation_conflict"
                        outcome.messages.append("This employee is already linked to another object in this tenant.")
                    else:
                        outcome.status = "eligible_for_link"
                else:
                    outcome.status = "potential_duplicate" if outcome.matching_employee_ids else "validation_conflict"
                    outcome.messages.append("Select the single employee with a matching normalized email. No employee fields will be changed.")
            elif outcome.matching_employee_ids:
                outcome.status = "potential_duplicate"
                outcome.messages.append("A local employee has this email. Review the match before linking explicitly.")
            elif proposal.employee_number in used_numbers:
                outcome.status = "validation_conflict"
                outcome.messages.append("This employee number is already in use.")
            elif item.department_id is not None and item.department_id not in active_departments:
                outcome.status = "validation_conflict"
                outcome.messages.append("The chosen department is missing or inactive.")
            else:
                try:
                    valid_employee(proposal)
                except ValidationError as error:
                    outcome.status = "missing_required_data"
                    fields = ", ".join(sorted({str(issue["loc"][0]) for issue in error.errors()}))
                    outcome.messages.append(f"Supply valid employee fields: {fields}.")
                else:
                    outcome.status = "eligible_for_creation"
    eligible = [outcome for outcome in outcomes if outcome.status in ELIGIBLE]
    emails = Counter(outcome.proposal.email for outcome in eligible)
    creation_numbers = Counter(outcome.proposal.employee_number for outcome in eligible if outcome.action == "create")
    for outcome in eligible:
        if emails[outcome.proposal.email] > 1 or (
            outcome.action == "create" and creation_numbers[outcome.proposal.employee_number] > 1
        ):
            outcome.status = "validation_conflict"
            outcome.messages.append("This batch contains repeated emails or employee numbers.")
    return ReconciliationResult(snapshot_run_id=run.id if run else None, items=outcomes), users


def audit_rejection(db: Session, actor_id: int, tenant: str, result: ReconciliationResult):
    record_event(db, actor_id, "entra.provision.rejected", "entra_users", None, tenant_id=tenant, outcomes=[
        {"object_id": str(outcome.object_id), "status": outcome.status, "employee_id": outcome.local_employee_id}
        for outcome in result.items
    ])


def apply_batch(db: Session, actor_id: int, tenant: str, data):
    result, users = inspect_batch(db, tenant, data, execute=True)
    if any(outcome.status not in {*ELIGIBLE, "already_linked"} for outcome in result.items):
        audit_rejection(db, actor_id, tenant, result)
        db.commit()
        return result

    selected = {item.object_id: item for item in data.items}
    try:
        for outcome in result.items:
            if outcome.status == "already_linked":
                continue
            user = users[str(outcome.object_id)]
            item = selected[outcome.object_id]
            if item.action == "create":
                employee = Employee(**valid_employee(outcome.proposal).model_dump(), status="inactive", password_hash=None)
                db.add(employee)
                db.flush()
                local_id = employee.id
                outcome.status = "created"
            else:
                local_id = item.local_employee_id
                outcome.status = "linked"
            user.local_employee_id = local_id
            outcome.local_employee_id = local_id
            record_event(db, actor_id, f"entra.provision.{outcome.status}", "employees", local_id,
                         tenant_id=tenant, object_id=str(outcome.object_id))
        db.commit()
        result.applied = True
    except IntegrityError:
        db.rollback()
        for outcome in result.items:
            if outcome.status != "already_linked":
                outcome.status = "validation_conflict"
                outcome.local_employee_id = None
                outcome.messages = ["A concurrent edit conflicted with the batch. No changes were applied. Preview again."]
        audit_rejection(db, actor_id, tenant, result)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return result
