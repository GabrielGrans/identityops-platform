# IdentityOps 0.7.0

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
docker compose --env-file .env -f compose.release.yml up --no-build --pull never --wait
docker compose --env-file .env -f compose.release.yml exec api \
  python -m backend.app.scripts.bootstrap_admin admin@example.com
```

A interface fica em `http://127.0.0.1:8080` e a documentação OpenAPI em `http://127.0.0.1:8080/api/docs`. Para mudar a porta local, defina `IDENTITYOPS_HTTP_PORT`. Para disponibilizar a aplicação remotamente, configure um proxy TLS no ambiente de destino.

## Instalações existentes

Faça backup do PostgreSQL antes da atualização e aponte a nova API para o mesmo banco de dados da instalação. A pilha Docker de release usa um volume próprio para instalações novas. Ao iniciar, o FastAPI cria as tabelas adicionais de governança mantendo os dados existentes.

Execute `python -m backend.app.scripts.seed_permissions` com as variáveis da instalação, ou execute o módulo por meio de `docker compose exec api` quando estiver usando a pilha Docker. A operação atualiza o grupo existente `IT Administrators` e cadastra `audit:read` e `reviews:manage`. O script também restaura as permissões padrão desse grupo. Para funções delegadas, atribua cada permissão conforme o [guia IAM](IAM.md).

## CI e entrega

O workflow `IdentityOps CI and release packaging` executa Pytest com PostgreSQL 17, ESLint e o build do Vite. A execução manual via `workflow_dispatch` também sobe a pilha Docker, verifica a página inicial e a conexão com o banco pela API e gera o artefato `identityops-0.7.0` para implantação manual. Ao informar `release_tag`, o workflow anexa o pacote ao rascunho cujo commit corresponde à execução. A publicação da release e a implantação são manuais.

Para montar a pilha a partir do repositório, configure `.env` e execute:

```sh
npm --prefix frontend ci
VITE_API_URL=/api npm --prefix frontend run build
docker compose --env-file .env -f infrastructure/docker/compose.release.yml up --build --wait
```
