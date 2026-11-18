"""Create the read-only Entra directory and synchronization history."""
from alembic import op
import sqlalchemy as sa


revision = "entra_080"
down_revision = None


def upgrade():
    op.create_table(
        "entra_sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("active_slot", sa.Integer(), unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(40)),
        sa.Column("users_count", sa.Integer()),
        sa.Column("groups_count", sa.Integer()),
        sa.Column("memberships_count", sa.Integer()),
        sa.Column("skipped_users_count", sa.Integer()),
    )
    op.create_index("ix_entra_sync_runs_tenant_id", "entra_sync_runs", ["tenant_id"])
    op.create_table(
        "entra_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("object_id", sa.String(36), nullable=False),
        sa.Column("display_name", sa.String(256)),
        sa.Column("principal_name", sa.String(320)),
        sa.Column("mail", sa.String(320)),
        sa.Column("account_enabled", sa.Boolean()),
        sa.Column("present", sa.Boolean(), nullable=False),
        sa.Column("last_seen_run_id", sa.Integer(), sa.ForeignKey("entra_sync_runs.id"), nullable=False),
        sa.Column("local_employee_id", sa.Integer(), sa.ForeignKey("employees.id")),
        sa.UniqueConstraint("tenant_id", "object_id"),
        sa.UniqueConstraint("tenant_id", "local_employee_id"),
    )
    op.create_table(
        "entra_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("object_id", sa.String(36), nullable=False),
        sa.Column("display_name", sa.String(256)),
        sa.Column("security_enabled", sa.Boolean()),
        sa.Column("present", sa.Boolean(), nullable=False),
        sa.Column("last_seen_run_id", sa.Integer(), sa.ForeignKey("entra_sync_runs.id"), nullable=False),
        sa.Column("local_group_id", sa.Integer(), sa.ForeignKey("groups.id")),
        sa.UniqueConstraint("tenant_id", "object_id"),
        sa.UniqueConstraint("tenant_id", "local_group_id"),
    )
    op.create_table(
        "entra_memberships",
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("entra_groups.id"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("entra_users.id"), primary_key=True),
    )


def downgrade():
    raise RuntimeError("Restore a database backup for a rollback that removes Entra tables.")
