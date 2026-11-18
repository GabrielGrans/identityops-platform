from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.database import SessionLocal
from backend.app.models.associations import group_permissions
from backend.app.models.group import Group
from backend.app.models.permission import Permission
from backend.app.services.access_state import lock_group, reset_group_policy
from backend.app.services.audit_service import record_event


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
    {
        "name": "View Audit Events",
        "code": "audit:read",
        "resource": "audit",
        "action": "read",
        "description": "Allows viewing IAM audit events.",
    },
    {
        "name": "Manage Access Reviews",
        "code": "reviews:manage",
        "resource": "reviews",
        "action": "manage",
        "description": "Allows opening reviews and retaining or revoking memberships.",
    },
    {
        "name": "View Entra Directory",
        "code": "entra:read",
        "resource": "entra",
        "action": "read",
        "description": "Allows viewing the Entra snapshot and synchronization history.",
    },
    {
        "name": "Synchronize Entra Directory",
        "code": "entra:sync",
        "resource": "entra",
        "action": "sync",
        "description": "Allows importing a read-only Microsoft Graph snapshot.",
    },
    {
        "name": "Manage Entra Links",
        "code": "entra:manage_links",
        "resource": "entra",
        "action": "manage_links",
        "description": "Allows explicitly linking directory objects to local IAM records.",
    },
]


def assign_default_permissions(db: Session, admin_group: Group):
    created_count = 0
    assigned_count = 0
    reactivated_ids = []
    for definition in PERMISSIONS:
        permission = db.scalar(select(Permission).where(Permission.code == definition["code"]))
        if permission is None:
            permission = Permission(**definition)
            db.add(permission)
            db.flush()
            created_count += 1
        elif not permission.is_active:
            permission.is_active = True
            reactivated_ids.append(permission.id)

        if permission not in admin_group.permissions:
            admin_group.permissions.append(permission)
            assigned_count += 1

    group_ids = {admin_group.id} if assigned_count else set()
    if reactivated_ids:
        group_ids.update(db.scalars(
            select(group_permissions.c.group_id).where(group_permissions.c.permission_id.in_(reactivated_ids))
        ).all())
    if group_ids:
        db.flush()
        for group_id in sorted(group_ids):
            lock_group(db, group_id)
            reset_group_policy(db, group_id, None)

    return created_count, assigned_count


def seed_permissions():
    with SessionLocal.begin() as db:
        admin_group = db.scalar(select(Group).where(Group.name == "IT Administrators"))
        if admin_group is None:
            raise RuntimeError("IT Administrators group was not found. No permissions were changed.")
        created, assigned = assign_default_permissions(db, admin_group)
        record_event(
            db, None, "system.permissions.seeded", "groups", admin_group.id,
            created=created, assigned=assigned,
        )

    print(f"Permission seeding completed. Created: {created}. New assignments: {assigned}.")


if __name__ == "__main__":
    seed_permissions()
