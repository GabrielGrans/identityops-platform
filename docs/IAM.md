# Operação de IAM

## Solicitações e aprovações

1. Em **Access Groups**, um operador com `access:manage` abre um grupo ativo para solicitações.
2. O colaborador autenticado escolhe o grupo em **Access Requests**, informa a justificativa e acompanha a decisão em **My requests**.
3. Outro operador com `access:manage` registra aprovação ou rejeição e informa o motivo. A aprovação concede o grupo na mesma transação que grava a decisão e a auditoria.

Existe no máximo uma solicitação pendente por par colaborador/grupo. A atribuição direta substitui a solicitação pendente correspondente. Fechar o grupo para solicitações, alterar suas permissões efetivas ou mudar seu status encerra as solicitações pendentes. Alterar as permissões efetivas ou o status também desabilita a oferta do grupo até que um operador volte a habilitá-la. As decisões encerradas permanecem no histórico.

## Grupos, permissões e departamentos

| Ação | Permissão |
| --- | --- |
| Consultar catálogos | `groups:read`, `permissions:read` ou `departments:read` |
| Editar os registros do catálogo correspondente | `groups:manage`, `permissions:manage` ou `departments:manage` |
| Configurar grupos solicitáveis e editar atribuições diretas | `access:manage` |
| Consultar auditoria | `audit:read` |
| Abrir, manter ou revogar uma revisão | `reviews:manage` |

No frontend, combine as permissões de consulta e administração para editar um catálogo. Em **Access Groups**, use **Permissions** para listar e remover permissões do grupo. Use **Employee memberships** para consultar e alterar a participação do colaborador. Os seletores de novas atribuições consultam os respectivos catálogos.

## Ciclo de vida

Os eventos são acionados em **Identity Lifecycle**. Cada operação exige `access:manage` e a permissão correspondente na tabela.

| Evento | Permissão adicional | Efeito |
| --- | --- | --- |
| Joiner | `employees:create` | Cria o colaborador e atribui os grupos iniciais ativos. Para habilitar o login local, defina a senha com `python -m backend.app.scripts.set_employee_password ID`. |
| Mover | `employees:update` | Altera cargo, departamento e gestor. A seleção representa o conjunto final de grupos. Se outra operação alterar as associações antes do envio, recarregue o colaborador para revisar o novo conjunto. Solicitações e revisões pendentes anteriores são encerradas quando o perfil ou os grupos mudam. |
| Leaver | `employees:deactivate` | Desativa a conta, invalida o uso de tokens existentes, remove a senha local e todos os grupos, encerra pendências e desvincula subordinados diretos. |

O operador precisa selecionar outra pessoa para eventos Mover e Leaver. Os fluxos operam no diretório local. A [integração com Microsoft Entra ID](ENTRA_ID.md) oferece uma visão externa de leitura e vínculos explícitos para reconciliação.

## Revisões e auditoria

Em **Access Reviews**, informe o colaborador e o grupo ativo do qual ele faz parte. Registre **retained** para manter a associação ou **revoked** para revogá-la imediatamente. Cada decisão exige uma justificativa. O revisor precisa ser outra pessoa. Remover a associação ou alterar as permissões efetivas ou o status do grupo encerra a revisão pendente, preservando o histórico.

**Audit Logs** permite pesquisar por ação exata e pelo ID do operador. Os eventos registram horário, ação, operador, alvo e detalhes operacionais. O sistema grava eventos de mutações IAM e logins bem-sucedidos. A API oferece somente consulta aos eventos e usa paginação por `before_id`. Os dados anteriores à atualização mantêm suas associações existentes e passam a produzir eventos a partir da versão 0.7.0.

## API

Use `/docs` no ambiente de desenvolvimento ou `/api/docs` no pacote Docker.

| Recurso | Endpoints |
| --- | --- |
| Permissões efetivas | `GET /auth/me/permissions` |
| Solicitações | `GET /access-requests/catalog`, `GET/POST /access-requests`, `GET /access-requests/queue`, `POST /access-requests/{id}/decision` |
| Política de solicitação | `PUT /groups/{id}/requestability` |
| Atribuições | `GET /employees/{id}/groups`, `GET /groups/{id}/permissions` e operações de associação existentes |
| Ciclo de vida | `POST /lifecycle/joiner`, `POST /lifecycle/{employee_id}/mover`, `POST /lifecycle/{employee_id}/leaver` |
| Revisões | `GET/POST /access-reviews`, `POST /access-reviews/{id}/decision` |
| Auditoria | `GET /audit-events` |

Para revisar várias associações em um ciclo com prazo e revisores designados, use as [campanhas de certificação](CERTIFICATION.md).

## Employee and group administration / Administração de colaboradores e grupos

- **EN.** Employee creation can include an initial password and group memberships in a single transaction. The group and permission selectors use the existing directories. Inactive employees cannot receive new memberships. To enable password management and elevated delegation for the administrator group, run `python -m backend.app.scripts.seed_permissions`. No new database migration is required.
- **PT.** A criação de colaboradores pode incluir senha inicial e grupos na mesma transação. Os seletores usam os catálogos existentes. Colaboradores inativos não recebem novos vínculos. Execute `python -m backend.app.scripts.seed_permissions` para habilitar a administração de senhas e delegação elevada no grupo administrador. Esta alteração não requer nova migração.
- **EN.** Use `access:manage` for memberships, `permissions:manage` for group permission changes, and `employees:reset_password` to administer credentials. Operations that grant or restore access, and password resets, are limited to permissions already held by the operator unless they also hold `access:delegate`. Existing tokens retain their normal expiry after a password reset.
- **PT.** Use `access:manage` para vínculos, `permissions:manage` para permissões de grupos e `employees:reset_password` para senhas. Concessões, reativações e redefinições de senha respeitam o escopo do operador, salvo quando ele também possui `access:delegate`. Tokens já emitidos mantêm a expiração original após a redefinição.


## Enterprise governance / Governança empresarial

Run `python -m backend.app.scripts.migrate` and `python -m backend.app.scripts.seed_permissions` after updating. The migration `enterprise_governance_140` stores one policy per installation. The seed grants `governance:read` and `governance:manage` to the administrator group. Policy edits record before/after values in the audit trail.

Após atualizar, execute a migração e o seed de permissões. Abra **Achados de governança** para ajustar a política e consultar evidências. Em **Configurações**, escolha inglês ou português do Brasil. A escolha é salva no dispositivo.

| Rule / Regra | Evidence / Evidência |
| --- | --- |
| Excessive permissions / Permissões excessivas | Distinct effective permissions across active local groups exceed the configured per-employee limit. |
| Privileged access / Acesso privilegiado | An active employee belongs to a configured active privileged group and is missing from its employee allowlist. |
| Inactive access / Acesso de contas inativas | An inactive employee retains memberships in active local groups. This evidence describes retained links. |
| Review age / Idade da revisão | A pending access review was opened before the configured number of days. The default is 30 days. |
| Segregation of duties / Segregação de funções | An active employee holds both effective permissions from a configured pair. |
| Entra mismatch / Divergência do Entra | Direct membership differs for a linked employee and actively mapped entities present in the latest completed snapshot, up to 24 hours old. Requires `entra:read`. |

Comparison in the Entra user details requires `access:manage`. Unmapped groups are shown separately from confirmed differences. A dash on the dashboard indicates a rule was not evaluated. Findings are evaluated on demand and are advisory. Policy settings do not change user entitlements.
