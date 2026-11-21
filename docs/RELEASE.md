# IdentityOps 2.0 beta

[English](#english) · [README](../README.md) · [Changelog](../CHANGELOG.md)

A beta **v2.0.0-beta.2** apresenta o IdentityOps como ferramenta de monitoramento IAM e SecOps. O dashboard usa diferenças entre coletas para identificar inclusões e remoções de membros. Os eventos mostram o horário da observação e o autor permanece desconhecido.

## Instalação e atualização

- Siga o [README](../README.md) para executar a versão web e o [guia do Entra](ENTRA_ID.md) para usar uma integração de leitura.
- Em uma instalação existente, faça backup do PostgreSQL, desligue o processo legado de provisionamento e execute `python -m backend.app.scripts.migrate` sem `--bootstrap`. Mantenha os dados antigos de auditoria e os registros de solicitações.
- Para Docker, use `infrastructure/docker/compose.release.yml`. Configure as credenciais a partir de `.env.example` e execute a migração antes de iniciar a API. O perfil de coleta periódica é opcional. A versão Windows usa a mesma API local.
- Valide com dados fictícios e depois com um tenant de teste. Confira duas coletas consecutivas, a exibição de uma mudança e a ausência de rotas de alteração de acesso no Swagger.

Os [releases anteriores](https://github.com/GabrielGrans/identityops-platform/releases) preservam os instaladores, pacotes e guias de cada versão. Os arquivos de instalação da beta só devem ser disponibilizados depois da validação de empacotamento no GitHub Actions.

## English

**v2.0.0-beta.2** previews IAM and SecOps monitoring. Membership changes are inferred from consecutive snapshots. An observation records when a change was detected. Snapshots do not identify the actor.

For a fresh install, use the [README](../README.md) and [Entra read-only setup](ENTRA_ID.md). For an upgrade, back up PostgreSQL, stop the legacy provisioning worker, and run the migration without `--bootstrap`. Historical records remain available. Validate consecutive snapshots, audit visibility, and the API surface on a test tenant. Publish beta installers only after the GitHub Actions packaging checks pass.
