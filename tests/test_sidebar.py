import os, sys, sqlite3, tempfile, time, json
root = tempfile.mkdtemp(prefix="agyside_")
base = os.path.join(root, "gemini")
os.environ.update(HOME=os.path.join(root, "home"), ANTIGRAVITY_HOME=base, LOCALAPPDATA=os.path.join(root, "local"))
U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)
ant = os.path.join(base, "antigravity"); conv = os.path.join(ant, "conversations"); os.makedirs(conv); proj = os.path.join(base, "config", "projects"); os.makedirs(proj)
for pid, name in (("p1", "Alpha"), ("p2", "Beta")): json.dump({"id": pid, "name": name}, open(os.path.join(proj, pid + ".json"), "w"))
c = sqlite3.connect(os.path.join(ant, "conversation_summaries.db"))
c.execute("CREATE TABLE conversation_summaries(conversation_id TEXT, title TEXT, preview TEXT, step_count INT, last_modified_time TEXT, project_id TEXT, workspace_uris TEXT, agent_name TEXT, parent_conversation_id TEXT)")
for i, pid in ((1, "p1"), (2, "p1"), (3, "p2"), (4, "")): c.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?,?,?)", (U(i), "", "sessao %d" % i, i, "2026-10-26T1%d:00:00Z" % i, pid, "", "", ""))
c.commit(); c.close()
for i in range(1, 5):
    d = sqlite3.connect(os.path.join(conv, U(i) + ".db")); d.execute("CREATE TABLE steps(idx INTEGER PRIMARY KEY, step_type INT, status INT, step_payload BLOB, error_details BLOB)"); d.commit(); d.close()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G
from tkinter import messagebox
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, **k: None)
messagebox.askyesno = lambda *a, **k: True
G.setup_logging()

def wait(a):
    end = time.time() + 20
    while a.loading and time.time() < end: a.update(); time.sleep(0.01)
    for _ in range(6): a.update(); time.sleep(0.02)
def settle(a): a.update(); time.sleep(0.25); a.update()
def iid(a, n): return next(i for i in a.iter_sessions() if a.cid_of(i) == U(n))
def shown(a): return {a.cid_of(i) for i in a.iter_sessions()}
def counts(a): return {k: int(it.count.cget("text")) for k, it in a.side_items.items()}

app = G.AntigravityGateApp(); app.geometry("1240x720+0+0"); wait(app); settle(app)

# 1. barra lateral aberta ao iniciar, com categorias e projetos
assert app.sidebar.winfo_manager() == "pack" and app.tabs_frame.winfo_manager() == "pack"
assert list(app.side_items) == ["pendente", "rot", "crit", "aprovada", "arquivada"]
assert counts(app) == dict(pendente=4, rot=0, crit=0, aprovada=0, arquivada=0), counts(app)
assert [(i.name.cget("text"), i.count.cget("text")) for i in app.proj_items] == [("Alpha", "2"), ("Beta", "1"), ("Outside of Project", "1")]
assert app.tabs["todas"].on and not app.tabs["aguardando"].on

# 2. contagens acompanham os estados; "aguardando" = aprovada sem retomada
for ids, st in (((1, 2), "aprovada"), ((3,), "arquivada")):
    app.tree.selection_set([iid(app, n) for n in ids]); app.mark_selected(st); app.update()
assert counts(app) == dict(pendente=1, rot=0, crit=0, aprovada=2, arquivada=1), counts(app)
assert app.tabs["aguardando"].cget("text") == "Aprovadas aguardando · 2"
app.handoffs[U(1)] = "aaaaaaaa-0000"; app.update_chips()
assert app.tabs["aguardando"].cget("text") == "Aprovadas aguardando · 1" and app.chip_match("aguardando", app.row_by_cid[U(2)]) and not app.chip_match("aguardando", app.row_by_cid[U(1)])

