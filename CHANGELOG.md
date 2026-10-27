# Histórico de versões

Formato: [Versionamento Semântico](https://semver.org/lang/pt-BR/). Enquanto a versão começar com 0, o app está em candidato a lançamento: funciona, mas faltam itens listados abaixo.

## [Não lançado]

Correções dos três críticos da auditoria `reviews/audit-full-v0.9.0.md`, todos no Auto-Run.

### Adicionado
- Escolha do modelo do `agy` na confirmação do Auto-Run (`--model`; vazio = padrão do `agy`). Último valor e histórico ficam em `settings.json`.
- Janela **Sobre** (botão no cabeçalho e F1): versão, autor, e-mail, GitHub, projeto, aviso de independência e diagnóstico do ambiente com **Copiar informações**.

### Adicionado (segunda rodada de teste no Windows)
- Número da montagem (commit e data) no Sobre e no diagnóstico: o CI grava no `.exe`; rodando do código aparece "código-fonte".
- Selos do rodapé (pendentes, aprovadas, arquivadas, em atenção, críticas) filtram a tabela. Clique, Enter ou Espaço; de novo, mostra todas.

### Alterado
- A janela reabre no monitor em que estava e, se estava maximizada, reabre maximizada nele.
- O X da janela do Auto-Run faz o mesmo que o botão: cancela o lote em andamento ou fecha depois do "Fim.".
- Nome de modelo recusado pelo `agy` sai da lista e do campo; o erro aparece numa linha só no log.
- Campo Modelo do Auto-Run vem com a lista de modelos aceitos pelo `agy` (o esforço faz parte do nome: `Gemini 3.8 Flash (Medium)`). Se o `agy` recusar um nome, o log mostra a lista que ele aceita e o app passa a oferecê-la.
- Botão Sobre só com o ícone (o texto aparece na dica, ou no botão quando o tema está sem ícones).
- Painel de detalhes: os quatro botões têm a mesma largura e o conteúdo centralizado.
- Ícone de Exportar: disquete (Segoe MDL2 `E74E`; `↧` no modo Unicode) no lugar da folha em branco. Glifo não visto num Windows.

### Teclado e janelas (revisão final, etapa 2b)
- Confirmação do Auto-Run no tema do app, com uma caixa por sessão aprovada: só as marcadas rodam. As já retomadas vêm desmarcadas; "Refazer" marca todas.
- Janela de andamento do Auto-Run no tema, com tamanho escalado pelo DPI.
- Menu de contexto pelo teclado (Shift+F10 ou tecla Menu). Rótulos do menu sem emoji fora do BMP (o Tk 8.6 desenha mal).
- Barra "Detalhes da sessão" abre e fecha com Enter ou Espaço.
- Dicas aparecem também com o foco do teclado (inclusive o motivo de um botão desabilitado).
- Notificação com Desfazer não some enquanto o mouse ou o foco estão nela; some 4 s depois.
- Janela que fechou maximizada reabre maximizada (a maximização agora espera a janela aparecer).

### Tabela (revisão final, etapa 2a)
- Duplo clique no divisor do cabeçalho ajusta a largura da coluna ao conteúdo. As colunas não se esticam mais sozinhas (o Tk desfazia o ajuste); a rolagem horizontal mostra o resto.
- Coluna Título logo depois de Projeto / Sessão.
- Duplo clique numa sessão abre o painel de detalhes (antes abria "Salvar como"). Exportar continua no botão e no menu.
- Exportar e Dossiê ficam desabilitados, com o motivo, quando há mais de uma sessão selecionada (antes usavam só a primeira, sem aviso).
- Dicas nos alertas: contexto (nível, limites e o que fazer), falhas de ferramenta (onde ver os detalhes), retomada, título longo; no painel, falhas, workspace, estado e medidor.
- Dica do Workspace lista cada pasta com ✔ (existe) ou ✖ (não existe mais); antes dizia só "não existe mais", sem dizer qual, quando a sessão tinha várias pastas.

### Segurança e dados (revisão final, etapa 1)
- Máscara de segredos do dossiê cobre também chaves Stripe (`sk_live_`/`rk_test_`), JWT, tokens Slack (`xox…`), Google OAuth (`ya29.`), GitHub granular (`github_pat_`), `Authorization: Basic` e senha em URL (`postgres://usuário:[REDACTED]@host`). O dossiê agora vai dentro do prompt enviado ao modelo, então a máscara passou a importar mais.
- Estado em memória (quando a pasta de dados não aceita gravação) funciona também nas threads do Auto-Run e da exportação; antes dava `ProgrammingError` e o Auto-Run falhava.
- `settings.json` gravado de forma atômica: erro ou queda no meio não estragam as preferências.
- `gate.log` com rotação em ~1 MB (3 cópias antigas).

### Corrigido
- Dicas (tooltips) perto da borda direita saíam da janela (ex.: botão Sobre). Agora ficam dentro da janela e do monitor, e acima do botão se faltar espaço embaixo.
- **Sucesso falso do Auto-Run:** o `agy` sem janela não tem permissão para ler o arquivo do dossiê (`denied_actions: read_file`) e devolvia `SUCCESS` com resposta vazia, que o app aceitava como retomada. Agora resposta vazia é falha (com as ações negadas no log), e o dossiê vai **dentro do prompt** (até 20 mil caracteres; acima disso o meio é cortado e o caminho do arquivo é citado). Retomadas antigas gravadas como sucesso sem resposta são corrigidas ao abrir o app, e as sessões vazias delas vão para arquivadas (salvo marcação sua).
- Janela num monitor à esquerda (ou acima) do principal nunca tinha a posição gravada: o Windows informa a coordenada como `+-1928` e o app falhava ao ler. Por isso ela sempre reabria no monitor principal.
- Sessão que o `agy` cria numa tentativa com erro, sem informar o id, ficava como pendente. Agora o app compara a pasta de sessões antes e depois da chamada e arquiva o que surgiu numa tentativa que falhou.
- Workspace aparecia como `\c:\Users\...` (barra a mais): o Windows não reconhecia a unidade com `:` codificado (`%3A`). Com isso o Auto-Run não passava a pasta do projeto ao `agy` (`--add-dir`) e o painel marcava o workspace como inexistente.
- Lista de temas abria no monitor principal quando a janela estava num monitor à esquerda dele (coordenadas negativas). Agora abre sob o botão, no monitor da janela, e para cima se faltar espaço embaixo.
- Sucesso do `agy` agora exige código de saída 0, `conversation_id` preenchido e status diferente de `ERROR`. Antes, qualquer saída sem erro explícito contava como retomada. A saída bruta de cada chamada vai para o `gate.log`.
- Argumentos do `agy`: prompt numa linha só e por último; `--mode plan` e `--output-format json` vêm antes. Se o `agy` for um `.cmd`/`.bat` e os argumentos tiverem caracteres que o `cmd.exe` reinterpreta, o lote para sem executar e explica o motivo.
- Fechar a janela com Auto-Run ou exportação em andamento pergunta antes; se confirmar, cancela, encerra o `agy` e registra a falha antes de sair.
- Cancelar o Auto-Run fica registrado como "cancelada" (antes aparecia como "saída sem JSON").
- Exportações gravam num arquivo `.part` e só renomeiam no fim: erro ou cancelamento não deixam arquivo pela metade.

## [0.9.0] - 2026-10-26

Primeira versão neste repositório. Reúne tudo o que foi feito desde a auditoria do script original.

### Faltando para a 1.0.0
- Teste real do Auto-Run com o `agy` (só foi testado com um `agy` simulado; a cota do usuário estava esgotada).
- Revisão final do código e da documentação.
- Conferir no Windows do usuário: glifos Segoe MDL2, indicador "em execução", significado dos status 6 e 7, escala 125% a 150%, vários monitores.

### Leitura e curadoria
- Leitura somente-leitura dos bancos de sessão do Antigravity (`mode=ro`); estado próprio em `%LOCALAPPDATA%\AntigravityGate\`.
- Fontes separadas para ativas e backups (`.bak`, `bkp`, `backup`, `corrupt_quarantine`).
- Carga em segundo plano com cache; árvore de projetos e sub-agentes; busca (título, pasta, agente, UUID e conteúdo via FTS5); ordenação; menu de contexto.
- Estado de aprovação (pendente, aprovada, arquivada) com Desfazer.

### Exportação
- Diálogo completo e dossiê de retomada (com máscara de segredos por padrões conhecidos), lista de arquivos alterados e consultados com ícone por tipo e coluna "No disco".

### Auto-Run
- Retomada limpa (opção B): gera o dossiê e abre uma sessão nova com `agy --print --mode plan`; modo simulação; interrompe o lote em erro de cota.

### Interface
- 8 temas (Escuro, Claro e 6 inspirados no navigator-agy) com contraste WCAG AA; seletor em lista suspensa com amostra de cores.
- Botões desenhados em Canvas com estados e modo só ícone em janela estreita; ícones próprios nas linhas.
- Painel de detalhes com medidor de contexto; coluna Falhas; notificações com Desfazer; estados vazios com ação.
- Limites de contexto: 3 faixas prontas (Conservador, Equilibrado, Amplo) e personalizada, com alerta de nível crítico.
- Barra de título nativa nas cores do tema (Windows 10 1809+; cor exata no Windows 11).
- Janela principal e diálogos dentro da área útil do monitor (barra de tarefas em qualquer lado); tamanho e posição lembrados.

### Empacotamento
- `.exe` único gerado no GitHub Actions (PyInstaller, Windows), com autoteste do próprio `.exe` antes de publicar; Release automática ao criar uma tag `vX.Y.Z`.
