# Histórico de versões

Formato: [Versionamento Semântico](https://semver.org/lang/pt-BR/). Enquanto a versão começar com 0, o app está em candidato a lançamento: funciona, mas faltam itens listados abaixo.

## [1.2.2] - 2026-11-05

Ajustes no dossiê, vistos ao ler os dossiês das sessões de 28 e 29/10 (pasta `handoffs`).

### Corrigido
- **Resposta do modelo trocada pelo raciocínio interno.** O app lia o campo `f20.f3` como a resposta do modelo, mas ele guarda o raciocínio interno; a resposta que o usuário vê está em `f20.f1` (com cópia em `f20.f8`). Afetava a "Última resposta do modelo" do dossiê e todo o diálogo completo. Conferido nas 65 sessões locais em 05/11. Agora o diálogo mostra a resposta e, acima dela, o raciocínio marcado como "Raciocínio interno do modelo". O dossiê mostra a última resposta visível; quando o modelo ainda pensou depois dela (ou nunca respondeu), o último raciocínio aparece em citação, avisando que a sessão parou no meio.
- **Campo "Modelo(s)" vazio.** As versões atuais do Antigravity gravam o nome em `gen_metadata` `f3.f28` (ex.: `gemini-3.8-flash-high`), e nem toda linha o traz. O app agora lê esse campo (e o antigo `f21`) nas 10 primeiras e nas 10 últimas linhas.

### Adicionado
- **Seção "Artefatos da sessão" no topo do dossiê:** os documentos que o agente deixou em `brain/<id>/` (relatórios, planos, handoffs), com tamanho e data. Antes eles ficavam perdidos no meio de centenas de scripts temporários.

### Alterado
- **Arquivos temporários do agente recolhidos numa linha.** Scripts em `brain/<id>/scratch` e saídas em `.system_generated` saem das tabelas "Arquivos alterados" e "Arquivos consultados" do dossiê e viram uma contagem (quantos ainda estão no disco). O diálogo completo continua com a lista inteira.

## [1.2.1] - 2026-11-05

### Alterado
- **Cabeçalho alinhado com o painel de sessões.** A marca (ícone e nome) fica isolada na esquerda, numa coluna com a largura da barra lateral e separada por uma linha; as abas começam onde começa o painel de sessões (alinhadas com a busca e a tabela) e os botões terminam na mesma borda direita. Sem a barra lateral, a marca volta a ocupar só o espaço do nome.

## [1.2.0] - 2026-11-04

Ajustes pedidos depois de usar a 1.1.0. Marcos: M1 recibo de retomada; M2 janela única do Auto-Run.

### Adicionado
- **Recibo de retomada.** Na sessão retomada, clicar em "↪ … ver recibo" nos detalhes (ou "Ver recibo da retomada" no menu da sessão) abre o recibo: sessão original e nova, projeto, modelo, pasta de trabalho, duração, turnos, tokens, dossiê e a resposta completa do agy. Dá para copiar e **salvar em arquivo** (Markdown ou texto). A resposta passa pela máscara de segredos. O Auto-Run passa a gravar esses campos; retomadas de versões anteriores mostram o que existe e "não registrado" no resto (a resposta, nelas, é só o começo).

- **Janela do Auto-Run reescrita: uma só, em três etapas.** 1 Preparar (marcar as sessões, simulação ou retomada real, modelo, **pasta dos dossiês**), 2 Executando (lista com o estado de cada sessão: aguardando, rodando, retomada, dossiê gerado, falhou, não executada) e 3 Resumo. Clicar numa sessão mostra o detalhe: onde a nova será criada, sessão nova, pasta, projeto, modelo, duração, tokens, motivo da falha, o que aconteceu e a resposta; duplo clique (ou "Ver recibo") abre o recibo. **Salvar relatório…** grava o resumo do lote em Markdown. O registro completo continua na janela, recolhido.
- **Pasta dos dossiês escolhível** (Escolher… e Padrão), lembrada entre execuções. É também a pasta de trabalho das sessões sem projeto.

### Alterado
- **Cabeçalho e busca com menos texto.** A marca virou o ícone e o nome (a descrição "Gestão de contexto e curadoria" foi para a dica ao passar o mouse). As abas ganharam sublinhado na marcada e um selo de contagem em "Aprovadas aguardando" (a aba "Todas as sessões" passou a "Todas"). A busca ocupa a linha inteira, com a dica dentro do campo, e Buscar e Limpar ficaram só com ícone. A **fonte das sessões** foi para o topo da barra lateral; sem a barra (Ctrl+B ou janela estreita), o seletor volta para a linha da busca.

### Corrigido
- As janelas de confirmação e de andamento do Auto-Run se sobrepunham e fechar uma delas podia travar. Agora é uma janela só: iniciar outro lote a reaproveita. Esc fecha nas etapas 1 e 3; na 2 não, para não cancelar o lote sem querer.

## [1.1.0] - 2026-10-29

Pacote visual (plano em `docs/PACOTE_VISUAL_1.1.md`). Marcos M1 (ícones e fontes), M2 (barra lateral), M3 (tabela) e M4 (cores, ambiente e ícone do app).

### Adicionado
- **Fontes Inter (interface) e JetBrains Mono (texto de código, andamento do Auto-Run e títulos do Mil-Spec, Cyber e Mecha)**, dentro do `.exe` (subconjunto latino, cerca de 190 KB, SIL OFL 1.1). Sem elas (fora do Windows), o app usa Segoe UI e Consolas, como antes.
- **Três conjuntos de ícones novos, com as fontes dentro do `.exe`:** Font Awesome Free 6.7.2 (Solid), Bootstrap Icons 1.11.3 e Material Icons 4.0.0. Escolha em Tema > Ícones. As fontes são registradas só para o app: nada é instalado no Windows. Sem a fonte (fora do Windows), os botões usam os símbolos Unicode.
- Licenças das fontes em `fonts/` e créditos no Sobre. O autoteste do `.exe` no CI confere que as 7 fontes (ícones, Inter e JetBrains Mono) foram registradas.

- **Barra lateral** (220 px, aberta ao iniciar): categorias (pendentes, em atenção, críticas, aprovadas, arquivadas) com contagem e projetos com contagem. Clicar numa categoria filtra a tabela (é o mesmo filtro dos selos do rodapé); clicar num projeto leva a tabela até ele. Ctrl+B recolhe; abaixo de 900 px de largura ela se esconde sozinha.
- **Abas no cabeçalho:** Todas as sessões, **Aprovadas aguardando** (aprovadas ainda sem retomada: o que o Auto-Run vai pegar, com a contagem) e Arquivadas. São atalhos para o mesmo filtro: um só filtro vale de cada vez, marcado nas abas, na barra lateral e nos selos. Abaixo de 1000 px as abas somem.
- **Ctrl+K** vai ao campo de busca (como o Ctrl+F).
- **Coluna Consumo** (antes Contexto): tokens, % do nível crítico, medidor de 5 células (eram 6) e a marca ⚠ ou ‼.
- **Densidade da tabela** em Tema > Tabela: **compacta** (1 linha por sessão, padrão) ou **confortável** (2 linhas: data e hora; tokens e %, medidor e faixa). Lembrada entre execuções.
- **Coluna ⋮ (Ações):** clicar abre o menu da sessão, como o botão direito.
- A coluna **Agente** deixou de aparecer na tabela (o agente continua nos detalhes e na busca) e as larguras das colunas diminuíram: com a barra lateral aberta, as colunas até ⋮ cabem numa janela de 1300 px.

- **Ícone do app** (um portal em arco com o medidor de três níveis): no `.exe`, na barra de tarefas e nas janelas. Gerado por `tools/make_icon.py`.
- **Ambiente na barra lateral:** mostra se o `agy` foi encontrado e se o daemon do remote control inicia no login (procura `remote-control` na chave Run do Windows). Só leitura: não executa o `agy`, que abre o editor a cada chamada. Atualiza com F5. Mostra o registro, não se o daemon está online.

### Alterado
- **Cores das 8 skins** refeitas a partir do pacote visual (Stitch). O tema padrão **Escuro** passa a se chamar **Dark Alloy** (azul-preto, paleta Obsidian); a preferência salva continua valendo. O **Claro** vira ardósia com azul-céu, o Mil-Spec ganha o verde tático, o Brutalista troca a borda branca por cinza e a seleção amarela por âmbar escuro. O texto secundário, que ficava abaixo de 4,5:1 nas 8 skins dos mockups, foi reajustado: contraste conferido pelo `test_theme`.

### Corrigido
- A janela de andamento do Auto-Run continuava com o título "executando" depois do "Fim.". Agora mostra "concluído", "concluído com problemas" ou "erro".
- Resumo do Auto-Run no singular quando o número é 1 ("1 retomada", "1 falha").
- A lupa da busca não acompanhava a troca do estilo de ícones.

## [1.0.2] - 2026-10-27

Alerta de contexto em destaque. Entra no lugar do item 8 do backlog (divisor de altura entre a tabela e os detalhes).

### Alterado
- **Dica do contexto como janela de alerta.** Ao parar o mouse sobre o contexto de uma sessão em atenção ou crítica (na tabela ou no medidor do painel), a dica vem com as cores do nível (vermelho forte ou âmbar), ícone grande e título "CRÍTICO" ou "ATENÇÃO". Sessões no nível normal continuam com a dica comum.
- **Faixa de alerta em dois níveis.** Crítico: fundo vermelho do tema, forte, com texto claro, ícone grande, título "CRÍTICO · N sessão(ões) acima do nível crítico" e o que fazer na linha de baixo. Atenção (novo): faixa âmbar suave, "ATENÇÃO · N sessão(ões) acima do nível de atenção", que só aparece quando não há críticas, com o botão `Ver em atenção`. Barra colorida à esquerda nos dois níveis. Como antes, a faixa some enquanto há busca ou filtro de selo.
- Dispensar vale para o nível exibido: a faixa volta se mudar a fonte ou os limites.
- Contraste das duas faixas (e das dicas de alerta) conferido nos 8 temas (texto ≥ 4,5:1; ícone e barra ≥ 3:1). O vermelho escurece o mínimo necessário para o texto claro passar.

### Corrigido
- **Janelas de andamento do Auto-Run.** Rodar um segundo Auto-Run com a janela do anterior aberta criava outra janela, e o Fechar e o X da antiga passavam a agir sobre a nova (a antiga não fechava, e podia até cancelar o lote novo). Agora fica uma janela por vez (a anterior fecha) e cada uma age só sobre si.
- A janela de andamento abria atrás da principal. Agora fica sempre acima dela (`transient`) e recebe o foco ao abrir.

## [1.0.1] - 2026-10-27

Correção do crítico C1 da auditoria `reviews/audit-full-v1.0.0.md`: a retomada do Auto-Run nascia fora do projeto da sessão original.

### Corrigido
- **Retomada no projeto de origem.** Sem `--project`, o `agy` põe toda sessão do CLI em "CLI Project", qualquer que seja a pasta (CHANGELOG oficial do `agy`, versão 1.0.12). As retomadas da 1.0.0 apareciam no remoto em "CLI Project" e, na busca do VS Code, com a pasta `handoffs`. Agora o Auto-Run passa `--project <id>` quando o projeto da sessão original existe em `config/projects` (fora disso, nada muda: o `agy` usa "CLI Project").
- **Pasta de trabalho do `agy`.** O `agy` registra a pasta de trabalho como workspace da sessão. O app não a definia, e a sessão nova herdava a pasta de onde o `.exe` foi aberto (ex.: `Downloads\AntigravityGate-windows`). Agora o `agy` roda na pasta do projeto (a do `config/projects` primeiro, depois as do workspace original); sem nenhuma, em `handoffs`.
- **Sem `handoffs` como workspace.** O dossiê já vai no prompt, então a pasta `handoffs` deixou de entrar como `--add-dir` (continua no modo antigo, em que o prompt manda ler o arquivo).
- Pastas do próprio app (dados em `%LOCALAPPDATA%\AntigravityGate` e qualquer pasta com `AntigravityGate.exe`) não são repassadas ao `agy`, nem quando vêm do workspace de uma retomada antiga.
- JSON de projeto com BOM (gravado pelo PowerShell 5.1) era "Projeto ilegível". Agora é lido.

### Alterado
- O andamento do Auto-Run mostra, para cada sessão, a pasta de trabalho e o projeto de destino. Vale também na simulação, que confere o destino sem gastar cota.

## [1.0.0] - 2026-10-27

Primeira versão estável. Critérios cumpridos: revisão final (auditoria `reviews/audit-full-v0.9.0.md`, críticos C1 a C3 e as recomendações das etapas 1 a 3) e Auto-Run real testado no Windows (retomada `a56f46f0` → `5c583e36` com resposta completa, dossiê no prompt).

Ainda não verificado no Windows: escala 125% a 150%, glifos Segoe MDL2 em todos os botões, significado dos status 6 e 7 das ferramentas. O editor do Antigravity abre sozinho a cada chamada do `agy` (comportamento do `agy`, sem opção para evitar).

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

### Blindagem (revisão final, etapa 3)
- Testes rodam no GitHub antes da montagem; teste vermelho barra o `.exe`. O executor exige código de saída 0.
- PyInstaller com versão fixa (6.22.3). Escrita no repositório só no job que publica a Release.
- Release em rascunho primeiro: anexa o `.exe`, confere, e só então publica; cada chamada do `gh` é conferida; notas e marcações feitas na tela são preservadas.
- Revisão de código de todo o branch. Corrigido: resposta do `agy` ia para o `gate.log` sem máscara de segredos; conversa aberta por você durante uma tentativa com erro podia ser arquivada (agora só arquiva sessão cuja primeira fala é o prompt do Auto-Run); "basic" em texto comum era mascarado; menu do botão direito exportava a primeira de várias selecionadas; filtro de selo desatualizava ao marcar; dica podia apontar para linha recriada; notificações vizinhas confundiam a pausa.
- **Maximizar nunca funcionou:** o atributo `self.state` (estado das sessões) escondia o método `state()` do Tk. Agora usa `wm_state`.

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
