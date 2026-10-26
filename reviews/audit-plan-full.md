# Auditoria Full Spectrum: AntigravityGate.py

**Data**: 2026-10-26
**Modo**: Repo (arquivo único, fora de git). Revisão de código, não de plano.
**Fonte**: `AntigravityGate.py` (302 linhas, Python 3 + Tkinter + sqlite3), enviado como anexo.
**Lentes executadas**: 8/10
**Lentes puladas**:
- Frontend Engineer: sem React/TS/CSS.
- Structural Engineer: arquivo único, sem módulos. Os pontos estruturais relevantes entram na lente Repo Maintainer.

**Método e limites**
- Li o arquivo inteiro. `py_compile` passa.
- Testei isoladamente quatro suspeitas: preview via `str(row)`, `unquote(None)`, `last_mod[:19]` com int, contraste dos botões. Os resultados estão marcados **[Verificado]**.
- Não executei o app: ele depende de Windows, `C:\Users\Thomáz\.gemini` e Tk com display. O schema real dos `.db` do Antigravity não foi visto. Tudo que depende dele está marcado **[Não verificado]**.
- Os sub-skills `audit-as-*` são calibrados para Orbit (Tauri/React/Rust). Apliquei o critério de cada lente diretamente ao código Python em vez de carregar os 8 skills.

---

## Veredito Mestre: APPROVE WITH CHANGES

Como **inspetor somente-leitura** de sessões, o script funciona e é compacto. Como **gestor** ("Aprovar Projeto", "Auto-Run", status "Aprovada"), ele ainda não existe. Esses botões exibem mensagens de sucesso sem executar nada, e todas as linhas mostram "[Aprovada]" fixo. Isso é o pior defeito: a UI afirma estados falsos.

Em segundo lugar vêm tudo-na-thread-da-UI (congela com muitas sessões) e conexões SQLite sem fechamento nem modo somente-leitura sobre bancos vivos. A exportação usa heurística lossy e grava conteúdo de conversas na Área de Trabalho, que pode estar sincronizada com OneDrive.

## Veredito por Lente

| # | Lente | Veredito | Críticos | Recomendações |
|---|-------|----------|----------|---------------|
| 1 | Design Engineer | APPROVE WITH CHANGES | 1 | 5 |
| 2 | UX Engineer | NEEDS REWORK | 3 | 6 |
| 3 | Frontend Engineer | Pulada | – | – |
| 4 | Backend Engineer (Python/SQLite) | NEEDS REWORK | 4 | 6 |
| 5 | Structural Engineer | Pulada | – | – |
| 6 | Repo Maintainer | APPROVE WITH CHANGES | 0 | 7 |
| 7 | Production Readiness | NEEDS REWORK | 3 | 5 |
| 8 | DX Engineer | APPROVE WITH CHANGES | 1 | 4 |
| 9 | Performance Engineer | NEEDS REWORK | 2 | 5 |
| 10 | Accessibility Engineer | APPROVE WITH CHANGES | 1 | 4 |

## Todos os Problemas Críticos (Must Fix)

Deduplicados e ordenados por severidade.

