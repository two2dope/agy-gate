# Handoff Técnico: Evolução do `agy-gate` (Ecosystem Guardian)

**Data de Emissão:** 2026-10-29  
**Origem:** Sessão de Auditoria e Sincronização do Ecossistema Antigravity (`ece4c25f-16fa-47aa-906a-c1a73abbd058`)  
**Repositório Alvo:** `two2dope/agy-gate` (`C:\Users\Thomáz\Projetos\01_dev-systems\04_apps-games\agy-gate`)  
**Versão Atual:** `1.0.0` (Monólito Tkinter, `AntigravityGate.py`)  
**Ponto de Retomada:** Decisão arquitetural de escopo (Abordagem 1: Doctor Passivo vs Abordagem 2: Reparo Assistido)  

---

## 1. Snapshot do Ecossistema Antigravity (Blindado e Estável)

Toda a infraestrutura do Antigravity foi auditada, reparada e testada empiricamente:

1. **Paridade Multi-Ambiente (Desktop, VS Code, IDE User, CLI e Remote Control):**
   - 67 conversas reconciliadas (65 ativas no índice centralizado de sumários, 40 com títulos textuais e metadados de projetos restaurados).
   - Campo `source` estritamente normalizado para `0` (`UNSPECIFIED`) em todas as bases SQLite individuais (`<uuid>.db`), no banco agregado `conversation_summaries.db` e nos caches protobuf.
   - **Remote Control (`dev-thomaz`):** Operacional no celular e webview via WebRTC, conectado ao relay do Google sem expurgo de memória (`cached: 67, dropped: 0`).
2. **Topologia de Armazenamento NTFS Segura:**
   - As pastas de dados `brain/` e `conversations/` sob `~/.gemini/antigravity-cli/` são **Junções NTFS (`mklink /J`)** apontando diretamente para `~/.gemini/antigravity/`.
   - As raízes dos diretórios permanecem fisicamente desacopladas, eliminando o risco de contenção concorrente e erros `PermissionError: [Errno 13]`.
3. **Persistência de Repositórios e Serviços:**
   - Repositório `navigator-agy` commitado na branch `main` (`dd3204f`) com árvore limpa.
   - Daemon `nav_bridge.py` ativo na porta `49152` com `CREATE_BREAKAWAY_FROM_JOB = 0x01000000`.

---

## 2. Conhecimento Técnico Mapeado para o `agy-gate`

A investigação de baixo nível revelou regras internas essenciais que o `agy-gate` pode auditar ou gerenciar:

| Mecanismo Interno | Comportamento Descoberto | Impacto no Antigravity | Oportunidade no `agy-gate` |
|---|---|---|---|
| **Filtro Redux UI (`main.js`)** | `Fna(source)` descarta se `source != 0, 18, 20`. Se `source = 1` ou `17`, move para `externalSummaries`. | Conversas somem da barra lateral do VS Code e da tela inicial. | Auditar e alertar quando houver sessões com `source != 0`. |
| **Dualidade de Protobuf Caches** | IDE/VS Code (`--hub`) lê `agyhub_summaries_proto.pb`. Desktop lê `jetbox_summaries_proto.pb`. | Divergência de títulos e sumários entre IDE e Desktop. | Validação de consistência e sincronização espelhada dos dois arquivos. |
| **Reconciliação do Daemon (`reconcile_summaries.go`)** | O daemon cruza `conversation_summaries.db` com a pasta física `conversations/`. Sessões ausentes no disco são expurgadas da memória. | Remote Control móvel abre vazio ou rejeita sessões (`trajectory not found in any store`). | Verificação de integridade das Junções NTFS (`conversations` e `brain`). |
| **Manifestos de Projetos (`config/projects/*.json`)** | Armazena array de UUIDs de conversas (`projectConversations.conversations`). Desalinhamento com SQLite causa omissão de pastas no IDE. | Conversas não agrupam em pastas de projetos na UI ou sofrem duplicação de nós. | Auditoria de consistência bidirecional entre `config/projects/*.json` e SQLite `conversation_summaries.db`. |
| **Separação Multi-Tenant (`app_data_dir`)** | O SQLite `conversation_summaries.db` filtra por `app_data_dir = 'antigravity'` ou `'antigravity-cli'`. | Registros com `app_data_dir` divergente não são retornados nas consultas do Language Server. | Checagem de paridade do campo `app_data_dir` em ambos os bancos. |

---

## 3. Diretrizes Arquiteturais para a Implementação

Ao iniciar o trabalho no chat novo dentro da pasta `C:\Users\Thomáz\Projetos\01_dev-systems\04_apps-games\agy-gate`:

1. **Preservar o Invariante de Segurança da v1.0.0:**
   - A v1.0.0 é confiável porque **apenas lê** os bancos do Antigravity (`mode=ro`).
   - Qualquer nova funcionalidade de reparo ativo deve ser estritamente opcional, com confirmação e verificação de que os processos do Antigravity (`Antigravity IDE.exe`, `language_server.exe`, `agy.exe`) estão fechados antes de tocar no disco.
2. **Modularização contra o Inchaço do Monólito:**
   - [`AntigravityGate.py`](file:///C:/Users/Thom%C3%A1z/Projetos/01_dev-systems/04_apps-games/agy-gate/AntigravityGate.py) já possui ~5.000 linhas (206 KB).
   - Não injetar rotinas de diagnóstico ou reparo no meio do monólito. Criar um módulo limpo e desacoplado: `tools/ecosystem_doctor.py` ou `gate_doctor.py`.
3. **Compatibilidade com o Linux CI (`tests/run_all.sh`):**
   - O CI roda em Linux com `xvfb` usando bancos sintéticos.
   - Todo código específico do Windows (`ctypes`, `mklink`, `schtasks`, chaves de registro) deve ter *fallback* seguro ou mocks nos testes para não quebrar o workflow de montagem do `.exe` no GitHub Actions.
4. **Manipulação de Protobuf Sem Dependências Pesadas:**
   - Evitar compilar esquemas com `protoc`. Utilizar manipulador cirúrgico de varint/tag em Python puro para ler/escrever `source` e metadados nos arquivos `.pb`.

---

## 4. Decisão de Partida para o Novo Chat

O novo chat deve iniciar solicitando ao usuário a escolha da estratégia:

- **Opção A (Doctor Passivo - Recomendada para v1.1.0):**
  - Implementar painel/botão "Diagnóstico do Ecossistema".
  - Apenas audita: verifica junções NTFS, `source` inválido, títulos vazios, sincronismo de `.pb` e status do daemon `dev-thomaz`.
  - Zero risco de corrupção. Mantém o invariante `mode=ro`.
- **Opção B (Doctor + Reparo Assistido - v1.2.0):**
  - Inclui a Opção A e adiciona o botão "Reparar Ecossistema com 1 Clique".
  - Executa travamento de segurança de processos, recria junções `mklink /J` se quebradas, normaliza `source = 0` no SQLite e nos `.pb`.

---

## 5. Prompt de Retomada Rápida (Copie e cole no novo chat)

```text
Olá! Estou iniciando uma nova sessão de trabalho focada exclusivamente no repositório agy-gate.
Leia o arquivo de handoff em docs/HANDOFF_ECOSYSTEM_EVOLUTION.md e o STATE.md / docs/ESTADO_DO_PROJETO.md.
Estamos prontos para decidir a abordagem da evolução (Opção A: Doctor Passivo vs Opção B: Reparo Assistido) e definir o plano de implementação modular.
Como prosseguimos?
```
