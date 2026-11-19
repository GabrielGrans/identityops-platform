"""Persist the policy used to evaluate enterprise IAM findings."""
import sqlalchemy as sa
from alembic import op

revision = "enterprise_governance_140"
down_revision = "provisioning_110"


def upgrade():
    policy = op.create_table(
        "enterprise_governance_policy",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.CheckConstraint("id = 1"),
    )
    op.bulk_insert(policy, [{"id": 1, "rules": {}}])


def downgrade():
    op.drop_table("enterprise_governance_policy")
