# Auditoria Full Spectrum: AntigravityGate 1.0.0 × sessão de recuperação de 27/10

**Data**: 2026-10-27
**Modo**: Saúde do repositório, dirigida. A ferramenta foi confrontada com tentativas, erros, acertos e aprendizados da sessão de recuperação do Antigravity (`handoffs/2026-10-27-antigravity-sync.md`, no repositório `zuvuya`)
**Fonte**: `two2dope/agy-gate`, `main` @ `e1ce3f1` (v1.0.0)
**Lentes executadas**: 7/10
**Lentes puladas**:
- Design Engineer: nenhum aprendizado da sessão toca tema, ícones ou paletas; a auditoria v0.9.0 cobriu e as correções entraram na 1.0.
- Frontend Engineer: sem React/TS/CSS. O único ponto da camada Tk relevante aqui (busca FTS na thread da interface) está na lente Performance.
- Accessibility Engineer: nenhum achado da sessão; teclado, foco e dicas foram tratados na 1.0 (etapa 2b).

**Método e limites**
- Li `README.md`, `CHANGELOG.md`, `docs/ESTADO_DO_PROJETO.md`, as duas auditorias anteriores, o workflow, `packaging/` e `tests/test_sources.py`, `tests/fake_agy.py`. No `AntigravityGate.py`, li por inteiro as camadas de dados, exportação, estado, Auto-Run e varredura (linhas 1 a 1.512) e os fluxos de busca, exportação, Auto-Run, fechamento, autoteste e `main` (3.002 a 3.046 e 3.477 a 4.074).
- **[Verificado]** = rodei o código do app. Este ambiente não tem `tkinter`, então importei o módulo com um `tkinter` simulado e chamei só funções puras (`discover_sources`, `load_projects`, `redact`, `build_agy_args`) sobre uma árvore `~/.gemini` sintética, com symlinks no lugar das junctions. O script foi descartável e ficou fora do repositório.
- **[Verificado no banco]** = dado observado no computador do usuário durante a sessão de 27/10 (consultas somente leitura e telas).
- **[Inferência]** = conclusão apoiada em evidência, não testada diretamente. **[Não verificado]** = hipótese.
- Não rodei a suíte `tests/run_all.sh` (precisa de Tk). Não rodei o app no Windows.
- Os sub-skills `audit-as-*` são calibrados para Orbit (Tauri/React/Rust). Como na auditoria anterior deste repositório, apliquei o critério de cada lente diretamente ao Python.
- Achados abertos da auditoria v0.9.0 conferidos no código atual: R6 (FTS na thread da interface), R9 (`taskkill /T`), R15 (`--help`) e R16 (monólito) **seguem abertos**.

---

## Veredito Mestre: APPROVE WITH CHANGES

A ferramenta e a sessão chegaram, por caminhos independentes, às mesmas regras sobre os dados: só ler, `project_id` é a fonte da verdade, ignorar `projectConversations`, converter de UTC, extrair em vez de interpretar. Essa convergência valida o desenho do Gate.

Dois defeitos, porém, aparecem exatamente no ambiente real que a sessão descobriu:
1. **O Auto-Run abre a retomada fora do projeto da sessão original.** A pasta `handoffs` entra como workspace e o processo herda a pasta de onde o `.exe` foi aberto. Resultado: as retomadas caem em "CLI Project" e o IDE mostra "This conversation is in a different workspace".
2. **As junctions `antigravity-cli` e `antigravity-ide` aparecem como "Backup".** São os dados vivos, rotulados como cópia de segurança. É o mesmo tipo de defeito-raiz da primeira auditoria: a interface afirma um estado falso.

Nenhum dos dois perde dados, e os dois têm correção pequena e testável.

---

## Confronto com a sessão (respostas diretas)

### O que converge com a sessão

| Aprendizado da sessão | No AntigravityGate | Onde |
|---|---|---|
| Não escrever nos dados do Antigravity | Abre tudo com `mode=ro`; estado próprio em `gate_state.db` | `:148-151`, `:45` |
| `project_id` do banco é a fonte da ligação conversa↔projeto | Agrupa por `project_id`; o JSON de projeto só dá o nome | `:1365`, `:1389` |
| `projectConversations` (injetada pelo Gemini) é irrelevante | Nunca lê essa chave | `load_projects`, `:1290-1309` |
| Horários do banco estão em UTC | Converte para o horário local | `fmt_time`, `:167-188` |
| Handoff escrito por modelo mente (`local_mode: true` nunca existiu) | O dossiê é extração local: "nenhum modelo foi usado… nada aqui é interpretação" | `:769-771` |
| Bancos corrompidos ficam em `corrupt_quarantine` | Quarentena vira fonte separada, com aviso e sem derrubar o app | `discover_sources`, `test_sources.py` |
| Toda chamada do `agy` cria uma conversa | Detecta e arquiva no próprio estado as sessões vazias das tentativas com erro | `:1227-1231`, `:1252-1257` |
| Ler sempre com cópia ou somente leitura (WAL, motor rodando) | `mode=ro` com `timeout` | `:148-151` |

### O que conflita com a sessão

