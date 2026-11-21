"""Run the tenant worker as a supervised service independent of Web and Desktop."""
import logging
from time import monotonic, sleep

import httpx
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal, engine
from backend.app.services.entra_role_governance import refresh_alerts
from backend.app.services.entra_sync_worker import sync_due
from backend.app.services.graph_client import GraphClient, GraphConfig, TokenCache


def main():
    config = GraphConfig.from_settings(settings)
    lock = text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))")
    unlock = text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))")
    key = {"key": f"identityops:entra-worker:{config.tenant_id}"}
    cache = TokenCache()
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger(__name__)
    log.info("Entra monitoring worker started")
    refresh_due = 0.0
    with httpx.Client(trust_env=False, follow_redirects=False, headers={"Accept-Encoding": "identity"}) as http:
        def make_client():
            return GraphClient(config, http, cache)

        while True:
            try:
                with engine.connect() as connection:
                    if connection.scalar(lock, key):
                        try:
                            with SessionLocal() as db:
                                synchronized = sync_due(db, config.tenant_id, settings.ENTRA_SYNC_INTERVAL_MINUTES, make_client)
                                if synchronized or monotonic() >= refresh_due:
                                    refresh_alerts(db, config.tenant_id)
                                    refresh_due = monotonic() + 60
                        finally:
                            connection.execute(unlock, key)
            except SQLAlchemyError:
                log.error("Worker database operation failed; check availability and apply migrations")
            sleep(15)


if __name__ == "__main__":
    main()
