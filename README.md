# AntigravityGate

Aplicativo de janela (Windows) para **gerir o contexto e curar as conversas do Antigravity**: lista as sessões, mostra o tamanho do contexto de cada uma, avisa quando está grande demais, deixa aprovar ou arquivar, e gera um **dossiê de retomada** para continuar o trabalho numa sessão nova sem perder o fio.

O app só **lê** os bancos do Antigravity. O que ele grava (estado, log, exportações) fica em `%LOCALAPPDATA%\AntigravityGate\`.

Versão atual: **0.9.0** (candidato a 1.0). Veja o [CHANGELOG](CHANGELOG.md).

## Como usar (sem instalar nada)

1. Abra a aba **Releases** deste repositório e baixe `AntigravityGate.exe` da versão mais recente.
   Se não houver Release, abra **Actions**, escolha a execução mais recente e baixe o artefato `AntigravityGate-windows` (um `.zip` com o `.exe`).
2. Dê dois cliques no `.exe`. O Windows pode mostrar o aviso azul do SmartScreen, porque o arquivo não é assinado: clique em **Mais informações** e depois em **Executar assim mesmo**.
3. O app abre já com as suas sessões (pasta `~/.gemini`). Para outra pasta, defina a variável de ambiente `ANTIGRAVITY_HOME` antes de abrir.

A conferência da integridade do download: a Release mostra o SHA-256 do `.exe`. No PowerShell: `Get-FileHash .\AntigravityGate.exe -Algorithm SHA256`.

## Principais recursos

- Tabela de sessões por projeto, com sub-agentes, contexto em tokens (medidor), passos e falhas de ferramenta.
- **Limites de contexto** (botão Limites): três faixas prontas e uma personalizada, com alerta de nível crítico.
- Painel de detalhes, busca (inclusive no conteúdo das conversas), ordenação e menu de contexto.
- **Diálogo completo** e **dossiê de retomada** em Markdown, com lista de arquivos alterados e consultados. O dossiê mascara chaves e senhas por padrões conhecidos (heurística: confira antes de compartilhar).
- **Auto-Run**: abre uma sessão nova no `agy` com o dossiê das sessões aprovadas (modo simulação disponível).
- 8 temas, botões com ícones e estados, barra de título que segue o tema.

## Rodar a partir do código

Precisa de Python 3.12 ou mais novo com `tkinter` (já vem no instalador do python.org para Windows).

```powershell
python AntigravityGate.py
```

Sem tela (Linux) para testes: `sudo apt install python3-tk xvfb`.

## Testes

```bash
tests/run_all.sh              # todos
tests/run_all.sh test_theme   # um só
```

São 15 conjuntos (leitura, exportação, Auto-Run com `agy` simulado, temas e contraste, janelas e interface). Usam bancos sintéticos; não tocam nos seus dados. Foram escritos e validados em Linux com Xvfb; não foram validados no Windows (o `agy` simulado usa a linha `#!` do arquivo).

## Gerar o `.exe` e publicar uma versão

- A cada push em `main`, o GitHub Actions monta o `.exe`, abre-o em modo de autoteste e guarda o artefato (30 dias).
- Para publicar uma versão: suba o número em `__version__` (`AntigravityGate.py`), registre no `CHANGELOG.md`, faça o commit em `main` e crie a tag `vX.Y.Z` com o mesmo número (por `git tag` e `git push --tags`, ou pela tela **Releases > Draft a new release**, digitando a tag e escolhendo *Create new tag on publish*). A Release recebe o `.exe`, o SHA-256 e as notas do CHANGELOG sozinha. Se a tag não bater com `__version__`, o build falha de propósito.
- Local: `packaging\build_exe.bat`.

## Estrutura

| Caminho | O que é |
|---|---|
| `AntigravityGate.py` | o app inteiro (arquivo único) |
| `tests/` | testes e o `agy` simulado |
| `tools/` | scripts de inspeção da estrutura dos bancos (sem conteúdo) |
| `docs/ESTADO_DO_PROJETO.md` | estado do projeto, decisões, formato dos bancos, contrato do `agy` |
| `reviews/` | auditoria do script original |
| `packaging/`, `.github/workflows/` | geração do `.exe` |

Para retomar o trabalho, leia a seção "Snapshot" de `docs/ESTADO_DO_PROJETO.md`.
