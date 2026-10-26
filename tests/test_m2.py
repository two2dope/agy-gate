import os, sys, sqlite3, tempfile, time
root = tempfile.mkdtemp(prefix="agym2_")
home = os.path.join(root, "home"); os.makedirs(os.path.join(home, "Desktop"))
base = os.path.join(root, "gemini")
os.environ.update(HOME=home, ANTIGRAVITY_HOME=base, LOCALAPPDATA=os.path.join(root, "local"))

def vi(n):
    o = bytearray()
    while True:
        b = n & 0x7f; n >>= 7
        if n: o.append(b | 0x80)
        else: o.append(b); return bytes(o)
fv = lambda f, v: vi(f << 3) + vi(v)
fl = lambda f, b: vi(f << 3 | 2) + vi(len(b)) + b
fs = lambda f, s: fl(f, s.encode())
U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)

conv = os.path.join(base, "antigravity", "conversations"); os.makedirs(conv)
bkp = os.path.join(base, "antigravity-ide.bak", "conversations"); os.makedirs(bkp)
os.makedirs(os.path.join(base, "config", "projects"))

def mk(folder, cid, steps):
    c = sqlite3.connect(os.path.join(folder, cid + ".db"))
    c.execute("CREATE TABLE steps (idx integer PRIMARY KEY, step_type integer NOT NULL DEFAULT 0, status integer NOT NULL DEFAULT 0, step_payload blob)")
    c.execute("CREATE INDEX idx_steps_step_type ON steps(step_type)")
    for i, (t, payload) in enumerate(steps): c.execute("INSERT INTO steps VALUES(?,?,3,?)", (i, t, payload))
    c.commit(); c.close()

user = fv(1, 14) + fl(19, fs(2, "/gdrive lista meus 10\nultimos arquivos") + fs(3, "x"))
resp = lambda f2, f5: fv(1, 15) + fl(5, fv(3, 2) + fl(9, fv(1, 1318) + fv(2, f2) + (fv(5, f5) if f5 else b"") + fv(3, 10) + fv(9, 6) + fv(10, 4)))
A, B, C = U(1), U(2), U(3)
mk(conv, A, [(14, user), (15, resp(3000, 150000)), (132, fv(1, 132)), (15, resp(2500, 153000))])      # ctx = 2500 + 153000 = 155500 -> Rot
mk(conv, B, [(101, fv(1, 101) + fl(114, fs(1, "hook") + fs(3, "hook_json_SessionStart"))),
             (101, fv(1, 101) + fl(114, fs(1, "[Message] ts") + fl(2, fs(1, "Message from Parent Agent") + fl(10, fs(1, "Acesse a URL https://x.example/y"))) + fs(3, "agent_message"))),
             (15, resp(108524, 0))])                                                                    # cache frio: só f2 -> 108k, sem Rot
mk(conv, C, [(15, resp(1200, 0))])                                                                      # 1200 tokens
mk(bkp, A, [(14, user)])

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G
from tkinter import messagebox
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, **k: None)
G.setup_logging()

def wait(a):
    end = time.time() + 30
    while a.loading and time.time() < end:
        a.update(); time.sleep(0.01)
    a.update()
def leaves(a): return {a.tree.item(c, "values")[7]: a.tree.item(c, "values") for p in a.tree.get_children() for c in a.tree.get_children(p)}

# 1. janela abre sem esperar a varredura lenta
calls = {"metrics": 0, "scan": 0}
orig_metrics, orig_scan = G.session_metrics, G.scan_source
def slow(path):
    calls["metrics"] += 1; time.sleep(0.4); return orig_metrics(path)
def counted_scan(*a, **k):
    calls["scan"] += 1; return orig_scan(*a, **k)
G.session_metrics, G.scan_source = slow, counted_scan
t0 = time.time(); app = G.AntigravityGateApp(); app.update(); dt = time.time() - t0
print("construtor: %.2fs | loading=%s | status=%r" % (dt, app.loading, app.status.cget("text")))
assert dt < 1.0 and app.loading and "carregando" in app.status.cget("text"), "UI não pode esperar a varredura (3 sessões x 0,4s)"
wait(app); assert not app.loading

# 2. métricas
L = leaves(app)
print({k[:8]: (v[2], v[5]) for k, v in L.items()})
assert L[A][2] == G.ctx_label(155500) and "⚠" in L[A][2], L[A][2]
assert L[B][2] == G.ctx_label(108524) and "⚠" not in L[B][2], L[B][2]
assert L[C][2] == G.ctx_label(1200), L[C][2]
assert L[A][5] == "/gdrive lista meus 10 ultimos arquivos", L[A][5]            # passo 14, quebra de linha achatada
assert L[B][5] == "Acesse a URL https://x.example/y", L[B][5]                   # sub-agente: mensagem do pai, não o hook
assert str(L[A][3]) == "4" and str(L[B][3]) == "3"

# 3. cache: refresh sem mudança não reabre bancos; mudança reabre só o que mudou
n = calls["metrics"]; app.refresh(); wait(app); assert calls["metrics"] == n, "cache deveria evitar reabrir"
time.sleep(0.01)
c = sqlite3.connect(os.path.join(conv, C + ".db")); c.execute("INSERT INTO steps VALUES(9,15,3,?)", (resp(9999, 0),)); c.commit(); c.close()
app.refresh(); wait(app); assert calls["metrics"] == n + 1, calls
assert leaves(app)[C][2] == G.ctx_label(9999)

# 4. tema não varre o disco e recolore widgets
s0 = calls["scan"]; bg0 = app.top_frame.cget("bg"); sb0 = app.status.cget("bg")
app.toggle_theme(); app.update()
assert calls["scan"] == s0, "tema não deve recarregar dados"
assert app.top_frame.cget("bg") != bg0 and app.status.cget("bg") != sb0 and app.top_frame.cget("bg") == app.t["header_bg"]
app.set_theme("escuro"); app.update(); assert app.top_frame.cget("bg") == bg0

# 5. troca rápida de fonte: vale a última; resposta velha é descartada
G.session_metrics = slow
labels = [s[0] for s in app.sources]
app.src_box.current(1); app.on_source_change()      # backup (1 sessão, lenta)
app.src_box.current(0); app.on_source_change()      # volta p/ ativas
wait(app)
assert set(leaves(app)) == {A, B, C}, leaves(app).keys()
assert "Ativas" in app.status.cget("text") and "carregando" not in app.status.cget("text")

# 6. fonte de backup tem coluna de contexto própria
app.src_box.current(1); app.on_source_change(); wait(app)
assert set(leaves(app)) == {A} and leaves(app)[A][2] == "-"
app.destroy(); print("TODOS OS TESTES M2 OK")
