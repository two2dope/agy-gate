import os
import sqlite3
import gc
import glob
import re
import json
import logging
import logging.handlers
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
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter import font as tkfont

__version__ = "1.2.0"  # ver CHANGELOG.md
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
EXTRA_OWN_DIRS = []  # pastas de dossiê escolhidas pelo usuário (Auto-Run): também são do app
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
HEADINGS = {"col_date": "Modificação", "col_size": "Tamanho", "col_ctx": "Consumo (tokens)", "col_steps": "Passos",
            "col_title": "Título / Contexto Inicial", "col_agent": "Agente", "col_fail": "Falhas", "col_uuid": "UUID", "col_menu": ""}
SORT_FUNCS = {
    "col_date": lambda r: r["date"], "col_size": lambda r: r["size_kb"], "col_ctx": lambda r: r["ctx"],
    "col_steps": lambda r: r["steps"], "col_title": lambda r: r["title"].lower(), "col_agent": lambda r: r["agent"].lower(),
    "col_fail": lambda r: r["failures"],
}
NUMERIC_COLS = ("col_date", "col_size", "col_ctx", "col_steps", "col_fail")  # primeiro clique ordena do maior para o menor

# Cache por (caminho, mtime_ns, tamanho): só reabre o banco de uma sessão se ele mudou.
METRICS_CACHE = {}

log = logging.getLogger("antigravitygate")


LOG_MAX_BYTES = 1_000_000  # gate.log roda ao chegar em ~1 MB; ficam 3 cópias antigas (gate.log.1 a .3)


def setup_logging():
    log.setLevel(logging.INFO)
    for h in list(log.handlers):
        log.removeHandler(h)
        h.close()
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=3, encoding="utf-8")
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


def ctx_label(ctx, two_lines=False):
    """Consumo de contexto: tokens, % do nível crítico, medidor de 5 células (cheio = crítico) e marca de nível (⚠ atenção, ‼ crítico).
    `two_lines` (tabela confortável): tokens e % em cima; medidor e faixa (segura, atenção, crítica) embaixo."""
    if not ctx:
        return "-"
    cells = 5
    level = ctx_level(ctx)
    pct = round(ctx / CONTEXT_LIMITS["critical"] * 100)
    bar = "■" * min(cells, max(1, math.ceil(ctx / CONTEXT_LIMITS["critical"] * cells)))
    bar += "□" * (cells - len(bar))
    if two_lines:
        return f"{fmt_tokens(ctx)} · {pct}%\n{bar} {('segura', 'atenção', 'crítica')[level]}"
    return f"{fmt_tokens(ctx)}  {bar}  {pct}%" + {0: "", 1: " ⚠", 2: " ‼"}[level]


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
    re.compile(r"(?i)(\bAuthorization:\s*Basic\s+)[A-Za-z0-9+/]{8,}=*"),        # cabeçalho Authorization: Basic
    re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}"),                    # Stripe
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),  # JWT
    re.compile(r"\bxox[abposr]-[A-Za-z0-9\-]{10,}"),                         # Slack
    re.compile(r"\bya29\.[A-Za-z0-9_\-]{20,}"),                              # Google OAuth
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}"),                            # GitHub (granular)
    re.compile(r"(\b[a-z][a-z0-9+.\-]*://[^\s:/@]+:)[^\s@/]+(?=@)"),           # senha em URL: user:senha@host
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

HANDOFF_EXTRA = (("model", "TEXT"), ("cwd", "TEXT"), ("project", "TEXT"), ("duration", "REAL"), ("turns", "INTEGER"), ("usage", "TEXT"), ("response", "TEXT"))


class StateStore:
    """Status por sessão (pendente/aprovada/arquivada) + histórico, em gate_state.db.
    Se o arquivo não puder ser criado, cai para memória e `persistent` fica False."""

    def __init__(self, path):
        self.path = path
        self.persistent = True
        self._mem_lock = threading.RLock()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._init()
        except (OSError, sqlite3.Error) as e:
            log.warning("Estado não será salvo (%s): %s", path, e)
            self.path, self.persistent = ":memory:", False
            # Usado também pelas threads de Auto-Run e exportação: sem check_same_thread, com trava própria.
            self._mem = sqlite3.connect(":memory:", check_same_thread=False)
            self._init()

    def _connect(self):
        if not self.persistent:
            return self._mem_session()
        return closing(sqlite3.connect(self.path, timeout=5.0))

    @contextmanager
    def _mem_session(self):
        with self._mem_lock:
            yield _NoClose(self._mem)

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
            have = {r[1] for r in conn.execute("PRAGMA table_info(handoffs)")}
            for col, kind in HANDOFF_EXTRA:  # recibo de retomada (1.2): colunas novas em bancos antigos
                if col not in have:
                    conn.execute(f"ALTER TABLE handoffs ADD COLUMN {col} {kind}")
            # Versões até 2026-10-26 aceitavam SUCCESS sem resposta (o agy não conseguia ler o dossiê). Uma retomada real
            # sempre traz resposta: 'ok' sem detalhe vira erro, e a sessão vazia criada vai para arquivadas se o usuário
            # não tiver marcado outra coisa. Idempotente.
            false_ok = [r[0] for r in conn.execute("SELECT new_cid FROM handoffs WHERE status='ok' AND (detail IS NULL OR detail='')")]
            if false_ok:
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                conn.execute("UPDATE handoffs SET status='erro', detail='sem resposta (sucesso falso de versão anterior, corrigido)' "
                             "WHERE status='ok' AND (detail IS NULL OR detail='')")
                for cid in filter(None, false_ok):
                    conn.execute("INSERT OR IGNORE INTO session_state(cid, status, updated_at) VALUES(?, 'arquivada', ?)", (cid, now))
                log.info("Corrigidas %d retomadas sem resposta de versões anteriores", len(false_ok))
        if self.persistent:
            conn.close()

    def load(self):
        with self._connect() as c:
            return dict(c.execute("SELECT cid, status FROM session_state").fetchall())

    def add_handoff(self, src_cid, new_cid, dossier_path, status, detail='', **extra):
        """Registra uma tentativa de retomada. `extra`: campos do recibo (HANDOFF_EXTRA); os None não são gravados."""
        cols = ["src_cid", "new_cid", "dossier_path", "status", "detail", "at"]
        vals = [src_cid, new_cid, dossier_path, status, detail[:500], datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        for col, _kind in HANDOFF_EXTRA:
            if extra.get(col) is not None:
                cols.append(col)
                vals.append(json.dumps(extra[col]) if col == "usage" and not isinstance(extra[col], str) else extra[col])
        with self._connect() as c:
            with c:
                c.execute(f"INSERT INTO handoffs({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})", vals)

    def handoff_record(self, src_cid):
        """Linha completa da retomada concluída mais recente da sessão (dict), ou None."""
        with self._connect() as c:
            cur = c.execute("SELECT * FROM handoffs WHERE src_cid=? AND status='ok' ORDER BY id DESC LIMIT 1", (src_cid,))
            row = cur.fetchone()
            return dict(zip([d[0] for d in cur.description], row)) if row else None

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


def gate_owned(path):
    """True para pastas do próprio AntigravityGate (dados em LOCALAPPDATA, handoffs ou a pasta do .exe).
    Não são workspace de projeto: as retomadas até a 1.0.0 gravaram essas pastas como workspace da sessão nova."""
    real = os.path.normcase(os.path.realpath(path))
    for own in (LOG_DIR, HANDOFF_DIR, *EXTRA_OWN_DIRS):
        own = os.path.normcase(os.path.realpath(own))
        if real == own or real.startswith(own.rstrip(os.sep) + os.sep):
            return True
    return os.path.isfile(os.path.join(path, "AntigravityGate.exe"))


def workspace_dirs(uris):
    """Pastas existentes citadas em workspace_uris (file:///...), sem as pastas do próprio app."""
    out = []
    for uri in re.findall(r"file://[^\s,;\"'\[\]<>]+", uris or ""):  # URIs vêm codificadas (%20), às vezes dentro de uma lista JSON
        path = uri_to_path(uri)
        if os.path.isdir(path) and path not in out and not gate_owned(path):
            out.append(path)
    return out[:3]


NO_PROJECT_IDS = ("outside-of-project", "default-cli-project")


def project_target(pid):
    """(valor para --project, pastas existentes do projeto) a partir de config/projects.
    Sem --project o agy põe toda sessão do CLI em "CLI Project", qualquer que seja a pasta (CHANGELOG do agy 1.0.12).
    Só devolve o id de um projeto que existe em config/projects: um id desconhecido faria o agy falhar."""
    if not pid or pid in NO_PROJECT_IDS:
        return "", []
    for p_file in glob.glob(os.path.join(PROJECTS_DIR, "*.json")):
        try:
            with open(p_file, encoding="utf-8-sig") as f:
                d = json.load(f)
            if not isinstance(d, dict) or d.get("id") != pid:
                continue
            dirs = []
            for res in (d.get("projectResources") or {}).get("resources") or []:
                u = res.get("folderUri") or (res.get("gitFolder") or {}).get("folderUri")
                path = uri_to_path(u) if u else ""
                if path and os.path.isdir(path) and not gate_owned(path) and path not in dirs:
                    dirs.append(path)
            return pid, dirs
        except (OSError, ValueError, AttributeError, TypeError):
            continue
    return "", []


def uri_paths(uris):
    """Caminhos citados em workspace_uris (sem exigir que existam), para exibição."""
    out = []
    for uri in re.findall(r"file://[^\s,;\"'\[\]<>]+", uris or ""):
        path = uri_to_path(uri)
        if path not in out:
            out.append(path)
    return out


AGY_PROMPT_MARK = "Você está retomando o trabalho de uma sessão anterior"  # início dos dois prompts do Auto-Run
DOSSIER_INLINE_MAX = 20000  # caracteres do dossiê dentro do prompt (a linha de comando do Windows aceita ~32 mil)
AGY_PROMPT_INLINE = ("Você está retomando o trabalho de uma sessão anterior. O dossiê de retomada está abaixo, entre as marcas "
                     "INÍCIO DO DOSSIÊ e FIM DO DOSSIÊ (cópia em: {path}). Depois de ler, responda em poucas linhas: (1) o que entendeu "
                     "do objetivo e do estado atual; (2) o que falta; (3) os próximos passos que propõe. Não altere nenhum arquivo e "
                     "não execute comandos; aguarde minha confirmação.\n\n=== INÍCIO DO DOSSIÊ ===\n{dossier}\n=== FIM DO DOSSIÊ ===")


def inline_dossier(text, path, limit=DOSSIER_INLINE_MAX):
    """Dossiê para ir dentro do prompt; se for grande, corta o meio e aponta o arquivo completo."""
    if len(text) <= limit:
        return text
    head, tail = int(limit * 0.7), int(limit * 0.3)
    return (text[:head] + f"\n\n[… dossiê cortado: {len(text) - head - tail} caracteres omitidos; arquivo completo em {path} …]\n\n"
            + text[-tail:])


def build_agy_args(agy, dossier_path, extra_dirs, mode="plan", timeout_s=AGY_TIMEOUT_S, model=None, dossier_text=None, project=None):
    """Lista de argumentos (sem shell). Nunca inclui --dangerously-skip-permissions.
    As flags de segurança vêm antes do prompt: se algo truncar a linha, o prompt se perde, nunca o `--mode`."""
    args = [agy, "--output-format", "json", "--mode", mode, "--print-timeout", f"{timeout_s}s"]
    if dossier_text is None:
        # O prompt manda ler o arquivo: a pasta do dossiê precisa ser acessível. Com o dossiê no prompt ela não serve,
        # e era a pasta que aparecia como workspace das retomadas, no lugar do projeto.
        args += ["--add-dir", os.path.dirname(dossier_path)]
    for d in extra_dirs:
        args += ["--add-dir", d]
    if project:
        args += ["--project", project]
    if model and model.strip():  # vazio = modelo padrão do agy
        args += ["--model", model.strip()]
    if dossier_text is not None:
        # O modo sem janela do agy nega read_file: o dossiê vai no prompt em vez de ser lido do disco.
        prompt = AGY_PROMPT_INLINE.format(path=dossier_path, dossier=inline_dossier(dossier_text, dossier_path))
    else:
        prompt = AGY_PROMPT.format(path=dossier_path)
    return args + ["--print", prompt]


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
    return (f"o agy é um script {os.path.splitext(args[0])[1]} (passa pelo cmd.exe), e o prompt com o dossiê tem caracteres "
            f"que o cmd.exe reinterpreta ({shown}). Defina AGY_EXE com o caminho de um agy.exe.")


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
    res = {'ok': False, 'conversation_id': '', 'response': '', 'error': '', 'quota': quota, 'reset': m.group(1).strip() if m else '',
           'duration': None, 'turns': None, 'usage': None}
    if isinstance(obj, dict):
        res['conversation_id'] = str(obj.get('conversation_id') or '')
        res['response'] = str(obj.get('response') or '')
        res['duration'] = obj['duration_seconds'] if isinstance(obj.get('duration_seconds'), (int, float)) else None
        res['turns'] = obj['num_turns'] if isinstance(obj.get('num_turns'), int) else None
        res['usage'] = obj['usage'] if isinstance(obj.get('usage'), dict) else None
        res['error'] = str(obj.get('error') or '')
        if not res['error'] and str(obj.get('status', '')).upper() == 'ERROR':
            res['error'] = "agy informou status ERROR sem mensagem"
        if not res['error'] and not res['conversation_id']:
            res['error'] = "resposta sem conversation_id"
        if not res['error'] and not res['response'].strip():
            # Visto em 26/10: status SUCCESS, resposta vazia e denied_actions=read_file (o modo sem janela não pede permissão).
            denied = [str(a.get('action') or a.get('display_name')) for a in obj.get('denied_actions') or [] if isinstance(a, dict)]
            res['error'] = "agy terminou sem resposta" + (f" (ações negadas no modo sem janela: {', '.join(denied)})" if denied else "")
    else:
        res['error'] = "saída sem JSON reconhecível: " + (blob.strip()[:200] or "(vazia)")
    if returncode not in (None, 0) and not res['error']:
        res['error'] = f"agy terminou com código {returncode}"
    res['ok'] = not res['error']
    return res


class AutoRunner:
    """Percorre as sessões aprovadas: gera o dossiê local e, se não for simulação, abre uma sessão nova com `agy --print`.
    Roda em thread de trabalho; fala com a tela só por `log` (callback). Sem Tk aqui."""

    def __init__(self, items, store, log_cb, agy=None, dry_run=True, mode="plan", timeout_s=AGY_TIMEOUT_S, max_failures=3, grace_s=60, model=None, dossier_dir=None, item_cb=None):
        self.items, self.store, self.log_cb = items, store, log_cb
        self.model = model
        self.dossier_dir = dossier_dir or HANDOFF_DIR  # onde os dossiês são gravados (o usuário escolhe na janela do Auto-Run)
        self.item_cb, self._finished, self._ctx = item_cb, set(), {}  # item_cb(kind, cid, info): 'start', 'done', 'skipped' por sessão
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

    def _item(self, kind, cid, **info):
        if self.item_cb:
            try:
                self.item_cb(kind, cid, info)
            except Exception:
                log.exception("item_cb falhou")

    def _record(self, cid, new_cid, dossier, status, detail='', **extra):
        """Grava a tentativa em `handoffs` e avisa a tela: um evento 'done' por sessão, com o que se sabe dela."""
        extra = {**self._ctx, **extra}
        self.store.add_handoff(cid, new_cid, dossier, status, detail, **extra)
        self._finished.add(cid)
        self._item('done', cid, state=status, new_cid=new_cid, dossier=dossier, error=detail if status == 'erro' else '', **extra)

    @staticmethod
    def _session_files():
        """UUIDs das sessões na pasta ativa (para achar a sessão que o agy cria mesmo quando falha)."""
        return {os.path.splitext(e.name)[0] for e in scandir_safe(ACTIVE_CONV_DIR) if e.is_file() and UUID_DB_RE.match(e.name)}

    @staticmethod
    def _started_by_autorun(cid):
        """True se a primeira fala da sessão é o prompt do Auto-Run (não uma conversa que o usuário abriu no meio)."""
        try:
            with open_ro(os.path.join(ACTIVE_CONV_DIR, cid + ".db")) as c:
                return AGY_PROMPT_MARK in first_user_text(c)
        except (sqlite3.Error, OSError, ValueError):
            return False

    @staticmethod
    def _target(it, fallback=None):
        """(--project, pastas para --add-dir, pasta de trabalho) da retomada: o projeto e as pastas da sessão original.
        O agy registra a pasta de trabalho como workspace; sem `cwd`, herdava a pasta de onde o app foi aberto."""
        project, pdirs = project_target(it.get('project_id', ''))
        dirs = list(dict.fromkeys(pdirs + workspace_dirs(it.get('workspace', ''))))[:3]
        return project, dirs, (dirs[0] if dirs else (fallback or HANDOFF_DIR))

    def _run_agy(self, args, cwd=None):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                     encoding="utf-8", errors="replace", creationflags=flags, cwd=cwd)
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
        os.makedirs(self.dossier_dir, exist_ok=True)
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
            self._ctx = {}
            self._item('start', cid)
            self.log_cb(f"[{i + 1}/{n}] {title}  ({cid[:8]})")
            dossier = os.path.join(self.dossier_dir, f"retomada_{cid[:8]}_{stamp}.md")
            try:
                export_session('dossier', it['fpath'], it['meta'], dossier)
            except Exception as e:
                log.exception("Dossiê falhou para %s", cid)
                self._record(cid, '', dossier, 'erro', f"dossiê: {e}")
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
            project, dirs, cwd = self._target(it, self.dossier_dir)
            proj_label = f"{it['meta'].get('project') or project} (--project)" if project else "CLI Project (sem --project)"
            self.log_cb(f"    pasta: {cwd} · projeto: " + (proj_label if project else "CLI Project (sem --project: a sessão original não tem projeto em config/projects)"))
            self._ctx = {'cwd': cwd, 'project': proj_label}
            if self.dry_run:
                self._record(cid, '', dossier, 'dossie', 'simulação: agy não foi chamado')
                summary['dossier'] += 1
                continue
            with open(dossier, encoding="utf-8") as fh:
                dossier_text = fh.read()
            args = build_agy_args(self.agy, dossier, dirs, self.mode, self.timeout_s, self.model, dossier_text, project)
            problem = cmd_shim_problem(args)
            if problem:
                self._record(cid, '', dossier, 'erro', problem)
                summary['failed'] += 1
                summary['skipped'] += n - i - 1
                summary['aborted'] = 'agy .cmd/.bat inseguro'
                self.log_cb(f"    ✖ não executado: {problem}")
                break
            before = self._session_files()
            try:
                out, err, why, code = self._run_agy(args, cwd)
            except OSError as e:
                self._record(cid, '', dossier, 'erro', f"não executou o agy: {e}")
                summary['failed'] += 1
                self.log_cb(f"    ✖ não foi possível executar o agy: {e}")
                summary['skipped'] += n - i - 1
                summary['aborted'] = 'agy não executou'
                break
            if why:
                self._record(cid, '', dossier, 'erro', why)
                summary['failed'] += 1
                self.log_cb(f"    ✖ {why}")
                if why == "cancelada":
                    summary['skipped'] += n - i - 1
                    summary['aborted'] = 'cancelado pelo usuário'
                    break
                failures += 1
            else:
                log.info("agy %s: código %s; stdout %s; stderr %s", cid[:8], code, redact(out[:4000]), redact(err[:2000]))
                res = parse_agy_output(out, err, code)
                new_cid = res['conversation_id']
                if res['ok']:
                    self._record(cid, new_cid, dossier, 'ok', res['response'][:300], model=self.model or '', cwd=cwd, project=proj_label,
                                           duration=res['duration'], turns=res['turns'], usage=res['usage'], response=res['response'])
                    summary['ok'] += 1
                    failures = 0
                    self.log_cb(f"    ✔ sessão nova: {new_cid or '(sem id)'}")
                    if res['response']:
                        self.log_cb("    resposta: " + " ".join(res['response'].split())[:300])
                    continue
                self._record(cid, new_cid, dossier, 'erro', res['error'])
                summary['failed'] += 1
                # O agy cria a sessão mesmo quando falha, às vezes sem informar o id: o que surgiu na pasta é dessa tentativa.
                for junk in ([new_cid] if new_cid else []) + [c for c in sorted(self._session_files() - before - {new_cid})
                                                              if self._started_by_autorun(c)]:
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
        for it in self.items:  # o que sobrou depois de uma interrupção
            if it['cid'] not in self._finished:
                self._item('skipped', it['cid'])
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
                with open(p_file, 'r', encoding='utf-8-sig') as f:  # aceita BOM (JSON regravado pelo PowerShell 5.1)
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

