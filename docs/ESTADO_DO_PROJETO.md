# AntigravityGate: estado do projeto

Atualizado em 2026-10-27, versão **1.0.2** (publicada em 27/10: Release `v1.0.2`, PR two2dope/agy-gate#4; contém a 1.0.1 e a 1.0.2). Repositório próprio: `two2dope/agy-gate` (privado), separado do `zuvuya`. Ao retomar, leia só a seção "Snapshot".

## Snapshot

| | |
|---|---|
| **Feito** | 1.0.0 publicada. Antigravity restaurado no Windows (27/10: conversas de volta no remoto `dev-thomaz` e na busca do VS Code). Auditoria `reviews/audit-full-v1.0.0.md`. **1.0.2 publicada** (27/10; aprovada depois da retomada real `4c326dce` → `3723a6eb`; Release `v1.0.2`): 1.0.1 (crítico C1: retomada no projeto de origem; simulação conferida no Windows: `d:\Segurança`, `SMT1_WATCHDOG (--project)`) e 1.0.2 (faixa e dica de contexto como alerta em dois níveis; janelas do Auto-Run), com testes. Pacote visual: duas entregas do Stitch avaliadas (8 skins + `DESIGN.md`), caminho A decidido, tokens das 8 skins propostos com contraste conferido, decisões da 1.1 fechadas: `docs/PACOTE_VISUAL_1.1.md` |
| **Faltando** | 1.1: conferir M1a, M1b, M2 e M4a no Windows; M3 e o resto do M4. Retomada real de uma sessão **com** projeto: o `--project` só foi visto na simulação (a retomada real de 27/10 era de sessão sem projeto). Duas observações de 27/10 sem diagnóstico (editor vazio a cada `agy`; PowerShell piscando no remote control). Não verificado: escala 125–150%, status 6 e 7 |
| **Próximo passo único** | Baixar o `.exe` da branch (artefato do CI) e conferir no Windows a interface em Inter e os 3 conjuntos de ícones (Tema > Ícones): botões, faixa de alerta, lupa da busca, texto cortado |

## Pendências (backlog pós-1.0)

Em ordem de prioridade. Cada item vira uma 1.0.x com teste; nada entra sem decidir o que sai.

0. **Auditoria v1.0.0, crítico C2:** junctions (`antigravity-cli`, `antigravity-ide` → `antigravity`) aparecem como fontes "Backup/outros", com os dados vivos. Corrigir com `realpath` em `discover_sources`. Demais recomendações (R2–R17) na auditoria.
1. **1.1 — pacote visual** (decidido em 27/10: caminho A, evolução em Tk; aba "Em Revisão" vira "Aprovadas aguardando"; os 3 conjuntos de ícones ficam). Também decidido em 27/10: tema padrão "Dark Alloy" (paleta Obsidian, azul-preto, no lugar do Escuro), tabela padrão compacta, barra lateral aberta ao abrir. Plano e tokens das 8 skins em `docs/PACOTE_VISUAL_1.1.md`. Começa depois do merge da 1.0.2. Já entra:
   - **Ícone autoral do app** (`.ico` multi-tamanho 16–256 px para o `.exe`, a barra de tarefas e a barra de título). Hoje o `.exe` usa o ícone padrão do PyInstaller e a janela usa a pena do Tk. Fazer: arte própria → `packaging/app.ico` → `--icon` no PyInstaller → `iconbitmap`/`iconphoto` nas janelas.
   - **[Feito na branch: M1a, 27/10] Mais 3 conjuntos de ícones, com as fontes reais dentro do `.exe`:** Font Awesome Free (Solid, SIL OFL 1.1), Bootstrap Icons (MIT) e Material Icons (Apache 2.0), além dos atuais (Segoe MDL2, Unicode, sem ícones). Com Inter e JetBrains Mono, cerca de +2,5 MB no `.exe`; créditos de licença no Sobre; registro privado da fonte no Windows (`AddFontResourceExW`, `FR_PRIVATE`) e `--add-data` no PyInstaller. As três fontes podem ser baixadas do GitHub (Bootstrap vem em WOFF: converter para TTF). Conferir cada glifo renderizando antes de entregar.
   - **[Feito na branch: M1a, 27/10] Ajustes pequenos vistos na retomada real de 27/10:** a janela de andamento continua com o título "executando" depois do "Fim."; o resumo final diz "1 retomadas" (plural fixo).
2. **1.2 — lixeira com prazo** (pedido do usuário em 27/10; entra depois da 1.1). Sessão arquivada há N dias (padrão 30, ajustável) vai para a lixeira: o Gate a esconde da lista, apaga os próprios dossiês dela (pasta `handoffs`) e lista os IDs para o usuário apagar pela exclusão oficial do `agy` (`/resume`, tecla F4, desde a 1.1.13), que também limpa subagentes, worktrees e anotações (changelog 1.1.24, 1.1.26, 1.2.2, 1.4.8). **O Gate não apaga nada nos bancos do Antigravity:** o motor guarda índice, subagentes e worktrees fora do `.db`, e já recriou como arquivo vazio conversa apagada por fora (corrigido na 1.2.2). Data do arquivamento: `session_state.updated_at`, já gravada. Exportações salvas pelo usuário ficam. Absorve o antigo item "limpeza de dossiês antigos".
3. Validar no uso real o fluxo completo (curadoria → dossiê → Auto-Run). Retomada real de sessão sem projeto feita em 27/10; falta uma de sessão com projeto (`--project`).
4. Não verificado no Windows: escala 125% a 150%, glifos Segoe MDL2 em todos os botões, significado dos status 6 e 7 das ferramentas.
5. Lista de modelos do Auto-Run pelo `agy models` (hoje: lista embutida + a que o `agy` devolve no erro).
6. Campo "Modelo(s)" vazio no dossiê de algumas sessões (o banco não tinha o nome em `gen_metadata`; não investigado).
7. Datas `0001-01-01 00:00:00` em sessões sem horário: mostrar "-".

Saiu do backlog em 27/10: divisor de altura entre a tabela e os detalhes (a faixa de alerta da 1.0.2 entrou no lugar dele).

Fora do alcance do app: o editor do Antigravity abre vazio a cada chamada do `agy` (comportamento do `agy`; o `--help` não tem opção para evitar). Continua em 27/10; diagnóstico proposto em "Observações do usuário em 27/10".

## Registro da sessão de 2026-10-27 (1.0.0 → 1.0.1)

- **Restauração do Antigravity** (fora do app): a config `~/.gemini/config/projects` tinha sido alterada por scripts do Gemini e o daemon de remote control estava desregistrado. Registro completo: `handoffs/2026-10-27-antigravity-sync.md` no repositório `zuvuya`.
- **Auditoria full spectrum** do app contra o que a restauração revelou: `reviews/audit-full-v1.0.0.md`. Dois críticos: C1 (retomada fora do projeto, corrigido na 1.0.1) e C2 (junctions como "Backup", no backlog).
- **Fatos do ambiente real** que os testes não cobriam: junctions para a pasta mestra; JSON de projeto com BOM; a barra lateral do VS Code (extensão 1.9.0 + `agy` 1.4.7) só lista conversas abertas, enquanto a busca 🔍 e o remoto listam tudo; três motores escrevendo na mesma pasta (daemon, VS Code, Auto-Run).
- Testes da 1.0.1 rodados localmente com Python 3.12 e **Tk 9.0**: 24 de 25 passam. `test_theme` falha igual antes e depois da mudança (largura de fonte do Tk 9; o CI usa Tk 8.6). No CI (Tk 8.6), a 1.0.1 passou nos 25 e o `.exe` foi montado e autotestado (execução 40465486627).
- **1.0.2** (pedido do usuário, mesma sessão): alerta de contexto em dois níveis no lugar do item 8 do backlog. O pedido era para a **dica** do contexto (a "janela de alerta" ao passar o mouse); a primeira entrega mudou só a faixa, e a correção levou o mesmo estilo à dica. Também corrigidas as janelas do Auto-Run (duas abertas se travavam; abriam atrás da principal). Ícones adicionais (Font Awesome, Bootstrap, Material, com as fontes reais) ficaram para a 1.1 "pacote visual", junto com o ícone autoral.
- Neste ambiente de teste o Tk só enxerga 8 fontes do X, sem símbolos: os ícones (botões e faixa) não aparecem nas capturas de Linux. Não é defeito do app.
- **Pacote visual, segunda entrega do Stitch** (8 skins + `DESIGN.md`): 6 das 8 telas usam uma linha por sessão, o que o Treeview faz; células de duas linhas verificadas no Tk 9.0. Nas 8 skins o texto terciário fica abaixo de 4,5:1; os tokens propostos passam em todos os pares do `test_theme`. MCP do Stitch: dispensável agora. Decisões fechadas pelo usuário: "Dark Alloy" (paleta Obsidian) como tema padrão no lugar do Escuro, tabela compacta, barra lateral aberta. Detalhes em `docs/PACOTE_VISUAL_1.1.md`.
- **1.0.2 aprovada** depois da retomada real com o `.exe` da execução 40471275835: `4c326dce` ("cancele o deep coder") → `3723a6eb`, Gemini 3.8 Flash (Medium), resposta completa. A sessão original não tinha projeto em `config/projects` nem pasta de workspace válida: a nova foi para CLI Project, com a pasta `handoffs` como pasta de trabalho (o caminho previsto para esse caso). O `--project` continua visto só na simulação.
- **Publicação da 1.0.2:** PR two2dope/agy-gate#4 (merge `bc50fcf`). O push da tag a partir desta sessão foi recusado (HTTP 403); a Release saiu pelo `workflow_dispatch` com `release_tag: v1.0.2` (execução 40483779704), que cria a tag na `main` ao publicar. `AntigravityGate.exe` de 13,3 MB, SHA-256 `8D2EB3E241EE8B5EDCDFAEC7A97132A0982254A3E9AD360D13AB05B4DCDB7757`. As notas da Release trazem só a seção 1.0.2 do CHANGELOG; a 1.0.1 está no CHANGELOG.
- **Lixeira com prazo** pedida pelo usuário: decidido fazer pela exclusão oficial do `agy`, sem o Gate apagar nada nos bancos, depois da 1.1 (item 2 das pendências).

### Observações do usuário em 27/10 (sem diagnóstico)

1. **O editor do Antigravity continua abrindo vazio a cada chamada do `agy`.** O Gate só executa o `agy` no Auto-Run: `agy.exe` de `%LOCALAPPDATA%\agy\bin` (verificado em 26/10), com `CREATE_NO_WINDOW`. O Sobre só localiza o arquivo, sem executá-lo. O changelog oficial (até a 1.4.8; o usuário tem a 1.4.7) não cita o efeito. Guias da comunidade relatam conflito entre o `agy` da linha de comando e o do aplicativo de desktop [não verificado; o caminho conferido em 26/10 é o da linha de comando]. Diagnóstico de 2 passos, no PowerShell, com o editor fechado: `Get-Command agy -All | Format-List Source` (todos os `agy` no PATH, na ordem); depois `agy --version`. Se o editor abrir já no `--version`, o problema está no lançador ou na instalação. Se abrir só nas execuções com `--print`, é do modo sem interação: reportar ao Google e conviver. O Gate não fecha o editor (nunca encerrar processo do usuário).
2. **O remote control faz piscar janelas do PowerShell a cada interação no chat.** Não é do Gate. Registrado no repositório `zuvuya` (`handoffs/2026-10-27-antigravity-sync.md`, pendências), com a hipótese e o teste.

## Registro da sessão de 2026-10-26/27 (0.9.0 → 1.0.0)

- **Auditoria full spectrum** (10 lentes): `reviews/audit-full-v0.9.0.md`. Críticos C1–C3 do Auto-Run corrigidos.
- **Testes reais no Windows** (montagens identificadas no Sobre): caminho do workspace com `%3A`, monitor à esquerda (`+-1928`), lista de temas, dicas na borda, nome de modelo com esforço, sessões vazias criadas pelo `agy`, sucesso falso por `read_file` negado → dossiê no prompt. Retomada validada: `a56f46f0` → `5c583e36`.
- **Revisão final em 3 etapas:** segurança e dados; tabela, teclado e janelas; blindagem do CI (testes barram a montagem, PyInstaller fixo, permissões mínimas, Release em rascunho primeiro).
- **Revisão de código do branch:** 9 achados corrigidos (log sem máscara de segredos, arquivamento indevido, maximizar escondido por `self.state` etc.).
- **Publicação:** PR two2dope/agy-gate#1 (1.0.0) e two2dope/agy-gate#2 (correção do passo de Release: função `Gh` recursiva no PowerShell). Release v1.0.0 com `AntigravityGate.exe`, SHA-256 `A9154FDAF6D5EC10B8FCC702A183003DD19FAF24F922D24CA5ECEF389B3CC9B1`.
- Lição de processo: trecho que não dá para ensaiar localmente (PowerShell do job de Release) precisa de uma execução de teste antes da publicação; o `workflow_dispatch` com `release_tag` agora permite isso numa Release de rascunho.

O dossiê é extração local (sem modelo). Resumo feito pelo modelo fica como opção futura.

## Exportação (M4)

- **Diálogo completo:** todos os passos em ordem, com hora local, papel, ferramentas, argumentos e resultados. Resultados de ferramenta são cortados em 6000 caracteres e argumentos em 2000, com aviso do que foi omitido. Não mascara segredos (o cabeçalho avisa).
- **Dossiê de retomada:** origem, pedidos do usuário, última resposta do modelo, arquivos alterados e consultados, comandos, falhas de ferramenta, mensagens entre agentes e instrução para quem retomar. **Mascara** chaves de API, tokens e senhas por padrões conhecidos (heurístico).
- Ambos são salvos por diálogo "Salvar como" (pasta inicial `%LOCALAPPDATA%\AntigravityGate\exports`), em segundo plano, com progresso na barra de status. Medição sintética: 6000 passos e 37 MB em 0,5 s.
- "Arquivos alterados" usa o nome da ferramenta (`write`, `edit`, `replace` etc.). É heurística e pode errar.
- Passos de tipo desconhecido (17) aparecem como "não interpretado". Passos de tipo 90 são omitidos.

## Decisões tomadas

- O app só lê os bancos do Antigravity (`mode=ro`). O estado fica em `%LOCALAPPDATA%\AntigravityGate\gate_state.db`.
- Padrão de leitura: `antigravity\conversations`. Backups (`.bak`, `bkp`, `backup`, `corrupt_quarantine`) aparecem como fontes separadas no seletor.
- Alerta de contexto por tokens da última resposta (`f2 + f5`), em **dois níveis** (atenção e crítico), escolhidos em `Limites` (ver "Limites de contexto").
- Auto-Run = **opção B, retomada limpa**: o app monta um dossiê compacto da sessão aprovada e abre uma **sessão nova** com `agy --print`, sem tocar na sessão original.

## Formato dos bancos de sessão (resumo)

Tabelas: `steps`, `gen_metadata`, `executor_metadata`, `trajectory_meta`, `trajectory_metadata_blob`. Os blobs são protobuf sem compressão. Cada resposta do modelo (`step_type` 15) tem uma linha em `gen_metadata` nas sessões inspecionadas, com exceções.

| `step_type` | Origem (`f5.f3`) | Papel | Onde está o conteúdo | Confiança |
|---|---|---|---|---|
| 14 | 4 | Usuário | `f19.f2` | Verificado em amostra |
| 15 | 2 | Modelo | texto: `f20.f3`; chamada de ferramenta: `f20.f7` (`f1` id, `f2` nome, `f3` argumentos JSON) | Verificado em amostra |
| 132 | 2 | Resultado de ferramenta | chamada em `f5.f4`; resultado em `f140.f2.f1`; `f140.f1` repete o parâmetro | Verificado em amostra |
| 101 | 5 ou 6 | Sistema ou agente | tipo em `f114.f3` (`agent_message`, `hook_json_SessionStart`); texto em `f114.f1` e `f114.f2.f10.f1` | Verificado em amostra |
| 90 | 5 | Marcador sem texto | nada | Inferência |
| 17 | 5 | Desconhecido | desconhecido | **Não verificado** |

Outros campos:
- Hora do passo: `f5.f1.f1` (segundos Unix UTC) e `f5.f1.f2` (nanos). Verificado.
- Contexto: `f5.f9.f2` (entrada) + `f5.f9.f5` (cache). `f5.f9.f3` = `f9` + `f10` (saída). A saída do `agy` nomeia `input_tokens`, `cache_read_tokens`, `output_tokens` e `thinking_tokens`, o que apoia esta leitura.
- Status do passo: 3 = concluído; 6 e 7 em passos de ferramenta (7 coincide com `error_details`). Interpretação de 6 e 7 é inferência.
- Raciocínio do modelo não está em texto: só uma assinatura binária opaca em `f20.f7.f7.f2.f1`.
- Nome do modelo: `gen_metadata` `f19` (id) e `f21` (nome exibido).
- Resumos: `conversation_summaries` (`title` vazio, `preview`, `agent_name`, `parent_conversation_id`, `nesting_depth`, `workspace_uris`, `raw_summary` protobuf) e índice FTS5 `conversations_fts` (`user_body`, `agent_body`).

## Contrato do `agy` (CLI)

Usado pelo Auto-Run:
- Executável: `agy.exe` (aplicativo nativo, não `.cmd`), em `%LOCALAPPDATA%\agy\bin\agy.exe`, no PATH. Verificado no Windows do usuário em 2026-10-26.
- `agy --print "<prompt>"`: roda sem interação e imprime a resposta.
- `--output-format json`: devolve um objeto com `conversation_id`, `status` (`ERROR` ou sucesso), `response`, `error`, `duration_seconds`, `num_turns` e `usage` (`input_tokens`, `output_tokens`, `thinking_tokens`, `cache_read_tokens`, `total_tokens`).
- Em erro, o `agy` também escreve na saída de erro as linhas `error: ...` e `AGY_ERROR: {json}`. O JSON traz `status`, `error_code`, `retryable` e `error_id`.
- Erro de cota observado: `RESOURCE_EXHAUSTED`, código 429, com o tempo para reset no texto.
- **Cada chamada cria um `conversation_id`, mesmo quando falha.** Sessões vazias aparecem na lista: arquive-as pelo app.
- `--model` exige o nome com o esforço, como o agy lista: `Gemini 3.8 Flash (Medium)`. Nome sem esforço dá código 1, `status` `ERROR`, `conversation_id` vazio e a lista `Available models:` no erro. Verificado em 2026-10-26.
- Primeiro teste real (2026-10-26, 20:03): erro de modelo tratado como falha, sem retomada falsa e sem sessão vazia (C1 validado no caminho de erro). Formato de sucesso ainda não visto.
- Segundo teste real (2026-10-26, 21:11): nome sem esforço recusado (código 1) e criou uma sessão sem informar o id; `Gemini 4 Argon (Medium)` deu cota esgotada (reset em 26h29m). A cota com saldo é a do Gemini 3.8 Flash.
- **Primeira retomada real com sucesso:** 2026-10-26 22:11, `74a14497` → `0b49637d`, resposta completa (entendimento, pendências, próximos passos).
- **Sucessos falsos** (21:17, 21:23, 21:26 e 22:17, todos de `a56f46f0`): `status: SUCCESS`, `response` vazia, `denied_actions: [read_file]`; stderr: "a tool required the read_file permission that headless mode cannot prompt for, so it was auto-denied". Correção: o dossiê vai no prompt; resposta vazia é falha.
- Formato de sucesso visto: `{"conversation_id", "status": "SUCCESS", "response", "duration_seconds", "num_turns", "usage", "denied_actions"?}`, código de saída 0. Cota esgotada: código 3.
- **Dossiê no prompt validado** (montagem 4bb7837, 2026-10-26 22:55): `a56f46f0` → `5c583e36`, resposta completa, sem `denied_actions`. A correção automática marcou 5 retomadas falsas antigas. Critério da 1.0 "Auto-Run real testado": **cumprido**.
- Pendentes menores do teste: janela não reabre maximizada (reabre no monitor certo); `agy models` pode alimentar a lista de modelos.
- Depois de uma chamada do `agy`, o editor do Antigravity abre uma janela vazia. Vem do próprio `agy`, não do app; o `--help` não tem opção para evitar. Continua em 27/10 (ver "Observações do usuário em 27/10").
- O Auto-Run aceita `--model` (campo na confirmação). Hipótese não verificada: o padrão do `agy` usa a cota do Gemini 4 Argon (o reset informado no erro de 26/10 bateu com o dele).
- Opções úteis: `--mode plan|accept-edits|auto`, `--add-dir`, `--project`, `--print-timeout`, `--effort`, `--model`, `--conversation` (retoma e muda a conversa original).
- **Projeto da sessão:** sem `--project`, toda sessão do CLI vai para "CLI Project" (`default-cli-project`), qualquer que seja a pasta. Fonte: CHANGELOG oficial do `agy` (github.com/google-antigravity/antigravity-cli): 1.0.12 "Added support for `--project` [...] updated the project resolution logic to default regardless of the active workspace"; 1.1.18 "Added support for passing a project name to `--project`". Confirmado no banco do usuário em 27/10: as retomadas da 1.0.0 ficaram em `default-cli-project`. A 1.0.1 passa `--project <id>` quando o projeto existe em `config/projects`.
- **Pasta de trabalho = workspace.** Visto em 27/10: `agy --print` rodado no PowerShell em `C:\Users\Thomáz`, sem `--add-dir`, gravou `workspace_uris = ["file:///C:/Users/Thom%C3%A1z"]`; as retomadas da 1.0.0 levaram a pasta de onde o app foi aberto. A 1.0.1 roda o `agy` com `cwd` na pasta do projeto. O `agy` grava `workspace_uris` em ordem alfabética.
- Nunca usar `--dangerously-skip-permissions`.

## Salvaguardas do Auto-Run

1. Confirmação listando as sessões e os workspaces antes de rodar.
2. Modo de teste (`dry-run`) que só gera os dossiês.
3. Uma chamada por vez, com lista de argumentos (sem `shell=True`).
4. Padrão `--mode plan` (só leitura).
5. Erro 429 interrompe o lote inteiro e informa o horário de reset. Sem tentativas em laço.
6. Log por item (iniciado, sucesso, falha) e botão Cancelar.
7. Trava para não rodar duas vezes sobre a mesma sessão.
8. Sucesso só com código de saída 0, `conversation_id` e status diferente de `ERROR`; na dúvida, falha.
9. Prompt numa linha, depois das flags; `agy` `.cmd`/`.bat` com caracteres perigosos para o `cmd.exe` não é executado.
10. Fechar a janela no meio pergunta, cancela e registra antes de sair.

## Pendências do usuário

- Quando a cota voltar (cerca de 31 h após 2026-10-26), repetir o teste `agy --print "responda apenas: ok" --output-format json --mode plan --print-timeout 60s` para ver o formato de sucesso.
- Revisar um dossiê real de uma sessão sua e dizer o que falta ou sobra antes de ele alimentar o Auto-Run.

## Como testar

`tests/run_all.sh` (precisa de Python 3.12 com `tkinter` e, sem tela, `xvfb`). São 25 conjuntos com bancos sintéticos e um `agy` simulado (`tests/fake_agy.py`). Os scripts `tools/inspect_*.py` dão a estrutura (sem conteúdo) de qualquer banco de sessão.

## Versões

- `__version__` em `AntigravityGate.py` é a fonte da versão (aparece na dica do cabeçalho, no log e no autoteste do `.exe`). Histórico em `CHANGELOG.md`.
- Publicar: subir `__version__`, registrar no CHANGELOG, commit em `main`, tag `vX.Y.Z` igual. O workflow confere a tag contra `__version__`, monta o `.exe`, testa e cria a Release (marcada como pré-lançamento enquanto a versão começar com 0).
- 0.9.0 = candidato a 1.0.0. 1.0.0 publicada em 2026-10-27.

## Auto-Run (implementado)

- Botão `⚡ Auto-Run`: pega as sessões **aprovadas** da fonte aberta, pede confirmação (simulação marcada por padrão) e, para cada uma, gera o dossiê em `%LOCALAPPDATA%\AntigravityGate\handoffs` e abre uma sessão nova com `agy --print ... --mode plan --output-format json`.
- Janela de andamento: uma por vez (um novo Auto-Run fecha a do anterior), sempre acima da principal (`transient`), e o Fechar ou o X de cada janela agem só sobre ela (`close_autorun`).
- Erro 429 interrompe o lote e mostra o reset. Três falhas seguidas interrompem. Sessões vazias criadas por tentativas com erro vão para arquivadas. Retomadas concluídas aparecem como `↪ retomada <id>` e ficam gravadas em `gate_state.db`.
- **Só foi testado com um `agy` simulado** que imita a saída real do erro de cota. A saída de sucesso real do `agy` ainda não foi vista: o código lê `status`, `conversation_id`, `response` e `error`, e aceita variações, mas isso é **não verificado**.
- Variável `AGY_EXE` aponta para outro `agy.exe` se ele não estiver no PATH.

## Gerar o .exe

- **Pronto no GitHub (recomendado):** a ação `Gerar AntigravityGate.exe` (`.github/workflows/build-exe.yml`) monta o `.exe` num servidor Windows, abre-o em modo de autoteste e só então publica o arquivo. Baixe em Actions, execução mais recente, seção Artifacts, `AntigravityGate-windows`.
- **No seu computador:** copie `packaging/build_exe.bat` para a pasta do `AntigravityGate.py` e dê duplo clique. O PyInstaller 6.16 ou mais novo suporta Python 3.14.
- O `.exe` não abre janela de terminal. Erros fatais gravam em `%LOCALAPPDATA%\AntigravityGate\gate.log` e mostram um aviso.
- `AntigravityGate.exe --selftest saida.txt` abre o app sem janela, espera a carga e grava `OK` ou `FALHA` em `saida.txt`.
- O Windows pode mostrar o aviso do SmartScreen ("editor desconhecido") e alguns antivírus desconfiam de `.exe` feito com PyInstaller. O arquivo não é assinado. A impressão digital SHA-256 aparece no log da ação.

## Interface visual

- **8 temas**, escolhidos em `Tema`: Escuro, Claro e seis inspirados nas skins do Cyber-HUD do `navigator-agy` (Mil-Spec, Cyber Synthwave, Vidro Aero, Brutalista, Obsidiana, Mecha). O tema fica salvo em `%LOCALAPPDATA%\AntigravityGate\settings.json`. Prévia: `docs/temas_preview.png` (renderizada no Linux, com outra fonte).
- Todas as combinações de texto das paletas passam em contraste WCAG AA (4,5:1). O teste `test_theme` confere isso para cada tema.
- **Botões** desenhados no app (cantos do tema, ícone e texto): medem o próprio texto e **viram só ícone** quando a janela estreita, com dica ao passar o mouse. Nunca cortam.
- **Estados:** normal, passar o mouse, pressionado, foco do teclado, desabilitado (a dica explica o motivo), ocupado (spinner), selo de contagem (Auto-Run mostra quantas aprovadas faltam retomar) e confirmação em verde depois de aprovar, arquivar ou exportar.
- Os botões habilitam e desabilitam conforme a seleção. Exportar e Dossiê só valem para uma sessão com arquivo. Aprovar, Arquivar e Pendente aceitam sessões ou pasta de projeto.
- **Ícones:** usam `Segoe MDL2 Assets` quando existe (Windows 10 e 11). Os códigos dos glifos **não foram vistos num Windows**. Se algum aparecer errado, use `Tema` > `Símbolos Unicode` (ou `Sem ícones`). Variável `AGY_ICONS=mdl2|symbol|none` também vale.
- Linhas da tabela: aprovada em verde, arquivada esmaecida, Rot em âmbar. Medidor de contexto de 6 células. Selos de contagem no rodapé. Rolagem horizontal para as colunas do fim.

## Limites de contexto

- Botão `Limites` no cabeçalho. Três faixas prontas e uma personalizada:

| Faixa | Atenção | Crítico | Uso |
|---|---|---|---|
| Conservador | 100k | 150k | troca cedo; tarefas longas com muitas ferramentas |
| **Equilibrado** (padrão) | 150k | 250k | avisa antes da degradação e deixa margem para o dossiê |
| Amplo | 300k | 500k | modelos de contexto muito grande |
| Personalizado | você define | você define | aceita `120000`, `120.000` ou `120k`; entre 10k e 5M; crítico maior que atenção |

- Os valores das faixas são **heurísticas**, não medidas: a degradação real depende do modelo e da tarefa **[Não verificado]** para o seu modelo. Nas suas sessões reais, o contexto chegou a ~201 mil e ~213 mil tokens.
- A janela mostra, antes de aplicar, quantas sessões carregadas ficariam em atenção e críticas.
- **Atenção:** linha em âmbar, `⚠`. **Crítico:** linha em vermelho, `‼`.
- **Dica do contexto como janela de alerta (1.0.2):** na tabela e no medidor do painel, a dica de uma sessão em atenção ou crítica usa as cores da faixa, ícone grande e o título "ATENÇÃO" ou "CRÍTICO" (`show_tip(..., level)`, `cell_level`). Nível normal: dica comum.
- **Faixa de alerta acima da tabela (1.0.2), em dois níveis.** Crítico: fundo vermelho forte do tema, texto claro, ícone grande, "CRÍTICO · N sessão(ões)…" e o que fazer; botões `Ver críticas` e `Dispensar`. Atenção: faixa âmbar suave, só quando não há críticas, com `Ver em atenção` e `Dispensar`. A faixa não conta sessões arquivadas. Dispensar vale para o nível exibido; a faixa volta se você mudar o limite ou a fonte. Cores em `banner_colors` (o vermelho escurece o mínimo para o texto claro ter 4,5:1); o `test_theme` confere o contraste nos 8 temas. Ícone: `Warning` do Segoe MDL2 (`E7BA`), `⚠` no modo Unicode e `‼` sem ícones. **Não visto num Windows.**
- Selos no rodapé: `N em atenção` e `N críticas`. O dossiê indica o nível no cabeçalho (`tokens (atenção)` ou `(crítico)`).
- Preferência salva em `settings.json`. A variável `AGY_ROT_TOKENS` (antiga) ainda vale: define a atenção, e o crítico fica 1,5 vez maior.

## Ícones, detalhes e notificações (última rodada visual)

- **Ícones das linhas** desenhados pelo próprio app (PNG com transparência, gerado em Python): pasta de projeto, pendente (anel), aprovada (verde com visto), arquivada (caixa) e selo de retomada. Não dependem de fonte do Windows. Seguem o tema.
- **Coluna `Falhas`:** passos de ferramenta (tipo 132) com status diferente de 3. A leitura usa o índice do banco. O significado dos status 6 e 7 continua inferência.
- **Datas** dos resumos vêm em UTC no banco e agora aparecem no horário local.
- **Painel `Detalhes da sessão`** (recolhível, preferência salva): título, projeto, agente, origem CLI, estado, UUID, workspace (com aviso se a pasta não existe mais), passos, modificação com tempo relativo ("há 3 h"), tamanho, falhas, retomada e **medidor de contexto** com as faixas normal, atenção e crítico. Com várias sessões ou uma pasta selecionadas, mostra os totais. Traz os botões Copiar UUID, Abrir pasta, Exportar e Dossiê.
  - "Em execução" e "encerrada à força" vêm das colunas `status` e `killed` do resumo. **Não verificado:** nos dados vistos, todas as sessões estavam ociosas.
- **Notificações** no canto da janela, sem travar o uso: salvar (com `Abrir arquivo` e `Abrir pasta`), marcar (com **`Desfazer`**), copiar UUID, limites aplicados, aviso de leitura (com `Abrir log`) e resultado do Auto-Run. Erros continuam em janela. O arquivo exportado ainda abre sozinho no Windows.
- **Estados vazios** no centro da tabela: carregando, busca sem resultado (com `Limpar busca`) e fonte vazia (com `Atualizar`).
- **Lista de arquivos** nos arquivos exportados: ícone por tipo, ordem do mais mexido para o menos, e coluna `No disco` (existe ou não neste computador). O diálogo completo ganhou o índice `Arquivos citados` (alterado e lido). O dossiê separa alterados e consultados em tabelas. Alterado ou lido é classificação por nome da ferramenta: heurística.

## Seletor de tema (lista suspensa)

- O botão do cabeçalho mostra o tema atual (`Escuro ▾`) e abre uma **lista suspensa própria**, no visual do tema. O menu nativo do Windows ficava branco nos temas escuros.
- Cada tema aparece com amostra de 4 cores (fundo, painel, destaque, texto) e marca de seleção. Abaixo, o estilo de ícones (Segoe MDL2, Símbolos Unicode, Sem ícones).
- Setas, Enter e Esc funcionam. Clicar fora ou no botão de novo fecha. Escolher aplica na hora e grava em `settings.json`.
- Não verificado no Windows real: posição da lista perto da borda da tela (testado só em Linux/Xvfb).

## Tamanho e posição das janelas

- A janela abria com 1240×820 px fixos e centralizada na tela inteira. Em tela baixa passava da borda; com a barra de tarefas no topo (caso real: notebook 1366×768 como monitor principal), a barra de título ficava sob ela. As janelas adicionais (Limites, confirmação e andamento do Auto-Run) abriam no canto do monitor principal, também sob a barra.
- Agora tudo é calculado sobre a **área útil do monitor** (sem a barra de tarefas, em qualquer lado): `MonitorFromPoint` + `GetMonitorInfoW` (`rcWork`) no Windows, `SystemParametersInfoW` para o principal. Fora do Windows vale a tela inteira.
- Janela principal: tamanho de projeto escalado pelo DPI, limitado à área útil (descontando barra de título e folga), centralizada. Tamanho e posição são lembrados em `settings.json` (chave `window`), 0,7 s depois de mexer e ao fechar; maximizada não é gravada. Posição salva sob a barra é corrigida; se o monitor sumiu, a janela volta para o mais próximo.
- Janelas adicionais: `place_over` centraliza sobre a principal, no monitor dela, sem passar da área útil.
- O autoteste do `.exe` no Windows do CI agora imprime a área útil encontrada (principal e no ponto da janela), o que valida essa consulta num Windows real.
- Não verificado: escala 125% a 150% e monitores de tamanhos diferentes. Testado com a função de cálculo e Xvfb.

## Barra de título nativa nas cores do tema

- A barra de título do Windows (e a das janelas adicionais) acompanha o tema: `DwmSetWindowAttribute` com modo escuro (Windows 10 1809+) e, no Windows 11, cor de fundo, cor do texto e borda exatas (`header_bg`, `header_fg`, `border`). Arrastar, encaixar, minimizar e redimensionar continuam nativos. Barra desenhada pelo app foi descartada: perde esses recursos.
- Troca de tema repinta na hora. Fora do Windows não faz nada.
- Temas com barra clara: Claro e Brutalista (cabeçalho amarelo). Os demais usam barra escura.
- No Windows 10 só vale claro/escuro; a cor exata depende do Windows 11 (build 22000+).
- Os botões minimizar, maximizar e fechar são do Windows e mudam de cor junto com a barra.
- O autoteste do `.exe` no Windows do CI imprime o HRESULT de cada atributo (0 = aplicado).
- Não verificado visualmente: só o seu Windows mostra o resultado. Caixas de mensagem nativas (avisos e erros) não são pintadas.

## Cabeçalho sem o nome repetido

- A barra de título do Windows já mostra "AntigravityGate". O cabeçalho do app repetia o nome em letras grandes. Agora diz para que o app serve: "Gestão de contexto e curadoria" (com o losango). O subtítulo pequeno foi removido.
- Fundir a barra de título com o cabeçalho exigiria desenhar a barra no app (sem moldura do Windows): perde arrastar, encaixar nas bordas, redimensionar e atalhos nativos. Descartado; a barra nativa segue as cores do tema.
