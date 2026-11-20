# Entra governance and controlled provisioning

## Backend service

Back up the database and run:

```powershell
python -m backend.app.scripts.migrate
python -m backend.app.scripts.seed_permissions
```

The `entra_automation` migration adds tenant checkpoints, role rules, administrative requests and a notification ledger. Scheduled runs have a system actor. Seed grants `entra:request_change` and `entra:approve_change` to the administrator group. Assign these permissions to separate operators for the approval workflow. Policy management uses `governance:manage` and `entra:read`. Reading notifications uses `governance:read` and `entra:read`.

Set credentials only in the server environment or its untracked `.env`. In a separate supervised process, run:

```powershell
python -m backend.app.scripts.entra_worker
```

The worker requires PostgreSQL and stays active when the Windows client is closed. For the release Compose stack, start its optional service with `docker compose --env-file .env -f infrastructure/docker/compose.release.yml --profile entra up -d entra-worker` once the migrated API image and database are available. An installation using the bare executable still needs the API and worker processes on the server.

| Variable | Purpose |
| --- | --- |
| `ENTRA_ENABLED` | Enables the Entra integration on the backend. |
| `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` | Single-tenant application credentials. Restart the backend services after changes. |
| `ENTRA_SYNC_INTERVAL_MINUTES` | 5 to 15 minutes. Default 10. |
| `ENTRA_WRITE_ENABLED` | Gates all remote provisioning. Default false. |
| `ENTRA_WRITE_GROUP_IDS` | Explicit comma-separated Entra object IDs. Empty means no group can be changed. |
| `ENTRA_PROTECTED_GROUP_IDS` | Additional group object IDs that are always protected. |

## App registration and consent

In Microsoft Entra admin center, register a **single-tenant** application and copy its tenant and client IDs. Create a client secret or supply one through your organization's secret store. Under **API permissions → Microsoft Graph → Application permissions**, add read permissions and have an authorized tenant administrator grant consent:

- `User.Read.All` for user delta and account attributes.
- `Group.Read.All` for group delta, group properties and direct membership reads.

For a test tenant and an explicitly approved write deployment, also grant **`GroupMember.ReadWrite.All`** application permission. This Graph permission is tenant-wide. IdentityOps enforces its narrower server-side allowlist. Keep `ENTRA_WRITE_ENABLED=false` until the allowlist, operator separation and protected group classifications have been reviewed. Role-management, directory-wide write and user-write permissions are unnecessary. If Graph cannot confirm that a group is eligible, the worker blocks the write.

## Behavior and limitations

- The worker reads user and group deltas and refreshes direct memberships of security-enabled groups. It performs a daily full delta baseline and falls back to a new baseline after an expired checkpoint. Checkpoints advance atomically with published snapshots. Failed or throttled cycles retain the previous snapshot and schedule a retry honoring `Retry-After`.
- Imports populate the source-managed Entra snapshot. Local employee status, department, credentials, memberships and explicit maps stay local. No local employee record is automatically created, activated or deleted. Nested groups and transitive memberships are outside the direct membership model. The existing Graph request, object and membership bounds still apply.
- Role rules can match the Entra job title and the mapped local employee's department and employment status. Rules without those local filters can evaluate unlinked Entra users. All matching roles are evaluated separately. Exceptions use an inclusive UTC date and only suppress the matching group. Findings are advisory and linked from Notifications. Acknowledgement is shared for each tenant-wide finding.
- Administrative requests require a recent snapshot and an employee mapped to an Entra user. Review is separate from the requester and the affected employee. Requests expire after 24 hours. Execution rechecks role permissions, the allowlist, protected classifications, group metadata and membership drift. Only assigned, non-role-assignable, cloud-managed security groups are supported. Dynamic, synchronized, mail-enabled and Microsoft 365 groups are blocked.
- Graph and PostgreSQL do not share a transaction. The worker records the execution attempt before sending it, checks direct membership afterward and recovers pending verifications on retry. An interrupted run can leave an uncertain outcome if authorization changes or the request expires. Reconcile that case using the Entra directory and the audit trail. External changes can race Graph calls because membership writes have no conditional-update transaction.
- Auditors can filter synchronization and provisioning events in Audit Logs. JSON routes under `/entra/automation` support future integration using a separately designed service identity. There is no ServiceNow connector in this change.

## Windows validation

With PostgreSQL and the server environment configured, start the API in one terminal and the worker in another:

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
python -m backend.app.scripts.entra_worker
```

Run these as separate processes, then start Desktop using `npm --prefix frontend ci` and `npm --prefix frontend run desktop:dev`. First validate read-only synchronization with a test tenant. Close the client and check the schedule and Audit Logs after reopening it. For a separately approved write test, create and preview a request for an allowlisted test group, approve using a different account, then verify the request state, membership and audit event.
