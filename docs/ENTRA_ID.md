# Microsoft Entra ID e Microsoft Graph

## Pré-requisitos no Entra ID Free

Use um tenant de teste e identidades fictícias. No **Microsoft Entra admin center**, em **App registrations**, registre um aplicativo de tenant único, como **IdentityOps Platform**. Copie o **Directory (tenant) ID** e o **Application (client) ID**.

Em **API permissions**, selecione **Microsoft Graph → Application permissions** e adicione:

| Permissão de aplicativo | Uso |
| --- | --- |
| `User.Read.All` | Ler os usuários e os campos selecionados. |
| `Group.Read.All` | Ler os grupos e as associações diretas disponíveis para o aplicativo. |

Um administrador do tenant precisa conceder consentimento para essas permissões. A permissão delegada `User.Read` não participa do fluxo **client credentials**. O login do IdentityOps continua usando as contas locais. Use as permissões de leitura acima no aplicativo. Permissões de gravação, como `User.ReadWrite.All`, `GroupMember.ReadWrite.All` e `Directory.ReadWrite.All`, ficam fora deste escopo.

Em **Certificates & secrets**, crie uma credencial de curta duração e copie o **Value**, exibido uma vez. Guarde o valor localmente em arquivo restrito ou gerenciador de segredos. Faça a rotação antes do vencimento e reinicie a API após a troca. Use um aplicativo dedicado para limitar as permissões que o escopo `/.default` inclui no token.

## Configuração local

Copie `.env.example` para `.env` se for uma instalação nova. Edite o arquivo localmente. As variáveis Azure são lidas apenas pela API e ficam fora do frontend, do Git, das imagens e dos artefatos de CI. Em Compose, use aspas simples no valor do segredo se precisar preservar caracteres como `$`.

| Variável | Valor |
| --- | --- |
| `ENTRA_ENABLED` | `true` para habilitar. Padrão `false`. |
| `AZURE_TENANT_ID` | GUID do diretório. |
| `AZURE_CLIENT_ID` | GUID do aplicativo. |
| `AZURE_CLIENT_SECRET` | Valor do segredo do aplicativo. |
| `ENTRA_GRAPH_BASE_URL` | Opcional. Padrão e origem permitida `https://graph.microsoft.com/v1.0`. |
| `ENTRA_HTTP_TIMEOUT_SECONDS` | Opcional. Padrão de 10 segundos por timeout de transporte, com máximo de 30. |

### Windows PowerShell com Docker Desktop

Partindo do repositório, configure `.env` e use Python 3.12 e Node.js 24. O Compose abaixo executa só o banco. A API e o Vite rodam no Windows.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
docker compose --env-file .env up -d --wait postgres
.\.venv\Scripts\python.exe -m backend.app.scripts.migrate --bootstrap
.\.venv\Scripts\python.exe -m backend.app.scripts.bootstrap_admin admin@example.com
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

Use `--bootstrap` e `bootstrap_admin` para a primeira instalação. Em uma base existente **v0.7.0**, faça backup, aplique `python -m backend.app.scripts.migrate` sem `--bootstrap` e execute `python -m backend.app.scripts.seed_permissions` em vez de criar um novo administrador. A instalação antiga precisa conter todas as tabelas IAM antes da migração Entra. O Alembic registra a revisão aditiva em `identityops_schema_version`.

Em outro terminal:

```powershell
npm --prefix frontend ci
npm --prefix frontend run dev
```

Acesse `http://localhost:5173`. Para a variante 100% em contêineres, consulte o [guia de instalação e atualização](RELEASE.md).

## Primeira sincronização

1. Entre com um administrador do IdentityOps e abra **Microsoft Entra ID**. **Ready to synchronize** indica que a configuração local está válida e a migração foi aplicada.
2. Selecione **Sync from Microsoft Graph** e confirme. A operação pode levar até alguns minutos. O estado **Verified** indica que a sincronização anterior completou as leituras e salvou o snapshot.
3. Confira o horário e as contagens em **Synchronization history**. Compare usuários e grupos com os registros fictícios do tenant. Em **Groups → View members**, veja os membros diretos do tipo usuário.
4. Para testar idempotência, repita a sincronização. O histórico recebe uma nova execução. Usuários, grupos e associações do snapshot mantêm a mesma identidade e não se duplicam.

Se habilitar a integração em uma base existente, o seed concede `entra:read`, `entra:sync` e `entra:manage_links` ao grupo `IT Administrators`. Para delegar, conceda somente os papéis necessários. A consulta requer `entra:read`, o disparo requer `entra:sync` e a alteração de vínculos requer `entra:manage_links`.

