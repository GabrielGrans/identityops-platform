"""Durable tenant checkpoints, administrative requests and governance exceptions."""
from alembic import op
import sqlalchemy as sa

revision = "entra_automation"
down_revision = "enterprise_governance_140"


def upgrade():
    with op.batch_alter_table("entra_sync_runs") as batch:
        batch.alter_column("actor_id", existing_type=sa.Integer(), nullable=True)
    op.create_table("entra_automation_state",
                    sa.Column("tenant", sa.String(36), primary_key=True),
                    sa.Column("checkpoint", sa.JSON(), nullable=False),
                    sa.Column("next_run", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("failures", sa.Integer(), nullable=False))
    op.create_table("entra_access_changes",
                    sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("tenant", sa.String(36), nullable=False, index=True),
                    sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
                    sa.Column("requester_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
                    sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("employees.id")),
                    sa.Column("status", sa.String(24), nullable=False),
                    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("next_attempt", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("attempts", sa.Integer(), nullable=False),
                    sa.Column("request", sa.JSON(), nullable=False))
    op.create_table("entra_role_policy",
                    sa.Column("tenant", sa.String(36), primary_key=True),
                    sa.Column("rules", sa.JSON(), nullable=False))
    op.create_table("entra_alerts",
                    sa.Column("tenant", sa.String(36), primary_key=True),
                    sa.Column("key", sa.String(64), primary_key=True),
                    sa.Column("state", sa.String(20), nullable=False),
                    sa.Column("payload", sa.JSON(), nullable=False))


def downgrade():
    for table in ("entra_alerts", "entra_role_policy", "entra_access_changes", "entra_automation_state"):
        op.drop_table(table)