# 3. um filtro só: categoria e abas marcam o mesmo estado, e clicar de novo tira o filtro
app.side_items["aprovada"].command(); app.update()
assert app.chip_filter == "aprovada" and shown(app) == {U(1), U(2)} and app.side_items["aprovada"].on and not app.tabs["todas"].on
app.side_items["aprovada"].command(); app.update()
assert app.chip_filter is None and len(shown(app)) == 4 and app.tabs["todas"].on and not app.side_items["aprovada"].on
app.tabs["aguardando"].command(); app.update()
assert app.chip_filter == "aguardando" and shown(app) == {U(2)} and app.tabs["aguardando"].on and not app.side_items["aprovada"].on
app.tabs["aguardando"].command(); app.update(); assert shown(app) == {U(2)}, "clicar na aba ativa não desfaz"
app.tabs["arquivada"].command(); app.update()
assert shown(app) == {U(3)} and app.side_items["arquivada"].on and app.tabs["arquivada"].on and not app.tabs["aguardando"].on
app.tabs["todas"].command(); app.update(); assert app.chip_filter is None and len(shown(app)) == 4

# 4. níveis de contexto
app.row_by_cid[U(2)]['ctx'] = 160_000; app.row_by_cid[U(4)]['ctx'] = 260_000; app.update_chips()
assert counts(app)["rot"] == 1 and counts(app)["crit"] == 1
app.side_items["rot"].command(); app.update(); assert shown(app) == {U(2)}
app.side_items["crit"].command(); app.update(); assert shown(app) == {U(4)}
app.tabs["todas"].command(); app.update()

# 5. projeto: abre, seleciona e rola até a pasta; com filtro ativo, mostra tudo antes
app.side_items["pendente"].command(); app.update(); assert shown(app) == {U(4)}
beta = next(i for i in app.proj_items if i.name.cget("text") == "Beta")
beta.command(); app.update()
node = app.tree.selection()[0]
assert app.chip_filter is None and app.tree.item(node, "text").startswith("  Beta (") and app.tree.item(node, "open")

# 6. atalhos e largura: Ctrl+B recolhe; janela estreita esconde sozinha e volta ao alargar
assert app.bind("<Control-b>") and app.bind("<Control-k>") and app.search_entry.bind("<Control-k>") and app.search_entry.bind("<Control-b>")
assert app.focus_search() == "break" and app.focus_get() in (app.search_entry, None)
assert app.toggle_sidebar() == "break"; app.update(); assert not app.sidebar.winfo_manager() and not app.sidebar_wanted
app.toggle_sidebar(); app.update(); assert app.sidebar.winfo_manager() == "pack"
app.geometry("940x700+0+0"); settle(app); assert app.sidebar.winfo_manager() == "pack" and not app.tabs_frame.winfo_manager(), "abas somem abaixo de 1000 px"
app.geometry("820x700+0+0"); settle(app); assert not app.sidebar.winfo_manager(), "barra se esconde abaixo de 900 px"
app.geometry("1240x720+0+0"); settle(app); assert app.sidebar.winfo_manager() == "pack" and app.tabs_frame.winfo_manager() == "pack"
assert app.sidebar.winfo_width() == app.px(220) and app.sidebar.winfo_x() < app.holder.winfo_x() and app.footer.winfo_width() >= app.winfo_width() - 2, "rodapé com a largura toda"

# 7. todos os temas: item marcado usa a cor de seleção; texto do item e da aba legíveis
app.side_items["aprovada"].command(); app.update()
for key in G.THEME_ORDER:
    app.set_theme(key); app.update(); t = G.THEMES[key]
    it = app.side_items["aprovada"]
    assert it.on and it.cget("bg") == t["sel_bg"] and it.name.cget("fg") == t["sel_fg"], key
    off = app.side_items["pendente"]; assert off.cget("bg") == t["panel"] and off.glyph.cget("fg") == t["accent_text"], key
    assert app.tabs["todas"].cget("bg") == t["header_bg"] and G.contrast(t["sel_fg"], t["sel_bg"]) >= 4.5
app.destroy(); print("TODOS OS TESTES DA BARRA LATERAL OK")