| # | Problema | Lente(s) | Linhas | Impacto | Correção |
|---|----------|----------|--------|---------|----------|
| K1 | `bulk_action` e `run_autonomous` são stubs que exibem sucesso ("aplicada com sucesso… log gravado no banco"). Nada é aplicado nem gravado. | UX, Backend, Prod, DX | 216-225 | A UI mente. O usuário acredita ter aprovado ou disparado automação. | Desabilitar os botões (`state=DISABLED`) e rotular "em breve", ou implementar de verdade (ver Marco 3). Nunca exibir sucesso sem efeito. |
| K2 | Status `[Aprovada]` fixo em toda sessão. Não existe armazenamento de estado. | UX, Backend | 211 | Informação falsa em 100% das linhas. | Remover o texto ou ler de um `gate_state.db` próprio (pendente/aprovada/arquivada). |
| K3 | Varredura, `COUNT(*)` e leitura de blobs de todos os `.db` na thread da UI. `os.walk` recursivo em `.gemini` roda no `__init__` e a cada troca de tema. | Perf, Prod, UX | 28, 55, 136-140, 162-177 | A janela só aparece depois da carga. O congelamento cresce com N sessões e MB de banco. | Scan em thread de trabalho (`threading` + `queue` + `after`). Cache por `(path, mtime, size)`. `COUNT(*)` sob demanda. |
| K4 | Conexões sem `try/finally` e abertas em modo leitura/escrita sobre bancos que o Antigravity pode estar usando. | Backend, Prod | 127-131, 162-175, 273-294 | Exceção deixa o handle aberto (no Windows, bloqueia o arquivo). Abrir em rw pode criar `-journal`/`-wal`. `database is locked` é engolido. | `sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=2)` dentro de `contextlib.closing`. |
| K5 | Três `except Exception: pass` silenciosos (JSON de projetos, summaries DB, DB por sessão). | Backend, Prod, DX | 121-122, 132-133, 176-177 | Falha vira lista vazia ou sem projeto, sem pista da causa. | `logging` em arquivo, contador de erros e barra de status ("3 bancos falharam, ver log"). |
| K6 | Crashes não tratados em `open_selected` e `load_data`. **[Verificado]** `urllib.parse.unquote(None)` gera `TypeError`; `s.get('workspace_uris','…')` devolve `None` se a coluna for NULL. `last_mod[:19]` com int gera `TypeError` **[Não verificado]** se o schema guarda epoch. | Backend, Prod | 200, 254-256 | Exceção em callback Tk fica só no stderr (invisível em `pythonw`). O duplo clique "não faz nada". `load_data` pode abortar inteiro. | `s.get(k) or default`. Normalizar `last_mod` com `str()` ou conversão de epoch. |
| K7 | Exportação: pasta fixa `~/Desktop` e conteúdo de conversa em texto puro. | Prod, Backend, UX | 15, 258-260 | Com OneDrive, a Área de Trabalho muda de caminho (`open()` falha) ou sincroniza conversas (podem conter chaves e segredos) para a nuvem. Sobrescreve sem avisar. | `filedialog.asksaveasfilename` ou pasta `exports/` local. Nome com data/hora. Aviso de privacidade. |
| K8 | Extração do "Diálogo Rico" é regex sobre dados protobuf. Perde e corrompe conteúdo. | Backend, UX | 169-174, 276-293 | Ver detalhes na lente Backend. | Decodificar o protobuf (ver Marco 4). Enquanto isso, rotular como "melhor esforço". |

## Preocupações Transversais

| Preocupação | Sinalizada por | Causa raiz | Correção unificada |
|-------------|----------------|------------|--------------------|
| UI afirma estados que não existem (K1, K2) | UX, Backend, DX, Prod | UI desenhada antes da camada de estado/ações | Criar `gate_state.db` próprio. Desabilitar o que não existe. |
| Falhas silenciosas (K5, K6, K8) | Backend, Prod, DX | `except Exception: pass` e sem log | Camada de log + status bar + erros por sessão visíveis. |
| Tudo na thread da UI | Perf, UX, Prod | `load_data` e export síncronos | Worker thread + fila + indicador de progresso. |
| Caminhos e plataforma fixos | Prod, Repo, Backend | `C:\Users\Thomáz`, `~/Desktop`, `os.startfile` | `Path.home()/".gemini"`, variável de ambiente `ANTIGRAVITY_HOME`, fallback `xdg-open`/`open`. |
| Conexões SQLite mal gerenciadas (K4) | Backend, Perf, Prod | Sem context manager nem modo `ro` | Helper único `open_ro(path)`. |
| Troca de tema reconstrói dados e deixa widgets antigos (D1) | Design, Perf, UX | `toggle_theme` chama `load_data`, não reestiliza widgets | Reestilizar widgets existentes. Não recarregar dados. |

## Todas as Recomendações

