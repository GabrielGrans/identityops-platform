from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.models.department import Department
from backend.app.services.audit_service import commit_change
from backend.app.services.department_catalog import department_key


def list_departments(db: Session):
    statement = select(Department).order_by(Department.name)
    return db.scalars(statement).all()


def get_department(db: Session, department_id: int):
    return db.get(Department, department_id)


def ensure_unique(db, data, exclude=None):
    if not department_key(data["name"]) or not department_key(data["code"]):
        raise ValueError("Department name and code are required")
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("LOCK TABLE departments IN SHARE ROW EXCLUSIVE MODE"))
    for row in db.scalars(select(Department).where(Department.id != exclude) if exclude else select(Department)):
        if (department_key(row.name) == department_key(data["name"]) or
                department_key(row.code) == department_key(data["code"])):
            raise ValueError("Department name or code already exists")


def create_department(db: Session, data: dict, actor_id: int | None = None):
    ensure_unique(db, data)
    data = {**data, "name": data["name"].strip(), "code": data["code"].strip()}
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
    ensure_unique(db, data, department.id)
    data = {**data, "name": data["name"].strip(), "code": data["code"].strip()}
    for field, value in data.items():
        setattr(department, field, value)

    commit_change(db, actor_id, "department.update", department)

    return department


def deactivate_department(db: Session, department: Department, actor_id: int | None = None):
    department.is_active = False

    commit_change(db, actor_id, "department.deactivate", department)

    return department