# Paletas do pacote visual 1.1 (Stitch: DESIGN.md "Obsidian Telemetry Aero" e as 8 skins), com cores sólidas: o Tk não faz gradiente nem transparência.
# Todas as combinações de texto foram checadas para contraste >= 4,5:1 (WCAG AA) em tests/test_theme.py.
_BASE = dict(radius=8, title_fonts=("Inter", "Segoe UI Semibold", "Segoe UI"))
THEMES = {
    "escuro": dict(name="Dark Alloy", bg="#07090e", panel="#0c0f17", panel2="#161b2c", border="#1e263d", fg="#e2e8f0", muted="#94a3b8", accent="#38bdf8", accent_fg="#04121f", accent_text="#38bdf8", success="#34d399", warning="#fbbf24", danger="#f43f5e", sel_bg="#0c3a57", sel_fg="#ffffff", header_bg="#0c0f17", header_fg="#e2e8f0",
        **_BASE),
    "claro": dict(name="Claro", bg="#f1f5f9", panel="#ffffff", panel2="#e9eef5", border="#cbd5e1", fg="#0f172a", muted="#475569", accent="#0369a1", accent_fg="#ffffff", accent_text="#0369a1", success="#047857", warning="#b45309", danger="#be123c", sel_bg="#e0f2fe", sel_fg="#0f172a", header_bg="#ffffff", header_fg="#0f172a",
        **_BASE),
    "milspec": dict(name="Mil-Spec", bg="#070a09", panel="#0d1311", panel2="#111916", border="#2a4536", fg="#e5e7eb", muted="#8aa597", accent="#22c55e", accent_fg="#04140a", accent_text="#4ade80", success="#4ade80", warning="#f59e0b", danger="#f87171", sel_bg="#243b31", sel_fg="#4ade80", header_bg="#0d1311", header_fg="#4ade80",
        radius=6, title_fonts=("JetBrains Mono", "Bahnschrift", "Consolas", "Segoe UI")),
    "cyber": dict(name="Cyber Synthwave", bg="#070814", panel="#0d0f22", panel2="#12142d", border="#1e2348", fg="#e6fbff", muted="#8e97b8", accent="#00f3ff", accent_fg="#001418", accent_text="#00f3ff", success="#4ade80", warning="#fbbf24", danger="#ff3d8b", sel_bg="#2a0a3d", sel_fg="#00f3ff", header_bg="#0d0f22", header_fg="#00f3ff",
        radius=4, title_fonts=("JetBrains Mono", "Bahnschrift", "Consolas", "Segoe UI")),
    "vidro": dict(name="Vidro Aero", bg="#030b18", panel="#06132a", panel2="#0a1d3d", border="#1d4d6e", fg="#e0f2fe", muted="#8fbfdf", accent="#38bdf8", accent_fg="#04121f", accent_text="#38bdf8", success="#34d399", warning="#fbbf24", danger="#fb7185", sel_bg="#0f3d66", sel_fg="#ffffff", header_bg="#030b18", header_fg="#e0f2fe",
        radius=10, title_fonts=("Inter", "Segoe UI Semibold", "Segoe UI")),
    "brutal": dict(name="Brutalista", bg="#000000", panel="#0b0b0b", panel2="#141414", border="#2a2a2a", fg="#ffffff", muted="#999999", accent="#facc15", accent_fg="#000000", accent_text="#facc15", success="#4ade80", warning="#facc15", danger="#f87171", sel_bg="#262208", sel_fg="#facc15", header_bg="#facc15", header_fg="#000000",
        radius=0, title_fonts=("Inter", "Bahnschrift", "Arial Black", "Segoe UI")),
    "obsidiana": dict(name="Obsidiana", bg="#07050d", panel="#0b0816", panel2="#151027", border="#34295c", fg="#f3ecff", muted="#a99dbd", accent="#c084fc", accent_fg="#12081f", accent_text="#c084fc", success="#34d399", warning="#fbbf24", danger="#f43f5e", sel_bg="#2b1646", sel_fg="#f3ecff", header_bg="#07050d", header_fg="#f3ecff",
        radius=12, title_fonts=("Inter", "Segoe UI Semibold", "Segoe UI")),
    "mecha": dict(name="Mecha", bg="#080a0e", panel="#0d1117", panel2="#121620", border="#323d53", fg="#e2e8f0", muted="#94a3b8", accent="#f97316", accent_fg="#1a0802", accent_text="#ff8c38", success="#10b981", warning="#f59e0b", danger="#ef4444", sel_bg="#33200f", sel_fg="#fdba74", header_bg="#0d1117", header_fg="#f97316",
        radius=6, title_fonts=("JetBrains Mono", "Bahnschrift", "Consolas", "Segoe UI")),
}
THEME_ORDER = ["escuro", "claro", "milspec", "cyber", "vidro", "brutal", "obsidiana", "mecha"]

# nome -> (Segoe MDL2 Assets, alternativa Unicode). Se os ícones do Windows aparecerem errados, use Tema > Ícones > Símbolos Unicode.
ICONS = {
    "refresh": ("\uE72C", "↻"), "search": ("\uE721", "⌕"), "clear": ("\uE711", "✕"), "approve": ("\uE73E", "✔"),
    "archive": ("\uE7B8", "▣"), "pending": ("\uE7A7", "↶"), "export": ("\uE74E", "↧"), "dossier": ("\uE768", "▶"),
    "autorun": ("\uE945", "⚡"), "theme": ("\uE790", "◐"), "warn": ("\uE7BA", "⚠"), "limits": ("\uE713", "⚙"), "copy": ("\uE8C8", "⧉"), "folder": ("\uE838", "▭"),
    "about": ("\uE946", "ⓘ"),
}

# Conjuntos com a fonte empacotada em fonts/ (registrada só para este processo, no Windows). modo -> (família, arquivo, glifos).
# Font Awesome Free 6.7.2 Solid (SIL OFL 1.1), Bootstrap Icons 1.11.3 (MIT), Material Icons 4.0.0 (Apache 2.0). Licenças em fonts/.
ICON_FONTS = {
    "fa": ("Font Awesome 6 Free Solid", "fa-solid-900.ttf", {
        "refresh": "\uf2f1", "search": "\uf002", "clear": "\uf00d", "approve": "\uf00c", "archive": "\uf187", "pending": "\uf2ea",
        "export": "\uf56e", "dossier": "\uf04b", "autorun": "\uf0e7", "theme": "\uf53f", "warn": "\uf071", "limits": "\uf1de",
        "copy": "\uf0c5", "folder": "\uf07c", "about": "\uf05a"}),
    "bootstrap": ("bootstrap-icons", "bootstrap-icons.ttf", {
        "refresh": "\uf116", "search": "\uf52a", "clear": "\uf659", "approve": "\uf633", "archive": "\uf10d", "pending": "\uf117",
        "export": "\uf1c6", "dossier": "\uf4f4", "autorun": "\uf46e", "theme": "\uf4b1", "warn": "\uf33a", "limits": "\uf56b",
        "copy": "\uf759", "folder": "\uf3d8", "about": "\uf431"}),
    "material": ("Material Icons", "MaterialIcons-Regular.ttf", {
        "refresh": "\ue5d5", "search": "\ue8b6", "clear": "\ue5cd", "approve": "\ue5ca", "archive": "\ue149", "pending": "\ue166",
        "export": "\ue171", "dossier": "\ue037", "autorun": "\uea0b", "theme": "\ue40a", "warn": "\ue002", "limits": "\ue429",
        "copy": "\ue14d", "folder": "\ue2c8", "about": "\ue88e"}),
}


def font_dir():
    """Pasta fonts/: ao lado do código ou, no .exe, na pasta temporária do PyInstaller."""
    import sys
    return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "fonts")


def register_fonts(folder=None):
    """Registra as fontes de fonts/ só para este processo (Windows, FR_PRIVATE): nada é instalado no sistema.
    Devolve os arquivos registrados. Fora do Windows, ou sem a pasta, não faz nada."""
    folder = folder or font_dir()
    if os.name != "nt" or not os.path.isdir(folder):
        return []
    import ctypes
    done = []
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith((".ttf", ".otf")):
            if ctypes.windll.gdi32.AddFontResourceExW(os.path.join(folder, name), 0x10, 0):  # 0x10 = FR_PRIVATE
                done.append(name)
            else:
                log.warning("Fonte não registrada: %s", name)
    return done


def icon_glyph(mode, name, families):
    """Glifo do ícone `name` no modo `mode`. Sem a fonte do conjunto (fora do Windows, por exemplo): símbolo Unicode."""
    if mode == "none" or name not in ICONS:
        return ""
    if mode == "mdl2":
        return ICONS[name][0]
    if mode in ICON_FONTS and ICON_FONTS[mode][0] in families:
        return ICON_FONTS[mode][2][name]
    return ICONS[name][1]


def asset_dir():
    """Pasta assets/: ao lado do código ou, no .exe, na pasta temporária do PyInstaller."""
    import sys
    return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "assets")


def set_app_icon(win):
    """Ícone do app nas janelas e na barra de tarefas (PNG de 256, 64 e 32 px). Sem os arquivos, fica o ícone padrão do Tk."""
    try:
        imgs = [tk.PhotoImage(master=win, file=os.path.join(asset_dir(), f"app-{n}.png")) for n in (256, 64, 32)]
        win.iconphoto(True, *imgs)
        win._app_icons = imgs  # o Tk não guarda a referência
    except (tk.TclError, OSError) as e:
        log.warning("Ícone do app não carregado: %s", e)


def run_key_values():
    """(nome, comando) das entradas da chave Run do usuário (Windows). None fora do Windows; [] se a chave não abre."""
    if os.name != "nt":
        return None
    try:
        import winreg
        out = []
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            for i in range(winreg.QueryInfoKey(key)[1]):
                name, data, _kind = winreg.EnumValue(key, i)
                out.append((name, str(data)))
        return out
    except OSError:
        return []


def remote_control_registered(values=None):
    """O daemon do remote control inicia no login? Procura 'remote-control' na chave Run (o `agy remote-control status` não enxerga
    esse registro). True/False; None fora do Windows. Mostra o registro, não se o daemon está online."""
    vals = run_key_values() if values is None else values
    if vals is None:
        return None
    return any("remote-control" in f"{n} {d}".lower() for n, d in vals)


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
        "Fontes: Inter e JetBrains Mono (SIL OFL 1.1)",
        "Ícones: Font Awesome Free (SIL OFL 1.1), Bootstrap Icons (MIT), Material Icons (Apache 2.0); licenças em fonts/ no repositório",
    ])


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(d):
    """Grava em settings.json.tmp e troca no fim: queda ou erro no meio não estragam o arquivo anterior."""
    tmp = SETTINGS_FILE + ".tmp"
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_FILE)
    except (OSError, TypeError, ValueError) as e:
        log.warning("Não foi possível salvar as preferências: %s", e)
        try:
            os.remove(tmp)
        except OSError:
            pass


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


def tooltip_pos(win, area, ax, ay, aw, ah, w, h, gap=6):
    """Posição (x, y) de uma dica w×h sob o widget (ax, ay, aw, ah): alinhada à esquerda dele, sem passar da borda direita
    da janela `win` nem da área útil `area` do monitor (ambas (x, y, largura, altura)). Sem espaço embaixo, fica acima."""
    left, right = max(win[0], area[0]), min(win[0] + win[2], area[0] + area[2])
    bottom = min(win[1] + win[3], area[1] + area[3])
    x = max(min(ax, right - w), left)
    y = ay + ah + gap
    if y + h > bottom:
        y = max(area[1], ay - h - gap)
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


def strong_bg(color, ink="#ffffff", target=4.6):
    """`color` escurecida o mínimo para o texto `ink` passar no contraste WCAG AA (4,5:1)."""
    for i in range(21):
        bg = blend(color, "#000000", i * 0.05)
        if contrast(ink, bg) >= target:
            return bg
    return "#000000"


