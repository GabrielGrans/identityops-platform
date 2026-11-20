# IdentityOps v1.4.0 Preview

Pré-release pública para avaliação. A homologação em produção, em estações Windows reais e com tenants reais fica a cargo do ambiente de avaliação.

Public pre-release for evaluation. Production qualification, installation on Windows workstations and real-tenant validation remain outside the verified CI and simulated Graph coverage.

## Pacote Docker

O pacote inclui imagens da API, da interface e do PostgreSQL 17 para a arquitetura indicada no nome do arquivo de entrega ou na plataforma do runner. Use Docker Engine com Compose v2.

Em um diretório com `identityops-images.tar.gz`, `SHA256SUMS`, `compose.release.yml` e `.env.example`:

```sh
sha256sum -c SHA256SUMS
docker load -i identityops-images.tar.gz
cp .env.example .env
```

Defina `POSTGRES_PASSWORD` e `SECRET_KEY` em `.env` com valores próprios. Para gerar uma chave JWT, use `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

```sh
docker compose --env-file .env -f compose.release.yml up -d --pull never --wait postgres
docker compose --env-file .env -f compose.release.yml run --rm --no-deps --pull never api \
  python -m backend.app.scripts.migrate --bootstrap
docker compose --env-file .env -f compose.release.yml up --no-build --pull never --wait
docker compose --env-file .env -f compose.release.yml exec api \
  python -m backend.app.scripts.bootstrap_admin admin@example.com
```

A interface fica em `http://127.0.0.1:8080` e a documentação OpenAPI em `http://127.0.0.1:8080/api/docs`. Para mudar a porta local, defina `IDENTITYOPS_HTTP_PORT`. Para disponibilizar a aplicação remotamente, configure um proxy TLS no ambiente de destino.

## Instalações existentes

Antes de atualizar, pare a API e o worker, preserve o `.env` em local seguro e faça um backup verificável do banco. Para o Compose local, substitua `identityops` abaixo pelos valores de `POSTGRES_USER` e `POSTGRES_DB` da instalação, respectivamente. Para o Compose de release, acrescente `-f compose.release.yml` ao comando e use o nome de contêiner retornado por `docker compose ps` em `docker cp`.

```powershell
docker compose exec -T postgres pg_dump -U identityops -d identityops -Fc -f /tmp/identityops-pre-v140.dump
docker compose exec -T postgres pg_restore --list /tmp/identityops-pre-v140.dump
docker cp identityops-postgres:/tmp/identityops-pre-v140.dump .\identityops-pre-v140.dump
```

Mantenha uma cópia protegida e teste a restauração em um banco separado. Configure a nova API para o mesmo banco da instalação. O Compose de release usa um volume independente para instalações novas.

Execute `python -m backend.app.scripts.migrate` sem `--bootstrap` em bancos existentes e, em seguida, `python -m backend.app.scripts.seed_permissions`. No Compose, prefixe os comandos com `docker compose -f compose.release.yml run --rm --no-deps api`. A atualização da v1.1.0 aplica as revisões `enterprise_governance_140`, `entra_automation`, `unified_entra_directory` e `official_departments`. Revise as funções atribuídas e as permissões do grupo administrador após o seed. Antes de migrar de uma versão anterior à v1.1.0, verifique e-mails locais duplicados normalizados, pois a revisão `provisioning_110` exige unicidade.

Depois de validar o login e a saúde do banco, reinicie o worker se a sincronização estiver configurada. Consulte o [guia de automação Entra](ENTRA_AUTOMATION.md).

## CI e entrega

O workflow `IdentityOps CI and release packaging` executa Pytest com PostgreSQL 17, ESLint e o build do Vite. A execução manual via `workflow_dispatch` também sobe a pilha Docker, verifica a página inicial e a conexão com o banco pela API e gera o artefato `identityops-1.4.0` para implantação manual. Ao informar `release_tag`, o workflow anexa o pacote ao rascunho cujo commit corresponde à execução. A publicação da release e a implantação são manuais.

Para montar a pilha a partir do repositório, configure `.env` e execute:

