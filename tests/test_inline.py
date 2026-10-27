import os, sys, json, sqlite3, tempfile, time, threading, glob
# Retomada sem leitura de arquivo (o modo sem janela do agy nega read_file) e sucesso só com resposta.
root = tempfile.mkdtemp(prefix="agyinl_")
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

os.environ["AGY_FAKE_CONV"] = conv
# --- sucesso exige resposta; ação negada aparece no erro
real = json.dumps({"conversation_id": "2a6dbfa4", "status": "SUCCESS", "response": "", "denied_actions": [{"action": "read_file", "display_name": "ReadFile"}]})
r = G.parse_agy_output(real, "jetski: no output produced", 0)
assert not r['ok'] and "sem resposta" in r['error'] and "read_file" in r['error'] and r['conversation_id'] == "2a6dbfa4", r
r = G.parse_agy_output(json.dumps({"conversation_id": "c", "status": "SUCCESS", "response": "  "}), "", 0)
assert not r['ok'] and "sem resposta" in r['error']
assert G.parse_agy_output(json.dumps({"conversation_id": "c", "status": "SUCCESS", "response": "Entendi."}), "", 0)['ok']

reset("denied"); st = store()
res = G.AutoRunner(items([1]), st, [].append, agy=FAKE, dry_run=False).run()
cid1 = "aaaaaaaa-0000-0000-0000-000000000001"
assert res['ok'] == 0 and res['failed'] == 1 and st.handoffs_ok() == {} and cid1 in res['junk'] and st.load().get(cid1) == "arquivada", (res, st.load())

# --- o dossiê vai dentro do prompt (o agy não precisa ler arquivo)
reset("ok"); st = store()
res = G.AutoRunner(items([1]), st, [].append, agy=FAKE, dry_run=False).run()
prompt = calls()[0][-1]
assert res['ok'] == 1 and "pedido 1" in prompt and "# Dossiê de retomada" in prompt and "retomada_00000001_" in prompt, prompt[:400]
big = "x" * (G.DOSSIER_INLINE_MAX * 3)
a = G.build_agy_args("agy", os.path.join(root, "d.md"), [], dossier_text="# Dossiê\n" + big + "\nFIM")
assert len(a[-1]) < G.DOSSIER_INLINE_MAX + 2000 and "dossiê cortado" in a[-1], len(a[-1])
a = G.build_agy_args("agy", os.path.join(root, "d.md"), [], model="M", dossier_text="curto")
assert a[-2] == "--print" and a.index("--model") < a.index("--print") and "curto" in a[-1]

# --- retomadas falsas de versões anteriores (ok sem resposta) são corrigidas ao abrir
path = os.path.join(root, "old_state.db")
c = sqlite3.connect(path)
c.execute("CREATE TABLE handoffs(id INTEGER PRIMARY KEY AUTOINCREMENT, src_cid TEXT NOT NULL, new_cid TEXT, dossier_path TEXT, status TEXT NOT NULL, detail TEXT, at TEXT NOT NULL)")
c.execute("CREATE TABLE session_state(cid TEXT PRIMARY KEY, status TEXT NOT NULL, updated_at TEXT NOT NULL)")
c.executemany("INSERT INTO handoffs(src_cid,new_cid,dossier_path,status,detail,at) VALUES(?,?,?,?,?,?)",
              [("a56", "falsa1", "d", "ok", "", "t"), ("a56", "falsa2", "d", "ok", None, "t"), ("74a", "real", "d", "ok", "### 1. Entendimento", "t")])
c.execute("INSERT INTO session_state VALUES('falsa2','aprovada','t')")
c.commit(); c.close()
st = G.StateStore(path)
assert st.handoffs_ok() == {"74a": "real"}, st.handoffs_ok()
s = st.load()
assert s.get("falsa1") == "arquivada" and s.get("falsa2") == "aprovada", "arquiva só as que não tinham marcação do usuário"
with sqlite3.connect(path) as c:
    assert c.execute("SELECT COUNT(*) FROM handoffs WHERE status='erro' AND detail LIKE '%sem resposta%'").fetchone()[0] == 2
G.StateStore(path)  # de novo: nada muda
assert G.StateStore(path).handoffs_ok() == {"74a": "real"}
print("TODOS OS TESTES DE RETOMADA SEM ARQUIVO OK")
