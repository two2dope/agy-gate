import os
import sqlite3
import glob
import re
import json
import logging
import queue
import threading
import urllib.parse
from collections import Counter
from contextlib import closing
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

BASE_DIR = os.environ.get("ANTIGRAVITY_HOME", r"C:\Users\Thomáz\.gemini")
ACTIVE_SUM_DB = os.path.join(BASE_DIR, "antigravity", "conversation_summaries.db")
ACTIVE_CONV_DIR = os.path.join(BASE_DIR, "antigravity", "conversations")
ACTIVE_LABEL = "Ativas (antigravity/conversations)"
PROJECTS_DIR = os.path.join(BASE_DIR, "config", "projects")
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "AntigravityGate")
LOG_FILE = os.path.join(LOG_DIR, "gate.log")
EXPORT_DIR = os.path.join(LOG_DIR, "exports")
STATE_DB = os.path.join(LOG_DIR, "gate_state.db")  # estado do AntigravityGate; nunca grava nos bancos do Antigravity

STATUS_LABEL = {"pendente": "💬 Pendente", "aprovada": "✅ Aprovada", "arquivada": "📦 Arquivada"}

# Alerta de Context Rot: tokens de entrada da última resposta do modelo (f2 + f5 de step_payload.f5.f9).
# Padrão provisório; ajuste com a variável de ambiente AGY_ROT_TOKENS.
ROT_TOKENS = int(os.environ.get("AGY_ROT_TOKENS", "150000"))

UUID_DB_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.db$', re.IGNORECASE)

# Posição das colunas na árvore (valores de cada linha de sessão)
COL_DATE, COL_SIZE, COL_CTX, COL_STEPS, COL_TITLE, COL_AGENT, COL_UUID = range(7)
HEADINGS = {"col_date": "Modificação", "col_size": "Tamanho", "col_ctx": "Contexto (tokens)", "col_steps": "Passos",
            "col_title": "Título / Contexto Inicial", "col_agent": "Agente", "col_uuid": "UUID"}
SORT_FUNCS = {
    "col_date": lambda r: r["date"], "col_size": lambda r: r["size_kb"], "col_ctx": lambda r: r["ctx"],
    "col_steps": lambda r: r["steps"], "col_title": lambda r: r["title"].lower(), "col_agent": lambda r: r["agent"].lower(),
}
NUMERIC_COLS = ("col_date", "col_size", "col_ctx", "col_steps")  # primeiro clique ordena do maior para o menor

# Cache por (caminho, mtime_ns, tamanho): só reabre o banco de uma sessão se ele mudou.
METRICS_CACHE = {}

log = logging.getLogger("antigravitygate")


def setup_logging():
    log.setLevel(logging.INFO)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)


def open_ro(path, timeout=2.0):
    """Abre um banco SQLite somente-leitura. Usar com `with`: fecha a conexão mesmo em erro."""
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    return closing(sqlite3.connect(uri, uri=True, timeout=timeout))


def val(d, key, default=''):
    """d.get(key) que trata None e '' como ausente (coluna NULL no SQLite)."""
    v = d.get(key)
    return default if v is None or v == '' else v


def to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def fmt_time(v):
    """Normaliza data do summaries (str ISO ou epoch em s/ms) para 'YYYY-MM-DD HH:MM:SS'."""
    if v is None or v == '':
        return ''
    if isinstance(v, (int, float)):
        secs = v / 1000 if v > 1e11 else v
        try:
            return datetime.fromtimestamp(secs).strftime('%Y-%m-%d %H:%M:%S')
        except (OverflowError, OSError, ValueError):
            return str(v)
    return str(v)[:19].replace('T', ' ')


def as_text(col):
    if isinstance(col, bytes):
        return col.decode('utf-8', errors='replace')
    return col if isinstance(col, str) else ''


def fmt_tokens(n):
    return "-" if not n else (f"{n / 1000:.0f}k" if n >= 1000 else str(n))


# --- protobuf mínimo (somente leitura) --------------------------------------------------------

def _varint(b, i):
    x = shift = 0
    while True:
        if i >= len(b):
            raise ValueError("varint truncado")
        c = b[i]
        i += 1
        x |= (c & 0x7F) << shift
        if not c & 0x80:
            return x, i
        shift += 7
        if shift > 70:
            raise ValueError("varint longo demais")


def pb_parse(b):
    """Decodifica protobuf genérico em [(campo, wire, valor)]. Levanta ValueError se não for protobuf."""
    i, out = 0, []
    while i < len(b):
        tag, i = _varint(b, i)
        f, w = tag >> 3, tag & 7
        if f == 0 or f > 100000:
            raise ValueError("campo inválido")
        if w == 0:
            v, i = _varint(b, i)
        elif w in (1, 5):
            n = 8 if w == 1 else 4
            v = b[i:i + n]
            if len(v) < n:
                raise ValueError("fixo truncado")
            i += n
        elif w == 2:
            n, i = _varint(b, i)
            v = b[i:i + n]
            if len(v) < n:
                raise ValueError("bloco truncado")
            i += n
        else:
            raise ValueError("wire type inválido")
        out.append((f, w, v))
    return out


def pb_dig(fields, path):
    """Segue `path` (números de campo) em protobuf já decodificado; devolve (wire, valor) ou None."""
    cur = fields
    for k, f in enumerate(path):
        hit = next(((w, v) for ff, w, v in cur if ff == f), None)
        if hit is None:
            return None
        if k == len(path) - 1:
            return hit
        if hit[0] != 2:
            return None
        try:
            cur = pb_parse(hit[1])
        except ValueError:
            return None
    return None


def pb_num(fields, path):
    r = pb_dig(fields, path)
    return r[1] if r and r[0] == 0 else None


def pb_text(fields, path):
    r = pb_dig(fields, path)
    if not r or r[0] != 2:
        return None
    try:
        return r[1].decode("utf-8")
    except UnicodeDecodeError:
        return None


# --- leitura de uma sessão --------------------------------------------------------------------

def first_user_text(c):
    """Primeira fala do usuário (passo 14, f19.f2) ou, em sub-agente, a mensagem do agente pai (passo 101)."""
    try:
        row = c.execute("SELECT step_payload FROM steps WHERE step_type=14 ORDER BY idx LIMIT 1").fetchone()
        if row and row[0]:
            t = pb_text(pb_parse(row[0]), [19, 2])
            if t:
                return t
        for (blob,) in c.execute("SELECT step_payload FROM steps WHERE step_type=101 ORDER BY idx LIMIT 5"):
            f = pb_parse(blob or b"")
            if pb_text(f, [114, 3]) == "agent_message":
                t = pb_text(f, [114, 2, 10, 1]) or pb_text(f, [114, 1])
                if t:
                    return t
    except (sqlite3.OperationalError, ValueError):
        pass
    return ""


