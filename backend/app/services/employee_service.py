from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.models.department import Department
from backend.app.models.employee import Employee


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
            Employee.email == str(data["email"]),
        )
    )

    if employee_id is not None:
        statement = statement.where(Employee.id != employee_id)

    duplicate = db.scalar(statement)

    if duplicate:
        if duplicate.employee_number == data["employee_number"]:
            raise ValueError("Employee number already exists")

        raise ValueError("Email address already exists")


def create_employee(db: Session, data: dict):
    validate_relationships(
        db,
        data.get("department_id"),
        data.get("manager_id"),
    )

    validate_unique_fields(db, data)

    employee = Employee(**data)

    db.add(employee)
    db.commit()
    db.refresh(employee)

    return employee


def update_employee(
    db: Session,
    employee: Employee,
    data: dict,
):
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

    db.commit()
    db.refresh(employee)

    return employee


def deactivate_employee(db: Session, employee: Employee):
    employee.status = "inactive"

    db.commit()
    db.refresh(employee)

    return employee