| # | Recomendação | Lente | Linhas | Correção |
|---|--------------|-------|--------|----------|
| R1 | Tema só reestiliza `ttk`/root. Frames, labels e `tk.Button` mantêm as cores antigas. | Design | 52-55, 59-75 | Guardar widgets e chamar `.configure(bg=…)`. Ou usar só `ttk` com styles. |
| R2 | Duplo clique em linha de projeto dispara popup "Clique numa conversa" em vez de expandir. Clique em cabeçalho ou área vazia reexporta a seleção antiga. | UX | 101, 233-236 | `iid = tree.identify_row(e.y)`. Ignorar se vazio. Em pai, só alternar `open`. |
| R3 | Sem botão/atalho de atualizar. Hoje só alternar o tema recarrega os dados. | UX | 52-55 | Botão "Atualizar" e `F5`. |
| R4 | Sem busca, filtro ou ordenação por coluna. "Tamanho" é string ("123 KB ⚠️"), então não ordena. | UX | 83, 193 | Guardar número em `values` e formatar na exibição. Campo de busca. `heading(command=…)`. |
| R5 | Matching de projeto por substring: pasta-pai casa filhos de outro projeto. A ordem do dict decide. | Backend | 182-185 | Normalizar URIs, comparar por prefixo de caminho com separador e preferir o match mais longo. |
| R6 | `projectResources` ou `gitFolder` `None` derruba o arquivo inteiro do projeto. | Backend | 117-120 | `(d.get('projectResources') or {})`, `res.get('gitFolder') or {}`. |
| R7 | `len(f) == 39` como detector de UUID. Frágil. | Backend | 138 | Regex `^[0-9a-f]{8}-…\.db$`. |
| R8 | Mesmo `cid` em vários diretórios (backup, cópias): vale o último `walk`. | Backend | 135-140 | Preferir o mais recente por `mtime`. Marcar duplicata. |
| R9 | Preview via `str(row)` usa o `repr` de bytes. **[Verificado]**: "Olá mundo" vira `'xa1 mundo, como vai voc'` (escapes `\xc3\xa1` quebram acentos). | Backend | 171 | Decodificar `bytes` antes (`errors="replace"`) e ler só colunas de texto. |
| R10 | Extração sem `ORDER BY`, sem papel (usuário/assistente) e sem timestamp. | Backend | 276 | `ORDER BY` pela coluna de índice/tempo (descobrir pelo schema) e cabeçalho por papel. |
| R11 | Escrita incremental do export sem barra de progresso, em thread da UI. | Perf | 259-294 | Thread + `ttk.Progressbar` indeterminado. |
| R12 | Constantes de caminho no topo e `Thomáz` fixo. | Prod | 12-15 | `Path.home()`, env var, `--base-dir` por `argparse`. |
| R13 | `os.startfile` só existe no Windows. Em outro SO, `AttributeError` vira "Não foi possível exportar", mentindo sobre a causa. | Prod | 296-298 | Helper `open_file()` por plataforma. Separar erro de escrita de erro de abertura. |
| R14 | `import subprocess` não usado. `messagebox.print = print` (linha 224) é lixo que altera módulo global. Variável `dirs` não usada. | Repo | 5, 224, 136 | Remover. |
| R15 | Classe única mistura varredura, parsing, estado e UI. Sem testes possíveis. | Repo | 17-298 | Separar `scan.py`, `export.py`, `ui.py`. `@dataclass Session`. |
| R16 | Cabeçalho "Tamanho (KB)" com valor já "123 KB". Limiar 1500 KB fixo e sem explicação. | Repo, UX | 83, 193 | Constante `ROT_KB = 1500` configurável. Rótulo coerente. |
| R17 | Segredos em export: sem redação de chaves/tokens. | Prod | 276-293 | Opção de redigir padrões (`sk-…`, `AIza…`, `Bearer …`). |
| R18 | Sem DPI awareness no Windows: texto borrado em telas escaladas. | Design | 17-21 | `ctypes.windll.shcore.SetProcessDpiAwareness(1)` no início. |
| R19 | Barra de rolagem empacotada depois da árvore com `expand`: pode ser cortada ao reduzir a janela. | Design | 98-99 | Empacotar a barra antes (`side=RIGHT`), depois a árvore. |
| R20 | Sem `minsize`, sem barra de status, sem contador de erros. | DX | 21 | `self.minsize(900,400)` e `Label` de status. |
| R21 | Sem atalhos: Enter não exporta, sem `Ctrl+F`/`F5`/`Ctrl+C`. | A11y | 101 | `bind("<Return>")`, `bind("<F5>")`. |
| R22 | Contraste dos botões. **[Verificado]** branco sobre `#28a745` = 3,13:1 e sobre `#17a2b8` = 3,04:1 (abaixo de 4,5:1 para texto pequeno). Aceitável: `#007acc` 4,51 e `#005a9e` 7,10. | A11y, Design | 65, 68 | Escurecer para `#1e7e34` (verde) e `#117a8b` (ciano). |

