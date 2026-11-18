"""Add campaign snapshots, reviewer assignments and membership invalidation."""

from alembic import op
import sqlalchemy as sa


revision = "certification_090"
down_revision = "entra_080"


def upgrade():
    op.create_table(
        "certification_campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("starts_on <= due_on", name="ck_certification_campaign_dates"),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'completed', 'cancelled', 'expired')",
            name="ck_certification_campaign_status",
        ),
    )
    op.create_table(
        "certification_reviewers",
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("certification_campaigns.id"), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), primary_key=True),
    )
    op.create_index("ix_certification_reviewers_employee", "certification_reviewers", ["employee_id"])
    op.create_table(
        "certification_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("certification_campaigns.id"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("groups.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("employees.id")),
        sa.Column("justification", sa.Text()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("campaign_id", "employee_id", "group_id", name="uq_certification_membership"),
        sa.CheckConstraint(
            """(
                status IN ('retained', 'revoked') AND reviewer_id IS NOT NULL
                AND reviewer_id <> employee_id AND decided_at IS NOT NULL
                AND justification IS NOT NULL AND length(trim(justification)) > 0
            ) OR (
                status IN ('pending', 'superseded', 'not_reviewed') AND reviewer_id IS NULL
                AND decided_at IS NULL AND justification IS NULL
            )""",
            name="ck_certification_item_decision",
        ),
    )
    op.create_index("ix_certification_item_campaign_status", "certification_items", ["campaign_id", "status", "id"])
    op.create_index("ix_certification_item_membership", "certification_items", ["employee_id", "group_id", "status"])

    # Re-granting the same employee/group pair must never revive a snapshot item.
    invalidate = """
        UPDATE certification_items SET status = 'superseded'
        WHERE employee_id = OLD.employee_id AND group_id = OLD.group_id
          AND status = 'pending';
    """
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"""
            CREATE FUNCTION identityops_supersede_certification_items() RETURNS trigger
            LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
            BEGIN
                {invalidate}
                RETURN OLD;
            END;
            $$
        """)
        op.execute("""
            CREATE TRIGGER identityops_certification_membership_removed
            AFTER DELETE ON employee_groups FOR EACH ROW
            EXECUTE FUNCTION identityops_supersede_certification_items()
        """)
    else:
        op.execute(f"""
            CREATE TRIGGER identityops_certification_membership_removed
            AFTER DELETE ON employee_groups FOR EACH ROW BEGIN
                {invalidate}
            END
        """)


def downgrade():
    raise RuntimeError("Restore a database backup for a rollback that removes certification history.")
