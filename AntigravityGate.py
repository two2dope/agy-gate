import os
import sqlite3
import glob
import re
import json
import logging
import math
import queue
import shutil
import struct
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
import zlib
import base64
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter import font as tkfont

__version__ = "0.9.0"  # ver CHANGELOG.md; 1.0.0 = revisão final + Auto-Run real testado
__build__ = "código-fonte"  # o CI troca pelo commit e pela data da montagem do .exe
APP_AUTHOR = "Thominha"
APP_EMAIL = "twoo2dope@gmail.com"
APP_GITHUB = "https://github.com/two2dope"
APP_REPO = "https://github.com/two2dope/agy-gate"

BASE_DIR = os.environ.get("ANTIGRAVITY_HOME") or os.path.join(os.path.expanduser("~"), ".gemini")
ACTIVE_SUM_DB = os.path.join(BASE_DIR, "antigravity", "conversation_summaries.db")
ACTIVE_CONV_DIR = os.path.join(BASE_DIR, "antigravity", "conversations")
ACTIVE_LABEL = "Ativas (antigravity/conversations)"
PROJECTS_DIR = os.path.join(BASE_DIR, "config", "projects")
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "AntigravityGate")
LOG_FILE = os.path.join(LOG_DIR, "gate.log")
EXPORT_DIR = os.path.join(LOG_DIR, "exports")
HANDOFF_DIR = os.path.join(LOG_DIR, "handoffs")
STATE_DB = os.path.join(LOG_DIR, "gate_state.db")  # estado do AntigravityGate; nunca grava nos bancos do Antigravity

STATUS_NAME = {"pendente": "Pendente", "aprovada": "Aprovada", "arquivada": "Arquivada"}

# Níveis de alerta do contexto (tokens de entrada da última resposta do modelo: f2 + f5 de step_payload.f5.f9).
# Faixas prontas e uma personalizada. Os valores são heurísticas de uso, não medidas: a degradação real depende do modelo e da tarefa.
CONTEXT_PRESETS = {
    "conservador": ("Conservador", 100_000, 150_000, "Troca de sessão cedo. Para tarefas longas com muitas ferramentas, onde a qualidade tende a cair primeiro."),
    "equilibrado": ("Equilibrado", 150_000, 250_000, "Padrão recomendado: avisa antes da degradação e deixa margem para gerar o dossiê e retomar."),
    "amplo": ("Amplo", 300_000, 500_000, "Para modelos de contexto muito grande e sessões em que o histórico completo importa."),
}
CONTEXT_CUSTOM = "personalizado"
DEFAULT_PRESET = "equilibrado"
LIMIT_MIN, LIMIT_MAX = 10_000, 5_000_000
CONTEXT_LIMITS = {"attention": CONTEXT_PRESETS[DEFAULT_PRESET][1], "critical": CONTEXT_PRESETS[DEFAULT_PRESET][2]}


def set_context_limits(attention, critical):
    CONTEXT_LIMITS["attention"], CONTEXT_LIMITS["critical"] = attention, critical


def ctx_level(ctx, attention=None, critical=None):
    """0 = normal, 1 = atenção, 2 = crítico."""
    attention = CONTEXT_LIMITS["attention"] if attention is None else attention
    critical = CONTEXT_LIMITS["critical"] if critical is None else critical
    return 2 if ctx >= critical else (1 if ctx >= attention else 0)


def parse_tokens(text):
    """'120000', '120.000', '1.000.000', '120k', '1,5m' -> inteiro; None se não entender."""
    t = (text or "").strip().lower().replace(" ", "").replace("_", "")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", t):  # 120.000 = cento e vinte mil
        return int(t.replace(".", ""))
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)([km])", t)
    if m:
        return round(float(m.group(1).replace(",", ".")) * (1_000 if m.group(2) == "k" else 1_000_000))
    return int(t) if t.isdigit() else None


def validate_limits(att_text, crit_text):
    """(atenção, crítico, erro). `erro` vazio quando os valores são aceitos."""
    att, crit = parse_tokens(att_text), parse_tokens(crit_text)
    if att is None or crit is None:
        return None, None, "Use números como 120000, 120.000 ou 120k."
    if not (LIMIT_MIN <= att <= LIMIT_MAX and LIMIT_MIN <= crit <= LIMIT_MAX):
        return None, None, f"Os valores precisam ficar entre {fmt_tokens(LIMIT_MIN)} e {fmt_tokens(LIMIT_MAX)} tokens."
    if crit <= att:
        return None, None, "O nível crítico precisa ser maior que o de atenção."
    return att, crit, ""


def limits_from_settings(settings):
    """(preset, atenção, crítico) a partir das preferências. AGY_ROT_TOKENS (legado) tem prioridade."""
    legacy = parse_tokens(os.environ.get("AGY_ROT_TOKENS", ""))
    if legacy:
        return CONTEXT_CUSTOM, legacy, round(legacy * 1.5)
    c = settings.get("context") if isinstance(settings.get("context"), dict) else {}
    key = c.get("preset")
    if key in CONTEXT_PRESETS:
        return key, CONTEXT_PRESETS[key][1], CONTEXT_PRESETS[key][2]
    if key == CONTEXT_CUSTOM:
        att, crit, err = validate_limits(str(c.get("attention")), str(c.get("critical")))
        if not err:
            return CONTEXT_CUSTOM, att, crit
    return DEFAULT_PRESET, CONTEXT_PRESETS[DEFAULT_PRESET][1], CONTEXT_PRESETS[DEFAULT_PRESET][2]


UUID_DB_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.db$', re.IGNORECASE)

# Posição das colunas na árvore (valores de cada linha de sessão)
COL_DATE, COL_SIZE, COL_CTX, COL_STEPS, COL_FAIL, COL_TITLE, COL_AGENT, COL_UUID = range(8)
HEADINGS = {"col_date": "Modificação", "col_size": "Tamanho", "col_ctx": "Contexto (tokens)", "col_steps": "Passos",
            "col_title": "Título / Contexto Inicial", "col_agent": "Agente", "col_fail": "Falhas", "col_uuid": "UUID"}
SORT_FUNCS = {
    "col_date": lambda r: r["date"], "col_size": lambda r: r["size_kb"], "col_ctx": lambda r: r["ctx"],
    "col_steps": lambda r: r["steps"], "col_title": lambda r: r["title"].lower(), "col_agent": lambda r: r["agent"].lower(),
    "col_fail": lambda r: r["failures"],
}
NUMERIC_COLS = ("col_date", "col_size", "col_ctx", "col_steps", "col_fail")  # primeiro clique ordena do maior para o menor

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
    m = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.\d+)?\s*(Z|[+-]\d{2}:?\d{2})?", str(v))
    if not m:
        return str(v)[:19].replace('T', ' ')
    naive = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M:%S")
    tz = m.group(3)
    if not tz:
        return naive.strftime('%Y-%m-%d %H:%M:%S')
    off = timedelta(0) if tz == "Z" else (1 if tz[0] == "+" else -1) * timedelta(hours=int(tz[1:3]), minutes=int(tz[-2:]))
    try:
        return naive.replace(tzinfo=timezone(off)).astimezone().strftime('%Y-%m-%d %H:%M:%S')  # UTC do banco -> horário local
    except (OverflowError, OSError, ValueError):
        return naive.strftime('%Y-%m-%d %H:%M:%S')


