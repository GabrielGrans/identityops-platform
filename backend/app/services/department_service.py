from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.models.department import Department
from backend.app.services.audit_service import commit_change


def list_departments(db: Session):
    statement = select(Department).order_by(Department.name)
    return db.scalars(statement).all()


def get_department(db: Session, department_id: int):
    return db.get(Department, department_id)


def create_department(db: Session, data: dict, actor_id: int | None = None):
    duplicate = db.scalar(
        select(Department).where(
            or_(
                Department.name == data["name"],
                Department.code == data["code"],
            )
        )
    )

    if duplicate:
        raise ValueError("Department name or code already exists")

    department = Department(**data)

    db.add(department)
    commit_change(db, actor_id, "department.create", department)

    return department


def update_department(
    db: Session,
    department: Department,
    data: dict,
    actor_id: int | None = None,
):
    duplicate = db.scalar(
        select(Department).where(
            or_(
                Department.name == data["name"],
                Department.code == data["code"],
            ),
            Department.id != department.id,
        )
    )

    if duplicate:
        raise ValueError("Department name or code already exists")

    for field, value in data.items():
        setattr(department, field, value)

    commit_change(db, actor_id, "department.update", department)

    return department


def deactivate_department(db: Session, department: Department, actor_id: int | None = None):
    department.is_active = False

    commit_change(db, actor_id, "department.deactivate", department)

    return department
