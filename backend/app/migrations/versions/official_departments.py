"""Seed the official catalog without rewriting existing department assignments."""
from alembic import op
from sqlalchemy.orm import Session

from backend.app.services.department_catalog import seed_official_departments

revision = "official_departments"
down_revision = "unified_entra_directory"


def upgrade():
    with Session(bind=op.get_bind()) as db:
        seed_official_departments(db)
        db.commit()


def downgrade():
    # Catalog records may now be referenced by employees and policies.
    pass
