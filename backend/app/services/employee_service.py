from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.authorization import group_codes, require_delegation
from backend.app.core.security import hash_password
from backend.app.models.department import Department
from backend.app.models.employee import Employee
from backend.app.models.governance import AccessRequest, AccessReview
from backend.app.services.access_state import close_pending, lock_employee, lock_group
from backend.app.services.audit_service import commit_change, record_event


EMPLOYEE_UPDATE_FIELDS = {
    "employee_number",
    "first_name",
    "last_name",
    "email",
    "job_title",
    "department_id",
    "manager_id",
}


def list_employees(
    db: Session,
    department_id: int | None = None,
    status: str | None = None,
):
    statement = select(Employee).order_by(Employee.id)

    if department_id is not None:
        statement = statement.where(
            Employee.department_id == department_id
        )

    if status is not None:
        statement = statement.where(Employee.status == status)

    return db.scalars(statement).all()


def get_employee(db: Session, employee_id: int):
    return db.get(Employee, employee_id)


def lock_reporting_hierarchy(db: Session):
    if db.get_bind().dialect.name == "postgresql":
        # Manager chains span multiple rows and must be validated serially.
        db.execute(text("SELECT pg_advisory_xact_lock(57223, 1)"))


def validate_relationships(
    db: Session,
    department_id: int | None,
    manager_id: int | None,
    employee_id: int | None = None,
):
    if department_id is not None:
        department = db.get(Department, department_id)

        if department is None or not department.is_active:
            raise ValueError("Department not found or inactive")

    if manager_id is None:
        return

    manager = db.get(Employee, manager_id)

    if manager is None or manager.status != "active":
        raise ValueError("Manager not found or inactive")

    if employee_id is None:
        return

    if manager_id == employee_id:
        raise ValueError("An employee cannot be their own manager")

    visited_manager_ids = {manager_id}
    current_manager_id = manager.manager_id

    while current_manager_id is not None:
        if current_manager_id == employee_id:
            raise ValueError(
                "Manager assignment would create a reporting hierarchy cycle"
            )

        if current_manager_id in visited_manager_ids:
            raise ValueError(
                "Existing manager hierarchy contains a cycle"
            )

        visited_manager_ids.add(current_manager_id)

        current_manager = db.get(Employee, current_manager_id)

        if current_manager is None:
            break

        current_manager_id = current_manager.manager_id


def validate_unique_fields(
    db: Session,
    data: dict,
    employee_id: int | None = None,
):
    statement = select(Employee).where(
        or_(
            Employee.employee_number == data["employee_number"],
            func.lower(func.trim(Employee.email)) == str(data["email"]).strip().lower(),
        )
    )

    if employee_id is not None:
        statement = statement.where(Employee.id != employee_id)

    duplicate = db.scalar(statement)

    if duplicate:
        if duplicate.employee_number == data["employee_number"]:
            raise ValueError("Employee number already exists")

        raise ValueError("Email address already exists")


def save_employee(db: Session, actor_id: int | None, action: str, employee: Employee):
    try:
        commit_change(db, actor_id, action, employee)
    except IntegrityError:
        db.rollback()
        raise ValueError("The employee record conflicts with existing data") from None


def password_hash_for(password: str) -> str:
    if not 12 <= len(password) <= 128 or len(password.strip()) == 0:
        raise ValueError("Use a password of 12 to 128 characters with at least one non-space character")
    return hash_password(password)


def create_employee(
    db: Session, data: dict, actor_id: int | None = None, *, password: str | None = None, group_ids=(),
):
    lock_reporting_hierarchy(db)
    validate_relationships(
        db,
        data.get("department_id"),
        data.get("manager_id"),
    )

    validate_unique_fields(db, data)

    groups = []
    if group_ids:
        require_delegation(db, actor_id, (), "access:manage")
        if data.get("status", "active") != "active":
            raise ValueError("Cannot assign groups to an inactive employee")
        for group_id in sorted(set(group_ids)):
            group = lock_group(db, group_id)
            if group is None or not group.is_active:
                raise ValueError("Group not found or inactive")
            groups.append(group)
        require_delegation(db, actor_id, group_codes(groups), "access:manage")
    hashed = None
    if password is not None:
        require_delegation(db, actor_id, (), "employees:reset_password")
        hashed = password_hash_for(password)
    employee = Employee(**data, password_hash=hashed, groups=groups)
    db.add(employee)
    if actor_id is not None and (groups or hashed is not None):
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise ValueError("The employee record conflicts with existing data") from None
        if hashed is not None:
            record_event(db, actor_id, "employee.password.set", "employees", employee.id)
        for group in groups:
            record_event(db, actor_id, "employee.group.assigned", "employees", employee.id, group_id=group.id)
    save_employee(db, actor_id, "employee.create", employee)

    return employee


def update_employee(
    db: Session,
    employee: Employee,
    data: dict,
    actor_id: int | None = None,
):
    lock_reporting_hierarchy(db)
    employee = lock_employee(db, employee.id)
    update_data = {
        field: value
        for field, value in data.items()
        if field in EMPLOYEE_UPDATE_FIELDS
    }

    validate_relationships(
        db,
        update_data.get("department_id"),
        update_data.get("manager_id"),
        employee.id,
    )

    validate_unique_fields(db, update_data, employee.id)

    for field, value in update_data.items():
        setattr(employee, field, value)

    save_employee(db, actor_id, "employee.update", employee)

    return employee


def deactivate_employee(db: Session, employee: Employee, actor_id: int | None = None):
    lock_reporting_hierarchy(db)
    employee = lock_employee(db, employee.id)
    for model in (AccessRequest, AccessReview):
        close_pending(db, model, actor_id, "Employee deactivated", employee_id=employee.id)
    employee.status = "inactive"

    commit_change(db, actor_id, "employee.deactivate", employee)

    return employee

def activate_employee(db: Session, employee_id: int, actor_id: int):
    lock_reporting_hierarchy(db)
    employee = lock_employee(db, employee_id)
    if employee is None:
        raise LookupError("Employee not found")
    groups = [lock_group(db, group_id) for group_id in sorted(group.id for group in employee.groups)]
    require_delegation(db, actor_id, group_codes(groups), "employees:update")
    if employee.status != "active":
        employee.status = "active"
        save_employee(db, actor_id, "employee.activate", employee)
    return employee


def set_employee_password(db: Session, employee_id: int, actor_id: int, password: str):
    employee = lock_employee(db, employee_id)
    if employee is None:
        raise LookupError("Employee not found")
    groups = [lock_group(db, group_id) for group_id in sorted(group.id for group in employee.groups)]
    require_delegation(db, actor_id, group_codes(groups), "employees:reset_password")
    action = "employee.password.reset" if employee.password_hash else "employee.password.set"
    employee.password_hash = password_hash_for(password)
    save_employee(db, actor_id, action, employee)
