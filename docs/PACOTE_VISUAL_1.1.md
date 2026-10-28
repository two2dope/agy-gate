# 1.1 — pacote visual: avaliação dos mockups e plano

Registrado em 2026-10-27. Duas entregas do Google Stitch, enviadas pelo usuário (HTML com Tailwind e PNG de 1600×1280; ficaram fora do repositório; os scripts dos HTML só configuram o Tailwind, destacam a linha clicada e ligam o atalho da busca; não foram executados):

1. `stitch_desktop_interface_layout_variations.zip`: 4 skins (Vidro Aero, Cyber Synthwave, Mil-Spec, Mecha), tabela em cartões.
2. `stitch_multi_theme_ui_design_system.zip`: uma tela para cada uma das 8 skins do app e um `DESIGN.md` ("Obsidian Telemetry Aero") com tokens de cor, tipografia, espaçamento e componentes.

## Decisões do usuário (27/10)

| # | Decisão | Consequência |
|---|---|---|
| 1 | **Caminho A:** evolução em Tk | A tabela continua no Treeview; sem WebView |
| 2 | Aba "Em Revisão" vira **"Aprovadas aguardando"** | Sessões aprovadas sem retomada registrada (`gate_state.handoffs`). Mesmo número do selo do Auto-Run, que já desconta as retomadas |
| 3 | **Font Awesome, Bootstrap Icons e Material Icons ficam** | Três fontes de ícones no M1, além de Windows (MDL2), Unicode e sem ícones |
| 4 | **Tema padrão: "Dark Alloy"** (paleta Obsidian, azul-preto), no lugar do "Escuro" | Tokens na tabela "Tokens propostos". A chave interna `escuro` fica: quem já tem o tema salvo em `settings.json` continua nele |
| 5 | **Tabela padrão: Compacta** (1 linha por sessão) | O modo Confortável (2 linhas) fica como opção |
| 6 | **Barra lateral aberta ao abrir o app** | Ctrl+B recolhe durante o uso; o app abre sempre com ela aberta. Trilho automático só em janela estreita |

## O que vale manter (das duas entregas)

1. **Categorias na barra lateral** (Pendentes, Em atenção, Aprovadas, Arquivadas) com contadores. Hoje são selos no rodapé, pouco visíveis. É o maior ganho de uso.
2. **Coluna Consumo:** % do nível crítico, valor/limite, medidor de 5 blocos e rótulo da faixa ("segura", "atenção", "crítica"). Reforça os níveis de alerta da 1.0.2.
3. **Metadados e chip do id** (agente · origem · tempo relativo; `5c583e36`): a tabela fica escaneável.
4. **Retomada como relação** (`5c583e36: retomada`) na árvore de projetos. O Gate já grava a linhagem em `gate_state.handoffs`.
5. **Detalhes em cartão:** medidor com as marcas de atenção e crítico, grade de fatos (Estado, UUID, Workspace, Passos, Modificação, Tamanho, Falhas, Retomada) e os botões UUID, Pasta e Dossiê.
6. **Rodapé com selos coloridos** (pendentes, aprovadas, arquivadas, em atenção, críticas). O app já tem; muda só o estilo.

## Segunda entrega: o que mudou na leitura

- **6 das 8 telas usam uma linha por sessão** (Escuro, Vidro, Cyber, Mecha, Brutalista, Obsidiana). Só o Aero Quartz (claro) usa cartões, e o Mil-Spec usa título com subtítulo. O desenho convergiu para o que o Treeview faz: a fidelidade do caminho A sobe de ~65–70% para ~80% [estimativa].
- **Células de duas linhas funcionam no Treeview** (data sobre hora; passos sobre falhas; tamanho sobre UUID, como no Escuro): altura de linha maior e `\n` no valor. Verificado no Tk 9.0 deste ambiente; o `.exe` usa Tk 8.6 [conferir no M3]. Custo: a linha de 40 px do `DESIGN.md` mostra metade das sessões de hoje. Por isso, dois modos: **Compacto** (1 linha, padrão) e **Confortável** (2 linhas).
- **Limite que continua: cor por linha, não por célula** (Tk 8.6). O medidor colorido, o selo de estado colorido e o chip âmbar "⚠ 1" viram texto com glifo de 5 blocos (`▰▰▱▱▱`, que o `DESIGN.md` já prevê), cor da linha pelo nível e imagem de estado na coluna da árvore (bolinha colorida em PNG gerado, como os ícones atuais). A marca de 2 px à esquerda da linha selecionada não dá; fica a cor de seleção.
- **Coluna Ações (⋮):** dá, como coluna de texto que abre o menu de contexto no clique.
- **Fonte:** o Treeview usa uma fonte por estilo ou por linha, não por coluna. Cada skin escolhe a fonte da tabela inteira (Inter ou JetBrains Mono). A Inter tem algarismos proporcionais: colunas numéricas alinhadas à direita.