---

# Relatórios por Lente

---

## 1. Design Engineer

**Veredito**: APPROVE WITH CHANGES

**Arquivos revisados**

| Arquivo | Escopo |
|---------|--------|
| AntigravityGate.py | `apply_theme` (30-50), `create_widgets` (57-101), cores inline |

**Problemas críticos**

| # | Problema | Linhas | Correção |
|---|----------|--------|----------|
| D1 | `toggle_theme` só atualiza `self` e o `ttk.Style`. Os widgets criados em `create_widgets` (frames, label, quatro `tk.Button`) guardam as cores do tema anterior. A alternância fica metade escura, metade clara. | 52-55 | Ver R1. |

**Recomendações**

| # | Recomendação | Linhas |
|---|--------------|--------|
| D2 | Cores hex repetidas e inline (`#28a745`, `#17a2b8`, `#ffffff`). Falta um dicionário de tokens por tema. | 65, 68, 74 |
| D3 | `ttk.Scrollbar` em tema `clam` não herda o modo escuro. Configurar `style.configure("Vertical.TScrollbar", …)`. | 95 |
| D4 | Ícones de emoji (🚀📁💬⚠️) dependem da fonte do sistema. `⚠️` com seletor de variação pode renderizar em largura irregular na árvore. | 20, 62, 193, 208-211 |
| D5 | `rowheight=28` e fontes em pontos fixos: sem escala com DPI (ver R18). | 48-49 |

**Conformidade com design system**: não há sistema. Cores, fontes (`Segoe UI`) e espaçamentos são literais. Sugestão: `THEMES = {"dark": {...}, "light": {...}}`.

**Matriz de estados visuais**

| Elemento | Normal | Hover | Foco | Desabilitado | Escuro/Claro |
|----------|--------|-------|------|--------------|--------------|
| Botões `tk.Button` | Sim | Padrão do SO | Padrão do SO | **Ausente** (necessário para K1) | Falha em D1 |
| Treeview linhas | Sim | – | Sim | – | Sim |
| Treeview cabeçalho | Sim | Padrão `clam` | – | – | Sim |
| Scrollbar | Sim | – | – | – | **Não temática** |
| Vazio (sem sessões) | **Ausente** | – | – | – | – |

**Detalhes do veredito**
- Fidelidade de tokens: baixa (literais).
- Cobertura de estados: faltam desabilitado e vazio.
- Modo escuro: parcialmente quebrado (D1, D3).
- Animação: n/a.
- Consistência: razoável. Paleta VS Code coerente.

---

## 2. UX Engineer

**Veredito**: NEEDS REWORK (pelo K1/K2: feedback falso)

**Mapa da jornada**

