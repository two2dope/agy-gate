# Histórico de versões

Formato: [Versionamento Semântico](https://semver.org/lang/pt-BR/). Enquanto a versão começar com 0, o app está em candidato a lançamento: funciona, mas faltam itens listados abaixo.

## [Não lançado]

Correções dos três críticos da auditoria `reviews/audit-full-v0.9.0.md`, todos no Auto-Run.

### Adicionado
- Escolha do modelo do `agy` na confirmação do Auto-Run (`--model`; vazio = padrão do `agy`). Último valor e histórico ficam em `settings.json`.
- Janela **Sobre** (botão no cabeçalho e F1): versão, autor, e-mail, GitHub, projeto, aviso de independência e diagnóstico do ambiente com **Copiar informações**.

### Alterado
- Campo Modelo do Auto-Run vem com a lista de modelos aceitos pelo `agy` (o esforço faz parte do nome: `Gemini 3.8 Flash (Medium)`). Se o `agy` recusar um nome, o log mostra a lista que ele aceita e o app passa a oferecê-la.
- Botão Sobre só com o ícone (o texto aparece na dica, ou no botão quando o tema está sem ícones).
- Painel de detalhes: os quatro botões têm a mesma largura e o conteúdo centralizado.
- Ícone de Exportar: disquete (Segoe MDL2 `E74E`; `↧` no modo Unicode) no lugar da folha em branco. Glifo não visto num Windows.

### Corrigido
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
