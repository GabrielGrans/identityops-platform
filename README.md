# Grans Enterprise | IdentityOps

![Grans Enterprise | IdentityOps — IAM & SecOps Monitoring. Engineered by Gabriel Grans.](docs/assets/grans-identityops-banner.svg)

**Monitoramento de IAM e SecOps · IAM & SecOps Monitoring**

Engineered by Gabriel Grans

[![Windows beta](https://img.shields.io/badge/Windows-v2.0.0--beta.2-b42318)](https://github.com/GabrielGrans/identityops-platform/releases/tag/v2.0.0-beta.2)
[![CI](https://github.com/GabrielGrans/identityops-platform/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/GabrielGrans/identityops-platform/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-FastAPI-blue)
![React](https://img.shields.io/badge/React-TypeScript-3178C6)
![IAM](https://img.shields.io/badge/IAM-Microsoft%20Entra%20ID-0078D4)

[Baixar instalador Windows](https://github.com/GabrielGrans/identityops-platform/releases/tag/v2.0.0-beta.2) · [Instalação Windows](docs/WINDOWS.md) · [English](#english) · [Changelog](CHANGELOG.md)

## Português

IdentityOps é uma ferramenta de monitoramento para equipes de IAM e SecOps. Ela consulta identidades, grupos e associações do Microsoft Entra ID, exibe mudanças de acesso observadas e reúne achados de segurança, saúde da sincronização e logs de auditoria.

- **Dashboard e análises** exibem inclusões, remoções e grupos com mais mudanças.
- **Diretório** permite consultar identidades e associações atuais.
- **Achados e logs** ajudam a investigar riscos e falhas de sincronização.
- **Coleta do Entra ID** usa permissões de leitura. A aplicação não disponibiliza comandos de concessão, remoção, aprovação ou provisionamento de acesso.

A primeira coleta bem-sucedida estabelece a referência para um tenant novo. Coletas posteriores comparam associações diretas de usuários em grupos de segurança. O horário registrado é o da coleta que observou a mudança. A comparação de snapshots não identifica o autor da mudança nem captura alterações feitas e revertidas entre duas coletas.

### Executar localmente

Use Python 3.12, Node.js 24 e PostgreSQL. Copie [`.env.example`](.env.example) para `.env`, defina uma senha para o PostgreSQL e gere uma chave de sessão. Para um banco novo, execute os comandos abaixo na raiz, em um ambiente virtual Python.

```sh
docker compose up -d --wait postgres
python -m pip install -r backend/requirements.txt
python -m backend.app.scripts.migrate --bootstrap
python -m backend.app.scripts.bootstrap_admin admin@example.com
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Em outro terminal, execute `cd frontend`, `npm ci` e `npm run dev`. Abra [o aplicativo local](http://127.0.0.1:5173/). Use [o guia de integração Entra](docs/ENTRA_ID.md) para configurar a leitura. Para coleta periódica, execute `python -m backend.app.scripts.entra_worker` em um processo separado.

Na atualização de uma instalação anterior, faça backup, encerre o worker legado antes de trocar a versão e execute a migração sem `--bootstrap`. A nova versão preserva os registros existentes e não processa a fila legada. Os [releases anteriores](https://github.com/GabrielGrans/identityops-platform/releases) mantêm a documentação das versões publicadas.

O [Flextrix Identity & Access](https://github.com/GabrielGrans/flextrix-access-project) é um projeto separado voltado para operações de acesso e ServiceNow.

## English

IdentityOps is an IAM and SecOps monitoring tool. It reads the Microsoft Entra ID directory, tracks observed direct security-group membership changes, and surfaces security findings, sync health, and audit logs. It provides no access grant, revocation, approval, or provisioning actions.

The first successful collection establishes a baseline for a new tenant. Subsequent collections compare direct user-to-security-group membership. The timestamp shows when the change was observed. Snapshot comparison does not identify the actor or capture changes that were reversed between collections.

Use the setup commands above to start PostgreSQL, bootstrap a fresh database, create a local operator and run FastAPI. Start the frontend with `npm ci` and `npm run dev`. Follow the [Entra setup guide](docs/ENTRA_ID.md) to configure read permissions. Run the dedicated worker for scheduled collection.

When upgrading an earlier deployment, back up the database, stop the legacy worker, and migrate without `--bootstrap`. Existing records remain available, and the new worker does not process the legacy queue. See the [previous releases](https://github.com/GabrielGrans/identityops-platform/releases) for version-specific documentation.

**Developed by Gabriel Grans** · [MIT license](LICENSE)
