"""Official local departments and normalization shared with Entra governance."""
import unicodedata

from sqlalchemy import select, text

from backend.app.models.department import Department

OFFICIAL = (
    ("TI", "TI"), ("VENDAS", "VENDAS"), ("FINANCEIRO", "FINANCEIRO"),
    ("RH", "RH"), ("DIRETORIA", "DIRETORIA"), ("ADMINISTRACAO", "ADMINISTRAÇÃO"),
    ("MARKETING", "MARKETING"),
)


def department_key(value):
    normalized = unicodedata.normalize("NFKD", (value or "").strip().casefold())
    return "".join(character for character in normalized if not unicodedata.combining(character))


def official_code(name, code=None):
    names = {department_key(label): key for key, label in OFFICIAL}
    return names.get(department_key(name)) or names.get(department_key(code))


def seed_official_departments(db):
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("LOCK TABLE departments IN SHARE ROW EXCLUSIVE MODE"))
    existing = db.scalars(select(Department)).all()
    present = {official_code(department.name, department.code) for department in existing}
    for code, name in OFFICIAL:
        if code not in present:
            db.add(Department(code=code, name=name))
    db.flush()