| Fato da sessão | O que o Gate faz | Efeito |
|---|---|---|
| `antigravity-cli` e `antigravity-ide` são **junctions** para `antigravity` | Lista as duas como "Backup/outros", junto com as quarentenas delas **[Verificado]** | Os dados vivos aparecem 3 vezes, 2 delas como "backup". Ver C2 |
| Os JSONs de projeto podem ser regravados com BOM (PowerShell 5.1 `Set-Content -Encoding UTF8`) | `open(..., encoding='utf-8')` + `json.load` falha com BOM **[Verificado]** | Projeto "ilegível": as conversas dele caem em "Outside of Project" ou num projeto errado |
| A retomada precisa nascer no projeto certo para aparecer bem no IDE e no remoto | Passa `--add-dir <handoffs>` primeiro e não define `cwd` | As sessões "/plan Você está retomando…" aparecem com a pasta "handoffs" na busca do VS Code e em "CLI Project (12)" no remoto **[Verificado no banco]**. Ver C1 |
| A chave do Stitch (`AQ.…`) vazou numa saída de diagnóstico | A máscara pega `AQ.…` em formato chave=valor, mas **não** solta no texto **[Verificado]** | Uma chave colada em texto corrido passa para o dossiê e, portanto, para o prompt do modelo |
| "O app só lê" | O Auto-Run faz o `agy` **gravar** sessões novas no banco do Antigravity | A promessa do README (`:5`) é verdadeira para o acesso direto, mas não para o efeito do Auto-Run |

### O que foge do escopo do Gate

- **Consertar o ambiente**: reescrever `config/projects`, criar ou desfazer junctions, registrar o daemon de remote control, mexer em `antigravity_state.pbtxt`. Contradiz a decisão "só lê" e a lição nº 2 da sessão: quem escreve na config arrisca quebrar a listagem inteira.
- **Consertar a barra lateral do VS Code** (lista só as conversas carregadas, `restored 0`). É defeito do produto.
- **Apagar sessões no Antigravity**, inclusive as de teste do próprio Auto-Run. O Gate não deve escrever no banco.
- **Retomar a conversa original** (`agy --conversation`). O ESTADO já registra que isso altera a original; a opção B (sessão nova) está correta.

**O que cabe:** **diagnosticar** e **sugerir** comandos que o usuário copia e roda por conta própria (ver "Vira recurso").

### O que pode virar recurso ou melhoria

| Ideia | Por quê (da sessão) | Custo | Entra no lugar de quê? |
|---|---|---|---|
| **Corrigir o local da retomada** (C1): `cwd` no projeto, sem `--add-dir` de `handoffs`, testar `--project` | Retomadas no projeto certo, sem o aviso "different workspace" | Pequeno | Prioridade sobre todo o backlog |
| **Fontes sem duplicata** (C2): chave por `realpath`, junction rotulada "link para Ativas" ou oculta | Fim de "backup" falso | Pequeno | Prioridade |
| **Diagnóstico do ambiente** (somente leitura), na janela Sobre ou num botão próprio | A sessão precisou de cerca de 25 passos manuais para ver isto | Médio | Item 8 do backlog (divisor de altura) |
| **"Copiar título para buscar"** no menu e no painel | No VS Code, a 🔍 é a única via confiável para abrir conversa antiga | Mínimo | Nada (cabe na 1.0.x) |
| **Aviso pós-Auto-Run**: "a sessão nova não aparece na barra lateral do VS Code; use a 🔍 ou o acesso remoto" | Evita a conclusão "não funcionou" | Mínimo | Nada |
| **Lista "criadas pelo Auto-Run"** (UUID, data, projeto) para limpeza manual no Antigravity | Hoje somam cerca de 12 em "CLI Project" no remoto | Pequeno | Item 7 do backlog (limpeza de dossiês) |
| **Notas por sessão** (em `gate_state`), anexadas ao dossiê | O dossiê extrai fatos; a causa verificada (ex.: "config/projects alterado pelo Gemini") só existe em nota humana | Médio | Item 4 do backlog (`agy models`) |
| **Títulos iguais aos do Antigravity**: conferir se o título gerado ("System Test Three", "Turn On Remote Control") mora em `title` ou em `raw_summary` **[Não verificado]** | Facilita achar no remoto e na busca do IDE a conversa vista no Gate | Pequeno (investigação) | Item 5 do backlog (modelo vazio no dossiê) |

### Possíveis bugs

| # | Bug | Evidência | Gravidade |
|---|---|---|---|
| B1 | Retomada nasce fora do projeto e do workspace da sessão original | Código `:1022-1023`, `:1125-1126` + banco do usuário | Alta (C1) |
| B2 | Junctions listadas como "Backup/outros" (dados vivos 3×, quarentena 3×) | **[Verificado]** com symlink: 6 fontes, das quais 4 são a mesma pasta | Alta (C2) |
| B3 | Projeto com BOM vira "ilegível" | **[Verificado]**: `JSONDecodeError: Unexpected UTF-8 BOM` | Média |
| B4 | Projeto por URI: a primeira substring vence. `…/navigator-agy` captura `…/navigator-agy-v2`, e uma pasta raiz cadastrada como projeto captura tudo abaixo dela | **[Verificado]** com dados sintéticos | Baixa (só quando `project_id` não resolve) |
| B5 | Re-rodar uma sessão criada pelo Auto-Run repassa `handoffs` e a pasta do `.exe` como `--add-dir` | `workspace_dirs` aceita qualquer pasta existente, `:982-989` | Média (agrava B1) |
| B6 | Chave `AQ.…` solta no texto não é mascarada | **[Verificado]** | Média |

