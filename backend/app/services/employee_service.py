from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.models.department import Department
from backend.app.models.employee import Employee


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

    if manager_id is not None:
        manager = db.get(Employee, manager_id)

        if manager is None or manager.status != "active":
            raise ValueError("Manager not found or inactive")

        if employee_id is not None and manager_id == employee_id:
            raise ValueError("An employee cannot be their own manager")


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
    validate_relationships(
        db,
        data.get("department_id"),
        data.get("manager_id"),
        employee.id,
    )

    validate_unique_fields(db, data, employee.id)

    for field, value in data.items():
        setattr(employee, field, value)

    db.commit()
    db.refresh(employee)

    return employee


def deactivate_employee(db: Session, employee: Employee):
    employee.status = "inactive"

    db.commit()
    db.refresh(employee)

    return employee
