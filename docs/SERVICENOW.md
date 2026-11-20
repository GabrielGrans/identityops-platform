# ServiceNow → IdentityOps

The v1.5.0 integration treats ServiceNow as the request system and IdentityOps as the IAM processor. This repository supplies PDI deployment scripts and configuration. The instance and tenant still require administrator setup and qualification.

## Architecture and security

1. A catalog flow creates a native Requested Item (RITM) and records a native approval against it.
2. The flow sends the RITM `sys_id` to the IdentityOps intake using an integration-only bearer secret. The payload has no approval, actor, tenant, group or target-user overrides.
3. IdentityOps reads a fixed HTTPS endpoint on the configured ServiceNow instance, using a separate read-only account. It verifies the configured tenant, item, approved state, independent approver and approved subject/group/operation. ServiceNow IAM administrators maintain the immutable Entra object ID for the beneficiary.
4. The intake ledger uniquely identifies RITMs by tenant, instance and record ID or RITM number. One transaction records the evidence, technical actor and queue reference. Retries return the same request.
5. In simulation mode IdentityOps validates the snapshot and group policy and records a distinct `simulated` result. It creates no queue item and sends no Graph write.
6. In live mode a different local reviewer must approve the existing queue entry. Before any write, the existing worker rechecks the verified ServiceNow evidence, local roles, allowlist, snapshot and target group. It records the result after checking membership via Graph.
7. ServiceNow polls IdentityOps and updates its RITM. There is no separate ticket or provisioning system within IdentityOps.

The intake token has access to these integration endpoints only. Use a fresh secret of at least 32 characters. The configured IdentityOps service employee must be active and have no password and only the active permission `entra:request_change`. Dedicate a group to this role. Keep the worker and API configuration consistent. To stop processing, disable the integration or Graph writeback. Permissions and upstream approval are checked before worker writes, but cross-system changes between that check and Graph are inherently non-atomic.

## IdentityOps configuration

Use `python -m backend.app.scripts.migrate` on an existing database, then run `python -m backend.app.scripts.seed_permissions`. The revision `servicenow_intake_150` adds the intake ledger. Preserve the ledger and back up before an upgrade.

Set `SERVICENOW_ENABLED=true`, `SERVICENOW_INSTANCE=devNNNNNN.service-now.com` (hostname only), `SERVICENOW_REQUESTER_ID` to the service employee ID, and configure `SERVICENOW_READ_USER`, `SERVICENOW_READ_PASSWORD` and `SERVICENOW_INTAKE_TOKEN` via protected runtime configuration. Keep `SERVICENOW_SIMULATION=true` and `ENTRA_WRITE_ENABLED=false` for initial validation. Set a test group allowlist even in simulation. Configure Entra synchronization following [the Graph guide](ENTRA_AUTOMATION.md).

PDI must have an authorized HTTPS route to the backend or a correctly configured MID Server. The Desktop loopback API port is not reachable from the PDI. Enforce TLS, restrict ingress to the integration and store both secrets separately. The deployment gateway should rate-limit intake and restrict request bodies. Avoid request/response body logging in production.

## PDI setup

For simulation acceptance and approval evidence protections, follow the [PDI checklist in Portuguese](SERVICENOW_PDI.md).

1. Add a managed string field `u_identityops_entra_object_id` to `sys_user`, writable only by trusted identity administrators. Populate it for test users with their immutable Entra object IDs.
2. Create the native catalog item **Solicitação de Acesso Corporativo**. Define `beneficiary` (reference to `sys_user`), `group_object_id` (controlled choices with Entra object IDs), `operation` (choice values `grant` and `revoke`) and `justification` (text). Let native request records record the RITM number, request submitter and approval. Treat corporate email as a display attribute. Restrict editing request inputs after approval using server-side ACLs/process enforcement, including changes to catalog variables submitted through different channels.
3. Configure a Flow Designer catalog trigger and **Ask for Approval** against the RITM. Use a managed approver or group with separation from the requester and beneficiary. Set overall RITM approval state through the native approval flow. Configure `x_identityops.catalog_item_sys_id` and `x_identityops.entra_tenant_id` as system properties maintained by administrators.
4. Register the Scripted REST API with API namespace `identityops`, API ID `approval`, version `v1`, GET resource `/ritm/{sys_id}` and the supplied [approval script](../integrations/servicenow/approval-resource.js). Configure authentication and restrict the resource ACL to `x_identityops.approval_reader`; use a dedicated web-service-only account with that role. If the selected ServiceNow scope generates a different API prefix, set `SERVICENOW_API_NAMESPACE` to the API namespace shown in the PDI. Validate the final URL and `sysapproval` reference against your PDI before enabling the integration.
5. Create REST Message **IdentityOps IAM** with methods `submit` (POST) and `status` (GET). Set the integration bearer via the instance credential mechanism. Point to the HTTPS reverse proxy base `/api/integrations/servicenow/access-requests`, or omit the leading `/api` when connecting through a gateway that forwards raw FastAPI paths. The status method adds `/${sys_id}`.
6. Create a reusable action with Script step from [flow-action.js](../integrations/servicenow/flow-action.js). Use inputs `sys_id` (String), `submit` (Boolean), outputs `http_status` (Integer), `retryable` and `simulated` (Boolean), and `identityops_status`, `identityops_reference` and `identityops_error_code` (String). Invoke submit only on the approved branch. Poll status on a bounded schedule, for example every minute for up to 24 hours, and repeat failed POSTs only for transient errors using the same `sys_id`.
7. Create dedicated integration fields on `sc_req_item` such as `u_identityops_status` and `u_identityops_reference`. Use the Flow Designer **Update Record** action to populate them. Use native Flow actions for transitions in your existing ticket lifecycle. The configuration does not prescribe numeric ServiceNow state values.