### Pontos de atenção

- **Três motores na mesma pasta.** Daemon (`dev-thomaz`), hub do VS Code e o `agy --print` do Auto-Run escrevem no mesmo banco. O SQLite aguenta, mas a regra prática da sessão vale: uma conversa por vez, num lugar só. Não rodar Auto-Run sobre uma sessão aberta no IDE.
- **Dois `agy.exe`.** A extensão recria `~/.gemini/bin/agy.exe`; o Gate usa o do PATH (`AppData\Local\agy\bin`). Hoje são idênticos (1.4.7). Se a extensão atualizar a cópia dela, o Gate continua no outro. A janela Sobre deveria mostrar os dois.
- **O protobuf é contrato não documentado.** Os números de campo valem para o `agy` 1.4.7 e a extensão 1.9.0. Toda atualização merece rodar `tools/inspect_*.py` numa sessão real antes de confiar no dossiê.
- **Exportação "Diálogo completo" não mascara.** É assim por projeto, e o cabeçalho avisa. Mas a sessão mostrou como um segredo entra numa conversa: uma ferramenta lê `mcp_config.json`. Vale a pena oferecer a opção de mascarar, ligada por padrão.

### Dicas

- Depois de corrigir C1, rodar **uma** retomada real e conferir no remoto (`dev-thomaz`) se ela aparece dentro do projeto de origem. Esse é o critério de pronto.
- Retestar "o editor do Antigravity abre sozinho a cada chamada do `agy`" agora que o daemon está registrado. **[Não verificado]**: com um hub já rodando, o `agy --print` pode não abrir o editor.
- Para checar C2 no Windows em 1 minuto: abra o seletor de fonte do Gate e conte as entradas "antigravity-cli/…" e "antigravity-ide/…".

### As duas frentes: onde uma completa a outra

| | AntigravityGate | Sessão de 27/10 |
|---|---|---|
| Estratégia | **Contornar.** Extrai do disco, gera dossiê e abre uma sessão **nova** | **Reparar.** Conserta a config e o daemon para as conversas **originais** voltarem às telas nativas |
| Força | Inventário confiável de **todas** as sessões, independente da tela do IDE; busca por conteúdo; dossiê sem interpretação | Causa real conhecida; acesso nativo restaurado (busca 🔍 e remoto); mapa do ambiente |
| Ponto cego | Não conhecia as junctions, o BOM e o efeito do `cwd` sobre o projeto | Não tem inventário nem extração; depende de telas com defeito (barra lateral) |

**Onde se completam:**
1. **Inventário + acesso.** A barra lateral do VS Code continua mostrando só o que está aberto. O Gate é o índice completo: escolhe a conversa, e a 🔍 do IDE ou o remoto a abre. O recurso "Copiar título para buscar" fecha esse circuito.
2. **Retomada que aparece.** Com o ambiente reparado, o remoto lista tudo por projeto. Com C1 corrigido, a retomada do Gate passa a cair no projeto certo e aparece ao lado da original.
3. **Dossiê + handoff.** O dossiê do Gate registra fatos extraídos. O handoff da sessão registra causa, hipóteses descartadas e rollback, conhecimento que não se extrai. As "notas por sessão" juntariam os dois no mesmo arquivo.
4. **Regras dos dados.** A sessão confirmou, com testes no ambiente real, três escolhas que o Gate fez sem essa prova: ignorar `projectConversations`, usar `project_id` e converter UTC. Em troca, entrega ao Gate três fatos que ele não tinha: junctions, BOM e o efeito do `cwd`.

### O que ainda pode ser revisado

- ESTADO, Snapshot: "Faltando: restaurar as sessões no Antigravity" foi feito em 27/10. O item 2 do backlog (uso real do fluxo completo) está desbloqueado.
- README: explicar que o Auto-Run cria sessões no banco do Antigravity por meio do `agy`.
- Achados abertos da v0.9.0: R6 (FTS na thread da interface), R9 (encerrar a árvore de processos), R15 (`--help`), R16 (monólito).
- Origem do título exibido no remoto (coluna `title` ou `raw_summary`).
- `packaging/build_exe.bat` instala o PyInstaller sem versão fixa (o CI fixa 6.22.3).

---

## Veredito por Lente

