# Campanhas de certificação de acesso

Use **Access Certification** para revisar associações de colaboradores a grupos locais. Uma campanha tem nome, descrição opcional, responsável, data de início, prazo e revisores designados. O responsável identifica quem responde pela campanha. As ações administrativas dependem de RBAC.

## Instalação e permissões

Em uma instalação v0.8.0 existente, faça backup do banco e execute na raiz do projeto:

```sh
python -m backend.app.scripts.migrate
python -m backend.app.scripts.seed_permissions
```

Em um banco novo, use `migrate --bootstrap` e o fluxo `bootstrap_admin`. A revisão Alembic `certification_090` cria as tabelas de campanhas, revisores e itens e instala um gatilho para identificar o fim de uma associação. A migração preserva as tabelas e os dados locais e do Entra existentes. A API de campanhas retorna 503 se a migração estiver pendente.

| Permissão | Acesso |
| --- | --- |
| `certifications:manage` | Criar campanhas, consultar todas as campanhas, alterar revisores e executar transições. |
| `certifications:review` | Consultar e decidir itens somente nas campanhas em que o colaborador está designado. |

O seed disponibiliza ambas ao grupo `IT Administrators`. A designação requer um colaborador ativo. Para decidir, o colaborador também precisa receber a permissão de revisão. Planeje revisores suficientes para que cada um tenha outra pessoa disponível para certificar seus acessos.

## Ciclo da campanha

1. Crie o rascunho e informe os IDs locais do responsável e dos revisores, consultáveis em `GET /employees` com `employees:read`.
2. Ative a campanha dentro do período definido. A ativação captura uma associação por par colaborador ativo/grupo ativo, de todo o IAM local, em uma única transação. Novas associações ficam para uma campanha posterior. Uma campanha sem associações elegíveis não pode ser ativada.
3. Um revisor designado registra **Retain** ou **Revoke** com justificativa obrigatória. O sistema grava o revisor e o horário. Uma revogação remove a associação local na mesma transação da decisão e da auditoria. Revisões individuais pendentes dessa associação são encerradas como superadas.
4. Quando todos os itens estiverem encerrados, um administrador pode concluir a campanha. Também pode cancelar um rascunho ou uma campanha ativa. Após o prazo, pode expirar uma campanha com pendências. Cancelar ou expirar marca pendências como `not_reviewed` e mantém as decisões já aplicadas.

As datas são interpretadas em UTC e o dia do prazo é inclusivo. Após esse dia, a API bloqueia novas decisões. A expiração é manual. Uma campanha concluída, cancelada ou expirada não pode ser reaberta.

Quando uma associação é removida, os itens pendentes correspondentes ficam `superseded`, inclusive em campanhas paralelas. Adicionar o mesmo par novamente não reabre o item anterior. Se um colaborador ou grupo estiver inativo no momento da decisão, o item também fica superado. A certificação cobre associações locais diretas. O escopo inclui exclusivamente os dados do IAM local e não aciona gravações no Microsoft Graph.

## API

As rotas usam o JWT local. O Swagger fica em `/docs` ou `/api/docs` na pilha Docker.

| Operação | Endpoint |
| --- | --- |
| Criar e listar | `POST /certification-campaigns`, `GET /certification-campaigns` |
| Consultar detalhes e contagens | `GET /certification-campaigns/{id}` |
| Substituir revisores | `PUT /certification-campaigns/{id}/reviewers` |
| Alterar estado | `POST /certification-campaigns/{id}/transition` |
| Consultar itens por campanha | `GET /certification-campaigns/{id}/items` |
| Reter ou revogar | `POST /certification-campaigns/{id}/items/{item_id}/decision` |

As listagens aceitam `status`, `limit` e `before_id`. Use `{"action":"activate"}` para ativar e `{"decision":"retained","justification":"Necessidade confirmada"}` para registrar uma decisão. O histórico do item mantém a justificativa. O log de auditoria registra as ações `certification.*` com IDs internos, sem duplicar o texto da justificativa.
