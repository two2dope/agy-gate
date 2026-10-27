# 1.1 — pacote visual: avaliação dos mockups

Registrado em 2026-10-27. Fonte: `stitch_desktop_interface_layout_variations.zip`, enviado pelo usuário: 4 telas geradas no Google Stitch (HTML com Tailwind e PNG de 1600×1280), uma por skin: Vidro Aero, Cyber Synthwave, Mil-Spec e Mecha. Os arquivos ficaram fora do repositório. Os scripts deles só configuram o Tailwind, destacam a linha clicada e ligam o atalho Ctrl+K.

## O que os mockups propõem (comum às 4 skins)

| Área | Proposta |
|---|---|
| Barra lateral | Fonte de dados; **Categorias** (Pendentes, Em Atenção, Aprovadas, Arquivadas) com contadores; **Projetos & Espaços** com contadores; o projeto aberto lista as sessões com um ponto de estado |
| Cabeçalho | Marca + "Gestão de contexto e curadoria"; abas **Todas as Sessões / Em Revisão / Arquivadas**; Atualizar, Limites, tema, Sobre |
| Busca | Campo com atalho (⌘K no mock; Ctrl+K no Windows) e limpar |
| Ações | Aprovar, Arquivar, Pendente · Exportar Diálogo, **Dossiê de Retomada** (botão primário), Auto-Run |
| Tabela | Linhas em **cartão**: caixa de seleção; projeto + selo de estado; chip do id (`5c583e36`) + título + linha de metadados (agente · CLI · há 19 horas); data e hora em duas linhas; **Consumo**: % do nível crítico, `146.624/250k`, barra e rótulo da faixa ("faixa segura") |
| Detalhes | Cartão com projeto, agente, título, medidor com as marcas 150k/250k, grade de fatos (Estado, UUID, Workspace, Passos, Modificação, Tamanho, Falhas, Retomada) e botões UUID, Pasta, Dossiê |
| Rodapé | Indicador "Engine Online v2.18-ag"; fonte, contagem e selos |
| Estilo | Fontes Inter + JetBrains Mono (Chakra Petch no Mecha); ícones **Font Awesome 6**; gradientes, brilho, desfoque e pulsação |

## O que vale manter

1. **Categorias na barra lateral.** Hoje são selos no rodapé, pouco visíveis. Como navegação principal, com contadores, é o maior ganho de uso.
2. **Coluna Consumo** com % do nível crítico, valor/limite e rótulo da faixa. Lê-se melhor que `■■■□□□` e reforça os níveis de alerta da 1.0.2.
3. **Linha de metadados** (agente · origem · tempo relativo) e **chip do id**: a tabela fica escaneável.
4. **Retomada visível como relação** (`5c583e36: retomada`). O Gate já grava a linhagem em `gate_state.handoffs`.
5. **Font Awesome** como conjunto de ícones do layout novo. É o pedido A, e o mock já usa.

## O que precisa de ajuste

| Ponto | Por quê | Proposta |
|---|---|---|
| Aba **"Em Revisão"** | O Gate não tem esse estado (só pendente, aprovada, arquivada) | **Decisão do usuário:** virar "Aprovadas aguardando Auto-Run" ou sair |
| Densidade | Cartões de ~110 px mostram ~6 sessões por tela (hoje ~20). Com 57 sessões, 3× mais rolagem | Modo compacto e confortável |
| Contraste | Textos secundários e linha arquivada em cinza escuro sobre quase preto ficam abaixo de 4,5:1 | Ajustar os tokens; o `test_theme` já barra |
| Painel de detalhes da variante 1 | Textos sobrepostos (falha do gerador) | Usar o das variantes 2 a 4 |
| "Engine Online v2.18-ag" | Não existe "engine" no Gate | Virar um indicador real: `agy` encontrado (versão) e daemon remoto (`dev-thomaz`). Ler sem chamar o `agy`, que abre o editor a cada chamada **[conferir]** |
| Semáforo do macOS no topo | Elemento do mock | No Windows fica a barra nativa, que já segue o tema (decisão anterior) |
| Só 4 skins | O app tem 8 (faltam Escuro, Claro, Brutalista, Obsidiana) | Derivar dos tokens. O **Claro** precisa de desenho próprio: os 4 mocks são escuros |
| Fontes | Inter, JetBrains Mono, Chakra Petch e Font Awesome não vêm no Windows | Empacotar no `.exe` (SIL OFL 1.1) com registro privado (`AddFontResourceExW`, `FR_PRIVATE`), a mesma base do pedido A |