| Passo | Ação | Resultado real | Problema |
|-------|------|----------------|----------|
| 1 | Abrir o app | Janela só aparece após varrer tudo | Congelamento (K3), sem indicador |
| 2 | Ver lista | Todas as sessões marcadas "[Aprovada]" | Estado falso (K2) |
| 3 | Selecionar projeto e "Aprovar Projeto" | Popup de sucesso, nada muda | Feedback falso (K1) |
| 4 | "Auto-Run Aprovadas" | Popup diz que disparou automação, nada roda | Feedback falso (K1) |
| 5 | Duplo clique em projeto | Popup "Clique numa conversa" | Impede expandir (R2) |
| 6 | Duplo clique em sessão | Gera `.md` na Área de Trabalho e abre | Sem progresso. Falha se OneDrive (K7) |
| 7 | Dados mudaram no disco | Só reabre o app ou alterna tema | Sem atualizar (R3) |

**Problemas críticos**
1. K1 e K2, acima.
2. Ação destrutiva potencial sem confirmação: quando "Auto-Run" for implementado, o botão verde primário não pede confirmação nem mostra o que será executado.
3. Falha de exportação mostra `Não foi possível exportar: {e}` bruto, sem ação sugerida.

**Recomendações**
1. Busca e filtro por texto e projeto (R4).
2. Ordenação por coluna (R4).
3. Menu de contexto: copiar UUID, abrir pasta do banco, exportar, aprovar.
4. Estado vazio: "Nenhuma sessão em {BASE_DIR}. Verifique o caminho."
5. Mostrar o caminho do `.md` gerado após o export, com botão "Mostrar na pasta".
6. Persistir tema escolhido entre execuções.

**Consistência de interação**: dois caminhos para exportar (botão e duplo clique) com regras diferentes de seleção (R2). Botão "Aprovar Projeto" permite selecionar uma sessão, não só um projeto, sem explicar o escopo.

**Detalhes do veredito**: o modelo mental "gestor com aprovação" só existe na aparência. Corrigir K1/K2 é pré-requisito para qualquer outra melhoria de UX.

---

## 3. Frontend Engineer

**Pulada**: sem React, TypeScript ou CSS. A camada de UI é Tkinter e foi coberta por Design, UX e A11y.

---

## 4. Backend Engineer (Python/SQLite)

**Veredito**: NEEDS REWORK

**Análise de caminhos de erro**

| Ponto | Linhas | O que acontece em falha | Avaliação |
|-------|--------|--------------------------|-----------|
| Leitura de JSON de projeto | 111-122 | `pass` silencioso. Se `projectResources` for `None`, perde o projeto inteiro | Ruim (K5, R6) |
| Leitura de `conversation_summaries` | 126-133 | `pass`. Tabela ausente, banco bloqueado ou corrompido = lista sem títulos | Ruim (K5) |
| Banco por sessão | 161-177 | `pass`. `c2.close()` pulado | Ruim (K4, K5) |
| `last_mod[:19]` | 200 | `TypeError` se não for `str` **[Não verificado]** | Pode abortar `load_data` |
| `unquote(None)` | 254 | **[Verificado]** `TypeError` fora do `try` | Crash em callback |
| Export | 259-298 | `try` amplo cobre escrita e abertura. A conexão `conn` não fecha se a leitura falhar | Parcial (K4) |

**Auditoria de ciclo de vida de recursos**

| Recurso | Aberto em | Fechado em | Problema |
|---------|-----------|------------|----------|
| `sqlite3` summaries | 127 | 131 | Sem `finally` |
| `sqlite3` por sessão (`c2`) | 162 | 175 | Sem `finally`. N conexões sequenciais |
| `sqlite3` export (`conn`) | 273 | 294 | Sem `finally` |
| Arquivo `.md` | 260 | `with` | OK |
| `os.walk` ×2 | 136, 246 | – | Varredura completa repetida |

