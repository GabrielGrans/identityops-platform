# IAM Governance & Security Dashboard

[Português](#português)

## English

The dashboard reads the local IdentityOps database. Each section requires the same organizational permission used for the corresponding workflow. The dashboard grants no new permission. Certification reviewers assigned to individual campaigns keep their existing workflow access and need `certifications:manage` to see the organization-wide rollup.

| Section | Permission | Calculation |
| --- | --- | --- |
| Employees | `employees:read` | Current active and inactive accounts by employee status. |
| Departments, groups, permissions | `departments:read`, `groups:read`, `permissions:read`, respectively | Current active and inactive records by each table's `is_active` flag. Cards show the sum and the two component counts. |
| Approval backlog | `access:manage` | Current access requests with status `pending`. Includes all ages. |
| Review backlog and decisions | `reviews:manage` | Current standalone access reviews with status `pending`. Retained and revoked decisions across those reviews are counted by `decided_at` within the selected window. |
| Certification | `certifications:manage` | Snapshot of campaigns with status `active`, including overdue campaigns. A campaign is overdue when its due date is earlier than the current UTC date. Overdue items are `pending` items in those campaigns. Progress is `(retained + revoked) / (retained + revoked + pending)` in active campaigns. Superseded items are shown separately and excluded from the denominator. Period decision totals count retained and revoked items by `decided_at` across all campaign states. |
| Membership indicators | `access:manage` | Privileged memberships count each active employee–active group pair once when the group has at least one active permission in the list below. Inactive accounts with active groups count distinct inactive employees with at least one membership in an active group. |
| Lifecycle | `audit:read` | Counts recorded `lifecycle.joiner`, `lifecycle.mover`, and `lifecycle.leaver` events separately in the selected window. The bars compare the three counts for that window. |
| Recorded security events | `audit:read` | Revocations count `employee.group.removed`, `review.revoked`, and `certification.item_revoked` events. This counts events, excludes bulk changes recorded only in JML payloads, and can include more than one revocation over time for a membership that was re-granted. Failed operations count only recorded `entra.sync.failed` events. Authentication failures and rejected requests are not included. |
| Recent audit activity | `audit:read` | Events in the window, newest UTC timestamp first and highest ID first on ties. Dashboard responses include an event ID, UTC timestamp, category, and safe label. Actor, target and details stay in the existing audit interface. |

The privileged permission list is `access:manage`, `groups:manage`, `permissions:manage`, `departments:manage`, `employees:create`, `employees:update`, `employees:deactivate`, `reviews:manage`, `certifications:manage`, `certifications:review` and `entra:manage_links`. This identifies elevated local IAM capabilities. An inactive account cannot authenticate even when database memberships remain.

The window is a rolling 7, 30 or 90 days, defaulting to 30. The inclusive bounds use UTC. Current-state metrics ignore the window. Request and standalone review records lack due dates. Only certification has overdue metrics. This release provides window totals and current-state counts. It does not reconstruct historical inventory, monitor unrecorded operations or calculate a risk score. Overview panels use bounded SQL aggregations and individual requests can observe concurrent updates at slightly different times.

### API and deployment

- `GET /v1/dashboard/summary?days=30` returns `as_of`, `period_start` and the authorized summary sections. Unauthorized sections are null and no eligible permissions returns 403. A user with certification permissions sees `certification_available: false` if the campaign tables are missing.
- `GET /v1/dashboard/activity?days=30&category=access&limit=20` requires `audit:read`. Categories include `lifecycle`, `access`, `certification`, `entra` and `other`. Pagination accepts `before_id` copied from `next_before_id`. Use the same filter when paging. Limit is 1–200.
- Apply `python -m backend.app.scripts.migrate` when upgrading from v0.9.0. Revision `dashboard_100` creates an audit timestamp and ID index to support range scans and pagination. On a large PostgreSQL audit table, schedule the migration during a maintenance window because index creation can block writes. Fresh Docker installs apply it through the existing `migrate --bootstrap` flow. No new RBAC seeds or configuration values are required.

## Português

O painel usa o banco local do IdentityOps e respeita as permissões de cada fluxo. Revisores designados continuam com acesso às suas campanhas. O consolidado de toda a organização exige `certifications:manage`.

| Indicador | Cálculo e acesso |
| --- | --- |
| Inventário atual | Colaboradores por status e departamentos, grupos e permissões por `is_active`. Cada cartão requer a permissão de leitura correspondente. |
| Filas | Solicitações e revisões individuais com status `pending`, sem filtro de idade. Requerem `access:manage` e `reviews:manage`, respectivamente. |
| Certificação | Campanhas com status `active`. O prazo é inclusivo em UTC. Atrasos contam campanhas ativas com prazo anterior ao dia atual e seus itens pendentes. O progresso divide decisões de manter e revogar pelo total de decisões e pendências nas campanhas ativas. Itens superados são exibidos à parte. |
| Decisões | Totais de manter e revogar pela data `decided_at` na janela selecionada. As revisões individuais e certificações usam suas permissões respectivas. Os totais de certificação incluem decisões de campanhas encerradas. |
| Segurança atual | Com `access:manage`, contabiliza cada associação entre colaborador ativo e grupo ativo que concede ao menos uma permissão privilegiada ativa da lista acima. Também conta colaboradores inativos distintos com ao menos um grupo ativo. Esses colaboradores continuam impedidos de entrar. |
| Atividade registrada | Com `audit:read`, contabiliza eventos de admissão, movimentação e desligamento, os três tipos de evento de revogação listados acima e falhas registradas de sincronização Entra. Alterações em lote registradas apenas nos detalhes JML e outras falhas não entram nessa contagem. |
| Auditoria recente | Com `audit:read`, exibe ID do evento, horário em UTC, categoria e rótulo. A ordenação usa horário e ID decrescentes. Os detalhes continuam disponíveis na tela de auditoria existente. |

O filtro usa uma janela móvel de 7, 30 ou 90 dias em UTC, com padrão de 30. Ele afeta decisões e eventos. Inventário, progresso e filas representam o estado atual. O painel não infere tendências, atrasos em fluxos que não têm prazo ou níveis de risco.

As rotas são `GET /v1/dashboard/summary` e `GET /v1/dashboard/activity`. Para paginar a atividade, use `next_before_id` como `before_id` mantendo a categoria e a janela. Após atualizar a v0.9.0, execute `python -m backend.app.scripts.migrate`. O novo índice apoia consultas de auditoria por data e ID. Em bancos com histórico de auditoria grande, programe a migração em uma janela de manutenção. Em bases novas, use o fluxo Docker existente com `migrate --bootstrap`. As permissões e variáveis de ambiente existentes continuam válidas.
