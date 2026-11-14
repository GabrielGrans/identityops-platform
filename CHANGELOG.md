# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog.

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
