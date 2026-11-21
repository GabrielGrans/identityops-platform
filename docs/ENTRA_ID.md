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

A consulta requer entra:read, a coleta manual requer entra:sync e o histórico de mudanças observadas requer entra:read e audit:read.

## Fluxo de dados

**React → API FastAPI com RBAC → Microsoft Identity Platform e Microsoft Graph → PostgreSQL.** A API busca um token por `client_credentials` no endpoint OAuth do tenant com escopo `https://graph.microsoft.com/.default`. O token fica em memória no processo da API. A API renova o token antes do vencimento e invalida o cache se o Graph responder 401. O navegador usa apenas a sessão local.

O conector percorre páginas de usuários, grupos e membros diretos. A API aceita paginação somente na origem Microsoft e na mesma rota da coleção. Cada execução tem até 500 requisições, incluindo retries, um orçamento de 120 segundos para o Graph, até 10.000 usuários, 10.000 grupos e 25.000 entradas de membros. O limite de requisições normalmente restringe o total de grupos antes dos limites de objetos. Páginas superiores a 4 MiB são rejeitadas.

A coleta grava o snapshot e os eventos observados em uma única transação. Uma falha mantém a última coleta bem-sucedida. Os eventos informam o usuário, o grupo e o momento da coleta.

Os registros importados ficam separados do diretório IAM local. Vínculos de versões antigas são preservados para consulta.

## API

Use o Swagger em `http://127.0.0.1:8000/docs` ou `http://127.0.0.1:8080/api/docs` na pilha Docker. Autorize com o JWT de uma sessão local. Exemplos de métodos, caminhos e payload:

```text
GET  /entra/status
POST /entra/sync
GET  /entra/sync-runs?limit=25&before_id=100
GET  /entra/users?search=fixture&limit=25
GET  /entra/groups?search=security&limit=25
GET  /entra/groups/00000000-0000-4000-8000-000000000001/members
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

A integração usa o Graph público v1.0 e um tenant configurado por vez. A coleta pode ser manual ou periódica pelo worker de monitoramento. A visão de associações inclui usuários diretos visíveis, sem expansão de grupos aninhados. Grupos com membros ocultos podem exigir `Member.Read.Hidden` e ficar incompletos com as permissões atuais. Usuários retornados como membros mas ausentes da coleção de usuários são contabilizados separadamente. O único POST externo é o pedido do token OAuth. Provisionamento externo, alterações de contas e mudanças de membros no Entra ficam fora desta versão.

Para detalhes de reconciliação, administração e provisionamento das versões anteriores, consulte os [releases históricos](https://github.com/GabrielGrans/identityops-platform/releases).
