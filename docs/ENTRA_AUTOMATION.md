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

For synchronized Employees and Access Groups, immutable subjects without a local employee, and directory capabilities, see [Unified Entra directory](UNIFIED_ENTRA_DIRECTORY.md).

## Prévia somente leitura e solicitação de escrita

`POST /entra/automation/preview` exige autenticação de operador e a permissão `entra:request_change`. A prévia lê somente o snapshot PostgreSQL mais recente. Ela aceita `user_id` (Object ID Entra) ou `employee_id` (identidade local vinculada), além de `group_id`, `add` e `justification`. Inclua exatamente um identificador de pessoa. O grupo deve ser de segurança, gerenciado na nuvem, com metadados completos e fora das proteções do ambiente e das políticas IAM. A associação retornada em `expected` é a do snapshot, e não uma consulta em tempo real ao Graph.

A prévia funciona com `ENTRA_WRITE_ENABLED=false` e `ENTRA_WRITE_GROUP_IDS` vazio. Nessa situação, `can_submit=false` e `write_blocker=write_disabled`. A API rejeita grupos protegidos, dinâmicos ou sincronizados do AD local, e snapshots expirados. Na tela Grupos de acesso, **Grupos do IdentityOps** administra grupos locais e suas permissões RBAC. **Grupos do Microsoft Entra ID** exibe o diretório sincronizado, os filtros de classificação, membros e o histórico das solicitações visíveis para o operador.

A prévia e o `snapshot_id` não concedem autorização. A criação, a aprovação positiva e a execução voltam a verificar as condições de escrita e a allowlist. O worker verifica a classificação do grupo e a associação diretamente no Graph antes de escrever e confirma o resultado depois. PostgreSQL serializa solicitações abertas para o mesmo par usuário–grupo e o worker usa um bloqueio por tenant. Uma mudança externa entre a leitura e a escrita continua possível, pois o Graph e o PostgreSQL não compartilham uma transação.

Para Flextrix e MID Server, use a [prévia dedicada do ServiceNow](SERVICENOW.md#prévia-flextrix-pelo-mid-server).

## Revalidar metadados no Windows

O `$select` da sincronização manual e o da rotina delta pedem
`securityEnabled`, `mailEnabled`, `groupTypes`, `onPremisesSyncEnabled` e
`isAssignableToRole`. Uma resposta de coleção ou delta pode chegar sem parte
desses campos. O coletor consulta `GET /v1.0/groups/{id}` com os mesmos campos
para candidatos incompletos, respeitando o limite geral de requisições.
A rotina delta recria o checkpoint uma vez após esta atualização.

`management_metadata_complete` exige quatro valores tipados e a presença
explícita de `onPremisesSyncEnabled`. O Graph usa `null` explícito para grupos
que nunca foram sincronizados do AD local. A omissão dessa propriedade não
equivale a esse estado. Um grupo com metadados completos ainda pode estar
protegido ou ser de um tipo não permitido.

1. No PowerShell, atualize a cópia de trabalho e inicie o PostgreSQL de teste.
   No `.env` já configurado, mantenha `ENTRA_WRITE_ENABLED=false` e
   `ENTRA_WRITE_GROUP_IDS=`. Confirme que a aplicação usada pela API tem
   consentimento administrativo para `Group.Read.All` e `User.Read.All`.
   Para esta validação de leitura, dispense permissões de escrita.
2. Reinicie a API com o código atualizado. No cliente, abra **Microsoft Entra
   ID → Sincronizar agora** e aguarde um registro concluído no histórico.
   Essa opção funciona com o worker parado. Reinicie o worker com a mesma
   versão se for validar a sincronização automática.

```powershell
git fetch origin
git switch fix/identityops-entra-group-metadata
docker compose up -d --wait postgres
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

3. No PostgreSQL, consulte o snapshot concluído para o tenant configurado.
   Substitua o placeholder pelo ID do seu tenant apenas na sessão local.

```sql
BEGIN READ ONLY;
WITH snapshot AS (
    SELECT id, tenant_id, finished_at
    FROM entra_sync_runs
    WHERE tenant_id = '<tenant-id>' AND status = 'completed'
    ORDER BY finished_at DESC, id DESC
    LIMIT 1
)
SELECT g.display_name, s.id AS snapshot_id, s.finished_at,
       g.management_metadata_complete, g.role_assignable, g.group_types,
       g.security_enabled, g.mail_enabled, g.on_premises_sync_enabled
FROM entra_groups g
JOIN snapshot s ON s.tenant_id = g.tenant_id AND s.id = g.last_seen_run_id
WHERE g.present
ORDER BY g.display_name;
ROLLBACK;
```

4. Na UI, confira a classificação do grupo. A prévia de um grupo elegível em
   um snapshot recente deve retornar HTTP 200 e `can_submit=false` com a
   escrita desabilitada. Se os metadados continuarem incompletos, compare
   a resposta de coleção com a resposta de `GET /v1.0/groups/{id}` usando
   a mesma aplicação e o mesmo tenant em uma sessão de diagnóstico autorizada.
   Verifique a presença e o tipo das propriedades, mantendo tokens e
   identificadores fora de logs e relatórios. Se a sincronização falhar com
   403, confira o consentimento de leitura. Se o detalhe ainda omitir campos,
   o grupo permanece bloqueado. Não ajuste registros manualmente no banco.
