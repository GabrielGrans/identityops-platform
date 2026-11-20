from sqlalchemy import Column, DateTime, Integer, JSON, MetaData, String, Table

metadata = MetaData()
state = Table("entra_automation_state", metadata,
              Column("tenant", String, primary_key=True), Column("checkpoint", JSON),
              Column("next_run", DateTime(timezone=True)), Column("failures", Integer))
changes = Table("entra_access_changes", metadata,
                Column("id", Integer, primary_key=True), Column("tenant", String),
                Column("employee_id", Integer), Column("requester_id", Integer), Column("reviewer_id", Integer),
                Column("status", String), Column("expires_at", DateTime(timezone=True)),
                Column("next_attempt", DateTime(timezone=True)), Column("attempts", Integer), Column("request", JSON))
policies = Table("entra_role_policy", metadata, Column("tenant", String, primary_key=True), Column("rules", JSON))
alerts = Table("entra_alerts", metadata,
               Column("tenant", String, primary_key=True), Column("key", String, primary_key=True),
               Column("state", String), Column("payload", JSON))