def rel_time(date_str, now=None):
    """'há 3 h', 'há 2 dias'... a partir de 'YYYY-MM-DD HH:MM:SS' no horário local."""
    try:
        then = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return ""
    secs = ((now or datetime.now()) - then).total_seconds()
    if secs < 60:
        return "agora"
    if secs < 3600:
        return f"há {int(secs // 60)} min"
    if secs < 86400:
        return f"há {int(secs // 3600)} h"
    days = int(secs // 86400)
    if days < 45:
        return f"há {days} dia" + ("s" if days != 1 else "")
    if days < 365:
        months = days // 30
        return f"há {months} " + ("mês" if months == 1 else "meses")
    years = days // 365
    return f"há {years} ano" + ("s" if years != 1 else "")


def ellipsize(text, n):
    """Corta o meio de textos longos (caminhos): 'C:\\Users\\...\\pasta'."""
    return text if len(text) <= n else text[: n // 2 - 1] + "…" + text[-(n - n // 2):]


def as_text(col):
    if isinstance(col, bytes):
        return col.decode('utf-8', errors='replace')
    return col if isinstance(col, str) else ''


def fmt_tokens(n):
    return "-" if not n else (f"{n / 1000:.0f}k" if n >= 1000 else str(n))


def ctx_label(ctx):
    """Contexto em tokens com medidor de 6 células (cheio = nível crítico) e marca de nível: ⚠ atenção, ‼ crítico."""
    if not ctx:
        return "-"
    cells = 6
    filled = min(cells, max(1, math.ceil(ctx / CONTEXT_LIMITS["critical"] * cells)))
    mark = {0: "", 1: " ⚠", 2: " ‼"}[ctx_level(ctx)]
    return f"{fmt_tokens(ctx)}  " + "■" * filled + "□" * (cells - filled) + mark


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
    """(passos, contexto estimado em tokens, prévia, falhas de ferramenta) de um banco de sessão, lendo só o necessário."""
    with open_ro(path) as c:
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'steps' not in tables:
            return 0, 0, '', 0
        cnt = c.execute("SELECT COUNT(*) FROM steps").fetchone()[0]
        ctx = 0
        try:  # passos de ferramenta (tipo 132) que não terminaram com status 3
            fails = c.execute("SELECT COUNT(*) FROM steps WHERE step_type=132 AND status != 3").fetchone()[0]
        except sqlite3.OperationalError:
            fails = 0
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
        return cnt, ctx, preview, fails


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


FILE_ICONS = {
    ".py": "🐍", ".pyw": "🐍", ".js": "📜", ".mjs": "📜", ".jsx": "📜", ".ts": "📘", ".tsx": "📘", ".html": "🌐", ".htm": "🌐",
    ".css": "🎨", ".scss": "🎨", ".json": "🧾", ".yaml": "⚙️", ".yml": "⚙️", ".toml": "⚙️", ".ini": "⚙️", ".cfg": "⚙️",
    ".md": "📝", ".txt": "📄", ".bat": "⌨️", ".cmd": "⌨️", ".ps1": "⌨️", ".sh": "⌨️", ".sql": "🗄️", ".db": "🗄️", ".sqlite": "🗄️",
    ".png": "🖼️", ".jpg": "🖼️", ".jpeg": "🖼️", ".gif": "🖼️", ".webp": "🖼️", ".svg": "🖼️", ".pdf": "📕", ".zip": "🗜️",
    ".csv": "📊", ".xlsx": "📊", ".log": "📋", ".lock": "🔒", ".env": "🔒", ".gitignore": "🙈", ".ipynb": "📓", ".go": "🐹", ".rs": "🦀",
}


def file_icon(path):
    """Emoji do tipo de arquivo (Markdown/terminais com suporte a emoji)."""
    name = re.split(r"[\\/]", path)[-1].lower()
    if name.startswith(".env"):
        return "🔒"
    if name in ("dockerfile", "makefile"):
        return "⚙️"
    return FILE_ICONS.get(os.path.splitext(name)[1], FILE_ICONS.get(name, "📄"))


def disk_state(path):
    """'✔' existe, '✖ não existe mais', ou '?' quando o caminho não pode ser conferido neste computador."""
    if not os.path.isabs(path):
        return "?"
    try:
        return "✔" if os.path.exists(path) else "✖ não existe mais"
    except OSError:
        return "?"


def classify_tool(name):
    low = name.lower()
    if any(h in low for h in TOOL_WRITE_HINTS):
        return "write"
    if any(h in low for h in TOOL_CMD_HINTS):
        return "cmd"
    return "read"


def collect_file_activity(steps):
    """{caminho: [alterações, leituras]} a partir dos passos de ferramenta (classificação por nome: heurística)."""
    acts = {}
    for _total, _n, st in steps:
        if st['kind'] != 'tool' or not st['calls']:
            continue
        kind = classify_tool(st['calls'][0]['name'])
        if kind == "cmd":
            continue
        for pth in tool_paths(st['calls'][0]['args']):
            acts.setdefault(pth, [0, 0])[0 if kind == "write" else 1] += 1
    return acts


def files_table(acts, mode, limit=60):
    """Tabela Markdown de arquivos. mode: 'mod' (só alterações), 'read' (só leituras) ou 'both'."""
    rows = sorted(((p, v[0], v[1]) for p, v in acts.items() if (mode == "both" or v[0 if mode == "mod" else 1])),
                  key=lambda r: (-(r[1] if mode != "read" else r[2]), -r[2], r[0].lower()))
    head = {"mod": "| | Arquivo | Alterações | No disco |\n| :-: | :-- | --: | :-- |\n", "read": "| | Arquivo | Leituras | No disco |\n| :-: | :-- | --: | :-- |\n",
            "both": "| | Arquivo | Alterado | Lido | No disco |\n| :-: | :-- | --: | --: | :-- |\n"}[mode]
    out = head
    for p, mod, rd in rows[:limit]:
        cell = p.replace("|", "\\|")
        counts = {"mod": f"×{mod}", "read": f"×{rd}", "both": f"{'×' + str(mod) if mod else '-'} | {'×' + str(rd) if rd else '-'}"}[mode]
        out += f"| {file_icon(p)} | `{cell}` | {counts} | {disk_state(p)} |\n"
    if len(rows) > limit:
        out += f"\n_… e mais {len(rows) - limit} arquivo(s)._\n"
    return out + "\n_\"No disco\" foi conferido neste computador, no momento em que o arquivo foi gerado._\n"


def meta_table(meta, qm):
    rows = [("UUID da sessão", meta['cid']), ("Projeto", meta.get('project') or '-'), ("Workspace", meta.get('workspace') or '-'),
            ("Agente", meta.get('agent') or '-'), ("Sessão pai", meta.get('parent') or '-'),
            ("Modelo(s)", ", ".join(qm['models']) or '-'), ("Início", fmt_ts(qm['started'], True)), ("Fim", fmt_ts(qm['ended'], True)),
            ("Passos", qm['steps']), ("Contexto na última resposta", (f"{qm['ctx']} tokens" + {0: "", 1: " (atenção)", 2: " (crítico)"}[ctx_level(qm['ctx'])]) if qm['ctx'] else '-'),
            ("Status no AntigravityGate", meta.get('status') or 'pendente'), ("Fonte", meta.get('source') or '-'),
            ("Banco", meta.get('fpath') or '-'), ("Gerado em", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))]
    out = "| Campo | Valor |\n| :--- | :--- |\n"
    for k, v in rows:
        out += f"| {k} | {str(v).replace('|', '/').replace(chr(10), ' ')} |\n"
    return out


def write_full_export(fh, meta, qm, steps, progress=None, files=None):
    fh.write(f"# Diálogo completo — {meta.get('title') or meta['cid']}\n\n")
    fh.write("> Este arquivo reproduz o conteúdo da conversa e pode conter chaves, senhas e dados pessoais. "
             "Revise antes de compartilhar. Horários no fuso local deste computador.\n\n")
    fh.write(meta_table(meta, qm) + "\n")
    if files:
        fh.write(f"## Arquivos citados ({len(files)})\n\n" + files_table(files, "both") + "\n")
    fh.write("---\n\n## Linha do tempo\n\n")
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
            kind_tool = classify_tool(name)
            if kind_tool == "write":
                for pth in tool_paths(c['args']):
                    files_mod[pth] = files_mod.get(pth, 0) + 1
            elif kind_tool == "cmd":
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
        o.append(files_table({p: [n, 0] for p, n in files_mod.items()}, "mod", 40))
    if files_read:
        o.append(f"## Arquivos consultados ({len(files_read)})\n")
        o.append(files_table({p: [0, n] for p, n in files_read.items()}, "read", 40))
    if commands:
        o.append(f"## Comandos executados (últimos {min(len(commands), 25)} de {len(commands)})\n")
        o.append("\n".join(f"- {fmt_ts(ts)} {'ok' if ok else '⚠ falhou'}: `{' '.join(c.split())[:200]}`" for ts, c, ok in commands[-25:]) + "\n")
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


class ExportCancelled(Exception):
    """Levantada pelo callback de progresso para interromper uma exportação."""


def export_session(kind, fpath, meta, out_path, progress=None):
    """Grava o diálogo completo ('full') ou o dossiê de retomada ('dossier') de uma sessão.
    Escreve num arquivo .part e só o renomeia no fim: erro ou cancelamento não deixam arquivo pela metade."""
    tmp = out_path + ".part"
    try:
        with open_ro(fpath) as conn:
            qm = quick_meta(conn)
            if kind == 'full':
                files = collect_file_activity(iter_steps(conn))
                with open(tmp, 'w', encoding='utf-8', newline='\n') as fh:
                    write_full_export(fh, meta, qm, iter_steps(conn), progress, files)
            else:
                text = build_dossier(meta, qm, iter_steps(conn), progress)
                with open(tmp, 'w', encoding='utf-8', newline='\n') as fh:
                    fh.write(text)
        os.replace(tmp, out_path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


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
            conn.execute("CREATE TABLE IF NOT EXISTS handoffs(id INTEGER PRIMARY KEY AUTOINCREMENT, src_cid TEXT NOT NULL, new_cid TEXT, "
                         "dossier_path TEXT, status TEXT NOT NULL, detail TEXT, at TEXT NOT NULL)")
        if self.persistent:
            conn.close()

    def load(self):
        with self._connect() as c:
            return dict(c.execute("SELECT cid, status FROM session_state").fetchall())

    def add_handoff(self, src_cid, new_cid, dossier_path, status, detail=''):
        with self._connect() as c:
            with c:
                c.execute("INSERT INTO handoffs(src_cid, new_cid, dossier_path, status, detail, at) VALUES(?,?,?,?,?,?)",
                          (src_cid, new_cid, dossier_path, status, detail[:500], datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    def handoffs_ok(self):
        """src_cid -> new_cid da retomada concluída mais recente."""
        with self._connect() as c:
            return dict(c.execute("SELECT src_cid, new_cid FROM handoffs WHERE status='ok' ORDER BY id").fetchall())

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


# --- Auto-Run (retomada limpa, opção B) -------------------------------------------------------

AGY_TIMEOUT_S = 600
# Nomes aceitos por `agy --model`, copiados da lista que o próprio agy devolveu em 2026-10-26 (o esforço faz parte do nome).
# Se o agy mudar a lista, o erro dele traz a nova, e o app passa a oferecê-la (settings: agy_models_known).
AGY_MODELS = ["Gemini 3.8 Flash (Medium)", "Gemini 3.8 Flash (High)", "Gemini 3.8 Flash (Low)",
              "Gemini 4 Argon (Medium)", "Gemini 4 Argon (High)", "Gemini 4 Argon (Low)",
              "Claude Sonnet 5.5 (Medium)", "Claude Sonnet 5.5 (High)", "Claude Sonnet 5.5 (Low)",
              "Claude Opus 5.5 (Medium)", "Claude Opus 5.5 (High)", "Claude Opus 5.5 (Low)", "GPT-OSS 120B (Medium)"]


def parse_agy_models(text):
    """Lista que o agy imprime depois de 'Available models:' quando recusa um --model."""
    m = re.search(r"Available models:\s*\n((?:[ \t]+\S.*(?:\n|$))+)", text or "")
    return [ln.strip() for ln in m.group(1).splitlines() if ln.strip()] if m else []
# Uma linha só: num shim .cmd/.bat, o cmd.exe encerra a linha de comando na primeira quebra de linha.
AGY_PROMPT = ("Você está retomando o trabalho de uma sessão anterior. Leia o dossiê em: {path} . "
              "Depois responda, em poucas linhas: (1) o que entendeu do objetivo e do estado atual; (2) o que falta; "
              "(3) os próximos passos que propõe. Não altere nenhum arquivo e não execute comandos; aguarde minha confirmação.")


def find_agy():
    exe = os.environ.get("AGY_EXE")
    if exe:
        return exe if os.path.isfile(exe) else None
    return shutil.which("agy")


def uri_to_path(uri, nt=None):
    """file:///c%3A/Users/... -> c:\\Users\\... (Windows) ou /home/... (outros).
    O url2pathname do Windows não reconhece a letra da unidade com ':' codificado (%3A, como o Antigravity grava)
    e devolvia '\\c:\\...', um caminho que não existe."""
    nt = (os.name == "nt") if nt is None else nt
    path = urllib.parse.unquote(urllib.parse.urlparse(uri).path)
    if nt:
        if re.match(r"^/[A-Za-z]:", path):
            path = path[1:]
        path = path.replace("/", "\\")
    return path


def workspace_dirs(uris):
    """Pastas existentes citadas em workspace_uris (file:///...)."""
    out = []
    for uri in re.findall(r"file://[^\s,;\"'\[\]<>]+", uris or ""):  # URIs vêm codificadas (%20), às vezes dentro de uma lista JSON
        path = uri_to_path(uri)
        if os.path.isdir(path) and path not in out:
            out.append(path)
    return out[:3]


def uri_paths(uris):
    """Caminhos citados em workspace_uris (sem exigir que existam), para exibição."""
    out = []
    for uri in re.findall(r"file://[^\s,;\"'\[\]<>]+", uris or ""):
        path = uri_to_path(uri)
        if path not in out:
            out.append(path)
    return out


def build_agy_args(agy, dossier_path, extra_dirs, mode="plan", timeout_s=AGY_TIMEOUT_S, model=None):
    """Lista de argumentos (sem shell). Nunca inclui --dangerously-skip-permissions.
    As flags de segurança vêm antes do prompt: se algo truncar a linha, o prompt se perde, nunca o `--mode`."""
    args = [agy, "--output-format", "json", "--mode", mode, "--print-timeout", f"{timeout_s}s",
            "--add-dir", os.path.dirname(dossier_path)]
    for d in extra_dirs:
        args += ["--add-dir", d]
    if model and model.strip():  # vazio = modelo padrão do agy
        args += ["--model", model.strip()]
    return args + ["--print", AGY_PROMPT.format(path=dossier_path)]


CMD_UNSAFE = set('"%^&|<>!\r\n')


def cmd_shim_problem(args):
    """Um `agy` .cmd/.bat roda pelo cmd.exe, que reinterpreta a linha de comando (%, &, |, quebras de linha...)
    e pode descartar ou trocar argumentos. Devolve o motivo para não executar, ou '' se é seguro."""
    if os.path.splitext(args[0])[1].lower() not in (".cmd", ".bat"):
        return ""
    bad = sorted({ch for a in args[1:] for ch in a if ch in CMD_UNSAFE})
    if not bad:
        return ""
    shown = " ".join(repr(ch) for ch in bad)
    return (f"o agy é um script {os.path.splitext(args[0])[1]} (passa pelo cmd.exe) e os argumentos têm caracteres "
            f"que o cmd.exe reinterpreta ({shown}). Defina AGY_EXE com o caminho de um agy.exe ou use uma pasta sem esses caracteres.")


def parse_agy_output(stdout, stderr, returncode=None):
    """Interpreta a saída do agy. Formato conhecido: um objeto JSON com conversation_id, status, response, error, usage;
    em erro, linhas 'error: ...' e 'AGY_ERROR: {json}' vão para stderr. Aceita saída fora do padrão sem quebrar.
    Sucesso exige tudo: código de saída 0 (quando informado), conversation_id, status diferente de ERROR e erro vazio.
    Na dúvida é falha: um sucesso falso tiraria a sessão do próximo lote."""
    obj = None
    for chunk in [stdout.strip()] + [ln.strip() for ln in reversed(stdout.strip().splitlines())]:
        if chunk.startswith("{"):
            try:
                obj = json.loads(chunk)
                break
            except ValueError:
                continue
    blob = f"{stdout}\n{stderr}"
    quota = "RESOURCE_EXHAUSTED" in blob or "quota reached" in blob.lower() or '"error_code":429' in blob.replace(" ", "")
    m = re.search(r"Resets in ([0-9hms ]+?)(?:\.|\"|$|\n)", blob)
    res = {'ok': False, 'conversation_id': '', 'response': '', 'error': '', 'quota': quota, 'reset': m.group(1).strip() if m else ''}
    if isinstance(obj, dict):
        res['conversation_id'] = str(obj.get('conversation_id') or '')
        res['response'] = str(obj.get('response') or '')
        res['error'] = str(obj.get('error') or '')
        if not res['error'] and str(obj.get('status', '')).upper() == 'ERROR':
            res['error'] = "agy informou status ERROR sem mensagem"
        if not res['error'] and not res['conversation_id']:
            res['error'] = "resposta sem conversation_id"
    else:
        res['error'] = "saída sem JSON reconhecível: " + (blob.strip()[:200] or "(vazia)")
    if returncode not in (None, 0) and not res['error']:
        res['error'] = f"agy terminou com código {returncode}"
    res['ok'] = not res['error']
    return res


class AutoRunner:
    """Percorre as sessões aprovadas: gera o dossiê local e, se não for simulação, abre uma sessão nova com `agy --print`.
    Roda em thread de trabalho; fala com a tela só por `log` (callback). Sem Tk aqui."""

    def __init__(self, items, store, log_cb, agy=None, dry_run=True, mode="plan", timeout_s=AGY_TIMEOUT_S, max_failures=3, grace_s=60, model=None):
        self.items, self.store, self.log_cb = items, store, log_cb
        self.model = model
        self.grace_s = grace_s
        self.agy, self.dry_run, self.mode, self.timeout_s, self.max_failures = agy, dry_run, mode, timeout_s, max_failures
        self.cancelled = False
        self.proc = None

    def cancel(self):
        self.cancelled = True
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except OSError:
                pass

    @staticmethod
    def _session_files():
        """UUIDs das sessões na pasta ativa (para achar a sessão que o agy cria mesmo quando falha)."""
        return {os.path.splitext(e.name)[0] for e in scandir_safe(ACTIVE_CONV_DIR) if e.is_file() and UUID_DB_RE.match(e.name)}

    def _run_agy(self, args):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                     encoding="utf-8", errors="replace", creationflags=flags)
        deadline = time.time() + self.timeout_s + self.grace_s
        while True:
            try:
                out, err = self.proc.communicate(timeout=0.3)
                # cancel() pode ter encerrado o processo: então a saída é de um agy interrompido, não uma resposta.
                # Se ele terminou com 0 antes do cancelamento chegar, a resposta vale.
                code = self.proc.returncode
                return out, err, "cancelada" if self.cancelled and code != 0 else None, code
            except subprocess.TimeoutExpired:
                if self.cancelled:
                    self.proc.terminate()
                    try:
                        out, err = self.proc.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.proc.kill()
                        out, err = self.proc.communicate()
                    return out, err, "cancelada", self.proc.returncode
                if time.time() > deadline:
                    self.proc.kill()
                    out, err = self.proc.communicate()
                    return out, err, "tempo esgotado", self.proc.returncode

    def run(self):
        os.makedirs(HANDOFF_DIR, exist_ok=True)
        summary = {'ok': 0, 'dossier': 0, 'failed': 0, 'skipped': 0, 'quota': '', 'junk': [], 'aborted': '', 'models': [], 'bad_model': ''}
        failures = 0
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        n = len(self.items)
        for i, it in enumerate(self.items):
            if self.cancelled:
                summary['skipped'] += n - i
                summary['aborted'] = 'cancelado pelo usuário'
                self.log_cb(f"Cancelado. {n - i} sessão(ões) não executadas.")
                break
            cid, title = it['cid'], it['title']
            self.log_cb(f"[{i + 1}/{n}] {title}  ({cid[:8]})")
            dossier = os.path.join(HANDOFF_DIR, f"retomada_{cid[:8]}_{stamp}.md")
            try:
                export_session('dossier', it['fpath'], it['meta'], dossier)
            except Exception as e:
                log.exception("Dossiê falhou para %s", cid)
                self.store.add_handoff(cid, '', dossier, 'erro', f"dossiê: {e}")
                summary['failed'] += 1
                failures += 1
                self.log_cb(f"    ✖ não foi possível gerar o dossiê: {e}")
                if failures >= self.max_failures:
                    summary['skipped'] += n - i - 1
                    summary['aborted'] = f"{failures} falhas seguidas"
                    self.log_cb(f"Interrompido após {failures} falhas seguidas.")
                    break
                continue
            self.log_cb(f"    dossiê: {dossier}")
            if self.dry_run:
                self.store.add_handoff(cid, '', dossier, 'dossie', 'simulação: agy não foi chamado')
                summary['dossier'] += 1
                continue
            args = build_agy_args(self.agy, dossier, workspace_dirs(it.get('workspace', '')), self.mode, self.timeout_s, self.model)
            problem = cmd_shim_problem(args)
            if problem:
                self.store.add_handoff(cid, '', dossier, 'erro', problem)
                summary['failed'] += 1
                summary['skipped'] += n - i - 1
                summary['aborted'] = 'agy .cmd/.bat inseguro'
                self.log_cb(f"    ✖ não executado: {problem}")
                break
            before = self._session_files()
            try:
                out, err, why, code = self._run_agy(args)
            except OSError as e:
                self.store.add_handoff(cid, '', dossier, 'erro', f"não executou o agy: {e}")
                summary['failed'] += 1
                self.log_cb(f"    ✖ não foi possível executar o agy: {e}")
                summary['skipped'] += n - i - 1
                summary['aborted'] = 'agy não executou'
                break
            if why:
                self.store.add_handoff(cid, '', dossier, 'erro', why)
                summary['failed'] += 1
                self.log_cb(f"    ✖ {why}")
                if why == "cancelada":
                    summary['skipped'] += n - i - 1
                    summary['aborted'] = 'cancelado pelo usuário'
                    break
                failures += 1
            else:
                log.info("agy %s: código %s; stdout %s; stderr %s", cid[:8], code, out[:4000], err[:2000])
                res = parse_agy_output(out, err, code)
                new_cid = res['conversation_id']
                if res['ok']:
                    self.store.add_handoff(cid, new_cid, dossier, 'ok', res['response'][:300])
                    summary['ok'] += 1
                    failures = 0
                    self.log_cb(f"    ✔ sessão nova: {new_cid or '(sem id)'}")
                    if res['response']:
                        self.log_cb("    resposta: " + " ".join(res['response'].split())[:300])
                    continue
                self.store.add_handoff(cid, new_cid, dossier, 'erro', res['error'])
                summary['failed'] += 1
                # O agy cria a sessão mesmo quando falha, às vezes sem informar o id: o que surgiu na pasta é dessa tentativa.
                for junk in ([new_cid] if new_cid else []) + sorted(self._session_files() - before - {new_cid}):
                    if junk not in summary['junk']:
                        summary['junk'].append(junk)
                self.log_cb(f"    ✖ {(res['error'].strip().splitlines() or [''])[0][:300]}")
                models = parse_agy_models(res['error']) or parse_agy_models(err)
                if models:
                    summary['models'] = models
                    if self.model and self.model not in models:
                        summary['bad_model'] = self.model
                    self.log_cb("    Modelos aceitos pelo agy (escolha um na lista do campo Modelo): " + "; ".join(models))
                if res['quota']:
                    summary['quota'] = res['reset'] or 'horário não informado'
                    summary['skipped'] += n - i - 1
                    summary['aborted'] = 'cota esgotada'
                    self.log_cb(f"Cota do modelo esgotada (volta em {summary['quota']}). Lote interrompido; "
                                f"{n - i - 1} sessão(ões) não executadas, sem novas tentativas.")
                    break
                failures += 1
            if failures >= self.max_failures:
                summary['skipped'] += n - i - 1
                summary['aborted'] = f"{failures} falhas seguidas"
                self.log_cb(f"Interrompido após {failures} falhas seguidas.")
                break
        if summary['junk']:
            try:
                self.store.set_many(summary['junk'], 'arquivada')
                self.log_cb(f"{len(summary['junk'])} sessão(ões) vazia(s) criada(s) pelas tentativas com erro foram marcadas como arquivadas.")
            except sqlite3.Error:
                pass
        return summary


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
        ctx = fails = 0

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
                    m = (0, 0, '', 0)
            cnt, ctx, first, fails = m
            step_count = max(step_count, cnt)
            if not preview:
                preview = first

        proj_name = proj_map.get(pid, '')
        w_decoded = urllib.parse.unquote(w_uris)
        ws_paths = uri_paths(w_uris)
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
            'failures': fails,
            'workspace': ", ".join(ws_paths),
            'ws_ok': (all(os.path.isdir(x) for x in ws_paths) if ws_paths else None),
            'origin': "CLI" if "CLI" in str(val(s, 'source')) else "",
            'running': str(val(s, 'status')) not in ("", "CASCADE_RUN_STATUS_IDLE"),
            'killed': bool(s.get('killed')),
        })

    return {'grouped': grouped, 'total': len(all_cids), 'warnings': warnings,
            'proj_map': proj_map, 'summaries': summaries, 'db_files': db_files}


# --- temas, ícones e widgets visuais ----------------------------------------------------------

SETTINGS_FILE = os.path.join(LOG_DIR, "settings.json")

# Paletas inspiradas nas 6 skins do Cyber-HUD do navigator-agy (cores sólidas: o Tk não faz gradiente nem transparência).
# Todas as combinações de texto foram checadas para contraste >= 4,5:1 (WCAG AA).
_BASE = dict(radius=8, title_fonts=("Segoe UI Semibold", "Segoe UI"))
THEMES = {
    "escuro": dict(name="Escuro", bg="#1e1e1e", panel="#252526", panel2="#333333", border="#454545", fg="#d4d4d4", muted="#9da0a6",
                   accent="#007acc", accent_fg="#ffffff", accent_text="#4daafc", success="#3fb950", warning="#e3b341", danger="#f85149",
                   sel_bg="#094771", sel_fg="#ffffff", header_bg="#252526", header_fg="#d4d4d4", **_BASE),
    "claro": dict(name="Claro", bg="#f5f5f5", panel="#ffffff", panel2="#e6e6e6", border="#cfcfcf", fg="#222222", muted="#5f6368",
                  accent="#005a9e", accent_fg="#ffffff", accent_text="#005a9e", success="#1a7f37", warning="#855300", danger="#cf222e",
                  sel_bg="#cfe4f7", sel_fg="#111111", header_bg="#ffffff", header_fg="#222222", **_BASE),
    "milspec": dict(name="Mil-Spec", bg="#111216", panel="#17181f", panel2="#232732", border="#3c4250", fg="#e7ecf3", muted="#9aa4b5",
                    accent="#4ade80", accent_fg="#07140c", accent_text="#4ade80", success="#4ade80", warning="#facc15", danger="#f87171",
                    sel_bg="#28303e", sel_fg="#4ade80", header_bg="#232732", header_fg="#f1f5f9", radius=6, title_fonts=("Bahnschrift", "Consolas", "Segoe UI")),
    "cyber": dict(name="Cyber Synthwave", bg="#04050e", panel="#0d0a1f", panel2="#17082c", border="#0e7f8f", fg="#e6fbff", muted="#8fb5c2",
                  accent="#00f0ff", accent_fg="#001418", accent_text="#00f0ff", success="#39ff88", warning="#ffd166", danger="#ff4d94",
                  sel_bg="#2a0a3d", sel_fg="#00f0ff", header_bg="#17082c", header_fg="#00f0ff", radius=4, title_fonts=("Bahnschrift", "Consolas", "Segoe UI")),
    "vidro": dict(name="Vidro Aero", bg="#060f1e", panel="#0a1830", panel2="#10294a", border="#2b6a8f", fg="#f8fafc", muted="#9db4cc",
                  accent="#38bdf8", accent_fg="#04121f", accent_text="#38bdf8", success="#34d399", warning="#fbbf24", danger="#f87171",
                  sel_bg="#12406a", sel_fg="#ffffff", header_bg="#0d2140", header_fg="#f8fafc", radius=10, title_fonts=("Segoe UI Semibold", "Segoe UI")),
    "brutal": dict(name="Brutalista", bg="#090a0e", panel="#000000", panel2="#1a1a1a", border="#ffffff", fg="#ffffff", muted="#b3b3b3",
                   accent="#facc15", accent_fg="#000000", accent_text="#facc15", success="#4ade80", warning="#facc15", danger="#ff6b6b",
                   sel_bg="#facc15", sel_fg="#000000", header_bg="#facc15", header_fg="#000000", radius=0, title_fonts=("Bahnschrift", "Arial Black", "Segoe UI")),
    "obsidiana": dict(name="Obsidiana", bg="#020204", panel="#0b0614", panel2="#14091f", border="#3b2158", fg="#f3ecff", muted="#a99dbd",
                      accent="#c084fc", accent_fg="#12081f", accent_text="#c084fc", success="#6ee7b7", warning="#fbbf24", danger="#fb7185",
                      sel_bg="#2b1646", sel_fg="#e9d5ff", header_bg="#0a0312", header_fg="#f3ecff", radius=12, title_fonts=("Segoe UI Semibold", "Segoe UI")),
    "mecha": dict(name="Mecha", bg="#080b12", panel="#0e131d", panel2="#1b1610", border="#7a3a10", fg="#f6ede4", muted="#b5a595",
                  accent="#f97316", accent_fg="#1a0802", accent_text="#f97316", success="#84cc16", warning="#fbbf24", danger="#f87171",
                  sel_bg="#3a1d08", sel_fg="#ffb066", header_bg="#140c07", header_fg="#f97316", radius=6, title_fonts=("Bahnschrift", "Consolas", "Segoe UI")),
}
THEME_ORDER = ["escuro", "claro", "milspec", "cyber", "vidro", "brutal", "obsidiana", "mecha"]

# nome -> (Segoe MDL2 Assets, alternativa Unicode). Se os ícones do Windows aparecerem errados, use Tema > Ícones > Símbolos Unicode.
ICONS = {
    "refresh": ("\uE72C", "↻"), "search": ("\uE721", "⌕"), "clear": ("\uE711", "✕"), "approve": ("\uE73E", "✔"),
    "archive": ("\uE7B8", "▣"), "pending": ("\uE7A7", "↶"), "export": ("\uE74E", "↧"), "dossier": ("\uE768", "▶"),
    "autorun": ("\uE945", "⚡"), "theme": ("\uE790", "◐"), "warn": ("\uE7BA", "⚠"), "limits": ("\uE713", "⚙"), "copy": ("\uE8C8", "⧉"), "folder": ("\uE838", "▭"),
    "about": ("\uE946", "ⓘ"),
}


def about_info():
    """Versão e ambiente em texto simples, para a janela Sobre e para colar num relato de problema."""
    import platform
    import sys
    run = "executável (.exe)" if getattr(sys, "frozen", False) else "código-fonte"
    return "\n".join([
        f"AntigravityGate {__version__} ({run}; montagem {__build__})",
        f"Python {platform.python_version()} · Tk {tk.TkVersion}",
        f"Sistema: {platform.platform()}",
        f"Pasta do Antigravity: {BASE_DIR}",
        f"agy: {find_agy() or 'não encontrado'}",
        f"Dados do app: {LOG_DIR}",
        f"Log: {LOG_FILE}",
    ])


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(d):
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=2)
    except OSError as e:
        log.warning("Não foi possível salvar as preferências: %s", e)


