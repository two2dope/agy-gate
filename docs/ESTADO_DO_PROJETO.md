# AntigravityGate: estado do projeto

Atualizado em 2026-10-26. Ao retomar, leia só a seção "Snapshot".

## Snapshot

| | |
|---|---|
| **Feito** | M1 (honestidade e robustez), seletor de fontes (ativas e backups separados), M2 (carga em segundo plano, cache, alerta por tokens), M3a (estado de aprovação), M3b (árvore de sub-agentes, busca, ordenação, menu de contexto) |
| **Faltando** | M4 (export fiel e dossiê de retomada), Auto-Run opção B |
| **Próximo passo único** | M4 |

Ordem combinada: M4, depois Auto-Run. O Auto-Run depende do M4.

## Decisões tomadas

- O app só lê os bancos do Antigravity (`mode=ro`). O estado fica em `%LOCALAPPDATA%\AntigravityGate\gate_state.db`.
- Padrão de leitura: `antigravity\conversations`. Backups (`.bak`, `bkp`, `backup`, `corrupt_quarantine`) aparecem como fontes separadas no seletor.
- Alerta de Context Rot por tokens da última resposta (`f2 + f5`), limite em `ROT_TOKENS` (padrão 150000, variável `AGY_ROT_TOKENS`). O limite é provisório.
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

## Pendências do usuário

- Quando a cota voltar (cerca de 31 h após 2026-10-26), repetir o teste `agy --print "responda apenas: ok" --output-format json --mode plan --print-timeout 60s` para ver o formato de sucesso.
- Escolher o limite do alerta Rot em tokens.
- Dizer se quer o dossiê só com extração local (padrão, sem usar cota) ou também com resumo feito pelo modelo.

## Como testar

Os testes rodam em Xvfb com Python 3.12 e `python3-tk`. Estão fora do repositório, no diretório temporário da sessão. Os scripts `tools/inspect_*.py` dão a estrutura (sem conteúdo) de qualquer banco de sessão.
