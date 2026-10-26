import os, sys, json, sqlite3, tempfile, time, threading, glob
# Modelo escolhido para o agy no Auto-Run (--model), lembrado entre execuções.
root = tempfile.mkdtemp(prefix="agymodel_")
base = os.path.join(root, "gemini"); local = os.path.join(root, "local")
os.environ.update(HOME=os.path.join(root, "home"), ANTIGRAVITY_HOME=base, LOCALAPPDATA=local)
os.environ.pop("AGY_ROT_TOKENS", None)
FAKE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_agy.py")
LOG = os.path.join(root, "agy_calls.log"); os.environ["AGY_FAKE_LOG"] = LOG

def vi(n):
    o = bytearray()
    while True:
        b = n & 0x7f; n >>= 7
        if n: o.append(b | 0x80)
        else: o.append(b); return bytes(o)
fv = lambda f, v: vi(f << 3) + vi(v); fl = lambda f, b: vi(f << 3 | 2) + vi(len(b)) + b; fs = lambda f, s: fl(f, s.encode())
U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)
conv = os.path.join(base, "antigravity", "conversations"); os.makedirs(conv); os.makedirs(os.path.join(base, "config", "projects"))
for i in range(1, 4):
    c = sqlite3.connect(os.path.join(conv, U(i) + ".db"))
    c.execute("CREATE TABLE steps (idx integer PRIMARY KEY, step_type integer, status integer, step_payload blob, error_details blob)")
    c.execute("INSERT INTO steps VALUES(0,14,3,?,NULL)", (fv(1, 14) + fl(5, fl(1, fv(1, 1792916000)) + fv(3, 4)) + fl(19, fs(2, "pedido %d" % i)),))
    c.execute("INSERT INTO steps VALUES(1,15,3,?,NULL)", (fv(1, 15) + fl(5, fl(1, fv(1, 1792916005)) + fv(3, 2)) + fl(20, fs(3, "resposta %d" % i)),))
    c.commit(); c.close()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G

def calls(): return [json.loads(l) for l in open(LOG)] if os.path.exists(LOG) else []
def reset(seq):
    if os.path.exists(LOG): os.remove(LOG)
    os.environ["AGY_FAKE_SEQ"] = seq
def items(ids):
    return [{'cid': U(i), 'title': "s%d" % i, 'fpath': os.path.join(conv, U(i) + ".db"),
             'meta': {'cid': U(i), 'title': "s%d" % i, 'fpath': os.path.join(conv, U(i) + ".db")}, 'workspace': ''} for i in ids]
def store(): return G.StateStore(os.path.join(root, "st_%d.db" % time.time_ns()))

# --- argumentos
d = os.path.join(root, "handoffs", "r.md")
a = G.build_agy_args("agy", d, [], model="gemini-3.8-flash")
assert a[a.index("--model") + 1] == "gemini-3.8-flash" and a.index("--model") < a.index("--print"), a
assert "--model" not in G.build_agy_args("agy", d, []) and "--model" not in G.build_agy_args("agy", d, [], model="  ")
assert G.cmd_shim_problem(["agy.cmd"] + G.build_agy_args("x", "C:\\h\\r.md", [], model="a&b")[1:]), "modelo também passa pela conferência do cmd.exe"

# --- runner repassa o modelo
reset("ok"); st = store()
res = G.AutoRunner(items([1]), st, [].append, agy=FAKE, dry_run=False, model="gemini-3.8-flash").run()
argv = calls()[0]
assert res['ok'] == 1 and argv[argv.index("--model") + 1] == "gemini-3.8-flash", argv

# --- tela: confirmação devolve o modelo; fica salvo; vazio = padrão do agy
from tkinter import messagebox
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, **k: None)
messagebox.askyesno = lambda *a, **k: True
G.STATE_DB = os.path.join(root, "ui_state.db"); os.environ["AGY_EXE"] = FAKE
def wait(a, secs=20):
    end = time.time() + secs
    while (a.loading or a.autorunning) and time.time() < end: a.update(); time.sleep(0.01)
    a.update()
app = G.AntigravityGateApp(); wait(app)
for i in app.iter_sessions(): app.tree.selection_add(i)
app.mark_selected("aprovada")

real_confirm = app.confirm_autorun
seen = {}
def fake_confirm(its, done):  # abre a janela de verdade, preenche e clica Iniciar
    app.after(300, lambda: (seen.update(values=list(app.model_box.cget("values"))), app.confirm_dry.set(False), app.model_var.set(" gemini-3.8-flash "), app.confirm_go()))
    return real_confirm(its, done)
app.confirm_autorun = fake_confirm
reset("ok"); app.start_autorun(); wait(app)
argv = calls()[0]
assert argv[argv.index("--model") + 1] == "gemini-3.8-flash", argv
assert "gemini-3.8-flash" in app.auto_win[1].get("1.0", "end"), "o log mostra o modelo"
assert G.load_settings().get("agy_model") == "gemini-3.8-flash"
app.cancel_autorun()

def blank_confirm(its, done):
    app.after(300, lambda: (seen.update(prefill=app.model_var.get(), values=list(app.model_box.cget("values"))), app.confirm_dry.set(False), app.confirm_redo.set(True), app.model_var.set(""), app.confirm_go()))
    return real_confirm(its, done)
app.confirm_autorun = blank_confirm
reset("ok"); app.start_autorun(); wait(app)
assert seen['prefill'] == "gemini-3.8-flash" and "gemini-3.8-flash" in seen['values'], seen
assert all("--model" not in c for c in calls()), "vazio = sem --model (padrão do agy)"
assert G.load_settings().get("agy_model") == "" and "gemini-3.8-flash" in G.load_settings().get("agy_models", [])
app.cancel_autorun(); app.destroy()
print("TODOS OS TESTES DE MODELO OK")