## Viabilidade no Tk (tecnologia atual)

| Elemento | Dá no Tk? | Custo |
|---|---|---|
| Barra lateral com categorias, contadores e projetos | Sim (Frames + Canvas) | Médio |
| Abas segmentadas, Ctrl+K | Sim | Baixo |
| Fontes e ícones empacotados | Sim, no Windows | Médio |
| Cartão de detalhes, selos, chips | Sim (Canvas e PNG gerado, como os ícones atuais) | Médio |
| Coluna Consumo **como texto** (% + medidor em células + rótulo) dentro do Treeview | Sim | Baixo |
| **Tabela em cartões** (2 linhas, selos e barra por linha, caixa de seleção) | **Não com o Treeview.** Exige uma lista própria em Canvas, refazendo seleção, teclado, ordenação, menu, dicas e rolagem | **Alto** (~800–1.200 linhas + testes); risco de regressão |
| Gradientes | Só como imagem gerada | Médio |
| Brilho, desfoque, transparência | **Não** | — |
| Pulsação | Possível com `after`, mas gasta e distrai | Não recomendo |

## Caminhos

| Caminho | O que entrega | Fidelidade ao mock | Custo | Risco |
|---|---|---|---|---|
| **A. Evolução em Tk** (recomendado para a 1.1) | Barra lateral, abas, fontes, Font Awesome, coluna Consumo em %, detalhes em cartão, indicador do `agy`/daemon. A tabela continua com uma linha por sessão | ~65–70% | Médio | Baixo |
| **B. Tk com lista em cartões** (1.2, se A agradar) | A + tabela em cartões | ~85% | Alto | Médio-alto |
| **C. Interface web** (2.0) | Janela WebView2 (pywebview) com o próprio HTML/Tailwind do Stitch, compilado sem CDN; Python como backend | ~100% | Muito alto: reescrever ~2.500 linhas de interface e os testes de UI | Alto; depende do WebView2 **[não verificado na máquina do usuário]** |

**Recomendação:** A agora. Ele entrega o grosso do ganho de uso (categorias, consumo legível, fontes e ícones) com risco baixo. O que A não alcança é sobretudo efeito visual (brilho, desfoque) e as linhas em cartão. Decidir B ou C só depois de usar A.

## Marcos sugeridos para a 1.1 (caminho A)

1. **M1 — fontes e ícones:** Inter, JetBrains Mono e Font Awesome empacotadas; seletor de conjunto de ícones; créditos de licença no Sobre.
2. **M2 — barra lateral e cabeçalho:** fonte de dados, categorias com contadores, projetos; abas; Ctrl+K.
3. **M3 — consumo e detalhes:** coluna Consumo em % com rótulo da faixa; cartão de detalhes no estilo novo.
4. **M4 — skins e acabamento:** tokens novos nas 8 skins (Claro com desenho próprio), contraste AA testado, indicador do `agy`/daemon, ícone autoral do app.

Cada marco fecha com `.exe` montado no CI e conferência no Windows.

## Decisões pendentes do usuário

1. Caminho A, B ou C.
2. O que é a aba "Em Revisão" (ou se sai).
3. Bootstrap Icons e Material Icons continuam no escopo? O mock usa só Font Awesome. Tirar os dois corta custo de M1.
