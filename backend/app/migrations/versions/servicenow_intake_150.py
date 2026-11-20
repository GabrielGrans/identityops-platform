"""Store verified ServiceNow submissions and their IAM queue references."""
from alembic import op
import sqlalchemy as sa

revision = "servicenow_intake_150"
down_revision = "official_departments"


def upgrade():
    op.create_table(
        "servicenow_access_requests",
        sa.Column("tenant", sa.String(36), primary_key=True),
        sa.Column("instance", sa.String(80), primary_key=True),
        sa.Column("sys_id", sa.String(32), primary_key=True),
        sa.Column("ritm", sa.String(24), nullable=False),
        sa.Column("change_id", sa.Integer(), sa.ForeignKey("entra_access_changes.id"), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.UniqueConstraint("tenant", "instance", "ritm", name="uq_servicenow_instance_ritm"),
    )


def downgrade():
    raise RuntimeError("Export and preserve the ServiceNow intake ledger before changing this schema.")
