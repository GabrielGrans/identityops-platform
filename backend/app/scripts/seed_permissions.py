from sqlalchemy import select

from backend.app.core.database import SessionLocal
from backend.app.models.group import Group
from backend.app.models.permission import Permission


PERMISSIONS = [
    {
        "name": "View Employees",
        "code": "employees:read",
        "resource": "employees",
        "action": "read",
        "description": "Allows viewing employee records.",
    },
    {
        "name": "Create Employees",
        "code": "employees:create",
        "resource": "employees",
        "action": "create",
        "description": "Allows creating employee records.",
    },
    {
        "name": "Update Employees",
        "code": "employees:update",
        "resource": "employees",
        "action": "update",
        "description": "Allows updating employee records.",
    },
    {
        "name": "Deactivate Employees",
        "code": "employees:deactivate",
        "resource": "employees",
        "action": "deactivate",
        "description": "Allows deactivating employee accounts.",
    },
    {
        "name": "View Departments",
        "code": "departments:read",
        "resource": "departments",
        "action": "read",
        "description": "Allows viewing departments.",
    },
    {
        "name": "Manage Departments",
        "code": "departments:manage",
        "resource": "departments",
        "action": "manage",
        "description": "Allows creating, updating and deactivating departments.",
    },
    {
        "name": "View Groups",
        "code": "groups:read",
        "resource": "groups",
        "action": "read",
        "description": "Allows viewing access groups.",
    },
    {
        "name": "Manage Groups",
        "code": "groups:manage",
        "resource": "groups",
        "action": "manage",
        "description": "Allows creating, updating and deactivating access groups.",
    },
    {
        "name": "Manage Access Assignments",
        "code": "access:manage",
        "resource": "access",
        "action": "manage",
        "description": "Allows assigning employees to groups and managing group permissions.",
    },
    {
        "name": "View Permissions",
        "code": "permissions:read",
        "resource": "permissions",
        "action": "read",
        "description": "Allows viewing system permissions.",
    },
    {
        "name": "Manage Permissions",
        "code": "permissions:manage",
        "resource": "permissions",
        "action": "manage",
        "description": "Allows creating, updating and deactivating permissions.",
    },
]


def seed_permissions():
    db = SessionLocal()

    try:
        admin_group = db.scalar(
            select(Group).where(Group.name == "IT Administrators")
        )

        if admin_group is None:
            raise RuntimeError(
                "IT Administrators group was not found. "
                "No permissions were changed."
            )

        created_count = 0
        assigned_count = 0

        for permission_data in PERMISSIONS:
            permission = db.scalar(
                select(Permission).where(
                    Permission.code == permission_data["code"]
                )
            )

            if permission is None:
                permission = Permission(**permission_data)
                db.add(permission)
                db.flush()
                created_count += 1
                print(f"Created permission: {permission.code}")
            else:
                if not permission.is_active:
                    permission.is_active = True
                    print(f"Reactivated permission: {permission.code}")

            if permission not in admin_group.permissions:
                admin_group.permissions.append(permission)
                assigned_count += 1
                print(f"Assigned to IT Administrators: {permission.code}")

        db.commit()

        print("\nPermission seeding completed.")
        print(f"Created: {created_count}")
        print(f"New assignments: {assigned_count}")
        print(f"Total permissions configured: {len(PERMISSIONS)}")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed_permissions()
