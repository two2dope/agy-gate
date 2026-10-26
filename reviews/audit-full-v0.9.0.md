# Auditoria Full Spectrum: AntigravityGate 0.9.0

**Data**: 2026-10-26
**Modo**: Repo Health (saúde geral do repositório; não é diff nem plano)
**Fonte**: `two2dope/agy-gate`, branch `claude/pensive-dijkstra-a82k36` (HEAD `29f70af`, igual ao `main` auditado)
**Lentes executadas**: 10/10 (Frontend e Backend adaptadas: não há React/Rust; foram aplicadas à camada Tk e à camada Python/SQLite/subprocess)
**Lentes puladas**: nenhuma

**Método e limites**
- Li `AntigravityGate.py` inteiro (3.323 linhas), README, CHANGELOG, `docs/ESTADO_DO_PROJETO.md`, workflow de CI, `packaging/build_exe.bat`, `tests/run_all.sh`, `tests/fake_agy.py` e amostras dos testes.
- Rodei a suíte: **15/15 passam** (Python 3.12.3, Tk 8.6, Xvfb, 31 s). **[Verificado]**
- Testei isoladamente 7 suspeitas com um script próprio (fora do repositório). Resultados marcados **[Verificado]**.
- Não rodei no Windows. Tudo que depende de Win32, DWM, Segoe MDL2, `cmd.exe` ou do `agy` real está marcado **[Não verificado]**.
- Os sub-skills `audit-as-*` são calibrados para Orbit (Tauri/React/Rust). Apliquei o critério de cada lente direto ao código Python, como na auditoria anterior (`reviews/audit-plan-full.md`, do script de 302 linhas). Este arquivo não sobrescreve aquele: ele documenta o script original; este documenta a 0.9.0.

---

## Veredito Mestre: APPROVE WITH CHANGES

A parte de leitura, curadoria e exportação está sólida: somente-leitura real (`mode=ro`), carga em segundo plano, estado próprio separado, testes que cobrem o que prometem e honestidade sobre o que não foi verificado. Os três problemas críticos estão todos no **Auto-Run**, que é justamente o critério que falta para a 1.0. São correções pequenas (dezenas de linhas), mas precisam entrar **antes do teste real com o `agy`**: o teste vai validar a leitura de sucesso, e hoje o código pode registrar como sucesso o que não foi.

## Veredito por Lente

| # | Lente | Veredito | Críticos | Recomendações |
|---|-------|----------|----------|---------------|
| 1 | Design Engineer | APPROVE WITH CHANGES | 0 | 4 |
| 2 | UX Engineer | APPROVE WITH CHANGES | 1 | 5 |
| 3 | Frontend Engineer (camada Tk) | APPROVE WITH CHANGES | 0 | 4 |
| 4 | Backend Engineer (Python/SQLite/subprocess) | NEEDS REWORK (só Auto-Run) | 2 | 5 |
| 5 | Structural Engineer | APPROVE WITH CHANGES | 0 | 3 |
| 6 | Repo Maintainer | APPROVE WITH CHANGES | 0 | 5 |
| 7 | Production Readiness | APPROVE WITH CHANGES | 2 (compartilhados) | 5 |
| 8 | DX Engineer | APPROVE WITH CHANGES | 0 | 4 |
| 9 | Performance Engineer | APPROVE | 0 | 3 |
| 10 | Accessibility Engineer | APPROVE WITH CHANGES | 0 | 5 |

## Todos os Problemas Críticos (Must Fix)

| # | Problema | Lente(s) | Arquivo(s) | Impacto | Correção |
|---|----------|----------|------------|---------|----------|
| C1 | Sucesso do `agy` é inferido pela **ausência** de erro: código de saída ignorado e `conversation_id` vazio aceito. `{"conversation_id":"x"}` sem `status` vira `ok=True` **[Verificado]** | Backend, Prod | `AntigravityGate.py:951`, `:1053-1062` | Formato de sucesso real ainda não visto. Uma saída inesperada grava handoff `ok`, mostra `↪ retomada` e tira a sessão do próximo lote (sem "Refazer"). A UI afirma um estado falso: o mesmo defeito-raiz da auditoria original | Guardar `proc.returncode` em `_run_agy`; `ok` só com `returncode == 0` **e** `conversation_id` não vazio **e** `status != ERROR`. Logar a saída bruta no `gate.log` nas primeiras execuções reais |
| C2 | A garantia "somente leitura" depende da ordem dos argumentos: o prompt (com `\n`) vem **antes** de `--mode plan` **[Verificado: ordem e quebra de linha]**. Se `agy` for um `.cmd`/`.bat` (shim comum de CLIs Node), o `cmd.exe` encerra a linha no `\n` e descarta `--mode plan` e `--output-format json` **[Não verificado: tipo do executável `agy` e comportamento no Windows]** | Backend, Prod | `AntigravityGate.py:891-893`, `:923-929`, `:896-900` | Pior caso: sessão nova roda no modo padrão do `agy` (pode editar arquivos), contra a salvaguarda nº 4 do projeto | (1) Prompt numa linha só (trocar `\n` por espaço). (2) Flags de segurança primeiro, prompt por último. (3) Em `find_agy`, se a extensão for `.cmd`/`.bat`, recusar ou avisar na confirmação |
| C3 | Fechar a janela durante Auto-Run ou exportação não pergunta nem cancela. `on_close` só salva a geometria e destrói; as threads são `daemon` | UX, Prod | `AntigravityGate.py:2506-2510`, `:3189`, `:3109` | Auto-Run: o processo `agy` fica sem dono **[Não verificado: se continua ou morre com o pipe fechado]**; a sessão nova pode existir sem handoff gravado, e o próximo lote repete a sessão (cota gasta duas vezes). Exportação: arquivo `.md` truncado no destino | Em `on_close`: se `autorunning` ou `exporting`, `askyesno` ("Cancelar e sair?"); se sim, `runner.cancel()`, esperar a thread por até ~5 s e só então destruir |

