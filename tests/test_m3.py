import os, sys, sqlite3, tempfile, time, hashlib, types
root = tempfile.mkdtemp(prefix="agym3_")
home = os.path.join(root, "home"); os.makedirs(os.path.join(home, "Desktop"))
base = os.path.join(root, "gemini"); local = os.path.join(root, "local")
os.environ.update(HOME=home, ANTIGRAVITY_HOME=base, LOCALAPPDATA=local)
U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)
conv = os.path.join(base, "antigravity", "conversations"); os.makedirs(conv)
os.makedirs(os.path.join(base, "config", "projects"))
c = sqlite3.connect(os.path.join(base, "antigravity", "conversation_summaries.db"))
c.execute("CREATE TABLE conversation_summaries(conversation_id TEXT, title TEXT, preview TEXT, step_count INT, last_modified_time TEXT, project_id TEXT, workspace_uris TEXT)")
for i in range(1, 5): c.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?)", (U(i), "", "sessao %d" % i, i, "2026-10-26T1%d:00:00Z" % i, "", ""))
c.commit(); c.close()
for i in range(1, 5):
    d = sqlite3.connect(os.path.join(conv, U(i) + ".db")); d.execute("CREATE TABLE steps(idx INTEGER PRIMARY KEY, step_type INT, step_payload BLOB)"); d.commit(); d.close()
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
dbs = [os.path.join(conv, U(i) + ".db") for i in range(1, 5)] + [os.path.join(base, "antigravity", "conversation_summaries.db")]
before = [sha(p) for p in dbs]

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G
from tkinter import messagebox
asked = []; infos = []; answer = {"v": True}
messagebox.askyesno = lambda *a, **k: (asked.append(a), answer["v"])[1]
messagebox.showinfo = lambda *a, **k: infos.append(a)
messagebox.showwarning = lambda *a, **k: infos.append(a)
messagebox.showerror = lambda *a, **k: infos.append(a)
G.setup_logging()

def wait(a):
    end = time.time() + 30
    while a.loading and time.time() < end: a.update(); time.sleep(0.01)
    a.update()
def leaf(a, cid):
    return next(i for p in a.tree.get_children() for i in a.tree.get_children(p) if a.tree.item(i, "values")[7] == cid)
def label(a, cid): return a.tree.item(leaf(a, cid), "text").strip()

app = G.AntigravityGateApp(); wait(app)
assert all(label(app, U(i)) == "Pendente" for i in range(1, 5))

# 1. aprovar uma sessão: não pede confirmação, grava e mostra
app.tree.selection_set(leaf(app, U(1))); app.mark_selected("aprovada")
assert not asked and label(app, U(1)) == "Aprovada" and label(app, U(2)) == "Pendente"
assert app.chips["aprovada"].cget("text") == "✔ 1 aprovadas", app.chips["aprovada"].cget("text")

# 2. multi-seleção pede confirmação; "não" não muda nada
app.tree.selection_set([leaf(app, U(2)), leaf(app, U(3))]); answer["v"] = False; app.mark_selected("arquivada")
assert len(asked) == 1 and "2 sessão" in asked[0][1] and label(app, U(2)) == "Pendente"
answer["v"] = True; app.mark_selected("arquivada")
assert label(app, U(2)) == "Arquivada" and label(app, U(3)) == "Arquivada"

# 3. pasta de projeto = lote de todas as sessões dela (com confirmação)
proj = app.tree.get_children()[0]; app.tree.selection_set(proj); asked.clear(); app.mark_selected("aprovada")
assert "4 sessão" in asked[0][1] and all(label(app, U(i)) == "Aprovada" for i in range(1, 5))
assert app.chips["aprovada"].cget("text") == "✔ 4 aprovadas"

# 4. voltar a pendente
app.tree.selection_set(leaf(app, U(4))); app.mark_selected("pendente"); assert label(app, U(4)) == "Pendente"

# 5. sem seleção: aviso
app.tree.selection_set(()); infos.clear(); app.mark_selected("aprovada"); assert infos and "Selecione" in infos[0][1]

# 6. persiste ao reabrir; recarregar mantém; histórico gravado
app.destroy()
app = G.AntigravityGateApp(); wait(app)
assert [label(app, U(i)) for i in range(1, 5)] == ["Aprovada"] * 3 + ["Pendente"], [label(app, U(i)) for i in range(1, 5)]
app.refresh(); wait(app); assert label(app, U(1)) == "Aprovada"
con = sqlite3.connect(G.STATE_DB); n_log = con.execute("SELECT COUNT(*) FROM state_log").fetchone()[0]; con.close()
assert n_log == 1 + 2 + 4 + 1, n_log

# 7. duplo clique: pasta não abre popup nem detalhes; sessão abre os detalhes; área vazia ignora
proj = app.tree.get_children()[0]
opened = []; app.open_details = lambda: opened.append(app.tree.selection())
app.tree.item(proj, open=True); app.update()
y_proj = app.tree.bbox(proj)[1] + 5
infos.clear(); app.on_double_click(types.SimpleNamespace(y=y_proj)); assert not opened and not infos
y_leaf = app.tree.bbox(leaf(app, U(1)))[1] + 5
app.on_double_click(types.SimpleNamespace(y=y_leaf)); assert len(opened) == 1 and app.tree.selection() == (leaf(app, U(1)),)
app.on_double_click(types.SimpleNamespace(y=9999)); assert len(opened) == 1
app.destroy()

# 8. bancos do Antigravity intactos
assert [sha(p) for p in dbs] == before, "AntigravityGate escreveu em banco do Antigravity!"

# 9. estado sem disco: cai para memória, avisa, continua funcionando
G.STATE_DB = "/proc/nao_pode/gate_state.db"
st = G.StateStore(G.STATE_DB); assert not st.persistent
st.set_many([U(1)], "aprovada"); assert st.load() == {U(1): "aprovada"}
st.set_many([U(1)], "pendente"); assert st.load() == {}
print("TODOS OS TESTES M3a OK")
