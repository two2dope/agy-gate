import os, sys, json, sqlite3, tempfile, time, threading, glob
# Salvaguardas do Auto-Run e do fechamento (auditoria 0.9.0, críticos C1 a C3).
root = tempfile.mkdtemp(prefix="agysafe_")
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

# --- C1: sucesso só com código 0, conversation_id e status diferente de ERROR -----------------------------
ok_json = json.dumps({"conversation_id": "c1", "status": "OK", "response": "r", "error": ""})
assert G.parse_agy_output(ok_json, "", 0)['ok'], "sucesso completo"
r = G.parse_agy_output(ok_json, "", 1)
assert not r['ok'] and "código 1" in r['error'], r
r = G.parse_agy_output(json.dumps({"conversation_id": "x", "response": "r"}), "", 0)
assert r['ok'], "sem status, com id, resposta e código 0: aceito"
r = G.parse_agy_output(json.dumps({"response": "algo"}), "", 0)
assert not r['ok'] and "conversation_id" in r['error'], r
r = G.parse_agy_output(json.dumps({"conversation_id": "", "status": "OK"}), "", 0)
assert not r['ok'], "id vazio não é sucesso"

for seq in ("nostatus", "okexit1"):
    reset(seq); st = store(); logs = []
    res = G.AutoRunner(items([1]), st, logs.append, agy=FAKE, dry_run=False).run()
    assert res['ok'] == 0 and res['failed'] == 1, (seq, res)
    assert st.handoffs_ok() == {}, f"{seq}: nada pode ficar registrado como retomada"
reset("ok"); st = store()
res = G.AutoRunner(items([1]), st, [].append, agy=FAKE, dry_run=False).run()
assert res['ok'] == 1 and st.handoffs_ok() == {U(1): "aaaaaaaa-0000-0000-0000-000000000001"}

# --- C2: prompt numa linha, flags de segurança antes do prompt, shim .cmd/.bat conferido ---------------------
assert "\n" not in G.AGY_PROMPT and "\r" not in G.AGY_PROMPT
d = os.path.join(root, "handoffs", "retomada_x.md")
a = G.build_agy_args("agy", d, [root])
assert all("\n" not in x and "\r" not in x for x in a), a
assert a[-2] == "--print" and d in a[-1], "prompt por último, logo depois de --print"
for flag, value in (("--mode", "plan"), ("--output-format", "json")):
    assert a.index(flag) < a.index("--print") and a[a.index(flag) + 1] == value, (flag, a)
assert "--dangerously-skip-permissions" not in a

assert G.cmd_shim_problem(["C:\\bin\\agy.exe", "a & b"]) == "", ".exe não passa pelo cmd.exe"
assert G.cmd_shim_problem(["C:\\bin\\agy.cmd", "--print", "texto simples (1); ok: sim"]) == ""
for bad in ("a & b", "100%", 'aspas "x"', "a|b", "a^b", "linha\noutra"):
    assert G.cmd_shim_problem(["agy.CMD", bad]), bad
    assert G.cmd_shim_problem(["agy.bat", bad]), bad

reset("ok"); st = store(); logs = []
G.HANDOFF_DIR = os.path.join(root, "P&D", "handoffs")  # pasta com & no caminho
res = G.AutoRunner(items([1, 2]), st, logs.append, agy=os.path.join(root, "agy.cmd"), dry_run=False).run()
assert calls() == [] and res['failed'] == 1 and res['skipped'] == 1 and "cmd" in res['aborted'], res
assert any("cmd.exe" in l for l in logs), logs
G.HANDOFF_DIR = os.path.join(local, "AntigravityGate", "handoffs")

# --- exportação: arquivo final só aparece completo --------------------------------------------------------
out = os.path.join(root, "exp.md")
def boom(n, t): raise G.ExportCancelled()
c = sqlite3.connect(os.path.join(conv, U(3) + ".db"))
c.executemany("INSERT INTO steps VALUES(?,15,3,?,NULL)", [(i, fv(1, 15) + fl(20, fs(3, "x"))) for i in range(2, 60)]); c.commit(); c.close()
for kind in ("full", "dossier"):
    try:
        G.export_session(kind, os.path.join(conv, U(3) + ".db"), {'cid': U(3)}, out, progress=boom); raise AssertionError("não cancelou")
    except G.ExportCancelled:
        pass
    assert not os.path.exists(out) and not glob.glob(out + "*"), (kind, os.listdir(root))
G.export_session('dossier', os.path.join(conv, U(3) + ".db"), {'cid': U(3)}, out)
assert os.path.exists(out) and not glob.glob(out + ".*")

# --- C3: fechar a janela com trabalho em andamento ----------------------------------------------------------
from tkinter import messagebox, filedialog
answers = []
messagebox.askyesno = lambda *a, **k: (answers.append(a), answers_reply[0])[1]
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, **k: None)
answers_reply = [False]
G.STATE_DB = os.path.join(root, "ui_state.db")
os.environ["AGY_EXE"] = FAKE

def wait(a, secs=20):
    end = time.time() + secs
    while a.loading and time.time() < end: a.update(); time.sleep(0.01)
    a.update()
def destroyed(a):
    try:
        a.winfo_exists(); return False
    except Exception:
        return True

app = G.AntigravityGateApp(); wait(app)
for i in app.iter_sessions():
    app.tree.selection_add(i)
answers_reply[0] = True; app.mark_selected("aprovada"); answers.clear()
app.confirm_autorun = lambda its, done: {'dry_run': False, 'redo': True}
reset("hang"); app.start_autorun()
end = time.time() + 10
while not calls() and time.time() < end: app.update(); time.sleep(0.05)
assert calls() and app.autorunning

answers_reply[0] = False; app.on_close()
assert answers and "Auto-Run" in answers[-1][1] and not destroyed(app) and app.autorunning, "recusar mantém o app aberto e o lote rodando"

answers_reply[0] = True; t0 = time.time(); app.on_close()
assert destroyed(app) and time.time() - t0 < 15, "aceitar cancela e fecha"
assert not app.auto_thread.is_alive(), "a thread do Auto-Run terminou antes de fechar"
assert len(calls()) == 1, "nenhuma sessão nova depois do cancelamento"
with sqlite3.connect(G.STATE_DB) as c:
    rows = c.execute("SELECT status, detail FROM handoffs").fetchall()
assert rows == [('erro', 'cancelada')], rows

# exportação em andamento
app = G.AntigravityGateApp(); wait(app)
out2 = os.path.join(root, "exp2.md")
filedialog.asksaveasfilename = lambda **k: out2
real_export = G.export_session
def slow_export(kind, fpath, meta, out_path, progress=None):
    def slow(n, t):
        time.sleep(0.05); progress(n, t)
    for n in range(1, 400):
        slow(n, 400)
    real_export(kind, fpath, meta, out_path)
G.export_session = slow_export
app.tree.selection_set(next(app.iter_sessions())); app.start_export('full')
assert app.exporting
answers.clear(); answers_reply[0] = True; t0 = time.time(); app.on_close()
assert answers and "exportação" in answers[-1][1] and destroyed(app) and time.time() - t0 < 5
assert not app.export_thread.is_alive() and not os.path.exists(out2), "exportação cancelada não deixa arquivo"
G.export_session = real_export

# sem trabalho em andamento: fecha sem perguntar
app = G.AntigravityGateApp(); wait(app)
answers.clear(); app.on_close(); assert destroyed(app) and not answers

print("TODOS OS TESTES DE SEGURANÇA OK")