| # | Lente | Veredito | Críticos | Recomendações |
|---|-------|----------|----------|---------------|
| 1 | Design Engineer | Pulada | – | – |
| 2 | UX Engineer | APPROVE WITH CHANGES | 1 (C2) | 4 |
| 3 | Frontend Engineer | Pulada | – | – |
| 4 | Backend Engineer (Python/SQLite/subprocess) | NEEDS REWORK (no Auto-Run) | 2 (C1, C2) | 5 |
| 5 | Structural Engineer | APPROVE WITH CHANGES | 0 | 3 |
| 6 | Repo Maintainer | APPROVE WITH CHANGES | 0 | 5 |
| 7 | Production Readiness | APPROVE WITH CHANGES | 1 (C1) | 4 |
| 8 | DX Engineer | APPROVE WITH CHANGES | 0 | 4 |
| 9 | Performance Engineer | APPROVE | 0 | 2 |
| 10 | Accessibility Engineer | Pulada | – | – |

## Todos os Problemas Críticos (Must Fix)

| # | Problema | Lente(s) | Arquivo(s) | Impacto | Correção |
|---|----------|----------|------------|---------|----------|
| C1 | O Auto-Run abre a retomada fora do projeto e do workspace da sessão original. `build_agy_args` põe `--add-dir <HANDOFF_DIR>` antes das pastas do projeto, e `_run_agy` chama `Popen` sem `cwd`, herdando a pasta de onde o `.exe` foi aberto. **[Verificado no banco]**: sessões "/plan Você está retomando…" com `workspace_uris` = `[AntigravityGate\handoffs, Downloads\AntigravityGate-windows, <projeto>]` e `project_id` = `default-cli-project`; a busca do VS Code as mostra na pasta "handoffs"; o remoto, em "CLI Project (12)". **[Inferência forte]**: o `agy` registra o `cwd` e cada `--add-dir` como workspace | Backend, Prod, UX | `AntigravityGate.py:1022-1023`, `:1125-1126`, `:982-989`; `tests/test_autorun.py:62`, `:78` | A retomada não aparece ao lado da original; o IDE avisa "different workspace" ao abri-la; "CLI Project" acumula sessões; reaprovar uma retomada piora o quadro (B5) | (1) `Popen(..., cwd=<primeira pasta existente do workspace original>)`, ou `HANDOFF_DIR` se não houver nenhuma. (2) Tirar `--add-dir` do `HANDOFF_DIR`: o dossiê já vai no prompt e o `read_file` é negado no modo sem janela. (3) Filtrar `LOG_DIR` e `HANDOFF_DIR` em `workspace_dirs`. (4) Testar `--project <project_id>` da sessão original **[Não verificado]**. (5) Ajustar os dois asserts de `test_autorun.py` e acrescentar um assert de `cwd` no `fake_agy` (gravar `os.getcwd()` no log) |
| C2 | Junctions (e symlinks) da pasta mestra viram fontes "Backup/outros". `discover_sources` deduplica por `normcase(abspath())`, que não resolve links; `DirEntry.is_dir()` segue a junction. **[Verificado]** com symlink: 6 fontes, das quais 4 são a mesma pasta (`antigravity-cli/conversations`, `antigravity-ide/conversations` e as duas quarentenas) | UX, Backend | `AntigravityGate.py:1275-1281`; `tests/test_sources.py` | Num cenário de recuperação, o usuário pode tratar dados vivos como cópia de segurança (comparar, exportar ou "restaurar a partir" dela). É o mesmo defeito-raiz da auditoria original: a interface afirma um estado falso | Chave de deduplicação com `os.path.normcase(os.path.realpath(...))` (no Windows, `realpath` resolve junctions desde o Python 3.8). Se o alvo for a pasta ativa, pular ou rotular "link para Ativas". Teste com `os.symlink` em `test_sources.py` |

## Preocupações Transversais

| Preocupação | Sinalizada por | Causa raiz | Correção unificada |
|-------------|----------------|------------|--------------------|
| O ambiente real difere do ambiente de teste | Backend, Prod, Repo | Os testes montam um `~/.gemini` sintético e limpo: sem junctions, sem BOM, sem `cwd` relevante, sem motores rodando | Fixture "ambiente sujo" em `tests/`: links para a pasta mestra, JSON com BOM, projeto com `projectConversations`, pasta pai e filha com prefixo comum. Assert de `cwd` no `fake_agy` |
| Fronteira de escrita mal declarada | Structural, Prod, UX | "Só lê" vale para o acesso direto, mas o Auto-Run grava sessões no Antigravity por meio do `agy` | README e confirmação do Auto-Run dizendo isso; lista "criadas pelo Auto-Run"; nunca escrever na config |
| Vias de acesso que funcionam hoje | UX, DX | A barra lateral do VS Code lista só o que está aberto; a 🔍 e o remoto listam tudo | "Copiar título para buscar" + aviso pós-Auto-Run + uma linha no README |
| Achados antigos ainda abertos | Perf, Prod, DX | R6, R9 e R15 da v0.9.0 ficaram para depois da 1.0 | Entram como 1.0.x, cada um com teste |

## Todas as Recomendações

