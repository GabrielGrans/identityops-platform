import sys
from getpass import getpass

from backend.app.core.database import SessionLocal
from backend.app.core.security import hash_password
from backend.app.models.employee import Employee


def main():
    if len(sys.argv) != 2:
        print(
            "Usage: python -m "
            "backend.app.scripts.set_employee_password EMPLOYEE_ID"
        )
        return

    try:
        employee_id = int(sys.argv[1])
    except ValueError:
        print("Employee ID must be a number.")
        return

    password = getpass("New password: ")
    confirmation = getpass("Confirm password: ")

    if password != confirmation:
        print("Passwords do not match.")
        return

    if len(password) < 12:
        print("Password must contain at least 12 characters.")
        return

    db = SessionLocal()

    try:
        employee = db.get(Employee, employee_id)

        if employee is None:
            print("Employee not found.")
            return

        employee.password_hash = hash_password(password)

        db.commit()

        print(
            f"Password successfully configured for "
            f"{employee.email} (ID: {employee.id})."
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()