## Preocupações Transversais

| Preocupação | Apontada por | Causa-raiz | Correção unificada |
|-------------|--------------|------------|--------------------|
| Auto-Run confia em comportamento não verificado do `agy` | Backend, Prod, DX, UX | O contrato do `agy` foi inferido de uma saída de erro e de um `agy` simulado com `#!` (Linux) | Pacote C1+C2 antes do teste real; no teste real, rodar primeiro em lote de 1 sessão e conferir `gate.log` |
| Ciclo de vida de trabalho em segundo plano | UX, Prod, Backend, Perf | Threads `daemon` sem dono; subprocesso sem encerramento da árvore; busca FTS fora do padrão "worker + fila" | `on_close` com cancelamento (C3); busca por conteúdo na mesma fila das outras tarefas |
| Janelas do Auto-Run fora do sistema visual e de teclado | Design, A11y, UX | `confirm_autorun` e `open_autorun_window` usam `tk.Button`/`tk.Listbox` crus, cor `#555555` fixa, tamanhos sem DPI | Reescrever as duas janelas com `IconButton`, `themed_widget`, `px()` e `place_over` (já usado) |
| Windows real nunca exercitado por testes | Repo, Prod, A11y | Testes rodam só em Linux/Xvfb e **não rodam no CI**; o CI do Windows só faz autoteste do `.exe` | Rodar `tests/run_all.sh` no CI (Linux, rápido) e manter a lista "Não verificado" do CHANGELOG como checklist da 1.0 |
| Dados de conversa gravados fora dos bancos do Antigravity | Prod, Backend | Dossiês em `handoffs/` acumulam sem limite; máscara de segredos tem lacunas | Ampliar `SECRET_PATTERNS` (R-B2) e informar/limpar `handoffs/` antigos |

## Todas as Recomendações

| # | Recomendação | Lente | Arquivo(s) | Correção |
|---|--------------|-------|------------|----------|
| R1 | Estado em memória (fallback) quebra o Auto-Run: conexão `:memory:` criada na thread da UI e usada pela thread de trabalho → `ProgrammingError` **[Verificado]** | Backend | `:818-827`, `:1018`, `:1030` | `sqlite3.connect(":memory:", check_same_thread=False)` + um `threading.Lock` em `_connect` |
| R2 | Máscara de segredos deixa passar `sk_live_…` (Stripe), `postgres://user:senha@`, JWT `eyJ…`, `xoxb-…` (Slack), `Authorization: Basic` **[Verificado]** | Backend, Prod | `:370-378` | Acrescentar 5 padrões; teste de regressão com estas amostras |
| R3 | Testes não rodam no CI | Repo, Prod | `.github/workflows/build-exe.yml` | Job `ubuntu-latest` com `python3-tk xvfb` e `tests/run_all.sh` antes do build do `.exe` |
| R4 | `run_all.sh` decide pelo texto "TODOS OS TESTES", não pelo código de saída | Repo | `tests/run_all.sh:17-19` | Exigir `exit 0` **e** o sentinela |
| R5 | `permissions: contents: write` vale para todo push no `main`; PyInstaller sem versão fixa | Repo, Prod | `build-exe.yml:11-12`, `:33` | `contents: read` no topo e `write` só no passo/job de Release; `pyinstaller==6.x.y` fixo |
| R6 | Busca por conteúdo (FTS) roda na thread da UI, com `timeout=2.0` no SQLite | Frontend, Perf | `:2847-2876` | Mandar para worker + `self.queue`, como `load_data` |
| R7 | Janelas de confirmação e log do Auto-Run sem tema, sem `px()`, cor fixa | Design, A11y | `:3113-3142`, `:3191-3201` | Ver preocupação transversal |
| R8 | `AGY_ROT_TOKENS` vence a escolha feita na tela, em silêncio, a cada abertura **[Verificado]** | DX, UX | `:88-92` | Usar a variável só se não houver `context` salvo, ou mostrar na janela Limites "valor definido por AGY_ROT_TOKENS" |
| R9 | `terminate()` no Windows não encerra a árvore de processos do `agy` | Prod, Backend | `:968-997` | `CREATE_NEW_PROCESS_GROUP` + `taskkill /T /F /PID` no cancelamento e no tempo esgotado |
| R10 | Menu de contexto só com botão direito; painel de detalhes só abre/fecha com mouse; dica de botão desabilitado só no hover | A11y | `:2474`, `:2418-2421`, `:1591-1620` | `<Shift-F10>` e `<App>` na árvore; `takefocus` + `<Return>`/`<space>` na barra de detalhes; dica também em `<FocusIn>` |
| R11 | Notificação com "Desfazer" some em 9 s | A11y, UX | `:2213` | Notificação com ação não expira enquanto tem foco ou mouse em cima; ou ttl ≥ 20 s |
| R12 | Duplo clique numa sessão abre "Salvar como" (exportar diálogo) | UX | `:2588-2593` | Duplo clique abre o painel de detalhes; exportar fica no botão e no menu |
| R13 | Coluna Título é a 6ª, depois de data, tamanho, contexto, passos e falhas | UX | `:2444` | Título logo após "Projeto / Sessão"; números à direita |
| R14 | Exportação com várias sessões selecionadas usa só a primeira, sem aviso | UX | `:3072-3079` | Desabilitar com motivo quando `len(selected_session_ids()) > 1` |
| R15 | `--help` inexistente; variáveis `ANTIGRAVITY_HOME`, `AGY_EXE`, `AGY_ICONS`, `AGY_ROT_TOKENS` só no README/docs | DX | `:3302-3309` | `--help` com a lista; mesma lista na dica do cabeçalho |
| R16 | Arquivo monolítico de 3,3 mil linhas; `AntigravityGateApp` com ~1.250 linhas | Structural | `AntigravityGate.py` | **Depois da 1.0**: separar `core` (protobuf, leitura, exportação), `autorun`, `ui`. O PyInstaller continua gerando um `.exe` |
| R17 | Gravações não atômicas (`settings.json`, exportações) | Prod | `:1309-1315`, `:798-803` | Gravar em `.tmp` e `os.replace` |