| # | Recomendação | Lente | Arquivo(s) | Correção |
|---|---------------|------|---------|-----|
| R1 | Projeto com BOM fica ilegível **[Verificado]** | Backend | `:1296` | `encoding='utf-8-sig'`; teste com BOM |
| R2 | Projeto por URI pega a primeira substring **[Verificado]** | Backend | `:1392-1396` | Maior prefixo vence, com fronteira de pasta (`k == w` ou `w.startswith(k + "/")`) |
| R3 | Chave `AQ.…` solta não é mascarada **[Verificado]**; o formato oficial do Google não foi conferido | Backend, Prod | `:384-399` | Padrão `\bAQ\.[A-Za-z0-9_\-]{30,}` + teste com chave sintética |
| R4 | O Diálogo completo não mascara segredos | Prod, UX | `:655-701` | Opção "Mascarar segredos" na exportação, ligada por padrão; o cabeçalho diz qual escolha foi feita |
| R5 | O README diz "só lê" sem ressalva | Structural, Repo | `README.md:5` | "O app só lê os bancos; o Auto-Run pede ao `agy` para criar sessões novas" |
| R6 | ESTADO desatualizado depois de 27/10 | Repo | `docs/ESTADO_DO_PROJETO.md` (Snapshot) | Marcar a restauração como feita, citar o handoff, desbloquear o item 2 do backlog |
| R7 | Diagnóstico do ambiente, somente leitura | DX, Prod | novo | Junctions e seus alvos; contagem summaries × arquivos; projetos ilegíveis, com BOM ou com `projectConversations`; quarentena; os dois `agy.exe` (caminho, tamanho, iguais?). Cada problema traz o comando sugerido para **copiar**; o app nunca executa a correção |
| R8 | "Copiar título para buscar" | UX | menu `:3545-3555`, painel | Copia as 3–4 primeiras palavras do título para colar na 🔍 do Antigravity |
| R9 | Aviso pós-Auto-Run sobre a barra lateral do VS Code | UX, DX | `:3996-4000` | Uma linha na notificação de sucesso |
| R10 | Lista "criadas pelo Auto-Run" | UX, Structural | `gate_state.handoffs` | Filtro ou selo com os `new_cid` e as sessões arquivadas como lixo, para limpeza manual no Antigravity |
| R11 | Busca FTS na thread da interface (R6 da v0.9.0) | Perf | `:3494-3515` | Worker + `self.queue`, como em `load_data` |
| R12 | Cancelamento não encerra a árvore de processos (R9 da v0.9.0) | Prod | `:1137-1146` | `CREATE_NEW_PROCESS_GROUP` + `taskkill /T /F /PID` |
| R13 | Sem `--help` (R15 da v0.9.0) | DX | `:4053-4060` | `--help` com variáveis (`ANTIGRAVITY_HOME`, `AGY_EXE`, `AGY_ICONS`, `AGY_ROT_TOKENS`) e opções |
| R14 | `build_exe.bat` instala o PyInstaller sem versão fixa | Repo | `packaging/build_exe.bat:11` | `pyinstaller==6.22.3`, igual ao CI |
| R15 | Notas por sessão no dossiê | UX, Structural | `StateStore`, `build_dossier` | Tabela `notes(cid, text, at)`; seção "Notas do usuário" no dossiê, também mascarada |
| R16 | Origem do título exibido pelo Antigravity | UX | `:1400-1401` | Investigar com `tools/inspect_schema.py` se o título gerado está em `title` ou em `raw_summary` **[Não verificado]** |
| R17 | Monólito de 4.074 linhas (R16 da v0.9.0) | Structural | `AntigravityGate.py` | Continua adiado: separar `core`, `autorun` e `ui` só quando a 1.0.x estabilizar |

---

# Relatórios por lente

---

## 1. Design Engineer

**Pulada.** Nenhum aprendizado da sessão de 27/10 toca tema, ícones, paleta ou contraste. A auditoria v0.9.0 cobriu essa lente, e a 1.0 incorporou as correções (WCAG AA testado em `test_theme`).

---

## 2. UX Engineer

**Veredito**: APPROVE WITH CHANGES

### Mapa da jornada do usuário (recuperar e retomar)

| Etapa | O que o usuário quer | O que acontece hoje | Atrito |
|---|---|---|---|
| 1. Abrir o Gate | Ver todas as sessões | Tabela completa por projeto, inclusive as que o VS Code esconde | Nenhum: é o ponto forte |
| 2. Escolher a fonte | Saber o que é vivo e o que é cópia | "Ativas" + "Backup/outros: antigravity-cli/conversations" + "…antigravity-ide/…" | **Alto**: duas "cópias" são os dados vivos (C2) |
| 3. Achar uma conversa antiga | Buscar por assunto | Busca no título, nos metadados e no conteúdo (FTS) | Baixo. O título pode diferir do que o Antigravity mostra (R16) |
| 4. Abrir no Antigravity | Continuar a conversa original | Nenhum caminho direto; o usuário precisa redigitar o título na 🔍 do IDE | Médio (R8) |
| 5. Retomar (Auto-Run) | Sessão nova no mesmo projeto | Sessão nova em "CLI Project", com o workspace `handoffs` | **Alto** (C1) |
| 6. Ver a retomada | Encontrá-la no IDE | Não aparece na barra lateral do VS Code (limitação do produto) | Médio: parece que falhou (R9) |
| 7. Limpar testes | Tirar as sessões de teste da frente | O Gate arquiva no próprio estado; no Antigravity elas continuam lá | Baixo (R10) |

