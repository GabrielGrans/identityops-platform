# IdentityOps 1.4.0

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

Faça backup do PostgreSQL antes da atualização e aponte a nova API para o mesmo banco de dados da instalação. A pilha Docker de release usa um volume próprio para instalações novas. Para atualizar a v1.0.1, execute `python -m backend.app.scripts.migrate` com a API nova e o banco existente. No Compose, use `docker compose run --rm --no-deps api python -m backend.app.scripts.migrate`. A revisão `provisioning_110` adiciona atributos ao snapshot Entra e garante a unicidade de e-mails locais normalizados. A migração interrompe o upgrade se já existirem e-mails duplicados. Em um banco de grande porte, programe uma janela de manutenção para aplicar o índice. Consulte o [guia do painel](DASHBOARD.md).

Execute `python -m backend.app.scripts.seed_permissions` e sincronize o Entra novamente para atualizar os atributos e disponibilizar o fluxo de reconciliação. Consulte o [guia do painel](DASHBOARD.md) para saber quais permissões habilitam cada seção.

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

A v1.4.0 consolida o aplicativo Tauri v2 (v1.2.0) e a administração de colaboradores e grupos (v1.3.0). Para homologação, use Windows com Node.js 24, Rust stable/MSVC, Visual Studio Build Tools com C++ e Microsoft Edge WebView2.

Na raiz do repositório, use o ambiente Python e o PostgreSQL configurados conforme o [README](../README.md). Em banco novo, inicialize o esquema com `migrate --bootstrap` e crie o administrador conforme o README. Em uma instalação existente, faça backup e execute a migração sem `--bootstrap`. Atualize as permissões do administrador e inicie a API.

```powershell
python -m backend.app.scripts.migrate
python -m backend.app.scripts.seed_permissions
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Em outro terminal, execute o aplicativo Desktop. Para gerar o instalador NSIS, encerre o modo de desenvolvimento antes de iniciar o build.

```powershell
npm --prefix frontend ci
npm --prefix frontend run desktop:dev
npm --prefix frontend run desktop:build
```

O instalador fica em `frontend\src-tauri\target\release\bundle\nsis\`. Ele instala o cliente Desktop, que requer a API local em `http://127.0.0.1:8000`. Na homologação, teste login, criação de colaborador com senha e grupo, permissões efetivas, edição de grupos e auditoria. O job `desktop` do GitHub Actions gera o instalador para teste como artefato de CI.