## Fluxo de dados e vínculos

**React → API FastAPI com RBAC → Microsoft Identity Platform e Microsoft Graph → PostgreSQL.** A API busca um token por `client_credentials` no endpoint OAuth do tenant com escopo `https://graph.microsoft.com/.default`. O token fica em memória no processo da API. A API renova o token antes do vencimento e invalida o cache se o Graph responder 401. O navegador usa apenas a sessão local.

O conector percorre páginas de usuários, grupos e membros diretos. A API aceita paginação somente na origem Microsoft e na mesma rota da coleção. Cada execução tem até 500 requisições, incluindo retries, um orçamento de 120 segundos para o Graph, até 10.000 usuários, 10.000 grupos e 25.000 entradas de membros. O limite de requisições normalmente restringe o total de grupos antes dos limites de objetos. Páginas superiores a 4 MiB são rejeitadas.

O banco usa a combinação do tenant e do ID estável do objeto Entra. A sincronização escreve as entidades e associações em uma transação após concluir a leitura. Uma falha mantém o último snapshot completo. A auditoria registra início, conclusão, falha e operações de vínculo com o operador, IDs internos, contagens ou códigos de erro. As respostas de erro omitem os corpos enviados pelo Graph.

Os registros importados ficam separados do diretório IAM local. Um operador verifica o objeto pelo ID do Entra, confere o identificador do registro local e cria o vínculo manualmente. Cada colaborador ou grupo local pode ser vinculado a um objeto de seu tipo por tenant. Em caso de conflito, remova o vínculo anterior antes de substituí-lo. O vínculo serve para identificação e reconciliação. Ele não concede permissões. Um objeto ausente no snapshot seguinte é marcado como ausente, e o vínculo e o registro local são preservados.

## API

Use o Swagger em `http://127.0.0.1:8000/docs` ou `http://127.0.0.1:8080/api/docs` na pilha Docker. Autorize com o JWT de uma sessão local. Exemplos de métodos, caminhos e payload:

```text
GET  /entra/status
POST /entra/sync
GET  /entra/sync-runs?limit=25&before_id=100
GET  /entra/users?search=fixture&limit=25
GET  /entra/groups?search=security&limit=25
GET  /entra/groups/00000000-0000-4000-8000-000000000001/members
PUT  /entra/users/00000000-0000-4000-8000-000000000002/link
     {"local_id": 42}
PUT  /entra/groups/00000000-0000-4000-8000-000000000001/link
     {"local_id": null}
```

## Diagnóstico e limitações

| Situação | Ação |
| --- | --- |
| 401 da API local | Entre novamente no IdentityOps ou confirme a sessão JWT local. |
| `token_rejected` | Confira o tenant, o ID do aplicativo, o valor e o prazo do segredo. Use o valor do segredo, não seu identificador. |
| `graph_unauthorized` (401 do Graph) | Verifique o tenant e a configuração do aplicativo e repita após corrigir o problema. |
| `graph_forbidden` ou `membership_forbidden` (403 do Graph) | Confira se as permissões são do tipo **Application** e se houve consentimento administrativo. Investigue também a visibilidade do grupo. A falha preserva o snapshot anterior. |
| 403 da API local | Verifique as permissões RBAC `entra:*` do operador. |
| `graph_throttled` (429) | Aguarde o intervalo de `Retry-After`. O conector respeita esse cabeçalho e faz até duas novas tentativas com limites de espera. |
| `sync_running` (409) | Aguarde a execução ativa. Uma execução interrompida é encerrada pelo próximo disparo após cinco minutos. |
| `migration_required` | Aplique a migração no mesmo banco utilizado pela API. |

A integração usa o Graph público v1.0 e um tenant configurado por vez. Faz importações completas sob demanda, sem agendamento nem sincronização incremental. A visão de associações inclui usuários diretos visíveis, sem expansão de grupos aninhados. Grupos com membros ocultos podem exigir `Member.Read.Hidden` e ficar incompletos com as permissões atuais. Usuários retornados como membros mas ausentes da coleção de usuários são contabilizados separadamente. O único POST externo é o pedido do token OAuth. Provisionamento externo, alterações de contas e mudanças de membros no Entra ficam fora desta versão.

## Local employee reconciliation (v1.1.0)

Directory synchronization refreshes the read-only snapshot. It never creates Employees. To provision local records, select up to 25 Entra users under **External directory**, open **Reconcile selected users**, review the preview and confirm the batch.

