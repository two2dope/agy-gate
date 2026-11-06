import os, sys, sqlite3, tempfile, time, json
root = tempfile.mkdtemp(prefix="agytheme_")
base = os.path.join(root, "gemini")
os.environ.update(HOME=os.path.join(root, "home"), ANTIGRAVITY_HOME=base, LOCALAPPDATA=os.path.join(root, "local"))
U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)
ant = os.path.join(base, "antigravity"); conv = os.path.join(ant, "conversations"); os.makedirs(conv); os.makedirs(os.path.join(base, "config", "projects"))
c = sqlite3.connect(os.path.join(ant, "conversation_summaries.db"))
c.execute("CREATE TABLE conversation_summaries(conversation_id TEXT, title TEXT, preview TEXT, step_count INT, last_modified_time TEXT, project_id TEXT, workspace_uris TEXT, agent_name TEXT, parent_conversation_id TEXT)")
for i in range(1, 5): c.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?,?,?)", (U(i), "", "sessao %d" % i, i, "2026-10-26T1%d:00:00Z" % i, "", "", "", ""))
c.commit(); c.close()
for i in range(1, 5):
    d = sqlite3.connect(os.path.join(conv, U(i) + ".db")); d.execute("CREATE TABLE steps(idx INTEGER PRIMARY KEY, step_type INT, status INT, step_payload BLOB, error_details BLOB)"); d.commit(); d.close()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G
from tkinter import messagebox
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, **k: None)
messagebox.askyesno = lambda *a, **k: True
def wait(a):
    end = time.time() + 20
    while a.loading and time.time() < end: a.update(); time.sleep(0.01)
    for _ in range(6): a.update(); time.sleep(0.02)
def iid(a, n): return next(i for i in a.iter_sessions() if a.cid_of(i) == U(n))

import ctypes, types
app = G.AntigravityGateApp(); wait(app)
# classificação claro/escuro: só o tema Claro e o Brutalista (cabeçalho amarelo) têm barra clara
dark = {k: G.is_dark_color(t['header_bg']) for k, t in G.THEMES.items()}
assert dark == {"escuro": True, "claro": False, "milspec": True, "cyber": True, "vidro": True, "brutal": False, "obsidiana": True, "mecha": True}, dark
# fora do Windows não faz nada e não levanta
assert G.style_titlebar(app, app.t) is None
# lógica do Windows com a API simulada: valores, ordem e cores em COLORREF (0x00BBGGRR)
calls, pos = [], []
def DwmSetWindowAttribute(hwnd, attr, ptr, size):
    calls.append((hwnd, attr, ctypes.cast(ptr, ctypes.POINTER(ctypes.c_int)).contents.value, size)); return 0
def GetParent(h): return 4242
def SetWindowPos(*a): pos.append(a); return 1
msgs, redraws = [], []
def SendMessageW(h, m, w, l): msgs.append((h, m, w)); return 0
def RedrawWindow(h, r, g, f): redraws.append((h, f)); return 1
fake = types.SimpleNamespace(user32=types.SimpleNamespace(GetParent=GetParent, SetWindowPos=SetWindowPos, GetForegroundWindow=lambda: 4242,
                                                          SendMessageW=SendMessageW, RedrawWindow=RedrawWindow), dwmapi=types.SimpleNamespace(DwmSetWindowAttribute=DwmSetWindowAttribute))
real_name, real_windll = G.os.name, getattr(ctypes, "windll", None)
G.os.name = "nt"; ctypes.windll = fake
try:
    t = dict(G.THEMES["milspec"]); res = G.style_titlebar(app, t)
    assert res == {"escuro": 0, "fundo": 0, "texto": 0, "borda": 0}, res
    by = {a: v for (_h, a, v, _s) in calls}
    assert by[20] == 1 and by[35] == 0x11 << 16 | 0x13 << 8 | 0x0d and by[36] == 0x4a | 0xde << 8 | 0x80 << 16, by   # header_bg #0d1311, header_fg #4ade80
    assert by[34] == 0x2a | 0x45 << 8 | 0x36 << 16 and all(h == 4242 and s == 4 for (h, _a, _v, s) in calls)   # border #2a4536
    assert pos and pos[0][-1] == 0x37
    # Windows 10: reenvia a ativação (janela em foco termina ativa) e repinta a moldura
    assert msgs == [(4242, 0x86, 0), (4242, 0x86, 1)] and redraws == [(4242, 0x0501)], (msgs, redraws)
    calls.clear(); G.style_titlebar(app, dict(G.THEMES["claro"])); assert {a: v for (_h, a, v, _s) in calls}[20] == 0
    # Windows sem suporte (HRESULT de erro): cai para o atributo antigo e não levanta
    calls.clear(); fake.dwmapi.DwmSetWindowAttribute = lambda *a: -2147024809
    res = G.style_titlebar(app, t); assert res["escuro"] != 0 and "escuro_antigo" in res, res
    # API ausente: não levanta
    ctypes.windll = types.SimpleNamespace(); assert G.style_titlebar(app, t) is None
finally:
    G.os.name = real_name
    if real_windll is None: del ctypes.windll
    else: ctypes.windll = real_windll
app.destroy()
print("TODOS OS TESTES OK")