def session_metrics(path):
    """(passos, contexto estimado em tokens, prévia) de um banco de sessão, lendo só o necessário."""
    with open_ro(path) as c:
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'steps' not in tables:
            return 0, 0, ''
        cnt = c.execute("SELECT COUNT(*) FROM steps").fetchone()[0]
        ctx = 0
        try:
            for (blob,) in c.execute("SELECT step_payload FROM steps WHERE step_type=15 ORDER BY idx DESC LIMIT 5"):
                f = pb_parse(blob or b"")
                f2, f5 = pb_num(f, [5, 9, 2]), pb_num(f, [5, 9, 5])
                if f2 is not None:
                    ctx = f2 + (f5 or 0)
                    break
        except (sqlite3.OperationalError, ValueError):
            pass
        preview = " ".join(first_user_text(c).split())[:150]
        if not preview:
            # Esquema desconhecido: heurística antiga sobre as primeiras linhas.
            for r in c.execute("SELECT * FROM steps LIMIT 3").fetchall():
                text = "\n".join(as_text(col) for col in r)
                chunks = re.findall(r'[A-Za-zÀ-ÿ0-9_/\-\.,\?!:;\"\' ]{15,}', text)
                if chunks:
                    preview = chunks[0][:150]
                    break
        return cnt, ctx, preview


# --- decodificação de passos e exportação -----------------------------------------------------

EXPORT_MAX_RESULT = 6000   # caracteres por resultado de ferramenta no diálogo completo
EXPORT_MAX_ARGS = 2000     # caracteres por argumentos de ferramenta
DOSSIER_MAX_USER = 700     # caracteres por pedido do usuário no dossiê
DOSSIER_MAX_FINAL = 3000   # caracteres da última resposta do modelo no dossiê
DOSSIER_MAX_USER_MSGS = 35

TOOL_WRITE_HINTS = ("write", "edit", "replace", "create", "delete", "remove", "move", "rename", "patch", "apply", "append", "insert")
TOOL_CMD_HINTS = ("command", "exec", "shell", "terminal", "bash", "run_")
PATH_KEYS = ("AbsolutePath", "TargetFile", "FilePath", "file_path", "Path", "path", "File", "SearchPath", "DirectoryPath", "Directory")
CMD_KEYS = ("CommandLine", "command", "Command", "cmd")

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/\-]{20,}=*"),
    re.compile(r"(?i)((?:api[_-]?key|secret|token|password|passwd|senha)[\"']?\s*[:=]\s*[\"']?)[^\s\"',;}]{6,}"),
]

ROLE_LABEL = {'user': '👤 Usuário', 'model': '🤖 Modelo', 'tool': '🛠 Ferramenta', 'agent_msg': '📨 Mensagem de agente',
              'system': '⚙ Sistema', 'unknown': '❔ Passo não interpretado'}


def redact(text):
    """Mascara padrões comuns de segredo (chaves de API, tokens, senhas). Heurístico: não garante cobertura total."""
    for pat in SECRET_PATTERNS:
        text = pat.sub(lambda m, g=pat.groups: (m.group(1) + "[REDACTED]") if g else "[REDACTED]", text)
    return text


def pb_all(fields, number):
    return [v for f, w, v in fields if f == number and w == 2]


def pb_strings(blob, depth=0):
    """Todos os textos legíveis de um protobuf (usado só em blocos de erro, de estrutura desconhecida).
    Tenta primeiro como mensagem aninhada: um texto curto que começa com tag+tamanho imprimíveis
    (ex.: b'\\n$abc…') também decodifica como UTF-8 e traria o prefixo do protobuf junto."""
    out = []
    try:
        fields = pb_parse(blob)
    except ValueError:
        return out
    for _f, w, v in fields:
        if w != 2:
            continue
        if depth < 6:
            try:
                if pb_parse(v):
                    out += pb_strings(v, depth + 1)
                    continue
            except ValueError:
                pass
        try:
            t = v.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if len(t) >= 4 and all(ch.isprintable() or ch in "\n\r\t" for ch in t):
            out.append(t)
    return out


def decode_step(idx, step_type, status, payload, err_blob=None):
    """Converte um passo em dict com papel e conteúdo. Mapa dos campos: docs/ESTADO_DO_PROJETO.md."""
    d = {'idx': idx, 'type': step_type, 'status': status, 'ts': None, 'kind': 'unknown', 'text': '', 'label': '',
         'calls': [], 'result': '', 'error': '', 'skills': [], 'ctx': 0}
    try:
        f = pb_parse(payload or b"")
    except ValueError:
        return d
    d['ts'] = pb_num(f, [5, 1, 1])
    if err_blob:
        strings = pb_strings(err_blob)
        d['error'] = max(strings, key=len) if strings else "(erro sem texto legível)"

    def call_from(path):
        r = pb_dig(f, path)
        if not r or r[0] != 2:
            return None
        try:
            sub = pb_parse(r[1])
        except ValueError:
            return None
        return {'id': pb_text(sub, [1]) or '', 'name': pb_text(sub, [2]) or '?', 'args': pb_text(sub, [3]) or ''}

    if step_type == 14:
        d['kind'], d['text'] = 'user', pb_text(f, [19, 2]) or ''
        r = pb_dig(f, [19])
        if r and r[0] == 2:
            try:
                for blob in pb_all(pb_parse(r[1]), 3):
                    try:
                        name = pb_text(pb_parse(blob), [2, 27, 1, 1])
                    except ValueError:
                        name = None
                    if name:
                        d['skills'].append(name)
            except ValueError:
                pass
    elif step_type == 15:
        d['kind'], d['text'] = 'model', pb_text(f, [20, 3]) or ''
        r = pb_dig(f, [20])
        if r and r[0] == 2:
            try:
                for blob in pb_all(pb_parse(r[1]), 7):
                    sub = pb_parse(blob)
                    d['calls'].append({'id': pb_text(sub, [1]) or '', 'name': pb_text(sub, [2]) or '?', 'args': pb_text(sub, [3]) or ''})
            except ValueError:
                pass
        f2, f5 = pb_num(f, [5, 9, 2]), pb_num(f, [5, 9, 5])
        d['ctx'] = (f2 + (f5 or 0)) if f2 is not None else 0
    elif step_type == 132:
        d['kind'] = 'tool'
        c = call_from([5, 4])
        d['calls'] = [c] if c else []
        d['result'] = pb_text(f, [140, 2, 1]) or ''
    elif step_type == 101:
        sub = pb_text(f, [114, 3]) or ''
        if sub == 'agent_message':
            d['kind'], d['label'] = 'agent_msg', pb_text(f, [114, 2, 1]) or 'Mensagem de agente'
            d['text'] = pb_text(f, [114, 2, 10, 1]) or pb_text(f, [114, 1]) or ''
        else:
            d['kind'], d['label'], d['text'] = 'system', sub or 'mensagem de sistema', pb_text(f, [114, 1]) or ''
    elif step_type == 90:
        d['kind'] = 'marker'
    return d


def iter_steps(conn):
    """Gera (total, n, passo_decodificado) em ordem de idx, lendo em lotes."""
    total = conn.execute("SELECT COUNT(*) FROM steps").fetchone()[0]
    cur = conn.execute("SELECT idx, step_type, status, step_payload, error_details FROM steps ORDER BY idx")
    n = 0
    while True:
        rows = cur.fetchmany(100)
        if not rows:
            return
        for idx, t, st, payload, err in rows:
            n += 1
            yield total, n, decode_step(idx, t, st, payload, err)


