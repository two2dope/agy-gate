import os
import sqlite3
import glob
import re
import json
import logging
import queue
import threading
import urllib.parse
from contextlib import closing
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

BASE_DIR = os.environ.get("ANTIGRAVITY_HOME", r"C:\Users\Thomáz\.gemini")
ACTIVE_SUM_DB = os.path.join(BASE_DIR, "antigravity", "conversation_summaries.db")
ACTIVE_CONV_DIR = os.path.join(BASE_DIR, "antigravity", "conversations")
ACTIVE_LABEL = "Ativas (antigravity/conversations)"
PROJECTS_DIR = os.path.join(BASE_DIR, "config", "projects")
DESKTOP_DIR = os.path.join(os.path.expanduser("~"), "Desktop")
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "AntigravityGate")
LOG_FILE = os.path.join(LOG_DIR, "gate.log")

# Alerta de Context Rot: tokens de entrada da última resposta do modelo (f2 + f5 de step_payload.f5.f9).
# Padrão provisório; ajuste com a variável de ambiente AGY_ROT_TOKENS.
ROT_TOKENS = int(os.environ.get("AGY_ROT_TOKENS", "150000"))

UUID_DB_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.db$', re.IGNORECASE)

# Posição das colunas na árvore (valores de cada linha de sessão)
COL_DATE, COL_SIZE, COL_CTX, COL_STEPS, COL_TITLE, COL_UUID = range(6)

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
            'ctx': ctx,
            'steps': step_count,
            'title': title,
            'fpath': fpath,
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
        self.warnings = 0
        self.proj_map, self.summaries, self.db_files = {}, {}, {}

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

        btn_bulk_app = self.themed_widget(tk.Button(self.top_frame, text="✅ Aprovar (em breve)", disabledforeground="#888888", font=('Segoe UI', 9), relief=tk.FLAT, state=tk.DISABLED), bg="header_bg")
        btn_bulk_app.pack(side=tk.RIGHT, padx=5)

        btn_theme = self.themed_widget(tk.Button(self.top_frame, text="🌓 Alternar Tema", font=('Segoe UI', 9), relief=tk.FLAT, command=self.toggle_theme), bg="header_bg", fg="fg_color")
        btn_theme.pack(side=tk.RIGHT, padx=5)

        btn_open = self.themed_widget(tk.Button(self.top_frame, text="📄 Exportar Diálogo Rico", fg="#ffffff", font=('Segoe UI', 9, 'bold'), relief=tk.FLAT, command=self.open_selected), bg="accent_color")
        btn_open.pack(side=tk.RIGHT, padx=5)

        # Barra de status: fonte, contagem de sessões, carga em andamento e avisos de leitura
        self.status = self.themed_widget(tk.Label(self, anchor=tk.W, padx=10, pady=4, font=('Segoe UI', 9)), bg="header_bg", fg="fg_color")
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        # Tabela (Treeview) com métricas de contexto
        columns = ("col_date", "col_size", "col_ctx", "col_steps", "col_title", "col_uuid")
        self.tree = ttk.Treeview(self, columns=columns, show="tree headings", selectmode="browse")

        self.tree.heading("#0", text="Projeto / Sessão", anchor=tk.W)
        self.tree.heading("col_date", text="Modificação", anchor=tk.W)
        self.tree.heading("col_size", text="Tamanho", anchor=tk.CENTER)
        self.tree.heading("col_ctx", text="Contexto (tokens)", anchor=tk.CENTER)
        self.tree.heading("col_steps", text="Passos", anchor=tk.CENTER)
        self.tree.heading("col_title", text="Título / Contexto Inicial", anchor=tk.W)
        self.tree.heading("col_uuid", text="UUID", anchor=tk.W)

        self.tree.column("#0", width=200, anchor=tk.W)
        self.tree.column("col_date", width=130, anchor=tk.W)
        self.tree.column("col_size", width=90, anchor=tk.CENTER)
        self.tree.column("col_ctx", width=130, anchor=tk.CENTER)
        self.tree.column("col_steps", width=60, anchor=tk.CENTER)
        self.tree.column("col_title", width=380, anchor=tk.W)
        self.tree.column("col_uuid", width=170, anchor=tk.W)

        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        # Barra empacotada antes da árvore: não some quando a janela encolhe.
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=10)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tree.bind("<Double-1>", lambda e: self.open_selected())
        self.bind("<F5>", lambda e: self.refresh())

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
        grouped = res['grouped']

        for pname in sorted(grouped.keys()):
            proj_node = self.tree.insert("", tk.END, text=f"📁 {pname} ({len(grouped[pname])} sessões)", values=("",) * 6)
            for c in sorted(grouped[pname], key=lambda x: x['date'], reverse=True):
                ctx = fmt_tokens(c['ctx']) + (" ⚠️ [Rot]" if c['ctx'] >= ROT_TOKENS else "")
                self.tree.insert(proj_node, tk.END, text="    💬 Sessão", values=(c['date'], c['size'], ctx, c['steps'], c['title'], c['cid']))

        if self.tree.get_children():
            self.tree.item(self.tree.get_children()[0], open=True)

        text = f"{label}  |  {res['total']} sessões"
        if self.warnings:
            text += f"  |  ⚠ {self.warnings} aviso(s) de leitura — ver {LOG_FILE}"
        self.set_status(text)

    def open_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Aviso", "Selecione uma conversa na tabela.")
            return

        node_id = selected[0]
        if not self.tree.parent(node_id):
            messagebox.showinfo("Aviso", "Clique numa conversa específica dentro da pasta do projeto.")
            return

        values = self.tree.item(node_id, 'values')
        if not values or len(values) <= COL_UUID:
            return

        cid = values[COL_UUID]
        s = self.summaries.get(cid, {})
        fpath = self.db_files.get(cid, '')

        pid = str(val(s, 'project_id', 'Outside of Project'))
        proj_name = self.proj_map.get(pid, pid)
        w_uris = urllib.parse.unquote(str(val(s, 'workspace_uris', 'Não registado')))
        last_mod = fmt_time(s.get('last_modified_time')) or 'Desconhecido'
        step_count = val(s, 'step_count', 'Desconhecido')

        out_md = os.path.join(DESKTOP_DIR, f"AntigravityGate_Relatorio_{cid[:8]}.md")
        try:
            with open(out_md, 'w', encoding='utf-8') as f:
                f.write("# Relatório de Contexto e Localização (AntigravityGate 🚀)\n\n")
                f.write("| Parâmetro Técnico | Registo do Sistema |\n")
                f.write("| :--- | :--- |\n")
                f.write(f"| UUID da Sessão | {cid} |\n")
                f.write(f"| Projeto Vinculado | {proj_name} (ID: {pid}) |\n")
                f.write(f"| Caminho Físico do Banco | {fpath} |\n")
                f.write(f"| Workspace de Origem | {w_uris} |\n")
                f.write(f"| Última Modificação | {last_mod} |\n")
                f.write(f"| Total de Passos | {step_count} |\n\n")
                f.write("---\n\n## Histórico de Interações\n\n")

                if fpath and os.path.exists(fpath):
                    with open_ro(fpath) as conn:
                        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                        if 'steps' in tables:
                            cursor = conn.execute("SELECT * FROM steps")
                            seen = set()
                            for idx, row in enumerate(cursor):
                                lines = []
                                for col in row:
                                    if isinstance(col, (bytes, str)):
                                        txt = as_text(col)
                                        for m in re.findall(r'[A-Za-zÀ-ÿ0-9_/\-\.,\?!:;\"\' \n\t\(\)\[\]#*+=<>]{30,}', txt):
                                            c = m.strip()
                                            if not any(x in c.lower() for x in ['google.protobuf', '.gemini', 'user_uploaded', 'editor_transcript']):
                                                if len(c) > 30 and c not in seen:
                                                    seen.add(c)
                                                    lines.append(c)
                                if lines:
                                    f.write(f"### Interação #{idx}\n\n")
                                    for l in lines:
                                        f.write(f"{l}\n\n")
                                    f.write("---\n\n")
        except Exception as e:
            log.exception("Falha ao exportar %s", cid)
            messagebox.showerror("Erro", f"Não foi possível gravar {out_md}:\n{e}")
            return

        opener = getattr(os, "startfile", None)
        if opener is None:
            messagebox.showinfo("Relatório gerado", f"Relatório salvo em:\n{out_md}")
            return
        try:
            opener(out_md)
        except OSError as e:
            log.warning("Relatório salvo, mas não abriu: %s", e)
            messagebox.showinfo("Relatório gerado", f"Relatório salvo em:\n{out_md}\n\nNão abriu automaticamente: {e}")


if __name__ == "__main__":
    setup_logging()
    app = AntigravityGateApp()
    app.mainloop()
