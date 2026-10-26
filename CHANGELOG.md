# Histórico de versões

Formato: [Versionamento Semântico](https://semver.org/lang/pt-BR/). Enquanto a versão começar com 0, o app está em candidato a lançamento: funciona, mas faltam itens listados abaixo.

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
