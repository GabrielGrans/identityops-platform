from sqlalchemy import Column, DateTime, Integer, JSON, MetaData, String, Table

requests = Table(
    "servicenow_access_requests", MetaData(),
    Column("tenant", String, primary_key=True),
    Column("instance", String, primary_key=True),
    Column("sys_id", String, primary_key=True),
    Column("ritm", String),
    Column("change_id", Integer),
    Column("created_at", DateTime(timezone=True)),
    Column("evidence", JSON),
)