def quick_meta(conn):
    """Início, fim, passos, contexto final e modelos de uma sessão, sem varrer tudo."""
    m = {'steps': 0, 'started': None, 'ended': None, 'ctx': 0, 'models': []}
    m['steps'] = conn.execute("SELECT COUNT(*) FROM steps").fetchone()[0]
    for col, order in (('started', 'ASC'), ('ended', 'DESC')):
        row = conn.execute(f"SELECT step_payload FROM steps ORDER BY idx {order} LIMIT 1").fetchone()
        if row and row[0]:
            try:
                m[col] = pb_num(pb_parse(row[0]), [5, 1, 1])
            except ValueError:
                pass
    try:
        for (blob,) in conn.execute("SELECT step_payload FROM steps WHERE step_type=15 ORDER BY idx DESC LIMIT 5"):
            f = pb_parse(blob or b"")
            f2, f5 = pb_num(f, [5, 9, 2]), pb_num(f, [5, 9, 5])
            if f2 is not None:
                m['ctx'] = f2 + (f5 or 0)
                break
        names = []
        for order in ("ASC", "DESC"):
            row = conn.execute(f"SELECT data FROM gen_metadata ORDER BY idx {order} LIMIT 1").fetchone()
            if row and row[0]:
                n = pb_text(pb_parse(row[0]), [21])
                if n and n not in names:
                    names.append(n)
        m['models'] = names
    except (sqlite3.OperationalError, ValueError):
        pass
    return m


def fmt_ts(ts, full=False):
    if ts is None:
        return "?"
    try:
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S' if full else '%d/%m %H:%M:%S')
    except (OverflowError, OSError, ValueError):
        return str(ts)


def fence(text):
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    ticks = "`" * max(3, longest + 1)
    return f"{ticks}\n{text}\n{ticks}\n"


def clip(text, n):
    return text if len(text) <= n else text[:n] + f"\n[… {len(text) - n} caracteres omitidos]"


def meta_table(meta, qm):
    rows = [("UUID da sessão", meta['cid']), ("Projeto", meta.get('project') or '-'), ("Workspace", meta.get('workspace') or '-'),
            ("Agente", meta.get('agent') or '-'), ("Sessão pai", meta.get('parent') or '-'),
            ("Modelo(s)", ", ".join(qm['models']) or '-'), ("Início", fmt_ts(qm['started'], True)), ("Fim", fmt_ts(qm['ended'], True)),
            ("Passos", qm['steps']), ("Contexto na última resposta", f"{qm['ctx']} tokens" if qm['ctx'] else '-'),
            ("Status no AntigravityGate", meta.get('status') or 'pendente'), ("Fonte", meta.get('source') or '-'),
            ("Banco", meta.get('fpath') or '-'), ("Gerado em", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))]
    out = "| Campo | Valor |\n| :--- | :--- |\n"
    for k, v in rows:
        out += f"| {k} | {str(v).replace('|', '/').replace(chr(10), ' ')} |\n"
    return out


def write_full_export(fh, meta, qm, steps, progress=None):
    fh.write(f"# Diálogo completo — {meta.get('title') or meta['cid']}\n\n")
    fh.write("> Este arquivo reproduz o conteúdo da conversa e pode conter chaves, senhas e dados pessoais. "
             "Revise antes de compartilhar. Horários no fuso local deste computador.\n\n")
    fh.write(meta_table(meta, qm) + "\n---\n\n## Linha do tempo\n\n")
    for total, n, st in steps:
        if progress and n % 20 == 0:
            progress(n, total)
        kind = st['kind']
        if kind == 'marker':
            continue
        head = f"### #{st['idx']} · {fmt_ts(st['ts'])} · {ROLE_LABEL.get(kind, kind)}"
        if kind == 'tool':
            ok = st['status'] == 3 and not st['error']
            name = st['calls'][0]['name'] if st['calls'] else '?'
            situacao = "ok" if ok else "⚠ status " + str(st['status'])
            head += f" · `{name}` · {situacao}"
        elif kind in ('agent_msg', 'system'):
            head += f" · {st['label']}"
        fh.write(head + "\n\n")
        if kind == 'user':
            fh.write((st['text'] or "(sem texto)") + "\n\n")
            if st['skills']:
                fh.write(f"_Skill invocada: {', '.join(st['skills'])}_\n\n")
        elif kind == 'model':
            if st['text']:
                fh.write(st['text'] + "\n\n")
            for c in st['calls']:
                fh.write(f"Chamada de ferramenta `{c['name']}` (`{c['id']}`):\n\n" + fence(clip(c['args'], EXPORT_MAX_ARGS)) + "\n")
            if not st['text'] and not st['calls']:
                fh.write("_(resposta sem texto visível)_\n\n")
        elif kind == 'tool':
            if st['calls'] and st['calls'][0]['args']:
                fh.write("Argumentos:\n\n" + fence(clip(st['calls'][0]['args'], EXPORT_MAX_ARGS)) + "\n")
            if st['result']:
                fh.write("Resultado:\n\n" + fence(clip(st['result'], EXPORT_MAX_RESULT)) + "\n")
            if st['error']:
                fh.write("Erro:\n\n" + fence(clip(st['error'], EXPORT_MAX_RESULT)) + "\n")
            if not st['result'] and not st['error']:
                fh.write("_(sem resultado textual)_\n\n")
        elif kind in ('agent_msg', 'system'):
            fh.write((clip(st['text'], EXPORT_MAX_RESULT) or "(sem texto)") + "\n\n")
        else:
            fh.write(f"_Passo de tipo {st['type']} não interpretado pelo AntigravityGate._\n\n")


def tool_paths(args):
    """Caminhos citados nos argumentos de uma ferramenta (JSON; se inválido, busca por regex)."""
    found = []
    try:
        data = json.loads(args)
        if isinstance(data, dict):
            found = [str(data[k]) for k in PATH_KEYS if isinstance(data.get(k), str)]
    except ValueError:
        for k in PATH_KEYS:
            found += re.findall(r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)"' % k, args)
        found = [x.replace("\\\\", "\\") for x in found]
    return found


def tool_command(args):
    try:
        data = json.loads(args)
        if isinstance(data, dict):
            for k in CMD_KEYS:
                if isinstance(data.get(k), str):
                    return data[k]
    except ValueError:
        for k in CMD_KEYS:
            m = re.search(r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)"' % k, args)
            if m:
                return m.group(1)
    return ''


