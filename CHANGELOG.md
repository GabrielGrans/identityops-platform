# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog.

## [1.4.0] — Enterprise IAM & Windows Desktop Preview

### English

- Consolidated the Windows Desktop and employee/group administration milestones into a Tauri v2 client with an NSIS installer and shared Web frontend.
- Redesigned the enterprise workspace with a collapsible sidebar, a minimal scrollbar, persistent English and Brazilian Portuguese preferences, tables and detail drawers.
- Added verified IAM dashboard metrics and Analytics for access activity, identities, departments, risks and compliance.
- Unified local and Entra directory workflows with explicit reconciliation, automatic worker synchronization and snapshot diagnostics.
- Added configurable access governance, certification and policy evidence, controlled Graph provisioning, separate operator approvals, direct queue submission for authorized administrators, and auditable verification. Graph writes remain disabled by default.
- Expanded PostgreSQL, authorization and Graph simulation coverage, and added native Windows installer builds to CI.

### Português

- Consolida o Windows Desktop e a administração de colaboradores e grupos em um cliente Tauri v2 com instalador NSIS e frontend compartilhado com a Web.
- Redesenha a interface com sidebar recolhível, scrollbar minimalista, idioma persistente em português do Brasil e inglês, tabelas e painéis de detalhes.
- Inclui métricas IAM verificadas no painel e análises de atividade de acesso, identidades, departamentos, riscos e conformidade.
- Unifica os fluxos de diretório local e Entra com reconciliação explícita, sincronização automática pelo worker e diagnóstico de snapshots.
- Inclui governança configurável, certificações e evidências de política, provisionamento controlado pelo Graph, aprovação separada para operadores, envio direto à fila por administradores autorizados e verificação auditável. A escrita no Graph vem desabilitada.
- Amplia os testes com PostgreSQL, autorização e Graph simulado e inclui a compilação nativa do instalador Windows no CI.

Atualize o banco e as permissões conforme o [guia de instalação](docs/RELEASE.md). Para avaliação / For evaluation.

## [1.1.0] - 2026-11-18

- Add preview and confirmed, local-only provisioning and linking for Microsoft Entra identities.
- Validate person eligibility, snapshot freshness and duplicate normalized emails. Apply batches atomically with audit events and inactive defaults.
- Introduce the `provisioning_110` migration and dedicated local provisioning permission.

**Português.** A reconciliação do Entra permite revisar conflitos e confirmar a criação de colaboradores inativos ou o vínculo com um registro local. O lote é atômico e auditado. A atualização exige a migração `provisioning_110` e a atualização das permissões.

## [1.0.1] - 2026-11-18

- Refresh the IdentityOps login, navigation and favicon with the Grans Enterprise brand.
- Add a scalable hexagonal G emblem, README banner and author credit.

## [1.0.0] - 2026-11-18

- Replace dashboard demo data with versioned IAM summary and audit activity endpoints and a responsive, permission-scoped dashboard.
- Show current inventory, approval queues, certification progress, and recorded lifecycle, revocation, and Entra failure counts. Document metric definitions in English and Portuguese.
- Add the `dashboard_100` migration for the chronological audit index. Existing installations run `python -m backend.app.scripts.migrate`.

## [0.9.0] - 2026-11-18

### Added

- Access certification campaigns with assigned reviewers, date windows and auditable transitions.
- A snapshot of active local employee–group memberships with justified retain and revoke decisions.
- Protection against self-review, duplicate decisions and decisions on memberships removed and re-granted after activation.
- A React campaign console and an additive Alembic migration from v0.8.0.

### Upgrade

- Run `python -m backend.app.scripts.migrate` and reseed permissions for existing installations. See the [campaign guide](docs/CERTIFICATION.md).

## [0.8.0]

### Added

- Read-only Microsoft Graph connector for Entra users, groups and direct user memberships.
- Transactional snapshots, auditable synchronization history and explicit tenant-scoped mappings to local employees and groups.
- RBAC-protected Entra console with synchronization status, search and pagination.
- Explicit Alembic migration for the Entra integration and mocked Graph regression tests.

### Upgrade

- Apply `python -m backend.app.scripts.migrate` to an existing v0.7.0 database and rerun the permission seed. Fresh installs use `--bootstrap`.
- Configure the optional integration as described in [docs/ENTRA_ID.md](docs/ENTRA_ID.md).

## [0.7.0] - 2026-11-18

### Added

- Self-service group access requests, an approval queue, and a business justification for decisions.
- Membership reviews with retain and revoke decisions and an audit trail.
- Joiner, Mover and Leaver operations for the local employee directory and RBAC memberships.
- React screens for groups, permissions, departments, assignments, governance and audit.
- Administrator bootstrap, PostgreSQL integration and concurrency tests, and Docker release packaging in GitHub Actions.

### Upgrade

- Start the updated API to create the additive governance tables. Then rerun the permission seed on existing installations to provision `audit:read` and `reviews:manage`.
- Access managers must explicitly open groups to requests. A change to effective group permissions or active status clears requestability and supersedes pending workflows.


## [0.6.1] - 2026-11-13

### Security
- Separated group management from access assignment permissions.
- Introduced the dedicated `access:manage` RBAC permission.
- Restricted employee group membership and group permission assignments.
- Added regression coverage against privilege escalation.

### Quality
- Backend test suite: 96 passing tests.
- RBAC and security hardening tests passing.

---
## [0.6.0] - 2026-11-13


### Added
- React and TypeScript frontend foundation.
- Login screen and authenticated session validation.
- Dashboard interface.
- Employee directory integrated with the backend API.
- Frontend API client with JWT Bearer authentication.
- Frontend-specific documentation.
- MIT License.
- Project roadmap and architecture documentation.

### Backend
- Expanded department, employee, group and permission API behavior.
- Improved employee update validation.
- Added protection against changing employee activation status through the regular update endpoint.
- Added organizational hierarchy validation.
- Added protection against manager hierarchy cycles.
- Added permission seeding utility.
- Expanded automated backend test coverage.
- Improved repository ignore rules for environment files and test artifacts.

### Quality
- Backend test suite: 95 passing tests in the latest recorded run.
- Backend test coverage: approximately 90%.
- Frontend ESLint validation passing.
- Frontend production build passing.

### Planned
- Complete frontend interfaces for departments, groups and permissions.
- Access request and approval workflows.
- Audit logs.
- Microsoft Entra ID and Microsoft Graph integration.
- Database migrations.
- CI/CD automation.
- End-to-end tests.
