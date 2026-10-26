import os, sys, sqlite3, tempfile, time, json
root = tempfile.mkdtemp(prefix="agytheme_")
base = os.path.join(root, "gemini")
os.environ.update(HOME=os.path.join(root, "home"), ANTIGRAVITY_HOME=base, LOCALAPPDATA=os.path.join(root, "local"))
U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)
ant = os.path.join(base, "antigravity"); conv = os.path.join(ant, "conversations"); os.makedirs(conv); os.makedirs(os.path.join(base, "config", "projects"))
c = sqlite3.connect(os.path.join(ant, "conversation_summaries.db"))
c.execute("CREATE TABLE conversation_summaries(conversation_id TEXT, title TEXT, preview TEXT, step_count INT, last_modified_time TEXT, project_id TEXT, workspace_uris TEXT, agent_name TEXT, parent_conversation_id TEXT)")
for i in range(1, 5): c.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?,?,?)", (U(i), "", "sessao %d" % i, i, "2026-10-26T1%d:00:00Z" % i, "", "", "", ""))
c.commit(); c.close()
for i in range(1, 5):
    d = sqlite3.connect(os.path.join(conv, U(i) + ".db")); d.execute("CREATE TABLE steps(idx INTEGER PRIMARY KEY, step_type INT, status INT, step_payload BLOB, error_details BLOB)"); d.commit(); d.close()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G
from tkinter import messagebox
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, **k: None)
messagebox.askyesno = lambda *a, **k: True
def wait(a):
    end = time.time() + 20
    while a.loading and time.time() < end: a.update(); time.sleep(0.01)
    for _ in range(6): a.update(); time.sleep(0.02)
def iid(a, n): return next(i for i in a.iter_sessions() if a.cid_of(i) == U(n))

import subprocess, tkinter as tk
app = G.AntigravityGateApp(); app.geometry("1240x720+0+0"); wait(app)
btn = app.btn['theme']
assert app.theme_picker is None and btn.text == "Escuro ▾", btn.text

# abre: 8 temas + 3 modos de ícone, atual selecionado
btn.command(); app.update()
p = app.theme_picker; assert isinstance(p, G.ThemePicker) and p.winfo_exists()
assert len(p.rows) == 8 + 3, len(p.rows)
assert [r[3] for r in p.rows[:8]].count(True) == 1 and p.rows[0][3] and p.cur == 0
assert sum(1 for r in p.rows[8:] if r[3]) == 1
# dentro da janela e alinhado ao botão
assert p.winfo_rootx() >= 0 and p.winfo_rooty() >= btn.winfo_rooty() + btn.winfo_height()
# clicar de novo no botão fecha (alterna)
app.show_theme_menu(); app.update(); assert app.theme_picker is None and not p.winfo_exists()

# teclado: Down x3 + Enter => 4º tema (cyber); botão acompanha o nome
app.show_theme_menu(); app.update(); p = app.theme_picker
p.event_generate("<Down>"); p.event_generate("<Down>"); p.event_generate("<Down>"); app.update()
assert p.cur == 3, p.cur
p.event_generate("<Return>"); app.update(); wait(app)
assert app.theme_key == "cyber" and app.theme_picker is None and btn.text == "Cyber Synthwave ▾", (app.theme_key, btn.text)
assert app.settings['theme'] == "cyber"
# a lista reflete o tema novo (marcado e cores)
app.show_theme_menu(); app.update(); p = app.theme_picker
assert p.rows[3][3] and p.t['panel'] == G.THEMES['cyber']['panel']
# Up no primeiro item dá a volta
p.highlight(0); p.event_generate("<Up>"); app.update(); assert p.cur == len(p.rows) - 1
# Esc fecha
p.event_generate("<Escape>"); app.update(); assert app.theme_picker is None

# clique no item de ícone (não troca o tema)
app.show_theme_menu(); app.update(); p = app.theme_picker
p.choose(len(p.rows) - 1); app.update(); wait(app)
assert app.icon_mode == "none" and app.theme_key == "cyber" and app.settings['icons'] == "none"
app.set_icon_mode("symbol")

# clique fora fecha; clique dentro não
app.show_theme_menu(); app.update(); p = app.theme_picker
class E: pass
e = E(); e.x_root, e.y_root = p.winfo_rootx() + 5, p.winfo_rooty() + 5; p.click_outside(e); assert app.theme_picker is p
e.x_root, e.y_root = 1, 1; p.click_outside(e); app.update(); assert app.theme_picker is None

# todos os temas: lista abre, texto legível (fg/sel_fg sobre painel/seleção já cobertos em test_theme), botão sem quebrar em janela estreita
for key in G.THEME_ORDER:
    app.set_theme(key); app.update()
    assert btn.text == G.THEMES[key]['name'] + " ▾"
    app.show_theme_menu(); app.update(); p = app.theme_picker
    assert p.winfo_width() >= btn.winfo_width() and p.winfo_exists(); p.close()
    app.update()
app.geometry("760x600+0+0"); wait(app); app.update()
assert btn.winfo_ismapped() and btn.winfo_x() + btn.winfo_width() <= app.winfo_width() + 2, (btn.winfo_x(), btn.winfo_width(), app.winfo_width())
app.show_theme_menu(); app.update(); app.theme_picker.close()
# persistência
app.set_theme("mecha"); app.destroy(); app = G.AntigravityGateApp(); wait(app)
assert app.theme_key == "mecha" and app.btn['theme'].text == "Mecha ▾"
app.destroy()
print("TODOS OS TESTES OK")