**Nice-to-haves** (sem impacto que justifique entrar antes da 1.0): rotação do `gate.log` (`RotatingFileHandler`); limpeza de `handoffs/` antigos; `METRICS_CACHE` sem despejo; troca de tema gera ícones em ~0,4 s a 150% DPI **[Verificado]**; busca e seleção perdidas após Atualizar/ordenar; emojis fora do BMP (`📦`, `📋`) em widgets Tk 8.6 **[Não verificado no Windows]**; nota de cabeçalho em `reviews/audit-plan-full.md` dizendo que é do script original.

---

# Relatórios por Lente

---

## 1. Design Engineer

**Veredito**: APPROVE WITH CHANGES

### Arquivos revisados

| Arquivo | Trechos |
|---|---|
| `AntigravityGate.py` | `THEMES` (`:1263-1290`), `ICONS` (`:1293-1297`), `IconButton` (`:1623-1787`), `Chip`, `Toast`, `ThemePicker`, `LimitDialog`, `apply_theme` (`:2103-2154`), `create_widgets`, `draw_gauge`, janelas do Auto-Run (`:3113-3201`) |
| `tests/test_theme.py` | conferência de contraste por tema |
| `docs/ESTADO_DO_PROJETO.md` | seções de interface |

### Problemas críticos

Nenhum.

### Recomendações

| # | Problema | Onde | Correção |
|---|---|---|---|
| D1 | Confirmação e log do Auto-Run usam widgets Tk crus: fundo cinza do sistema nos 6 temas escuros, `fg="#555555"` fixo, `wraplength=620` e `size=(780, 420)` sem `px()`, botões nativos ao lado dos `IconButton` do resto do app. É a única ação primária do app e a única tela fora do sistema visual | `:3113-3142`, `:3191-3201` | Montar com `themed_widget`, `IconButton(kind="primary")` para Iniciar, `px()` em todos os tamanhos |
| D2 | `messagebox` nativo continua branco nos temas escuros (documentado) e é usado em fluxos frequentes (`mark_selected` com várias sessões, avisos de seleção) | `:2611`, `:3069-3082` | Trocar avisos de seleção por botão desabilitado com motivo (já existe); manter `messagebox` só para erros |
| D3 | Troca de tema regenera todos os ícones na thread da UI: 16 ícones a 24 px em 0,38 s **[Verificado]** | `render_icon` `:1529-1556`, `apply_theme` `:2104-2106` | Gerar os ícones do tema novo sob demanda já acontece; pré-gerar no `after_idle` ou reduzir supersampling para `ss=3` |
| D4 | Emojis fora do BMP em widgets Tk (`📦` no menu, `📋 ⏭` no log do Auto-Run). Tk 8.6 trata mal pares substitutos **[Não verificado no Windows]** | `:2898`, `:3231` | Usar símbolos do BMP, como o resto do app já faz |

### Conformidade com o sistema de design

| Item | Situação |
|---|---|
| Tokens de cor | Todas as cores da janela principal vêm da paleta via `themed_widget`; exceções só nas janelas do Auto-Run e em `#555555` |
| Escala por DPI | `px()` aplicado na janela principal, diálogos de Limites e seletor de tema; ausente no Auto-Run |
| Raio de canto | Por tema (`radius` 0 a 12) aplicado nos botões e no medidor |
| Tipografia | Família base com fallback (`Segoe UI` → `Helvetica` → `DejaVu Sans`) e fonte de título por tema |
| Contraste | `test_theme` confere ≥ 4,5:1 para texto em fundo, painel, painel2, banner, selos e badge, em todos os 8 temas **[Verificado: teste passa]** |
| Barra de título | Segue o tema via DWM; caixas nativas não **[Não verificado visualmente]** |

### Cobertura de estados visuais

| Componente | Normal | Hover | Pressionado | Foco | Desabilitado | Ocupado | Vazio | Erro |
|---|---|---|---|---|---|---|---|---|
| `IconButton` | ✔ | ✔ | ✔ | ✔ (borda 2 px) | ✔ (com motivo) | ✔ (spinner) | n/a | ✔ (flash) |
| Tabela | ✔ | nativo | n/a | nativo | n/a | ✔ ("Lendo as sessões…") | ✔ (com ação) | ✔ (status + log) |
| Painel de detalhes | ✔ | n/a | n/a | ✘ | n/a | n/a | ✔ | n/a |
| Seletor de tema | ✔ | ✔ | n/a | ✔ (setas) | n/a | n/a | n/a | n/a |
| Limites | ✔ | n/a | n/a | nativo | ✔ (Aplicar) | n/a | n/a | ✔ (texto em vermelho) |
| Auto-Run (confirmação e log) | ✔ | nativo | nativo | nativo | ✘ | ✘ | n/a | ✔ (texto) |

### Detalhes do veredito

- **Fidelidade aos tokens**: alta, salvo D1.
- **Cobertura de estados**: acima do usual para Tk.
- **Modo escuro**: 6 de 8 temas são escuros; quebra só nas janelas nativas (D1, D2).
- **Animação**: spinner a 70 ms e flash de 900 ms; sem excesso.
- **Consistência**: a janela de Auto-Run é o desvio visível.

