"""Store person attributes for reconciliation and enforce normalized email uniqueness."""
from alembic import op
import sqlalchemy as sa


revision = "provisioning_110"
down_revision = "dashboard_100"

ATTRIBUTES = {
    "user_type": 32,
    "employee_type": 120,
    "employee_number": 64,
    "given_name": 100,
    "surname": 100,
    "job_title": 120,
}


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        op.execute("LOCK TABLE employees IN SHARE ROW EXCLUSIVE MODE")
    conflict = connection.scalar(sa.text(
        "SELECT 1 FROM employees GROUP BY lower(trim(email)) HAVING count(*) > 1 LIMIT 1"
    ))
    if conflict:
        raise RuntimeError("Resolve duplicate local employee emails (ignoring case and surrounding spaces) before migrating.")
    op.execute("CREATE UNIQUE INDEX uq_employees_normalized_email ON employees (lower(trim(email)))")
    for name, length in ATTRIBUTES.items():
        op.add_column("entra_users", sa.Column(name, sa.String(length), nullable=True))


def downgrade():
    for name in reversed(ATTRIBUTES):
        op.drop_column("entra_users", name)
    op.drop_index("uq_employees_normalized_email", table_name="employees")