## Regra: skin muda tokens, não layout

- **Estrutura igual nas 8 skins:** barra lateral (recolhível), cabeçalho com abas, barra de ações, tabela, detalhes, rodapé. Vidro e Cyber vieram sem barra lateral, e o Brutalista com os contadores em grade 2×2: no app, isso é a barra recolhida, não um layout próprio.
- **Texto igual nas 8 skins.** O Stitch trocou rótulos por skin ("Classificação operacional", "Categorias de triagem", "Pendentes de Curadoria", "ALVO INSPEÇÃO ATIVO", "Gerar Dossiê"). Vale o texto do Escuro e do Claro.
- **A skin muda:** cores, fonte da tabela e dos títulos, raio, borda, caixa alta nos títulos (Mil-Spec, Brutalista).
- **Um só filtro:** abas (Todas / Aprovadas aguardando / Arquivadas) e categorias da barra lateral são atalhos para o mesmo filtro; o item ativo aparece marcado nos dois lugares. Sem isso, "Arquivadas" nas abas e na barra viram dois controles que discordam.

## Dados inventados nos mocks (não entram)

"Engine Online v2.18-ag", "HOST 127.0.0.1:8920", "PID 4092", "STORAGE NVMe FREE 48%", "SYS.ACTIVE // HUD: OPERATIONAL", "AERO_WORKSPACE // READY", "PROD-TELEMETRY", "v2.4.0-brutalist", "Buffer Livre 80%", "Agent assigned: orchestrator-main", subtítulos descritivos das sessões (Mil-Spec, Brutalista), limites de 64k, 128k e 200k (o app usa os de Limites) e contagens divergentes entre telas (Aprovadas 0, 1 ou 8; "Em Revisão 11"). O indicador do rodapé vira dado real: `agy` encontrado e daemon remoto, lido sem executar o `agy` (cada execução abre o editor do Antigravity; ver `ESTADO_DO_PROJETO.md`).

## Contraste (WCAG AA, 4,5:1)

Medido sobre a superfície mais clara onde o texto aparece (pior caso). **Nas 8 skins, o texto terciário falha:**

| Skin | Passa | Falha (usos no HTML) |
|---|---|---|
| Escuro (Obsidian) | slate-300 11,5; slate-400 6,7 | slate-500 3,6 (40); slate-600 2,3 (12) |
| Claro (Aero Quartz) | quartz-600 6,9; quartz-700 9,5 | quartz-500 4,3 (35); quartz-400 2,3 (35); âmbar-600 2,9; esmeralda-600 3,4; texto branco no botão primário `#0284c7` 4,1 |
| Vidro Aero | sky-200 12,6; sky-300/80 6,9 | sky-400/60 3,7 (15); sky-400/50 3,0 (14) |
| Cyber Synthwave | rosa 4,8; gray-400 7,1 | cinza `#717b9e` 4,3 (60); roxo `#8b5cf6` 4,3 (14) |
| Mil-Spec | gray-300 12,1; verde 7,9 | verde apagado `#52695c` 3,0 (54) |
| Mecha | slate-400 7,1; laranja 6,5 | slate-500 3,8 (17); slate-600 2,4 (6) |
| Brutalista | `#888` 5,2; amarelo 12,0 | `#777` 4,1 (15); `#666` 3,2 (25); `#555` 2,5 (28) |
| Obsidiana | slate-400 7,2; ametista clara 7,0; ametista 4,7 | slate-500 3,9 (13); slate-600 2,4 (16) |

Regra para o app: um só tom secundário (`muted`) por skin, com 4,5:1 sobre `bg`, `panel` e `panel2`. O `test_theme` barra o resto.

## Tokens propostos (rascunho para o M4)

Derivados dos mocks. Os 8 passam em todos os pares do `test_theme` (texto ≥ 4,5; ícone e barra da faixa de alerta ≥ 3). A última coluna traz o menor contraste de cada tema.