---

## 2. UX Engineer

**Veredito**: APPROVE WITH CHANGES

### Mapa da jornada do usuário

| Etapa | O que o usuário faz | O que o app responde | Atrito |
|---|---|---|---|
| Abrir | Dois cliques no `.exe` | Janela dentro da área útil; carga em segundo plano com progresso | SmartScreen (documentado) |
| Entender o estado | Lê a tabela | Ícone e texto de estado por linha, medidor de contexto, selos no rodapé, aviso de críticas | Título fica na 6ª coluna (R13) |
| Encontrar uma sessão | Ctrl+F, digita, Enter | Lista plana com contagem; nota quando não há índice de conteúdo | Busca some ao clicar Atualizar |
| Ver detalhes | Clica numa linha | Painel com medidor, workspace, falhas, retomada | Duplo clique exporta em vez de abrir detalhes (R12) |
| Curar | Aprovar/Arquivar/Pendente | Confirmação em lote, flash verde, notificação com Desfazer | Desfazer some em 9 s (R11) |
| Exportar | Botão ou menu | "Salvar como", progresso, notificação com Abrir | Multi-seleção exporta só a primeira, sem aviso (R14) |
| Retomar | Auto-Run | Confirmação com simulação ligada por padrão; log ao vivo; resumo | Fechar a janela no meio não pergunta (C3); sucesso pode ser falso (C1) |
| Sair | Fecha a janela | Salva tamanho e posição | Ver C3 |

### Problemas críticos

| # | Problema | Onde | Impacto | Correção |
|---|---|---|---|---|
| U1 (= C3) | Fechar durante Auto-Run ou exportação, sem pergunta | `:2506-2510` | Trabalho perdido em silêncio; sessão nova sem registro; arquivo truncado | Confirmar e cancelar antes de sair |

### Recomendações

| # | Problema | Onde | Correção |
|---|---|---|---|
| U2 | Duplo clique = "Salvar como". Em tabelas, duplo clique costuma abrir/detalhar | `:2588-2593` | Duplo clique foca o painel de detalhes |
| U3 | Título na 6ª coluna; em janela estreita exige rolagem horizontal para ver o que identifica a sessão | `:2444` | Reordenar colunas |
| U4 | Exportar com várias sessões selecionadas usa só a primeira | `:3072-3079` | Desabilitar com motivo, ou exportar em lote |
| U5 | Desfazer com prazo de 9 s | `:2213` | Ver R11 |
| U6 | `AGY_ROT_TOKENS` reverte a escolha da tela a cada abertura | `:88-92` | Ver R8 |

### Verificação de consistência de interação

| Padrão | Consistente? | Observação |
|---|---|---|
| Ação destrutiva/em lote pede confirmação | Sim | Marcação de várias sessões e Auto-Run |
| Toda ação tem retorno visível | Sim | Flash, notificação, barra de status |
| Botão desabilitado explica o motivo | Sim (mouse) | Teclado não vê o motivo (A11y) |
| Erros em janela, sucesso em notificação | Sim | Regra documentada e seguida |
| Estados vazios com ação | Sim | Limpar busca / Atualizar |
| Sair protege trabalho em andamento | **Não** | C3 |

### Detalhes do veredito

- **Modelo mental**: "fonte → sessões → estado → retomada" está claro na tela.
- **Feedback**: forte em toda a janela principal.
- **Recuperação de erro**: boa (Desfazer, log, mensagens com próximo passo), salvo no fechamento.
- **Honestidade**: a UI diz o que é heurística e o que é medido; C1 é o ponto em que isso ainda pode falhar.

---

## 3. Frontend Engineer (camada Tk)

**Veredito**: APPROVE WITH CHANGES

Adaptação: não há React/TypeScript. A lente avaliou a camada de interface Tk como se avalia uma camada de renderização: quem muda estado, quem redesenha, o que roda na thread da UI.

### Análise do caminho de renderização

| Gatilho | Caminho | Custo |
|---|---|---|
| Fim da carga | `poll` → `render` → `populate` (apaga e recria a árvore) → `set_status` → `update_chips` + `update_banner` + `update_empty` + `update_actions` → `update_details` | O(n) inserções + ~3 chamadas Tcl por linha em `iter_sessions` |
| Seleção | `<<TreeviewSelect>>` → `update_actions` → `autorun_candidates` (O(n) em Python) + `update_details` | Leve |
| Marcar estado | `state.set_many` → `state.load` → `refresh_labels` (3 chamadas Tcl por linha) → `set_status` | Leve |
| Ordenar, buscar, limites | `populate` completo | Perde a seleção atual |
| Troca de tema | `apply_theme` → recolore widgets registrados → `restyle_rows` → ícones novos | ~0,4 s a 150% DPI (D3) |
| Redimensionar | `<Configure>` na raiz (dispara também para filhos) → debounce 60 ms → `_fit_all` | Estável: `measure(False)` não depende do modo compacto |

### Avaliação de segurança de tipos / estado

- **Estado global mutável**: `CONTEXT_LIMITS` (`:51`) e `METRICS_CACHE` (`:118`) são módulo-globais. `ctx_label` e `ctx_level` leem `CONTEXT_LIMITS` implicitamente; funciona porque só há uma janela, mas acopla funções puras à preferência atual.
- **Thread da UI**: a regra "só `poll` mexe na tela com dados novos" é seguida em carga, exportação e Auto-Run. Exceção: `run_search` → `fts_hits` abre SQLite na thread da UI (R6).
- **Referências de imagem**: `icon_lbl.image = img` e `old_icons` mantêm `PhotoImage` vivas durante a troca de tema. Correto.
- **`after` órfãos**: `Toast.dismiss` e `Tooltip._leave` cancelam; `IconButton.flash_ok` agenda um `after(900)` que pode disparar em widget destruído (Toast) e gerar `TclError` silencioso no Tk **[Inferência]**.

