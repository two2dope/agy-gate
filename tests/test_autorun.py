import os, sys, json, sqlite3, tempfile, time, threading, glob
root = tempfile.mkdtemp(prefix="agyauto_")
base = os.path.join(root, "gemini"); local = os.path.join(root, "local")
os.environ.update(HOME=os.path.join(root, "home"), ANTIGRAVITY_HOME=base, LOCALAPPDATA=local)
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
ws = os.path.join(root, "meu projeto"); os.makedirs(ws)
import urllib.parse
ws_uri = "file://" + urllib.parse.quote(ws)
for i in range(1, 6):
    c = sqlite3.connect(os.path.join(conv, U(i) + ".db"))
    c.execute("CREATE TABLE steps (idx integer PRIMARY KEY, step_type integer, status integer, step_payload blob, error_details blob)")
    c.execute("INSERT INTO steps VALUES(0,14,3,?,NULL)", (fv(1, 14) + fl(5, fl(1, fv(1, 1792916000)) + fv(3, 4)) + fl(19, fs(2, "pedido da sessão %d" % i)),))
    c.execute("INSERT INTO steps VALUES(1,15,3,?,NULL)", (fv(1, 15) + fl(5, fl(1, fv(1, 1792916005)) + fv(3, 2)) + fl(20, fs(3, "resposta final %d" % i)),))
    c.commit(); c.close()
sc = sqlite3.connect(os.path.join(base, "antigravity", "conversation_summaries.db"))
sc.execute("CREATE TABLE conversation_summaries(conversation_id TEXT, title TEXT, preview TEXT, step_count INT, last_modified_time TEXT, project_id TEXT, workspace_uris TEXT, agent_name TEXT, parent_conversation_id TEXT)")
for i in range(1, 6): sc.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?,?,?)", (U(i), "", "sessao %d" % i, 2, "2026-10-26T1%d:00:00Z" % i, "", ws_uri, "", ""))
sc.commit(); sc.close()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G

def calls(): return [json.loads(l) for l in open(LOG)] if os.path.exists(LOG) else []
def reset(seq):
    if os.path.exists(LOG): os.remove(LOG)
    os.environ["AGY_FAKE_SEQ"] = seq
def items(ids):
    out = []
    for i in ids:
        out.append({'cid': U(i), 'title': "sessao %d" % i, 'fpath': os.path.join(conv, U(i) + ".db"),
                    'meta': {'cid': U(i), 'title': "sessao %d" % i, 'fpath': os.path.join(conv, U(i) + ".db"), 'status': 'aprovada'}, 'workspace': ws_uri})
    return out
def store(): return G.StateStore(os.path.join(root, "st_%d.db" % time.time_ns()))

# --- parse com a saída REAL colada pelo usuário
real_out = '{"conversation_id":"56d4c7bb-9243-4ecb-a4ee-3f1e3db199f8","status":"ERROR","response":"","error":"Individual quota reached. Please upgrade your subscription to increase your limits. Resets in 31h40m31s.","duration_seconds":2.3195196,"num_turns":1,"usage":{"input_tokens":0,"output_tokens":0,"thinking_tokens":0,"cache_read_tokens":0,"total_tokens":0}}'
real_err = 'error: Individual quota reached. Please upgrade your subscription to increase your limits. Resets in 31h40m31s.\nAGY_ERROR: {"short_error":"RESOURCE_EXHAUSTED (code 429): Individual quota reached.","status":"RESOURCE_EXHAUSTED","error_code":429,"code_kind":"http","retryable":true,"error_id":"d8568a46-29bd-4091-84a1-fa264b06a710-2"}'
r = G.parse_agy_output(real_out, real_err)
assert not r['ok'] and r['quota'] and r['reset'] == "31h40m31s" and r['conversation_id'] == "56d4c7bb-9243-4ecb-a4ee-3f1e3db199f8", r
assert G.parse_agy_output(real_out, "")['quota'], "cota detectada só pelo JSON"
assert not G.parse_agy_output("banana", "")['ok'] and G.parse_agy_output("", "")['error'].startswith("saída sem JSON")
okr = G.parse_agy_output(json.dumps({"conversation_id": "c", "status": "OK", "response": "r", "error": ""}), "")
assert okr['ok'] and okr['conversation_id'] == "c" and not okr['quota']
pretty = G.parse_agy_output(json.dumps({"conversation_id": "p", "status": "OK", "response": "r"}, indent=2), "")
assert pretty['ok'] and pretty['conversation_id'] == "p", "JSON em várias linhas"

