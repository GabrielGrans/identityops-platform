# Administrator provisioning and IAM operations

Apply the `official_departments` migration and reseed local permissions. The release does not add environment variables.

```powershell
python -m backend.app.scripts.migrate
python -m backend.app.scripts.seed_permissions
```

## Direct authorization

The seed installs `entra:direct_provision` only on the built-in local group **IT Administrators** (`IT_ADMINS`). The API requires an authenticated active employee with `entra:request_change` and verifies that the direct permission comes from this active local role. Existing administrators whose deployment uses a custom group identity retain the approval workflow.

A supported submission is marked `direct_authorized` by the server, with an audit event recording the operator and reason. There is no second approver attributed to such a request. For all other operators, requests remain pending until approved by a different authorized person. The worker rechecks the same local role and permissions at execution, including retries, before calling Microsoft Graph.

Keep `ENTRA_WRITE_ENABLED=false` until a test deployment is authorized. The existing group allowlist, protected group list and live Graph eligibility checks still apply. The same provisioning worker handles remote verification and schedule refresh. See [Graph configuration and consent](ENTRA_AUTOMATION.md).

## Departments and Dashboard

The migration seeds TI, VENDAS, FINANCEIRO, RH, DIRETORIA, ADMINISTRAÇÃO and MARKETING. It reuses matching records after normalizing accents, case and surrounding whitespace. It preserves existing records and employee assignments. Entra department labels are aggregated separately, with a distinct unassigned category for missing attributes. Rules can use the synchronized department and job title or a linked local department, without automatically granting access.

The dashboard reports distinct source populations with separate Local and Microsoft Entra cards. It does not aggregate the two populations into a person total. Operational Entra counts are tenant-scoped. Failed requests count persisted failures and conflicts. The certification completion denominator includes recorded retain/revoke decisions and currently pending items in active campaigns. Empty campaigns and unavailable snapshots have explicit states.

## Windows

In separate terminals, start the API and provisioning worker, then open the Desktop application or run the Tauri development client:

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
python -m backend.app.scripts.entra_worker
npm --prefix frontend ci
npm --prefix frontend run desktop:dev
```