### Problemas críticos

Nenhum.

### Recomendações

| # | Problema | Onde | Correção |
|---|---|---|---|
| F1 | FTS na thread da UI | `:2847-2876` | Worker + fila |
| F2 | `populate` perde a seleção | `:3009-3054` | Guardar `selected_cids` antes e reselecionar depois |
| F3 | `render` limpa a busca a cada carga | `:2996-2997` | Reaplicar `run_search` se havia termo |
| F4 | Funções de formatação leem limite global | `:54-62`, `:215-222` | Passar `(att, crit)` explicitamente onde for barato |

### Detalhes do veredito

- **Responsividade**: carga e exportação fora da UI; busca é a exceção.
- **Corretude de redesenho**: boa; testes de janela e ícones cobrem.
- **Acoplamento**: aceitável para um arquivo único; ver Structural.

---

## 4. Backend Engineer (Python / SQLite / subprocess)

**Veredito**: NEEDS REWORK (restrito ao Auto-Run; leitura e exportação aprovadas)

Adaptação: não há Rust/Tauri. A lente avaliou a camada de dados (protobuf, SQLite), a exportação e o subprocesso do `agy`.

### Análise dos caminhos de erro

| Caminho | Tratamento | Avaliação |
|---|---|---|
| Banco de sessão corrompido ou travado | `session_metrics` em `try`, aviso por sessão, contagem no status, `Abrir log` | Bom; testado em `test_m1` |
| Protobuf truncado ou inválido | `pb_parse` levanta `ValueError`; chamadores tratam; limites de varint e campo | Bom |
| `conversation_summaries.db` ilegível | aviso e segue com os arquivos | Bom |
| JSON de projeto inválido | aviso por arquivo | Bom |
| Arquivo some entre `exists` e `stat` | `os.stat` sem `try` em `scan_source` derruba a varredura inteira **[Inferência: janela curta]** | Nice-to-have |
| Estado próprio sem disco | cai para `:memory:` com aviso | **Quebra o Auto-Run** (R1) **[Verificado]** |
| `agy` ausente | mensagem com próximo passo | Bom |
| `agy` com cota | interrompe o lote, mostra reset, arquiva sessões vazias | Bom (testado com simulado) |
| `agy` com saída inesperada | `parse_agy_output` aceita sem `status` como sucesso | **C1** |
| `agy` em tempo esgotado | `kill` após `timeout + 60 s` | Bom; não mata processos filhos (R9) |

### Auditoria de ciclo de vida de recursos

| Recurso | Abertura | Fechamento | Situação |
|---|---|---|---|
| Conexões dos bancos do Antigravity | `open_ro` (`closing`, `mode=ro`, `timeout=2`) | `with` | ✔ |
| Conexões do `gate_state.db` | `_connect` por chamada | `closing` | ✔ (persistente); ✘ entre threads no modo memória |
| Cursor de `iter_steps` | `fetchmany(100)` | junto com a conexão | ✔ |
| Arquivos de exportação | `open(..., 'w')` | `with` | ✔; não atômico (R17) |
| Subprocesso `agy` | `Popen` com pipes | `communicate`/`kill` | ✔ no fluxo normal; ✘ ao fechar o app (C3) |
| Threads | `daemon=True` | nunca aguardadas | Ver C3 |
| `gate.log` | `FileHandler` | fim do processo | Cresce sem limite (nice-to-have) |

### Problemas críticos

| # | Problema | Onde | Correção |
|---|---|---|---|
| B1 (= C1) | Sucesso por ausência de erro; `returncode` ignorado | `:932-954`, `:976-997` | `ok` exige `returncode == 0`, `conversation_id` e `status != ERROR` |
| B2 (= C2) | Prompt com `\n` antes de `--mode plan`; `.cmd` não tratado | `:891-893`, `:923-929` | Prompt de uma linha, flags antes do prompt, recusar `.cmd/.bat` |

### Recomendações

| # | Problema | Onde | Correção |
|---|---|---|---|
| B3 (= R1) | `:memory:` entre threads | `:818-827` | `check_same_thread=False` + lock |
| B4 (= R2) | Lacunas na máscara | `:370-378` | 5 padrões novos + teste |
| B5 (= R9) | Árvore de processos no cancelamento | `:968-997` | Grupo de processos + `taskkill /T` |
| B6 | Leitura com `mode=ro` em banco no modo rollback-journal segura `SHARED` durante a exportação (0,5 s em 37 MB) e pode fazer o Antigravity receber `SQLITE_BUSY` **[Não verificado: modo de journal dos bancos reais]** | `:134-137` | Conferir `PRAGMA journal_mode` com `tools/inspect_schema.py`; se não for WAL, exportar a partir de uma cópia (`sqlite3.backup`) |
| B7 | Exportação completa decodifica todos os passos duas vezes | `:796-799` | Aceitável hoje (medido em 0,5 s); acumular `files` na mesma passada se crescer |

### Detalhes do veredito

- **Somente leitura**: garantido por URI `mode=ro` em todos os acessos aos bancos do Antigravity. ✔
- **Robustez do parser**: alta.
- **Auto-Run**: as salvaguardas existem (lista de argumentos sem shell, simulação padrão, cota interrompe o lote, trava contra repetição), mas duas delas dependem de suposições não verificadas (C1, C2).

---

## 5. Structural Engineer

