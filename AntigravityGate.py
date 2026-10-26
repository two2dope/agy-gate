import os
import sqlite3
import glob
import re
import json
import logging
import urllib.parse
from contextlib import closing
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

BASE_DIR = os.environ.get("ANTIGRAVITY_HOME", r"C:\Users\Thomáz\.gemini")
SUM_DB = os.path.join(BASE_DIR, "antigravity", "conversation_summaries.db")
PROJECTS_DIR = os.path.join(BASE_DIR, "config", "projects")
DESKTOP_DIR = os.path.join(os.path.expanduser("~"), "Desktop")
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "AntigravityGate")
LOG_FILE = os.path.join(LOG_DIR, "gate.log")

UUID_DB_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.db$', re.IGNORECASE)

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


class AntigravityGateApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AntigravityGate 🚀 - Inspetor e Gestor Agêntico")
        self.geometry("1200x650")

        # Estado do Tema (Dark por padrão, com suporte a Light)
        self.dark_mode = True
        self.apply_theme()

        self.create_widgets()
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

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.apply_theme()
        self.load_data()

    def create_widgets(self):
        # Top Frame - Controles, Tema e Ações
        self.top_frame = tk.Frame(self, bg=self.bg_color, pady=10, padx=10)
        self.top_frame.pack(fill=tk.X)

        lbl_title = tk.Label(self.top_frame, text="🚀 AntigravityGate - Gestão de Contexto e Curadoria", fg=self.fg_color, bg=self.bg_color, font=('Segoe UI', 12, 'bold'))
        lbl_title.pack(side=tk.LEFT)

        # Ações ainda sem implementação: desabilitadas para não afirmar efeito que não ocorre.
        btn_auto = tk.Button(self.top_frame, text="⚡ Auto-Run (em breve)", bg=self.header_bg, disabledforeground="#888888", font=('Segoe UI', 9, 'bold'), relief=tk.FLAT, state=tk.DISABLED)
        btn_auto.pack(side=tk.RIGHT, padx=5)

        btn_bulk_app = tk.Button(self.top_frame, text="✅ Aprovar (em breve)", bg=self.header_bg, disabledforeground="#888888", font=('Segoe UI', 9), relief=tk.FLAT, state=tk.DISABLED)
        btn_bulk_app.pack(side=tk.RIGHT, padx=5)

        btn_theme = tk.Button(self.top_frame, text="🌓 Alternar Tema", bg=self.header_bg, fg=self.fg_color, font=('Segoe UI', 9), relief=tk.FLAT, command=self.toggle_theme)
        btn_theme.pack(side=tk.RIGHT, padx=5)

        btn_open = tk.Button(self.top_frame, text="📄 Exportar Diálogo Rico", bg=self.accent_color, fg="#ffffff", font=('Segoe UI', 9, 'bold'), relief=tk.FLAT, command=self.open_selected)
        btn_open.pack(side=tk.RIGHT, padx=5)

        # Barra de status: contagem de sessões e avisos de leitura
        self.status = tk.Label(self, anchor=tk.W, padx=10, pady=4, font=('Segoe UI', 9))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        # Tabela (Treeview) com métricas de contexto
        columns = ("col_date", "col_size", "col_steps", "col_title", "col_uuid")
        self.tree = ttk.Treeview(self, columns=columns, show="tree headings", selectmode="browse")

        self.tree.heading("#0", text="Projeto / Sessão", anchor=tk.W)
        self.tree.heading("col_date", text="Modificação", anchor=tk.W)
        self.tree.heading("col_size", text="Tamanho (KB)", anchor=tk.CENTER)
        self.tree.heading("col_steps", text="Passos", anchor=tk.CENTER)
        self.tree.heading("col_title", text="Título / Contexto Inicial", anchor=tk.W)
        self.tree.heading("col_uuid", text="UUID", anchor=tk.W)

        self.tree.column("#0", width=200, anchor=tk.W)
        self.tree.column("col_date", width=130, anchor=tk.W)
        self.tree.column("col_size", width=90, anchor=tk.CENTER)
        self.tree.column("col_steps", width=60, anchor=tk.CENTER)
        self.tree.column("col_title", width=420, anchor=tk.W)
        self.tree.column("col_uuid", width=170, anchor=tk.W)

        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=10)

        self.tree.bind("<Double-1>", lambda e: self.open_selected())

    def warn(self, msg, exc=None):
        """Registra falha de leitura no log e conta para a barra de status."""
        self.warnings += 1
        if exc is not None:
            log.warning("%s: %s: %s", msg, type(exc).__name__, exc)
        else:
            log.warning("%s", msg)

    def set_status(self, total):
        text = f"{total} sessões"
        if self.warnings:
            text += f"  |  ⚠ {self.warnings} aviso(s) de leitura — ver {LOG_FILE}"
        self.status.configure(text=text, bg=self.header_bg, fg=self.fg_color)

    def load_data(self):
        self.warnings = 0
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not os.path.isdir(BASE_DIR):
            self.warn(f"Pasta base inexistente: {BASE_DIR}")

        self.proj_map = {'outside-of-project': 'Outside of Project'}
        self.uri_to_proj = {}
        if os.path.exists(PROJECTS_DIR):
            for p_file in glob.glob(os.path.join(PROJECTS_DIR, '*.json')):
                try:
                    with open(p_file, 'r', encoding='utf-8') as f:
                        d = json.load(f)
                    if not isinstance(d, dict):
                        raise ValueError("JSON de projeto não é um objeto")
                    pid = d.get('id') or ''
                    pname = d.get('name') or pid
                    self.proj_map[pid] = pname
                    for res in (d.get('projectResources') or {}).get('resources') or []:
                        u = res.get('folderUri') or (res.get('gitFolder') or {}).get('folderUri')
                        if u:
                            self.uri_to_proj[urllib.parse.unquote(u).lower()] = pname
                except Exception as e:
                    self.warn(f"Projeto ilegível: {p_file}", e)

        self.summaries = {}
        if os.path.exists(SUM_DB):
            try:
                with open_ro(SUM_DB) as conn:
                    conn.row_factory = sqlite3.Row
                    for r in conn.execute("SELECT * FROM conversation_summaries").fetchall():
                        self.summaries[r['conversation_id']] = dict(r)
            except Exception as e:
                self.warn(f"Falha ao ler {SUM_DB}", e)

        self.db_files = {}
        for root, _dirs, files in os.walk(BASE_DIR):
            for f in files:
                if UUID_DB_RE.match(f):
                    cid = os.path.splitext(f)[0]
                    self.db_files[cid] = os.path.join(root, f)

        grouped = {}
        all_cids = set(self.db_files.keys()) | set(self.summaries.keys())

        for cid in all_cids:
            s = self.summaries.get(cid, {})
            fpath = self.db_files.get(cid, '')

            title = str(val(s, 'title')).strip()
            preview = str(val(s, 'preview')).strip()
            step_count = to_int(s.get('step_count'))
            last_mod = fmt_time(s.get('last_modified_time'))
            pid = str(val(s, 'project_id'))
            w_uris = str(val(s, 'workspace_uris'))
            file_size_kb = 0

            if fpath and os.path.exists(fpath):
                file_size_kb = round(os.path.getsize(fpath) / 1024, 1)
                if not last_mod:
                    last_mod = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime('%Y-%m-%d %H:%M:%S')
                try:
                    with open_ro(fpath) as c2:
                        tables = [r[0] for r in c2.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                        if 'steps' in tables:
                            cnt = c2.execute("SELECT COUNT(*) FROM steps").fetchone()[0]
                            if cnt > step_count:
                                step_count = cnt
                            if not preview:
                                first_rows = c2.execute("SELECT * FROM steps LIMIT 3").fetchall()
                                for r in first_rows:
                                    text = "\n".join(as_text(col) for col in r)
                                    text_chunks = re.findall(r'[A-Za-zÀ-ÿ0-9_/\-\.,\?!:;\"\' ]{15,}', text)
                                    if text_chunks:
                                        preview = text_chunks[0][:150]
                                        break
                except Exception as e:
                    self.warn(f"Falha ao ler sessão {cid}", e)

            proj_name = self.proj_map.get(pid, '')
            w_decoded = urllib.parse.unquote(w_uris)
            if not proj_name or proj_name == 'Outside of Project':
                for u_key, p_val in self.uri_to_proj.items():
                    if u_key in w_decoded.lower():
                        proj_name = p_val
                        break
            if not proj_name:
                proj_name = 'Outside of Project'

            if not title or title.startswith('Sessão '):
                title = (preview[:60] + '...') if len(preview) > 60 else (preview or f"Conversa {cid[:8]}")

            # Alerta visual de Context Rot se tamanho > 1500 KB
            size_label = f"{file_size_kb} KB" + (" ⚠️ [Rot]" if file_size_kb > 1500 else "")

            if proj_name not in grouped:
                grouped[proj_name] = []

            grouped[proj_name].append({
                'cid': cid,
                'date': last_mod[:19],
                'size': size_label,
                'steps': step_count,
                'title': title,
                'fpath': fpath
            })

        for pname in sorted(grouped.keys()):
            proj_node = self.tree.insert("", tk.END, text=f"📁 {pname} ({len(grouped[pname])} sessões)", values=("", "", "", "", ""))
            sorted_convs = sorted(grouped[pname], key=lambda x: x['date'], reverse=True)
            for c in sorted_convs:
                self.tree.insert(proj_node, tk.END, text="    💬 Sessão", values=(c['date'], c['size'], c['steps'], c['title'], c['cid']))

        if self.tree.get_children():
            self.tree.item(self.tree.get_children()[0], open=True)

        self.set_status(len(all_cids))

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
        if not values or len(values) < 5:
            return

        cid = values[4]
        s = self.summaries.get(cid, {})
        fpath = self.db_files.get(cid, '')
        if not fpath:
            for root, _dirs, files in os.walk(BASE_DIR):
                target_file = f"{cid}.db"
                if target_file in files:
                    fpath = os.path.join(root, target_file)
                    break

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