### Problemas críticos

| # | Problema | Onde | Correção |
|---|---|---|---|
| C2 | Dados vivos rotulados como "Backup/outros" | `:1275-1281` | Deduplicar por `realpath`; rotular "link para Ativas" |

### Recomendações

| # | Recomendação | Onde |
|---|---|---|
| R8 | "Copiar título para buscar" no menu e no painel | `:3545-3555` |
| R9 | Aviso pós-Auto-Run: usar a 🔍 ou o remoto para ver a sessão nova | `:3996-4000` |
| R10 | Lista ou selo "criadas pelo Auto-Run" | estado `handoffs` |
| R16 | Alinhar o título exibido ao do Antigravity | `:1400-1401` |

### Verificação de consistência de interação

- A busca do Gate e a 🔍 do Antigravity procuram em lugares parecidos (títulos e conteúdo), mas mostram títulos possivelmente diferentes. Alinhar (R16) ou exibir os dois.
- "Arquivada" no Gate não arquiva no Antigravity. O rótulo está correto, mas a confirmação do Auto-Run poderia dizer "arquivada no AntigravityGate".
- Os estados de fonte ("Ativas" e "Backup") precisam corresponder à realidade do disco. Hoje não correspondem com junctions (C2).

### Detalhes do veredito

- **Clareza de estado:** boa na tabela; falha no seletor de fonte (C2).
- **Fluxo de recuperação:** o Gate cobre inventário e extração; falta a ponte até o Antigravity (R8, R9).
- **Retomada:** o objetivo (continuar no mesmo projeto) não se cumpre por causa de C1.

---

## 3. Frontend Engineer

**Pulada.** Sem React, TypeScript ou CSS. O ponto da camada Tk relevante para este confronto (FTS bloqueando a interface) está na lente Performance.

---

## 4. Backend Engineer (Python / SQLite / subprocess)

**Veredito**: NEEDS REWORK no Auto-Run (C1); o restante está sólido

### Análise dos caminhos de erro

| Caminho | Comportamento | Situação |
|---|---|---|
| Banco de sessão corrompido | `session_metrics` em `try`; aviso + linha com zeros | OK (coincide com a quarentena da sessão) |
| `conversation_summaries.db` ilegível | Aviso; a fonte ativa segue só com os arquivos | OK |
| JSON de projeto com BOM | `JSONDecodeError` → "Projeto ilegível" **[Verificado]** | Falha evitável (R1) |
| JSON de projeto com `projectConversations` | Ignorado | OK (converge com a sessão) |
| Pasta de projeto com prefixo comum | Primeira substring vence **[Verificado]** | Atribuição errada (R2) |
| Junction na `~/.gemini` | Tratada como pasta comum → fonte duplicada **[Verificado com symlink]** | C2 |
| `agy` sem `cwd` definido | Herda a pasta do `.exe` → vira workspace da sessão nova **[Verificado no banco; mecanismo: inferência]** | C1 |
| `agy` cria sessão e falha | Compara a pasta antes e depois; arquiva só se a primeira fala é o prompt do Auto-Run (o prefixo "/plan " não atrapalha: usa `in`) | OK |
| Segredo solto no texto (`AQ.…`) | Não mascarado **[Verificado]** | R3 |

### Auditoria do ciclo de vida de recursos

| Recurso | Abre | Fecha | Situação |
|---|---|---|---|
| Conexões SQLite das sessões | `open_ro` (`closing`) | sempre | OK |
| `gate_state.db` | `closing` por operação; memória com trava | sempre | OK |
| Processo `agy` | `Popen` | `communicate` / `terminate` / `kill` | Árvore de processos não é encerrada (R12) |
| Arquivos exportados | `.part` → `os.replace` | sempre | OK |
| `METRICS_CACHE` | cresce por `(caminho, mtime, tamanho)` | nunca | Aceitável: dezenas a centenas de entradas |

### Problemas críticos

| # | Problema | Onde | Correção |
|---|---|---|---|
| C1 | Retomada fora do projeto (`--add-dir handoffs` primeiro; `Popen` sem `cwd`; `workspace_dirs` aceita `handoffs` e a pasta do `.exe` de sessões anteriores) | `:1022-1023`, `:1125-1126`, `:982-989` | `cwd` no projeto; sem `--add-dir` de `handoffs`; filtro em `workspace_dirs`; testar `--project`; ajustar os testes |
| C2 | Deduplicação de fontes sem resolver links | `:1275-1281` | `realpath` |

### Recomendações

R1 (BOM), R2 (maior prefixo com fronteira), R3 (`AQ.`), R4 (máscara opcional no Diálogo completo), R12 (árvore de processos).

### Detalhes do veredito

- **Leitura:** correta e defensiva; converge com a sessão em todas as regras de dados.
- **Escrita indireta (Auto-Run):** o detalhe de `cwd` e `--add-dir` derrota o objetivo da retomada.
- **Segredos:** boa cobertura em contexto chave=valor; lacuna no texto solto.