**Veredito**: APPROVE WITH CHANGES

### Mapa de dependências (dentro do arquivo)

```
constantes / caminhos (BASE_DIR, LOG_DIR, ...)
   │
   ├── utilitários puros: parse_tokens, fmt_*, ctx_level*  ── lê CONTEXT_LIMITS (global)
   ├── protobuf: _varint, pb_parse, pb_dig, pb_text, pb_num
   │       └── leitura: first_user_text, session_metrics, decode_step, iter_steps, quick_meta
   │               └── exportação: write_full_export, build_dossier, redact, export_session
   │                       └── AutoRunner (+ build_agy_args, parse_agy_output, find_agy)
   ├── StateStore (gate_state.db)  ◄── AutoRunner, App
   ├── fontes: discover_sources, load_projects, scan_source  ── lê METRICS_CACHE (global)
   ├── visual: THEMES, ICONS, render_icon, contrast, place_over, style_titlebar (Win32)
   ├── widgets: Tooltip, IconButton, Chip, Toast, ThemePicker, LimitDialog
   └── AntigravityGateApp (~1.250 linhas) ── usa tudo acima
```

Sem ciclos. A direção das dependências é limpa: nada abaixo de `AntigravityGateApp` importa Tk, exceto o bloco visual. `AutoRunner` declara "Sem Tk aqui" e cumpre.

### Análise de cruzamento de fronteiras

| Fronteira | Como é cruzada | Situação |
|---|---|---|
| UI ↔ worker | `queue.Queue` + `poll` a cada 100 ms; mensagens `(gen, kind, payload)` | ✔ Um único canal; `gen` descarta respostas velhas |
| App ↔ bancos do Antigravity | só por `open_ro` | ✔ |
| App ↔ estado próprio | só por `StateStore` | ✔ |
| App ↔ `agy` | só por `AutoRunner._run_agy` | ✔ |
| App ↔ Win32 | `_win_work_area`, `style_titlebar`, ambos com `os.name` e `try` | ✔ |
| Preferências | `settings.json` lido no `__init__`, gravado por vários métodos | Aceitável |

### Problemas críticos

Nenhum.

### Recomendações

| # | Problema | Correção |
|---|---|---|
| S1 | Arquivo único de 3.323 linhas; classe da janela com ~1.250 | Depois da 1.0: `agygate/core.py` (protobuf, leitura, exportação), `autorun.py`, `ui/`. O `build_exe` aponta para um `__main__.py`. Antes da 1.0, não: custo alto, sem defeito que exija |
| S2 | Dois globais mutáveis (`CONTEXT_LIMITS`, `METRICS_CACHE`) | Mover para atributos de uma instância (`Limits`, `MetricsCache`) quando houver S1 |
| S3 | Busca FTS fora do padrão worker/fila | Ver R6 |

### Detalhes do veredito

- **Coesão**: blocos bem separados por comentários e responsabilidades.
- **Acoplamento**: baixo entre blocos; alto dentro da classe da janela.
- **Evolução**: o tamanho já pesa na navegação, não na corretude.

---

## 6. Repo Maintainer

**Veredito**: APPROVE WITH CHANGES

### Checklist de convenções

| Item | Situação |
|---|---|
| README com uso, testes, publicação e estrutura | ✔ |
| CHANGELOG em SemVer, versão única em `__version__`, CI confere tag × versão | ✔ |
| Commits no padrão `feat/fix/chore/ci/docs` | ✔ |
| `.gitignore` cobre build, dist, venv, IDE | ✔ |
| Dependências | Só biblioteca padrão. ✔ |
| Testes versionados e executáveis com um comando | ✔ (`tests/run_all.sh`) |
| Testes no CI | ✘ (R3) |
| Runner usa código de saída | ✘ (R4) |
| Versões fixas no build | ✘ PyInstaller sem versão; actions por tag, não por SHA |
| Permissões mínimas no CI | ✘ `contents: write` global (R5) |
| Linter/formatador | ausente; estilo consistente mesmo assim |
| Docs de estado atualizadas | ✔ (`docs/ESTADO_DO_PROJETO.md` com snapshot) |
| Auditoria anterior rotulada | parcial: `reviews/audit-plan-full.md` descreve o script de 302 linhas sem dizer no título que está superada |

### Oportunidades de reuso

| Duplicação | Onde | Sugestão |
|---|---|---|
| Leitura de contexto `f2 + f5` repetida 3 vezes | `:337-342`, `:470-471`, `:515-520` | `ctx_from_fields(f)` |
| Regex de chave JSON em `tool_paths` e `tool_command` | `:691-693`, `:705-708` | Um `_json_str_values(args, keys)` |
| Contagem por estado repetida | `update_chips` `:2564-2573`, `update_details` `:2798-2805` | `count_states(rows)` |
| Monta `meta` + item de Auto-Run em dois lugares | `autorun_candidates` `:2529`, `start_autorun` `:3148-3155` | Reusar `autorun_candidates` |

### Problemas críticos

Nenhum.

### Recomendações

R3, R4, R5 e as duas abaixo:

| # | Recomendação |
|---|---|
| RM1 | Testes em `unittest` ou `pytest` simples ao migrar para o CI (hoje são scripts com `assert`); não precisa reescrever: basta o runner checar `exit code` |
| RM2 | Linha no topo de `reviews/audit-plan-full.md`: "Auditoria do script original (302 linhas). Ver `audit-full-v0.9.0.md`." |

### Detalhes do veredito

- **Higiene**: boa para projeto de um arquivo.
- **Reprodutibilidade**: build depende de versão flutuante do PyInstaller; isso também muda o perfil de falso positivo em antivírus.

---

## 7. Production Readiness

**Veredito**: APPROVE WITH CHANGES