**Problemas críticos**
- K4, K5, K6, K8.
- **K8 em detalhe** (extração do diálogo):
  1. `seen` é global ao export: um texto legítimo repetido (prompt reutilizado, saída idêntica de ferramenta) some das interações seguintes (285-288).
  2. Filtro por substring (`.gemini`, `user_uploaded`, `google.protobuf`, `editor_transcript`) descarta qualquer trecho que **mencione** esses termos, inclusive resposta legítima sobre caminhos `.gemini` (285).
  3. **[Verificado]** bytes de prefixo de tamanho protobuf que são imprimíveis colam no início do texto (`b"\x12H…"` gera `"HResposta do assistente…"`).
  4. `errors='ignore'` descarta bytes inválidos e quebra acentos e emojis (282).
  5. Se os blobs forem comprimidos (zlib/gzip), nada é extraído e o usuário vê um relatório vazio **[Não verificado]**.
  6. Sem `ORDER BY`, sem papel, sem timestamp: a ordem "histórico" não é garantida (276).
  7. A classe de caracteres inclui `*#+=<>`, aceitando ruído binário como texto.
- Modo de abertura: `sqlite3.connect(path)` abre em leitura/escrita. Com Antigravity ativo, isso pode criar arquivos auxiliares ou disputar locks. Use `mode=ro`. Se os bancos usam WAL, `mode=ro` exige acesso ao `-shm`. **[Não verificado]** se há WAL.

**Recomendações**
1. Helper único:
```python
import sqlite3
from contextlib import closing

def open_ro(path, timeout=2.0):
    uri = "file:" + urllib.parse.quote(path.replace("\\", "/")) + "?mode=ro"
    return closing(sqlite3.connect(uri, uri=True, timeout=timeout))
```
2. Leitura nula-segura: `s.get('workspace_uris') or 'Não registado'` (e igual para todo `.get(k, default)` que pode receber `None`).
3. Normalizar `last_mod`: aceitar `str` ISO e `int`/`float` epoch. Guardar `datetime` e formatar só na exibição, em um fuso único.
4. Inspecionar o schema real (`PRAGMA table_info(steps)`) e decodificar o protobuf (por exemplo `blackboxprotobuf`, ou `.proto` se existir). **[Não verificado]** o formato. Antes de investir, rode `PRAGMA table_info(steps)` e `SELECT typeof(col)` em uma sessão.
5. Dedup por `(índice do passo, texto)`, não global.
6. Remover filtros por substring ou aplicá-los apenas a campos de metadados.

**Detalhes do veredito**: lógica de leitura é simples e não escreve em banco alheio. O risco real é de robustez e de fidelidade do dado exportado.

---

## 5. Structural Engineer

**Pulada**: arquivo único, sem novos módulos. Ver R15 na lente Repo Maintainer.

---

## 6. Repo Maintainer

**Veredito**: APPROVE WITH CHANGES

**Checklist de convenções**

| Item | Estado |
|------|--------|
| Sem imports não usados | Falha: `subprocess` (5) |
| Sem variáveis não usadas | Falha: `dirs` (136, 246) |
| Sem monkeypatch de módulo | Falha: `messagebox.print = print` (224) |
| Constantes nomeadas | Parcial: caminhos sim, `1500` e `39` literais |
| Docstrings / tipos | Ausentes |
| Testes | Ausentes |
| Separação de responsabilidades | Ausente: UI, dados e export numa classe |
| Idioma consistente | OK (PT-BR na UI, comentários mistos) |
| `if __name__ == "__main__"` | OK |

**Oportunidades de reuso**
- Abrir conexão SQLite (3 lugares) → `open_ro()`.
- Varredura `os.walk` (2 lugares: 136 e 246) → índice único `cid → path` já existente em `self.db_files`. O fallback da linha 244-250 é redundante.
- Leitura de campos nulos → helper `g(row, key, default)`.

**Recomendações**: R14, R15, R16. Estrutura sugerida (sem inflar): `antigravity_gate/{scan.py, export.py, state.py, ui.py}` e um `Session` dataclass. Só vale se for crescer além do Marco 3. Até lá, duas funções de módulo (`scan_sessions()`, `export_session()`) já separam UI de dados e destravam testes.

**Detalhes do veredito**: nada bloqueante. Higiene de código, mais pontos que seriam fáceis de testar se a lógica saísse da classe Tk.

---

## 7. Production Readiness

**Veredito**: NEEDS REWORK

**Análise de modos de falha**