---

## 5. Structural Engineer

**Veredito**: APPROVE WITH CHANGES

### Mapa de dependências (fronteiras externas)

| Dependência | Tipo | Direção | Estabilidade |
|---|---|---|---|
| `~/.gemini/antigravity/conversation_summaries.db` | SQLite (WAL), esquema do Antigravity | leitura | Média: colunas vistas na 1.4.7 |
| `~/.gemini/antigravity/conversations/*.db` | SQLite + protobuf sem esquema publicado | leitura | **Baixa**: números de campo inferidos |
| `~/.gemini/config/projects/*.json` | JSON | leitura | Média: sofre edições de terceiros (Gemini, BOM) |
| `agy` (CLI) | processo | **gera escrita** no Antigravity | Média: contrato registrado no ESTADO |
| `%LOCALAPPDATA%\AntigravityGate` | estado, log, exportações | leitura e escrita própria | Alta |
| Junctions `antigravity-cli` / `antigravity-ide` | sistema de arquivos | leitura | Alta, mas **não modelada** no Gate |

### Análise de cruzamento de fronteiras

- **Leitura direta:** só leitura, como prometido.
- **Auto-Run:** cruza a fronteira de escrita por meio do `agy`, e o efeito colateral (sessão nova, workspace, projeto) é decidido pelos argumentos e pelo `cwd`. É a fronteira mais sensível e a menos testada contra o ambiente real (C1).
- **Configuração do Antigravity:** o Gate só lê. Correto, e deve continuar assim: diagnosticar sim, corrigir não.

### Problemas críticos

Nenhum novo nesta lente. C1 é a manifestação estrutural do cruzamento de fronteira pelo Auto-Run.

### Recomendações

| # | Recomendação |
|---|---|
| R5 | Declarar a fronteira no README: leitura direta; escrita apenas via `agy`, em sessões novas |
| R10 | Rastrear o que o Gate fez o Antigravity criar (lista "criadas pelo Auto-Run") |
| R17 | Monólito: manter adiado; quando separar, `autorun` vira o módulo com testes de contrato do `agy` |

### Detalhes do veredito

- **Contrato de dados:** bem documentado no ESTADO, com níveis de confiança. Esse rigor faltou aos handoffs do Gemini.
- **Acoplamento ao protobuf:** inevitável. Mitigado pelos `tools/inspect_*.py`; falta transformar isso num passo da rotina de atualização do `agy`.

---

## 6. Repo Maintainer

**Veredito**: APPROVE WITH CHANGES

### Checklist de convenções

| Item | Situação |
|---|---|
| Versão única (`__version__`) conferida pelo CI contra a tag | ✅ |
| CHANGELOG por versão, conferido na Release | ✅ |
| Testes barram a montagem | ✅ |
| PyInstaller fixo no CI | ✅ |
| PyInstaller fixo na montagem local | ❌ (R14) |
| ESTADO com Snapshot (feito / faltando / próximo) | ✅, mas desatualizado depois de 27/10 (R6) |
| README coerente com o comportamento | ⚠ "só lê" sem ressalva (R5) |
| Testes cobrem o ambiente real | ⚠ sem junction, BOM ou `cwd` (transversal) |
| `.gitignore` | ✅ |

### Oportunidades de reuso

- `tools/inspect_schema.py` pode alimentar o "Diagnóstico do ambiente" (R7) e a investigação do título (R16).
- `parse_tokens`, `fmt_time` e `uri_to_path` já resolvem os formatos que a sessão encontrou (`%3A`, UTC com 7 casas decimais).
- O teste de fontes já monta árvores sintéticas: estender com `os.symlink` custa poucas linhas.

### Problemas críticos

Nenhum.

### Recomendações

R5 (README), R6 (ESTADO), R14 (`build_exe.bat`), fixture "ambiente sujo" (transversal) e ajuste de `tests/test_autorun.py:62` e `:78` junto com C1.

### Detalhes do veredito

- **Disciplina de projeto:** alta. ESTADO, níveis de confiança e lições de processo registradas.
- **Deriva:** só a documental, causada por um evento externo (a sessão de 27/10).

---

## 7. Production Readiness

**Veredito**: APPROVE WITH CHANGES

### Análise de modos de falha

| Modo de falha | Probabilidade no ambiente do usuário | Efeito | Mitigação atual | Falta |
|---|---|---|---|---|
| Retomada em projeto errado | **Certa** em todo Auto-Run real | Sessão em "CLI Project"; "different workspace" no IDE | Nenhuma | C1 |
| Fonte "backup" que é a pasta viva | **Certa** (as junctions existem) | Decisão de recuperação errada | Nenhuma | C2 |
| JSON de projeto regravado com BOM | Média (scripts PowerShell 5.1 de terceiros) | Projeto some do agrupamento | Aviso genérico | R1 |
| Três motores escrevendo no mesmo banco | Alta (daemon + VS Code + Auto-Run) | Conflito numa mesma conversa **[Não verificado]** | Auto-Run usa sessão nova | Aviso na confirmação: "não rode sobre conversa aberta no IDE" |
| Atualização do `agy` muda o protobuf | Média | Dossiê incompleto e silencioso | `tools/inspect_*` manual | Contagem de passos "não interpretados" no dossiê ou no log |
| Cancelar deixa processo filho | Média | Processo órfão segurando arquivos | `terminate` / `kill` | R12 |
| Segredo no Diálogo completo | Média | Vazamento ao compartilhar | Cabeçalho de aviso | R4 |

