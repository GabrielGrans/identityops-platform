import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from backend.app.core.database import engine
from backend.app.models import Base


def upgrade_database(bind: Engine, *, bootstrap: bool = False):
    with bind.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(57223, 2)"))
        if bootstrap:
            Base.metadata.create_all(bind=connection)
        existing = set(inspect(connection).get_table_names())
        if missing := set(Base.metadata.tables) - existing:
            raise RuntimeError("IAM tables are missing. Start the existing installation or use --bootstrap for fresh setup.")

        config = Config()
        config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def main():
    parser = argparse.ArgumentParser(description="Apply IdentityOps database migrations.")
    parser.add_argument("--bootstrap", action="store_true", help="Initialize the legacy IAM tables on a fresh database.")
    args = parser.parse_args()
    upgrade_database(engine, bootstrap=args.bootstrap)
    print("IdentityOps database migrations applied.")


if __name__ == "__main__":
    main()
