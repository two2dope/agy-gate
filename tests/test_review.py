import os, sys, json, sqlite3, tempfile, time, threading, glob
# Achados da revisão de código do branch (27/10): log sem segredos, lixo só do Auto-Run, Basic ancorado,
# exportação de uma sessão por qualquer caminho, filtro de selo atualizado, dica após recarga, notificações vizinhas.
root = tempfile.mkdtemp(prefix="agyrv_")
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
from tkinter import messagebox
os.environ["AGY_EXE"] = FAKE


def calls(): return [json.loads(l) for l in open(LOG)] if os.path.exists(LOG) else []
def reset(seq):
    if os.path.exists(LOG): os.remove(LOG)
    os.environ["AGY_FAKE_SEQ"] = seq
def items(ids):
    return [{'cid': U(i), 'title': "s%d" % i, 'fpath': os.path.join(conv, U(i) + ".db"),
             'meta': {'cid': U(i), 'title': "s%d" % i, 'fpath': os.path.join(conv, U(i) + ".db")}, 'workspace': ''} for i in ids]
def store(): return G.StateStore(os.path.join(root, "st_%d.db" % time.time_ns()))

os.environ["AGY_FAKE_CONV"] = conv
import types, logging
from tkinter import messagebox, filedialog
shown = []
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, **k: shown.append((n, a)))
messagebox.askyesno = lambda *a, **k: True
def wait(a, secs=20):
    end = time.time() + secs
    while (a.loading or a.autorunning) and time.time() < end: a.update(); time.sleep(0.01)
    a.update()

# --- 4. gate.log sem segredos da resposta do agy
G.setup_logging()
p = os.path.join(root, "fake_secret.py")
open(p, "w").write("import json, sys\nprint(json.dumps({'conversation_id': 'c', 'status': 'SUCCESS', 'response': 'chave sk_live_51HxAbCdEfGhIjKlMnOpQrStUv ok'}))\n")
os.chmod(p, 0o755)
open(p, "r+").write("#!" + sys.executable + "\n" + open(p).read())
res = G.AutoRunner(items([1]), store(), [].append, agy=p, dry_run=False).run()
for h in G.log.handlers: h.flush()
text = open(G.LOG_FILE, encoding="utf-8").read()
assert "agy 00000001" in text and "sk_live_51" not in text and "[REDACTED]" in text, text[-500:]

# --- 7. "basic" em texto comum não é mascarado; cabeçalho Authorization é
for benign in ("covers basic responsibilities", "use the Basic DatabaseConnectionPool now", "Basic usage of the API"):
    assert G.redact(benign) == benign, benign
assert "dXNlcjpw" not in G.redact("Authorization: Basic dXNlcjpwYXNzd29yZA==")

# --- 2. só arquiva sessão nova que é do Auto-Run (primeira fala = prompt do Auto-Run)
user_cid = "dddddddd-0000-0000-0000-000000000001"
def make_session(cid, first_text):
    c = sqlite3.connect(os.path.join(conv, cid + ".db"))
    c.execute("CREATE TABLE steps (idx integer PRIMARY KEY, step_type integer, status integer, step_payload blob, error_details blob)")
    c.execute("INSERT INTO steps VALUES(0,14,3,?,NULL)", (fv(1, 14) + fl(19, fs(2, first_text)),)); c.commit(); c.close()
class R(G.AutoRunner):
    def _run_agy(self, args):
        make_session(user_cid, "conversa minha aberta no meio")         # do usuário: não pode ser arquivada
        make_session("eeeeeeee-0000-0000-0000-000000000001", "/plan " + args[-1])  # criada pelo agy com o nosso prompt
        return '{"conversation_id":"","status":"ERROR","error":"falhou"}', "", None, 1
st = store()
res = R(items([1]), st, [].append, agy="agy", dry_run=False).run()
assert "eeeeeeee-0000-0000-0000-000000000001" in res['junk'] and user_cid not in res['junk'], res['junk']
assert st.load().get(user_cid) is None

# --- 3. mensagem para agy .cmd não sugere trocar de pasta (o problema é o prompt de várias linhas)
msg = G.cmd_shim_problem(["agy.cmd", "--print", "linha1\nlinha2"])
assert "AGY_EXE" in msg and "pasta" not in msg, msg

app = G.AntigravityGateApp(); wait(app)
sessions = list(app.iter_sessions())
# --- 8. exportar pelo menu com várias selecionadas: avisa e não exporta
asked = []; filedialog.asksaveasfilename = lambda **k: (asked.append(k), "")[1]
app.tree.selection_set(sessions[:2]); shown.clear()
app.start_export('full'); app.start_export('dossier')
assert not asked and shown and "uma sessão" in shown[-1][1][1], shown

# --- 9. filtro de selo acompanha a marcação
app.toggle_chip_filter("pendente"); app.update()
first = next(app.iter_sessions()); cid = app.cid_of(first)
app.tree.selection_set(first); app.mark_selected("aprovada"); app.update()
assert cid not in [app.cid_of(i) for i in app.iter_sessions()], "aprovada sai do filtro de pendentes"
assert app.chip_filter == "pendente" and str(len(app.match)) in app.status.cget("text")
app.clear_search()

# --- 5. dica pendente some quando a tabela é refeita
sid = next(app.iter_sessions())
x, y, w, h = app.tree.bbox(sid, "col_title")
app.cell_tips.key, app.cell_tips.text = (sid, "col_title"), "dica"
app.cell_tips.job = app.tree.after(10000, app.cell_tips.show_now)
app.populate(); app.update()
assert app.cell_tips.key is None and app.cell_tips.job is None and app.cell_tips.tip is None
app.cell_tips.show_now()  # chamada atrasada depois da recarga não pode quebrar

# --- 6. duas notificações: sair de uma para a vizinha rearma a primeira
t1 = app.notify("ok", "um", [("Desfazer", lambda: None)], ttl=100000)
t2 = app.notify("ok", "dois", [("Desfazer", lambda: None)], ttl=100000)
assert t1._mine(str(t1) + ".!label") and not t1._mine(str(t2)) and not t1._mine(str(t2) + ".!iconbutton")
app.destroy()
print("TODOS OS TESTES DA REVISÃO OK")
