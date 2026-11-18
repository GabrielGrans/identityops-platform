from alembic import context


# The migration CLI supplies an authenticated connection without passing a DSN
# through Alembic's configuration or logging.
connection = context.config.attributes["connection"]
context.configure(connection=connection, version_table="identityops_schema_version")
with context.begin_transaction():
    context.run_migrations()
