import os, sys, sqlite3, tempfile, time, struct
root = tempfile.mkdtemp(prefix="agybrand_")
base = os.path.join(root, "gemini")
os.environ.update(HOME=os.path.join(root, "home"), ANTIGRAVITY_HOME=base, LOCALAPPDATA=os.path.join(root, "local"))
U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)
ant = os.path.join(base, "antigravity"); conv = os.path.join(ant, "conversations"); os.makedirs(conv); os.makedirs(os.path.join(base, "config", "projects"))
c = sqlite3.connect(os.path.join(ant, "conversation_summaries.db"))
c.execute("CREATE TABLE conversation_summaries(conversation_id TEXT, title TEXT, preview TEXT, step_count INT, last_modified_time TEXT, project_id TEXT, workspace_uris TEXT, agent_name TEXT, parent_conversation_id TEXT)")
c.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?,?,?)", (U(1), "", "sessao 1", 1, "2026-10-26T10:00:00Z", "", "", "", "")); c.commit(); c.close()
d = sqlite3.connect(os.path.join(conv, U(1) + ".db")); d.execute("CREATE TABLE steps(idx INTEGER PRIMARY KEY, step_type INT, status INT, step_payload BLOB, error_details BLOB)"); d.commit(); d.close()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G
from tkinter import messagebox
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, **k: None)
G.setup_logging()
fake_agy = os.path.join(root, "agy.exe"); open(fake_agy, "w").write("x")

# 1. arquivos do ícone: .ico com 7 tamanhos e PNGs de 256, 64 e 32 px
ico = open(os.path.join(G.asset_dir(), "app.ico"), "rb").read()
assert struct.unpack("<HHH", ico[:6]) == (0, 1, 7), "app.ico: 7 imagens"
for n in (256, 64, 32):
    png = open(os.path.join(G.asset_dir(), f"app-{n}.png"), "rb").read()
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", png[16:24]) == (n, n), n

# 2. o remote control no login: procura 'remote-control' na chave Run; fora do Windows, não mostra
assert G.remote_control_registered([("Foo", "x.exe"), ("AgyRemote", "agy.exe remote-control start")]) is True
assert G.remote_control_registered([("Foo", "x.exe")]) is False and G.remote_control_registered([]) is False
assert G.remote_control_registered(None) is G.run_key_values() if os.name != "nt" else True
orig_run_key = G.run_key_values

def wait(a):
    end = time.time() + 20
    while a.loading and time.time() < end: a.update(); time.sleep(0.01)
    for _ in range(6): a.update(); time.sleep(0.02)

# 3. ícone nas janelas e ambiente na barra lateral (agy e daemon), com as cores do tema
os.environ["AGY_EXE"] = fake_agy; G.run_key_values = lambda: [("AgyRemote", "agy.exe remote-control start")]
app = G.AntigravityGateApp(); app.geometry("1240x720+0+0"); wait(app)
assert len(app._app_icons) == 3 and all(i.width() in (256, 64, 32) for i in app._app_icons)
assert app.env_agy.cget("text") == "\u25cf agy encontrado" and app.env_agy.cget("fg") == app.t["success"] and app.env_tips[0] == fake_agy
assert app.env_rc.cget("text") == "\u25cf remoto: inicia no login" and app.env_rc.winfo_manager() == "pack"
os.environ["AGY_EXE"] = os.path.join(root, "nao-existe.exe"); G.run_key_values = lambda: []
app.update_env_status(); app.update()
assert app.env_agy.cget("text") == "\u25cb agy n\u00e3o encontrado" and app.env_agy.cget("fg") == app.t["warning"] and "PATH" in app.env_tips[0]
assert app.env_rc.cget("text") == "\u25cb remoto: n\u00e3o inicia no login" and app.env_rc.cget("fg") == app.t["warning"]
G.run_key_values = lambda: None; app.update_env_status(); app.update(); assert not app.env_rc.winfo_manager(), "sem Windows, a linha do remoto some"
G.run_key_values = lambda: [("AgyRemote", "agy.exe remote-control start")]; os.environ["AGY_EXE"] = fake_agy
app.refresh(); wait(app); assert app.env_state == (True, True), "Atualizar (F5) relê o ambiente"
for key in G.THEME_ORDER:
    app.set_theme(key); app.update(); assert app.env_agy.cget("fg") == G.THEMES[key]["success"], key
app.destroy()

# 4. autoteste do .exe informa fontes e ícone
G.run_key_values = orig_run_key
out = os.path.join(root, "selftest.txt"); assert G.selftest(out) == 0
txt = open(out, encoding="utf-8").read(); assert txt.startswith("OK") and "\u00edcone ok" in txt and "fontes registradas" in txt, txt
print("TODOS OS TESTES DA MARCA E DO AMBIENTE OK")