### Análise de modos de falha

| Falha | Probabilidade | Efeito | Mitigação atual | Lacuna |
|---|---|---|---|---|
| `agy` devolve sucesso em formato diferente do esperado | Média (formato nunca visto) | Handoff falso `ok` | `parse_agy_output` tolerante | C1 |
| `agy` é `.cmd` | Desconhecida | `--mode plan` descartado | nenhuma | C2 |
| Usuário fecha no meio do Auto-Run | Média | Sessão sem registro, repetição, cota | nenhuma | C3 |
| `%LOCALAPPDATA%` sem escrita | Baixa | Estado em memória; Auto-Run quebra | aviso ao marcar | R1 |
| Antigravity escrevendo durante leitura | Alta (uso normal) | Leitura parcial ou `BUSY` | `mode=ro`, `timeout=2`, cache por `mtime` | B6 não verificado |
| Glifos MDL2 errados | Média | Ícones trocados | modo Unicode e `AGY_ICONS` | conferir no Windows |
| DPI 125–150%, vários monitores | Média | Janela fora da área útil | cálculo testado, autoteste imprime área | conferir no Windows |
| Antivírus bloqueia `.exe` PyInstaller | Média | App não abre | SHA-256 publicado | assinatura (fora de escopo) |
| `gate.log` e `handoffs/` crescem | Certa, lenta | Disco | nenhuma | nice-to-have |
| `settings.json` corrompido por queda no meio da gravação | Baixa | Preferências voltam ao padrão em silêncio | `load_settings` tolera | R17 |

### Checklist de ambiente

| Item | Situação |
|---|---|
| Caminhos com acento (`C:\Users\Thomáz`) | `Path.as_uri()` codifica; SQLite decodifica **[Não verificado no Windows]** |
| Pasta base configurável | `ANTIGRAVITY_HOME` ✔ |
| Executável do `agy` configurável | `AGY_EXE` ✔ |
| Erro fatal | `gate.log` + aviso ✔ |
| Autoteste do `.exe` no CI | ✔ (`--selftest`, FTS5, área útil, HRESULT do DWM) |
| Testes funcionais no CI | ✘ (R3) |
| Rollback de versão | Releases antigas ficam disponíveis ✔ |

### Problemas críticos

C1 e C3 (compartilhados com Backend e UX). C2 entra aqui também como risco de segurança operacional.

### Recomendações

R3, R5, R9, R17 e:

| # | Recomendação |
|---|---|
| P1 | Roteiro do teste real (27/10 ou depois): lote de **1** sessão, simulação desligada; conferir no `gate.log` a saída bruta; só depois um lote maior |

### Detalhes do veredito

- **Pronto para uso como leitor/curador**: sim.
- **Pronto para Auto-Run real**: depois de C1–C3.
- **Observabilidade**: boa para um app local (log, autoteste, notificações com `Abrir log`).

---

## 8. DX Engineer

**Veredito**: APPROVE WITH CHANGES

O usuário do app é desenvolvedor (usa o Antigravity e o `agy`). A lente avaliou a superfície de linha de comando, configuração e mensagens.

### Auditoria de mensagens de erro

| Mensagem | Diz o quê? | Diz o próximo passo? | Avaliação |
|---|---|---|---|
| "Não encontrei o agy. Confira se `agy --help` funciona no PowerShell, ou defina AGY_EXE…" | ✔ | ✔ | Boa |
| "⚠ erro ao carregar — ver {LOG_FILE}" | ✔ | ✔ | Boa |
| "N aviso(s) ao ler os bancos… [Abrir log]" | ✔ | ✔ | Boa |
| "Cota do modelo esgotada (volta em …)" | ✔ | ✔ | Boa |
| "saída sem JSON reconhecível: …" (200 caracteres) | ✔ | ✘ | Acrescentar "veja gate.log" e logar a saída inteira |
| "O estado não pôde ser salvo em disco…" | ✔ | ✘ | Dizer qual pasta e por quê |
| `--selftest` grava `OK`/`FALHA: tipo: msg` | ✔ | n/a | Boa para CI |

### Jornada do desenvolvedor

| Etapa | Situação |
|---|---|
| Rodar do código | `python AntigravityGate.py` ✔ |
| Descobrir opções | Só lendo README/docs; sem `--help` (R15) |
| Apontar para outra pasta | `ANTIGRAVITY_HOME` ✔ |
| Testar sem Windows | `tests/run_all.sh` com Xvfb ✔ |
| Inspecionar bancos sem expor conteúdo | `tools/inspect_*.py` ✔ |
| Publicar versão | `__version__` + CHANGELOG + tag; CI confere ✔ |
| Gerar `.exe` local | `.bat` ✔ (exige copiar o `.bat` para a raiz) |

### Problemas críticos

Nenhum.

### Recomendações

| # | Recomendação |
|---|---|
| X1 (= R15) | `--help` com flags e variáveis de ambiente |
| X2 (= R8) | Precedência clara de `AGY_ROT_TOKENS` sobre a tela |
| X3 | `packaging/build_exe.bat` resolver a raiz sozinho (`cd /d "%~dp0.."`) em vez de pedir cópia |
| X4 | Mensagem de saída inesperada do `agy` apontar para `gate.log` e logar a saída completa |

### Detalhes do veredito

- **Configurabilidade**: adequada, mas invisível no app.
- **Diagnóstico**: bom (log, autoteste, ferramentas de inspeção).

---

## 9. Performance Engineer

**Veredito**: APPROVE

### Orçamento de recursos

