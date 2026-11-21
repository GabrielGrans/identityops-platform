# IdentityOps Web and Desktop

[Português](#português) · [Project README](../README.md)

The React and TypeScript interface presents IAM and SecOps monitoring, including Microsoft Entra ID directory snapshots, observed membership changes, synchronization health, findings, and audit logs. The Windows client shares the same interface using Tauri.

## Local development

Run the FastAPI backend as described in the [setup guide](../README.md), then run `npm ci` and `npm run dev` in this directory. Open [localhost:5173](http://127.0.0.1:5173/). For browser deployments, `VITE_API_URL` defaults to `http://127.0.0.1:8000`. Set it before building when deploying behind a reverse proxy. The desktop client uses the local backend.

Run `npm run lint` and `npm run build` to validate the frontend. The [release guide](../docs/RELEASE.md) covers deployment and upgrade checks.

## Português

A interface React e TypeScript apresenta o monitoramento de IAM e SecOps. Ela reúne snapshots do Microsoft Entra ID, mudanças de associação observadas, saúde da sincronização, achados e auditoria. O cliente Windows reutiliza a interface por meio do Tauri.

Inicie a API conforme o [guia do projeto](../README.md), execute `npm ci` e `npm run dev` nesta pasta e abra [localhost:5173](http://127.0.0.1:5173/). Na versão web, configure `VITE_API_URL` antes da compilação para usar outra rota ou endereço de API. O cliente Windows usa a API local.

Valide o frontend com `npm run lint` e `npm run build`. Consulte o [guia de release](../docs/RELEASE.md) para publicação e atualização.