WIN_DEFAULT = (1240, 820)  # tamanho de projeto, em pixels a 96 dpi
WIN_MIN = (760, 520)


def _win_work_area(x=None, y=None):
    """Área útil (x, y, largura, altura), sem a barra de tarefas, do monitor que contém o ponto (x, y); sem ponto, a do principal.
    Só Windows. Levanta exceção se a consulta falhar."""
    import ctypes
    from ctypes import wintypes

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    user32 = ctypes.windll.user32
    if x is None:
        r = wintypes.RECT()
        if not user32.SystemParametersInfoW(48, 0, ctypes.byref(r), 0):  # SPI_GETWORKAREA
            raise OSError("SystemParametersInfoW falhou")
    else:
        user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        user32.MonitorFromPoint.restype = ctypes.c_void_p
        user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        hmon = user32.MonitorFromPoint(wintypes.POINT(int(x), int(y)), 2)  # MONITOR_DEFAULTTONEAREST
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not hmon or not user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            raise OSError("GetMonitorInfoW falhou")
        r = info.rcWork
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def work_area_at(root, x=None, y=None):
    """Área útil do monitor do ponto (x, y) ou do principal. Fora do Windows, ou se a consulta falhar, vale a tela inteira."""
    if os.name == "nt":
        try:
            area = _win_work_area(x, y)
            if area[2] >= 300 and area[3] >= 300:
                return area
        except Exception as e:
            log.warning("Não foi possível consultar a área útil da tela: %s", e)
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def fit_rect(area, scale, w, h, x=None, y=None, min_size=WIN_MIN):
    """(largura, altura, x, y) de uma janela w×h dentro da área útil: nunca maior que ela (já descontados a barra de título e uma folga)
    e com a posição inteira à vista. Sem posição, centraliza."""
    l, t, aw, ah = area
    frame, gap = round(40 * scale), round(10 * scale)  # barra de título + bordas; folga
    max_w, max_h = max(1, int(aw * 0.96)), max(1, ah - frame - gap)
    w, h = max(min(w, max_w), min(min_size[0], max_w)), max(min(h, max_h), min(min_size[1], max_h))
    if x is None:
        return w, h, l + (aw - w) // 2, t + max(0, (ah - h - frame) // 2)
    return w, h, min(max(x, l), max(l, l + aw - w)), min(max(y, t), max(t, t + ah - h - frame))