def build_dossier(meta, qm, steps, progress=None):
    users, final_text, parent_task = [], '', ''
    tools, files_read, files_mod, commands, errors, agent_msgs = Counter(), {}, {}, [], [], []
    for total, n, st in steps:
        if progress and n % 20 == 0:
            progress(n, total)
        k = st['kind']
        if k == 'user':
            users.append((st['ts'], st['text'], st['skills']))
        elif k == 'agent_msg':
            if not parent_task and 'Parent' in st['label']:
                parent_task = st['text']
            else:
                agent_msgs.append((st['ts'], st['label'], st['text']))
        elif k == 'model' and st['text']:
            final_text = st['text']
        elif k == 'tool' and st['calls']:
            c = st['calls'][0]
            name, low = c['name'], c['name'].lower()
            tools[name] += 1
            ok = st['status'] == 3 and not st['error']
            if any(h in low for h in TOOL_WRITE_HINTS):
                for pth in tool_paths(c['args']):
                    files_mod[pth] = files_mod.get(pth, 0) + 1
            elif any(h in low for h in TOOL_CMD_HINTS):
                cmd = tool_command(c['args'])
                if cmd:
                    commands.append((st['ts'], cmd, ok))
            else:
                for pth in tool_paths(c['args']):
                    files_read[pth] = files_read.get(pth, 0) + 1
            if not ok:
                summary = (st['error'] or st['result'] or '(sem texto)').strip().splitlines()[0][:240]
                errors.append((st['ts'], name, st['status'], summary))

    o = [f"# Dossiê de retomada — {meta.get('title') or meta['cid']}\n",
         "> Extração local feita pelo AntigravityGate: nenhum modelo foi usado para resumir, então nada aqui é interpretação. "
         "Segredos conhecidos foram mascarados, mas revise antes de enviar a qualquer serviço.\n",
         "## Origem\n", meta_table(meta, qm)]
    if parent_task:
        o += ["## Tarefa recebida do agente pai\n", clip(parent_task, 2000) + "\n"]
    o.append(f"## Pedidos do usuário ({len(users)})\n")
    if not users:
        o.append("_Nenhuma fala direta do usuário nesta sessão._\n")
    shown = users if len(users) <= DOSSIER_MAX_USER_MSGS else users[:5] + [None] + users[-(DOSSIER_MAX_USER_MSGS - 5):]
    for i, u in enumerate(shown, 1):
        if u is None:
            o.append(f"_… {len(users) - DOSSIER_MAX_USER_MSGS} pedidos intermediários omitidos …_\n")
            continue
        ts, text, skills = u
        extra = f" _(skill: {', '.join(skills)})_" if skills else ""
        o.append(f"**{fmt_ts(ts)}**{extra}\n\n" + clip(" ".join(text.split()) if len(text) < 400 else text, DOSSIER_MAX_USER) + "\n")
    o.append("## Última resposta do modelo\n")
    o.append((clip(final_text, DOSSIER_MAX_FINAL) if final_text else "_(sem texto de resposta)_") + "\n")
    if files_mod:
        o.append(f"## Arquivos alterados ({len(files_mod)}) — por nome da ferramenta, heurístico\n")
        o.append("\n".join(f"- `{p}` ({n}x)" for p, n in list(files_mod.items())[:40]) + "\n")
    if files_read:
        o.append(f"## Arquivos consultados ({len(files_read)})\n")
        o.append("\n".join(f"- `{p}` ({n}x)" for p, n in list(files_read.items())[:40]) + "\n")
    if commands:
        o.append(f"## Comandos executados (últimos {min(len(commands), 25)} de {len(commands)})\n")
        o.append("\n".join(f"- {fmt_ts(ts)} {'ok' if ok else '⚠ falhou'}: `{c[:200]}`" for ts, c, ok in commands[-25:]) + "\n")
    if errors:
        o.append(f"## Falhas de ferramenta (últimas {min(len(errors), 10)} de {len(errors)})\n")
        o.append("\n".join(f"- {fmt_ts(ts)} `{name}` (status {stt}): {summ}" for ts, name, stt, summ in errors[-10:]) + "\n")
    if agent_msgs:
        o.append(f"## Mensagens entre agentes ({len(agent_msgs)}, últimas 8)\n")
        o.append("\n".join(f"- {fmt_ts(ts)} **{lab}**: {clip(' '.join(t.split()), 400)}" for ts, lab, t in agent_msgs[-8:]) + "\n")
    if tools:
        o.append("## Ferramentas usadas\n")
        o.append(", ".join(f"`{n}` ×{c}" for n, c in tools.most_common()) + "\n")
    o.append("## Instrução para quem retomar\n")
    o.append("Você está retomando este trabalho a partir do dossiê acima. Antes de agir: (1) diga em poucas linhas o que entendeu do "
             "objetivo e do estado atual; (2) liste o que falta; (3) proponha os próximos passos e espere confirmação. "
             "O dossiê é uma extração automática: confirme no código e nos arquivos antes de assumir qualquer detalhe.\n")
    return redact("\n".join(o))