def banner_colors(t, level):
    """Cores da faixa de alerta de contexto. 2 = crítico: vermelho do tema, forte, com texto claro.
    1 = atenção: âmbar suave, texto normal. Chaves: bg, fg, icon, stripe (borda e barra à esquerda)."""
    if level == 2:
        bg = strong_bg(t['danger'])
        return {'bg': bg, 'fg': "#ffffff", 'icon': "#ffffff", 'stripe': t['danger'] if bg != t['danger'] else blend(bg, "#000000", 0.35)}
    return {'bg': blend(t['panel'], t['warning'], 0.16), 'fg': t['fg'], 'icon': t['warning'], 'stripe': t['warning']}


def tab_colors(t):
    """Cores das abas do cabeçalho: texto das inativas (mais fraco que o da marcada), barra da marcada e fundo do selo de contagem."""
    bar = t['accent_text'] if contrast(t['accent_text'], t['header_bg']) >= 3 else t['header_fg']
    dim = t['header_fg']
    for i in range(12, -1, -1):  # o texto mais fraco que ainda passa em 4,6:1 (no Mecha, laranja sobre quase preto, fica mais forte)
        dim = blend(t['header_fg'], t['header_bg'], i * 0.03)
        if contrast(dim, t['header_bg']) >= 4.6:
            break
    return {'dim': dim, 'bar': bar, 'badge': blend(t['header_bg'], t['header_fg'], 0.18)}


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
    def __init__(self, widget, app, text_fn, delay=450, level_fn=None):
        self.w, self.app, self.fn, self.delay = widget, app, text_fn, delay
        self.tip = self.job = None
        self.level_fn = level_fn  # nível de alerta da dica (0, 1, 2); None = dica comum
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")
        widget.bind("<ButtonPress>", self._leave, add="+")
        widget.bind("<FocusIn>", self._enter, add="+")   # teclado: a dica (e o motivo de um botão desabilitado) aparece no Tab
        widget.bind("<FocusOut>", self._leave, add="+")

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
        w = self.w
        level = self.level_fn() if self.level_fn else 0
        self.tip = show_tip(w, self.app, text, w.winfo_rootx(), w.winfo_rooty(), w.winfo_width(), w.winfo_height(), level)


ALERT_TITLE = {1: "ATENÇÃO", 2: "CRÍTICO"}


def alert_glyph(app):
    """Ícone de alerta no modo de ícones atual: Warning do Segoe MDL2, ⚠ Unicode ou ‼ sem ícones. (texto, fonte)."""
    if app.icon_mode == "none":
        return "‼", app.f_title
    return icon_glyph(app.icon_mode, "warn", app.families), app.f_banner_icon


