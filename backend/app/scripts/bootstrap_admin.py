import argparse
from getpass import getpass

from sqlalchemy import select, text

from backend.app.core.database import SessionLocal
from backend.app.core.security import hash_password
from backend.app.models import Employee, Group
from backend.app.schemas.employee import EmployeeCreate
from backend.app.scripts.seed_permissions import assign_default_permissions
from backend.app.services.audit_service import record_event


def bootstrap_admin(data: EmployeeCreate, password: str):
    with SessionLocal.begin() as db:
        # Serialize the initial setup on PostgreSQL across CLI processes.
        db.execute(text("LOCK TABLE employees IN SHARE ROW EXCLUSIVE MODE"))
        if db.scalar(select(Employee.id).limit(1)) is not None:
            raise ValueError("Bootstrap requires an empty employee directory.")
        group = db.scalar(select(Group).where(Group.name == "IT Administrators"))
        if group is None:
            group = Group(name="IT Administrators", code="IT_ADMINS")
            db.add(group)
            db.flush()
        if not group.is_active:
            raise ValueError("IT Administrators group is inactive.")

        assign_default_permissions(db, group)
        employee = Employee(**data.model_dump(), password_hash=hash_password(password), groups=[group])
        db.add(employee)
        db.flush()
        record_event(db, None, "system.admin.bootstrapped", "employees", employee.id, group_id=group.id)
        return employee.id


def main():
    parser = argparse.ArgumentParser(description="Create the first IdentityOps administrator")
    parser.add_argument("email")
    parser.add_argument("--number", default="ADMIN001")
    parser.add_argument("--first-name", default="IdentityOps")
    parser.add_argument("--last-name", default="Administrator")
    args = parser.parse_args()
    try:
        data = EmployeeCreate(
            employee_number=args.number, first_name=args.first_name, last_name=args.last_name,
            email=args.email, job_title="IAM Administrator",
        )
        password = getpass("New administrator password: ")
        if len(password) < 12 or password != getpass("Confirm administrator password: "):
            parser.error("Passwords must match and contain at least 12 characters.")
        employee_id = bootstrap_admin(data, password)
    except ValueError as error:
        parser.error(str(error))
    print(f"Administrator created (employee ID {employee_id}).")


if __name__ == "__main__":
    main()