| Falha | Probabilidade | Efeito atual | Mitigação |
|-------|---------------|--------------|-----------|
| Banco bloqueado pelo Antigravity | Alta | Sessão some ou fica sem metadados, sem aviso | `timeout`, erro visível, tentar de novo |
| Área de Trabalho redirecionada (OneDrive) | Alta no Windows | `FileNotFoundError` ou upload das conversas para a nuvem | Escolher pasta (K7) |
| Usuário Windows diferente de `Thomáz` | Média | Pasta não existe, janela abre vazia sem explicação | `Path.home()`, estado vazio claro |
| Milhares de sessões / bancos grandes | Média | Congelamento (K3) | Thread + cache |
| Schema do Antigravity muda | Média | Exceções engolidas, lista vazia | Checar versão/colunas, log, mensagem |
| Segredos em conversas exportadas | Média | Texto puro em disco | Aviso + redação (R17) |
| Arquivo `.md` já aberto em outro app | Baixa | `PermissionError` genérico | Nome único com timestamp |

**Checklist de ambiente**

| Item | Estado |
|------|--------|
| Caminhos configuráveis | Não |
| Multiplataforma | Não (`os.startfile`) |
| Logs | Não |
| Tratamento de erros visível | Não |
| Dependências | Só stdlib (bom). Requer Tk com suporte a emoji |
| Empacotamento | Sem; rodar com `pythonw` esconde tracebacks |
| Versão de Python | Não declarada. Compatível com 3.8+ pelo que vi |

**Problemas críticos**: K5, K7 e o conjunto de falhas por ambiente acima.

**Recomendações**
1. Logging em `%LOCALAPPDATA%\AntigravityGate\gate.log`.
2. Estado vazio explicativo e mensagem com o caminho tentado.
3. `README` curto com requisitos, caminho esperado, o que o app lê e o que grava.
4. Fazer backup/cópia antes de qualquer ação futura que escreva em bancos do Antigravity (hoje não há escrita, mantenha assim).
5. Exportar para `exports/` e deixar claro que contém conteúdo sensível.

---

## 8. DX Engineer

**Veredito**: APPROVE WITH CHANGES

**Auditoria de mensagens de erro**

| Mensagem | Linhas | Problema | Melhor |
|----------|--------|----------|--------|
| "Não foi possível exportar: {e}" | 298 | Exceção crua, mistura erro de escrita com erro de abertura | "Falha ao gravar {out_md}: {e}. Escolha outra pasta." |
| "Ação '{action_type}' aplicada com sucesso…" | 221 | Falsa | Ver K1 |
| (silêncio) | 121, 132, 176 | Sem mensagem | Barra de status + log (K5) |
| "Clique numa conversa…" | 235 | Interrompe o gesto de expandir | Não mostrar; apenas expandir |

**Jornada do desenvolvedor**: para entender por que uma sessão não aparece, o usuário precisa depurar o código. Falta um modo `--verbose` ou aba de diagnóstico (arquivos achados, erros, tempo de scan).

**Problemas críticos**: K1 (mensagem enganosa).

**Recomendações**
1. `argparse`: `--base-dir`, `--export-dir`, `--log-level`.
2. Janela "Sobre/Diagnóstico": caminhos usados, contagem de bancos, erros.
3. Botão "Copiar UUID" e "Abrir pasta do banco" (úteis para depurar sessões).
4. Rótulos honestos ("Exportar relatório (melhor esforço)").

---

## 9. Performance Engineer

**Veredito**: NEEDS REWORK

**Orçamento de recursos**

| Operação | Custo | Frequência | Observação |
|----------|-------|------------|------------|
| `os.walk(BASE_DIR)` | O(arquivos em `.gemini`) | Início + cada troca de tema | Percorre também diretórios que não interessam |
| Abrir banco por sessão | N × conexão | Início + cada troca de tema | Sem cache |
| `SELECT COUNT(*) FROM steps` | O(linhas) por banco | Idem | Já existe `step_count` no summaries |
| `SELECT * FROM steps LIMIT 3` + `str(row)` | Lê blobs | Só sem preview | Gera repr de bytes grandes |
| Export | O(tamanho do banco) | Por ação | Regex sobre cada coluna, `seen` cresce sem limite |
| `urllib.parse.unquote` + loops de projeto | O(sessões × projetos) | Início | Aceitável |

