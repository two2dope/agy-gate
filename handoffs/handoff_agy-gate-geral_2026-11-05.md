# Handoff — AntigravityGate (geral) — 2026-11-05

## 1. Snapshot

- Sessão longa (27/10 a 05/11): restauração do Antigravity no Windows, auditoria do AntigravityGate e publicação das versões 1.0.1 a 1.2.1.
- Restrições ativas: orçamento curto (o usuário pediu economia de custo e alternou entre Sonnet e Opus); tudo em PT-BR; PR e tag só com pedido explícito.
- Estado agora: a v1.2.1 está publicada e conferida no Windows. A pasta local `handoffs\` (dossiês das sessões rodadas no Antigravity) ainda não foi lida: a sessão na nuvem não alcança o PC, por isso o usuário vai abrir uma sessão local.

## 2. Trabalho Concluído

- **Antigravity restaurado (27/10):** as conversas voltaram na busca do VS Code e no remoto `dev-thomaz`, com o daemon permanente via chave Run. Registro em `zuvuya/handoffs/2026-10-27-antigravity-sync.md`.
- **Auditoria completa** do agy-gate v1.0.0: `zuvuya/reviews/audit-full-agy-gate-v1.0.0.md` e `agy-gate/reviews/audit-full-v1.0.0.md`.
- **Releases publicadas** (PRs two2dope/agy-gate#4 a #7):
  - 1.0.2 (inclui 1.0.1): retomada no projeto de origem (`--project` e pasta de trabalho); alerta de contexto em dois níveis.
  - 1.1.0: pacote visual. Inter e JetBrains Mono; 6 estilos de ícones (Font Awesome, Bootstrap, Material, MDL2, Unicode, nenhum) com as fontes no `.exe`; barra lateral; abas; coluna Consumo; tabela compacta ou confortável; cores das 8 skins com Dark Alloy como padrão; ícone do app; indicador de ambiente.
  - 1.2.0: recibo de retomada salvável; janela única do Auto-Run em 3 etapas (Preparar, Executando, Resumo), com relatório salvável e pasta dos dossiês escolhível; cabeçalho e busca com menos texto.
  - 1.2.1: cabeçalho alinhado com o painel de sessões, marca isolada à esquerda. SHA-256 do `.exe`: `469EE122BD7C473C2304E4830EC128BF5766F1D4FB515C43DA3F9DBA9597E12F`.
- 31 conjuntos de teste passando no CI (Ubuntu, Tk 8.6) e no autoteste do `.exe` no Windows.
- `agy-gate/docs/ESTADO_DO_PROJETO.md` atualizado até 05/11 (commit `b579580` na branch, ainda fora da `main`).

## 3. Decisões Tomadas

- **Decisão:** caminho A, evoluir a interface em Tk. **Motivo:** risco baixo; os mockups do Stitch usam uma linha por sessão, que o Treeview já atende.
- **Decisão:** o Gate nunca escreve nos bancos do Antigravity. A lixeira com prazo (1.3) só esconde as sessões e lista os IDs para a exclusão oficial do `agy` (`/resume`, F4). **Motivo:** o motor guarda índice, subagentes e worktrees fora do `.db` e recria arquivos apagados por fora.
- **Decisão:** a aba "Em Revisão" virou "Aprovadas aguardando" (aprovadas sem retomada). **Motivo:** o Gate não tem estado de revisão; o número coincide com o selo do Auto-Run.
- **Decisão:** o tema padrão passou a se chamar "Dark Alloy", mantendo a chave interna `escuro`. **Motivo:** pedido do usuário, sem perder a preferência salva.
- **Decisão:** as considerações de 30/10 viraram a 1.2 e a lixeira passou para a 1.3. **Motivo:** escolha do usuário.
- **Decisão:** exportar o diálogo e o dossiê ficou como está. **Motivo:** o "Salvar como" já permite escolher a pasta; o usuário não tinha visto.
- **Decisão:** os backups `D:\backup_gemini_2026-10-27` e `.gemini\projects-backup-27-10` ficam; o prazo de 03/11 foi cancelado. **Motivo:** o `agy` travou conversas em novembro e foi abandonado por ora.
- **Decisão:** o MCP do Stitch não foi usado. **Motivo:** o zip mais o `DESIGN.md` bastam, e a chave anterior vazou.

## 4. Armadilhas

- **Tentativa:** enviar a tag pela sessão na nuvem (`git push origin vX.Y.Z`). **Resultado:** HTTP 403 do proxy. **Não repetir.** Publicar pelo `workflow_dispatch` do `build-exe.yml` com `release_tag`; a tag é criada ao publicar.
- **Tentativa:** ler `C:\Users\Thomáz\...\agy-gate\handoffs` via Remote Control a partir da nuvem. **Resultado:** a pasta "Projetos" do VOSTRO aparece como `not_available`, mesmo depois de reiniciar o app. **Não repetir;** usar uma sessão local.
- **Restrição conhecida:** sequências `\uXXXX` no texto de comandos viram o caractere antes de chegar ao arquivo. **Por que importa:** os escapes de glifos no código foram gerados por script (`chr(92)`).
- **Restrição conhecida:** o Tk 9 local não tem fontes de símbolos. **Por que importa:** ícones e ☑ ✔ aparecem vazios nas capturas do Linux; só o Windows confirma.
- **Restrição conhecida:** `tests/test_icons.py` já existia (ícones PNG) e foi sobrescrito por engano uma vez; foi restaurado. **Por que importa:** antes de criar um teste, conferir se o nome é novo.
- **Tentativa:** encadear o commit depois de um laço de testes sem checar falhas. **Resultado:** um commit subiu com teste vermelho e foi corrigido em seguida. **Não repetir;** usar `fail=0` e `[ $fail -eq 0 ] ||` antes do commit.
- **Restrição conhecida:** cada chamada do `agy` abre o editor do Antigravity vazio; o daemon na chave Run faz janelas do PowerShell piscarem [hipótese não verificada]. **Por que importa:** só leia o estado do `agy` sem executá-lo.

## 5. Acordos de Trabalho

- PR, merge e tag só com "PR + merge + tag" do usuário, depois de ele conferir o `.exe` (artefato `AntigravityGate-windows`) no Windows.
- O usuário quer marcos curtos com fechamento visível: CI verde e uma captura de tela enviada.
- Antes de abrir frente nova, perguntar "isso entra no lugar de quê?".
- Para decisões de design, usar perguntas de múltipla escolha (AskUserQuestion), com uma opção recomendada.
- Commits terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` e `Claude-Session: https://claude.ai/code/session_017vWnh2PNF5XBkhh9AXWdZm`.

