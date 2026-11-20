# Homologação ServiceNow PDI em modo de simulação

Use uma instância PDI, identidades fictícias e o mesmo commit do PR #8 para a API e o cliente. Mantenha `SERVICENOW_SIMULATION=true` e `ENTRA_WRITE_ENABLED=false` em todos os processos. Use um PostgreSQL de laboratório com a migração `servicenow_intake_150` aplicada. O ambiente precisa de um snapshot Entra recente e de um grupo de teste elegível na lista permitida para validar a operação simulada.

## Configurar a PDI

1. **Catálogo.** Crie **Solicitação de Acesso Corporativo**. Adicione `beneficiary` (referência a `sys_user`), `group_object_id` (escolha controlada), `operation` (`grant` ou `revoke`) e `justification` (texto). Mapeie o beneficiário por `u_identityops_entra_object_id`, com alteração restrita a administradores de identidade. Configure as propriedades `x_identityops.catalog_item_sys_id` e `x_identityops.entra_tenant_id`.
2. **Scripted REST API.** Registre a API `approval` versão `v1` com recurso `GET /ritm/{sys_id}`. Use o [script de evidência](../integrations/servicenow/approval-resource.js). Restringa o recurso ao papel `x_identityops.approval_reader` de uma conta web-service-only. Confira o namespace real e configure `SERVICENOW_API_NAMESPACE` no IdentityOps. Confirme a relação `sysapproval_approver.sysapproval` com a RITM e o formato JSON, conforme o [contrato](SERVICENOW.md#rest-contract).
3. **REST Message.** Crie **IdentityOps IAM** com `submit` (POST) e `status` (GET). No proxy padrão, use o caminho `/api/integrations/servicenow/access-requests`. Acrescente `/${sys_id}` no método GET. Configure o bearer no cofre de credenciais da PDI e use HTTPS autorizado. Teste a conectividade no sentido inverso, do IdentityOps ao recurso de aprovação, com a credencial de leitura separada.
4. **Flow Designer.** Use um gatilho de catálogo e **Ask for Approval** vinculado à RITM, com aprovador distinto do solicitante e do beneficiário. Use o [script da ação](../integrations/servicenow/flow-action.js) no ramo aprovado e passe somente o `sys_id`. Acompanhe o resultado por GET e grave `u_identityops_status` e `u_identityops_reference` com **Update Record**. Encerre o polling ao receber um estado terminal. Configure retries limitados para indisponibilidade, incluindo exceções de transporte, e reenvie com o mesmo `sys_id`.

## Evidências de aceite

| Cenário | Resultado esperado |
| --- | --- |
| RITM aprovada, beneficiário e grupo elegíveis | POST 201, GET com `status=simulated`, `simulated=true` e `change_id=null`. A RITM recebe status e referência. A auditoria registra `servicenow.simulated`. |
| Reenvio da mesma RITM, inclusive concorrente | A primeira entrega retorna 201 e as demais 200 com a mesma referência. Há um registro no ledger e um evento de simulação. |
| Bearer inválido, aprovação ausente ou grupo protegido | Rejeição por autenticação ou validação. A RITM recebe o status de erro e a referência existente fica preservada. |
| Serviço de evidência temporariamente indisponível | O Flow registra a falha, faz retry limitado com a mesma referência e encaminha ao operador se esgotar as tentativas. |
| Modo de simulação | A fila do worker não recebe uma mudança. A associação Microsoft Entra permanece igual. |

## Pendências antes de considerar execução real

- O recurso de evidência lê os valores **atuais** das variáveis da RITM e do mapeamento em `sys_user`. A aprovação nativa, por si só, não congela esses valores. A PDI deve impedir alterações desde o início da aprovação ou invalidar a aprovação e exigir uma nova decisão sobre os valores atualizados. Valide a proteção no servidor em todos os canais permitidos, incluindo API e automações, e comprove que o Object ID efetivamente aprovado corresponde ao entregue. O IdentityOps compara a evidência recebida com a evidência reconsultada pelo worker, o que cobre mudanças posteriores à recepção.
- A autenticação usa segredo compartilhado para o intake e uma credencial separada para ler a evidência. Restrinja TLS e o tráfego de entrada, proteja os segredos, aplique rate limit e retenha os resultados HTTP de entregas rejeitadas no ServiceNow. O ledger e a auditoria do IdentityOps registram as entregas aceitas e o processamento.
- Valide o catálogo, ACLs, recurso de evidência, Flow e retorno à RITM em uma PDI real. Registre a evidência de aceite e leve o resultado ao PR #8 para revisão. A homologação descrita aqui é somente em simulação.
