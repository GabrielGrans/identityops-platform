"""Index dashboard audit windows and chronological pagination."""

from alembic import op


revision = "dashboard_100"
down_revision = "certification_090"


def upgrade():
    op.create_index("ix_audit_events_created_at_id", "audit_events", ["created_at", "id"])


def downgrade():
    op.drop_index("ix_audit_events_created_at_id", table_name="audit_events")
