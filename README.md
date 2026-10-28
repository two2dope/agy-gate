# AntigravityGate

Aplicativo de janela (Windows) para **gerir o contexto e curar as conversas do Antigravity**: lista as sessões, mostra o tamanho do contexto de cada uma, avisa quando está grande demais, deixa aprovar ou arquivar, e gera um **dossiê de retomada** para continuar o trabalho numa sessão nova sem perder o fio.

O app só **lê** os bancos do Antigravity. O que ele grava (estado, log, exportações) fica em `%LOCALAPPDATA%\AntigravityGate\`.

Versão atual: **1.0.2**. Veja o [CHANGELOG](CHANGELOG.md).

## Como usar (sem instalar nada)

1. Abra a aba **Releases** deste repositório e baixe `AntigravityGate.exe` da versão mais recente.
   Se não houver Release, abra **Actions**, escolha a execução mais recente e baixe o artefato `AntigravityGate-windows` (um `.zip` com o `.exe`).
2. Dê dois cliques no `.exe`. O Windows pode mostrar o aviso azul do SmartScreen, porque o arquivo não é assinado: clique em **Mais informações** e depois em **Executar assim mesmo**.
3. O app abre já com as suas sessões (pasta `~/.gemini`). Para outra pasta, defina a variável de ambiente `ANTIGRAVITY_HOME` antes de abrir.

A conferência da integridade do download: a Release mostra o SHA-256 do `.exe`. No PowerShell: `Get-FileHash .\AntigravityGate.exe -Algorithm SHA256`.

## Principais recursos

- Tabela de sessões por projeto, com sub-agentes, contexto em tokens (medidor), passos e falhas de ferramenta.
- **Limites de contexto** (botão Limites): três faixas prontas e uma personalizada. Alerta acima da tabela em dois níveis: crítico (vermelho, em destaque) e atenção (âmbar).
- Barra lateral (categorias e projetos, Ctrl+B) e abas no cabeçalho (Todas, Aprovadas aguardando, Arquivadas) sobre um filtro só.
- Coluna Consumo (tokens, % do nível crítico, medidor) e tabela compacta ou confortável; coluna ⋮ com o menu da sessão.
- Painel de detalhes, busca (inclusive no conteúdo das conversas), ordenação e menu de contexto.
- **Diálogo completo** e **dossiê de retomada** em Markdown, com lista de arquivos alterados e consultados. O dossiê mascara chaves e senhas por padrões conhecidos (heurística: confira antes de compartilhar).
- **Auto-Run**: abre uma sessão nova no `agy` com o dossiê das sessões aprovadas, no projeto e na pasta da sessão original (modo simulação disponível). O app não grava nos bancos do Antigravity, mas cada sessão nova que o `agy` cria fica neles.
- 8 temas; ícones em 6 estilos (Windows, Font Awesome, Bootstrap, Material, Unicode ou nenhum), com as fontes dentro do `.exe`; barra de título que segue o tema.

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

São 26 conjuntos (leitura, exportação, Auto-Run com `agy` simulado, salvaguardas do Auto-Run e do fechamento, temas e contraste, janelas e interface). Usam bancos sintéticos; não tocam nos seus dados. Foram escritos e validados em Linux com Xvfb; não foram validados no Windows (o `agy` simulado usa a linha `#!` do arquivo).

## Gerar o `.exe` e publicar uma versão

- A cada push em `main`, o GitHub Actions monta o `.exe`, abre-o em modo de autoteste e guarda o artefato (30 dias).
- Os testes (`tests/run_all.sh`) rodam primeiro no GitHub; se algum falhar, o `.exe` não é montado.
- Para publicar uma versão: suba o número em `__version__` (`AntigravityGate.py`), registre a seção `## [X.Y.Z]` no `CHANGELOG.md`, faça o commit em `main` e envie a tag: `git tag vX.Y.Z` e `git push --tags`. O workflow cria a Release como **rascunho**, anexa o `.exe` e o SHA-256, confere e só então publica. Se a tag não bater com `__version__`, ou faltar a seção no CHANGELOG, nada é publicado.
- Pela tela (**Releases > Draft a new release**, *Create new tag on publish*) também funciona, mas a Release fica pública **antes** do `.exe` (alguns minutos) e, se a versão não bater, fica sem ele: apague-a nesse caso. Suas notas e marcações da tela são mantidas; o workflow só acrescenta o `.exe` e o SHA-256.
- Local: `packaging\build_exe.bat`.

## Estrutura

| Caminho | O que é |
|---|---|
| `AntigravityGate.py` | o app inteiro (arquivo único) |
| `tests/` | testes e o `agy` simulado |
| `fonts/` | fontes de ícones, Inter e JetBrains Mono (empacotadas no `.exe`) e suas licenças |
| `tools/` | scripts de inspeção da estrutura dos bancos (sem conteúdo) |
| `docs/ESTADO_DO_PROJETO.md` | estado do projeto, decisões, formato dos bancos, contrato do `agy` |
| `docs/PACOTE_VISUAL_1.1.md` | avaliação dos mockups da interface nova e plano da 1.1 |
| `reviews/` | auditorias (script original, v0.9.0 e v1.0.0) |
| `packaging/`, `.github/workflows/` | geração do `.exe` |

Para retomar o trabalho, leia a seção "Snapshot" de `docs/ESTADO_DO_PROJETO.md`.
