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
