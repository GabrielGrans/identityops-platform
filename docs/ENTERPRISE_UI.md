# Enterprise administration interface

The Dashboard and Analytics use the existing tenant and RBAC scopes. The updated Web and Tauri clients require the matching backend checkout. No new database migration or environment variable is required.

- **Access activity** counts one terminal record per request using the earliest matching audit timestamp. Grants and revocations require an explicit Graph membership verification and a different membership state in the approved preview. A verified operation with an unchanged state contributes to execution outcomes only. External changes, retries and queue states do not count. Month-to-date and daily windows use UTC calendar boundaries. The success rate divides verified successes by verified successes plus recorded failures and conflicts.
- **Directory** shows the last imported snapshot, with active, disabled and unknown account states kept separate. Department charts show the ten largest known departments per source and list unassigned identities separately.
- **Risks** use current open Entra governance alerts. Department attribution uses the Entra department when available, then the linked employee department. Policy findings count recorded rule violations, which may describe the same membership across multiple policies. The membership count deduplicates identity and group pairs across unexpected access, privileged access and segregation-of-duties findings. Historical trends require snapshots that are currently unavailable.
- **Audit** date filters use UTC and the end date is inclusive. Outcome filters match recorded event actions, while event drawers retain the original action identifiers and evidence.

# Interface administrativa em português

O Painel e a área de Análises respeitam o tenant e as permissões RBAC existentes. Use a mesma branch no backend e nos clientes Web ou Tauri. Esta atualização dispensa novas migrações e variáveis de ambiente.

- **Atividade de acesso** usa a primeira data auditada que corresponde ao resultado final de cada solicitação. Concessões e revogações exigem verificação explícita no Graph e mudança em relação ao vínculo observado na prévia aprovada. Uma operação verificada sem mudança entra somente no total de execuções. Alterações externas, novas tentativas e estados de fila ficam fora da contagem. Os intervalos usam o calendário UTC. A taxa de êxito divide os sucessos verificados pela soma de sucessos verificados, falhas e conflitos registrados.
- **Diretório** mostra o último snapshot importado e separa contas ativas, desabilitadas e de status desconhecido. A distribuição mostra os dez maiores departamentos por fonte e apresenta separadamente as identidades sem departamento.
- **Riscos** usa os alertas de governança Entra em aberto. Os achados usam o departamento informado no Entra ou o departamento do colaborador vinculado. O total de achados de política conta violações registradas, incluindo políticas distintas que podem apontar para o mesmo vínculo. A contagem de vínculos elimina pares repetidos de identidade e grupo entre achados de acesso inesperado, acesso privilegiado e segregação de funções. As tendências dependem de snapshots históricos indisponíveis no momento.
- **Auditoria** usa UTC com data final inclusiva. Os filtros de resultado usam as ações registradas, e os detalhes preservam os identificadores e as evidências originais.