**Análise de caminho quente**: o caminho crítico é a abertura da janela (K3). A troca de tema repete todo o scan sem necessidade.

**Problemas críticos**
1. K3.
2. `toggle_theme` → `load_data` (55): custo total para mudar cor. Remover.

**Recomendações**
1. Cache em memória/disco por `(path, mtime, size)`; revalidar só o que mudou.
2. Preferir `step_count` do summaries. Contar no banco só quando o usuário abrir a sessão.
3. Limitar `os.walk` aos diretórios conhecidos (`conversations`, `brain` etc. — **[Não verificado]** estrutura) ou parar de descer em pastas como `node_modules`.
4. Export em streaming com thread e botão Cancelar. Limite configurável do `seen` ou dedup por passo.
5. Medir: registrar tempo de scan no log para validar ganhos.

---

## 10. Accessibility Engineer

**Veredito**: APPROVE WITH CHANGES

(Tkinter tem suporte limitado a leitores de tela; o foco abaixo é teclado, contraste e rótulos.)

**Percurso por teclado**

| Passo | Resultado |
|-------|-----------|
| Tab | Segue a ordem de criação: Auto-Run, Aprovar, Tema, Exportar. Como todos usam `pack(side=RIGHT)`, o foco anda da direita para a esquerda, contrário à leitura visual |
| Setas na árvore | Funcionam (nativo do `Treeview`) |
| Enter na árvore | **Não** exporta |
| Atalho de atualizar/buscar | Inexistente |
| Menu de contexto | Inexistente |

**Checklist ARIA**: n/a em Tk. Equivalentes: texto claro nos botões (sim), nomes acessíveis (texto dos botões), indicação por cor + texto (o aviso de Rot usa `⚠️` + `[Rot]`, bom).

**Problemas críticos**
1. Contraste insuficiente nos botões verde e ciano (R22): **[Verificado]** 3,13:1 e 3,04:1.

**Recomendações**
1. `bind("<Return>", …)` na árvore (R21).
2. Ordem de foco coerente com a ordem visual (criar os botões na ordem visual da esquerda para a direita, ou ajustar `takefocus`).
3. Atalhos documentados: `F5`, `Ctrl+F`, `Ctrl+E`.
4. Respeitar escala de fonte/DPI do sistema (R18).

---

# Plano de marcos (proposta, em ordem)

Cada marco é curto e fecha com um critério visível.

| Marco | Escopo | Fecha quando |
|-------|--------|--------------|
| M1 · Honestidade e robustez | K1, K2, K4, K5, K6, R6, R7, R9, R14 | Nenhum popup afirma algo que não ocorreu. App abre mesmo com bancos bloqueados ou NULLs, e o log mostra os erros. |
| M2 · Velocidade | K3, R3, R11, tema sem recarregar (R1) | Janela aparece em <1 s. Scan em segundo plano com barra de status. Alternar tema não varre disco. |
| M3 · Gestão de verdade | `gate_state.db` próprio, aprovar/arquivar, filtros, ordenação, atualizar, copiar UUID, abrir pasta (R2, R4, R13) | Aprovar uma sessão persiste e sobrevive ao reiniciar. |
| M4 · Exportação fiel | K7, K8, R10, R17 | Export em pasta escolhida, ordem e papéis corretos, sem perda de acentos. Depende de ver o schema real. |

**Perguntas que decidem o rumo**
1. "Auto-Run Aprovadas": que comando ou automação deve disparar? Sem essa definição, deixe o botão desabilitado.
2. Isso entra no lugar de quê? Se o M3 for aberto como nova frente, diga qual outra frente pausa.
3. Para o M4, preciso do resultado de `PRAGMA table_info(steps)` e de `SELECT typeof(<coluna>)` de uma sessão pequena, sem conteúdo sensível.
