# Instalar IdentityOps no Windows

[English](#english) · [Baixar o instalador](https://github.com/GabrielGrans/identityops-platform/releases/tag/v2.0.0-beta.2)

O instalador Windows x64 inclui a interface. A API e o PostgreSQL rodam em separado. Para a primeira instalação, use o código-fonte da mesma versão, Docker Desktop em execução e Python 3.12. Extraia o código-fonte do ZIP da release e abra o PowerShell na pasta que contém `backend`.

## 1. Banco e API

Cole o bloco abaixo para uma **instalação nova**. O banco usa a porta `5540`, e a API usa a porta `8000`. Mantenha a janela aberta enquanto usa o aplicativo.

```powershell
$env:POSTGRES_HOST = '127.0.0.1'
$env:POSTGRES_PORT = '5540'
$env:POSTGRES_USER = 'identityops'
$env:POSTGRES_DB = 'identityops'
$env:POSTGRES_PASSWORD = [Guid]::NewGuid().ToString('N')
$env:SECRET_KEY = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')
$env:ENTRA_ENABLED = 'false'
$env:ENTRA_WRITE_ENABLED = 'false'
$env:SERVICENOW_ENABLED = 'false'
$env:SERVICENOW_SIMULATION = 'true'

if (docker container ls -a --format '{{.Names}}' | Where-Object { $_ -eq 'identityops-windows-db' }) {
    throw 'Este banco do aplicativo já existe. Use a configuração salva na primeira instalação.'
}

# Guarde este arquivo localmente. Ele contém a senha do banco e a chave de sessão.
@(
    "POSTGRES_HOST=$env:POSTGRES_HOST"
    "POSTGRES_PORT=$env:POSTGRES_PORT"
    "POSTGRES_USER=$env:POSTGRES_USER"
    "POSTGRES_DB=$env:POSTGRES_DB"
    "POSTGRES_PASSWORD=$env:POSTGRES_PASSWORD"
    "SECRET_KEY=$env:SECRET_KEY"
    'ENTRA_ENABLED=false'
    'ENTRA_WRITE_ENABLED=false'
    'SERVICENOW_ENABLED=false'
    'SERVICENOW_SIMULATION=true'
) | Set-Content -LiteralPath .env.windows.local -Encoding ascii

docker run -d --name identityops-windows-db -p "127.0.0.1:${env:POSTGRES_PORT}:5432" `
  -e POSTGRES_DB -e POSTGRES_USER -e POSTGRES_PASSWORD -v identityops-windows-data:/var/lib/postgresql/data postgres:17
if ($LASTEXITCODE) { throw 'Falha ao iniciar o PostgreSQL.' }

for ($i = 0; $i -lt 30; $i++) {
    docker exec identityops-windows-db pg_isready -h 127.0.0.1 -U $env:POSTGRES_USER | Out-Null
    if (-not $LASTEXITCODE) { break }
    if ($i -eq 29) { throw 'O PostgreSQL não ficou disponível.' }
    Start-Sleep -Seconds 1
}

py -3.12 -m venv .venv
if ($LASTEXITCODE) { throw 'Falha ao criar o ambiente Python.' }
$python = '.\.venv\Scripts\python.exe'
& $python -m pip install -r backend/requirements.txt
if ($LASTEXITCODE) { throw 'Falha ao instalar as dependências.' }
& $python -m backend.app.scripts.migrate --bootstrap
if ($LASTEXITCODE) { throw 'Falha ao preparar o banco.' }
& $python -m backend.app.scripts.bootstrap_admin admin@example.com
if ($LASTEXITCODE) { throw 'Falha ao criar a conta local.' }
& $python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

No passo `bootstrap_admin`, digite uma senha nova de pelo menos 12 caracteres quando o terminal solicitar. O login será `admin@example.com`.

## 2. Instalar e entrar

1. Baixe o `.exe` da release. Para conferir o download, compare `Get-FileHash .\<instalador.exe> -Algorithm SHA256` com `SHA256SUMS`.
2. Execute o instalador e abra **IdentityOps** pelo menu Iniciar.
3. Com a API em execução, entre com a conta local que você criou.

Para voltar a usar o app depois, abra outro PowerShell na pasta do código e rode:

```powershell
docker start identityops-windows-db
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app `
  --host 127.0.0.1 --port 8000 --env-file .env.windows.local
```

Se o login informar falha de conexão, confira se `http://127.0.0.1:8000/health/database` mostra `"database":"connected"`. O aplicativo usa essa porta local. Para ambientes existentes, preserve o banco e siga o guia de atualização antes de executar migrações. Se a porta estiver ocupada por outra API, identifique o serviço antes de iniciar uma segunda instância.

## English

Download the Windows x64 installer and the source ZIP for the same release. Docker Desktop and Python 3.12 are required for the local API setup. Open PowerShell in the extracted source and run the block above. It creates a dedicated PostgreSQL container on port 5540, sets up the database, creates the local administrator account, and runs FastAPI on port 8000. Enter a password of at least 12 characters when prompted.

Install the `.exe`, then sign in with `admin@example.com` and the password you created. Keep the API terminal running. To restart later, use the second PowerShell block. The generated `.env.windows.local` contains local secrets and is excluded by Git. The default setup leaves external integrations disabled.

Para preencher o painel com coletas do laboratório, configure a integração de leitura conforme o [guia do Entra ID](ENTRA_ID.md). Edite o arquivo local .env.windows.local e reinicie a API.