# --- workspace_dirs / args
assert G.workspace_dirs(ws_uri) == [ws] and G.workspace_dirs("file:///nao/existe/xyz") == [] and G.workspace_dirs("") == []
a = G.build_agy_args("agy", os.path.join(root, "d.md"), [ws])
assert a[0] == "agy" and a[-2] == "--print" and "--dangerously-skip-permissions" not in a and a[a.index("--mode") + 1] == "plan"
assert a[a.index("--output-format") + 1] == "json" and a[a.index("--print-timeout") + 1] == "600s" and a.count("--add-dir") == 2 and ws in a

logs = []
# --- 1. simulação: só dossiês
reset("ok"); st = store()
res = G.AutoRunner(items([1, 2]), st, logs.append, agy=FAKE, dry_run=True).run()
assert res['dossier'] == 2 and res['ok'] == 0 and calls() == [], "simulação não pode chamar o agy"
ds = sorted(glob.glob(os.path.join(G.HANDOFF_DIR, "retomada_00000001_*.md"))); assert ds and "pedido da sessão 1" in open(ds[-1], encoding="utf-8").read()
assert st.handoffs_ok() == {}, "simulação não conta como retomada"

# --- 2. execução real (agy simulado): argumentos, sessão nova registrada
reset("ok,ok"); st = store(); logs.clear()
res = G.AutoRunner(items([1, 2]), st, logs.append, agy=FAKE, dry_run=False).run()
assert res['ok'] == 2 and res['failed'] == 0 and len(calls()) == 2
argv = calls()[0]
assert "--dangerously-skip-permissions" not in argv and argv[-2] == "--print" and "retomada_00000001_" in argv[-1] and argv[argv.index("--mode") + 1] == "plan"
assert ws in argv and G.HANDOFF_DIR not in argv and "--project" not in argv, "pasta do projeto sim; handoffs não (o dossiê vai no prompt)"
ok = st.handoffs_ok(); assert ok == {U(1): "aaaaaaaa-0000-0000-0000-000000000001", U(2): "aaaaaaaa-0000-0000-0000-000000000002"}, ok
assert any("Entendi o objetivo" in l for l in logs)

# --- 3. cota: interrompe o lote, sem novas tentativas, arquiva a sessão vazia criada
reset("ok,quota,ok,ok"); st = store(); logs.clear()
res = G.AutoRunner(items([1, 2, 3, 4]), st, logs.append, agy=FAKE, dry_run=False).run()
assert res['ok'] == 1 and res['failed'] == 1 and res['skipped'] == 2 and res['quota'] == "31h40m31s" and res['aborted'] == "cota esgotada", res
assert len(calls()) == 2, "depois do 429 não pode chamar de novo"
assert st.load().get("aaaaaaaa-0000-0000-0000-000000000002") == "arquivada", "sessão vazia criada pela tentativa com erro vai para arquivadas"
assert any("31h40m31s" in l and "sem novas tentativas" in l for l in logs)

# --- 4. falhas seguidas
reset("garbage"); st = store(); logs.clear()
res = G.AutoRunner(items([1, 2, 3, 4, 5]), st, logs.append, agy=FAKE, dry_run=False).run()
assert res['failed'] == 3 and res['skipped'] == 2 and len(calls()) == 3 and "3 falhas seguidas" in res['aborted'], res
reset("fail,ok,ok"); st = store()
res = G.AutoRunner(items([1, 2, 3]), st, logs.append, agy=FAKE, dry_run=False).run()
assert res['ok'] == 2 and res['failed'] == 1 and res['aborted'] == "", "uma falha isolada não interrompe"

# --- 5. cancelar durante a execução
reset("hang"); st = store(); logs.clear()
runner = G.AutoRunner(items([1, 2, 3]), st, logs.append, agy=FAKE, dry_run=False, timeout_s=300)
box = {}
t = threading.Thread(target=lambda: box.update(res=runner.run())); t0 = time.time(); t.start(); time.sleep(1.5); runner.cancel(); t.join(15)
assert not t.is_alive() and time.time() - t0 < 12, "cancelar precisa encerrar o agy"
assert box['res']['aborted'] == "cancelado pelo usuário" and box['res']['skipped'] == 2 and len(calls()) == 1

