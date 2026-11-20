"""Extend the Entra snapshot and persist immutable provisioning subjects."""
from alembic import op
import sqlalchemy as sa

revision = "unified_entra_directory"
down_revision = "entra_automation"


def upgrade():
    op.add_column("entra_users", sa.Column("department", sa.String(256)))
    op.add_column("entra_users", sa.Column("on_premises_sync_enabled", sa.Boolean()))
    op.add_column("entra_groups", sa.Column("description", sa.Text()))
    op.add_column("entra_groups", sa.Column("mail_enabled", sa.Boolean()))
    op.add_column("entra_groups", sa.Column("role_assignable", sa.Boolean()))
    op.add_column("entra_groups", sa.Column("group_types", sa.JSON()))
    op.add_column("entra_groups", sa.Column("on_premises_sync_enabled", sa.Boolean()))
    op.add_column("entra_groups", sa.Column("management_metadata_complete", sa.Boolean()))
    op.add_column("entra_access_changes", sa.Column("user_object_id", sa.String(36)))
    op.add_column("entra_access_changes", sa.Column("group_object_id", sa.String(36)))
    op.add_column("entra_access_changes", sa.Column("error_code", sa.String(64)))
    if op.get_bind().dialect.name == "postgresql":
        op.execute("UPDATE entra_access_changes SET user_object_id = request->>'user_id', group_object_id = request->>'group_id'")
    else:
        op.execute("UPDATE entra_access_changes SET user_object_id = json_extract(request, '$.user_id'), group_object_id = json_extract(request, '$.group_id')")
    with op.batch_alter_table("entra_access_changes") as batch:
        batch.alter_column("employee_id", existing_type=sa.Integer(), nullable=True)
    op.create_index("ix_entra_change_subject", "entra_access_changes", ["tenant", "user_object_id", "group_object_id"])
    op.create_index("ix_entra_membership_user", "entra_memberships", ["user_id"])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT 1 FROM entra_access_changes WHERE employee_id IS NULL LIMIT 1")):
        raise RuntimeError("Archive remote-only requests before downgrading the unified directory")
    op.drop_index("ix_entra_membership_user", table_name="entra_memberships")
    op.drop_index("ix_entra_change_subject", table_name="entra_access_changes")
    with op.batch_alter_table("entra_access_changes") as batch:
        batch.alter_column("employee_id", existing_type=sa.Integer(), nullable=False)
        for column in ("user_object_id", "group_object_id", "error_code"):
            batch.drop_column(column)
    for column in ("description", "mail_enabled", "role_assignable", "group_types",
                   "on_premises_sync_enabled", "management_metadata_complete"):
        op.drop_column("entra_groups", column)
    for column in ("department", "on_premises_sync_enabled"):
        op.drop_column("entra_users", column)
