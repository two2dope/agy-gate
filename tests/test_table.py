import os, sys, sqlite3, tempfile, time, json
root = tempfile.mkdtemp(prefix="agytable_")
base = os.path.join(root, "gemini")
os.environ.update(HOME=os.path.join(root, "home"), ANTIGRAVITY_HOME=base, LOCALAPPDATA=os.path.join(root, "local"))
U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)
ant = os.path.join(base, "antigravity"); conv = os.path.join(ant, "conversations"); os.makedirs(conv); os.makedirs(os.path.join(base, "config", "projects"))
c = sqlite3.connect(os.path.join(ant, "conversation_summaries.db"))
c.execute("CREATE TABLE conversation_summaries(conversation_id TEXT, title TEXT, preview TEXT, step_count INT, last_modified_time TEXT, project_id TEXT, workspace_uris TEXT, agent_name TEXT, parent_conversation_id TEXT)")
for i in range(1, 4): c.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?,?,?)", (U(i), "", "sessao %d" % i, i, "2026-10-26T1%d:00:00Z" % i, "", "", "", ""))
c.commit(); c.close()
for i in range(1, 4):
    d = sqlite3.connect(os.path.join(conv, U(i) + ".db")); d.execute("CREATE TABLE steps(idx INTEGER PRIMARY KEY, step_type INT, status INT, step_payload BLOB, error_details BLOB)"); d.commit(); d.close()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G
from tkinter import messagebox, ttk
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, **k: None)
G.setup_logging()

# 1. Consumo: tokens, % do nível crítico, medidor de 5 células e marca; versão em 2 linhas
assert G.ctx_label(0) == "-"
assert G.ctx_label(25_400) == "25k  \u25a0\u25a1\u25a1\u25a1\u25a1  10%", G.ctx_label(25_400)
assert G.ctx_label(160_000).endswith("64% \u26a0") and G.ctx_label(260_000).endswith("104% \u2021".replace("\u2021", "\u203c"))
assert G.ctx_label(25_400, two_lines=True) == "25k \u00b7 10%\n\u25a0\u25a1\u25a1\u25a1\u25a1 segura"
assert G.ctx_label(160_000, two_lines=True).endswith("atenção") and G.ctx_label(260_000, two_lines=True).endswith("crítica")
assert G.HEADINGS["col_ctx"] == "Consumo (tokens)"

def wait(a):
    end = time.time() + 20
    while a.loading and time.time() < end: a.update(); time.sleep(0.01)
    for _ in range(6): a.update(); time.sleep(0.02)
def iid(a, n): return next(i for i in a.iter_sessions() if a.cid_of(i) == U(n))
def vals(a, n): return a.tree.item(iid(a, n), "values")
def rowheight(a): return int(ttk.Style().lookup("Treeview", "rowheight"))

app = G.AntigravityGateApp(); app.geometry("1240x720+0+0"); wait(app)

# 2. densidade: compacta por padrão (1 linha); confortável tem 2 linhas e é lembrada
assert app.density == "compact" and rowheight(app) == app.px(30)
assert "\n" not in vals(app, 1)[G.COL_DATE] and "\n" not in str(vals(app, 1)[G.COL_CTX])
app.row_by_cid[U(1)]['ctx'] = 160_000; app.populate(); app.update()
assert vals(app, 1)[G.COL_CTX] == G.ctx_label(160_000)
app.set_density("comfortable"); app.update()
assert rowheight(app) == app.px(46) and json.load(open(G.SETTINGS_FILE))["density"] == "comfortable"
d = vals(app, 1)[G.COL_DATE]; assert "\n" in d and d.replace("\n", " ") == app.row_by_cid[U(1)]['date']
assert vals(app, 1)[G.COL_CTX] == G.ctx_label(160_000, two_lines=True) and "atenção" in vals(app, 1)[G.COL_CTX]
app.show_theme_menu(); app.update(); p = app.theme_picker
assert [r[3] for r in p.rows[-2:]] == [False, True], "seletor marca a densidade atual"
p.choose(len(p.rows) - 2); app.update(); assert app.density == "compact" and rowheight(app) == app.px(30) and "\n" not in vals(app, 1)[G.COL_DATE]
app.set_density("comfortable"); app.destroy()
app = G.AntigravityGateApp(); wait(app); assert app.density == "comfortable" and rowheight(app) == app.px(46), "densidade lembrada"
app.set_density("compact")

# 3. coluna Ações (⋮): última, abre o menu da linha com o clique esquerdo; nas pastas e nos outros campos o clique segue normal
cols = list(app.tree["displaycolumns"]); assert cols[-1] == "col_menu" and app.menu_col_id() == f"#{len(cols)}"
assert vals(app, 1)[-1] == "\u22ee" and app.tree.item(app.tree.get_children()[0], "values")[-1] == ""
app.tree.xview_moveto(1.0); app.update()
class Ev: pass
def click(item, col):
    bx, by, bw, bh = app.tree.bbox(item, col); e = Ev(); e.x, e.y, e.x_root, e.y_root = bx + bw // 2, by + bh // 2, 10, 10; return e
opened = []; app.show_menu = lambda e: opened.append(e)
assert app.on_tree_click(click(iid(app, 2), "col_menu")) == "break" and len(opened) == 1
assert app.on_tree_click(click(iid(app, 2), "col_uuid")) is None and len(opened) == 1, "outra coluna não abre o menu"
assert app.on_tree_click(click(app.tree.get_children()[0], "col_menu")) is None and len(opened) == 1, "pasta de projeto não tem menu pela coluna"
assert "Menu da sessão" in app.cell_tip(app.row_by_cid[U(1)], "col_menu")
app.destroy(); print("TODOS OS TESTES DA TABELA OK")