def export_session(kind, fpath, meta, out_path, progress=None):
    """Grava o diálogo completo ('full') ou o dossiê de retomada ('dossier') de uma sessão."""
    with open_ro(fpath) as conn:
        qm = quick_meta(conn)
        steps = iter_steps(conn)
        if kind == 'full':
            with open(out_path, 'w', encoding='utf-8', newline='\n') as fh:
                write_full_export(fh, meta, qm, steps, progress)
        else:
            text = build_dossier(meta, qm, steps, progress)
            with open(out_path, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(text)


# --- estado de aprovação (banco próprio) -----------------------------------------------------

class StateStore:
    """Status por sessão (pendente/aprovada/arquivada) + histórico, em gate_state.db.
    Se o arquivo não puder ser criado, cai para memória e `persistent` fica False."""

    def __init__(self, path):
        self.path = path
        self.persistent = True
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._init()
        except (OSError, sqlite3.Error) as e:
            log.warning("Estado não será salvo (%s): %s", path, e)
            self.path, self.persistent = ":memory:", False
            self._mem = sqlite3.connect(":memory:")
            self._init()

    def _connect(self):
        if not self.persistent:
            return closing(_NoClose(self._mem))
        return closing(sqlite3.connect(self.path, timeout=5.0))

    def _init(self):
        if not self.persistent:
            conn = self._mem
        else:
            conn = sqlite3.connect(self.path, timeout=5.0)
        with conn:
            conn.execute("CREATE TABLE IF NOT EXISTS session_state(cid TEXT PRIMARY KEY, status TEXT NOT NULL, updated_at TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS state_log(id INTEGER PRIMARY KEY AUTOINCREMENT, cid TEXT NOT NULL, status TEXT NOT NULL, at TEXT NOT NULL)")
        if self.persistent:
            conn.close()

    def load(self):
        with self._connect() as c:
            return dict(c.execute("SELECT cid, status FROM session_state").fetchall())

    def set_many(self, cids, status):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with self._connect() as c:
            with c:
                for cid in cids:
                    if status == "pendente":
                        c.execute("DELETE FROM session_state WHERE cid=?", (cid,))
                    else:
                        c.execute("INSERT INTO session_state(cid, status, updated_at) VALUES(?,?,?) "
                                  "ON CONFLICT(cid) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at", (cid, status, now))
                    c.execute("INSERT INTO state_log(cid, status, at) VALUES(?,?,?)", (cid, status, now))


class _NoClose:
    """Envolve a conexão em memória para o `closing` não destruir o banco entre chamadas."""
    def __init__(self, conn):
        self._c = conn

    def __getattr__(self, name):
        return getattr(self._c, name)

    def __enter__(self):
        return self._c.__enter__()

    def __exit__(self, *a):
        return self._c.__exit__(*a)

    def close(self):
        pass


# --- fontes e varredura -----------------------------------------------------------------------

def scandir_safe(folder):
    try:
        return list(os.scandir(folder))
    except OSError:
        return []


def discover_sources():
    """Fontes de sessões: (rótulo, pasta com os .db, conversation_summaries.db ou None).
    A primeira é sempre a pasta ativa. Cópias de backup e quarentena ficam em fontes separadas,
    nunca misturadas com as ativas."""
    sources = [(ACTIVE_LABEL, ACTIVE_CONV_DIR, ACTIVE_SUM_DB if os.path.isfile(ACTIVE_SUM_DB) else None)]
    seen = {os.path.normcase(os.path.abspath(ACTIVE_CONV_DIR))}
    for top in sorted((e for e in scandir_safe(BASE_DIR) if e.is_dir()), key=lambda e: e.name.lower()):
        for folder in [top] + sorted((e for e in scandir_safe(top.path) if e.is_dir()), key=lambda e: e.name.lower()):
            key = os.path.normcase(os.path.abspath(folder.path))
            if key in seen or not any(UUID_DB_RE.match(e.name) for e in scandir_safe(folder.path) if e.is_file()):
                continue
            seen.add(key)
            parent = os.path.dirname(folder.path)
            summ = next((p for p in (os.path.join(parent, "conversation_summaries.db"),
                                     os.path.join(folder.path, "conversation_summaries.db")) if os.path.isfile(p)), None)
            rel = os.path.relpath(folder.path, BASE_DIR).replace(os.sep, "/")
            sources.append((f"Backup/outros: {rel}", folder.path, summ))
    return sources


def load_projects(warn):
    proj_map = {'outside-of-project': 'Outside of Project'}
    uri_to_proj = {}
    if os.path.exists(PROJECTS_DIR):
        for p_file in glob.glob(os.path.join(PROJECTS_DIR, '*.json')):
            try:
                with open(p_file, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                if not isinstance(d, dict):
                    raise ValueError("JSON de projeto não é um objeto")
                pid = d.get('id') or ''
                pname = d.get('name') or pid
                proj_map[pid] = pname
                for res in (d.get('projectResources') or {}).get('resources') or []:
                    u = res.get('folderUri') or (res.get('gitFolder') or {}).get('folderUri')
                    if u:
                        uri_to_proj[urllib.parse.unquote(u).lower()] = pname
            except Exception as e:
                warn(f"Projeto ilegível: {p_file}", e)
    return proj_map, uri_to_proj


def scan_source(conv_dir, sum_db, is_active, progress=None, is_stale=None):
    """Lê uma fonte inteira. Não toca em Tk, então roda em thread de trabalho.
    Devolve dict com as sessões agrupadas por projeto e os dados que a tela precisa, ou None se ficou obsoleta."""
    warnings = []

    def warn(msg, exc=None):
        warnings.append(msg)
        if exc is not None:
            log.warning("%s: %s: %s", msg, type(exc).__name__, exc)
        else:
            log.warning("%s", msg)

    if not os.path.isdir(BASE_DIR):
        warn(f"Pasta base inexistente: {BASE_DIR}")
    proj_map, uri_to_proj = load_projects(warn)

    summaries = {}
    if sum_db:
        try:
            with open_ro(sum_db) as conn:
                conn.row_factory = sqlite3.Row
                for r in conn.execute("SELECT * FROM conversation_summaries").fetchall():
                    summaries[r['conversation_id']] = dict(r)
        except Exception as e:
            warn(f"Falha ao ler {sum_db}", e)

    # Só a pasta da fonte selecionada: uma sessão com cópias em várias pastas não é mais sobrescrita.
    db_files = {}
    if not os.path.isdir(conv_dir):
        warn(f"Pasta de sessões inexistente: {conv_dir}")
    for entry in scandir_safe(conv_dir):
        if entry.is_file() and UUID_DB_RE.match(entry.name):
            db_files[os.path.splitext(entry.name)[0]] = entry.path

    # Fonte ativa mostra também sessões que só existem no summaries ("sem arquivo").
    # Nas cópias de backup só entram sessões que têm arquivo naquela pasta.
    all_cids = set(db_files)
    if is_active:
        all_cids |= set(summaries)

    grouped = {}
    for n, cid in enumerate(sorted(all_cids), 1):
        if is_stale and is_stale():
            return None
        if progress and n % 5 == 0:
            progress(n, len(all_cids))
        s = summaries.get(cid, {})
        fpath = db_files.get(cid, '')

        title = str(val(s, 'title')).strip()
        preview = str(val(s, 'preview')).strip()
        step_count = to_int(s.get('step_count'))
        last_mod = fmt_time(s.get('last_modified_time'))
        pid = str(val(s, 'project_id'))
        w_uris = str(val(s, 'workspace_uris'))
        file_size_kb = 0
        ctx = 0

        if fpath and os.path.exists(fpath):
            st = os.stat(fpath)
            file_size_kb = round(st.st_size / 1024, 1)
            if not last_mod:
                last_mod = datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            key = (fpath, st.st_mtime_ns, st.st_size)
            m = METRICS_CACHE.get(key)
            if m is None:
                try:
                    m = session_metrics(fpath)
                    METRICS_CACHE[key] = m
                except Exception as e:
                    warn(f"Falha ao ler sessão {cid}", e)
                    m = (0, 0, '')
            cnt, ctx, first = m
            step_count = max(step_count, cnt)
            if not preview:
                preview = first

        proj_name = proj_map.get(pid, '')
        w_decoded = urllib.parse.unquote(w_uris)
        if not proj_name or proj_name == 'Outside of Project':
            for u_key, p_val in uri_to_proj.items():
                if u_key in w_decoded.lower():
                    proj_name = p_val
                    break
        if not proj_name:
            proj_name = 'Outside of Project'

        if not title or title.startswith('Sessão '):
            title = (preview[:60] + '...') if len(preview) > 60 else (preview or f"Conversa {cid[:8]}")

        grouped.setdefault(proj_name, []).append({
            'cid': cid,
            'date': last_mod[:19],
            'size': f"{file_size_kb} KB" if fpath else "sem arquivo",
            'size_kb': file_size_kb,
            'ctx': ctx,
            'steps': step_count,
            'title': title,
            'fpath': fpath,
            'agent': str(val(s, 'agent_name')),
            'parent': str(val(s, 'parent_conversation_id')),
            'project': proj_name,
            'hay': " ".join((title, preview, cid, str(val(s, 'agent_name')), proj_name, w_decoded)).lower(),
        })

    return {'grouped': grouped, 'total': len(all_cids), 'warnings': warnings,
            'proj_map': proj_map, 'summaries': summaries, 'db_files': db_files}


class AntigravityGateApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AntigravityGate 🚀 - Inspetor e Gestor Agêntico")
        self.geometry("1200x650")

        self.themed = []
        self.queue = queue.Queue()
        self.gen = 0
        self.loading = False
        self.exporting = False
        self.warnings = 0
        self.base_status = ""
        self.proj_map, self.summaries, self.db_files = {}, {}, {}
        self.state = StateStore(STATE_DB)
        self.states = {}
        self.grouped, self.total, self.sub_count = {}, 0, {}
        self.match, self.sort_col, self.sort_rev = None, "col_date", True
        self.search_note = ""

        # Estado do Tema (Dark por padrão, com suporte a Light)
        self.dark_mode = True
        self.apply_theme()

        self.sources = discover_sources()
        self.source_idx = 0
        self.create_widgets()
        self.poll()
        self.load_data()

    def apply_theme(self):
        if self.dark_mode:
            self.bg_color = "#1e1e1e"
            self.fg_color = "#d4d4d4"
            self.panel_bg = "#252526"
            self.header_bg = "#333333"
            self.accent_color = "#007acc"
        else:
            self.bg_color = "#f5f5f5"
            self.fg_color = "#222222"
            self.panel_bg = "#ffffff"
            self.header_bg = "#e0e0e0"
            self.accent_color = "#005a9e"

        self.configure(bg=self.bg_color)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background=self.panel_bg, foreground=self.fg_color, fieldbackground=self.panel_bg, rowheight=28)
        style.configure("Treeview.Heading", background=self.header_bg, foreground=self.fg_color, font=('Segoe UI', 10, 'bold'))
        style.map("Treeview", background=[('selected', self.accent_color)])
        style.configure("TCombobox", fieldbackground=self.panel_bg, background=self.header_bg, foreground=self.fg_color, arrowcolor=self.fg_color)
        style.map("TCombobox", fieldbackground=[("readonly", self.panel_bg)], foreground=[("readonly", self.fg_color)])
        style.configure("Vertical.TScrollbar", background=self.header_bg, troughcolor=self.bg_color, arrowcolor=self.fg_color)

        # Widgets tk (não-ttk) já criados: reaplica as cores sem recarregar dados.
        for widget, opts in self.themed:
            widget.configure(**{opt: getattr(self, attr) for opt, attr in opts.items()})

    def themed_widget(self, widget, **opts):
        """Registra um widget tk para ser recolorido por apply_theme. opts: opção -> nome do atributo de cor."""
        self.themed.append((widget, opts))
        widget.configure(**{opt: getattr(self, attr) for opt, attr in opts.items()})
        return widget

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.apply_theme()

    def create_widgets(self):
        # Top Frame - Controles, Tema e Ações
        self.top_frame = self.themed_widget(tk.Frame(self, pady=10, padx=10), bg="bg_color")
        self.top_frame.pack(fill=tk.X)

        lbl_title = self.themed_widget(tk.Label(self.top_frame, text="🚀 AntigravityGate - Gestão de Contexto e Curadoria", font=('Segoe UI', 12, 'bold')), bg="bg_color", fg="fg_color")
        lbl_title.pack(side=tk.LEFT)

        # Fonte: sessões ativas ou cada cópia de backup, lidas separadamente
        self.src_box = ttk.Combobox(self.top_frame, state="readonly", width=48, values=[s[0] for s in self.sources])
        self.src_box.current(self.source_idx)
        self.src_box.bind("<<ComboboxSelected>>", lambda e: self.on_source_change())
        self.src_box.pack(side=tk.LEFT, padx=(20, 5))
        btn_refresh = self.themed_widget(tk.Button(self.top_frame, text="🔄 Atualizar", font=('Segoe UI', 9), relief=tk.FLAT, command=self.refresh), bg="header_bg", fg="fg_color")
        btn_refresh.pack(side=tk.LEFT, padx=5)

        # Ações ainda sem implementação: desabilitadas para não afirmar efeito que não ocorre.
        btn_auto = self.themed_widget(tk.Button(self.top_frame, text="⚡ Auto-Run (em breve)", disabledforeground="#888888", font=('Segoe UI', 9, 'bold'), relief=tk.FLAT, state=tk.DISABLED), bg="header_bg")
        btn_auto.pack(side=tk.RIGHT, padx=5)

        for status, text in (("pendente", "↩ Pendente"), ("arquivada", "📦 Arquivar"), ("aprovada", "✅ Aprovar")):
            btn = self.themed_widget(tk.Button(self.top_frame, text=text, font=('Segoe UI', 9), relief=tk.FLAT,
                                               command=lambda st=status: self.mark_selected(st)), bg="header_bg", fg="fg_color")
            btn.pack(side=tk.RIGHT, padx=3)

        btn_theme = self.themed_widget(tk.Button(self.top_frame, text="🌓 Alternar Tema", font=('Segoe UI', 9), relief=tk.FLAT, command=self.toggle_theme), bg="header_bg", fg="fg_color")
        btn_theme.pack(side=tk.RIGHT, padx=5)

        btn_dossier = self.themed_widget(tk.Button(self.top_frame, text="📋 Dossiê de retomada", fg="#ffffff", font=('Segoe UI', 9, 'bold'), relief=tk.FLAT, command=lambda: self.start_export('dossier')), bg="accent_color")
        btn_dossier.pack(side=tk.RIGHT, padx=5)
        btn_open = self.themed_widget(tk.Button(self.top_frame, text="📄 Exportar diálogo", fg="#ffffff", font=('Segoe UI', 9, 'bold'), relief=tk.FLAT, command=self.open_selected), bg="accent_color")
        btn_open.pack(side=tk.RIGHT, padx=5)

        # Barra de status: fonte, contagem de sessões, carga em andamento e avisos de leitura
        self.status = self.themed_widget(tk.Label(self, anchor=tk.W, padx=10, pady=4, font=('Segoe UI', 9)), bg="header_bg", fg="fg_color")
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        # Busca: título, pasta, agente, UUID (metadados) e conteúdo das conversas (índice do Antigravity)
        self.search_frame = self.themed_widget(tk.Frame(self, padx=10), bg="bg_color")
        self.search_frame.pack(fill=tk.X, before=self.status)
        self.themed_widget(tk.Label(self.search_frame, text="Buscar:", font=('Segoe UI', 9)), bg="bg_color", fg="fg_color").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_entry = self.themed_widget(tk.Entry(self.search_frame, textvariable=self.search_var, width=50, relief=tk.FLAT, font=('Segoe UI', 10)),
                                               bg="panel_bg", fg="fg_color", insertbackground="fg_color")
        self.search_entry.pack(side=tk.LEFT, padx=6, ipady=3)
        self.search_entry.bind("<Return>", lambda e: self.run_search())
        self.search_entry.bind("<Escape>", lambda e: self.clear_search())
        self.bind("<Control-f>", lambda e: (self.search_entry.focus_set(), "break")[1])
        self.themed_widget(tk.Button(self.search_frame, text="🔍 Buscar", font=('Segoe UI', 9), relief=tk.FLAT, command=self.run_search), bg="header_bg", fg="fg_color").pack(side=tk.LEFT, padx=3)
        self.themed_widget(tk.Button(self.search_frame, text="✖ Limpar", font=('Segoe UI', 9), relief=tk.FLAT, command=self.clear_search), bg="header_bg", fg="fg_color").pack(side=tk.LEFT, padx=3)

        # Tabela (Treeview) com métricas de contexto
        columns = ("col_date", "col_size", "col_ctx", "col_steps", "col_title", "col_agent", "col_uuid")
        self.tree = ttk.Treeview(self, columns=columns, show="tree headings", selectmode="extended")

        self.tree.heading("#0", text="Projeto / Sessão", anchor=tk.W)
        for col in columns:
            anchor = tk.CENTER if col in ("col_size", "col_ctx", "col_steps") else tk.W
            cmd = (lambda c=col: self.sort_by(c)) if col in SORT_FUNCS else ""
            self.tree.heading(col, text=HEADINGS[col], anchor=anchor, command=cmd)

        self.tree.heading("col_date", text=HEADINGS["col_date"] + " ▼")  # ordenação inicial: mais recentes primeiro
        self.tree.column("#0", width=230, anchor=tk.W)
        self.tree.column("col_date", width=130, anchor=tk.W)
        self.tree.column("col_size", width=80, anchor=tk.CENTER)
        self.tree.column("col_ctx", width=130, anchor=tk.CENTER)
        self.tree.column("col_steps", width=60, anchor=tk.CENTER)
        self.tree.column("col_title", width=330, anchor=tk.W)
        self.tree.column("col_agent", width=140, anchor=tk.W)
        self.tree.column("col_uuid", width=150, anchor=tk.W)

        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        # Barra empacotada antes da árvore: não some quando a janela encolhe.
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=10)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Button-3>", self.show_menu)
        self.bind("<F5>", lambda e: self.refresh())

    def is_session(self, iid):
        v = self.tree.item(iid, 'values') if iid else ()
        return len(v) > COL_UUID and v[COL_UUID] != ''

    def iter_sessions(self, root=''):
        for iid in self.tree.get_children(root):
            if self.is_session(iid):
                yield iid
            yield from self.iter_sessions(iid)

    def cid_of(self, iid):
        return self.tree.item(iid, 'values')[COL_UUID]

    def on_double_click(self, event):
        iid = self.tree.identify_row(event.y)
        if not self.is_session(iid):
            return  # cabeçalho, área vazia ou pasta de projeto: o duplo clique padrão só expande/recolhe
        self.tree.selection_set(iid)
        self.open_selected()

    def selected_cids(self):
        """UUIDs das sessões selecionadas; selecionar uma pasta de projeto vale para todas as sessões dela."""
        cids, from_project = [], False
        for iid in self.tree.selection():
            if self.is_session(iid):
                cids.append(self.cid_of(iid))
            else:
                from_project = True
                cids.extend(self.cid_of(i) for i in self.iter_sessions(iid))
        return list(dict.fromkeys(cids)), from_project

    def mark_selected(self, status):
        cids, from_project = self.selected_cids()
        if not cids:
            messagebox.showwarning("Aviso", "Selecione uma sessão ou uma pasta de projeto.")
            return
        if (len(cids) > 1 or from_project) and not messagebox.askyesno(
                "Confirmar", f"Marcar {len(cids)} sessão(ões) como {STATUS_LABEL[status][2:]}?"):
            return
        try:
            self.state.set_many(cids, status)
        except sqlite3.Error as e:
            log.exception("Falha ao gravar estado")
            messagebox.showerror("Erro", f"Não foi possível gravar o estado:\n{e}")
            return
        if not self.state.persistent:
            messagebox.showwarning("Aviso", "O estado não pôde ser salvo em disco e será perdido ao fechar o app.")
        self.states = self.state.load()
        self.refresh_labels()

    def leaf_text(self, cid):
        n = self.sub_count.get(cid, 0)
        sub = f"  (+{n} sub-agente{'s' if n != 1 else ''})" if n else ""
        return "    " + STATUS_LABEL[self.states.get(cid, "pendente")] + sub

    def refresh_labels(self):
        for iid in self.iter_sessions():
            self.tree.item(iid, text=self.leaf_text(self.cid_of(iid)))
        self.set_status(self.base_status)

    # --- ordenação, busca, menu de contexto ---

    def sort_by(self, col):
        self.sort_rev = (not self.sort_rev) if col == self.sort_col else (col in NUMERIC_COLS)
        self.sort_col = col
        for c in SORT_FUNCS:
            arrow = (" ▼" if self.sort_rev else " ▲") if c == col else ""
            self.tree.heading(c, text=HEADINGS[c] + arrow)
        self.populate()

    @staticmethod
    def fts_hits(sum_db, query):
        terms = re.findall(r"\w+", query)
        if not terms:
            return set()
        match = " ".join(f'"{t}"*' for t in terms)
        with open_ro(sum_db) as c:
            return {r[0] for r in c.execute("SELECT DISTINCT conversation_id FROM conversations_fts WHERE conversations_fts MATCH ?", (match,))}

    def run_search(self):
        q = self.search_var.get().strip()
        if not q:
            self.clear_search()
            return
        terms = q.lower().split()
        rows = [r for grp in self.grouped.values() for r in grp]
        hits = {r['cid'] for r in rows if all(t in r['hay'] for t in terms)}
        content_ok = True
        sum_db = self.sources[self.source_idx][2]
        if sum_db:
            try:
                hits |= self.fts_hits(sum_db, q)
            except sqlite3.Error as e:
                content_ok = False
                log.info("Busca por conteúdo indisponível: %s", e)
        else:
            content_ok = False
        self.match = hits & {r['cid'] for r in rows}
        self.search_note = f"{len(self.match)} resultado(s) para “{q}”" + ("" if content_ok else " (só metadados: sem índice de conteúdo nesta fonte)")
        self.populate()

    def clear_search(self):
        self.search_var.set("")
        self.match = None
        self.search_note = ""
        if self.grouped:
            self.populate()

    def show_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
        m = tk.Menu(self, tearoff=0)
        if self.is_session(iid):
            m.add_command(label="Copiar UUID", command=lambda: self.copy_uuid(iid))
            m.add_command(label="Abrir pasta do banco", command=lambda: self.open_folder(iid))
            m.add_command(label="Exportar diálogo", command=self.open_selected)
            m.add_command(label="Dossiê de retomada", command=lambda: self.start_export('dossier'))
            m.add_separator()
        for status, text in (("aprovada", "✅ Aprovar"), ("arquivada", "📦 Arquivar"), ("pendente", "↩ Pendente")):
            m.add_command(label=text, command=lambda st=status: self.mark_selected(st))
        m.tk_popup(event.x_root, event.y_root)

    def copy_uuid(self, iid):
        self.clipboard_clear()
        self.clipboard_append(self.cid_of(iid))

    def open_folder(self, iid):
        fpath = self.db_files.get(self.cid_of(iid), '')
        if not fpath:
            messagebox.showinfo("Aviso", "Esta sessão não tem arquivo nesta fonte.")
            return
        opener = getattr(os, "startfile", None)
        if opener is None:
            messagebox.showinfo("Pasta do banco", os.path.dirname(fpath))
            return
        try:
            opener(os.path.dirname(fpath))
        except OSError as e:
            messagebox.showinfo("Pasta do banco", f"{os.path.dirname(fpath)}\n\nNão abriu automaticamente: {e}")

    def on_source_change(self):
        self.source_idx = self.src_box.current()
        self.load_data()

    def refresh(self):
        """Relê as fontes do disco (pode haver novas pastas) e recarrega a fonte selecionada."""
        label = self.sources[self.source_idx][0]
        self.sources = discover_sources()
        self.source_idx = next((i for i, s in enumerate(self.sources) if s[0] == label), 0)
        self.src_box.configure(values=[s[0] for s in self.sources])
        self.src_box.current(self.source_idx)
        self.load_data()

    def set_status(self, text):
        self.base_status = text
        shown = {self.cid_of(i) for i in self.iter_sessions()}
        n_ok = sum(1 for c in shown if self.states.get(c) == "aprovada")
        n_arq = sum(1 for c in shown if self.states.get(c) == "arquivada")
        if n_ok or n_arq:
            text += f"  |  ✅ {n_ok} aprovadas · 📦 {n_arq} arquivadas"
        self.status.configure(text=text)

    def load_data(self):
        """Dispara a leitura em thread de trabalho; a janela continua responsiva."""
        self.gen += 1
        gen = self.gen
        label, conv_dir, sum_db = self.sources[self.source_idx]
        is_active = self.source_idx == 0
        self.loading = True
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.set_status(f"{label}  |  carregando…")

        def work():
            try:
                res = scan_source(conv_dir, sum_db, is_active,
                                  progress=lambda n, t: self.queue.put((gen, 'progress', (n, t))),
                                  is_stale=lambda: gen != self.gen)
            except Exception as e:
                log.exception("Falha ao varrer %s", conv_dir)
                res = {'error': e}
            if res is not None:
                self.queue.put((gen, 'done', res))

        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        """Recebe resultados da thread de trabalho. Só esta função mexe na tela com dados novos."""
        try:
            while True:
                gen, kind, payload = self.queue.get_nowait()
                if kind.startswith('export'):
                    self.on_export_event(kind, payload)
                    continue
                if gen != self.gen:
                    continue  # resposta de uma carga antiga (o usuário trocou de fonte)
                label = self.sources[self.source_idx][0]
                if kind == 'progress':
                    self.set_status(f"{label}  |  carregando… {payload[0]}/{payload[1]}")
                elif kind == 'done':
                    self.render(payload)
        except queue.Empty:
            pass
        try:
            self.after(100, self.poll)
        except tk.TclError:
            pass  # janela fechada

    def render(self, res):
        self.loading = False
        label = self.sources[self.source_idx][0]
        if 'error' in res:
            self.set_status(f"{label}  |  ⚠ erro ao carregar — ver {LOG_FILE}")
            return
        self.proj_map, self.summaries, self.db_files = res['proj_map'], res['summaries'], res['db_files']
        self.warnings = len(res['warnings'])
        self.grouped, self.total = res['grouped'], res['total']
        self.match, self.search_note = None, ""
        self.search_var.set("")
        try:
            self.states = self.state.load()
        except sqlite3.Error as e:
            log.warning("Falha ao ler estado: %s", e)
            self.states = {}
        self.populate()

    def populate(self):
        """Monta a árvore a partir dos dados carregados, aplicando ordenação e busca. Não toca no disco."""
        label = self.sources[self.source_idx][0]
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.sub_count = {}
        key, rev = SORT_FUNCS[self.sort_col], self.sort_rev
        flat = self.match is not None  # com busca ativa a lista é plana; sem busca, sub-agentes ficam sob o pai
        for pname in sorted(self.grouped):
            rows = [r for r in self.grouped[pname] if not flat or r['cid'] in self.match]
            if not rows:
                continue
            ids = {r['cid'] for r in rows}
            kids, roots = {}, []
            for r in rows:
                if not flat and r['parent'] in ids and r['parent'] != r['cid']:
                    kids.setdefault(r['parent'], []).append(r)
                else:
                    roots.append(r)
            for parent, lst in kids.items():
                self.sub_count[parent] = len(lst)
            proj_node = self.tree.insert("", tk.END, text=f"📁 {pname} ({len(rows)} sessões)", values=("",) * 7)
            placed = set()

            def add(parent_iid, r):
                if r['cid'] in placed:
                    return  # proteção contra ciclos de parentesco
                placed.add(r['cid'])
                ctx = fmt_tokens(r['ctx']) + (" ⚠️ [Rot]" if r['ctx'] >= ROT_TOKENS else "")
                iid = self.tree.insert(parent_iid, tk.END, text=self.leaf_text(r['cid']),
                                       values=(r['date'], r['size'], ctx, r['steps'], r['title'], r['agent'] or "-", r['cid']))
                for ch in sorted(kids.get(r['cid'], []), key=key, reverse=rev):
                    add(iid, ch)

            for r in sorted(roots, key=key, reverse=rev):
                add(proj_node, r)
            for r in sorted(rows, key=key, reverse=rev):  # sobras de um ciclo viram raízes
                add(proj_node, r)

        if self.tree.get_children():
            self.tree.item(self.tree.get_children()[0], open=True)

        text = f"{label}  |  " + (self.search_note if self.match is not None else f"{self.total} sessões")
        if self.warnings:
            text += f"  |  ⚠ {self.warnings} aviso(s) de leitura — ver {LOG_FILE}"
        self.set_status(text)

    def open_selected(self):
        """Exporta o diálogo completo da sessão selecionada."""
        self.start_export('full')

    def meta_for(self, cid):
        row = next((r for grp in self.grouped.values() for r in grp if r['cid'] == cid), {})
        s = self.summaries.get(cid, {})
        return {'cid': cid, 'title': row.get('title') or cid, 'project': row.get('project', ''),
                'workspace': urllib.parse.unquote(str(val(s, 'workspace_uris'))), 'agent': row.get('agent', ''),
                'parent': row.get('parent', ''), 'status': self.states.get(cid, 'pendente'),
                'source': self.sources[self.source_idx][0], 'fpath': self.db_files.get(cid, '')}

    def start_export(self, kind):
        if self.exporting:
            messagebox.showinfo("Aviso", "Já existe uma exportação em andamento.")
            return
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Aviso", "Selecione uma conversa na tabela.")
            return
        if not self.is_session(sel[0]):
            messagebox.showinfo("Aviso", "Clique numa conversa específica dentro da pasta do projeto.")
            return
        cid = self.cid_of(sel[0])
        meta = self.meta_for(cid)
        if not meta['fpath']:
            messagebox.showinfo("Aviso", "Esta sessão não tem arquivo de banco nesta fonte.")
            return
        try:
            os.makedirs(EXPORT_DIR, exist_ok=True)
        except OSError:
            pass
        nome = ("AntigravityGate_dialogo_" if kind == 'full' else "AntigravityGate_dossie_") + cid[:8] + ".md"
        out = filedialog.asksaveasfilename(
            title="Salvar diálogo completo" if kind == 'full' else "Salvar dossiê de retomada",
            initialdir=EXPORT_DIR if os.path.isdir(EXPORT_DIR) else None, initialfile=nome,
            defaultextension=".md", filetypes=[("Markdown", "*.md"), ("Todos os arquivos", "*.*")])
        if not out:
            return
        self.exporting = True
        self.set_status(f"{self.base_status}  |  exportando…")

        def job():
            try:
                export_session(kind, meta['fpath'], meta, out, progress=lambda n, t: self.queue.put((0, 'export_progress', (n, t))))
                self.queue.put((0, 'export_done', out))
            except Exception as e:
                log.exception("Falha ao exportar %s", cid)
                self.queue.put((0, 'export_error', f"{type(e).__name__}: {e}"))

        threading.Thread(target=job, daemon=True).start()

    def on_export_event(self, kind, payload):
        if kind == 'export_progress':
            self.status.configure(text=f"{self.base_status}  |  exportando… {payload[0]}/{payload[1]}")
            return
        self.exporting = False
        self.set_status(self.base_status)
        if kind == 'export_error':
            messagebox.showerror("Erro", f"Não foi possível exportar:\n{payload}")
            return
        opener = getattr(os, "startfile", None)
        if opener is None:
            messagebox.showinfo("Arquivo gerado", f"Salvo em:\n{payload}")
            return
        try:
            opener(payload)
        except OSError as e:
            log.warning("Arquivo salvo, mas não abriu: %s", e)
            messagebox.showinfo("Arquivo gerado", f"Salvo em:\n{payload}\n\nNão abriu automaticamente: {e}")


if __name__ == "__main__":
    setup_logging()
    app = AntigravityGateApp()
    app.mainloop()