## 6. Arquivos Alterados

Repositório `two2dope/agy-gate`, branch `claude/funny-tesla-4w2i3q`, já na `main` até a v1.2.1:
- `AntigravityGate.py` (~5.000 linhas; centenas alteradas [não verificado o número]): fontes e ícones (`ICON_FONTS`, `register_fonts`, `icon_glyph`); `THEMES`; barra lateral (`SideItem`, `update_nav`); abas (`Tab`, `tab_colors`); `ctx_label` com 5 células; densidade; coluna ⋮; recibo (`receipt_fields`, `receipt_markdown`, `ReceiptDialog`, `handoff_record`, colunas novas em `handoffs`); `AutoRunWindow`; eventos por sessão no `AutoRunner`; `paint_header`; versão 1.2.1.
- `fonts/` (arquivos novos: 3 de ícones, Inter e JetBrains Mono, licenças) e `assets/` (`app.ico` e PNGs); `tools/make_icon.py` (arquivo inteiro, ~35 linhas).
- `tests/` (arquivos novos: `test_icon_fonts`, `test_sidebar`, `test_table`, `test_brand`, `test_receipt`, `test_autorun_window`; ajustes em `test_theme`, `test_picker`, `test_limits`, `test_titlebar`, `test_details`, `test_autorun`, `test_window`).
- `.github/workflows/build-exe.yml` e `packaging/build_exe.bat` (~4 linhas): `--add-data` de fontes e assets, `--icon`, e o autoteste exige 7 fontes e o ícone.
- `CHANGELOG.md` (seções 1.0.1 a 1.2.1), `README.md`, `docs/PACOTE_VISUAL_1.1.md` (arquivo inteiro, ~150 linhas), `docs/ESTADO_DO_PROJETO.md` (snapshot, backlog e registros).

Repositório `two2dope/zuvuya`, branch `claude/funny-tesla-4w2i3q`:
- `handoffs/2026-10-27-antigravity-sync.md` (arquivo inteiro, ~170 linhas): restauração do Antigravity e pendências, com as atualizações de 27/10 e 05/11.
- `reviews/audit-full-agy-gate-v1.0.0.md` (arquivo inteiro): auditoria.
- `handoffs/handoff_agy-gate-geral_2026-11-05.md`: este arquivo.

## 7. Trabalho em Aberto

- Análise da pasta local `handoffs\`: não iniciada. Depende de uma sessão local no PC do usuário.
- Commit `b579580` (ESTADO com a v1.2.1 publicada): na branch, fora da `main`. Entra no próximo PR.
- Lixeira com prazo (1.3): desenhada no ESTADO (item 2 do backlog), não iniciada. A prioridade pode mudar com o aprendizado dos handoffs.
- Conferência da 1.2.0 e da 1.2.1 no Windows: cabeçalho, busca e marca conferidos pelo usuário. Auto-Run em 3 etapas e recibo no Windows [não verificado].
- Retomada real de sessão com projeto (`--project`), teste do PowerShell piscando e editor vazio a cada `agy`: parados enquanto o `agy` estiver fora de uso.
- Auditoria C2 (junctions aparecem como fontes "Backup") e R2 a R17: não iniciadas.

## 8. Solicitação para Novo Chat

Projeto AntigravityGate (repositório `two2dope/agy-gate`, app Tk em arquivo único, versão 1.2.1 publicada). Esta sessão roda localmente no PC do usuário, que fica abaixo de `C:\Users\Thomáz\Projetos\01_dev-systems\04_apps-games\agy-gate`.

O estado completo está em `docs/ESTADO_DO_PROJETO.md`, seção Snapshot, e no handoff `zuvuya/handoffs/handoff_agy-gate-geral_2026-11-05.md`.

A pasta `handoffs\` contém os dossiês das sessões que o usuário rodou no Antigravity. Ela traz conhecimento e aprendizado que o usuário quer aproveitar de forma concreta no Gate, e ainda não foi analisada.

O usuário abandonou o `agy` por ora e usa o Auto-Run em simulação para trazer as sessões como dossiês. A lixeira com prazo (1.3) é o próximo item da fila.

Aguarde instruções.