```sh
npm --prefix frontend ci
VITE_API_URL=/api npm --prefix frontend run build
docker compose --env-file .env -f infrastructure/docker/compose.release.yml up -d --wait postgres
docker compose --env-file .env -f infrastructure/docker/compose.release.yml build
docker compose --env-file .env -f infrastructure/docker/compose.release.yml run --rm --no-deps api \
  python -m backend.app.scripts.migrate --bootstrap
docker compose --env-file .env -f infrastructure/docker/compose.release.yml up --no-build --wait
```

Configure a integração opcional conforme o [guia Microsoft Entra ID](ENTRA_ID.md).

## Windows Desktop

1. Use Windows x64 com Microsoft Edge WebView2, Python 3.12 e PostgreSQL 17. Docker Desktop é uma opção para rodar o PostgreSQL local. Node.js 24, Rust stable/MSVC e Visual Studio Build Tools com C++ são necessários para compilar o cliente a partir do código.
2. Use o código da tag `v1.4.0` e configure o ambiente Python e o `.env` conforme o [README](../README.md). Em um banco novo, execute `python -m backend.app.scripts.migrate --bootstrap` e crie o administrador com `python -m backend.app.scripts.bootstrap_admin admin@example.com`. Em um banco existente, faça backup, migre sem `--bootstrap` e atualize as permissões conforme a seção anterior.
3. Inicie a API local com `python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`. Verifique `http://127.0.0.1:8000/health/database`.
4. Baixe o instalador NSIS x64 e o arquivo de checksums na [pré-release v1.4.0](https://github.com/GabrielGrans/identityops-platform/releases/tag/v1.4.0). Compare a saída do PowerShell com o SHA-256 publicado antes de abrir o instalador.

```powershell
Get-FileHash .\IdentityOps_1.4.0_x64-setup.exe -Algorithm SHA256
```

5. Abra o cliente pelo menu Iniciar e entre com as credenciais cadastradas na API. Mantenha a API e o PostgreSQL ativos durante o uso.
6. Para sincronização automática, configure o [Microsoft Graph](ENTRA_AUTOMATION.md#app-registration-and-consent) no servidor e execute `python -m backend.app.scripts.entra_worker` em outro terminal. Guarde credenciais em um secret store ou no `.env` do servidor. Use o consentimento administrativo para as permissões de leitura do Graph e mantenha `ENTRA_WRITE_ENABLED=false`. Limite testes de escrita a grupos suportados em um tenant de teste, com aprovação explícita e allowlist.

Para compilar o instalador localmente:

```powershell
npm --prefix frontend ci
npm --prefix frontend run desktop:build
```

A saída do build fica em `frontend/src-tauri/target/release/bundle/nsis/`. O instalador distribui o cliente, que acessa a API local em `http://127.0.0.1:8000`. Use a configuração de loopback para avaliar o cliente. Para validar a aplicação Web em Docker, siga a seção Pacote Docker.

### Windows quick start (English)

Use Windows x64 with Edge WebView2 and a local FastAPI service backed by PostgreSQL 17. Check out tag `v1.4.0` and configure the Python environment and server `.env` using the README. On a fresh database, run `migrate --bootstrap` and `bootstrap_admin`. For an existing database, back up and test restoration first, then run `migrate` and `seed_permissions`. Start FastAPI on `127.0.0.1:8000`, verify the installer with `Get-FileHash -Algorithm SHA256`, and run the NSIS setup. Start `python -m backend.app.scripts.entra_worker` separately for automatic Entra synchronization. Keep `ENTRA_WRITE_ENABLED=false` and use server-side secrets and scoped Graph read permissions. See the [Entra setup guide](ENTRA_AUTOMATION.md).

### Limitações da pré-release / Preview limitations

- O cliente Desktop depende da API e do banco em execução. A sincronização automática depende do worker no servidor.
- O diretório usa vínculos diretos e snapshots. Tendências históricas de risco e de crescimento ainda dependem de snapshots históricos.
- A validação com Graph simulado e o build Windows no CI cobrem os fluxos automatizados. Faça a homologação da instalação e do tenant separadamente.
- The client needs the API and database running, and automatic Entra synchronization needs the worker. The directory uses direct memberships and snapshots. Historical risk and directory growth trends require historical snapshots. Perform workstation and tenant qualification separately.
