# Demonstração IdentityOps e ServiceNow

Use uma PDI e um tenant de laboratório ou a suíte de respostas simuladas. Use identidades fictícias e mantenha `SERVICENOW_SIMULATION=true` e `ENTRA_WRITE_ENABLED=false`. Garanta que o PostgreSQL, a API e o worker estejam executando. Consulte o [guia da PDI](SERVICENOW.md) para implantar o catálogo e os scripts.

| Tempo | Mostre |
| --- | --- |
| 0:00–0:40 | Abra o IdentityOps Desktop, entre com um operador de teste e mostre o painel IAM. Abra Colaboradores e alterne entre local e Entra. |
| 0:40–1:20 | Abra Microsoft Entra ID, execute **Sincronizar agora** e confira o histórico, horário e contagens. Mostre **Atualizar dados locais**, que apenas consulta o snapshot persistido. |
| 1:20–2:10 | Abra a RITM na PDI e mostre a aprovação nativa do catálogo. O fluxo envia somente o `sys_id` e o IdentityOps lê a evidência diretamente. |
| 2:10–3:15 | Em Solicitações de acesso, abra as simulações ServiceNow e mostre a RITM, o beneficiário, a operação e a evidência. A interface indica que o Entra ficou sem alteração. |
| 3:15–4:15 | Consulte a auditoria por `servicenow.simulated`, explique que a execução real passa por revisão IAM e mostre a RITM atualizada pelo polling com status e referência. |

Em uma gravação sem PDI, use as fixtures de `backend/tests/test_servicenow.py` para demonstrar testes de contrato, idempotência, revisão e verificação remota simulada. Identifique as respostas como simuladas e descreva separadamente os passos de instalação da PDI real.

**English.** Open the Desktop client, demonstrate a manual Entra snapshot, then show a native catalog approval in the PDI. Follow the RITM into IAM, inspect the distinctly simulated result and audit entry, and show the RITM fields updated by authenticated status polling. For a demo without a PDI, label the contract and Graph responses as fixtures.