- Reconciliation requires `entra:read`, `entra:provision_local` and `entra:manage_links`. A batch with creation also requires `employees:create`. The department picker requires `departments:read`. The existing explicit link and unlink endpoints remain available under their existing permission.
- A selected identity must be present in the latest completed snapshot of the configured tenant, captured within 24 hours. It must be an enabled Entra Member with `employeeType=Employee`, or an employee ID when the type is blank. Explicit non-employee classifications are blocked. The operator must still verify that the account belongs to a person. Directory metadata alone cannot establish that.
- The stable lookup key is tenant ID plus Entra object ID. Local matching uses Graph `mail`, after validation, trimming and case normalization. The UPN is not an email fallback. A matching email blocks creation. Linking requires choosing the sole matching Employee ID explicitly, and leaves all Employee fields unchanged.
- The import proposes the employee number from Graph `employeeId`, the first and last names from `givenName` and `surname`, and the job title from `jobTitle`. Operators can supply verified local values for those fields and choose an active department. The system does not generate missing employee numbers or infer names from the display name.
- New Employees start `inactive`, with no password, manager, groups or local sign-in access. Activation and assigning access are separate IAM operations outside this flow. The Graph connector still has no write operations or additional Graph permission requirements.
- Apply revalidates the submitted data against the preview's snapshot run. The batch is atomic. One blocked item prevents all Employee and link writes. Repeating an already applied batch returns existing links without creating duplicate records. Audit events store the actor and time, tenant and object IDs, local IDs where applicable, and outcome codes, with no copied names or email addresses.
- To undo a successful link, unlink explicitly in the Entra directory. Unlinking keeps the Employee. For an unintended imported Employee, review the inactive record with the local IAM administrator. There is no automatic deletion or bulk undo.

The preview is `POST /entra/reconciliation/preview` with an `items` array. Apply is `POST /entra/reconciliation/apply` with the same selected actions, `snapshot_run_id` returned by preview and `confirmed: true`. Mark each actionable identity `person_verified: true` after checking it. The response contains per-item statuses and an `applied` flag.

### Upgrade

Back up PostgreSQL, run `python -m backend.app.scripts.migrate`, then run `python -m backend.app.scripts.seed_permissions` to grant the new permission to the existing administrator group. Run Entra sync again to collect the new attributes. The migration rejects existing local email duplicates after trimming and ignoring case. Review and resolve those records explicitly before retrying. Use a maintenance window for the index on large employee tables. [Docker and upgrade guide](RELEASE.md)

## Reconciliação local de colaboradores (v1.1.0)

A sincronização atualiza apenas o snapshot de leitura. A criação de colaboradores depende de prévia e confirmação explícita. Em **External directory**, selecione até 25 usuários, abra **Reconcile selected users** e revise as ações antes de confirmar.

- O fluxo exige `entra:read`, `entra:provision_local` e `entra:manage_links`. Criar exige também `employees:create`. O seletor de departamentos usa `departments:read`. Vínculos e desvínculos manuais existentes continuam com suas permissões atuais.
- A identidade precisa estar presente no último snapshot concluído do tenant configurado, com até 24 horas. Exige-se um Member habilitado com `employeeType=Employee` ou, se o tipo estiver vazio, matrícula informada no Entra. Classificações explícitas de não colaborador são bloqueadas. O operador confirma que a conta pertence a uma pessoa.
- A identidade usa o par tenant e ID do objeto Entra. Para encontrar possíveis duplicatas, o sistema usa `mail` validado, sem espaços nas pontas e sem distinção de maiúsculas. A existência de um e-mail igual bloqueia novas criações. Vincular exige escolher explicitamente o único ID local correspondente e preserva os dados do colaborador.
- A proposta usa `employeeId` para matrícula, `givenName` e `surname` para nome e sobrenome, e `jobTitle` para cargo. O operador pode preencher valores locais verificados e selecionar um departamento ativo. O sistema não inventa dados ausentes.
- Novos colaboradores ficam inativos, sem senha, gestor ou grupos. O fluxo não habilita login nem modifica o Entra.
- A aplicação revalida o lote e verifica a revisão do snapshot. Um item bloqueado cancela todas as alterações de colaboradores e vínculos. Repetir um lote aplicado retorna os vínculos existentes. A auditoria registra operador, horário, IDs e resultado. Para desfazer um vínculo, desvincule explicitamente. O colaborador permanece cadastrado.
- Antes de atualizar, faça backup. Rode `python -m backend.app.scripts.migrate` e `python -m backend.app.scripts.seed_permissions`, depois sincronize novamente. Se houver e-mails locais duplicados ignorando maiúsculas e espaços nas pontas, a migração é interrompida. Resolva os registros manualmente antes de tentar novamente.