| Recurso | Medida/estimativa | Situação |
|---|---|---|
| Exportação completa | 6000 passos, 37 MB em 0,5 s (medição do projeto, sintética) | ✔ |
| Carga | `session_metrics` lê só `COUNT`, últimos 5 passos tipo 15 e primeiros passos; cache por `(caminho, mtime_ns, tamanho)` | ✔ |
| Ícones | 16 ícones a 24 px em 0,38 s **[Verificado]**; a 16 px, cerca da metade **[Inferência]** | Aceitável; ver D3 |
| `poll` | `after(100)` permanente | Desprezível |
| Spinner | `after(70)` só enquanto ocupado | ✔ |
| Memória em sessão longa | `METRICS_CACHE` ganha uma entrada por mudança de `mtime` e nunca despeja | Desprezível (tuplas pequenas) |
| Suíte de testes | 31 s | ✔ |

### Análise de caminho quente

| Caminho | Frequência | Custo | Observação |
|---|---|---|---|
| `set_status` | a cada 5 sessões durante a carga, e em toda ação | `iter_sessions` com ~3 chamadas Tcl por linha | Árvore vazia durante a carga; depois O(n) |
| `update_actions` | a cada mudança de seleção | `autorun_candidates` O(n) em Python | Leve |
| `run_search` | Enter na busca | FTS na thread da UI, até 2 s se o banco estiver travado | R6 |
| `populate` | ordenar/buscar/limites | Recria a árvore | Leve para centenas de sessões |

### Problemas críticos

Nenhum.

### Recomendações

| # | Recomendação |
|---|---|
| PF1 (= R6) | FTS em worker |
| PF2 | Despejo simples em `METRICS_CACHE`: ao fim de `scan_source`, descartar chaves de caminhos que não estão mais em `db_files` |
| PF3 | `iter_sessions` lê `values` duas vezes por linha (`is_session` + `cid_of`); guardar `iid → cid` em `populate` |

### Detalhes do veredito

- **Responsividade**: boa; o padrão worker + fila cobre o que pesa.
- **Sessões longas**: sem vazamento relevante.

---

## 10. Accessibility Engineer

**Veredito**: APPROVE WITH CHANGES

Limite da plataforma: Tk 8.6 expõe pouco ou nada a leitores de tela no Windows (NVDA, Narrador). Botões desenhados em `Canvas` não têm nome acessível. Isso não tem correção barata dentro do Tk; registro como restrição conhecida, não como defeito do app. As recomendações abaixo tratam teclado, tempo e contraste, que estão ao alcance.

### Navegação por teclado

| Ação | Teclado | Situação |
|---|---|---|
| Ir à busca | Ctrl+F | ✔ |
| Buscar / limpar | Enter / Esc | ✔ |
| Atualizar | F5 | ✔ |
| Navegar na tabela | setas, Shift/Ctrl | ✔ (nativo do Treeview) |
| Botões de ação | Tab, Espaço, Enter | ✔ (`takefocus=1`, anel de foco de 2 px) |
| Menu de contexto | — | ✘ só botão direito (R10) |
| Abrir/fechar detalhes | — | ✘ só mouse (R10) |
| Motivo de botão desabilitado | — | ✘ só no hover (R10) |
| Seletor de tema | setas, Enter, Esc | ✔ |
| Limites | Tab entre campos | ✔ |
| Notificação com Desfazer | Tab até o botão | ✔, mas some em 9 s (R11) |
| Confirmação do Auto-Run | Tab nos widgets nativos | ✔ |

### Checklist (equivalente ARIA para Tk)

| Item | Situação |
|---|---|
| Nome acessível dos botões | ✘ (limite do Tk) |
| Estado não só por cor | ✔ ícone + texto ("Aprovada", `⚠`, `‼`) |
| Contraste de texto ≥ 4,5:1 | ✔ em todos os temas (teste) |
| Foco visível | ✔ nos botões; nativo na tabela e campos |
| Tempo suficiente | ✘ notificação com ação (R11) |
| Tamanho de alvo | 34 px de altura escalados por DPI ✔ |
| Texto escala com DPI | ✔; sem zoom próprio |

### Problemas críticos

Nenhum.

### Recomendações

| # | Recomendação |
|---|---|
| A1 | `<Shift-F10>` e `<App>` abrem o menu de contexto na linha focada |
| A2 | Barra "Detalhes da sessão" focável, com Enter/Espaço |
| A3 | `Tooltip` também em `<FocusIn>`/`<FocusOut>` |
| A4 | Notificação com ação não expira com foco ou mouse em cima |
| A5 | Janelas do Auto-Run com o mesmo tratamento de foco do resto (D1) |

### Detalhes do veredito

- **Teclado**: cobre os fluxos principais; faltam três atalhos.
- **Leitor de tela**: fora do alcance do Tk 8.6.
- **Contraste**: verificado por teste em todos os temas.

---

## Anexo: verificações executadas

| # | Verificação | Resultado |
|---|---|---|
| 1 | `tests/run_all.sh` com Python 3.12.3, Tk 8.6, Xvfb | 15/15 ok |
| 2 | `StateStore` em memória usado por outra thread | `ProgrammingError: SQLite objects created in a thread can only be used in that same thread` |
| 3 | `redact` em 7 amostras | vazam: `sk_live_`, `postgres://user:senha@`, JWT, `xoxb-`, `Authorization: Basic`; mascaram: `sk-ant-`, `api_key = '…'` |
| 4 | `build_agy_args` | prompt no índice 2 contém `\n`; `--mode` no índice 5 |
| 5 | `render_icon` de 16 ícones a 24 px | 0,38 s |
| 6 | `parse_agy_output('{"conversation_id":"x"}', "")` | `ok = True` |
| 7 | `limits_from_settings` com `AGY_ROT_TOKENS=90k` e preset salvo `amplo` | devolve `personalizado, 90000, 135000` |
