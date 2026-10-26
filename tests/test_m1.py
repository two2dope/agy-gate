import os, sys, json, sqlite3, hashlib, time, glob, tempfile

import time
def wait(a):
    end = time.time() + 30
    while a.loading and time.time() < end:
        a.update(); time.sleep(0.01)
    a.update()

root = tempfile.mkdtemp(prefix="agy_")
home = os.path.join(root, "home"); os.makedirs(os.path.join(home, "Desktop"))
base = os.path.join(root, "gemini")
os.environ.update(HOME=home, ANTIGRAVITY_HOME=base, LOCALAPPDATA=os.path.join(root, "local"))
os.makedirs(os.path.join(base, "antigravity")); os.makedirs(os.path.join(base, "config", "projects"))
os.makedirs(os.path.join(base, "antigravity", "conversations"))

# projetos: ok, resources None, gitFolder None, JSON quebrado
def wj(n, d): open(os.path.join(base, "config", "projects", n), "w", encoding="utf-8").write(d if isinstance(d, str) else json.dumps(d))
wj("ok.json", {"id": "p1", "name": "Projeto Um", "projectResources": {"resources": [{"folderUri": "file:///c%3A/work/um"}]}})
wj("nores.json", {"id": "p2", "name": "Sem Recursos", "projectResources": None})
wj("gitnull.json", {"id": "p3", "name": "Git Nulo", "projectResources": {"resources": [{"gitFolder": None}, {"folderUri": "file:///c%3A/work/tres"}]}})
wj("quebrado.json", "{nao e json")

U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)
A, B, C, D = U(1), U(2), U(3), U(4)

def mk_sessions_db():
    c = sqlite3.connect(os.path.join(base, "antigravity", "conversation_summaries.db"))
    c.execute("CREATE TABLE conversation_summaries(conversation_id TEXT, title TEXT, preview TEXT, step_count INT, last_modified_time, project_id TEXT, workspace_uris TEXT)")
    c.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?)", (A, None, None, None, 1730000000, None, None))      # tudo NULL + epoch int
    c.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?)", (B, "Título B", "prev B", 5, "2026-10-01T12:30:00Z", "p1", "file:///c%3A/work/um"))
    c.commit(); c.close()
mk_sessions_db()

def mk_session(cid, rows):
    p = os.path.join(base, "antigravity", "conversations", cid + ".db")
    c = sqlite3.connect(p); c.execute("CREATE TABLE steps(id INTEGER, data BLOB)")
    for i, r in enumerate(rows): c.execute("INSERT INTO steps VALUES(?,?)", (i, r))
    c.commit(); c.close(); return p
pA = mk_session(A, ["\x12\x0aOlá mundo, como vai você hoje? Texto longo para extrair.".encode(), "Segunda mensagem do assistente com acentuação ção ã é.".encode()])
pB = mk_session(B, [b"x"])
pC = mk_session(C, [b"locked one"])
open(os.path.join(base, "antigravity", "conversations", D + ".db"), "wb").write(b"isto nao e sqlite" * 50)       # corrompido
open(os.path.join(base, "antigravity", "conversations", "naouuid.db"), "wb").write(b"x")                           # ignorado

sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
before = {p: sha(p) for p in (pA, pB, pC)}

# trava exclusiva em C (bloqueia leitores)
lock = sqlite3.connect(pC, isolation_level=None); lock.execute("BEGIN EXCLUSIVE")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)).replace("scratchpad", "scratchpad"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G
from tkinter import messagebox
msgs = []
for n in ("showinfo", "showwarning", "showerror"):
    setattr(messagebox, n, lambda *a, _n=n, **k: msgs.append((_n, a)))
G.setup_logging()

t0 = time.time(); app = G.AntigravityGateApp(); wait(app); dt = time.time() - t0
print("load ok em %.1fs" % dt)
print("status:", app.status.cget("text"))

def leaves():
    out = []
    for p in app.tree.get_children():
        for c in app.tree.get_children(p):
            out.append((app.tree.item(p, "text"), app.tree.item(c, "text"), app.tree.item(c, "values")))
    return out
L = leaves()
for r in L: print(r)
by = {r[2][7]: r for r in L}
assert set(by) == {A, B, C, D}, "esperava 4 sessoes UUID (naouuid.db ignorado)"
assert all(r[1].strip().endswith("Pendente") and "Aprovada" not in r[1] for r in L), "nenhuma sessão nasce aprovada"
assert "2024-10-27" in by[A][2][0] or by[A][2][0].startswith("20"), by[A][2][0]       # epoch normalizado
assert by[B][0].strip().startswith("Projeto Um"), by[B][0]
assert "Olá mundo" in by[A][2][5], "preview mantém acentos: %r" % by[A][2][5]
assert app.warnings >= 2, app.warnings                                                    # C travado + D corrompido
assert "aviso" in app.status.cget("text")

# botões desabilitados
def walk(w):
    yield w
    for c in w.winfo_children(): yield from walk(c)
btns = [w for w in walk(app) if w.winfo_class() == "Button"]
dis = [b.cget("text") for b in btns if str(b.cget("state")) == "disabled"]
print("desabilitados:", dis); assert dis == [], "nenhum botão fantasma: tudo que aparece funciona"
assert all(b.enabled or b.reason for b in app.btn.values()), "botão desabilitado sempre explica o motivo"
assert app.btn["autorun"].text == "Auto-Run" and not app.btn["autorun"].enabled and "Nenhuma sessão aprovada" in app.btn["autorun"].tooltip_text()

# exportar com esquema sem step_type: erro visível, sem travar nem deixar "exportando"
from tkinter import filedialog
filedialog.asksaveasfilename = lambda *a, **k: os.path.join(root, "x.md")
for cid in (A, B):
    for p in app.tree.get_children():
        for c in app.tree.get_children(p):
            if app.tree.item(c, "values")[7] == cid: app.tree.selection_set(c)
    msgs.clear(); app.open_selected()
    end = time.time() + 20
    while app.exporting and time.time() < end: app.update(); time.sleep(0.01)
    app.update()
    assert not app.exporting and msgs and msgs[-1][0] == "showerror", msgs

# toggle de tema roda de novo sem erro
app.toggle_theme(); wait(app); assert len(leaves()) == 4

lock.execute("ROLLBACK"); lock.close()
after = {p: sha(p) for p in (pA, pB, pC)}
assert before == after, "bancos do Antigravity foram alterados!"
assert not glob.glob(os.path.join(base, "**", "*-journal"), recursive=True) and not glob.glob(os.path.join(base, "**", "*-wal"), recursive=True)
log = open(G.LOG_FILE, encoding="utf-8").read(); print("--- log ---"); print(log)
assert "locked" in log and "Projeto ilegível" in log
print("TODOS OS TESTES M1 OK")
app.destroy()
