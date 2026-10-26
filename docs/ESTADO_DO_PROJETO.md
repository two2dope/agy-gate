# AntigravityGate: estado do projeto

Atualizado em 2026-10-26, versão **0.9.0**. Repositório próprio: `two2dope/agy-gate` (privado), separado do `zuvuya`. Ao retomar, leia só a seção "Snapshot".

## Snapshot

| | |
|---|---|
| **Feito** | M1 a M4 (leitura, estado, exportação, dossiê), Auto-Run opção B (testado só com `agy` simulado), `.exe` no GitHub Actions com autoteste, interface visual completa (8 temas, ícones, painel de detalhes, notificações, limites de contexto, janelas dentro da área útil do monitor, barra de título nos temas), repositório próprio com testes, README, CHANGELOG e Release automática por tag |
| **Faltando** | Teste real do Auto-Run com o `agy` (cota; depois de 27/10; começar com lote de 1 sessão e conferir o `gate.log`); revisão final (auditoria feita: `reviews/audit-full-v0.9.0.md`, críticos C1 a C3 corrigidos; recomendações pendentes); conferir no Windows do usuário os itens "Não verificado" abaixo; decisão do limite Rot |
| **Próximo passo único** | Revisão final (critério da 1.0.0: revisão feita + Auto-Run real testado) |

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
- Opções úteis: `--mode plan|accept-edits|auto`, `--add-dir`, `--project`, `--print-timeout`, `--effort`, `--model`, `--conversation` (retoma e muda a conversa original).
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

`tests/run_all.sh` (precisa de Python 3.12 com `tkinter` e, sem tela, `xvfb`). São 16 conjuntos com bancos sintéticos e um `agy` simulado (`tests/fake_agy.py`). Os scripts `tools/inspect_*.py` dão a estrutura (sem conteúdo) de qualquer banco de sessão.

## Versões

- `__version__` em `AntigravityGate.py` é a fonte da versão (aparece na dica do cabeçalho, no log e no autoteste do `.exe`). Histórico em `CHANGELOG.md`.
- Publicar: subir `__version__`, registrar no CHANGELOG, commit em `main`, tag `vX.Y.Z` igual. O workflow confere a tag contra `__version__`, monta o `.exe`, testa e cria a Release (marcada como pré-lançamento enquanto a versão começar com 0).
- 0.9.0 = candidato a 1.0.0.

## Auto-Run (implementado)

- Botão `⚡ Auto-Run`: pega as sessões **aprovadas** da fonte aberta, pede confirmação (simulação marcada por padrão) e, para cada uma, gera o dossiê em `%LOCALAPPDATA%\AntigravityGate\handoffs` e abre uma sessão nova com `agy --print ... --mode plan --output-format json`.
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
- **Atenção:** linha em âmbar, `⚠`. **Crítico:** linha em vermelho, `‼`, mais um **aviso** acima da tabela com os botões `Ver críticas` (lista só as críticas) e `Dispensar`. O aviso não conta sessões arquivadas. Ele volta se você mudar o limite ou a fonte.
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