| Tema | bg · panel · panel2 · border | fg · muted | accent / texto do botão · accent_text | success · warning · danger | seleção | cabeçalho | menor |
|---|---|---|---|---|---|---|---|
| Dark Alloy (era Escuro) | `#07090e` `#0c0f17` `#161b2c` `#1e263d` | `#e2e8f0` `#94a3b8` | `#38bdf8` / `#04121f` · `#38bdf8` | `#34d399` `#fbbf24` `#f43f5e` | `#0c3a57` / `#ffffff` | `#0c0f17` / `#e2e8f0` | 4,89 |
| Claro | `#f1f5f9` `#ffffff` `#e9eef5` `#cbd5e1` | `#0f172a` `#475569` | `#0369a1` / `#ffffff` · `#0369a1` | `#047857` `#b45309` `#be123c` | `#e0f2fe` / `#0f172a` | `#ffffff` / `#0f172a` | 4,58 |
| Mil-Spec | `#070a09` `#0d1311` `#111916` `#2a4536` | `#e5e7eb` `#8aa597` | `#22c55e` / `#04140a` · `#4ade80` | `#4ade80` `#f59e0b` `#f87171` | `#243b31` / `#4ade80` | `#0d1311` / `#4ade80` | 4,65 |
| Cyber | `#070814` `#0d0f22` `#12142d` `#1e2348` | `#e6fbff` `#8e97b8` | `#00f3ff` / `#001418` · `#00f3ff` | `#4ade80` `#fbbf24` `#ff3d8b` | `#2a0a3d` / `#00f3ff` | `#0d0f22` / `#00f3ff` | 4,96 |
| Vidro | `#030b18` `#06132a` `#0a1d3d` `#1d4d6e` | `#e0f2fe` `#8fbfdf` | `#38bdf8` / `#04121f` · `#38bdf8` | `#34d399` `#fbbf24` `#fb7185` | `#0f3d66` / `#ffffff` | `#030b18` / `#e0f2fe` | 5,09 |
| Brutalista | `#000000` `#0b0b0b` `#141414` `#2a2a2a` | `#ffffff` `#999999` | `#facc15` / `#000000` · `#facc15` | `#4ade80` `#facc15` `#f87171` | `#262208` / `#facc15` | `#facc15` / `#000000` | 4,65 |
| Obsidiana | `#07050d` `#0b0816` `#151027` `#34295c` | `#f3ecff` `#a99dbd` | `#c084fc` / `#12081f` · `#c084fc` | `#34d399` `#fbbf24` `#f43f5e` | `#2b1646` / `#f3ecff` | `#07050d` / `#f3ecff` | 4,89 |
| Mecha | `#080a0e` `#0d1117` `#121620` `#323d53` | `#e2e8f0` `#94a3b8` | `#f97316` / `#1a0802` · `#ff8c38` | `#10b981` `#f59e0b` `#ef4444` | `#33200f` / `#fdba74` | `#0d1117` / `#f97316` | 4,99 |

O que muda em relação a hoje: **Escuro → Dark Alloy** (cinza do VS Code → azul-preto Obsidian), **Claro** (cinza neutro → ardósia com azul-céu), **Mil-Spec** (neutro → verde tático), **Brutalista** (borda branca e seleção amarela → borda `#2a2a2a` e seleção âmbar-escura com texto amarelo). Vidro, Cyber, Obsidiana e Mecha mudam pouco: os temas atuais já vinham de paletas parecidas (Cyber-HUD do navigator-agy). Os botões primários usam texto escuro sobre o acento: texto branco sobre azul-céu ou ametista não passa (o mock do Claro usa branco sobre `#0284c7`, 4,1; o Claro proposto usa `#0369a1`, 5,9).

## Tipografia e medidas (`DESIGN.md` → Tk)

- **Inter** (interface) e **JetBrains Mono** (métricas e UUID), em arquivos estáticos. Fonte variável no Windows: o GDI usa só a instância padrão [não verificado; usar estáticas evita a dúvida]. A Chakra Petch saiu: estava só na primeira entrega.
- Tamanhos de 10 a 16 px viram tamanhos negativos (pixels) no Tk, multiplicados pela escala do monitor.
- **Barra lateral:** o `DESIGN.md` pede 288 px, com trilho de 64 px abaixo de 1280 px de largura. Com a janela padrão de 1240 px, o app abriria sempre no trilho. No app: 232 px, aberta ao iniciar, recolhível (Ctrl+B), trilho automático abaixo de ~1100 px.
- Barra de título de 44 px: no Windows fica a barra nativa, que já segue o tema. Sub-cabeçalho de 48 px, rodapé de 28 px, botões de 28 px e raios de 0 a 16 px: viáveis (Canvas, como os botões atuais).
- Brilho, desfoque, vidro e transparência: não dão no Tk. Gradiente só como imagem gerada; fora da 1.1.