def parse_geometry(text):
    """'LxA+X+Y' -> (L, A, X, Y). O Windows escreve coordenada negativa como '+-1928' (monitor à esquerda ou acima
    do principal). '-N' (distância da borda direita/inferior) não é posição absoluta: devolve None."""
    m = re.match(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$", text or "")
    return tuple(int(v) for v in m.groups()) if m else None


def saved_zoomed(saved):
    """True se a janela estava maximizada ao fechar (com o ponto do monitor onde estava)."""
    return (isinstance(saved, dict) and saved.get("zoomed") is True
            and all(isinstance(saved.get(k), int) and not isinstance(saved.get(k), bool) for k in ("zx", "zy")))


def window_geometry(work_at, scale, saved=None):
    """(largura, altura, x, y) da janela principal. Parte do tamanho de projeto (ou do salvo) e fica dentro da área útil do monitor
    onde estava (ou do principal, se não houver posição salva). `work_at(x, y)` devolve a área útil do monitor desse ponto."""
    w, h, x, y = round(WIN_DEFAULT[0] * scale), round(WIN_DEFAULT[1] * scale), None, None
    if isinstance(saved, dict):
        vals = [saved.get(k) for k in ("w", "h", "x", "y")]
        if all(isinstance(v, int) and not isinstance(v, bool) for v in vals) and 300 <= vals[0] <= 20000 and 300 <= vals[1] <= 20000:
            w, h, x, y = vals
    if saved_zoomed(saved):
        # Maximizada: o tamanho normal fica no monitor onde ela estava maximizada (o mesmo em que vai reabrir).
        area = work_at(saved["zx"], saved["zy"])
        l, t, aw, ah = area
        if x is not None and not (l <= x + w // 2 < l + aw and t <= y + h // 2 < t + ah):
            x = y = None
        return fit_rect(area, scale, w, h, x, y)
    area = work_at(None, None) if x is None else work_at(x + w // 2, y + h // 2)
    return fit_rect(area, scale, w, h, x, y)


def place_over(win, parent, size=None):
    """Centraliza a janela `win` sobre `parent`, dentro da área útil do monitor de `parent`. Sem isso o Windows abre janelas
    adicionais no canto do monitor principal, onde a barra de tarefas pode cobrir a barra de título. `size`: (largura, altura)
    fixos; senão vale o tamanho que o conteúdo pede."""
    win.withdraw()  # não aparece na posição padrão antes de ser movida
    win.update_idletasks()
    w, h = size or (win.winfo_reqwidth(), win.winfo_reqheight())
    px, py, pw, ph = parent.winfo_rootx(), parent.winfo_rooty(), parent.winfo_width(), parent.winfo_height()
    area = work_area_at(win, px + pw // 2, py + ph // 2)
    w, h, x, y = fit_rect(area, win.winfo_fpixels('1i') / 96, w, h, px + (pw - w) // 2, py + (ph - h) // 2, min_size=(0, 0))
    win.geometry(f"{w}x{h}+{x}+{y}")
    if hasattr(parent, "t"):
        style_titlebar(win, parent.t)
    win.deiconify()
    try:
        win.wait_visibility()
    except tk.TclError:
        pass


def dropdown_pos(area, ax, ay, aw, ah, w, h, gap=2):
    """Posição (x, y) de uma lista w×h aberta sob o botão (ax, ay, aw, ah), alinhada à direita dele e dentro da área útil
    `area` do monitor do botão. Aceita coordenadas negativas (monitor à esquerda ou acima do principal). Sem espaço
    embaixo, abre para cima."""
    l, t, W, H = area
    x = min(max(ax + aw - w, l), max(l, l + W - w))
    y = ay + ah + gap
    if y + h > t + H:
        y = max(t, ay - h - gap)
    return x, y


def is_dark_color(h):
    r, g, b = _rgb(h)
    return 0.299 * r + 0.587 * g + 0.114 * b < 128


def style_titlebar(win, t):
    """Pinta a barra de título nativa do Windows com as cores do tema, sem perder arrastar, encaixar e redimensionar.
    Windows 10 (1809+): modo claro ou escuro conforme o tema. Windows 11: cor, texto e borda exatos.
    Devolve {atributo: HRESULT} (0 = aplicado) ou None fora do Windows. Nunca levanta."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
        user32.GetParent.argtypes, user32.GetParent.restype = [wintypes.HWND], wintypes.HWND
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()

        def put(attr, value):
            v = ctypes.c_int(value)
            return dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))

        colorref = lambda hx: (lambda r, g, b: r | g << 8 | b << 16)(*_rgb(hx))  # 0x00BBGGRR
        dark = int(is_dark_color(t['header_bg']))
        res = {"escuro": put(20, dark)}  # DWMWA_USE_IMMERSIVE_DARK_MODE
        if res["escuro"] != 0:
            res["escuro_antigo"] = put(19, dark)  # Windows 10 1809 a 1909
        res["fundo"] = put(35, colorref(t['header_bg']))  # DWMWA_CAPTION_COLOR (Windows 11)
        res["texto"] = put(36, colorref(t['header_fg']))  # DWMWA_TEXT_COLOR
        res["borda"] = put(34, colorref(t['border']))  # DWMWA_BORDER_COLOR
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x37)  # sem mover/redimensionar/ativar; só repinta a moldura
        return res
    except Exception as e:
        log.warning("Não foi possível pintar a barra de título: %s", e)
        return None


def _rgb(h):
    h = h.lstrip('#')
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def blend(a, b, t):
    """Mistura a cor `a` com `b`: t=0 devolve a, t=1 devolve b."""
    ra, rb = _rgb(a), _rgb(b)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ra, rb))


def _luminance(h):
    out = []
    for v in _rgb(h):
        v /= 255
        out.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def contrast(a, b):
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def ink_on(color):
    """Preto ou branco, o que tiver mais contraste sobre `color`."""
    return "#000000" if contrast("#000000", color) >= contrast("#ffffff", color) else "#ffffff"


def round_rect(c, x1, y1, x2, y2, r, **kw):
    if r <= 0:
        return c.create_rectangle(x1, y1, x2, y2, **kw)
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


# --- ícones desenhados pelo app (PNG RGBA gerado em Python: transparência correta em qualquer cor de linha) ---

def _png(width, height, rows):
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def _disc(cx, cy, r):
    return lambda x, y: (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _ring(cx, cy, r, w):
    return lambda x, y: abs(math.hypot(x - cx, y - cy) - r) <= w / 2


def _seg(x1, y1, x2, y2, w):
    dx, dy = x2 - x1, y2 - y1
    ln = dx * dx + dy * dy

    def f(x, y):
        t = 0 if ln == 0 else max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / ln))
        return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)) <= w / 2
    return f


def _rrect(x1, y1, x2, y2, rad):
    def f(x, y):
        if not (x1 <= x <= x2 and y1 <= y <= y2):
            return False
        cx = min(max(x, x1 + rad), x2 - rad)
        cy = min(max(y, y1 + rad), y2 - rad)
        return math.hypot(x - cx, y - cy) <= rad
    return f


def _tri(ax, ay, bx, by, cx, cy):
    def f(x, y):
        d = lambda px, py, qx, qy, rx, ry: (px - rx) * (qy - ry) - (qx - rx) * (py - ry)
        d1, d2, d3 = d(x, y, ax, ay, bx, by), d(x, y, bx, by, cx, cy), d(x, y, cx, cy, ax, ay)
        return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))
    return f


def render_icon(layers, size=16, ss=4):
    """Rasteriza camadas [(predicado em coordenadas 0..16, '#rrggbb')] com suavização; devolve bytes PNG."""
    k = 16 / size
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            acc = [0, 0, 0]
            cov = 0
            for sy in range(ss):
                for sx in range(ss):
                    px, py = (x + (sx + 0.5) / ss) * k, (y + (sy + 0.5) / ss) * k
                    col = None
                    for fn, color in layers:
                        if fn(px, py):
                            col = color
                    if col:
                        r, g, b = _rgb(col)
                        acc[0] += r
                        acc[1] += g
                        acc[2] += b
                        cov += 1
            if cov:
                row += bytes((round(acc[0] / cov), round(acc[1] / cov), round(acc[2] / cov), round(255 * cov / (ss * ss))))
            else:
                row += b"\x00\x00\x00\x00"
        rows.append(bytes(row))
    return _png(size, size, rows)


def icon_layers(name, t, handoff=False):
    """Camadas de cada ícone, nas cores do tema `t`."""
    L = []
    if name == "pending":
        L = [(_ring(8, 8, 5.2, 1.9), t['accent_text'])]
    elif name in ("approved", "ok"):
        ink = ink_on(t['success'])
        L = [(_disc(8, 8, 6.4), t['success']), (_seg(4.8, 8.4, 7.1, 10.7, 1.9), ink), (_seg(7.1, 10.7, 11.4, 5.7, 1.9), ink)]
    elif name == "archived":
        dark = blend(t['muted'], "#000000", 0.55)
        L = [(_rrect(2.2, 3.2, 13.8, 6.4, 1.0), t['muted']), (_rrect(3.2, 5.6, 12.8, 13.4, 1.2), t['muted']), (_seg(6.3, 8.6, 9.7, 8.6, 1.5), dark)]
    elif name == "folder":
        L = [(_rrect(1.8, 3.2, 7.4, 6.4, 1.0), t['accent_text']), (_rrect(1.8, 5.0, 14.2, 13.4, 1.4), t['accent_text'])]
    elif name == "warn":
        ink = ink_on(t['warning'])
        L = [(_tri(8, 2, 14.6, 13.6, 1.4, 13.6), t['warning']), (_seg(8, 6.4, 8, 9.6, 1.7), ink), (_disc(8, 11.7, 1.0), ink)]
    elif name == "error":
        ink = ink_on(t['danger'])
        L = [(_disc(8, 8, 6.4), t['danger']), (_seg(5.4, 5.4, 10.6, 10.6, 1.8), ink), (_seg(10.6, 5.4, 5.4, 10.6, 1.8), ink)]
    elif name == "info":
        ink = ink_on(t['accent'])
        L = [(_disc(8, 8, 6.4), t['accent']), (_disc(8, 5.2, 1.0), ink), (_seg(8, 7.6, 8, 11.4, 1.8), ink)]
    elif name == "sub":
        L = [(_seg(4, 2.5, 4, 11.5, 1.8), t['muted']), (_seg(3.1, 11.5, 11.5, 11.5, 1.8), t['muted']), (_seg(9.2, 8.8, 12.2, 11.5, 1.8), t['muted']),
             (_seg(9.2, 14.2, 12.2, 11.5, 1.8), t['muted'])]
    if handoff:  # selo "retomada" no canto inferior direito
        ink = ink_on(t['accent'])
        L += [(_disc(11.6, 11.6, 4.0), t['accent']), (_seg(9.6, 11.6, 13.4, 11.6, 1.4), ink), (_seg(11.9, 9.7, 13.6, 11.6, 1.4), ink), (_seg(11.9, 13.5, 13.6, 11.6, 1.4), ink)]
    return L



class Tooltip:
    def __init__(self, widget, app, text_fn, delay=450):
        self.w, self.app, self.fn, self.delay = widget, app, text_fn, delay
        self.tip = self.job = None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")
        widget.bind("<ButtonPress>", self._leave, add="+")

    def _enter(self, _e):
        self._leave()
        self.job = self.w.after(self.delay, self._show)

    def _leave(self, _e=None):
        if self.job:
            self.w.after_cancel(self.job)
            self.job = None
        if self.tip:
            self.tip.destroy()
            self.tip = None

    def _show(self):
        text = self.fn()
        if not text:
            return
        t = self.app.t
        self.tip = tk.Toplevel(self.w)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{self.w.winfo_rootx()}+{self.w.winfo_rooty() + self.w.winfo_height() + 6}")
        tk.Label(self.tip, text=text, bg=t['panel2'], fg=t['fg'], font=self.app.f_small, padx=9, pady=5, justify=tk.LEFT,
                 highlightthickness=1, highlightbackground=t['border'], wraplength=320).pack()


class IconButton(tk.Canvas):
    """Botão desenhado em Canvas: ícone + texto, cantos do tema, estados (normal, hover, pressionado, foco,
    desabilitado, ocupado com spinner, selo de contagem, confirmação) e modo compacto só com o ícone."""

    def __init__(self, master, app, icon, text, command, kind="normal", tip="", bg_token="bg", icon_token="btn_fg", stretch=False, icon_only=False):
        super().__init__(master, highlightthickness=0, bd=0, takefocus=1, cursor="hand2")
        self.icon_only = icon_only  # sempre compacto: o texto aparece só sem ícones (Tema > Sem ícones)
        self.stretch = stretch  # ocupa a largura que o gerenciador de layout der (grid com sticky), conteúdo centralizado
        self.app, self.icon, self.text, self.command = app, icon, text, command
        self.kind, self.tip, self.bg_token, self.icon_token = kind, tip, bg_token, icon_token
        self.enabled, self.reason, self.busy, self.compact = True, "", False, icon_only
        self.hover = self.pressed = self.focused = self.ok_flash = False
        self.badge, self._spin, self._spin_job = 0, 0, None
        self.bind("<Enter>", lambda e: self._set(hover=True))
        self.bind("<Leave>", lambda e: self._set(hover=False, pressed=False))
        self.bind("<ButtonPress-1>", lambda e: self._set(pressed=True) if self.enabled else None)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<FocusIn>", lambda e: self._set(focused=True))
        self.bind("<FocusOut>", lambda e: self._set(focused=False))
        self.bind("<space>", lambda e: self.invoke())
        self.bind("<Return>", lambda e: self.invoke())
        Tooltip(self, app, self.tooltip_text)
        if stretch:
            self.bind("<Configure>", lambda e: self.redraw(), add="+")
        self.relayout()

    # --- API ---
    def tooltip_text(self):
        if not self.enabled and self.reason:
            return self.reason
        return self.tip

    def invoke(self):
        if self.enabled and not self.busy and self.command:
            self.command()

    def set_enabled(self, flag, reason=""):
        if (flag, reason) != (self.enabled, self.reason):
            self.enabled, self.reason = flag, reason
            self.configure(cursor="hand2" if flag else "arrow")
            self.redraw()

    def set_busy(self, flag, text=None):
        self.busy = flag
        if text is not None:
            self.text = text
        if flag and not self._spin_job:
            self._tick()
        self.relayout()

    def set_text(self, text):
        self.text = text
        self.relayout()

    def badge_text(self):
        return str(self.badge) if self.badge < 100 else "99+"

    def badge_width(self):
        return max(self.app.px(18), self.app.f_small.measure(self.badge_text()) + self.app.px(10))

    def set_badge(self, n):
        if n != self.badge:
            self.badge = n
            self.relayout()

    def set_compact(self, flag):
        flag = flag or self.icon_only
        if flag != self.compact:
            self.compact = flag
            self.relayout()

    def flash_ok(self):
        self.ok_flash = True
        self.redraw()
        self.after(900, lambda: (setattr(self, "ok_flash", False), self.redraw()))

    # --- desenho ---
    def glyph(self):
        mode = self.app.icon_mode
        if self.icon not in ICONS or mode == "none":
            return ""
        return ICONS[self.icon][0 if mode == "mdl2" else 1]

    def measure(self, compact=None):
        compact = self.compact if compact is None else compact
        pad, gap = self.app.px(12), self.app.px(8)
        g = self.glyph()
        w = pad * 2
        if g:
            w += self.app.f_icon.measure(g)
        if self.text and (not compact or not g):
            w += (gap if g else 0) + self.app.f_btn.measure(self.text)
            if self.badge:
                w += gap + self.badge_width()
        elif self.badge:
            w += self.app.px(10)  # espaço para o selo no canto do botão compacto
        return w

    def relayout(self):
        self.configure(width=self.measure(), height=self.app.px(34))
        self.redraw()

    def _set(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self.redraw()

    def _release(self, _e):
        was = self.pressed
        self._set(pressed=False)
        if was and self.hover:
            self.invoke()

    def _tick(self):
        if not self.busy:
            self._spin_job = None
            self.redraw()
            return
        self._spin = (self._spin + 30) % 360
        self.redraw()
        self._spin_job = self.after(70, self._tick)

    def colors(self):
        t = self.app.t
        if self.kind == "primary":
            base, hov, prs, fg = t['accent'], blend(t['accent'], "#ffffff", 0.18), blend(t['accent'], "#000000", 0.2), t['accent_fg']
            border = base
        else:
            base, hov, prs, fg = t['panel2'], blend(t['panel2'], t['fg'], 0.12), blend(t['panel2'], t['fg'], 0.22), t['fg']
            border = t['border']
        if not self.enabled or self.busy:
            return blend(t[self.bg_token], base, 0.45), blend(t[self.bg_token], border, 0.5), blend(t[self.bg_token], t['muted'], 0.55) if not self.busy else fg
        bg = prs if self.pressed else (hov if self.hover else base)
        return bg, (t['accent'] if self.focused else border), fg

    def redraw(self):
        t = self.app.t
        self.configure(bg=t[self.bg_token])
        self.delete("all")
        w, h = int(self["width"]), int(self["height"])
        if self.stretch and self.winfo_width() > 1:
            w = self.winfo_width()
        bg, border, fg = self.colors()
        r = self.app.px(t['radius'])
        round_rect(self, 1, 1, w - 1, h - 1, r, fill=bg, outline=border, width=2 if self.focused and self.enabled else 1)
        g = self.glyph()
        off = 1 if self.pressed and self.enabled else 0
        icon_fg = fg if (self.kind == "primary" or not self.enabled or self.busy) else t.get(self.icon_token, fg)
        pad, gap = self.app.px(12), self.app.px(8)
        x = pad + (max(0, (w - self.measure()) // 2) if self.stretch else 0)
        cy = h // 2 + off
        if self.busy:
            iw = max(self.app.f_icon.measure(g or "●"), self.app.px(16))
            self.create_arc(x + 1, cy - iw // 2 + 1, x + iw - 1, cy + iw // 2 - 1, start=self._spin, extent=250, style=tk.ARC, outline=t['accent'] if self.kind != "primary" else fg, width=2)
            x += iw
        elif g or self.ok_flash:
            shown = ICONS["approve"][0 if self.app.icon_mode == "mdl2" else 1] if self.ok_flash else g
            self.create_text(x, cy, text=shown, font=self.app.f_icon, fill=t['success'] if self.ok_flash else icon_fg, anchor="w")
            x += self.app.f_icon.measure(shown)
        if self.text and (not self.compact or not g):
            x += gap if (g or self.busy) else 0
            self.create_text(x, cy, text=self.text, font=self.app.f_btn, fill=fg, anchor="w")
        if self.badge:
            bw, bh = self.badge_width(), self.app.px(18)
            if self.text and (not self.compact or not g):   # selo ao lado do texto
                x += self.app.f_btn.measure(self.text) + gap
                bx1, by1 = x, cy - bh // 2
            else:                                            # modo compacto: selo no canto superior direito
                bx1, by1 = w - bw - 1, 1
            pill, ink = (t['accent_fg'], t['accent']) if self.kind == "primary" else (t['warning'], ink_on(t['warning']))
            round_rect(self, bx1, by1, bx1 + bw, by1 + bh, bh // 2, fill=pill, outline="")
            self.create_text(bx1 + bw / 2, by1 + bh / 2, text=self.badge_text(), font=self.app.f_small, fill=ink)


class Chip(tk.Label):
    """Selo colorido de contagem na barra de status. Clicar (ou Enter/Espaço com foco) filtra a tabela; de novo, mostra tudo."""

    def __init__(self, master, app, token, key=None):
        super().__init__(master, font=app.f_small, padx=8, pady=2, highlightthickness=1, takefocus=1 if key else 0,
                         cursor="hand2" if key else "")
        self.app, self.token, self.key = app, token, key
        if key:
            for seq in ("<Button-1>", "<Return>", "<space>"):
                self.bind(seq, lambda e: app.toggle_chip_filter(key))
            self.bind("<FocusIn>", lambda e: self.repaint(), add="+")
            self.bind("<FocusOut>", lambda e: self.repaint(), add="+")
            Tooltip(self, app, lambda: "Mostrar todas as sessões" if app.chip_filter == key else "Mostrar só estas sessões")
        self.repaint()

    def repaint(self):
        t = self.app.t
        on = self.key is not None and getattr(self.app, "chip_filter", None) == self.key
        focused = self.key is not None and self.focus_displayof() is self
        self.configure(bg=blend(t['panel'], t[self.token], 0.22) if on else t['panel'], fg=t[self.token],
                       highlightbackground=t[self.token] if (on or focused) else blend(t['panel2'], t[self.token], 0.4))


class Toast(tk.Frame):
    """Notificação discreta no canto da janela: ícone, texto, botões de ação e fechar. Some sozinha."""

    TOKENS = {"ok": "success", "info": "accent", "warn": "warning", "error": "danger"}

    def __init__(self, app, kind, text, actions=(), ttl=6000):
        t = app.t
        super().__init__(app, bg=t['panel2'], highlightthickness=2, highlightbackground=t[self.TOKENS[kind]], padx=app.px(10), pady=app.px(8))
        self.app, self.kind = app, kind
        img = app.icon({"ok": "ok", "info": "info", "warn": "warn", "error": "error"}[kind])
        self.icon_lbl = tk.Label(self, image=img, bg=t['panel2'])
        self.icon_lbl.image = img  # referência: o cache de ícones pode ser trocado
        self.icon_lbl.pack(side=tk.LEFT, anchor="n", padx=(0, app.px(8)))
        tk.Label(self, text=text, bg=t['panel2'], fg=t['fg'], font=app.f_ui, justify=tk.LEFT, anchor="w", wraplength=app.px(330)).pack(side=tk.LEFT, anchor="w")
        self.buttons = []
        for label, fn in actions:
            b = IconButton(self, app, "", label, lambda f=fn: (self.dismiss(), f()), bg_token="panel2")
            b.pack(side=tk.LEFT, padx=(app.px(10), 0))
            self.buttons.append(b)
        close = IconButton(self, app, "clear", "", self.dismiss, bg_token="panel2", tip="Fechar")
        close.pack(side=tk.LEFT, padx=(app.px(8), 0))
        self.job = self.after(ttl, self.dismiss)

    def dismiss(self):
        if self.job:
            try:
                self.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None
        if self in self.app.toasts:
            self.app.toasts.remove(self)
        self.destroy()
        self.app.layout_toasts()


class ThemePicker(tk.Toplevel):
    """Lista suspensa no visual do app: temas com amostra de cores e estilo de ícones. Setas, Enter e Esc funcionam; clicar fora fecha."""

    ICON_MODES = (("mdl2", "Ícones do Windows (Segoe MDL2)"), ("symbol", "Símbolos Unicode"), ("none", "Sem ícones"))

    def __init__(self, app, anchor):
        super().__init__(app)
        self.app, self.anchor = app, anchor
        t = self.t = app.t
        self.overrideredirect(True)
        self.configure(bg=t['border'], padx=1, pady=1)
        body = tk.Frame(self, bg=t['panel'], padx=app.px(4), pady=app.px(4))
        body.pack()
        self.rows = []  # [frame, [labels], comando]
        self.cur = -1
        self.heading(body, "Tema")
        for key in THEME_ORDER:
            self.add_row(body, THEMES[key]['name'], key == app.theme_key, lambda k=key: app.set_theme(k), swatch=THEMES[key])
        tk.Frame(body, bg=t['border'], height=1).pack(fill=tk.X, pady=app.px(5), padx=app.px(4))
        self.heading(body, "Ícones")
        for mode, label in self.ICON_MODES:
            self.add_row(body, label, mode == app.icon_mode, lambda m=mode: app.set_icon_mode(m), radio=True)
        self.cur = next((i for i, r in enumerate(self.rows) if r[3]), 0)
        self.highlight(self.cur)
        self.update_idletasks()
        w, h = max(self.winfo_reqwidth(), anchor.winfo_width()), self.winfo_reqheight()
        ax, ay, aw, ah = anchor.winfo_rootx(), anchor.winfo_rooty(), anchor.winfo_width(), anchor.winfo_height()
        x, y = dropdown_pos(work_area_at(self, ax + aw // 2, ay + ah // 2), ax, ay, aw, ah, w, h, gap=app.px(2))
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.bind("<Escape>", lambda e: self.close())
        self.bind("<Up>", lambda e: self.move(-1))
        self.bind("<Down>", lambda e: self.move(1))
        self.bind("<Return>", lambda e: self.choose(self.cur))
        self.bind("<Button-1>", self.click_outside)
        self.focus_force()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def heading(self, body, text):
        tk.Label(body, text=text.upper(), bg=self.t['panel'], fg=self.t['muted'], font=self.app.f_small, anchor="w").pack(fill=tk.X, padx=self.app.px(8), pady=(self.app.px(2), self.app.px(2)))

    def add_row(self, body, text, selected, command, swatch=None, radio=False):
        app, t = self.app, self.t
        row = tk.Frame(body, bg=t['panel'], padx=app.px(8), pady=app.px(5), cursor="hand2")
        row.pack(fill=tk.X)
        widgets = []
        if swatch:
            sw = tk.Canvas(row, width=app.px(52), height=app.px(14), bg=t['panel'], highlightthickness=0)
            for i, tok in enumerate(("bg", "panel2", "accent", "fg")):
                sw.create_rectangle(i * app.px(13), 0, (i + 1) * app.px(13), app.px(14), fill=swatch[tok], outline=blend(swatch['border'], swatch['bg'], 0.5))
            sw.pack(side=tk.LEFT, padx=(0, app.px(10)))
            widgets.append(sw)
        else:
            mark = tk.Label(row, text="●" if selected else "○", bg=t['panel'], fg=t['accent_text'], font=app.f_ui, width=3)
            mark.pack(side=tk.LEFT, padx=(0, app.px(7)))
            widgets.append(mark)
        name = tk.Label(row, text=text, bg=t['panel'], fg=t['fg'], font=app.f_bold if selected else app.f_ui, anchor="w")
        name.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tick = tk.Label(row, text="✓" if selected and swatch else "", bg=t['panel'], fg=t['accent_text'], font=app.f_bold, width=2)
        tick.pack(side=tk.RIGHT, padx=(app.px(12), 0))
        widgets += [name, tick]
        idx = len(self.rows)
        self.rows.append([row, widgets, command, selected])
        for w in [row] + widgets:
            w.bind("<Enter>", lambda e, i=idx: self.highlight(i))
            w.bind("<ButtonRelease-1>", lambda e, i=idx: self.choose(i))

    def highlight(self, i):
        t = self.t
        self.cur = i
        for n, (row, widgets, _cmd, _sel) in enumerate(self.rows):
            on = n == i
            bg = t['sel_bg'] if on else t['panel']
            row.configure(bg=bg)
            for w in widgets:
                w.configure(bg=bg)
                if isinstance(w, tk.Label):
                    w.configure(fg=t['sel_fg'] if on else (t['fg'] if w is widgets[1] else t['accent_text']))

    def move(self, step):
        self.highlight((self.cur + step) % len(self.rows))

    def choose(self, i):
        command = self.rows[i][2]
        self.close()
        command()

    def click_outside(self, e):
        x0, y0 = self.winfo_rootx(), self.winfo_rooty()
        if not (x0 <= e.x_root < x0 + self.winfo_width() and y0 <= e.y_root < y0 + self.winfo_height()):
            self.close()

    def close(self):
        if self.app.theme_picker is self:
            self.app.theme_picker = None
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


class AboutDialog(tk.Toplevel):
    """Sobre: versão, autor, links e diagnóstico do ambiente, com botão para copiar tudo."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        t = app.t
        self.title("Sobre o AntigravityGate")
        self.configure(bg=t['panel'], padx=app.px(20), pady=app.px(16))
        self.transient(app)
        self.resizable(False, False)
        self.f_link = tkfont.Font(self, font=app.f_ui)
        self.f_link.configure(underline=True)

        def lab(parent, text, font=None, fg='fg', **kw):
            return tk.Label(parent, text=text, bg=t['panel'], fg=t[fg], font=font or app.f_ui, justify=tk.LEFT, anchor="w", **kw)

        head = tk.Frame(self, bg=t['panel'])
        head.pack(anchor="w", fill=tk.X)
        lab(head, "◆", app.f_title, 'accent_text').pack(side=tk.LEFT)
        lab(head, "AntigravityGate", app.f_title).pack(side=tk.LEFT, padx=(app.px(8), app.px(10)))
        lab(head, f"versão {__version__} · {__build__}", app.f_small, 'muted').pack(side=tk.LEFT, anchor="s", pady=(0, app.px(3)))
        lab(self, "Gestão de contexto e curadoria de sessões do Antigravity.").pack(anchor="w", pady=(app.px(4), app.px(12)))

        grid = tk.Frame(self, bg=t['panel'])
        grid.pack(anchor="w", fill=tk.X)
        rows = (("Autor", APP_AUTHOR, None), ("E-mail", APP_EMAIL, "mailto:" + APP_EMAIL),
                ("GitHub", APP_GITHUB.replace("https://", ""), APP_GITHUB), ("Projeto", APP_REPO.replace("https://", ""), APP_REPO))
        for r, (label, text, url) in enumerate(rows):
            lab(grid, label, app.f_small, 'muted').grid(row=r, column=0, sticky="w", padx=(0, app.px(14)), pady=1)
            v = lab(grid, text, self.f_link if url else app.f_ui, 'accent_text' if url else 'fg')
            v.grid(row=r, column=1, sticky="w", pady=1)
            if url:
                v.configure(cursor="hand2", takefocus=1, highlightthickness=1, highlightbackground=t['panel'], highlightcolor=t['accent'])
                v.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
                v.bind("<Return>", lambda e, u=url: webbrowser.open(u))
                Tooltip(v, app, lambda u=url: f"Abrir {u}")
        lab(self, f"© 2026 {APP_AUTHOR}. Ferramenta independente, sem vínculo com o Google ou com o Antigravity.",
            app.f_small, 'muted', wraplength=app.px(520)).pack(anchor="w", pady=(app.px(10), app.px(12)))

        box = tk.Frame(self, bg=t['panel2'], padx=app.px(12), pady=app.px(10), highlightthickness=1, highlightbackground=t['border'])
        box.pack(fill=tk.X)
        tk.Label(box, text="Diagnóstico", bg=t['panel2'], fg=t['fg'], font=app.f_bold, anchor="w").pack(anchor="w")
        tk.Label(box, text="\n".join(about_info().splitlines()[1:]), bg=t['panel2'], fg=t['fg'], font=app.f_small, justify=tk.LEFT,
                 anchor="w", wraplength=app.px(520)).pack(anchor="w", pady=(app.px(4), 0))

        buttons = tk.Frame(self, bg=t['panel'])
        buttons.pack(anchor="e", pady=(app.px(14), 0))
        IconButton(buttons, app, "copy", "Copiar informações", self.copy_info, bg_token="panel",
                   tip="Copiar versão e ambiente para colar num relato de problema").pack(side=tk.LEFT, padx=(0, app.px(8)))
        IconButton(buttons, app, "folder", "Pasta de dados", lambda: app.open_path(LOG_DIR), bg_token="panel",
                   tip=f"Abrir {LOG_DIR}").pack(side=tk.LEFT, padx=(0, app.px(8)))
        IconButton(buttons, app, "", "Fechar", self.close, kind="primary", bg_token="panel").pack(side=tk.LEFT)
        self.bind("<Escape>", lambda e: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)
        place_over(self, app)
        self.focus_set()

    def copy_info(self):
        self.app.clipboard_clear()
        self.app.clipboard_append(about_info())
        self.app.notify("ok", "Informações do app copiadas.")

    def close(self):
        if self.app.about_win is self:
            self.app.about_win = None
        self.destroy()


class LimitDialog(tk.Toplevel):
    """Escolha dos níveis de alerta de contexto: três faixas prontas ou valores personalizados, com prévia sobre as sessões carregadas."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        t = app.t
        self.title("Limites de contexto")
        self.configure(bg=t['panel'], padx=app.px(18), pady=app.px(14))
        self.transient(app)
        self.resizable(False, False)
        self.var = tk.StringVar(value=app.limit_preset)
        self.att_var = tk.StringVar(value=str(app.limits_custom[0]))
        self.crit_var = tk.StringVar(value=str(app.limits_custom[1]))

        def lab(text, font=None, fg=None, **kw):
            return tk.Label(self, text=text, bg=t['panel'], fg=fg or t['fg'], font=font or app.f_ui, justify=tk.LEFT, anchor="w", **kw)

        lab("Quando avisar que o contexto da conversa está grande?", app.f_bold).pack(anchor="w")
        lab("O contexto é o tamanho do histórico que o modelo relê a cada resposta. Quanto maior, mais caro e mais sujeito a perder detalhes. "
            "Atenção sugere preparar a retomada; crítico, retomar já em sessão nova.", app.f_small, t['muted'], wraplength=app.px(560)).pack(anchor="w", pady=(2, 10))

        def radio(value, text):
            return tk.Radiobutton(self, text=text, variable=self.var, value=value, command=self.refresh, bg=t['panel'], fg=t['fg'], selectcolor=t['panel2'],
                                  activebackground=t['panel'], activeforeground=t['fg'], font=app.f_bold, anchor="w", highlightthickness=0)

        for key, (name, att, crit, desc) in CONTEXT_PRESETS.items():
            tag = "  (recomendado)" if key == DEFAULT_PRESET else ""
            radio(key, f"{name}{tag}  —  atenção {fmt_tokens(att)} · crítico {fmt_tokens(crit)}").pack(anchor="w")
            lab(desc, app.f_small, t['muted'], wraplength=app.px(540)).pack(anchor="w", padx=(app.px(26), 0), pady=(0, 6))
        radio(CONTEXT_CUSTOM, "Personalizado").pack(anchor="w")
        row = tk.Frame(self, bg=t['panel'])
        row.pack(anchor="w", padx=(app.px(26), 0), pady=(2, 4))
        mk = lambda var: tk.Entry(row, textvariable=var, width=11, bg=t['panel2'], fg=t['fg'], insertbackground=t['fg'], relief=tk.FLAT, font=app.f_ui,
                                  highlightthickness=1, highlightbackground=t['border'], highlightcolor=t['accent'])
        tk.Label(row, text="Atenção", bg=t['panel'], fg=t['fg'], font=app.f_ui).pack(side=tk.LEFT)
        self.att_entry = mk(self.att_var)
        self.att_entry.pack(side=tk.LEFT, padx=(6, 16), ipady=3)
        tk.Label(row, text="Crítico", bg=t['panel'], fg=t['fg'], font=app.f_ui).pack(side=tk.LEFT)
        self.crit_entry = mk(self.crit_var)
        self.crit_entry.pack(side=tk.LEFT, padx=(6, 0), ipady=3)
        for var in (self.att_var, self.crit_var):
            var.trace_add("write", lambda *_: (self.var.set(CONTEXT_CUSTOM), self.refresh()))
        lab(f"Aceita 120000, 120.000 ou 120k. Entre {fmt_tokens(LIMIT_MIN)} e {fmt_tokens(LIMIT_MAX)}; o crítico precisa ser maior que a atenção.",
            app.f_small, t['muted'], wraplength=app.px(540)).pack(anchor="w", padx=(app.px(26), 0))
        self.preview = lab("", app.f_ui)
        self.preview.pack(anchor="w", pady=(12, 0))
        self.error = lab("", app.f_small, t['danger'], wraplength=app.px(560))
        self.error.pack(anchor="w")
        buttons = tk.Frame(self, bg=t['panel'])
        buttons.pack(anchor="e", pady=(12, 0))
        IconButton(buttons, app, "", "Cancelar", self.destroy, bg_token="panel").pack(side=tk.LEFT, padx=(0, 8))
        self.ok_btn = IconButton(buttons, app, "approve", "Aplicar", self.apply, kind="primary", bg_token="panel")
        self.ok_btn.pack(side=tk.LEFT)
        self.refresh()
        place_over(self, app)

    def values(self):
        """(preset, atenção, crítico, erro)"""
        key = self.var.get()
        if key in CONTEXT_PRESETS:
            return key, CONTEXT_PRESETS[key][1], CONTEXT_PRESETS[key][2], ""
        att, crit, err = validate_limits(self.att_var.get(), self.crit_var.get())
        return CONTEXT_CUSTOM, att, crit, err

    def refresh(self):
        key, att, crit, err = self.values()
        self.error.configure(text=err)
        self.ok_btn.set_enabled(not err, err)
        if err:
            self.preview.configure(text="")
            return
        rows = list(self.app.row_by_cid.values())
        lv = [ctx_level(r['ctx'], att, crit) for r in rows]
        self.preview.configure(text=f"Com estes valores, nas {len(rows)} sessões carregadas: {lv.count(1)} em atenção · {lv.count(2)} críticas.")

    def apply(self):
        key, att, crit, err = self.values()
        if err:
            return
        self.app.set_limits(key, att, crit)
        self.destroy()


class AntigravityGateApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AntigravityGate")
        self._win_job = None

        self.themed, self.icon_buttons, self.btn, self.chips = [], [], {}, {}
        self.icon_cache = {}
        self.toasts, self.toast_log = [], []
        self.theme_picker = None
        self.about_win = None
        self.queue = queue.Queue()
        self.gen = 0
        self.loading = False
        self.exporting = False
        self.autorunning, self.runner, self.auto_win = False, None, None
        self.auto_thread = self.export_thread = None
        self.export_cancel = False
        self.handoffs = {}
        self.warnings = 0
        self.base_status = ""
        self.proj_map, self.summaries, self.db_files = {}, {}, {}
        self.state = StateStore(STATE_DB)
        self.states = {}
        self.grouped, self.total, self.sub_count, self.row_by_cid = {}, 0, {}, {}
        self.match, self.sort_col, self.sort_rev = None, "col_date", True
        self.chip_filter = None
        self.search_note = ""

        self.settings = load_settings()
        w, h, x, y = window_geometry(lambda px, py: work_area_at(self, px, py), self.winfo_fpixels('1i') / 96, self.settings.get("window"))
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(min(WIN_MIN[0], w), min(WIN_MIN[1], h))
        self.start_zoomed = saved_zoomed(self.settings.get("window"))
        if self.start_zoomed:
            self.after_idle(self.zoom)
        self.limit_preset, att, crit = limits_from_settings(self.settings)
        set_context_limits(att, crit)
        c = self.settings.get("context") if isinstance(self.settings.get("context"), dict) else {}
        self.limits_custom = (c.get("attention") or att, c.get("critical") or crit)
        self.banner_dismissed = None
        self.families = set(tkfont.families(self))
        self.base_family = next((f for f in ("Segoe UI", "Helvetica", "DejaVu Sans") if f in self.families),
                                tkfont.nametofont("TkDefaultFont").actual("family"))
        self.theme_key = self.settings.get("theme") if self.settings.get("theme") in THEMES else "escuro"
        wanted = (os.environ.get("AGY_ICONS") or self.settings.get("icons") or "auto").lower()
        self.icon_mode = wanted if wanted in ("mdl2", "symbol", "none") else ("mdl2" if "Segoe MDL2 Assets" in self.families else "symbol")
        self.f_ui = tkfont.Font(self, family=self.base_family, size=10)
        self.f_bold = tkfont.Font(self, family=self.base_family, size=10, weight="bold")
        self.f_small = tkfont.Font(self, family=self.base_family, size=9)
        self.f_btn = tkfont.Font(self, family=self.base_family, size=9, weight="bold")
        self.f_title = tkfont.Font(self, family=self.base_family, size=15, weight="bold")
        self.f_icon = tkfont.Font(self, family=self.base_family, size=11)
        self.update_icon_font()
        self.apply_theme()

        self.sources = discover_sources()
        self.source_idx = 0
        self.create_widgets()
        self.apply_theme()
        self.bind("<Configure>", self.on_resize)
        self.bind("<Configure>", self.schedule_save_window, add="+")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.poll()
        self.load_data()

    # --- tema e ícones ---

    def px(self, n):
        """Tamanho em pixels escalado pelo DPI da tela (96 dpi = 1:1)."""
        return max(1, round(n * self.winfo_fpixels('1i') / 96))

    def update_icon_font(self):
        if self.icon_mode == "mdl2" and "Segoe MDL2 Assets" in self.families:
            self.f_icon.configure(family="Segoe MDL2 Assets", size=11)
        else:
            sym = next((f for f in ("Segoe UI Symbol", "DejaVu Sans", self.base_family) if f in self.families), self.base_family)
            self.f_icon.configure(family=sym, size=11)

    @property
    def bg_color(self):
        return self.t['bg']

    def apply_theme(self):
        old_icons = self.icon_cache  # mantém as imagens antigas vivas até todos os widgets receberem as novas
        self.icon_cache = {}
        t = self.t = dict(THEMES[self.theme_key])
        t['header_sub'] = blend(t['header_fg'], t['header_bg'], 0.12)
        t['btn_fg'] = t['fg']
        t['banner_bg'] = blend(t['panel'], t['danger'], 0.16)
        self.configure(bg=t['bg'])
        self.f_title.configure(family=next((f for f in t['title_fonts'] if f in self.families), self.base_family))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background=t['panel'], fieldbackground=t['panel'], foreground=t['fg'], rowheight=self.px(30),
                        borderwidth=1, bordercolor=t['border'], lightcolor=t['panel'], darkcolor=t['panel'], font=self.f_ui)
        style.configure("Treeview.Heading", background=t['panel2'], foreground=t['fg'], relief="flat", font=self.f_bold,
                        padding=(self.px(8), self.px(6)))
        style.map("Treeview.Heading", background=[('active', blend(t['panel2'], t['fg'], 0.12))])
        style.map("Treeview", background=[('selected', t['sel_bg'])], foreground=[('selected', t['sel_fg'])])
        style.configure("TCombobox", fieldbackground=t['panel'], background=t['panel2'], foreground=t['fg'], arrowcolor=t['fg'],
                        bordercolor=t['border'], lightcolor=t['border'], darkcolor=t['border'], padding=self.px(5))
        style.map("TCombobox", fieldbackground=[("readonly", t['panel'])], foreground=[("readonly", t['fg'])],
                  selectbackground=[("readonly", t['panel'])], selectforeground=[("readonly", t['fg'])])
        self.option_add("*TCombobox*Listbox.background", t['panel'])
        self.option_add("*TCombobox*Listbox.foreground", t['fg'])
        self.option_add("*TCombobox*Listbox.selectBackground", t['sel_bg'])
        self.option_add("*TCombobox*Listbox.selectForeground", t['sel_fg'])
        thumb = blend(t['panel2'], t['fg'], 0.18)
        for orient in ("Vertical", "Horizontal"):
            style.configure(f"{orient}.TScrollbar", background=thumb, troughcolor=t['bg'], arrowcolor=t['fg'],
                            bordercolor=t['bg'], lightcolor=thumb, darkcolor=thumb)
            style.map(f"{orient}.TScrollbar", background=[('active', blend(t['panel2'], t['fg'], 0.35))])

        if hasattr(self, 'tree'):
            self.tree.tag_configure('proj', foreground=t['accent_text'], font=self.f_bold)
            self.tree.tag_configure('st_aprovada', foreground=t['success'])
            self.tree.tag_configure('st_arquivada', foreground=t['muted'])
            self.tree.tag_configure('rot', foreground=t['warning'])
            self.tree.tag_configure('crit', foreground=t['danger'])
        # Widgets tk (não-ttk): reaplica as cores sem recarregar dados.
        for widget, opts in self.themed:
            widget.configure(**{opt: t[tok] for opt, tok in opts.items()})
        for b in self.icon_buttons:
            b.redraw()
        for c in self.chips.values():
            c.repaint()
        if hasattr(self, 'tree'):
            self.restyle_rows()
            if hasattr(self, 'd_icon'):
                self.update_details()
        del old_icons
        if os.name == "nt":
            self.after_idle(lambda: style_titlebar(self, self.t))

    def icon(self, name, handoff=False):
        """Imagem do ícone `name` no tema atual (em cache; gerada pelo próprio app)."""
        size = self.px(16)
        key = (name, handoff, self.theme_key, size)
        img = self.icon_cache.get(key)
        if img is None:
            png = render_icon(icon_layers(name, self.t, handoff), size)
            img = self.icon_cache[key] = tk.PhotoImage(master=self, data=base64.b64encode(png))
        return img

    def status_icon(self, cid):
        name = {"pendente": "pending", "aprovada": "approved", "arquivada": "archived"}[self.states.get(cid, "pendente")]
        return self.icon(name, handoff=bool(self.handoffs.get(cid)))

    def restyle_rows(self):
        """Reaplica as imagens das linhas (troca de tema, de estado ou de retomada)."""
        for proj in self.tree.get_children():
            self.tree.item(proj, image=self.icon("folder"))
        for iid in self.iter_sessions():
            self.tree.item(iid, image=self.status_icon(self.cid_of(iid)))

    def themed_widget(self, widget, **opts):
        """Registra um widget tk para ser recolorido por apply_theme. opts: opção -> nome do token da paleta."""
        self.themed.append((widget, opts))
        widget.configure(**{opt: self.t[tok] for opt, tok in opts.items()})
        return widget

    def set_theme(self, key):
        self.dismiss_toasts()
        self.theme_key = key
        self.settings['theme'] = key
        save_settings(self.settings)
        self.apply_theme()
        if 'theme' in self.btn:
            b = self.btn['theme']
            b.text = self.theme_button_text()
            b.relayout()
            self.on_resize()

    def toggle_theme(self):
        """Passa para o próximo tema da lista."""
        self.set_theme(THEME_ORDER[(THEME_ORDER.index(self.theme_key) + 1) % len(THEME_ORDER)])

    def set_icon_mode(self, mode):
        self.icon_mode = mode
        self.settings['icons'] = mode
        save_settings(self.settings)
        self.update_icon_font()
        for b in self.icon_buttons:
            b.relayout()
        self.on_resize()

    # --- notificações ---

    def notify(self, kind, text, actions=(), ttl=None):
        """Mostra uma notificação não bloqueante. `actions`: [(rótulo, função)]. Também registra em toast_log."""
        self.toast_log.append((kind, text, [a[0] for a in actions]))
        ttl = ttl or (10000 if kind in ("warn", "error") else (9000 if actions else 6000))
        while len(self.toasts) >= 4:
            self.toasts[0].dismiss()
        toast = Toast(self, kind, text, actions, ttl)
        self.toasts.append(toast)
        self.layout_toasts()
        return toast

    def layout_toasts(self):
        self.update_idletasks()
        y = self.px(14) + (self.footer.winfo_height() if hasattr(self, "footer") else 0)
        for toast in reversed(self.toasts):
            toast.place(in_=self, relx=1.0, rely=1.0, x=-self.px(18), y=-y, anchor="se")
            toast.lift()
            y += toast.winfo_reqheight() + self.px(8)

    def dismiss_toasts(self):
        for toast in list(self.toasts):
            toast.dismiss()

    def open_path(self, path):
        """Abre um arquivo ou pasta no programa padrão do sistema."""
        opener = getattr(os, "startfile", None)
        if opener is None:
            self.notify("info", f"Caminho: {path}")
            return False
        try:
            opener(path)
            return True
        except OSError as e:
            log.warning("Não abriu %s: %s", path, e)
            self.notify("warn", f"Não foi possível abrir automaticamente: {e}")
            return False

    def open_limits(self):
        dlg = LimitDialog(self)
        dlg.grab_set()
        dlg.wait_window()

    def set_limits(self, preset, attention, critical):
        """Aplica e salva os níveis de alerta. Repinta a tabela, os selos e o aviso sem reler o disco."""
        self.limit_preset = preset
        set_context_limits(attention, critical)
        if preset == CONTEXT_CUSTOM:
            self.limits_custom = (attention, critical)
        self.settings['context'] = {'preset': preset, 'attention': attention, 'critical': critical}
        save_settings(self.settings)
        self.banner_dismissed = None
        self.btn["limits"].tip = self.limits_tip()
        if self.grouped:
            self.populate()
        self.notify("info", f"Limites de contexto aplicados: atenção {fmt_tokens(attention)}, crítico {fmt_tokens(critical)}.")

    def limits_tip(self):
        name = CONTEXT_PRESETS[self.limit_preset][0] if self.limit_preset in CONTEXT_PRESETS else "Personalizado"
        return (f"Níveis de alerta de contexto: {name} — atenção {fmt_tokens(CONTEXT_LIMITS['attention'])}, "
                f"crítico {fmt_tokens(CONTEXT_LIMITS['critical'])}. Clique para mudar.")

    def critical_rows(self):
        shown = [self.row_by_cid[self.cid_of(i)] for i in self.iter_sessions() if self.cid_of(i) in self.row_by_cid]
        return [r for r in shown if ctx_level(r['ctx']) == 2 and self.states.get(r['cid']) != "arquivada"]

    def update_empty(self):
        """Mensagem no centro da tabela quando não há linhas: carregando, busca sem resultado ou fonte vazia."""
        if self.tree.get_children():
            self.empty.place_forget()
            return
        b = self.btn["empty_action"]
        if self.loading:
            icon, title, sub, action = "info", "Lendo as sessões…", "Na primeira leitura isso pode levar alguns segundos.", None
        elif self.match is not None:
            q = self.search_var.get().strip()
            icon, title = "warn", "Nenhuma sessão encontrada"
            sub = f"Nada para “{q}”. Tente outros termos ou limpe a busca." if q else "Nenhuma sessão atende ao filtro."
            action = ("clear", "Limpar busca", self.clear_search)
        else:
            icon, title = "info", "Nenhuma sessão nesta fonte"
            sub = f"Pasta: {ellipsize(self.sources[self.source_idx][1], 70)}"
            action = ("refresh", "Atualizar", self.refresh)
        img = self.icon(icon)
        self.empty_icon.configure(image=img)
        self.empty_icon.image = img
        self.empty_title.configure(text=title)
        self.empty_sub.configure(text=sub)
        if action:
            b.icon, b.text, b.command = action
            b.relayout()
            if not b.winfo_manager():
                b.pack()
        elif b.winfo_manager():
            b.pack_forget()
        self.empty.place(in_=self.tree, relx=0.5, rely=0.42, anchor="center")
        self.empty.lift()

    def update_banner(self):
        crit = self.critical_rows()
        key = (self.sources[self.source_idx][0], CONTEXT_LIMITS['critical'])
        show = bool(crit) and self.match is None and self.banner_dismissed != key
        if show:
            n = len(crit)
            self.banner_msg.configure(text=f"{n} sessão(ões) acima do nível crítico ({fmt_tokens(CONTEXT_LIMITS['critical'])} tokens). "
                                           "Gere o dossiê e retome em uma sessão nova para não perder qualidade.")
            if not self.banner.winfo_manager():
                self.banner.pack(fill=tk.X, padx=self.px(16), pady=(0, self.px(8)), before=self.holder)
        elif self.banner.winfo_manager():
            self.banner.pack_forget()

    def show_critical(self):
        crit = self.critical_rows()
        self.match = {r['cid'] for r in crit}
        self.chip_filter = None
        self.search_note = f"{len(crit)} sessão(ões) críticas"
        self.populate()

    def dismiss_banner(self):
        self.banner_dismissed = (self.sources[self.source_idx][0], CONTEXT_LIMITS['critical'])
        self.update_banner()

    def show_theme_menu(self):
        if self.theme_picker is not None:
            self.theme_picker.close()
            return
        self.theme_picker = ThemePicker(self, self.btn['theme'])

    def theme_button_text(self):
        return f"{THEMES[self.theme_key]['name']} ▾"

    # --- widgets ---

    def open_about(self):
        if self.about_win is not None and self.about_win.winfo_exists():
            self.about_win.lift()
            self.about_win.focus_set()
            return
        self.about_win = AboutDialog(self)

    def make_button(self, parent, name, icon, text, command, tip, kind="normal", bg_token="bg", icon_token="btn_fg", stretch=False, icon_only=False):
        b = IconButton(parent, self, icon, text, command, kind=kind, tip=tip, bg_token=bg_token, icon_token=icon_token, stretch=stretch, icon_only=icon_only)
        self.icon_buttons.append(b)
        self.btn[name] = b
        return b

    def create_widgets(self):
        t = self.t
        # Cabeçalho: marca à esquerda; atualizar e tema à direita
        self.top_frame = self.themed_widget(tk.Frame(self, padx=self.px(16), pady=self.px(10)), bg="header_bg")
        self.top_frame.pack(fill=tk.X)
        self.brand = self.themed_widget(tk.Frame(self.top_frame), bg="header_bg")
        self.brand.pack(side=tk.LEFT)
        self.themed_widget(tk.Label(self.brand, text="◆", font=self.f_title), bg="header_bg", fg="header_fg").pack(side=tk.LEFT)
        # O nome do app já está na barra de título da janela; o cabeçalho diz para que serve.
        self.title_lbl = self.themed_widget(tk.Label(self.brand, text="Gestão de contexto e curadoria", font=self.f_title), bg="header_bg", fg="header_fg")
        self.title_lbl.pack(side=tk.LEFT, padx=(self.px(8), self.px(12)))
        Tooltip(self.title_lbl, self, lambda: f"AntigravityGate v{__version__}")
        self.hdr_right = self.themed_widget(tk.Frame(self.top_frame), bg="header_bg")
        self.hdr_right.pack(side=tk.RIGHT)
        self.make_button(self.hdr_right, "about", "about", "Sobre", self.open_about, "Sobre: versão, autor e diagnóstico (F1)", bg_token="header_bg", icon_token="accent_text", icon_only=True).pack(side=tk.RIGHT, padx=(self.px(8), 0))
        self.make_button(self.hdr_right, "theme", "theme", self.theme_button_text(), self.show_theme_menu, "Escolher tema e estilo de ícones", bg_token="header_bg", icon_token="accent_text").pack(side=tk.RIGHT, padx=(self.px(8), 0))
        self.make_button(self.hdr_right, "limits", "limits", "Limites", self.open_limits, self.limits_tip(), bg_token="header_bg", icon_token="warning").pack(side=tk.RIGHT, padx=(self.px(8), 0))
        self.make_button(self.hdr_right, "refresh", "refresh", "Atualizar", self.refresh, "Reler as pastas e recarregar as sessões (F5)", bg_token="header_bg").pack(side=tk.RIGHT)

        # Filtros: fonte das sessões e busca
        self.filter_frame = self.themed_widget(tk.Frame(self, padx=self.px(16), pady=self.px(10)), bg="bg")
        self.filter_frame.pack(fill=tk.X)
        self.src_box = ttk.Combobox(self.filter_frame, state="readonly", width=44, values=[s[0] for s in self.sources])
        self.src_box.current(self.source_idx)
        self.src_box.bind("<<ComboboxSelected>>", lambda e: self.on_source_change())
        self.src_box.pack(side=tk.LEFT)
        self.make_button(self.filter_frame, "clear", "clear", "Limpar", self.clear_search, "Limpar a busca (Esc)").pack(side=tk.RIGHT, padx=(self.px(6), 0))
        self.make_button(self.filter_frame, "search", "search", "Buscar", self.run_search, "Buscar em título, pasta, agente, UUID e no conteúdo das conversas (Enter)", icon_token="accent_text").pack(side=tk.RIGHT, padx=(self.px(10), 0))
        box = self.themed_widget(tk.Frame(self.filter_frame, padx=1, pady=1), bg="border")
        box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(self.px(12), 0), ipady=self.px(2))
        inner = self.themed_widget(tk.Frame(box), bg="panel")
        inner.pack(fill=tk.BOTH, expand=True)
        self.search_icon = self.themed_widget(tk.Label(inner, font=self.f_icon, text=ICONS["search"][0 if self.icon_mode == "mdl2" else 1]), bg="panel", fg="muted")
        self.search_icon.pack(side=tk.LEFT, padx=(self.px(8), self.px(4)))
        self.search_var = tk.StringVar()
        self.search_entry = self.themed_widget(tk.Entry(inner, textvariable=self.search_var, relief=tk.FLAT, font=self.f_ui, highlightthickness=0),
                                               bg="panel", fg="fg", insertbackground="fg")
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=self.px(4))
        self.search_entry.bind("<Return>", lambda e: self.run_search())
        self.search_entry.bind("<Escape>", lambda e: self.clear_search())
        self.bind("<Control-f>", lambda e: (self.search_entry.focus_set(), "break")[1])

        # Ações sobre a seleção
        self.actions_frame = self.themed_widget(tk.Frame(self, padx=self.px(16), pady=0), bg="bg")
        self.actions_frame.pack(fill=tk.X, pady=(0, self.px(8)))
        gap = self.px(8)
        mk = lambda *a, **k: self.make_button(self.actions_frame, *a, **k)
        mk("approve", "approve", "Aprovar", lambda: self.mark_selected("aprovada"), "Marcar a seleção como aprovada (entra no Auto-Run)", icon_token="success").pack(side=tk.LEFT)
        mk("archive", "archive", "Arquivar", lambda: self.mark_selected("arquivada"), "Marcar a seleção como arquivada", icon_token="warning").pack(side=tk.LEFT, padx=(gap, 0))
        mk("pending", "pending", "Pendente", lambda: self.mark_selected("pendente"), "Voltar a seleção para pendente", icon_token="muted").pack(side=tk.LEFT, padx=(gap, 0))
        self.sep1 = self.themed_widget(tk.Frame(self.actions_frame, width=1, height=self.px(22)), bg="border")
        self.sep1.pack(side=tk.LEFT, padx=self.px(14))
        mk("export", "export", "Exportar diálogo", self.open_selected, "Salvar a conversa completa em Markdown (duplo clique na sessão)").pack(side=tk.LEFT)
        mk("dossier", "dossier", "Dossiê de retomada", lambda: self.start_export('dossier'), "Salvar um resumo local para retomar a sessão (segredos mascarados)", icon_token="accent_text").pack(side=tk.LEFT, padx=(gap, 0))
        mk("autorun", "autorun", "Auto-Run", self.start_autorun, "Retomar as sessões aprovadas em sessões novas com o agy", kind="primary").pack(side=tk.RIGHT)

        # Barra de status: fonte, carga, avisos e selos de contagem
        self.footer = self.themed_widget(tk.Frame(self, padx=self.px(14), pady=self.px(6)), bg="panel2")
        self.footer.pack(side=tk.BOTTOM, fill=tk.X)
        for token, key in (("danger", "crit"), ("warning", "rot"), ("muted", "arquivada"), ("success", "aprovada"), ("accent_text", "pendente")):
            chip = Chip(self.footer, self, token, key)
            chip.pack(side=tk.RIGHT, padx=(self.px(6), 0))
            self.chips[key] = chip
        self.status = self.themed_widget(tk.Label(self.footer, anchor=tk.W, font=self.f_small), bg="panel2", fg="fg")
        self.status.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Tabela (Treeview) com métricas de contexto
        # Painel de detalhes da seleção (recolhível), acima do rodapé
        self.details = self.themed_widget(tk.Frame(self, highlightthickness=1), bg="panel", highlightbackground="border")
        self.details.pack(side=tk.BOTTOM, fill=tk.X, padx=self.px(16), pady=(0, self.px(8)))
        bar = self.themed_widget(tk.Frame(self.details, padx=self.px(10), pady=self.px(4), cursor="hand2"), bg="panel2")
        bar.pack(fill=tk.X)
        self.details_toggle = self.themed_widget(tk.Label(bar, font=self.f_bold, cursor="hand2"), bg="panel2", fg="fg")
        self.details_toggle.pack(side=tk.LEFT)
        for w in (bar, self.details_toggle):
            w.bind("<Button-1>", lambda e: self.toggle_details())
        self.details_body = self.themed_widget(tk.Frame(self.details, padx=self.px(14), pady=self.px(10)), bg="panel")
        self.build_details()
        self.apply_details_visibility()

        # Aviso de sessões acima do nível crítico (aparece só quando há; fica entre as ações e a tabela)
        self.banner = self.themed_widget(tk.Frame(self, padx=self.px(12), pady=self.px(8), highlightthickness=1), bg="banner_bg", highlightbackground="danger")
        self.themed_widget(tk.Label(self.banner, text="‼", font=self.f_title), bg="banner_bg", fg="danger").pack(side=tk.LEFT, padx=(0, self.px(10)))
        self.banner_msg = self.themed_widget(tk.Label(self.banner, anchor="w", justify=tk.LEFT, font=self.f_ui), bg="banner_bg", fg="fg")
        self.banner_msg.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.make_button(self.banner, "banner_dismiss", "clear", "Dispensar", self.dismiss_banner, "Esconder este aviso até mudar de fonte ou de limite", bg_token="banner_bg").pack(side=tk.RIGHT, padx=(self.px(8), 0))
        self.make_button(self.banner, "banner_view", "search", "Ver críticas", self.show_critical, "Listar só as sessões críticas", bg_token="banner_bg", icon_token="danger").pack(side=tk.RIGHT)

        holder = self.holder = self.themed_widget(tk.Frame(self, padx=self.px(16)), bg="bg")
        holder.pack(fill=tk.BOTH, expand=True, pady=(0, self.px(10)))
        self.empty = self.themed_widget(tk.Frame(holder, padx=self.px(24), pady=self.px(18)), bg="panel")
        self.empty_icon = self.themed_widget(tk.Label(self.empty), bg="panel")
        self.empty_icon.pack()
        self.empty_title = self.themed_widget(tk.Label(self.empty, font=self.f_title), bg="panel", fg="fg")
        self.empty_title.pack(pady=(self.px(6), 0))
        self.empty_sub = self.themed_widget(tk.Label(self.empty, font=self.f_ui, wraplength=self.px(420), justify=tk.CENTER), bg="panel", fg="muted")
        self.empty_sub.pack(pady=(self.px(4), self.px(10)))
        self.make_button(self.empty, "empty_action", "refresh", "Atualizar", self.refresh, "", bg_token="panel")
        columns = ("col_date", "col_size", "col_ctx", "col_steps", "col_fail", "col_title", "col_agent", "col_uuid")
        self.tree = ttk.Treeview(holder, columns=columns, show="tree headings", selectmode="extended")

        self.tree.heading("#0", text="Projeto / Sessão", anchor=tk.W)
        for col in columns:
            anchor = tk.CENTER if col in ("col_size", "col_ctx", "col_steps", "col_fail") else tk.W
            cmd = (lambda c=col: self.sort_by(c)) if col in SORT_FUNCS else ""
            self.tree.heading(col, text=HEADINGS[col], anchor=anchor, command=cmd)

        self.tree.heading("col_date", text=HEADINGS["col_date"] + " ▼")  # ordenação inicial: mais recentes primeiro
        self.tree.column("#0", width=self.px(270), anchor=tk.W)
        self.tree.column("col_date", width=self.px(150), anchor=tk.W)
        self.tree.column("col_size", width=self.px(95), anchor=tk.CENTER)
        self.tree.column("col_ctx", width=self.px(165), anchor=tk.CENTER)
        self.tree.column("col_steps", width=self.px(75), anchor=tk.CENTER)
        self.tree.column("col_title", width=self.px(320), anchor=tk.W)
        self.tree.column("col_agent", width=self.px(140), anchor=tk.W)
        self.tree.column("col_fail", width=self.px(75), anchor=tk.CENTER)
        self.tree.column("col_uuid", width=self.px(150), anchor=tk.W)

        scrollbar = ttk.Scrollbar(holder, orient=tk.VERTICAL, command=self.tree.yview)
        hscroll = ttk.Scrollbar(holder, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar.set, xscrollcommand=hscroll.set)

        # Barras empacotadas antes da árvore: não somem quando a janela encolhe. A horizontal dá acesso às colunas do fim.
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        hscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Button-3>", self.show_menu)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.update_actions())
        self.bind("<F5>", lambda e: self.refresh())
        self.bind("<F1>", lambda e: self.open_about())
        self.update_actions()

    # --- responsividade e estados ---

    def fit_buttons(self, frame, buttons, reserved=0):
        """Se os botões não cabem na largura, todos viram só ícone (com dica ao passar o mouse): nada é cortado."""
        avail = frame.winfo_width() - reserved
        if avail <= 1 or self.icon_mode == "none":
            return
        need = sum(b.measure(False) + self.px(8) for b in buttons)
        for b in buttons:
            b.set_compact(need > avail)

    def schedule_save_window(self, e):
        if e.widget is not self:
            return
        if self._win_job:
            self.after_cancel(self._win_job)
        self._win_job = self.after(700, self.save_window)

    def zoom(self):
        """Maximiza (Windows: estado 'zoomed'; X11: atributo -zoomed)."""
        try:
            self.state("zoomed")
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)
            except tk.TclError:
                pass

    def save_window(self):
        """Grava tamanho e posição. Maximizada: guarda só que estava maximizada e em que monitor (centro da janela);
        o tamanho normal anterior é mantido."""
        self._win_job = None
        geo = parse_geometry(self.geometry())
        state = self.wm_state()
        if not geo or state not in ("normal", "zoomed"):
            return
        w, h, x, y = geo
        if state == "zoomed":
            win = dict(self.settings.get("window") or {})
            win.update(zoomed=True, zx=x + w // 2, zy=y + h // 2)
        else:
            win = dict(w=w, h=h, x=x, y=y, zoomed=False)
        self.settings["window"] = win
        save_settings(self.settings)

    def on_close(self):
        busy = [name for name, flag in (("o Auto-Run", self.autorunning), ("uma exportação", self.exporting)) if flag]
        if busy:
            if not messagebox.askyesno("Sair do AntigravityGate",
                                       f"Há {' e '.join(busy)} em andamento. Cancelar e sair?\n\n"
                                       "O que já terminou fica registrado; o item em curso é interrompido e não é salvo."):
                return
            self.status.configure(text="Cancelando antes de sair…")
            self.update_idletasks()
            self.stop_background_work()
        if self._win_job:
            self.after_cancel(self._win_job)
            self.save_window()
        self.destroy()

    def stop_background_work(self, timeout=12.0):
        """Cancela Auto-Run e exportação e espera as threads terminarem (o agy é encerrado e a falha fica registrada)."""
        self.export_cancel = True
        if self.runner and self.autorunning:
            self.runner.cancel()
        deadline = time.time() + timeout
        for th in (self.auto_thread, self.export_thread):
            if th and th.is_alive():
                th.join(max(0.0, deadline - time.time()))
                if th.is_alive():
                    log.warning("Trabalho em segundo plano não terminou em %.0f s; saindo mesmo assim", timeout)

    def on_resize(self, _e=None):
        if getattr(self, "_fit_job", None):
            self.after_cancel(self._fit_job)
        self._fit_job = self.after(60, self._fit_all)

    def _fit_all(self):
        self._fit_job = None
        if not self.btn:
            return
        names = ("approve", "archive", "pending", "export", "dossier", "autorun")
        self.fit_buttons(self.actions_frame, [self.btn[n] for n in names], reserved=self.px(60) + self.px(32))
        hdr_room = self.top_frame.winfo_width() - self.brand.winfo_reqwidth() - self.px(32)
        both = [self.btn["limits"], self.btn["refresh"], self.btn["theme"]]
        compact = sum(b.measure(False) for b in both) + self.btn["about"].measure() + self.px(32) > hdr_room
        for b in both:
            b.set_compact(compact)

    def autorun_candidates(self):
        return [r for grp in self.grouped.values() for r in grp if self.states.get(r['cid']) == "aprovada" and r['fpath']]

    def update_actions(self):
        """Habilita ou desabilita cada botão conforme a seleção e o que está em andamento, e explica o motivo na dica."""
        if not self.btn:
            return
        sel = self.tree.selection()
        first_session = bool(sel) and self.is_session(sel[0])
        fpath = self.db_files.get(self.cid_of(sel[0]), '') if first_session else ''
        for name in ("approve", "archive", "pending"):
            self.btn[name].set_enabled(bool(sel) and not self.loading, "" if sel else "Selecione uma ou mais sessões (ou uma pasta de projeto).")
        if self.exporting:
            reason = "Exportação em andamento."
        elif not first_session:
            reason = "Selecione uma sessão na tabela."
        elif not fpath:
            reason = "Esta sessão não tem arquivo de banco nesta fonte."
        else:
            reason = ""
        for name in ("export", "dossier"):
            self.btn[name].set_enabled(not reason, reason)
        cands = self.autorun_candidates()
        pend = [r for r in cands if r['cid'] not in self.handoffs]
        ar_reason = "Auto-Run em andamento." if self.autorunning else ("" if cands else "Nenhuma sessão aprovada com arquivo nesta fonte. Aprove sessões primeiro.")
        self.btn["autorun"].set_enabled(not ar_reason, ar_reason)
        self.btn["autorun"].set_badge(len(pend))
        if "d_export" in self.btn:
            for name in ("d_export", "d_dossier"):
                self.btn[name].set_enabled(not reason, reason)
            one = first_session and len(self.selected_session_ids()) >= 1
            self.btn["d_copy"].set_enabled(one, "" if one else "Selecione uma sessão.")
            self.btn["d_folder"].set_enabled(bool(fpath), "" if fpath else "Selecione uma sessão com arquivo nesta fonte.")
        self.update_details()

    CHIP_FILTERS = {"pendente": "pendentes", "aprovada": "aprovadas", "arquivada": "arquivadas", "rot": "em atenção", "crit": "críticas"}

    def chip_match(self, key, r):
        if key in ("rot", "crit"):
            return ctx_level(r['ctx']) == (1 if key == "rot" else 2)
        return self.states.get(r['cid'], "pendente") == key

    def toggle_chip_filter(self, key):
        """Selo do rodapé como filtro: mostra só as sessões dele; clicar de novo volta a mostrar todas."""
        if not self.grouped:
            return
        if self.chip_filter == key:
            self.clear_search()
            return
        self.search_var.set("")
        rows = list(self.row_by_cid.values())
        self.match = {r['cid'] for r in rows if self.chip_match(key, r)}
        self.chip_filter = key
        self.search_note = f"Filtro: {len(self.match)} {self.CHIP_FILTERS[key]} (clique no selo de novo para ver todas)"
        self.populate()

    def update_chips(self):
        shown = [self.row_by_cid[self.cid_of(i)] for i in self.iter_sessions() if self.cid_of(i) in self.row_by_cid]
        if self.chip_filter:  # com filtro de selo, cada selo continua contando todas as sessões
            shown = list(self.row_by_cid.values())
        st = lambda r: self.states.get(r['cid'], "pendente")
        counts = {k: sum(1 for r in shown if st(r) == k) for k in ("pendente", "aprovada", "arquivada")}
        levels = [ctx_level(r['ctx']) for r in shown]
        self.chips['pendente'].configure(text=f"○ {counts['pendente']} pendentes")
        self.chips['aprovada'].configure(text=f"✔ {counts['aprovada']} aprovadas")
        self.chips['arquivada'].configure(text=f"▣ {counts['arquivada']} arquivadas")
        self.chips['rot'].configure(text=f"⚠ {levels.count(1)} em atenção")
        self.chips['crit'].configure(text=f"‼ {levels.count(2)} críticas")
        for c in self.chips.values():
            c.repaint()

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
                "Confirmar", f"Marcar {len(cids)} sessão(ões) como {STATUS_NAME[status]}?"):
            return
        previous = {c: self.states.get(c, "pendente") for c in cids}
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
        self.btn[{"aprovada": "approve", "arquivada": "archive", "pendente": "pending"}[status]].flash_ok()
        n = len(cids)
        self.notify("ok", f"{n} sessão marcada como {STATUS_NAME[status]}" if n == 1 else f"{n} sessões marcadas como {STATUS_NAME[status]}",
                    [("Desfazer", lambda: self.undo_mark(previous))])

    def undo_mark(self, previous):
        """Volta cada sessão ao estado que tinha antes da última marcação."""
        by_status = {}
        for cid, st in previous.items():
            by_status.setdefault(st, []).append(cid)
        try:
            for st, cids in by_status.items():
                self.state.set_many(cids, st)
        except sqlite3.Error as e:
            log.exception("Falha ao desfazer")
            messagebox.showerror("Erro", f"Não foi possível desfazer:\n{e}")
            return
        self.states = self.state.load()
        self.refresh_labels()
        self.notify("info", f"Desfeito: {len(previous)} sessão(ões) voltaram ao estado anterior.")

    def row_tags(self, cid):
        st = self.states.get(cid, "pendente")
        level = ctx_level(self.row_by_cid.get(cid, {}).get('ctx', 0))
        if st == "arquivada":
            return ("st_arquivada",)
        if level == 2:
            return ("crit",)
        if st == "aprovada":
            return ("st_aprovada",)
        return ("rot",) if level == 1 else ()

    def leaf_text(self, cid):
        n = self.sub_count.get(cid, 0)
        sub = f"  (+{n} sub-agente{'s' if n != 1 else ''})" if n else ""
        ret = f"  ↪ retomada {self.handoffs[cid][:8]}" if self.handoffs.get(cid) else ""
        return "  " + STATUS_NAME[self.states.get(cid, "pendente")] + ret + sub

    def refresh_labels(self):
        for iid in self.iter_sessions():
            cid = self.cid_of(iid)
            self.tree.item(iid, text=self.leaf_text(cid), tags=self.row_tags(cid), image=self.status_icon(cid))
        self.set_status(self.base_status)

    # --- painel de detalhes ---

    def build_details(self):
        body = self.details_body
        left = self.themed_widget(tk.Frame(body), bg="panel")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        head = self.themed_widget(tk.Frame(left), bg="panel")
        head.pack(fill=tk.X)
        self.d_icon = self.themed_widget(tk.Label(head), bg="panel")
        self.d_icon.pack(side=tk.LEFT, padx=(0, self.px(8)))
        self.d_title = self.themed_widget(tk.Label(head, font=self.f_bold, anchor="w", justify=tk.LEFT), bg="panel", fg="fg")
        self.d_title.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.d_sub = self.themed_widget(tk.Label(left, font=self.f_small, anchor="w", justify=tk.LEFT), bg="panel", fg="muted")
        self.d_sub.pack(fill=tk.X, pady=(0, self.px(6)))
        self.gauge = self.themed_widget(tk.Canvas(left, height=self.px(72), highlightthickness=0, bd=0), bg="panel")
        self.gauge.pack(fill=tk.X)
        self.gauge.bind("<Configure>", lambda e: self.draw_gauge(self.gauge_ctx))
        self.gauge_ctx = 0
        self.d_note = self.themed_widget(tk.Label(left, font=self.f_ui, anchor="w", justify=tk.LEFT, wraplength=self.px(520)), bg="panel", fg="muted")

        self.d_facts = self.themed_widget(tk.Frame(body), bg="panel")
        self.d_facts.pack(side=tk.LEFT, fill=tk.Y, padx=self.px(18))
        self.fact_vals = {}
        facts = (("Estado", "state"), ("UUID", "uuid"), ("Workspace", "ws"), ("Agente", "agent"), ("Passos", "steps"),
                 ("Modificação", "date"), ("Tamanho", "size"), ("Falhas", "fails"), ("Retomada", "handoff"), ("Origem", "origin"))
        for i, (label, key) in enumerate(facts):
            r, c = i % 5, (i // 5) * 2
            self.themed_widget(tk.Label(self.d_facts, text=label, font=self.f_small, anchor="w"), bg="panel", fg="muted").grid(row=r, column=c, sticky="w", padx=(0 if c == 0 else self.px(18), self.px(8)), pady=1)
            v = self.themed_widget(tk.Label(self.d_facts, font=self.f_ui, anchor="w", justify=tk.LEFT), bg="panel", fg="fg")
            v.grid(row=r, column=c + 1, sticky="w", pady=1)
            self.fact_vals[key] = v

        acts = self.themed_widget(tk.Frame(body), bg="panel")
        acts.pack(side=tk.RIGHT, fill=tk.Y)
        acts.grid_columnconfigure(0, uniform="dacts")  # duas colunas da mesma largura: botões alinhados
        acts.grid_columnconfigure(1, uniform="dacts")
        mkb = lambda name, icon, text, cmd, tip, tok="btn_fg": self.make_button(acts, name, icon, text, cmd, tip, bg_token="panel", icon_token=tok, stretch=True)
        mkb("d_copy", "copy", "Copiar UUID", self.copy_selected_uuid, "Copiar o UUID da sessão").grid(row=0, column=0, padx=(0, self.px(3)), pady=(0, self.px(6)), sticky="ew")
        mkb("d_folder", "folder", "Abrir pasta", self.open_selected_folder, "Abrir a pasta do banco da sessão").grid(row=0, column=1, padx=(self.px(3), 0), pady=(0, self.px(6)), sticky="ew")
        mkb("d_export", "export", "Exportar diálogo", self.open_selected, "Salvar a conversa completa em Markdown").grid(row=1, column=0, padx=(0, self.px(3)), sticky="ew")
        mkb("d_dossier", "dossier", "Dossiê", lambda: self.start_export('dossier'), "Salvar o dossiê de retomada", "accent_text").grid(row=1, column=1, padx=(self.px(3), 0), sticky="ew")

    def toggle_details(self):
        self.settings['details'] = not self.settings.get('details', True)
        save_settings(self.settings)
        self.apply_details_visibility()

    def apply_details_visibility(self):
        opened = self.settings.get('details', True)
        self.details_toggle.configure(text=("▾  Detalhes da sessão" if opened else "▸  Detalhes da sessão"))
        if opened and not self.details_body.winfo_manager():
            self.details_body.pack(fill=tk.X)
        elif not opened and self.details_body.winfo_manager():
            self.details_body.pack_forget()

    def selected_session_ids(self):
        return [i for i in self.tree.selection() if self.is_session(i)]

    def copy_selected_uuid(self):
        ids = self.selected_session_ids()
        if ids:
            self.copy_uuid(ids[0])

    def open_selected_folder(self):
        ids = self.selected_session_ids()
        if ids:
            self.open_folder(ids[0])

    def level_text(self, ctx):
        return {0: "normal", 1: "atenção", 2: "crítico"}[ctx_level(ctx)]

    def draw_gauge(self, ctx):
        """Medidor de contexto: faixas normal, atenção e crítico, barra até o valor atual e marcas dos limites."""
        c = self.gauge
        c.delete("all")
        t = self.t
        w, h = max(c.winfo_width(), self.px(280)), self.px(72)
        pad = self.px(8)
        x0, x1, y0, y1 = pad, w - pad, self.px(24), self.px(38)
        att, crit = CONTEXT_LIMITS['attention'], CONTEXT_LIMITS['critical']
        top = max(crit * 1.25, ctx * 1.05)
        X = lambda v: x0 + (x1 - x0) * min(v / top, 1)
        r = self.px(4)
        round_rect(c, x0, y0, x1, y1, r, fill=blend(t['panel'], t['fg'], 0.08), outline="")
        for lo, hi, tok in ((0, att, 'success'), (att, crit, 'warning'), (crit, top, 'danger')):
            c.create_rectangle(X(lo), y0 + 1, X(hi), y1 - 1, fill=blend(t['panel'], t[tok], 0.22), outline="")
        if ctx:
            tok = ('success', 'warning', 'danger')[ctx_level(ctx)]
            round_rect(c, x0, y0 + 2, max(X(ctx), x0 + self.px(6)), y1 - 2, r, fill=t[tok], outline="")
        for v, label in ((att, "atenção"), (crit, "crítico")):
            c.create_line(X(v), y0 - self.px(5), X(v), y1 + self.px(5), fill=t['muted'])
            c.create_text(X(v), y0 - self.px(8), text=f"{label} {fmt_tokens(v)}", font=self.f_small, fill=t['muted'], anchor="s" if X(v) < x1 - self.px(70) else "se")
        if ctx:
            tok = ('success', 'warning', 'danger')[ctx_level(ctx)]
            c.create_text(x0, y1 + self.px(8), text=f"{ctx:,}".replace(",", ".") + f" tokens · {self.level_text(ctx)}", font=self.f_bold, fill=t[tok], anchor="nw")
        else:
            c.create_text(x0, y1 + self.px(8), text="Sem dado de contexto nesta sessão", font=self.f_small, fill=t['muted'], anchor="nw")

    def set_detail_icon(self, name, handoff=False, cid=None):
        img = self.status_icon(cid) if cid else self.icon(name, handoff)
        self.d_icon.configure(image=img)
        self.d_icon.image = img

    def update_details(self):
        if not hasattr(self, "d_title"):
            return
        sel = self.tree.selection()
        sessions = [self.row_by_cid[self.cid_of(i)] for i in self.selected_session_ids() if self.cid_of(i) in self.row_by_cid]
        t = self.t
        self.d_note.pack_forget()
        show_rich = len(sel) == 1 and len(sessions) == 1
        for w in (self.gauge, self.d_facts):
            if show_rich:
                w.pack(fill=tk.X) if w is self.gauge else w.pack(side=tk.LEFT, fill=tk.Y, padx=self.px(18))
            else:
                w.pack_forget()
        if not sel:
            self.set_detail_icon("info")
            self.d_title.configure(text="Nenhuma sessão selecionada")
            self.d_sub.configure(text="")
            self.d_note.configure(text="Selecione uma sessão para ver contexto, workspace, falhas e retomada. Use Ctrl ou Shift para várias.")
            self.d_note.pack(fill=tk.X)
            self.gauge_ctx = 0
            return
        if not show_rich:
            rows = sessions
            if not rows:  # pasta de projeto
                rows = [self.row_by_cid[self.cid_of(i)] for p in sel for i in self.iter_sessions(p) if self.cid_of(i) in self.row_by_cid]
                name = self.tree.item(sel[0], "text").strip() if len(sel) == 1 else f"{len(sel)} pastas"
            else:
                name = f"{len(rows)} sessões selecionadas"
            st = lambda r: self.states.get(r['cid'], "pendente")
            lv = [ctx_level(r['ctx']) for r in rows]
            self.set_detail_icon("folder")
            self.d_title.configure(text=name)
            self.d_sub.configure(text=f"{len(rows)} sessões · maior contexto {fmt_tokens(max((r['ctx'] for r in rows), default=0))}")
            self.d_note.configure(text=(f"○ {sum(1 for r in rows if st(r) == 'pendente')} pendentes   ✔ {sum(1 for r in rows if st(r) == 'aprovada')} aprovadas   "
                                        f"▣ {sum(1 for r in rows if st(r) == 'arquivada')} arquivadas   ⚠ {lv.count(1)} em atenção   ‼ {lv.count(2)} críticas   "
                                        f"falhas de ferramenta: {sum(r['failures'] for r in rows)}"))
            self.d_note.pack(fill=tk.X)
            return
        r = sessions[0]
        cid = r['cid']
        self.set_detail_icon(None, cid=cid)
        self.d_title.configure(text=r['title'])
        bits = [r['project'], r['agent'] or "agente principal"]
        if r['origin']:
            bits.append(r['origin'])
        self.d_sub.configure(text=" · ".join(bits))
        self.gauge_ctx = r['ctx']
        self.draw_gauge(r['ctx'])
        F = self.fact_vals
        state = STATUS_NAME[self.states.get(cid, "pendente")]
        if r['running']:
            state += " · em execução"
        if r['killed']:
            state += " · encerrada à força"
        F['state'].configure(text=state)
        F['uuid'].configure(text=cid)
        ws_mark = "" if r['ws_ok'] is None else ("✔ " if r['ws_ok'] else "⚠ ")
        F['ws'].configure(text=(ws_mark + ellipsize(r['workspace'], 46)) if r['workspace'] else "não informado",
                          fg=t['warning'] if r['ws_ok'] is False else t['fg'])
        F['agent'].configure(text=r['agent'] or "-")
        F['steps'].configure(text=str(r['steps']))
        F['date'].configure(text=f"{r['date']}  ·  {rel_time(r['date'])}".rstrip(" ·"))
        F['size'].configure(text=r['size'])
        F['fails'].configure(text=(f"⚠ {r['failures']} ferramenta(s)" if r['failures'] else "nenhuma"), fg=t['warning'] if r['failures'] else t['fg'])
        F['handoff'].configure(text=(f"↪ {self.handoffs[cid][:8]}" if self.handoffs.get(cid) else "-"))
        F['origin'].configure(text=r['origin'] or "-")

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
        self.chip_filter = None
        self.search_note = f"{len(self.match)} resultado(s) para “{q}”" + ("" if content_ok else " (só metadados: sem índice de conteúdo nesta fonte)")
        self.populate()

    def clear_search(self):
        self.search_var.set("")
        self.match = None
        self.chip_filter = None
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
        self.notify("ok", f"UUID copiado: {self.cid_of(iid)}")

    def open_folder(self, iid):
        fpath = self.db_files.get(self.cid_of(iid), '')
        if not fpath:
            messagebox.showinfo("Aviso", "Esta sessão não tem arquivo nesta fonte.")
            return
        self.open_path(os.path.dirname(fpath))

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
        self.status.configure(text=text)
        self.update_chips()
        self.update_banner()
        self.update_empty()
        self.update_actions()

    def load_data(self):
        """Dispara a leitura em thread de trabalho; a janela continua responsiva."""
        self.gen += 1
        gen = self.gen
        label, conv_dir, sum_db = self.sources[self.source_idx]
        is_active = self.source_idx == 0
        self.loading = True
        self.btn["refresh"].set_busy(True)
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
                if kind.startswith('auto'):
                    self.on_auto_event(kind, payload)
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
        self.btn["refresh"].set_busy(False)
        label = self.sources[self.source_idx][0]
        if 'error' in res:
            self.set_status(f"{label}  |  ⚠ erro ao carregar — ver {LOG_FILE}")
            return
        self.proj_map, self.summaries, self.db_files = res['proj_map'], res['summaries'], res['db_files']
        self.warnings = len(res['warnings'])
        self.grouped, self.total = res['grouped'], res['total']
        self.row_by_cid = {r['cid']: r for grp in self.grouped.values() for r in grp}
        self.match, self.search_note, self.chip_filter = None, "", None
        self.search_var.set("")
        try:
            self.states = self.state.load()
            self.handoffs = self.state.handoffs_ok()
        except sqlite3.Error as e:
            log.warning("Falha ao ler estado: %s", e)
            self.states, self.handoffs = {}, {}
        self.populate()
        if self.warnings:
            self.notify("warn", f"{self.warnings} aviso(s) ao ler os bancos de sessão. Algumas sessões podem estar incompletas.",
                        [("Abrir log", lambda: self.open_path(LOG_FILE))])

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
            proj_node = self.tree.insert("", tk.END, text=f"  {pname} ({len(rows)} sessões)", values=("",) * 8, tags=('proj',), image=self.icon("folder"))
            placed = set()

            def add(parent_iid, r):
                if r['cid'] in placed:
                    return  # proteção contra ciclos de parentesco
                placed.add(r['cid'])
                iid = self.tree.insert(parent_iid, tk.END, text=self.leaf_text(r['cid']), tags=self.row_tags(r['cid']), image=self.status_icon(r['cid']),
                                       values=(r['date'], r['size'], ctx_label(r['ctx']), r['steps'], f"⚠ {r['failures']}" if r['failures'] else "-",
                                               r['title'], r['agent'] or "-", r['cid']))
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
                'workspace': ", ".join(uri_paths(str(val(s, 'workspace_uris')))) or urllib.parse.unquote(str(val(s, 'workspace_uris'))), 'agent': row.get('agent', ''),
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
        self.exporting, self.export_cancel = True, False
        self.exporting_btn = self.btn["export" if kind == 'full' else "dossier"]
        self.exporting_btn.set_busy(True, "Exportando…")
        self.update_actions()
        self.set_status(f"{self.base_status}  |  exportando…")

        def progress(n, total):
            if self.export_cancel:
                raise ExportCancelled()
            self.queue.put((0, 'export_progress', (n, total)))

        def job():
            try:
                export_session(kind, meta['fpath'], meta, out, progress=progress)
                self.queue.put((0, 'export_done', out))
            except ExportCancelled:
                log.info("Exportação de %s cancelada", cid)
                self.queue.put((0, 'export_error', "cancelada"))
            except Exception as e:
                log.exception("Falha ao exportar %s", cid)
                self.queue.put((0, 'export_error', f"{type(e).__name__}: {e}"))

        self.export_thread = threading.Thread(target=job, daemon=True)
        self.export_thread.start()

    # --- Auto-Run ---

    def confirm_autorun(self, items, done):
        """Janela de confirmação. Devolve {'dry_run', 'redo'} ou None se o usuário cancelar."""
        win = tk.Toplevel(self)
        win.title("Auto-Run — confirmar")
        win.transient(self)
        result = {'v': None}
        tk.Label(win, text=f"{len(items)} sessão(ões) aprovada(s) nesta fonte. Para cada uma o app gera o dossiê de retomada e, "
                           "fora do modo simulação, abre uma sessão NOVA com o agy (a original não é alterada).",
                 wraplength=620, justify=tk.LEFT, padx=12, pady=8).pack(anchor=tk.W)
        box = tk.Listbox(win, width=90, height=min(12, max(3, len(items))))
        for it in items:
            marca = "  (já retomada)" if it['cid'] in done else ""
            box.insert(tk.END, f"{it['title'][:60]}  [{it['cid'][:8]}]  {it.get('workspace_label', '')}{marca}")
        box.pack(padx=12, fill=tk.BOTH, expand=True)
        dry, redo = tk.BooleanVar(value=True), tk.BooleanVar(value=False)
        tk.Checkbutton(win, text="Só gerar os dossiês (simulação: não chama o agy, não gasta cota)", variable=dry).pack(anchor=tk.W, padx=12, pady=(8, 0))
        tk.Checkbutton(win, text="Refazer as que já foram retomadas", variable=redo).pack(anchor=tk.W, padx=12)
        mrow = tk.Frame(win, padx=12)
        mrow.pack(anchor=tk.W, fill=tk.X, pady=(6, 0))
        tk.Label(mrow, text="Modelo do agy:").pack(side=tk.LEFT)
        self.model_var = tk.StringVar(value=str(self.settings.get("agy_model") or ""))
        history = [m for m in self.settings.get("agy_models", []) if isinstance(m, str)]
        self.model_box = ttk.Combobox(mrow, textvariable=self.model_var, values=self.agy_model_choices(), width=32)
        self.model_box.pack(side=tk.LEFT, padx=(6, 8))
        tk.Label(mrow, text="vazio = padrão do agy; o nome inclui o esforço, ex.: Gemini 3.8 Flash (Medium)", fg="#555555").pack(side=tk.LEFT)
        tk.Label(win, text="Modo do agy: plan (somente leitura). Um erro de cota interrompe o lote inteiro.", fg="#555555", padx=12).pack(anchor=tk.W)

        def go():
            model = self.model_var.get().strip()
            result['v'] = {'dry_run': dry.get(), 'redo': redo.get(), 'model': model}
            self.settings["agy_model"] = model
            if model:
                self.settings["agy_models"] = ([model] + [m for m in history if m != model])[:6]
            save_settings(self.settings)
            win.destroy()
        self.confirm_go, self.confirm_dry, self.confirm_redo = go, dry, redo  # usados pelos testes
        row = tk.Frame(win, pady=10)
        row.pack()
        tk.Button(row, text="Iniciar", width=12, command=go).pack(side=tk.LEFT, padx=6)
        tk.Button(row, text="Cancelar", width=12, command=win.destroy).pack(side=tk.LEFT, padx=6)
        place_over(win, self)
        win.grab_set()
        self.wait_window(win)
        return result['v']

    def agy_model_choices(self):
        """Usados por último, depois a lista conhecida (a mais recente que o agy devolveu, ou a do app), sem repetir."""
        known = [m for m in self.settings.get("agy_models_known", []) if isinstance(m, str)] or AGY_MODELS
        recent = [m for m in self.settings.get("agy_models", []) if isinstance(m, str)]
        # usados por último que o agy conhece vêm primeiro; nomes fora da lista (modelo personalizado) vão para o fim
        return list(dict.fromkeys([m for m in recent if m in known] + known + recent))

    def start_autorun(self):
        if self.autorunning:
            messagebox.showinfo("Aviso", "O Auto-Run já está em andamento.")
            return
        cands = []
        for grp in self.grouped.values():
            for r in grp:
                if self.states.get(r['cid']) == "aprovada" and r['fpath']:
                    meta = self.meta_for(r['cid'])
                    cands.append({'cid': r['cid'], 'title': r['title'], 'fpath': r['fpath'], 'meta': meta,
                                  'workspace': str(val(self.summaries.get(r['cid'], {}), 'workspace_uris')),
                                  'workspace_label': meta['workspace'][-40:]})
        if not cands:
            messagebox.showinfo("Auto-Run", "Nenhuma sessão aprovada com arquivo nesta fonte. Aprove sessões primeiro (botão ✅ Aprovar).")
            return
        cands.sort(key=lambda x: x['title'].lower())
        opts = self.confirm_autorun(cands, set(self.handoffs))
        if not opts:
            return
        items = [c for c in cands if opts['redo'] or c['cid'] not in self.handoffs]
        if not items:
            messagebox.showinfo("Auto-Run", "Todas as sessões aprovadas já foram retomadas. Marque \"Refazer\" para repetir.")
            return
        agy = None
        if not opts['dry_run']:
            agy = find_agy()
            if not agy:
                messagebox.showerror("Auto-Run", "Não encontrei o agy. Confira se `agy --help` funciona no PowerShell, "
                                                 "ou defina AGY_EXE com o caminho do agy.exe.")
                return
        self.autorunning = True
        self.btn["autorun"].set_busy(True, "Executando…")
        self.update_actions()
        model = (opts.get('model') or '').strip()
        self.open_autorun_window(len(items), opts['dry_run'], model)
        runner = AutoRunner(items, self.state, lambda line: self.queue.put((0, 'auto_log', line)), agy=agy, dry_run=opts['dry_run'], model=model or None)
        self.runner = runner

        def job():
            try:
                summary = runner.run()
            except Exception as e:
                log.exception("Auto-Run falhou")
                summary = {'error': f"{type(e).__name__}: {e}"}
            self.queue.put((0, 'auto_done', summary))

        self.auto_thread = threading.Thread(target=job, daemon=True)
        self.auto_thread.start()

    def open_autorun_window(self, n, dry_run, model=""):
        win = tk.Toplevel(self)
        win.title("Auto-Run — " + ("simulação" if dry_run else "executando"))
        txt = tk.Text(win, wrap=tk.WORD, state=tk.DISABLED, font=('Consolas', 9))
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        btn = tk.Button(win, text="Cancelar", width=14, command=self.cancel_autorun)
        btn.pack(pady=(0, 8))
        win.protocol("WM_DELETE_WINDOW", self.cancel_autorun)  # X = Cancelar (lote rodando) ou Fechar (depois do Fim)
        place_over(win, self, size=(780, 420))
        self.auto_win = (win, txt, btn)
        mode = 'simulação (só dossiês)' if dry_run else 'agy --mode plan, modelo ' + (model or 'padrão do agy')
        self.append_auto(f"{n} sessão(ões) na fila. Modo: {mode}.")

    def append_auto(self, line):
        if not self.auto_win:
            return
        _win, txt, _btn = self.auto_win
        txt.configure(state=tk.NORMAL)
        txt.insert(tk.END, line + "\n")
        txt.see(tk.END)
        txt.configure(state=tk.DISABLED)

    def cancel_autorun(self):
        if self.runner and self.autorunning:
            self.append_auto("Cancelando…")
            self.runner.cancel()
        elif self.auto_win:
            self.auto_win[0].destroy()
            self.auto_win = None

    def on_auto_event(self, kind, payload):
        if kind == 'auto_log':
            self.append_auto(payload)
            return
        self.autorunning = False
        self.btn["autorun"].set_busy(False, "Auto-Run")
        if payload.get('models'):
            self.settings["agy_models_known"] = payload['models']
            bad = payload.get('bad_model')
            if bad:  # nome recusado pelo agy não volta a ser oferecido
                self.settings["agy_models"] = [m for m in self.settings.get("agy_models", []) if m != bad]
                if self.settings.get("agy_model") == bad:
                    self.settings["agy_model"] = ""
            save_settings(self.settings)
        if 'error' not in payload:
            self.btn["autorun"].flash_ok()
        if 'error' in payload:
            self.append_auto(f"Erro inesperado: {payload['error']}")
        else:
            self.append_auto(f"Fim. ✔ {payload['ok']} retomadas · 📋 {payload['dossier']} dossiês (simulação) · ✖ {payload['failed']} falhas · "
                             f"⏭ {payload['skipped']} não executadas" + (f" · motivo: {payload['aborted']}" if payload['aborted'] else ""))
        if self.auto_win:
            self.auto_win[2].configure(text="Fechar")
        try:
            self.states = self.state.load()
            self.handoffs = self.state.handoffs_ok()
        except sqlite3.Error:
            pass
        self.refresh_labels()
        if 'error' in payload:
            self.notify("error", f"Auto-Run falhou: {payload['error']}")
        elif payload['quota']:
            self.notify("warn", f"Auto-Run interrompido: cota esgotada (volta em {payload['quota']}). {payload['ok']} retomadas concluídas.")
        elif payload['failed'] or payload['aborted']:
            self.notify("warn", f"Auto-Run terminou com problemas: {payload['ok']} retomadas, {payload['failed']} falhas, {payload['skipped']} não executadas.")
        else:
            feito = payload['ok'] or payload['dossier']
            self.notify("ok", f"Auto-Run concluído: {feito} sessão(ões) " + ("retomadas." if payload['ok'] else "com dossiê gerado (simulação)."))

    def on_export_event(self, kind, payload):
        if kind == 'export_progress':
            self.status.configure(text=f"{self.base_status}  |  exportando… {payload[0]}/{payload[1]}")
            return
        self.exporting = False
        btn = getattr(self, "exporting_btn", None)
        if btn:
            btn.set_busy(False, "Exportar diálogo" if btn is self.btn["export"] else "Dossiê de retomada")
            if kind == 'export_done':
                btn.flash_ok()
        self.set_status(self.base_status)
        if kind == 'export_error':
            messagebox.showerror("Erro", f"Não foi possível exportar:\n{payload}")
            return
        self.notify("ok", f"Salvo: {os.path.basename(payload)}",
                    [("Abrir arquivo", lambda: self.open_path(payload)), ("Abrir pasta", lambda: self.open_path(os.path.dirname(payload)))])
        if getattr(os, "startfile", None):
            self.open_path(payload)


def selftest(out_path):
    """Abre o app sem mostrar a janela, espera a carga e grava o resultado em `out_path`.
    Usado para verificar o .exe empacotado (tk, sqlite3 e FTS5 presentes). Devolve o código de saída."""
    try:
        try:
            sqlite3.connect(":memory:").execute("CREATE VIRTUAL TABLE t USING fts5(x)")
            fts = "com FTS5"
        except sqlite3.Error:
            fts = "SEM FTS5 (busca por conteúdo indisponível)"
        pb_parse(b"\x08\x01")
        app = AntigravityGateApp()
        app.withdraw()
        end = time.time() + 60
        while app.loading and time.time() < end:
            app.update()
            time.sleep(0.05)
        done = not app.loading
        app.update()
        area = ""
        if os.name == "nt":  # confere a consulta de monitor no Windows de verdade
            primary, at = _win_work_area(), _win_work_area(app.winfo_x() + 50, app.winfo_y() + 50)
            area = f"; área útil principal {primary}, no ponto {at}; barra de título {style_titlebar(app, app.t)}"
        app.destroy()
        msg = f"OK (v{__version__}; {fts}{area})" if done else "FALHA: a carga não terminou em 60 s"
    except Exception as e:
        msg = f"FALHA: {type(e).__name__}: {e}"
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(msg + "\n")
    return 0 if msg.startswith("OK") else 1


def main(argv):
    if len(argv) >= 2 and argv[1] == "--version":
        print(f"AntigravityGate {__version__}")
        return 0
    setup_logging()
    log.info("AntigravityGate %s", __version__)
    if len(argv) >= 3 and argv[1] == "--selftest":
        return selftest(argv[2])
    try:
        AntigravityGateApp().mainloop()
    except Exception:
        log.exception("Falha fatal")
        try:
            messagebox.showerror("AntigravityGate", f"O app fechou por um erro.\nDetalhes em: {LOG_FILE}")
        except Exception:
            pass
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv))
