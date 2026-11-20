# Grans Enterprise | IdentityOps

![Grans Enterprise | IdentityOps. Identity & Access Management Platform. Engineered by Gabriel Grans.](docs/assets/grans-identityops-banner.svg)

**Identity & Access Management Platform**

Engineered by Gabriel Grans

[![v1.4.0 Preview](https://img.shields.io/badge/Release-v1.4.0%20Preview-b42318)](https://github.com/GabrielGrans/identityops-platform/releases/tag/v1.4.0)
[![CI](https://github.com/GabrielGrans/identityops-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/GabrielGrans/identityops-platform/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-FastAPI-blue)
![React](https://img.shields.io/badge/React-TypeScript-3178C6)
![IAM](https://img.shields.io/badge/IAM-Microsoft%20Entra%20ID-0078D4)

**Identity governance · RBAC · Access workflows · Lifecycle automation · Microsoft Entra ID**

**English | Português**

### v1.4.0 Preview

**English.** Evaluate enterprise IAM from the Web or the Windows Desktop client. The client requires a running FastAPI API and PostgreSQL. Automatic Microsoft Entra synchronization requires the server-side worker. This preview is for evaluation and has yet to be qualified for production.

**Português.** Avalie o IAM corporativo pela Web ou pelo cliente Windows Desktop. O cliente depende da API FastAPI e do PostgreSQL em execução. A sincronização automática com o Microsoft Entra exige o worker no servidor. Esta pré-release é destinada à avaliação e ainda aguarda homologação para produção.

[GitHub Pre-release](https://github.com/GabrielGrans/identityops-platform/releases/tag/v1.4.0) · [Windows and Docker installation / Instalação Windows e Docker](docs/RELEASE.md) · [IAM](docs/IAM.md) · [Microsoft Entra](docs/ENTRA_AUTOMATION.md) · [Analytics / Análises](docs/ENTERPRISE_UI.md) · [Previous stable release / Release estável anterior](https://github.com/GabrielGrans/identityops-platform/releases/tag/v1.1.0)

![IAM Governance Dashboard with evaluation data / Painel de governança IAM com dados de avaliação](docs/assets/v140-dashboard.png)

---

# 🇺🇸 English

## Overview

IdentityOps is a bilingual IAM administration platform for managing employee identities, local access and Microsoft Entra security-group memberships. The Web and Windows Desktop workspaces bring access decisions, verified provisioning outcomes and governance evidence together under role-based access control.

## Current Features

### Identity Management
- **Employee Management:** Create, retrieve, update, and deactivate employee records.
- **Department Management:** Organize employees by department.
- **Access Group Management:** Create, retrieve, update, and deactivate access groups.
- **Permission Management:** Define granular permissions based on resources and actions.

### Authentication & Authorization
- **JWT Authentication:** Secure API authentication using JSON Web Tokens.
- **Password Security:** Password hashing using Argon2.
- **Role-Based Access Control (RBAC):** Manage access through employee group membership and group permissions.
- **Granular Permission Enforcement:** Separate group administration from access assignment privileges.
- **Access Assignment Protection:** Restrict employee membership and group permission assignments to authorized users.
- **Privilege Escalation Protection:** Enforce backend authorization rules and include regression tests for unauthorized access attempts.

### IAM workspace

- **Web and Desktop.** React and Tauri v2 share a dark, bilingual interface with collapsible navigation and an NSIS installer for Windows.
- **Dashboard and Analytics.** See verified grants and revocations, active Entra accounts, open findings, provisioning outcomes and department distributions. Historical views use recorded evidence.
- **Unified directory.** Explore Entra and local identities and groups, review direct memberships, and preview explicit local reconciliation.
- **Access workflows.** Submit and review requests, manage lifecycle events, certify memberships and investigate audit events.
- **Microsoft Graph.** A server worker imports directory snapshots and executes approved changes for allowlisted security groups when writeback is explicitly enabled. Authorized administrators can submit eligible requests directly to the queue. The worker verifies membership after execution.
### Infrastructure & Quality
- **PostgreSQL:** Relational database integration.
- **SQLAlchemy ORM:** Database models and persistence.
- **Docker Compose:** Local infrastructure orchestration.
- **Automated Testing:** Backend test suite using Pytest.
- **API Documentation:** OpenAPI, Swagger UI, and ReDoc.

## Technology Stack

| Category | Technology |
|---|---|
| Backend | Python, FastAPI |
| Frontend | React, TypeScript, Vite |
| Windows Desktop | Tauri v2, Rust, WebView2, NSIS |
| Database | PostgreSQL 17 |
| ORM | SQLAlchemy |
| Authentication | JWT |
| Password Hashing | Argon2 |
| Configuration | Pydantic Settings |
| Infrastructure | Docker, Docker Compose |
| API Documentation | OpenAPI / Swagger |
| Testing | Pytest |

## Security Architecture

IdentityOps implements permission-based authorization using RBAC.

The authorization model distinguishes between managing access groups and assigning access:

| Permission | Responsibility |
|---|---|
| `groups:manage` | Create, update, and deactivate access groups |
| `access:manage` | Assign employees to groups and permissions to groups |

This separation prevents users with group administration privileges from automatically receiving permission to grant access.

Authorization is enforced by the backend, independently of frontend visibility.

## Architecture

```text
IdentityOps Platform
│
├── Backend
│   ├── API Routes
│   ├── Core
│   │   ├── Authentication
│   │   ├── Authorization
│   │   └── Configuration
│   ├── Models
│   ├── Schemas
│   ├── Services
│   ├── Scripts
│   └── Tests
│
├── Frontend
│   ├── React
│   ├── TypeScript
│   ├── Dashboard
│   ├── Employee Management
│   └── API Services
│
├── Infrastructure
│   └── Docker Compose
│
└── Documentation
```

## Getting Started

### Prerequisites

- Python 3.12 or compatible version
- Node.js 24 and npm
- Docker Desktop
- Git

### 1. Clone the repository

```powershell
git clone https://github.com/GabrielGrans/identityops-platform.git
cd identityops-platform
```

### 2. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Configure environment variables

```powershell
Copy-Item .env.example .env
```

Generate a secret key:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the generated value into `SECRET_KEY` in your `.env` file.

### 4. Install backend dependencies

```powershell
pip install -r backend/requirements.txt
```

### 5. Start PostgreSQL

```powershell
docker compose up -d
```

### 6. Apply database migrations and start the backend API

Run `python -m backend.app.scripts.migrate --bootstrap` for a new database.
Use `python -m backend.app.scripts.migrate` for an existing database after making a backup.

```powershell
python -m uvicorn backend.app.main:app --reload
```

### 7. Configure the administrator

With the API running, open another terminal and run this on a fresh database:

```powershell
python -m backend.app.scripts.bootstrap_admin admin@example.com
```

For an existing installation with an active `IT Administrators` group, run
`python -m backend.app.scripts.seed_permissions` to provision the new permissions.
Sign in with the administrator email and the password configured at the prompt.

### 8. Start the frontend

Open another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

The frontend will be available at:

```text
http://localhost:5173/
```

## API Documentation

Once the backend is running:

- **Swagger UI:** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc

## Running Tests

From the project root, with the virtual environment activated:

```powershell
python -m pytest backend/tests -v
```

Run `npm run lint` and `npm run build` in `frontend`. The default API tests use SQLite.
Set `IDENTITYOPS_TEST_DATABASE_URL` to a PostgreSQL test database to include concurrency tests.
GitHub Actions runs the PostgreSQL suite and frontend checks. The manual workflow packages
Docker images for controlled deployment. See the [release guide](docs/RELEASE.md).

## Roadmap

- [x] FastAPI backend foundation
- [x] PostgreSQL integration
- [x] Employee and department management
- [x] Access group management
- [x] Permission management
- [x] JWT authentication
- [x] Argon2 password hashing
- [x] Role-Based Access Control (RBAC)
- [x] Granular access assignment permissions
- [x] RBAC security hardening and regression tests
- [x] React + TypeScript frontend foundation
- [x] Initial IAM administrative dashboard
- [x] Employee management interface
- [x] Complete frontend integration for all IAM modules
- [x] Access request and approval workflows
- [x] Joiner, Mover, and Leaver automation
- [x] Audit logs and access reviews
- [x] Read-only Microsoft Entra ID / Microsoft Graph integration
- [x] CI/CD pipeline

## Project Status

**v1.4.0 Preview** consolidates the Windows Desktop and employee/group administration milestones with Entra automation and the enterprise IAM workspace. The preview uses direct Entra memberships and current directory snapshots. Historical risk and directory growth trends require snapshots that are currently unavailable. Graph writeback defaults to disabled. See the [installation guide and limitations](docs/RELEASE.md#windows-desktop).

---

# 🇧🇷 Português

## Visão Geral

O IdentityOps é uma plataforma bilíngue de administração IAM para gerenciar identidades de colaboradores, acessos locais e vínculos com grupos de segurança do Microsoft Entra. As interfaces Web e Windows Desktop reúnem decisões de acesso, resultados verificados de provisionamento e evidências de governança sob controle de acesso por funções.

## Funcionalidades Implementadas

### Gerenciamento de Identidades
- **Gerenciamento de Colaboradores:** Criar, consultar, atualizar e desativar registros de funcionários.
- **Gerenciamento de Departamentos:** Organizar colaboradores por departamento.
- **Gerenciamento de Grupos de Acesso:** Criar, consultar, atualizar e desativar grupos de acesso.
- **Gerenciamento de Permissões:** Definir permissões granulares com base em recursos e ações.

### Autenticação e Autorização
- **Autenticação JWT:** Autenticação segura utilizando JSON Web Tokens.
- **Segurança de Senhas:** Hash de senhas utilizando Argon2.
- **Controle de Acesso Baseado em Funções (RBAC):** Gerenciar acessos por meio de grupos e permissões.
- **Controle Granular de Permissões:** Separação entre administração de grupos e atribuição de acessos.
- **Proteção na Atribuição de Acessos:** Restringir a associação de colaboradores a grupos e a atribuição de permissões a usuários autorizados.
- **Proteção contra Escalação de Privilégios:** Aplicar regras de autorização no backend e validar tentativas de acesso não autorizado por meio de testes automatizados.

### Espaço de trabalho IAM

- **Web e Desktop.** React e Tauri v2 compartilham uma interface escura e bilíngue, com navegação recolhível e instalador NSIS para Windows.
- **Painel e Análises.** Consulte concessões e revogações verificadas, contas ativas do Entra, achados em aberto, resultados de provisionamento e distribuição por departamento. As consultas históricas usam evidências registradas.
- **Diretório unificado.** Explore identidades e grupos locais e do Entra, consulte vínculos diretos e revise a prévia da reconciliação local explícita.
- **Fluxos de acesso.** Envie e avalie solicitações, gerencie eventos de ciclo de vida, certifique vínculos e investigue eventos de auditoria.
- **Microsoft Graph.** Um worker no servidor importa snapshots e executa alterações aprovadas em grupos de segurança autorizados quando a escrita é habilitada explicitamente. Administradores autorizados podem encaminhar solicitações elegíveis diretamente para a fila. O worker verifica o vínculo após a execução.
### Infraestrutura e Qualidade
- **PostgreSQL:** Integração com banco de dados relacional.
- **SQLAlchemy ORM:** Modelagem e persistência de dados.
- **Docker Compose:** Orquestração da infraestrutura local.
- **Testes Automatizados:** Suíte de testes backend utilizando Pytest.
- **Documentação da API:** OpenAPI, Swagger UI e ReDoc.

## Tecnologias

| Categoria | Tecnologia |
|---|---|
| Backend | Python, FastAPI |
| Frontend | React, TypeScript, Vite |
| Windows Desktop | Tauri v2, Rust, WebView2, NSIS |
| Banco de Dados | PostgreSQL 17 |
| ORM | SQLAlchemy |
| Autenticação | JWT |
| Hash de Senhas | Argon2 |
| Configurações | Pydantic Settings |
| Infraestrutura | Docker, Docker Compose |
| Documentação da API | OpenAPI / Swagger |
| Testes | Pytest |

## Arquitetura de Segurança

O IdentityOps implementa autorização baseada em permissões utilizando RBAC.

O modelo de autorização diferencia a administração de grupos da atribuição de acessos:

| Permissão | Responsabilidade |
|---|---|
| `groups:manage` | Criar, atualizar e desativar grupos de acesso |
| `access:manage` | Associar colaboradores a grupos e permissões a grupos |

Essa separação impede que usuários com privilégios de administração de grupos recebam automaticamente autorização para conceder acessos.

As regras de autorização são aplicadas no backend, independentemente da visibilidade dos recursos no frontend.

## Arquitetura

```text
IdentityOps Platform
│
├── Backend
│   ├── Rotas da API
│   ├── Core
│   │   ├── Autenticação
│   │   ├── Autorização
│   │   └── Configurações
│   ├── Models
│   ├── Schemas
│   ├── Services
│   ├── Scripts
│   └── Tests
│
├── Frontend
│   ├── React
│   ├── TypeScript
│   ├── Dashboard
│   ├── Gerenciamento de Colaboradores
│   └── Serviços de API
│
├── Infraestrutura
│   └── Docker Compose
│
└── Documentação
```

## Como Executar

### Pré-requisitos

- Python 3.12 ou versão compatível
- Node.js 24 e npm
- Docker Desktop
- Git

### 1. Clonar o repositório

```powershell
git clone https://github.com/GabrielGrans/identityops-platform.git
cd identityops-platform
```

### 2. Criar e ativar o ambiente virtual

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Configurar as variáveis de ambiente

```powershell
Copy-Item .env.example .env
```

Gere uma chave secreta:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copie o valor gerado para `SECRET_KEY` no arquivo `.env`.

### 4. Instalar as dependências do backend

```powershell
pip install -r backend/requirements.txt
```

### 5. Iniciar o PostgreSQL

```powershell
docker compose up -d
```

### 6. Aplicar as migrações e iniciar a API

Em um banco novo, execute `python -m backend.app.scripts.migrate --bootstrap`.
Em um banco existente, faça backup e execute `python -m backend.app.scripts.migrate`.

```powershell
python -m uvicorn backend.app.main:app --reload
```

### 7. Configurar o administrador

Com a API em execução e um banco novo, abra outro terminal e execute:

```powershell
python -m backend.app.scripts.bootstrap_admin admin@example.com
```

Em uma instalação existente com o grupo `IT Administrators` ativo, execute
`python -m backend.app.scripts.seed_permissions` para provisionar as novas permissões.
Entre com o e-mail do administrador e a senha cadastrada no terminal.

### 8. Iniciar o frontend

Abra outro terminal:

```powershell
cd frontend
npm ci
npm run dev
```

O frontend estará disponível em:

```text
http://localhost:5173/
```

## Documentação da API

Com o backend em execução:

- **Swagger UI:** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc

## Executando os Testes

Na raiz do projeto, com o ambiente virtual ativado:

```powershell
python -m pytest backend/tests -v
```

Execute `npm run lint` e `npm run build` em `frontend`. Os testes da API usam SQLite por padrão.
Configure `IDENTITYOPS_TEST_DATABASE_URL` com um banco PostgreSQL de testes para incluir a validação
de concorrência. O GitHub Actions executa a suíte PostgreSQL e as verificações do frontend.
O fluxo manual gera imagens Docker para implantação controlada. Consulte o [guia da versão](docs/RELEASE.md).

## Roadmap

- [x] Estrutura inicial do backend com FastAPI
- [x] Integração com PostgreSQL
- [x] Gerenciamento de colaboradores e departamentos
- [x] Gerenciamento de grupos de acesso
- [x] Gerenciamento de permissões
- [x] Autenticação JWT
- [x] Hash de senhas com Argon2
- [x] Controle de Acesso Baseado em Funções (RBAC)
- [x] Permissões granulares para atribuição de acessos
- [x] Reforço de segurança RBAC e testes de regressão
- [x] Estrutura inicial do frontend com React + TypeScript
- [x] Dashboard administrativo inicial
- [x] Interface de gerenciamento de colaboradores
- [x] Integração completa do frontend com todos os módulos IAM
- [x] Fluxos de solicitação e aprovação de acessos
- [x] Automação do ciclo Joiner, Mover e Leaver
- [x] Logs de auditoria e revisões de acesso
- [x] Integração de leitura com Microsoft Entra ID / Microsoft Graph
- [x] Pipeline CI/CD

## Status do Projeto

**v1.4.0 Preview** consolida o Windows Desktop e a administração de colaboradores e grupos com a automação Entra e o espaço de trabalho IAM corporativo. A pré-release usa vínculos diretos e snapshots atuais do diretório. Tendências históricas de risco e de crescimento exigem snapshots ainda indisponíveis. A escrita no Graph vem desabilitada. Consulte o [guia de instalação e limitações](docs/RELEASE.md#windows-desktop).

---

**Developed by Gabriel Grans**

GitHub: https://github.com/GabrielGrans

Project: https://github.com/GabrielGrans/identityops-platform