### Checklist de ambiente (o que a sessão revelou)

| Fato do ambiente real | O Gate lida? |
|---|---|
| `antigravity-cli` e `antigravity-ide` são junctions | ❌ (C2) |
| Pastas `.bak` reais (`antigravity-cli.bak`, `antigravity-ide.bak`, `antigravity-backup`) | ✅ como fontes separadas |
| `corrupt_quarantine` com 2 bancos | ✅ |
| `workspace_uris` com `%3A` e `%C3%A1` | ✅ (`uri_to_path`) |
| Horários em UTC com 7 casas decimais | ✅ |
| Daemon de remote control ativo | n/a (fora do escopo); relevante para concorrência |
| `agy.exe` em dois lugares, hoje idênticos | ⚠ o Gate usa só o do PATH |
| `config/projects` editado por terceiros | ⚠ BOM (R1); `projectConversations` ignorada ✅ |

### Problemas críticos

| # | Problema | Correção |
|---|---|---|
| C1 | Toda retomada real cai fora do projeto | Ver a tabela mestre |

### Recomendações

R1, R4, R12 e aviso de concorrência na confirmação do Auto-Run.

### Detalhes do veredito

- **Robustez:** alta para leitura (falha isolada por sessão, log com rotação, gravação atômica).
- **Aderência ao ambiente real:** dois desvios certos (C1, C2) e um provável (R1).

---

## 8. DX Engineer

**Veredito**: APPROVE WITH CHANGES

### Auditoria de mensagens de erro

| Mensagem | Diz o que houve? | Diz o que fazer? | Nota |
|---|---|---|---|
| "Projeto ilegível: <arquivo>" | Em parte | Não | Com BOM, deveria dizer "arquivo com BOM (marca de início UTF-8)" |
| "N aviso(s) ao ler os bancos de sessão" + Abrir log | Sim | Sim | Bom |
| "Não encontrei o agy…" | Sim | Sim (AGY_EXE) | Bom |
| Erro de modelo do `agy` | Sim | Sim (lista de modelos aceitos) | Muito bom |
| Sucesso do Auto-Run | Sim | Não diz onde ver a sessão nova | R9 |

### Jornada do desenvolvedor-usuário

1. **Instalar:** baixa o `.exe` com SHA-256. Bom.
2. **Entender o ambiente:** o Gate não mostra junctions, os dois `agy` nem projetos com problema. Na sessão de 27/10, isso custou cerca de 25 passos manuais (R7).
3. **Configurar:** variáveis de ambiente só no README e no ESTADO (R13).
4. **Diagnosticar falha:** `gate.log` + janela Sobre com "Copiar informações". Bom; ganharia os dois `agy` e o alvo das junctions.

### Problemas críticos

Nenhum.

### Recomendações

R7 (diagnóstico somente leitura), R9 (aviso pós-Auto-Run), R13 (`--help`) e mensagem específica para BOM (junto com R1).

### Detalhes do veredito

- **Observabilidade:** boa para o próprio app; falta a do ambiente Antigravity. É ali que mora a maior dor do usuário.

---

## 9. Performance Engineer

**Veredito**: APPROVE

### Orçamento de recursos

| Recurso | Uso | Limite / risco |
|---|---|---|
| Varredura de fonte | Thread de trabalho, cache por arquivo | OK (cerca de 50 sessões no ambiente real) |
| Fontes duplicadas por junction | Cada uma relê os mesmos bancos (o cache é por caminho) | Desperdício pequeno; some com C2 |
| Busca FTS | **Thread da interface**, `timeout=2.0` | Congela até 2 s com o banco ocupado (3 motores ativos) (R11) |
| `discover_sources` | 2 níveis sob `~/.gemini` (inclui `config/plugins` e `skills`, com milhares de arquivos) | Só lista pastas de 2 níveis: barato |
| Exportação | Thread de trabalho, lotes de 100 | OK (6.000 passos em 0,5 s, medição do ESTADO) |

### Análise de caminho quente

- **Abrir o app / trocar de fonte:** fora da thread da interface. OK.
- **Digitar na busca:** FTS na thread da interface. Com o daemon e o VS Code escrevendo no mesmo banco, a espera pelo lock fica mais provável que nos testes.

### Problemas críticos

Nenhum.

### Recomendações

R11 (FTS em worker) e C2 (evita varreduras duplicadas).

### Detalhes do veredito

- **Responsividade:** boa, com uma exceção conhecida (FTS).

---

## 10. Accessibility Engineer

**Pulada.** Nenhum achado da sessão de 27/10. Teclado, foco, dicas e menu de contexto foram corrigidos na 1.0 (etapa 2b da revisão final).
