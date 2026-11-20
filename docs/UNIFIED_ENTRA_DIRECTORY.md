# Unified Entra directory / Diretório integrado do Entra

**Colaboradores** e **Grupos de acesso** consultam o snapshot existente automaticamente para operadores com `entra:read`. A opção **IdentityOps local** continua usando os catálogos e controles de RBAC locais. Sincronização e provisionamento remoto não criam contas de login nem concedem RBAC local.

## Atualização

A migração `unified_entra_directory` adiciona departamento, origem da sincronização e metadados de grupo ao snapshot. Também preserva os IDs imutáveis e os códigos de erro na fila de provisionamento existente. Solicitações feitas diretamente do diretório Entra podem ter `employee_id` nulo. Atualize o frontend, API e worker juntos:

```powershell
python -m backend.app.scripts.migrate
python -m backend.app.scripts.seed_permissions
```

O próximo ciclo do worker reconstrói o checkpoint da projeção. Até lá, grupos sem metadados completos aparecem como não suportados. O perfil indica contas sincronizadas do ambiente local e contas cuja origem de atributos não foi confirmada. A edição de perfil fica indisponível.

## Operações e permissões

- **Leitura** — `User.Read.All` e `Group.Read.All`. As rotas de leitura paginadas ficam em `/entra/directory/users` e `/entra/directory/groups`, com detalhes e vínculos por ID de objeto.
- **Vínculos de grupo** — `GroupMember.ReadWrite.All` somente em implantação autorizada. Use `ENTRA_WRITE_ENABLED` (padrão `false`), `ENTRA_WRITE_GROUP_IDS` e `ENTRA_PROTECTED_GROUP_IDS`. A solicitação usa `entra:request_change` e a decisão usa `entra:approve_change`. As rotas existentes em `/entra/automation` aceitam o ID do usuário Entra ou o ID do colaborador local.
- **Perfis** — nenhuma permissão de escrita em usuário é necessária. O indicador de origem é pelo objeto do diretório, e a origem por atributo ainda precisa de um modelo específico de autorização. Escritas de perfil, grupos Microsoft 365 e grupos de segurança dinâmicos ou sincronizados estão fora das operações suportadas.

A aprovação exige outra pessoa. O worker revalida a configuração e os metadados ao vivo, verifica a associação no Graph e só então registra sucesso. Um sucesso antecipa a próxima sincronização quando ela não está em backoff. As telas abertas consultam novamente o snapshot a cada 10 segundos. Se o Graph estiver indisponível, as telas continuam mostrando o último snapshot concluído.

Em **Governança de funções do Entra**, use `entra_department` para comparar o departamento sincronizado. `department_id` e a situação do colaborador referem-se ao vínculo local. Achados de acesso e exceções expiradas oferecem links para os objetos relacionados.

## Homologação no Windows

Com PostgreSQL configurado e a API e o worker em terminais separados, execute:

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
python -m backend.app.scripts.entra_worker
npm --prefix frontend ci
npm --prefix frontend run desktop:dev
```

Acesse Colaboradores e Grupos de acesso. Confira a origem, a pesquisa por departamento e os vínculos. Em tenant de teste autorizado, solicite uma alteração em um grupo permitido, aprove com outra conta em **Solicitações de acesso** e confira a verificação e a atualização do snapshot. [Configuração do worker e consentimento](ENTRA_AUTOMATION.md)