# --- 6. tempo esgotado
reset("hang"); st = store()
t0 = time.time(); res = G.AutoRunner(items([1]), st, logs.append, agy=FAKE, dry_run=False, timeout_s=1, grace_s=0.5).run()
assert res['failed'] == 1 and time.time() - t0 < 10 and any("tempo esgotado" in l for l in logs)

# --- 7. agy inexistente / travado
st = store(); res = G.AutoRunner(items([1, 2]), st, logs.append, agy="/nao/existe/agy", dry_run=False).run()
assert res['failed'] == 1 and res['skipped'] == 1 and res['aborted'] == "agy não executou"
reset("crash"); res = G.AutoRunner(items([1]), store(), logs.append, agy=FAKE, dry_run=False).run(); assert res['failed'] == 1

# --- 8. retomada no projeto de origem (27/10): sem --project o agy põe tudo em "CLI Project"; sem cwd, a pasta
#        de onde o app foi aberto e a pasta handoffs viravam o workspace da sessão nova
CWD = os.path.join(root, "agy_cwd.log"); os.environ["AGY_FAKE_CWD"] = CWD
proj = os.path.join(root, "projeto X"); os.makedirs(proj)
pj = {"id": "proj-x", "name": "Projeto X", "projectResources": {"resources": [{"gitFolder": {"folderUri": "file://" + urllib.parse.quote(proj)}}]}}
open(os.path.join(base, "config", "projects", "proj-x.json"), "wb").write(b"\xef\xbb\xbf" + json.dumps(pj).encode())  # BOM do PowerShell 5.1
exe_dir = os.path.join(root, "Downloads", "AntigravityGate-windows"); os.makedirs(exe_dir); open(os.path.join(exe_dir, "AntigravityGate.exe"), "w").close()
os.makedirs(G.HANDOFF_DIR, exist_ok=True)
dirty = json.dumps(["file://" + urllib.parse.quote(p) for p in (G.HANDOFF_DIR, exe_dir, ws)])  # workspace de uma retomada da 1.0.0
assert G.workspace_dirs(dirty) == [ws], G.workspace_dirs(dirty)
assert G.project_target("proj-x") == ("proj-x", [proj]), G.project_target("proj-x")
assert G.project_target("outside-of-project") == G.project_target("default-cli-project") == G.project_target("sumiu") == G.project_target("") == ("", [])
assert G.load_projects(lambda *a: None)[0].get("proj-x") == "Projeto X", "JSON de projeto com BOM é lido"

def run_one(pid, workspace, dry=False):
    reset("ok"); open(CWD, "w").close(); out = []
    res = G.AutoRunner([dict(items([1])[0], project_id=pid, workspace=workspace)], store(), out.append, agy=FAKE, dry_run=dry).run()
    assert res['ok' if not dry else 'dossier'] == 1, res
    return (calls() or [[]])[0], open(CWD).read().strip(), out

argv, cwd, out = run_one("proj-x", dirty)
assert argv[argv.index("--project") + 1] == "proj-x" and argv.index("--project") < argv.index("--print"), argv
assert os.path.samefile(cwd, proj) and proj in argv and ws in argv, (cwd, argv)
assert G.HANDOFF_DIR not in argv and exe_dir not in argv, argv
assert any("pasta:" in l and "proj-x (--project)" in l for l in out), out
for pid in ("", "outside-of-project", "default-cli-project", "sumiu"):
    argv, cwd, out = run_one(pid, ws_uri)
    assert "--project" not in argv and os.path.samefile(cwd, ws), (pid, argv, cwd)
    assert any("pasta:" in l and "CLI Project" in l for l in out), out
argv, cwd, out = run_one("", "")
assert os.path.samefile(cwd, G.HANDOFF_DIR) and "--add-dir" not in argv, (cwd, argv)  # sem pasta: handoffs, nunca a pasta do app
argv, cwd, out = run_one("proj-x", ws_uri, dry=True)                                       # a simulação já mostra o destino
assert argv == [] and any("pasta:" in l and "proj-x (--project)" in l for l in out), out
os.environ.pop("AGY_FAKE_CWD")