def show_tip(owner, app, text, ax, ay, aw, ah, level=0):
    """Mostra uma dica sob o retângulo (ax, ay, aw, ah) da tela, dentro da janela de `owner` e do monitor. Devolve o Toplevel.
    `level` 1 ou 2 (contexto em atenção ou crítico) vira janela de alerta: cores da faixa, ícone grande e título."""
    t = app.t
    tip = tk.Toplevel(owner)
    tip.wm_overrideredirect(True)
    tip.withdraw()  # mede antes de mostrar: perto da borda direita a dica é puxada para dentro da janela
    if level in ALERT_TITLE:
        c = banner_colors(t, level)
        box = tk.Frame(tip, bg=c['bg'], highlightthickness=1, highlightbackground=c['stripe'])
        box.pack()
        tk.Frame(box, bg=c['stripe'], width=app.px(5)).pack(side=tk.LEFT, fill=tk.Y)
        glyph, font = alert_glyph(app)
        tk.Label(box, text=glyph, font=font, bg=c['bg'], fg=c['icon']).pack(side=tk.LEFT, anchor="n", padx=(app.px(10), app.px(8)), pady=app.px(6))
        body = tk.Frame(box, bg=c['bg'])
        body.pack(side=tk.LEFT, padx=(0, app.px(12)), pady=app.px(6))
        tk.Label(body, text=ALERT_TITLE[level], font=app.f_bold, bg=c['bg'], fg=c['fg'], anchor="w").pack(fill=tk.X)
        tk.Label(body, text=text, font=app.f_small, bg=c['bg'], fg=c['fg'], justify=tk.LEFT, anchor="w",
                 wraplength=app.px(340)).pack(fill=tk.X)
    else:
        tk.Label(tip, text=text, bg=t['panel2'], fg=t['fg'], font=app.f_small, padx=9, pady=5, justify=tk.LEFT,
                 highlightthickness=1, highlightbackground=t['border'], wraplength=app.px(340)).pack()
    tip.update_idletasks()
    top = owner.winfo_toplevel()
    win = (top.winfo_rootx(), top.winfo_rooty(), top.winfo_width(), top.winfo_height())
    x, y = tooltip_pos(win, work_area_at(owner, ax + aw // 2, ay + ah // 2), ax, ay, aw, ah, tip.winfo_reqwidth(), tip.winfo_reqheight())
    tip.wm_geometry(f"+{x}+{y}")
    tip.deiconify()
    return tip


class CellTooltip:
    """Dica por célula da tabela: ao parar o mouse sobre uma célula com alerta (contexto, falhas, retomada, título longo)."""

    def __init__(self, tree, app, text_fn, delay=450, level_fn=None):
        self.tree, self.app, self.fn, self.delay, self.level_fn = tree, app, text_fn, delay, level_fn
        self.key = self.tip = self.job = None
        self.text = ""
        tree.bind("<Motion>", self.on_motion, add="+")
        tree.bind("<Leave>", lambda e: self.hide(), add="+")
        tree.bind("<ButtonPress>", lambda e: self.hide(), add="+")

    def edges(self):
        """[(coluna, x_esquerda, x_direita)] na tela da tabela, na ordem exibida, já descontada a rolagem horizontal.
        Calculado pelas larguras: com displaycolumns, o identify_column do Tk 8.6 numera as colunas de outro jeito que o bbox."""
        disp = list(self.tree["displaycolumns"])
        if disp == ["#all"]:
            disp = list(self.tree["columns"])
        cols = ["#0"] + disp
        widths = [int(self.tree.column(c, "width")) for c in cols]
        offset = round(self.tree.xview()[0] * sum(widths))
        out, x = [], -offset
        for c, w in zip(cols, widths):
            out.append((c, x, x + w))
            x += w
        return out

    def column_at(self, x):
        return next((c for c, l, r in self.edges() if l <= x < r), "")

    def on_motion(self, e):
        iid = self.tree.identify_row(e.y)
        col = self.column_at(e.x) if iid else ""
        key = (iid, col) if iid and col else None
        if key == self.key:
            return
        self.hide()
        self.key = key
        if key:
            self.text = self.fn(iid, col)
            if self.text:
                self.job = self.tree.after(self.delay, self.show_now)

    def show_now(self):
        self.job = None
        if not self.key or not self.text or not self.tree.exists(self.key[0]):
            return
        box = self.tree.bbox(*self.key)
        if not box:
            return
        x, y, w, h = box
        level = self.level_fn(*self.key) if self.level_fn else 0
        self.tip = show_tip(self.tree, self.app, self.text, self.tree.winfo_rootx() + x, self.tree.winfo_rooty() + y, w, h, level)

    def hide(self):
        if self.job:
            self.tree.after_cancel(self.job)
            self.job = None
        if self.tip:
            self.tip.destroy()
            self.tip = None
        self.key = None


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
        self.tooltip = Tooltip(self, app, self.tooltip_text)
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
        return icon_glyph(self.app.icon_mode, self.icon, self.app.families)

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
            shown = (icon_glyph(self.app.icon_mode, "approve", self.app.families) or ICONS["approve"][1]) if self.ok_flash else g
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


class SideItem(tk.Frame):
    """Linha clicável da barra lateral: glifo, nome e contagem. A marcada (`on`) usa as cores de seleção do tema."""

    def __init__(self, master, app, text, glyph, token, command):
        super().__init__(master, padx=app.px(10), pady=app.px(4), cursor="hand2", takefocus=1, highlightthickness=1)
        self.app, self.token, self.command, self.on = app, token, command, False
        self.glyph = tk.Label(self, text=glyph, font=app.f_small, width=2)
        self.name = tk.Label(self, text=text, font=app.f_ui, anchor="w")
        self.count = tk.Label(self, font=app.f_small, padx=app.px(6))
        self.glyph.pack(side=tk.LEFT)
        self.name.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.count.pack(side=tk.RIGHT)
        for w in (self, self.glyph, self.name, self.count):
            w.bind("<Button-1>", lambda e: self.command())
        for seq in ("<Return>", "<space>"):
            self.bind(seq, lambda e: self.command())
        self.repaint()

    def update_item(self, count=None, on=None):
        if count is not None:
            self.count.configure(text=str(count))
        if on is not None:
            self.on = on
        self.repaint()

    def repaint(self):
        t = self.app.t
        bg, fg = (t['sel_bg'], t['sel_fg']) if self.on else (t['panel'], t['fg'])
        self.configure(bg=bg, highlightbackground=bg, highlightcolor=t['accent'])
        self.glyph.configure(bg=bg, fg=fg if self.on else t[self.token])
        self.name.configure(bg=bg, fg=fg)
        self.count.configure(bg=t['panel2'], fg=t['muted'])


class Tab(tk.Frame):
    """Aba do cabeçalho: texto, selo de contagem opcional e uma barra embaixo da marcada. Clicar (ou Enter ou Espaço) aplica o filtro."""

    def __init__(self, master, app, text, command):
        super().__init__(master, takefocus=1, cursor="hand2", highlightthickness=1)
        self.app, self.command, self.on, self.hover, self.count = app, command, False, False, 0
        self.bar = tk.Frame(self, height=app.px(2))
        self.bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.label = tk.Label(self, text=text, font=app.f_ui, padx=app.px(10), pady=app.px(6))
        self.label.pack(side=tk.LEFT)
        self.badge = tk.Label(self, font=app.f_small, padx=app.px(6))
        for w in (self, self.label, self.badge):
            w.bind("<Button-1>", lambda e: self.command())
            w.bind("<Enter>", lambda e: self._hover(True), add="+")
            w.bind("<Leave>", lambda e: self._hover(False), add="+")
        for seq in ("<Return>", "<space>"):
            self.bind(seq, lambda e: self.command())
        self.repaint()

    def configure(self, cnf=None, **kw):  # `text` vai para o rótulo
        if "text" in kw:
            self.label.configure(text=kw.pop("text"))
        return super().configure(cnf, **kw) if (cnf or kw) else None
    config = configure

    def cget(self, key):
        return self.label.cget("text") if key == "text" else super().cget(key)

    def _hover(self, flag):
        self.hover = flag
        self.repaint()

    def set_count(self, n):
        self.count = n
        if n:
            self.badge.configure(text=str(n))
            if not self.badge.winfo_manager():
                self.badge.pack(side=tk.LEFT, padx=(0, self.app.px(8)))
        else:
            self.badge.pack_forget()

    def repaint(self):
        t = self.app.t
        c = tab_colors(t)
        self.configure(bg=t['header_bg'], highlightbackground=t['header_bg'], highlightcolor=t['accent'])
        self.label.configure(bg=t['header_bg'], fg=t['header_fg'] if (self.on or self.hover) else c['dim'])
        self.badge.configure(bg=c['badge'], fg=t['header_fg'])
        self.bar.configure(bg=c['bar'] if self.on else t['header_bg'])


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
        self.resume_ms = 4000  # depois que o mouse/foco sai, ainda fica este tempo
        self.job = self.after(ttl, self.dismiss)
        # Com o mouse ou o foco em cima (para clicar em Desfazer), o relógio para.
        self.bind("<Enter>", lambda e: self.pause(), add="+")
        self.bind("<Leave>", lambda e: self.after_idle(self.resume_if_away), add="+")
        for b in self.buttons + [close]:
            b.bind("<FocusIn>", lambda e: self.pause(), add="+")
            b.bind("<FocusOut>", lambda e: self.after_idle(self.resume_if_away), add="+")

    def pause(self):
        if self.job:
            self.after_cancel(self.job)
            self.job = None

    def resume(self):
        if not self.job and self.winfo_exists():
            self.job = self.after(self.resume_ms, self.dismiss)

    def resume_if_away(self):
        try:
            x, y = self.winfo_pointerxy()
            inside = self.winfo_containing(x, y)
            focus = self.focus_get()
        except (tk.TclError, KeyError):
            inside = focus = None
        if not self._mine(inside) and not self._mine(focus):
            self.resume()

    def _mine(self, w):
        """True se `w` é esta notificação ou um widget dentro dela (".!toast" não pode casar com ".!toast2")."""
        if w is None:
            return False
        name, me = str(w), str(self)
        return name == me or name.startswith(me + ".")

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

    DENSITIES = (("compact", "Compacta (1 linha por sessão)"), ("comfortable", "Confortável (2 linhas por sessão)"))
    ICON_MODES = (("mdl2", "Ícones do Windows (Segoe MDL2)"), ("fa", "Font Awesome"), ("bootstrap", "Bootstrap Icons"),
                  ("material", "Material Icons"), ("symbol", "Símbolos Unicode"), ("none", "Sem ícones"))

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
        tk.Frame(body, bg=t['border'], height=1).pack(fill=tk.X, pady=app.px(5), padx=app.px(4))
        self.heading(body, "Tabela")
        for mode, label in self.DENSITIES:
            self.add_row(body, label, mode == app.density, lambda m=mode: app.set_density(m), radio=True)
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


def receipt_fields(rec, src=None):
    """(campos, resposta, nota) do recibo de uma retomada. Campos que a versão da época não gravava aparecem como 'não registrado'."""
    missing = "não registrado (retomada de versão anterior à 1.2)"
    try:
        usage = json.loads(rec.get('usage') or "{}")
    except (TypeError, ValueError):
        usage = {}
    toks = usage_text(usage)
    dossier = rec.get('dossier_path') or ""
    new_format = rec.get('model') is not None
    d = rec.get('duration')
    fields = [
        ("Retomada em", rec.get('at') or "-"),
        ("Estado", "concluída" if rec.get('status') == 'ok' else str(rec.get('status'))),
        ("Sessão original", f"{src['title']} ({rec['src_cid']})" if src else rec['src_cid']),
        ("Projeto original", (src or {}).get('project') or "-"),
        ("Sessão nova", rec.get('new_cid') or "-"),
        ("Modelo", (rec['model'] or "padrão do agy") if new_format else missing),
        ("Modo do agy", "plan (somente leitura)" if new_format else missing),
        ("Pasta de trabalho", rec.get('cwd') or missing),
        ("Projeto na retomada", rec.get('project') or missing),
        ("Duração", f"{d:.1f} s".replace(".", ",") if isinstance(d, (int, float)) else missing),
        ("Turnos", str(rec['turns']) if rec.get('turns') is not None else missing),
        ("Tokens", toks or missing),
        ("Dossiê", (dossier + ("" if os.path.isfile(dossier) else "  (arquivo não encontrado)")) if dossier else "-"),
    ]
    response, note = rec.get('response') or "", ""
    if not response:
        response = rec.get('detail') or ""
        note = "Trecho de até 300 caracteres: as retomadas de versões anteriores à 1.2 guardam só o início da resposta." if response else ""
    return fields, redact(response), note


def receipt_markdown(rec, src=None):
    """Recibo de retomada em Markdown (o texto da janela e do arquivo salvo). A resposta passa pela máscara de segredos."""
    fields, response, note = receipt_fields(rec, src)
    out = ["# Recibo de retomada", ""] + [f"- **{k}:** {v}" for k, v in fields] + ["", "## Resposta do agy", ""]
    if note:
        out += [f"_{note}_", ""]
    out.append(response or "(sem resposta registrada)")
    return "\n".join(out) + "\n"


class ReceiptDialog(tk.Toplevel):
    """Recibo de retomada: o que o Auto-Run fez com uma sessão (sessão nova, modelo, pasta, projeto, dossiê, tempo, tokens, resposta).
    Dá para selecionar e copiar qualquer trecho, copiar tudo e salvar em Markdown."""

    def __init__(self, app, rec, src=None):
        super().__init__(app)
        self.app, self.rec, self.md = app, rec, receipt_markdown(rec, src)
        t = app.t
        self.title("Recibo de retomada")
        self.transient(app)
        self.configure(bg=t['panel'], padx=app.px(14), pady=app.px(12))
        tk.Label(self, text="Recibo de retomada", font=app.f_title, bg=t['panel'], fg=t['fg'], anchor="w").pack(fill=tk.X)
        tk.Label(self, text="O que o Auto-Run fez com esta sessão. Selecione e copie qualquer trecho, ou salve o recibo em arquivo.",
                 font=app.f_small, bg=t['panel'], fg=t['muted'], anchor="w", justify=tk.LEFT, wraplength=app.px(680)).pack(fill=tk.X, pady=(2, 8))
        indent = app.px(150)
        self.text = tk.Text(self, wrap=tk.WORD, font=app.f_ui, bg=t['panel2'], fg=t['fg'], relief=tk.FLAT, highlightthickness=1,
                            highlightbackground=t['border'], highlightcolor=t['accent'], padx=app.px(10), pady=app.px(8), width=84, height=20,
                            tabs=(indent,), selectbackground=t['sel_bg'], selectforeground=t['sel_fg'], insertbackground=t['fg'])
        self.text.tag_configure("k", font=app.f_bold, foreground=t['muted'])
        self.text.tag_configure("row", lmargin2=indent)  # linha quebrada alinha com o valor
        self.text.tag_configure("h", font=app.f_bold, foreground=t['accent_text'], spacing1=app.px(10), spacing3=app.px(2))
        fields, response, note = receipt_fields(rec, src)
        for label, value in fields:
            self.text.insert(tk.END, label, ("k", "row"))
            self.text.insert(tk.END, f"\t{value}\n", ("row",))
        self.text.insert(tk.END, "Resposta do agy\n", "h")
        if note:
            self.text.insert(tk.END, note + "\n", "k")
        self.text.insert(tk.END, (response or "(sem resposta registrada)") + "\n")
        self.text.configure(state=tk.NORMAL)
        self.text.bind("<Key>", lambda e: None if (e.state & 0x4 and e.keysym.lower() in ("c", "a")) else "break")  # só leitura, mas copia
        self.text.pack(fill=tk.BOTH, expand=True)
        row = tk.Frame(self, bg=t['panel'])
        row.pack(fill=tk.X, pady=(app.px(10), 0))
        IconButton(row, app, "copy", "Copiar", self.copy, bg_token="panel").pack(side=tk.LEFT)
        IconButton(row, app, "export", "Salvar recibo…", self.save, bg_token="panel", kind="primary").pack(side=tk.LEFT, padx=(app.px(8), 0))
        IconButton(row, app, "folder", "Abrir pasta do dossiê", self.open_dossier, bg_token="panel").pack(side=tk.LEFT, padx=(app.px(8), 0))
        IconButton(row, app, "", "Fechar", self.destroy, bg_token="panel").pack(side=tk.RIGHT)
        self.bind("<Escape>", lambda e: self.destroy())
        place_over(self, app)
        self.lift()
        self.focus_force()

    def copy(self):
        self.app.clipboard_clear()
        self.app.clipboard_append(self.md)
        self.app.notify("ok", "Recibo copiado.")

    def save(self):
        os.makedirs(EXPORT_DIR, exist_ok=True)
        name = f"AntigravityGate_recibo_{self.rec['src_cid'][:8]}_{(self.rec.get('new_cid') or 'sem-id')[:8]}.md"
        out = filedialog.asksaveasfilename(parent=self, title="Salvar recibo de retomada", initialdir=EXPORT_DIR, initialfile=name,
                                           defaultextension=".md", filetypes=[("Markdown", "*.md"), ("Texto", "*.txt"), ("Todos os arquivos", "*.*")])
        if not out:
            return
        try:
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(self.md)
        except OSError as e:
            messagebox.showerror("Recibo", f"Não foi possível salvar o recibo: {e}", parent=self)
            return
        self.app.notify("ok", f"Recibo salvo: {out}")

    def open_dossier(self):
        d = self.rec.get('dossier_path') or ""
        if d and os.path.isdir(os.path.dirname(d)):
            self.app.open_path(os.path.dirname(d))
        else:
            messagebox.showinfo("Recibo", "A pasta do dossiê não existe mais neste computador.", parent=self)


def usage_text(usage):
    """Tokens do agy em texto: 'entrada 1.500, saída 20, total 1.520' (só o que veio)."""
    usage = usage if isinstance(usage, dict) else {}
    names = (("input_tokens", "entrada"), ("output_tokens", "saída"), ("thinking_tokens", "raciocínio"), ("cache_read_tokens", "cache"), ("total_tokens", "total"))
    return ", ".join(f"{label} {usage[k]:,}".replace(",", ".") for k, label in names if isinstance(usage.get(k), int))


class AutoRunWindow(tk.Toplevel):
    """Janela única do Auto-Run, em três etapas: 1 Preparar (escolher as sessões e as opções), 2 Executando (cada sessão com o seu estado;
    clicar numa linha mostra o detalhe) e 3 Resumo (contagens, detalhe, recibo e relatório). Só existe uma: iniciar outro lote a reaproveita."""

    STEPS = (("prepare", "1  Preparar"), ("run", "2  Executando"), ("done", "3  Resumo"))
    INTRO = {
        "prepare": "Para cada sessão marcada, o app gera um dossiê de retomada e abre uma sessão NOVA no agy; a original não é alterada. "
                   "Rodam uma de cada vez. Clique numa sessão para ver onde a nova será criada.",
        "run": "Em andamento. Clique numa sessão para acompanhar o que ela está fazendo. \"Cancelar lote\" encerra o agy em curso e pula as demais.",
        "done": "Lote concluído. Clique numa sessão para ver o detalhe; duplo clique abre o recibo. Salve o relatório do lote em arquivo se quiser guardá-lo.",
    }
    STATE_TEXT = {"ready": "pronta", "redo": "refazer", "done_off": "já retomada", "off": "não marcada", "wait": "aguardando", "run": "rodando…",
                  "ok": "✔ retomada", "dossie": "▤ dossiê gerado", "erro": "✖ falhou", "skipped": "» não executada"}
    STATE_TAG = {"ready": "wait", "redo": "wait", "done_off": "muted", "off": "muted", "wait": "wait", "run": "run", "ok": "ok", "dossie": "ok",
                 "erro": "erro", "skipped": "muted"}

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        t = self.t = app.t
        self.title("Auto-Run — preparar")
        self.transient(app)
        self.configure(bg=t['panel'], padx=app.px(14), pady=app.px(10))
        self.step, self.items, self.by_cid, self.checks, self.states, self.info, self.lines = "prepare", [], {}, {}, {}, {}, {}
        self.done_ids, self.current, self.summary, self.result = set(), None, None, None
        self.dry_run, self.model_used, self.dossier_used = True, "", HANDOFF_DIR
        self.decision = tk.StringVar(master=self, value="")
        self.dry, self.redo = tk.BooleanVar(master=self, value=True), tk.BooleanVar(master=self, value=False)
        self.model_var = tk.StringVar(master=self, value=str(app.settings.get("agy_model") or ""))
        self.dir_var = tk.StringVar(master=self, value=str(app.settings.get("dossier_dir") or HANDOFF_DIR))
        self.build()
        self.protocol("WM_DELETE_WINDOW", lambda: app.close_autorun(self))
        self.bind("<Escape>", lambda e: app.close_autorun(self) if self.step != "run" else None)
        place_over(self, app, size=(app.px(980), app.px(680)))
        self.minsize(app.px(760), app.px(520))
        self.lift()
        self.focus_force()

    def build(self):
        app, t = self.app, self.t
        lab = lambda parent, text, fg='fg', font=None, **kw: tk.Label(parent, text=text, bg=t['panel'], fg=t[fg], font=font or app.f_ui, justify=tk.LEFT, anchor="w", **kw)
        bar = tk.Frame(self, bg=t['panel'])
        bar.pack(fill=tk.X)
        self.step_labels = {}
        for i, (key, text) in enumerate(self.STEPS):
            if i:
                lab(bar, "›", 'muted').pack(side=tk.LEFT, padx=app.px(6))
            self.step_labels[key] = tk.Label(bar, text=text, font=app.f_btn, padx=app.px(12), pady=app.px(4), highlightthickness=1)
            self.step_labels[key].pack(side=tk.LEFT)
        self.intro = lab(self, "", 'muted', app.f_small, wraplength=app.px(900))
        self.intro.pack(fill=tk.X, pady=(app.px(8), app.px(8)))
        self.bind("<Configure>", lambda e: self.intro.configure(wraplength=max(app.px(300), self.winfo_width() - app.px(48))) if e.widget is self else None)
        # rodapé e registro primeiro: reservam o fundo da janela; o corpo ocupa o resto
        self.foot = tk.Frame(self, bg=t['panel'])
        self.foot.pack(side=tk.BOTTOM, fill=tk.X, pady=(app.px(10), 0))
        self.status = lab(self.foot, "", 'muted', app.f_small)
        self.status.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.primary = IconButton(self.foot, app, "autorun", "Iniciar", self.on_primary, kind="primary", bg_token="panel")
        self.primary.pack(side=tk.RIGHT)
        self.secondary = IconButton(self.foot, app, "", "Cancelar", self.on_secondary, bg_token="panel")
        self.log_toggle = lab(self, "▸  Registro completo (para suporte)", 'muted', app.f_small, cursor="hand2")
        self.log_toggle.pack(side=tk.BOTTOM, fill=tk.X, pady=(app.px(8), 0))
        self.log_toggle.bind("<Button-1>", lambda e: self.toggle_log())
        mono = next((f for f in ("JetBrains Mono", "Consolas", "DejaVu Sans Mono") if f in app.families), "TkFixedFont")
        self.log = tk.Text(self, wrap=tk.WORD, state=tk.DISABLED, font=(mono, 9), bg=t['panel'], fg=t['fg'], insertbackground=t['fg'],
                           selectbackground=t['sel_bg'], selectforeground=t['sel_fg'], relief=tk.FLAT, highlightthickness=1,
                           highlightbackground=t['border'], highlightcolor=t['border'], padx=app.px(8), pady=app.px(6), height=7)
        # opções (só na etapa Preparar)
        self.opts = tk.Frame(self, bg=t['panel'])

        def choice(widget, **kw):
            return widget(self.opts, bg=t['panel'], fg=t['fg'], selectcolor=t['panel2'], activebackground=t['panel'], activeforeground=t['fg'],
                          font=app.f_ui, anchor="w", highlightthickness=1, highlightbackground=t['panel'], highlightcolor=t['accent'], **kw)
        choice(tk.Radiobutton, text="Simulação: só gera os dossiês (não chama o agy, não gasta cota)", variable=self.dry, value=True).grid(row=0, column=0, columnspan=4, sticky="w")
        choice(tk.Radiobutton, text="Retomar de verdade: abre uma sessão nova no agy para cada sessão marcada", variable=self.dry, value=False).grid(row=1, column=0, columnspan=4, sticky="w")
        choice(tk.Checkbutton, text="Refazer as que já foram retomadas", variable=self.redo, command=self.redo_changed).grid(row=2, column=0, columnspan=4, sticky="w")
        gap = (app.px(6), 0)
        lab(self.opts, "Modelo do agy:").grid(row=3, column=0, sticky="w", pady=gap)
        self.model_box = ttk.Combobox(self.opts, textvariable=self.model_var, values=app.agy_model_choices(), width=34)
        self.model_box.grid(row=3, column=1, sticky="w", padx=app.px(6), pady=gap)
        lab(self.opts, "vazio = padrão do agy · o agy roda em modo plan (somente leitura)", 'muted', app.f_small).grid(row=3, column=2, columnspan=2, sticky="w", pady=gap)
        lab(self.opts, "Pasta dos dossiês:").grid(row=4, column=0, sticky="w", pady=gap)
        self.dir_entry = tk.Entry(self.opts, textvariable=self.dir_var, state="readonly", readonlybackground=t['panel2'], fg=t['fg'], relief=tk.FLAT,
                                  font=app.f_ui, highlightthickness=1, highlightbackground=t['border'], width=52)
        self.dir_entry.grid(row=4, column=1, sticky="we", padx=app.px(6), pady=gap, ipady=app.px(2))
        IconButton(self.opts, app, "folder", "Escolher…", self.choose_dir, bg_token="panel").grid(row=4, column=2, padx=(0, app.px(6)), pady=gap)
        IconButton(self.opts, app, "", "Padrão", self.reset_dir, bg_token="panel").grid(row=4, column=3, pady=gap)
        # corpo: lista de sessões à esquerda, detalhe à direita
        self.body = tk.Frame(self, bg=t['panel'])
        self.body.pack(fill=tk.BOTH, expand=True)
        left = tk.Frame(self.body, bg=t['panel'])
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right = tk.Frame(self.body, bg=t['panel'], width=app.px(400))
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(app.px(10), 0))
        right.pack_propagate(False)
        self.tools = tk.Frame(left, bg=t['panel'])
        lab(self.tools, "Sessões aprovadas", font=app.f_bold).pack(side=tk.LEFT)
        IconButton(self.tools, app, "", "Marcar todas", lambda: self.mark_all(True), bg_token="panel").pack(side=tk.LEFT, padx=(app.px(10), 0))
        IconButton(self.tools, app, "", "Desmarcar todas", lambda: self.mark_all(False), bg_token="panel").pack(side=tk.LEFT, padx=(app.px(6), 0))
        self.list_title = lab(left, "Sessões deste lote", font=app.f_bold)
        self.tree_box = tk.Frame(left, bg=t['border'], padx=1, pady=1)
        self.tree_box.pack(fill=tk.BOTH, expand=True, pady=(app.px(6), 0))
        ttk.Style().configure("AutoRun.Treeview", rowheight=app.px(28))
        self.tree = ttk.Treeview(self.tree_box, style="AutoRun.Treeview", columns=("sel", "state", "title", "where"), show="headings", selectmode="browse", height=7)
        for col, text, width, stretch in (("sel", "", 36, False), ("state", "Estado", 130, False), ("title", "Sessão", 250, True), ("where", "Projeto / pasta", 170, False)):
            self.tree.heading(col, text=text, anchor=tk.W)
            self.tree.column(col, width=app.px(width), stretch=stretch, anchor=tk.CENTER if col == "sel" else tk.W)
        sb = ttk.Scrollbar(self.tree_box, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for tag, tok in (("ok", "success"), ("erro", "danger"), ("run", "accent_text"), ("wait", "fg"), ("muted", "muted")):
            self.tree.tag_configure(tag, foreground=t[tok])
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.render_detail())
        self.tree.bind("<Button-1>", self.on_click, add="+")
        self.tree.bind("<space>", self.on_space)
        self.tree.bind("<Double-1>", lambda e: self.open_receipt() if self.step != "prepare" else None)
        lab(right, "Detalhe da sessão", font=app.f_bold).pack(fill=tk.X)
        self.detail = tk.Text(right, wrap=tk.WORD, font=app.f_ui, bg=t['panel2'], fg=t['fg'], relief=tk.FLAT, highlightthickness=1, highlightbackground=t['border'],
                              highlightcolor=t['border'], padx=app.px(10), pady=app.px(8), width=40, height=12, tabs=(app.px(120),),
                              selectbackground=t['sel_bg'], selectforeground=t['sel_fg'])
        self.detail.tag_configure("k", font=app.f_bold, foreground=t['muted'])
        self.detail.tag_configure("row", lmargin2=app.px(120))
        self.detail.tag_configure("h", font=app.f_bold, foreground=t['accent_text'], spacing1=app.px(8), spacing3=app.px(2))
        self.detail.bind("<Key>", lambda e: None if (e.state & 0x4 and e.keysym.lower() in ("c", "a")) else "break")  # só leitura, mas copia
        self.btn_receipt = IconButton(right, app, "export", "Ver recibo", self.open_receipt, bg_token="panel")
        self.detail.pack(fill=tk.BOTH, expand=True, pady=(app.px(6), 0))

    # --- etapas -----------------------------------------------------------------------------

    def set_step(self, step):
        app, t = self.app, self.t
        self.step = step
        for key, label in self.step_labels.items():
            on = key == step
            label.configure(bg=t['sel_bg'] if on else t['panel'], fg=t['sel_fg'] if on else t['muted'], highlightbackground=t['accent'] if on else t['panel'])
        self.intro.configure(text=self.INTRO[step])
        if step == "prepare":
            self.opts.pack(fill=tk.X, pady=(0, app.px(8)), before=self.body)
            self.list_title.pack_forget()
            self.tools.pack(fill=tk.X, before=self.tree_box)
            self.primary.kind, self.primary.icon = "primary", "autorun"
            self.primary.set_text("Iniciar")
            self.secondary.set_text("Cancelar")
            self.secondary.pack(side=tk.RIGHT, padx=(0, app.px(8)))
        else:
            self.opts.pack_forget()
            self.tools.pack_forget()
            self.list_title.pack(fill=tk.X, before=self.tree_box)
            if step == "run":
                self.primary.kind, self.primary.icon = "normal", ""
                self.primary.set_text("Cancelar lote")
                self.secondary.pack_forget()
            else:
                self.primary.kind, self.primary.icon = "primary", ""
                self.primary.set_text("Fechar")
                self.secondary.set_text("Salvar relatório…")
                self.secondary.pack(side=tk.RIGHT, padx=(0, app.px(8)))
        self.tree["displaycolumns"] = ("sel", "state", "title", "where") if step == "prepare" else ("state", "title", "where")
        self.primary.redraw()
        self.secondary.redraw()

    def show_prepare(self, items, done):
        self.title("Auto-Run — preparar")
        self.items, self.by_cid, self.done_ids = list(items), {it['cid']: it for it in items}, set(done)
        self.checks = {it['cid']: tk.BooleanVar(master=self, value=it['cid'] not in self.done_ids) for it in self.items}
        for cid, var in self.checks.items():
            var.trace_add("write", lambda *a, c=cid: self.refresh_row(c))
        self.states, self.info, self.lines, self.current, self.summary, self.result = {}, {}, {}, None, None, None
        self.decision.set("")
        self.fill_tree()
        self.set_step("prepare")
        self.update_status()
        if self.items:
            self.tree.selection_set(self.items[0]['cid'])
        self.render_detail()

    def show_run(self, items, n, dry_run, model, dossier_dir):
        if items:
            self.items, self.by_cid = list(items), {it['cid']: it for it in items}
        self.states = {it['cid']: "wait" for it in self.items}
        self.info, self.lines, self.current, self.summary = {}, {}, None, None
        self.dry_run, self.model_used, self.dossier_used = dry_run, model, dossier_dir
        self.title("Auto-Run — " + ("simulação" if dry_run else "executando"))
        self.fill_tree()
        self.set_step("run")
        self.update_status()
        if self.items:
            self.tree.selection_set(self.items[0]['cid'])
        self.render_detail()

    def finish(self, payload):
        self.summary = payload if isinstance(payload, dict) else {}
        self.current = None
        self.set_step("done")
        self.update_status()
        self.render_detail()

    # --- lista ------------------------------------------------------------------------------

    def state_key(self, cid):
        if self.step == "prepare":
            if self.checks.get(cid) is not None and not self.checks[cid].get():
                return "done_off" if cid in self.done_ids else "off"
            return "redo" if cid in self.done_ids else "ready"
        return self.states.get(cid, "wait")

    def row_values(self, cid):
        it = self.by_cid[cid]
        meta = it.get('meta') or {}
        mark = "☑" if self.checks.get(cid) is not None and self.checks[cid].get() else "☐"
        return (mark, self.STATE_TEXT[self.state_key(cid)], it['title'][:80], it.get('workspace_label') or meta.get('project') or "")

    def fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        for it in self.items:
            self.tree.insert("", tk.END, iid=it['cid'], values=self.row_values(it['cid']), tags=(self.STATE_TAG[self.state_key(it['cid'])],))

    def refresh_row(self, cid):
        if cid in self.by_cid and self.tree.exists(cid):
            self.tree.item(cid, values=self.row_values(cid), tags=(self.STATE_TAG[self.state_key(cid)],))
            self.update_status()
            if self.selected() == cid:
                self.render_detail()

    def selected(self):
        sel = self.tree.selection()
        return sel[0] if sel else None

    def mark_all(self, flag):
        for var in self.checks.values():
            var.set(flag)

    def redo_changed(self):  # Refazer marca ou desmarca as já retomadas
        for cid in self.done_ids:
            if cid in self.checks:
                self.checks[cid].set(self.redo.get())

    def on_click(self, e):
        if self.step == "prepare" and self.tree.identify_region(e.x, e.y) == "cell" and self.tree.identify_column(e.x) == "#1":
            cid = self.tree.identify_row(e.y)
            if cid in self.checks:
                self.checks[cid].set(not self.checks[cid].get())
                self.tree.selection_set(cid)
                return "break"

    def on_space(self, e):
        cid = self.selected()
        if self.step == "prepare" and cid in self.checks:
            self.checks[cid].set(not self.checks[cid].get())
        return "break"

    # --- eventos do lote ------------------------------------------------------------------------

    def item_event(self, kind, cid, info):
        if cid not in self.by_cid:
            return
        if kind == "start":
            self.current, self.states[cid] = cid, "run"
        elif kind == "done":
            self.info[cid], self.states[cid] = info, info.get('state', 'erro')
        elif kind == "skipped":
            self.states[cid] = "skipped"
        self.refresh_row(cid)

    def add_line(self, line):
        if self.current:
            self.lines.setdefault(self.current, []).append(line.strip())
            if self.selected() == self.current:
                self.render_detail()

    def update_status(self):
        n = len(self.items)
        if self.step == "prepare":
            self.status.configure(text=f"{sum(1 for v in self.checks.values() if v.get())} de {n} sessões marcadas")
            return
        cnt = lambda *keys: sum(1 for s in self.states.values() if s in keys)
        pl = lambda k, one, many: f"{k} {one if k == 1 else many}"
        if self.step == "run":
            self.status.configure(text=f"{cnt('ok', 'erro', 'dossie')} de {n} processadas · ✔ {cnt('ok')} · ✖ {pl(cnt('erro'), 'falha', 'falhas')}")
            return
        s = self.summary or {}
        text = (f"✔ {pl(s.get('ok', 0), 'retomada', 'retomadas')} · ▤ {pl(s.get('dossier', 0), 'dossiê', 'dossiês')} · ✖ {pl(s.get('failed', 0), 'falha', 'falhas')} · "
                f"» {pl(s.get('skipped', 0), 'não executada', 'não executadas')}")
        if s.get('aborted'):
            text += f" · motivo: {s['aborted']}"
        if s.get('error'):
            text = f"Erro inesperado: {s['error']}"
        self.status.configure(text=text)

    # --- detalhe ------------------------------------------------------------------------------

    def dossier_dir(self):
        return self.dir_var.get().strip() or HANDOFF_DIR

    def render_detail(self):
        txt = self.detail
        txt.configure(state=tk.NORMAL)
        txt.delete("1.0", tk.END)

        def kv(label, value):
            txt.insert(tk.END, label, ("k", "row"))
            txt.insert(tk.END, f"\t{value}\n", ("row",))
        cid = self.selected()
        show_receipt = False
        if not cid or cid not in self.by_cid:
            txt.insert(tk.END, "Selecione uma sessão na lista para ver o detalhe." if self.items else "Sem sessões neste lote.", "k")
        else:
            it, info = self.by_cid[cid], self.info.get(cid, {})
            meta = it.get('meta') or {}
            kv("Sessão", it['title'])
            kv("UUID", cid)
            kv("Estado", self.STATE_TEXT[self.state_key(cid)])
            if self.step == "prepare":
                project, _dirs, cwd = AutoRunner._target(it, self.dossier_dir())
                kv("Projeto original", meta.get('project') or "-")
                kv("Nova sessão em", cwd)
                kv("Projeto no agy", f"{meta.get('project') or project} (--project)" if project else "CLI Project (sem --project)")
                kv("Dossiê em", self.dossier_dir())
                if cid in self.done_ids:
                    kv("Já retomada", f"↪ {str(self.app.handoffs.get(cid, ''))[:8]}")
            else:
                if info.get('new_cid'):
                    kv("Sessão nova", info['new_cid'])
                if info.get('cwd'):
                    kv("Pasta", info['cwd'])
                if info.get('project'):
                    kv("Projeto no agy", info['project'])
                if info.get('model') is not None and info.get('state') == 'ok':
                    kv("Modelo", info['model'] or "padrão do agy")
                if isinstance(info.get('duration'), (int, float)):
                    kv("Duração", f"{info['duration']:.1f} s".replace(".", ","))
                if usage_text(info.get('usage')):
                    kv("Tokens", usage_text(info['usage']))
                if info.get('dossier'):
                    kv("Dossiê", info['dossier'])
                if info.get('error'):
                    kv("Motivo", info['error'].strip().splitlines()[0][:300] if info['error'].strip() else "-")
                show_receipt = self.states.get(cid) == "ok"
                if self.lines.get(cid):
                    txt.insert(tk.END, "O que aconteceu\n", "h")
                    txt.insert(tk.END, "\n".join(self.lines[cid]) + "\n")
                if info.get('response'):
                    resp = " ".join(redact(info['response']).split())
                    txt.insert(tk.END, "Resposta do agy\n", "h")
                    txt.insert(tk.END, resp[:700] + ("…" if len(resp) > 700 else "") + ("\nA resposta completa está no recibo.\n" if len(resp) > 700 else "\n"))
        txt.configure(state=tk.DISABLED)
        if show_receipt:
            if not self.btn_receipt.winfo_manager():
                self.btn_receipt.pack(side=tk.BOTTOM, anchor="w", pady=(self.app.px(8), 0), before=self.detail)
        elif self.btn_receipt.winfo_manager():
            self.btn_receipt.pack_forget()

    def open_receipt(self):
        cid = self.selected()
        if cid and self.states.get(cid) == "ok":
            self.app.show_receipt(cid)

    # --- botões -------------------------------------------------------------------------------

    def on_primary(self):
        if self.step == "prepare":
            self.go()
        elif self.step == "run":
            self.app.cancel_autorun()
        else:
            self.app.close_autorun(self)

    def on_secondary(self):
        if self.step == "prepare":
            self.cancel_prepare()
        elif self.step == "done":
            self.save_report()

    def toggle_log(self):
        if self.log.winfo_manager():
            self.log.pack_forget()
            self.log_toggle.configure(text="▸  Registro completo (para suporte)")
        else:
            self.log.pack(side=tk.BOTTOM, fill=tk.X, before=self.log_toggle)
            self.log_toggle.configure(text="▾  Registro completo (para suporte)")

    def choose_dir(self):
        folder = filedialog.askdirectory(parent=self, title="Pasta dos dossiês do Auto-Run", initialdir=self.dossier_dir() if os.path.isdir(self.dossier_dir()) else None, mustexist=False)
        if folder:
            self.dir_var.set(os.path.normpath(folder))
            self.render_detail()

    def reset_dir(self):
        self.dir_var.set(HANDOFF_DIR)
        self.render_detail()

    def go(self):
        """Iniciar: confere a pasta dos dossiês, guarda as escolhas e libera o `confirm_autorun`. A janela fica: vira a etapa Executando."""
        app = self.app
        folder = self.dossier_dir()
        try:
            os.makedirs(folder, exist_ok=True)
            probe = os.path.join(folder, ".agygate_teste")
            open(probe, "w").close()
            os.remove(probe)
        except OSError as e:
            messagebox.showerror("Auto-Run", f"Não consigo gravar na pasta dos dossiês:\n{folder}\n\n{e}", parent=self)
            return
        model = self.model_var.get().strip()
        history = [m for m in app.settings.get("agy_models", []) if isinstance(m, str)]
        self.result = {'dry_run': self.dry.get(), 'redo': self.redo.get(), 'model': model, 'dossier_dir': folder,
                       'cids': {c for c, v in self.checks.items() if v.get()}}
        app.settings["agy_model"] = model
        if model:
            app.settings["agy_models"] = ([model] + [m for m in history if m != model])[:6]
        same = os.path.normcase(os.path.abspath(folder)) == os.path.normcase(os.path.abspath(HANDOFF_DIR))
        app.settings["dossier_dir"] = "" if same else folder
        save_settings(app.settings)
        self.decision.set("go")

    def cancel_prepare(self):
        self.result = None
        self.decision.set("cancel")
        self.destroy()

    def destroy(self):
        app = getattr(self, "app", None)
        if app is not None and app.auto_win and app.auto_win[0] is self:
            app.auto_win = None
        try:
            if self.step == "prepare" and not self.decision.get():
                self.result = None
                self.decision.set("cancel")  # solta o confirm_autorun que ainda espera
        except tk.TclError:
            pass
        super().destroy()

    # --- relatório ------------------------------------------------------------------------------

    def report_markdown(self):
        s = self.summary or {}
        pl = lambda k, one, many: f"{k} {one if k == 1 else many}"
        out = ["# Relatório do Auto-Run", "",
               f"- **Quando:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
               "- **Modo:** " + ("simulação (só gera os dossiês)" if self.dry_run else "retomada real (agy, modo plan)"),
               f"- **Modelo:** {self.model_used or 'padrão do agy'}",
               f"- **Pasta dos dossiês:** {self.dossier_used}",
               f"- **Resultado:** ✔ {pl(s.get('ok', 0), 'retomada', 'retomadas')} · ▤ {pl(s.get('dossier', 0), 'dossiê', 'dossiês')} · "
               f"✖ {pl(s.get('failed', 0), 'falha', 'falhas')} · » {pl(s.get('skipped', 0), 'não executada', 'não executadas')}"]
        if s.get('aborted'):
            out.append(f"- **Interrompido:** {s['aborted']}")
        if s.get('quota'):
            out.append(f"- **Cota esgotada:** volta em {s['quota']}")
        for i, it in enumerate(self.items, 1):
            cid, info = it['cid'], self.info.get(it['cid'], {})
            out += ["", f"## {i}. {it['title']}", "", f"- **UUID:** `{cid}`", f"- **Estado:** {self.STATE_TEXT[self.states.get(cid, 'wait')]}"]
            if info.get('new_cid'):
                out.append(f"- **Sessão nova:** `{info['new_cid']}`")
            for label, key in (("Pasta de trabalho", "cwd"), ("Projeto no agy", "project"), ("Dossiê", "dossier")):
                if info.get(key):
                    out.append(f"- **{label}:** {info[key]}")
            if isinstance(info.get('duration'), (int, float)):
                out.append(f"- **Duração:** {info['duration']:.1f} s".replace(".", ","))
            if usage_text(info.get('usage')):
                out.append(f"- **Tokens:** {usage_text(info['usage'])}")
            if info.get('error'):
                out.append(f"- **Motivo:** {info['error'].strip().splitlines()[0][:300] if info['error'].strip() else '-'}")
            if info.get('response'):
                out += ["", "Resposta do agy:", "", redact(info['response']).strip()]
        return "\n".join(out) + "\n"

    def save_report(self):
        os.makedirs(EXPORT_DIR, exist_ok=True)
        name = f"AntigravityGate_autorun_{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
        out = filedialog.asksaveasfilename(parent=self, title="Salvar relatório do Auto-Run", initialdir=EXPORT_DIR, initialfile=name,
                                           defaultextension=".md", filetypes=[("Markdown", "*.md"), ("Texto", "*.txt"), ("Todos os arquivos", "*.*")])
        if not out:
            return
        try:
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(self.report_markdown())
        except OSError as e:
            messagebox.showerror("Auto-Run", f"Não foi possível salvar o relatório: {e}", parent=self)
            return
        self.app.notify("ok", f"Relatório salvo: {out}")


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
        # Janelas do app já fechadas (nos testes, várias por processo) são lixo cíclico com objetos Tk. Se o coletor rodar
        # dentro da thread de leitura, o Tk aborta ("async handler deleted by the wrong thread"): coleta aqui, na principal.
        gc.collect()
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
        self.side_items, self.proj_items, self.tabs, self._proj_key, self.sidebar_wanted = {}, [], {}, None, True
        self._confirming = False  # a janela do Auto-Run está na etapa Preparar, esperando o Iniciar
        self.search_note = ""

        self.settings = load_settings()
        w, h, x, y = window_geometry(lambda px, py: work_area_at(self, px, py), self.winfo_fpixels('1i') / 96, self.settings.get("window"))
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(min(WIN_MIN[0], w), min(WIN_MIN[1], h))
        self.start_zoomed = saved_zoomed(self.settings.get("window"))
        if self.start_zoomed:
            # Antes de a janela aparecer o Windows ignora o "zoomed": maximiza no primeiro <Map>.
            self._zoom_bind = self.bind("<Map>", self._zoom_on_map, add="+")
        self.limit_preset, att, crit = limits_from_settings(self.settings)
        set_context_limits(att, crit)
        c = self.settings.get("context") if isinstance(self.settings.get("context"), dict) else {}
        self.limits_custom = (c.get("attention") or att, c.get("critical") or crit)
        self.banner_dismissed = None
        set_app_icon(self)
        self.fonts_loaded = register_fonts()  # ícones Font Awesome, Bootstrap e Material (Windows; só para este processo)
        self.families = set(tkfont.families(self))
        self.base_family = next((f for f in ("Inter", "Segoe UI", "Helvetica", "DejaVu Sans") if f in self.families),
                                tkfont.nametofont("TkDefaultFont").actual("family"))
        self.theme_key = self.settings.get("theme") if self.settings.get("theme") in THEMES else "escuro"
        self.density = self.settings.get("density") if self.settings.get("density") in self.ROW_HEIGHT else "compact"
        wanted = (os.environ.get("AGY_ICONS") or self.settings.get("icons") or "auto").lower()
        self.icon_mode = wanted if wanted in ("mdl2", "symbol", "none", *ICON_FONTS) else ("mdl2" if "Segoe MDL2 Assets" in self.families else "symbol")
        self.f_ui = tkfont.Font(self, family=self.base_family, size=10)
        self.f_bold = tkfont.Font(self, family=self.base_family, size=10, weight="bold")
        self.f_small = tkfont.Font(self, family=self.base_family, size=9)
        self.f_btn = tkfont.Font(self, family=self.base_family, size=9, weight="bold")
        self.f_title = tkfont.Font(self, family=self.base_family, size=15, weight="bold")
        self.f_icon = tkfont.Font(self, family=self.base_family, size=11)
        self.f_banner_icon = tkfont.Font(self, family=self.base_family, size=20)
        self.f_brand = tkfont.Font(self, family=self.base_family, size=12, weight="bold")
        self.banner_level, self._banner_style = 2, None
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
            family = "Segoe MDL2 Assets"
        elif self.icon_mode in ICON_FONTS and ICON_FONTS[self.icon_mode][0] in self.families:
            family = ICON_FONTS[self.icon_mode][0]
        else:
            family = next((f for f in ("Segoe UI Symbol", "DejaVu Sans", self.base_family) if f in self.families), self.base_family)
        self.f_icon.configure(family=family, size=11)
        self.f_banner_icon.configure(family=family, size=20)  # ícone da faixa de alerta, em destaque

    @property
    def bg_color(self):
        return self.t['bg']

    def apply_theme(self):
        old_icons = self.icon_cache  # mantém as imagens antigas vivas até todos os widgets receberem as novas
        self.icon_cache = {}
        t = self.t = dict(THEMES[self.theme_key])
        t['header_sub'] = blend(t['header_fg'], t['header_bg'], 0.12)
        t['btn_fg'] = t['fg']
        t['banner_bg'] = banner_colors(t, self.banner_level)['bg']  # muda com o nível da faixa (style_banner)
        self.configure(bg=t['bg'])
        self.f_title.configure(family=next((f for f in t['title_fonts'] if f in self.families), self.base_family))
        self.f_brand.configure(family=self.f_title.cget("family"))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background=t['panel'], fieldbackground=t['panel'], foreground=t['fg'], rowheight=self.px(self.ROW_HEIGHT[self.density]),
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
        if hasattr(self, 'banner'):
            self._banner_style = None
            self.style_banner()
        for b in self.icon_buttons:
            b.redraw()
        for c in self.chips.values():
            c.repaint()
        self.repaint_nav()
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
        if hasattr(self, 'banner'):
            self._banner_style = None
            self.style_banner()
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

    def level_rows(self, level):
        """Sessões visíveis e não arquivadas no nível de contexto `level` (1 atenção, 2 crítico)."""
        shown = [self.row_by_cid[self.cid_of(i)] for i in self.iter_sessions() if self.cid_of(i) in self.row_by_cid]
        return [r for r in shown if ctx_level(r['ctx']) == level and self.states.get(r['cid']) != "arquivada"]

    def critical_rows(self):
        return self.level_rows(2)

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

    def banner_key(self, level):
        return (self.sources[self.source_idx][0], CONTEXT_LIMITS['attention'], CONTEXT_LIMITS['critical'], level)

    def style_banner(self):
        """Cores, ícone e botão da faixa conforme o nível atual. Só repinta quando tema, ícones ou nível mudaram."""
        key = (self.theme_key, self.icon_mode, self.banner_level)
        if key == self._banner_style:
            return
        self._banner_style = key
        c = banner_colors(self.t, self.banner_level)
        self.t['banner_bg'] = c['bg']
        self.banner.configure(bg=c['bg'], highlightbackground=c['stripe'], highlightcolor=c['stripe'])
        self.banner_stripe.configure(bg=c['stripe'])
        self.banner_text.configure(bg=c['bg'])
        glyph, font = alert_glyph(self)
        self.banner_icon.configure(text=glyph, bg=c['bg'], fg=c['icon'], font=font)
        for lab in (self.banner_msg, self.banner_detail):
            lab.configure(bg=c['bg'], fg=c['fg'])
        view = self.btn["banner_view"]
        view.tip = "Listar só as sessões críticas" if self.banner_level == 2 else "Listar só as sessões em atenção"
        view.icon_token = "danger" if self.banner_level == 2 else "warning"
        view.set_text("Ver críticas" if self.banner_level == 2 else "Ver em atenção")
        for name in ("banner_view", "banner_dismiss"):
            self.btn[name].redraw()

    def update_banner(self):
        """Faixa de alerta: crítico tem prioridade; atenção aparece só quando não há críticas."""
        crit = self.critical_rows()
        level, rows = (2, crit) if crit else (1, self.level_rows(1))
        show = bool(rows) and self.match is None and self.banner_dismissed != self.banner_key(level)
        if show:
            self.banner_level = level
            self.style_banner()
            n, att, cri = len(rows), fmt_tokens(CONTEXT_LIMITS['attention']), fmt_tokens(CONTEXT_LIMITS['critical'])
            if level == 2:
                self.banner_msg.configure(text=f"CRÍTICO · {n} sessão(ões) acima do nível crítico ({cri} tokens)")
                self.banner_detail.configure(text="Gere o dossiê e retome em uma sessão nova para não perder qualidade.")
            else:
                self.banner_msg.configure(text=f"ATENÇÃO · {n} sessão(ões) acima do nível de atenção ({att} tokens)")
                self.banner_detail.configure(text=f"Ainda dá para trabalhar, mas planeje a troca: gere o dossiê antes do nível crítico ({cri} tokens).")
            if not self.banner.winfo_manager():
                self.banner.pack(fill=tk.X, padx=self.px(16), pady=(0, self.px(8)), before=self.holder)
        elif self.banner.winfo_manager():
            self.banner.pack_forget()

    def show_level(self, level):
        """Lista só as sessões (não arquivadas) do nível: 2 = críticas, 1 = em atenção."""
        rows = self.level_rows(level)
        self.match = {r['cid'] for r in rows}
        self.chip_filter = None
        self.search_note = f"{len(rows)} sessão(ões) " + ("críticas" if level == 2 else "em atenção")
        self.populate()

    def show_critical(self):
        self.show_level(2)

    def dismiss_banner(self):
        self.banner_dismissed = self.banner_key(self.banner_level)
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
        # Marca compacta: ícone e nome. A descrição ("Gestão de contexto e curadoria") ficou na dica, para o cabeçalho ter menos texto.
        self.logo = self.themed_widget(tk.Label(self.brand, font=self.f_title), bg="header_bg", fg="header_fg")
        icons = getattr(self, "_app_icons", None)
        if icons:
            self.logo.configure(image=icons[2] if self.px(32) < 48 else icons[1])  # 32 px, ou 64 px em tela de alta densidade
        else:
            self.logo.configure(text="◆")
        self.logo.pack(side=tk.LEFT)
        self.title_lbl = self.themed_widget(tk.Label(self.brand, text="AntigravityGate", font=self.f_brand), bg="header_bg", fg="header_fg")
        self.title_lbl.pack(side=tk.LEFT, padx=(self.px(8), self.px(18)))
        for w in (self.logo, self.title_lbl):
            Tooltip(w, self, lambda: f"Gestão de contexto e curadoria · v{__version__}")
        # Abas: atalhos para o mesmo filtro dos selos do rodapé e da barra lateral (`chip_filter`).
        self.tabs_frame = self.themed_widget(tk.Frame(self.top_frame), bg="header_bg")
        self.tabs_frame.pack(side=tk.LEFT)
        for key, text in (("todas", "Todas"), ("aguardando", "Aprovadas aguardando"), ("arquivada", "Arquivadas")):
            tab = Tab(self.tabs_frame, self, text, lambda k=key: self.set_filter(None if k == "todas" else k))
            tab.pack(side=tk.LEFT, padx=(0, self.px(2)))
            self.tabs[key] = tab
        self.hdr_right = self.themed_widget(tk.Frame(self.top_frame), bg="header_bg")
        self.hdr_right.pack(side=tk.RIGHT)
        self.make_button(self.hdr_right, "about", "about", "Sobre", self.open_about, "Sobre: versão, autor e diagnóstico (F1)", bg_token="header_bg", icon_token="accent_text", icon_only=True).pack(side=tk.RIGHT, padx=(self.px(8), 0))
        self.make_button(self.hdr_right, "theme", "theme", self.theme_button_text(), self.show_theme_menu, "Escolher tema e estilo de ícones", bg_token="header_bg", icon_token="accent_text").pack(side=tk.RIGHT, padx=(self.px(8), 0))
        self.make_button(self.hdr_right, "limits", "limits", "Limites", self.open_limits, self.limits_tip(), bg_token="header_bg", icon_token="warning").pack(side=tk.RIGHT, padx=(self.px(8), 0))
        self.make_button(self.hdr_right, "refresh", "refresh", "Atualizar", self.refresh, "Reler as pastas e recarregar as sessões (F5)", bg_token="header_bg").pack(side=tk.RIGHT)

        # Barra de status: fonte, carga, avisos e selos de contagem
        self.footer = self.themed_widget(tk.Frame(self, padx=self.px(14), pady=self.px(6)), bg="panel2")
        self.footer.pack(side=tk.BOTTOM, fill=tk.X)
        for token, key in (("danger", "crit"), ("warning", "rot"), ("muted", "arquivada"), ("success", "aprovada"), ("accent_text", "pendente")):
            chip = Chip(self.footer, self, token, key)
            chip.pack(side=tk.RIGHT, padx=(self.px(6), 0))
            self.chips[key] = chip
        self.status = self.themed_widget(tk.Label(self.footer, anchor=tk.W, font=self.f_small), bg="panel2", fg="fg")
        self.status.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Barra lateral: categorias e projetos. As categorias são atalhos para o filtro dos selos do rodapé; um projeto leva a tabela até ele.
        # Ctrl+B recolhe; em janela estreita ela se esconde sozinha (apply_nav_layout).
        self.sidebar = self.themed_widget(tk.Frame(self, width=self.px(232)), bg="panel")
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)
        self.side_sep = self.themed_widget(tk.Frame(self, width=1), bg="border")
        self.side_sep.pack(side=tk.LEFT, fill=tk.Y)
        sec = lambda text: self.themed_widget(tk.Label(self.sidebar, text=text, font=self.f_small, anchor="w", padx=self.px(14)), bg="panel", fg="muted")
        sec("FONTE DE DADOS").pack(fill=tk.X, pady=(self.px(14), self.px(4)))
        self.src_box = ttk.Combobox(self.sidebar, state="readonly", values=[x[0] for x in self.sources])
        self.src_box.bind("<<ComboboxSelected>>", self.on_source_change)
        self.src_box.pack(fill=tk.X, padx=self.px(14))
        Tooltip(self.src_box, self, lambda: self.sources[self.source_idx][0])
        sec("CATEGORIAS").pack(fill=tk.X, pady=(self.px(16), self.px(4)))
        for key, text, glyph, token in self.NAV_CATS:
            item = SideItem(self.sidebar, self, text, glyph, token, lambda k=key: self.toggle_chip_filter(k))
            item.pack(fill=tk.X, padx=self.px(8), pady=1)
            self.side_items[key] = item
        sec("PROJETOS E ESPAÇOS").pack(fill=tk.X, pady=(self.px(16), self.px(4)))
        self.proj_box = self.themed_widget(tk.Frame(self.sidebar), bg="panel")
        self.proj_box.pack(fill=tk.X)
        self.proj_more = self.themed_widget(tk.Label(self.sidebar, font=self.f_small, anchor="w", padx=self.px(14)), bg="panel", fg="muted")
        self.proj_more.pack(fill=tk.X)
        # Ambiente (só leitura, sem executar o agy: cada execução abre o editor do Antigravity): agy encontrado e daemon no login.
        self.env_box = self.themed_widget(tk.Frame(self.sidebar), bg="panel")
        self.env_box.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, self.px(10)))
        self.env_agy = self.themed_widget(tk.Label(self.env_box, font=self.f_small, anchor="w", padx=self.px(14)), bg="panel")
        self.env_rc = self.themed_widget(tk.Label(self.env_box, font=self.f_small, anchor="w", padx=self.px(14)), bg="panel")
        self.env_agy.pack(fill=tk.X)
        self.env_rc.pack(fill=tk.X)
        self.env_state, self.env_tips = (False, None), ("", "")
        Tooltip(self.env_agy, self, lambda: self.env_tips[0])
        Tooltip(self.env_rc, self, lambda: self.env_tips[1])
        self.update_env_status()

        # Busca: campo largo com a dica dentro; Buscar e Limpar só com ícone. A fonte das sessões fica no topo da barra lateral
        # (sem a barra, aparece aqui: src_box_top).
        self.filter_frame = self.themed_widget(tk.Frame(self, padx=self.px(16), pady=self.px(10)), bg="bg")
        self.filter_frame.pack(fill=tk.X)
        self.src_box_top = ttk.Combobox(self.filter_frame, state="readonly", width=26)
        self.src_box_top.bind("<<ComboboxSelected>>", self.on_source_change)
        self.sync_source_boxes()
        self.make_button(self.filter_frame, "clear", "clear", "Limpar", self.clear_search, "Limpar a busca (Esc)", icon_only=True).pack(side=tk.RIGHT, padx=(self.px(6), 0))
        self.make_button(self.filter_frame, "search", "search", "Buscar", self.run_search, "Buscar em título, pasta, agente, UUID e no conteúdo das conversas (Enter; Ctrl+K vai ao campo)", icon_token="accent_text", icon_only=True).pack(side=tk.RIGHT, padx=(self.px(10), 0))
        self.search_box = self.themed_widget(tk.Frame(self.filter_frame, padx=1, pady=1), bg="border")
        self.search_box.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=self.px(2))
        inner = self.themed_widget(tk.Frame(self.search_box), bg="panel")
        inner.pack(fill=tk.BOTH, expand=True)
        self.search_var = tk.StringVar()
        self.search_entry = self.themed_widget(tk.Entry(inner, textvariable=self.search_var, relief=tk.FLAT, font=self.f_ui, highlightthickness=0),
                                               bg="panel", fg="fg", insertbackground="fg")
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(self.px(10), 0), ipady=self.px(4))
        # dica dentro do campo (some ao digitar); o texto digitado nunca a inclui
        self.search_hint = self.themed_widget(tk.Label(inner, text="Buscar em título, pasta, agente, UUID e conteúdo das conversas", font=self.f_ui, anchor="w"), bg="panel", fg="muted")
        self.search_hint.bind("<Button-1>", lambda e: self.search_entry.focus_set())
        self.search_var.trace_add("write", lambda *a: self.update_search_hint())
        self.update_search_hint()
        self.search_entry.bind("<Return>", lambda e: self.run_search())
        self.search_entry.bind("<Escape>", lambda e: self.clear_search())
        self.bind("<Control-f>", lambda e: (self.search_entry.focus_set(), "break")[1])
        # Ctrl+K e Ctrl+B também no campo de busca: a ligação do próprio campo vem antes da do Tk (apagar até o fim da linha; voltar um caractere).
        self.bind("<Control-k>", lambda e: self.focus_search())
        self.search_entry.bind("<Control-k>", lambda e: self.focus_search())
        self.bind("<Control-b>", lambda e: self.toggle_sidebar())
        self.search_entry.bind("<Control-b>", lambda e: self.toggle_sidebar())

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


        # Tabela (Treeview) com métricas de contexto
        # Painel de detalhes da seleção (recolhível), acima do rodapé
        self.details = self.themed_widget(tk.Frame(self, highlightthickness=1), bg="panel", highlightbackground="border")
        self.details.pack(side=tk.BOTTOM, fill=tk.X, padx=self.px(16), pady=(0, self.px(8)))
        bar = self.details_bar = self.themed_widget(tk.Frame(self.details, padx=self.px(10), pady=self.px(4), cursor="hand2",
                                                             takefocus=1, highlightthickness=1), bg="panel2", highlightbackground="panel2",
                                                    highlightcolor="accent")
        bar.pack(fill=tk.X)
        for seq in ("<Return>", "<space>"):
            bar.bind(seq, lambda e: self.toggle_details())
        self.details_toggle = self.themed_widget(tk.Label(bar, font=self.f_bold, cursor="hand2"), bg="panel2", fg="fg")
        self.details_toggle.pack(side=tk.LEFT)
        for w in (bar, self.details_toggle):
            w.bind("<Button-1>", lambda e: self.toggle_details())
        self.details_body = self.themed_widget(tk.Frame(self.details, padx=self.px(14), pady=self.px(10)), bg="panel")
        self.build_details()
        self.apply_details_visibility()

        # Faixa de alerta de contexto (aparece só quando há; fica entre as ações e a tabela). Dois níveis:
        # crítico (vermelho forte, texto claro) e atenção (âmbar suave, só quando não há críticas). Cores: banner_colors.
        self.banner = tk.Frame(self, highlightthickness=1)
        self.banner_stripe = tk.Frame(self.banner, width=self.px(6))
        self.banner_stripe.pack(side=tk.LEFT, fill=tk.Y)
        self.banner_icon = tk.Label(self.banner, font=self.f_banner_icon)
        self.banner_icon.pack(side=tk.LEFT, padx=(self.px(12), self.px(10)), pady=self.px(8))
        self.make_button(self.banner, "banner_dismiss", "clear", "Dispensar", self.dismiss_banner, "Esconder este aviso até mudar de fonte ou de limite", bg_token="banner_bg").pack(side=tk.RIGHT, padx=(self.px(8), self.px(12)))
        self.make_button(self.banner, "banner_view", "search", "Ver críticas", lambda: self.show_level(self.banner_level), "Listar só as sessões críticas", bg_token="banner_bg", icon_token="danger").pack(side=tk.RIGHT)
        self.banner_text = tk.Frame(self.banner)
        self.banner_text.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=self.px(8))
        self.banner_msg = tk.Label(self.banner_text, anchor="w", justify=tk.LEFT, font=self.f_bold)
        self.banner_msg.pack(fill=tk.X)
        self.banner_detail = tk.Label(self.banner_text, anchor="w", justify=tk.LEFT, font=self.f_ui)
        self.banner_detail.pack(fill=tk.X)
        self.style_banner()

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
        columns = ("col_date", "col_size", "col_ctx", "col_steps", "col_fail", "col_title", "col_agent", "col_uuid", "col_menu")
        self.tree = ttk.Treeview(holder, columns=columns, show="tree headings", selectmode="extended")

        self.tree.heading("#0", text="Projeto / Sessão", anchor=tk.W)
        for col in columns:
            anchor = tk.CENTER if col in ("col_size", "col_ctx", "col_steps", "col_fail", "col_menu") else tk.W
            cmd = (lambda c=col: self.sort_by(c)) if col in SORT_FUNCS else ""
            self.tree.heading(col, text=HEADINGS[col], anchor=anchor, command=cmd)

        self.tree.heading("col_date", text=HEADINGS["col_date"] + " ▼")  # ordenação inicial: mais recentes primeiro
        self.tree.column("#0", width=self.px(220), anchor=tk.W)
        self.tree.column("col_date", width=self.px(132), anchor=tk.W)
        self.tree.column("col_size", width=self.px(66), anchor=tk.CENTER)
        self.tree.column("col_ctx", width=self.px(170), anchor=tk.CENTER)
        self.tree.column("col_steps", width=self.px(52), anchor=tk.CENTER)
        self.tree.column("col_title", width=self.px(220), anchor=tk.W)
        self.tree.column("col_agent", width=self.px(140), anchor=tk.W)
        self.tree.column("col_fail", width=self.px(52), anchor=tk.CENTER)
        self.tree.column("col_uuid", width=self.px(88), anchor=tk.W)
        self.tree.column("col_menu", width=self.px(36), anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(holder, orient=tk.VERTICAL, command=self.tree.yview)
        hscroll = ttk.Scrollbar(holder, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar.set, xscrollcommand=hscroll.set)

        # Barras empacotadas antes da árvore: não somem quando a janela encolhe. A horizontal dá acesso às colunas do fim.
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        hscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Título logo depois de Projeto / Sessão; os valores das linhas continuam na ordem de `columns` (COL_*).
        # Larguras fixas (sem stretch): o Tk encolhia as colunas esticáveis sozinho e desfazia o ajuste do usuário.
        for c in ("#0",) + columns:
            self.tree.column(c, stretch=False)
        self.tree["displaycolumns"] = ("col_title", "col_date", "col_ctx", "col_steps", "col_fail", "col_size", "col_uuid", "col_menu")  # sem Agente: está nos detalhes e na busca; larguras somam ~1040 px (cabem com a barra lateral)
        self.cell_tips = CellTooltip(self.tree, self, self.tree_cell_tip, level_fn=self.tree_cell_level)
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Button-1>", self.on_tree_click, add="+")  # coluna Ações (⋮)
        self.tree.bind("<Button-3>", self.show_menu)
        for seq in ("<Shift-F10>", "<App>"):
            try:
                self.tree.bind(seq, self.menu_from_keyboard)
            except tk.TclError:  # <App> só existe no Windows
                pass
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

    def _zoom_on_map(self, e):
        if e.widget is not self or not getattr(self, "_zoom_bind", None):
            return
        self.unbind("<Map>", self._zoom_bind)
        self._zoom_bind = None
        self.after(50, self.zoom)

    def zoom(self):
        """Maximiza (Windows: estado 'zoomed'; X11: atributo -zoomed)."""
        try:
            self.wm_state("zoomed")  # não self.state(): o atributo self.state é o StateStore e esconde o método do Tk
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
        self.apply_nav_layout()
        hdr_room = self.top_frame.winfo_width() - self.brand.winfo_reqwidth() - self.px(32)
        if self.tabs_frame.winfo_manager():
            hdr_room -= self.tabs_frame.winfo_reqwidth()
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
        elif len(self.selected_session_ids()) > 1:
            reason = "Selecione uma sessão só: exportação e dossiê são de uma conversa por vez."
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

    ROW_HEIGHT = {"compact": 30, "comfortable": 46}  # px a 96 dpi: 1 linha por sessão, ou 2 (data e hora, consumo e faixa)
    CHIP_FILTERS = {"pendente": "pendentes", "aprovada": "aprovadas", "arquivada": "arquivadas", "rot": "em atenção", "crit": "críticas",
                    "aguardando": "aprovadas aguardando o Auto-Run"}
    NAV_CATS = (("pendente", "Pendentes", "○", "accent_text"), ("rot", "Em atenção", "⚠", "warning"), ("crit", "Críticas", "‼", "danger"),
                ("aprovada", "Aprovadas", "✔", "success"), ("arquivada", "Arquivadas", "▣", "muted"))
    NAV_PROJECTS = 14  # projetos listados na barra lateral; os demais ficam só na tabela

    def chip_match(self, key, r):
        if key in ("rot", "crit"):
            return ctx_level(r['ctx']) == (1 if key == "rot" else 2)
        if key == "aguardando":  # aprovada e ainda sem retomada: é o que o Auto-Run vai pegar
            return self.states.get(r['cid'], "pendente") == "aprovada" and not self.handoffs.get(r['cid'])
        return self.states.get(r['cid'], "pendente") == key

    def set_density(self, mode):
        """Tabela compacta (1 linha por sessão) ou confortável (2 linhas). Lembrada entre execuções."""
        self.density = mode
        self.settings['density'] = mode
        save_settings(self.settings)
        ttk.Style().configure("Treeview", rowheight=self.px(self.ROW_HEIGHT[mode]))
        if self.grouped:
            self.populate()

    def menu_col_id(self):
        return f"#{list(self.tree['displaycolumns']).index('col_menu') + 1}"

    def on_tree_click(self, e):
        """Clique na coluna Ações (⋮): abre o menu de contexto da sessão, como o botão direito."""
        if self.tree.identify_region(e.x, e.y) == "cell" and self.tree.identify_column(e.x) == self.menu_col_id():
            iid = self.tree.identify_row(e.y)
            if iid and self.is_session(iid):
                self.show_menu(e)
                return "break"

    def set_filter(self, key):
        """Abas: levam a lista a um filtro (None = todas as sessões). Clicar na aba já ativa não faz nada."""
        if not self.grouped:
            return
        if key is None:
            if self.chip_filter or self.match is not None:
                self.clear_search()
        elif self.chip_filter != key:
            self.toggle_chip_filter(key)

    def focus_search(self):
        self.search_entry.focus_set()
        self.search_entry.select_range(0, tk.END)
        return "break"

    def toggle_sidebar(self):
        self.sidebar_wanted = not self.sidebar_wanted
        self.apply_nav_layout()
        return "break"

    def apply_nav_layout(self):
        """Barra lateral e abas só aparecem com espaço: abaixo de 900 px de largura a barra se esconde (o filtro continua nos selos do
        rodapé e a fonte no seletor do topo), abaixo de 1000 px as abas. Ctrl+B recolhe a barra em qualquer largura."""
        w = self.winfo_width()
        if w <= 1:
            return
        want = self.sidebar_wanted and w >= self.px(900)
        if want != bool(self.sidebar.winfo_manager()):
            if want:
                self.sidebar.pack(side=tk.LEFT, fill=tk.Y, before=self.filter_frame)
                self.side_sep.pack(side=tk.LEFT, fill=tk.Y, before=self.filter_frame)
            else:
                self.sidebar.pack_forget()
                self.side_sep.pack_forget()
        top = not self.sidebar.winfo_manager()  # sem a barra lateral, a fonte das sessões volta para a linha da busca
        if top != bool(self.src_box_top.winfo_manager()):
            if top:
                self.src_box_top.pack(side=tk.LEFT, padx=(0, self.px(10)), before=self.search_box)
            else:
                self.src_box_top.pack_forget()
        tabs = w >= self.px(1000)
        if tabs != bool(self.tabs_frame.winfo_manager()):
            if tabs:
                self.tabs_frame.pack(side=tk.LEFT)
            else:
                self.tabs_frame.pack_forget()

    def goto_project(self, name):
        """Leva a tabela até o projeto: abre a pasta e rola até ela. Com busca ou filtro ativo, mostra tudo antes."""
        prefix = f"  {name} ("
        find = lambda: next((i for i in self.tree.get_children() if self.tree.item(i, "text").startswith(prefix)), None)
        node = find()
        if node is None and (self.match is not None or self.chip_filter):
            self.clear_search()
            node = find()
        if node is not None:
            self.tree.item(node, open=True)
            self.tree.selection_set(node)
            self.tree.see(node)

    def update_nav(self):
        """Barra lateral e abas: contagens (sempre de todas as sessões) e item ativo. O filtro é um só (`chip_filter`)."""
        if not self.tabs:  # ainda montando a janela
            return
        rows = list(self.row_by_cid.values())
        st = lambda r: self.states.get(r['cid'], "pendente")
        levels = [ctx_level(r['ctx']) for r in rows]
        counts = {k: sum(1 for r in rows if st(r) == k) for k in ("pendente", "aprovada", "arquivada")}
        counts.update(rot=levels.count(1), crit=levels.count(2))
        for key, item in self.side_items.items():
            item.update_item(count=counts[key], on=self.chip_filter == key)
        waiting = sum(1 for r in rows if self.chip_match("aguardando", r))
        self.tabs["aguardando"].set_count(waiting)
        on = {"todas": not self.chip_filter and self.match is None, "aguardando": self.chip_filter == "aguardando", "arquivada": self.chip_filter == "arquivada"}
        for key, tab in self.tabs.items():
            tab.on = on[key]
            tab.repaint()
        names = tuple((n, len(self.grouped[n])) for n in sorted(self.grouped))
        if names != self._proj_key:
            self._proj_key = names
            for it in self.proj_items:
                it.destroy()
            self.proj_items = []
            for name, n in names[:self.NAV_PROJECTS]:
                it = SideItem(self.proj_box, self, name, "▭", "accent_text", lambda nm=name: self.goto_project(nm))
                it.update_item(count=n)
                it.pack(fill=tk.X, padx=self.px(8), pady=1)
                self.proj_items.append(it)
            more = len(names) - self.NAV_PROJECTS
            self.proj_more.configure(text=f"+{more} projeto(s) só na tabela" if more > 0 else "")

    def repaint_nav(self):
        for w in list(self.side_items.values()) + self.proj_items + list(self.tabs.values()):
            w.repaint()
        self.paint_env()

    def update_env_status(self):
        """Lê o ambiente: `agy` no PATH (ou AGY_EXE) e o daemon na chave Run. Roda ao abrir e no Atualizar (F5)."""
        agy, rc = find_agy(), remote_control_registered()
        self.env_state = (bool(agy), rc)
        self.env_tips = (agy or "Não achei o agy no PATH nem em AGY_EXE: o Auto-Run precisa dele. Confira `agy --help` no PowerShell.",
                         "Procurei 'remote-control' na chave Run do Windows (HKCU, Run): mostra se o daemon inicia no login, não se está online. "
                         "Para ver se está online, abra o site do Antigravity (instância dev-thomaz). Para registrar: agy remote-control start.")
        self.paint_env()

    def paint_env(self):
        if not hasattr(self, "env_agy"):
            return
        t, (agy_ok, rc) = self.t, self.env_state
        self.env_agy.configure(text="● agy encontrado" if agy_ok else "○ agy não encontrado", fg=t['success'] if agy_ok else t['warning'])
        if rc is None:
            self.env_rc.pack_forget()
            return
        self.env_rc.configure(text="● remoto: inicia no login" if rc else "○ remoto: não inicia no login", fg=t['success'] if rc else t['warning'])
        if not self.env_rc.winfo_manager():
            self.env_rc.pack(fill=tk.X)

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
        self.update_nav()

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
        """Divisor do cabeçalho: ajusta a largura da coluna ao conteúdo. Sessão: abre o painel de detalhes."""
        x = getattr(event, "x", 0)
        if self.tree.identify_region(x, event.y) == "separator":
            # coluna cuja borda direita está mais perto do clique
            col, _l, right = min(self.cell_tips.edges(), key=lambda e: abs(e[2] - x))
            if abs(right - x) <= self.px(8):
                self.autofit_column(col)
            return "break"
        iid = self.tree.identify_row(event.y)
        if not self.is_session(iid):
            return  # cabeçalho, área vazia ou pasta de projeto: o duplo clique padrão só expande/recolhe
        self.tree.selection_set(iid)
        self.open_details()

    def open_details(self):
        """Abre o painel de detalhes (se estava recolhido) para a sessão selecionada."""
        if not self.settings.get('details', True):
            self.toggle_details()
        self.update_details()

    def autofit_column(self, col):
        """Largura da coluna = maior texto (cabeçalho ou células) + folga, entre 50 e 900 px escalados."""
        pad = self.px(24)
        width = self.f_bold.measure(self.tree.heading(col, "text")) + pad
        def walk(parent, depth):
            nonlocal width
            for iid in self.tree.get_children(parent):
                if col == "#0":
                    w = self.f_ui.measure(self.tree.item(iid, "text")) + self.px(20) * (depth + 1) + self.px(16) + pad
                else:
                    w = self.f_ui.measure(str(self.tree.set(iid, col))) + pad
                width = max(width, w)
                walk(iid, depth + 1)
        walk("", 0)
        self.tree.column(col, width=max(self.px(50), min(width, self.px(900))))

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
        if self.chip_filter:  # filtro de selo: refaz a lista (uma sessão marcada pode ter saído do filtro)
            key = self.chip_filter
            self.chip_filter = None
            self.toggle_chip_filter(key)
            return
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
        self.fact_vals['handoff'].configure(cursor="hand2")  # clicar abre o recibo da retomada
        self.fact_vals['handoff'].bind("<Button-1>", lambda e: self.show_receipt())
        self.fact_tips = {}
        for key, col in (("fails", "col_fail"), ("ws", "ws"), ("handoff", "#0"), ("state", "#0")):
            self.fact_tips[key] = Tooltip(self.fact_vals[key], self, lambda c=col: (self.cell_tip(self.selected_row(), c) if self.selected_row() else ""))
        Tooltip(self.gauge, self, lambda: (self.cell_tip(self.selected_row(), "col_ctx") if self.selected_row() else ""),
                level_fn=lambda: self.cell_level(self.selected_row(), "col_ctx"))

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

    def cell_tip(self, r, col):
        """Dica de uma célula ou de um campo do painel ('ws'): explica o alerta e o que fazer. '' quando não há o que dizer."""
        if col == "col_ctx":
            if not r.get('ctx'):
                return "Sem dado de contexto nesta sessão."
            level = ctx_level(r['ctx'])
            text = (f"Contexto: {r['ctx']:,} tokens ({self.level_text(r['ctx'])}).".replace(",", ".")
                    + f" Atenção a partir de {fmt_tokens(CONTEXT_LIMITS['attention'])}, crítico a partir de "
                      f"{fmt_tokens(CONTEXT_LIMITS['critical'])} (botão Limites).")
            if level == 1:
                text += " Hora de preparar a retomada: gere o Dossiê."
            elif level == 2:
                text += " Retome já numa sessão nova (Dossiê ou Auto-Run) para não perder qualidade."
            return text
        if col == "col_fail":
            n = r.get('failures') or 0
            if not n:
                return ""
            return (f"{n} passo(s) de ferramenta terminaram sem sucesso (status diferente de 3). Os detalhes estão no Exportar diálogo "
                    "(passos marcados com ⚠) e no Dossiê, seção Falhas de ferramenta. O significado exato dos status 6 e 7 não está confirmado.")
        if col == "#0":
            bits = []
            if self.handoffs.get(r['cid']):
                bits.append(f"Retomada pelo Auto-Run na sessão nova {self.handoffs[r['cid']][:8]}.")
            if r.get('running'):
                bits.append("Em execução no Antigravity agora.")
            if r.get('killed'):
                bits.append("Encerrada à força no Antigravity.")
            return " ".join(bits)
        if col == "col_menu":
            return "Menu da sessão (também no botão direito ou Shift+F10)."
        if col == "col_title":
            return r['title'] if len(r.get('title') or "") > 40 else ""
        if col == "ws":
            paths = [x for x in (r.get('workspace') or "").split(", ") if x]
            if not paths:
                return ""
            missing = [x for x in paths if not os.path.isdir(x)]
            lines = "\n".join(("✖ " if x in missing else "✔ ") + x for x in paths)
            if missing:
                return (f"{len(missing)} de {len(paths)} pasta(s) do workspace não existe(m) mais neste computador; "
                        f"o Auto-Run anexa ao agy só as que existem.\n{lines}")
            return "Pastas encontradas neste computador:\n" + lines
        return ""

    def tree_cell_tip(self, iid, col):
        if not self.is_session(iid):
            return ""
        r = self.row_by_cid.get(self.cid_of(iid))
        return self.cell_tip(r, col) if r else ""

    @staticmethod
    def cell_level(r, col):
        """Nível de alerta da dica (0 comum, 1 atenção, 2 crítico): só a de contexto vira janela de alerta."""
        return ctx_level(r['ctx']) if r and col == "col_ctx" and r.get('ctx') else 0

    def tree_cell_level(self, iid, col):
        return self.cell_level(self.row_by_cid.get(self.cid_of(iid)), col) if self.is_session(iid) else 0

    def selected_row(self):
        ids = self.selected_session_ids()
        return self.row_by_cid.get(self.cid_of(ids[0])) if len(ids) == 1 else None

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
        F['handoff'].configure(text=(f"↪ {self.handoffs[cid][:8]}  ·  ver recibo" if self.handoffs.get(cid) else "-"),
                               fg=t['accent_text'] if self.handoffs.get(cid) else t['fg'])
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
        self.build_menu(iid).tk_popup(event.x_root, event.y_root)

    def menu_from_keyboard(self, _e=None):
        """Shift+F10 ou tecla Menu: abre o menu de contexto na linha com foco (ou na primeira selecionada)."""
        iid = self.tree.focus() or (self.tree.selection() or ("",))[0]
        if not iid:
            return "break"
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
        self.tree.see(iid)
        box = self.tree.bbox(iid) or (0, 0, 0, 0)
        self.build_menu(iid).tk_popup(self.tree.winfo_rootx() + box[0] + self.px(40), self.tree.winfo_rooty() + box[1] + box[3])
        return "break"

    def build_menu(self, iid):
        m = tk.Menu(self, tearoff=0)
        if self.is_session(iid):
            m.add_command(label="Copiar UUID", command=lambda: self.copy_uuid(iid))
            m.add_command(label="Abrir pasta do banco", command=lambda: self.open_folder(iid))
            m.add_command(label="Exportar diálogo", command=self.open_selected)
            m.add_command(label="Dossiê de retomada", command=lambda: self.start_export('dossier'))
            if self.handoffs.get(self.cid_of(iid)):
                m.add_command(label="Ver recibo da retomada", command=lambda: self.show_receipt(self.cid_of(iid)))
            m.add_separator()
        for status, text in (("aprovada", "✔ Aprovar"), ("arquivada", "▣ Arquivar"), ("pendente", "↩ Pendente")):
            m.add_command(label=text, command=lambda st=status: self.mark_selected(st))
        return m

    def show_receipt(self, cid=None):
        """Recibo da retomada da sessão (a selecionada, se não vier `cid`): janela com os detalhes, copiar e salvar."""
        if not cid:
            ids = self.selected_session_ids()
            cid = self.cid_of(ids[0]) if ids else ""
        rec = self.state.handoff_record(cid) if cid else None
        if not rec:
            messagebox.showinfo("Recibo de retomada", "Esta sessão ainda não foi retomada pelo Auto-Run.")
            return None
        return ReceiptDialog(self, rec, self.row_by_cid.get(cid))

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

    def on_source_change(self, event=None):
        self.source_idx = (event.widget if event is not None else self.src_box).current()
        self.sync_source_boxes()
        self.load_data()

    def sync_source_boxes(self):
        """O seletor de fonte existe na barra lateral e (só sem a barra) na linha da busca: os dois mostram sempre o mesmo."""
        values = [x[0] for x in self.sources]
        for box in (getattr(self, "src_box", None), getattr(self, "src_box_top", None)):
            if box is not None:
                box.configure(values=values)
                box.current(self.source_idx)

    def update_search_hint(self):
        if self.search_var.get():
            self.search_hint.place_forget()
        else:
            self.search_hint.place(in_=self.search_entry, x=self.px(2), rely=0.5, anchor="w")

    def refresh(self):
        """Relê as fontes do disco (pode haver novas pastas) e recarrega a fonte selecionada."""
        self.update_env_status()
        label = self.sources[self.source_idx][0]
        self.sources = discover_sources()
        self.source_idx = next((i for i, s in enumerate(self.sources) if s[0] == label), 0)
        self.sync_source_boxes()
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
        if hasattr(self, "cell_tips"):
            self.cell_tips.hide()  # as linhas (e os ids) vão ser recriados
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.sub_count = {}
        key, rev = SORT_FUNCS[self.sort_col], self.sort_rev
        two = self.density == "comfortable"
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
            proj_node = self.tree.insert("", tk.END, text=f"  {pname} ({len(rows)} sessões)", values=("",) * 9, tags=('proj',), image=self.icon("folder"))
            placed = set()

            def add(parent_iid, r):
                if r['cid'] in placed:
                    return  # proteção contra ciclos de parentesco
                placed.add(r['cid'])
                iid = self.tree.insert(parent_iid, tk.END, text=self.leaf_text(r['cid']), tags=self.row_tags(r['cid']), image=self.status_icon(r['cid']),
                                       values=(r['date'].replace(" ", "\n", 1) if two else r['date'], r['size'], ctx_label(r['ctx'], two_lines=two), r['steps'],
                                               f"⚠ {r['failures']}" if r['failures'] else "-", r['title'], r['agent'] or "-", r['cid'], "⋮"))
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
        if len(self.selected_session_ids()) > 1:  # vale para botão, menu e duplo clique
            messagebox.showinfo("Aviso", "Selecione uma sessão só: exportação e dossiê são de uma conversa por vez.")
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

    def auto_window(self):
        """A janela única do Auto-Run (cria se não existir)."""
        if self.auto_win and self.auto_win[0].winfo_exists():
            return self.auto_win[0]
        win = AutoRunWindow(self)
        self.auto_win = (win, win.log, win.primary)
        return win

    def drop_auto_window(self):
        """O lote não começou (nada marcado, sem agy): fecha a janela que ficou na etapa Preparar."""
        if self.auto_win and self.auto_win[0].step == "prepare":
            self.auto_win[0].destroy()

    def confirm_autorun(self, items, done):
        """Etapa 1 (Preparar) da janela única do Auto-Run: uma linha por sessão aprovada (as já retomadas vêm desmarcadas, salvo Refazer),
        simulação ou retomada real, modelo e pasta dos dossiês. Espera o Iniciar. Devolve {'dry_run', 'redo', 'model', 'cids', 'dossier_dir'}
        ou None se o usuário cancelar."""
        win = self.auto_window()
        win.show_prepare(items, done)
        self.confirm_win, self.confirm_checks, self.confirm_dry, self.confirm_redo = win, win.checks, win.dry, win.redo  # usados pelos testes
        self.confirm_redo_changed, self.confirm_go, self.model_var, self.model_box = win.redo_changed, win.go, win.model_var, win.model_box
        win.lift()
        win.focus_force()
        self._confirming = True
        try:
            self.wait_variable(win.decision)
        except tk.TclError:
            return None
        finally:
            self._confirming = False
        return win.result

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
        if self._confirming:  # a janela de preparação já está aberta: só traz para a frente
            if self.auto_win:
                self.auto_win[0].lift()
            return
        cands = []
        for grp in self.grouped.values():
            for r in grp:
                if self.states.get(r['cid']) == "aprovada" and r['fpath']:
                    meta = self.meta_for(r['cid'])
                    s = self.summaries.get(r['cid'], {})
                    cands.append({'cid': r['cid'], 'title': r['title'], 'fpath': r['fpath'], 'meta': meta,
                                  'workspace': str(val(s, 'workspace_uris')), 'project_id': str(val(s, 'project_id')),
                                  'workspace_label': meta['workspace'][-40:]})
        if not cands:
            messagebox.showinfo("Auto-Run", "Nenhuma sessão aprovada com arquivo nesta fonte. Aprove sessões primeiro (botão ✅ Aprovar).")
            return
        cands.sort(key=lambda x: x['title'].lower())
        opts = self.confirm_autorun(cands, set(self.handoffs))
        if not opts:
            return
        if 'cids' in opts:  # caixas marcadas na confirmação
            items = [c for c in cands if c['cid'] in opts['cids']]
            if not items:
                messagebox.showinfo("Auto-Run", "Nenhuma sessão marcada. Marque ao menos uma na lista para rodar.")
                self.drop_auto_window()
                return
        else:
            items = [c for c in cands if opts['redo'] or c['cid'] not in self.handoffs]
        if not items:
            messagebox.showinfo("Auto-Run", "Todas as sessões aprovadas já foram retomadas. Marque \"Refazer\" para repetir.")
            self.drop_auto_window()
            return
        agy = None
        if not opts['dry_run']:
            agy = find_agy()
            if not agy:
                messagebox.showerror("Auto-Run", "Não encontrei o agy. Confira se `agy --help` funciona no PowerShell, "
                                                 "ou defina AGY_EXE com o caminho do agy.exe.")
                self.drop_auto_window()
                return
        self.autorunning = True
        self.btn["autorun"].set_busy(True, "Executando…")
        self.update_actions()
        model = (opts.get('model') or '').strip()
        dossier_dir = opts.get('dossier_dir') or HANDOFF_DIR
        EXTRA_OWN_DIRS[:] = [dossier_dir]  # pasta escolhida pelo usuário: do app, nunca workspace de projeto (gate_owned)
        self.open_autorun_window(len(items), opts['dry_run'], model, items=items, dossier_dir=dossier_dir)
        runner = AutoRunner(items, self.state, lambda line: self.queue.put((0, 'auto_log', line)), agy=agy, dry_run=opts['dry_run'], model=model or None,
                            dossier_dir=dossier_dir, item_cb=lambda kind, cid, info: self.queue.put((0, 'auto_item', (kind, cid, info))))
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

    def open_autorun_window(self, n, dry_run, model="", items=None, dossier_dir=None):
        """Etapa Executando da janela única (cria a janela se a confirmação não passou por ela)."""
        win = self.auto_window()
        win.show_run(items or [], n, dry_run, model, dossier_dir or HANDOFF_DIR)
        win.lift()
        win.focus_force()
        mode = 'simulação (só dossiês)' if dry_run else 'agy --mode plan, modelo ' + (model or 'padrão do agy')
        self.append_auto(f"{n} sessão(ões) na fila. Modo: {mode}.")

    def append_auto(self, line):
        if not self.auto_win:
            return
        win, txt, _btn = self.auto_win
        txt.configure(state=tk.NORMAL)
        txt.insert(tk.END, line + "\n")
        txt.see(tk.END)
        txt.configure(state=tk.DISABLED)
        win.add_line(line)

    def cancel_autorun(self):
        if self.runner and self.autorunning:
            self.append_auto("Cancelando…")
            self.runner.cancel()
        elif self.auto_win:
            self.auto_win[0].destroy()

    def close_autorun(self, win):
        """Botão e X da janela do Auto-Run: agem só sobre ela. Preparar: cancela. Executando: cancela o lote. Resumo: fecha.
        Outra janela que tenha ficado aberta apenas fecha, sem tocar no lote em curso."""
        if self.auto_win and self.auto_win[0] is win:
            if win.step == "prepare":
                win.cancel_prepare()
            else:
                self.cancel_autorun()
        else:
            try:
                win.destroy()
            except tk.TclError:
                pass

    def on_auto_event(self, kind, payload):
        if kind == 'auto_log':
            self.append_auto(payload)
            return
        if kind == 'auto_item':  # estado de uma sessão do lote (começou, terminou, não executada)
            if self.auto_win:
                self.auto_win[0].item_event(*payload)
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
            n = lambda k, um, varios: f"{payload[k]} {um if payload[k] == 1 else varios}"
            self.append_auto(f"Fim. ✔ {n('ok', 'retomada', 'retomadas')} · ▤ {n('dossier', 'dossiê', 'dossiês')} (simulação) · "
                             f"✖ {n('failed', 'falha', 'falhas')} · » {n('skipped', 'não executada', 'não executadas')}"
                             + (f" · motivo: {payload['aborted']}" if payload['aborted'] else ""))
        if self.auto_win:
            self.auto_win[0].finish(payload)  # etapa Resumo; o botão passa a Fechar
            fim = "erro" if 'error' in payload else ("concluído com problemas" if payload.get('failed') or payload.get('aborted') else "concluído")
            self.auto_win[0].title("Auto-Run — " + fim)  # antes ficava "executando" depois do Fim
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
        fonts = len(app.fonts_loaded)
        icon = "ok" if os.path.isfile(os.path.join(asset_dir(), "app-256.png")) and getattr(app, "_app_icons", None) else "AUSENTE"
        app.destroy()
        msg = f"OK (v{__version__}; {fts}; {fonts} fontes registradas; ícone {icon}{area})" if done else "FALHA: a carga não terminou em 60 s"
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
