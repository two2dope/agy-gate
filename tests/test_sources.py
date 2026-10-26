import os, sys, sqlite3, tempfile, glob

import time
def wait(a):
    end = time.time() + 30
    while a.loading and time.time() < end:
        a.update(); time.sleep(0.01)
    a.update()
root = tempfile.mkdtemp(prefix="agysrc_")
home = os.path.join(root, "home"); os.makedirs(os.path.join(home, "Desktop"))
base = os.path.join(root, "gemini")
os.environ.update(HOME=home, ANTIGRAVITY_HOME=base, LOCALAPPDATA=os.path.join(root, "local"))
U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)
A, B = U(1), U(2)

def summ(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE conversation_summaries(conversation_id TEXT, title TEXT, preview TEXT, step_count INT, last_modified_time TEXT, project_id TEXT, workspace_uris TEXT)")
    for r in rows: c.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?)", r)
    c.commit(); c.close()

def sess(folder, cid, nsteps, pad=0):
    os.makedirs(folder, exist_ok=True)
    c = sqlite3.connect(os.path.join(folder, cid + ".db")); c.execute("CREATE TABLE steps(idx INTEGER PRIMARY KEY, step_type INT DEFAULT 0, status INT DEFAULT 3, step_payload BLOB, error_details BLOB)")
    for i in range(nsteps): c.execute("INSERT INTO steps VALUES(?,?,?,?,?)", (i, 0, 3, b"x" * (50 + pad), None))
    c.commit(); c.close()

ant = os.path.join(base, "antigravity")
summ(os.path.join(ant, "conversation_summaries.db"), [(A, "", "ativa A", 5, "2026-10-26T10:00:00Z", "", ""), (B, "", "ativa B", 9, "2026-10-26T11:00:00Z", "", "")])
sess(os.path.join(ant, "conversations"), A, 5); sess(os.path.join(ant, "conversations"), B, 9)
sess(os.path.join(ant, "conversations_bkp"), A, 5)
os.makedirs(os.path.join(ant, "corrupt_quarantine")); open(os.path.join(ant, "corrupt_quarantine", U(7) + ".db"), "wb").write(b"lixo" * 100)
ide = os.path.join(base, "antigravity-ide.bak")
summ(os.path.join(ide, "conversation_summaries.db"), [(A, "", "ANTIGA A no backup", 3, "2026-10-20T08:00:00Z", "", "")])
sess(os.path.join(ide, "conversations"), A, 3); sess(os.path.join(ide, "conversations"), U(9), 2)   # U(9) só existe no backup
os.makedirs(os.path.join(base, "config", "projects")); os.makedirs(os.path.join(base, "tmp", "x"))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G
from tkinter import messagebox, filedialog
OUT = os.path.join(root, 'saida.md')
filedialog.asksaveasfilename = lambda *a, **k: OUT
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, **k: None)
G.setup_logging()
app = G.AntigravityGateApp(); wait(app)

def leaves():
    return {app.tree.item(c, "values")[7]: app.tree.item(c, "values") for p in app.tree.get_children() for c in app.tree.get_children(p)}
labels = [s[0] for s in app.sources]; print("fontes:", labels)
assert labels[0] == G.ACTIVE_LABEL and len(labels) == 4, labels
assert any("conversations_bkp" in l for l in labels) and any("corrupt_quarantine" in l for l in labels) and any("antigravity-ide.bak/conversations" in l for l in labels)
L = leaves(); print("ativas:", {k[:8]: (v[3], v[5]) for k, v in L.items()})
assert set(L) == {A, B} and L[A][5] == "ativa A" and str(L[B][3]) == "9", "ativas devem vir só da pasta ativa"
assert app.warnings == 0, app.warnings
assert labels[0] in app.status.cget("text")

# trocar para o backup ide.bak
app.src_box.current(labels.index(next(l for l in labels if "ide.bak" in l))); app.on_source_change(); wait(app)
L = leaves(); print("ide.bak:", {k[:8]: (v[3], v[5]) for k, v in L.items()})
assert set(L) == {A, U(9)} and L[A][5] == "ANTIGA A no backup" and str(L[A][3]) == "3", "backup lido separado com o próprio summaries"
assert U(9) in L and L[U(9)][5].startswith("xxxx")

# quarentena: banco corrompido gera aviso, app segue de pé
app.src_box.current(labels.index(next(l for l in labels if "corrupt" in l))); app.on_source_change(); wait(app)
assert app.warnings == 1 and set(leaves()) == {U(7)}, (app.warnings, leaves())
print("quarentena:", app.status.cget("text")[:70])

# conversations_bkp usa o summaries da pasta pai (ativa)
app.src_box.current(labels.index(next(l for l in labels if "conversations_bkp" in l))); app.on_source_change(); wait(app)
assert set(leaves()) == {A} and leaves()[A][5] == "ativa A", leaves()

# refresh mantém a fonte selecionada e vê pasta nova
sess(os.path.join(base, "antigravity-cli.bak", "conversations"), U(5), 1)
sel = app.sources[app.source_idx][0]; app.refresh(); wait(app)
assert app.sources[app.source_idx][0] == sel and len(app.sources) == 5, [s[0] for s in app.sources]
# tema mantém a fonte
app.toggle_theme(); wait(app); assert app.sources[app.source_idx][0] == sel
# export numa fonte de backup usa o arquivo daquela fonte
labels = [x[0] for x in app.sources]
app.src_box.current(1 if False else labels.index(next(l for l in labels if "ide.bak" in l))); app.on_source_change(); wait(app)
node = [c for p in app.tree.get_children() for c in app.tree.get_children(p) if app.tree.item(c, "values")[7] == A][0]
app.tree.selection_set(node); app.open_selected()
end = time.time() + 20
while app.exporting and time.time() < end: app.update(); time.sleep(0.01)
app.update()
md = open(OUT, encoding="utf-8").read()
assert "antigravity-ide.bak" in md.replace("\\", "/"), "export deve apontar para o banco da fonte selecionada"
app.destroy()

# sem pasta ativa: abre sem quebrar
os.environ["ANTIGRAVITY_HOME"] = os.path.join(root, "vazio"); os.makedirs(os.environ["ANTIGRAVITY_HOME"])
import importlib; importlib.reload(G)
app = G.AntigravityGateApp(); wait(app); assert app.warnings >= 1 and len(app.sources) == 1; app.destroy()
print("TODOS OS TESTES DE FONTES OK")