# --- UI ---------------------------------------------------------------------------------------
from tkinter import messagebox
info = []
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, _n=n, **k: info.append((_n, a)))
G.STATE_DB = os.path.join(root, "ui_state.db")
os.environ["AGY_EXE"] = FAKE
def wait(a, secs=30):
    end = time.time() + secs
    while (a.loading or a.autorunning) and time.time() < end: a.update(); time.sleep(0.01)
    a.update()
app = G.AntigravityGateApp(); wait(app)
def iid(n): return next(i for i in app.iter_sessions() if app.cid_of(i) == U(n))
def text(): return app.auto_win[1].get("1.0", "end") if app.auto_win else ""

# sem aprovadas
info.clear(); app.start_autorun(); assert info and "Nenhuma sessão aprovada" in info[0][1][1]
for n in (1, 2, 3):
    app.tree.selection_set(iid(n)); app.mark_selected("aprovada")
# cancelar a confirmação não faz nada
app.confirm_autorun = lambda its, done: None
app.start_autorun(); assert not app.autorunning and calls() == [] if False else not app.autorunning
# simulação pela tela
app.confirm_autorun = lambda its, done: {'dry_run': True, 'redo': False}
reset("ok"); app.start_autorun(); assert app.autorunning; wait(app)
assert "Fim." in text() and "3 dossiês" in text() and calls() == []
app.cancel_autorun(); assert app.auto_win is None
# duas simulações seguidas (1.0.2): a janela anterior fecha; cada janela age só sobre si; janela presa à principal
reset("ok"); app.start_autorun(); wait(app); w1 = app.auto_win[0]
assert str(w1.transient()) == str(app), "janela de andamento acima da principal (transient)"
app.start_autorun(); wait(app); w2 = app.auto_win[0]
assert w2 is not w1 and not w1.winfo_exists() and w2.winfo_exists(), "uma janela de andamento por vez"
stray = G.tk.Toplevel(app); app.close_autorun(stray)
assert not stray.winfo_exists() and app.auto_win and app.auto_win[0] is w2, "fechar outra janela não mexe na atual"
app.close_autorun(w2); assert app.auto_win is None and not w2.winfo_exists()
# execução real: cota na segunda -> lote interrompido, rótulos mostram só as retomadas ok
app.confirm_autorun = lambda its, done: {'dry_run': False, 'redo': False}
reset("ok,quota,ok"); app.start_autorun()
info.clear(); app.start_autorun(); assert info and "já está em andamento" in info[0][1][1]       # trava contra segundo clique
wait(app); t = text()
assert "Cota do modelo esgotada (volta em 31h40m31s)" in t and "motivo: cota esgotada" in t and len(calls()) == 2, t
assert "↪ retomada" in app.tree.item(iid(1), "text") and "↪" not in app.tree.item(iid(2), "text")
app.cancel_autorun()
# segunda rodada: as já retomadas ficam de fora; sobra a 2 e a 3
seen = {}
app.confirm_autorun = lambda its, done: (seen.update(n=len(its), done=set(done)), {'dry_run': False, 'redo': False})[1]
reset("ok,ok"); app.start_autorun(); wait(app)
assert seen['done'] == {U(1)} and len(calls()) == 2 and "↪" in app.tree.item(iid(3), "text") and "↪" in app.tree.item(iid(2), "text"), (seen, calls())
app.cancel_autorun()
# nada a fazer
info.clear(); app.start_autorun(); assert info and "já foram retomadas" in info[0][1][1]
# agy ausente (fora da simulação)
os.environ["AGY_EXE"] = "/nao/existe"; app.confirm_autorun = lambda its, done: {'dry_run': False, 'redo': True}
info.clear(); app.start_autorun(); assert info and info[0][0] == "showerror" and "agy" in info[0][1][1] and not app.autorunning
# o estado das retomadas persiste
app.destroy(); app = G.AntigravityGateApp(); wait(app)
assert "↪ retomada" in app.tree.item(iid(1), "text") and "↪ retomada" in app.tree.item(iid(3), "text")
app.destroy(); print("TODOS OS TESTES AUTORUN OK")