## Viabilidade no Tk (caminho A)

| Elemento | Dá no Tk? | Custo |
|---|---|---|
| Barra lateral com categorias, contadores e projetos (recolhível) | Sim (Frames + Canvas) | Médio |
| Abas segmentadas, Ctrl+K, Ctrl+B | Sim | Baixo |
| Fontes e ícones empacotados | Sim, no Windows | Médio |
| Cartão de detalhes, selos, chips | Sim (Canvas e PNG gerado) | Médio |
| Coluna Consumo como texto (% + 5 blocos + rótulo) | Sim | Baixo |
| Células de duas linhas (modo Confortável) | Sim (verificado no Tk 9.0; conferir no 8.6) | Baixo |
| Cor por célula, marca lateral da linha selecionada | Não no Tk 8.6 | — |
| Tabela em cartões (só no Claro) | Não com o Treeview; lista própria em Canvas | Alto (caminho B) |
| Brilho, desfoque, transparência, pulsação | Não (pulsação daria, mas distrai) | — |

## Marcos da 1.1 (caminho A)

1. **M1 — fontes e ícones** (M1a e M1b feitos em 27 e 28/10: ícones e fontes; subconjunto latino de ~190 KB, não os 2,5 MB estimados): Inter e JetBrains Mono; Font Awesome Free Solid (SIL OFL 1.1), Bootstrap Icons (MIT; vem em WOFF, converter para TTF) e Material Icons (Apache 2.0); registro privado no Windows (`AddFontResourceExW`, `FR_PRIVATE`) e `--add-data` no PyInstaller; seletor com 6 opções (Windows, Font Awesome, Bootstrap, Material, Unicode, sem ícones); licenças no Sobre e na pasta `licenses/`. Cerca de +2,5 MB no `.exe` [estimativa]. Fecha com o `.exe` do CI conferido no Windows: os glifos não aparecem no Linux deste ambiente.
2. **M2 — barra lateral e cabeçalho** (feito em 28/10; sem o trilho de ícones: abaixo de 900 px a barra se esconde; a fonte de dados continua no seletor do topo): categorias com contadores; projetos com sessões e retomadas; abas Todas / Aprovadas aguardando / Arquivadas sobre um filtro único; Ctrl+K na busca; Ctrl+B recolhe a barra; o app abre com a barra aberta.
3. **M3 — tabela e detalhes:** coluna Consumo; estado com bolinha colorida; modos Compacto (padrão) e Confortável; coluna Ações; cartão de detalhes com medidor e marcas.
4. **M4 — skins e acabamento** (tokens das 8 skins feitos em 28/10; faltam o indicador do `agy` e do daemon e o ícone autoral): tokens da tabela acima (Dark Alloy como tema padrão, no lugar do Escuro), fonte e raio por skin, contraste testado; indicador do `agy` e do daemon; ícone autoral do app.

Cada marco fecha com o `.exe` montado no CI e conferência no Windows. O código da 1.1 começa depois do merge da 1.0.2.

## MCP do Stitch

**Parecer: não vale agora.**

- O caminho A não consome o HTML: usa tokens, medidas e layout, e o zip com o `DESIGN.md` já traz isso.
- Cada geração nova inventa dados e troca textos (lista acima). Mais material pede mais curadoria.
- Exigiria a chave do Stitch neste ambiente. A anterior vazou na saída de um script e foi revogada.
- Passa a valer para telas que faltam no estilo novo: Limites, confirmação e andamento do Auto-Run, Sobre, menu de contexto, estados vazio e de erro, faixa e dica de alerta. Mesmo nesse caso, gerar no Stitch e mandar o zip funciona sem chave aqui.

## Decisões pendentes do usuário

Nenhuma. As três que restavam foram fechadas em 27/10 (itens 4 a 6 da tabela de decisões).

Fora da 1.1: o tema **Crimson Matrix**, citado no `DESIGN.md` sem tela. Seria o 9º tema; só entra no lugar de outro.