| IdentityOps status | Suggested RITM status label |
| --- | --- |
| `pending` | Aguardando revisão IAM |
| `approved` | Aguardando execução |
| `executing` | Em execução |
| `succeeded` | Concluída e verificada |
| `failed`, `conflict`, `expired` | Falhou / requer revisão |
| `rejected` | Rejeitada |
| `simulated` | Simulada, sem alteração no Entra |

## REST contract

- `POST /integrations/servicenow/access-requests` with `{"sys_id":"11111111111111111111111111111111"}`. A new request returns 201 and a repeated submission returns 200. No approval flags are accepted.
- `GET /integrations/servicenow/access-requests/{sys_id}` returns `sys_id`, `ritm`, `change_id`, `status`, `simulated`, `created_at` and `error_code`. Both integration endpoints require the dedicated bearer.
- `GET /integrations/servicenow/access-requests/snapshot` is the IAM reviewer view of simulated deliveries. It uses the platform JWT and `entra:approve_change`.

A 401 indicates the wrong integration token. A 409 requires reviewing evidence, approved target, allowed group or duplicate RITM. A 502 indicates an unavailable approval source. A 503 indicates missing configuration or migration. Retry transient errors with backoff. If the worker reports an uncertain outcome, check the Graph membership and audit before submitting a different RITM.

## Resumo em português

O ServiceNow registra a RITM e a aprovação nativa. O IdentityOps consulta a evidência na instância configurada e valida beneficiário, tenant e grupo. Em modo real, um revisor IAM distinto autoriza a entrada na fila e o worker revalida a evidência antes de escrever. Em simulação, a auditoria registra a validação e o resultado `simulated`, sem alterar o Entra. O Flow Designer consulta o status e atualiza somente campos de integração que você configurar na RITM. Use uma PDI e um tenant de teste. A instalação dos scripts e a homologação da PDI não fazem parte dos testes automatizados.

## Prévia Flextrix pelo MID Server

Mantenha `ENTRA_WRITE_ENABLED=false` e `SERVICENOW_SIMULATION=true` no laboratório. A prévia funciona com allowlist vazia. A entrega simulada do POST de intake continua exigindo um grupo explicitamente permitido, pois valida a política de destino completa. O modo simulado nunca cria uma operação na fila do Graph.

1. Configure `SERVICENOW_ENABLED=true`, `SERVICENOW_INSTANCE`, `SERVICENOW_API_NAMESPACE`, `SERVICENOW_REQUESTER_ID`, `SERVICENOW_READ_USER`, `SERVICENOW_READ_PASSWORD` e `SERVICENOW_INTAKE_TOKEN` de acordo com [a configuração do laboratório](SERVICENOW_PDI.md). A identidade técnica local continua sem senha e com somente `entra:request_change`. A conta separada de leitura na PDI só precisa consultar o recurso de evidência.
2. Em **IdentityOps IAM**, adicione um método POST de prévia ao mesmo REST Message e mantenha o MID Server que já chega ao FastAPI. Use `/integrations/servicenow/access-requests/preview` no FastAPI direto ou `/api/integrations/servicenow/access-requests/preview` no proxy padrão. Vincule o bearer dedicado por perfil de autenticação/credencial gerenciada ou por um alias que injete a credencial no runtime. Evite salvar um JWT de operador ou o valor do segredo como header literal no registro REST Message. Proteja a rota com HTTPS autorizado.
3. Teste com `Content-Type: application/json` e corpo `{"sys_id":"<sys_id-da-RITM-aprovada>"}`. Espere HTTP 200 com `read_only=true`, `can_submit=false`, `snapshot_id`, `expected` e `operation`. O endpoint recusa dados de autorização enviados pelo cliente, consulta a aprovação na instância configurada e checa o beneficiário e o grupo no snapshot local. Nenhuma solicitação ou associação é criada pela prévia.
4. Faça o fluxo de entrega aprovado chamar o endpoint de intake já documentado, usando o mesmo `sys_id`. O intake consulta a evidência novamente. A prévia não substitui a aprovação nativa, a revisão IAM no modo real ou os controles do worker. Confirme na PDI que os dados aprovados são protegidos desde o início da aprovação ou que qualquer mudança invalida a decisão.

Se estiver isolando o 409 pelo endpoint histórico `/entra/automation/preview`, use um JWT de operador emitido para a sessão de teste com `entra:request_change`. Confirme HTTP 200 e `can_submit=false` com escrita desabilitada. O bearer dedicado do ServiceNow é exclusivo das rotas de integração, incluindo a prévia dedicada.
