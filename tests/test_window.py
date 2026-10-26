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

def mon(sw, sh, tb=40, side="bottom", at=(0, 0)):
    """monitor (retângulo, área útil) de sw x sh em `at`, com barra de tarefas de `tb` px em `side`"""
    x, y = at
    work = {"bottom": (x, y, sw, sh - tb), "top": (x, y + tb, sw, sh - tb), "left": (x + tb, y, sw - tb, sh), "right": (x, y, sw - tb, sh)}[side]
    return (x, y, sw, sh), work
def desk(*mons):
    """work_at(x, y): área útil do monitor que contém o ponto (o mais próximo, senão); sem ponto, a do primeiro (principal)"""
    def work_at(x, y):
        if x is None: return mons[0][1]
        for (l, t, w, h), work in mons:
            if l <= x < l + w and t <= y < t + h: return work
        return min(mons, key=lambda m: abs(x - m[0][0] - m[0][2] // 2) + abs(y - m[0][1] - m[0][3] // 2))[1]
    return work_at
W = lambda work_at, scale=1.0, saved=None: G.window_geometry(work_at, scale, saved)
FR = 40
def inside(res, work, scale=1.0):
    w, h, x, y = res; l, t, aw, ah = work
    return l <= x and t <= y and x + w <= l + aw and y + h + round(FR * scale) <= t + ah
# 1920x1080 com barra embaixo: tamanho de projeto, centralizada
m = mon(1920, 1080); r = W(desk(m)); assert r[:2] == (1240, 820) and inside(r, m[1]) and r[2] == 340, r
# o caso do relato: 1366x768 com a barra de tarefas NO TOPO: a janela começa abaixo dela e cabe inteira
m = mon(1366, 768, 40, "top"); r = W(desk(m)); assert r[3] >= 40 and inside(r, m[1]) and r[1] >= 520, r
# barra embaixo, à esquerda e à direita
for side in ("bottom", "left", "right"):
    m = mon(1366, 768, 48, side); r = W(desk(m)); assert inside(r, m[1]), (side, r)
# 1920x1080 a 150% (DPI consciente): escalado, dentro da área útil
m = mon(1920, 1080, 60); r = W(desk(m), 1.5); assert inside(r, m[1], 1.5), r
# tela minúscula
m = mon(800, 600); r = W(desk(m)); assert inside(r, m[1]) and r[2] <= 768, r
# salvo: restaurado quando cabe
m = mon(1920, 1080); assert W(desk(m), saved=dict(w=1000, h=700, x=100, y=50)) == (1000, 700, 100, 50)
# salvo por versão anterior, sob a barra do topo (y=35): sobe para a área útil
m = mon(1366, 768, 40, "top"); r = W(desk(m), saved=dict(w=1240, h=658, x=63, y=35)); assert r[3] >= 40 and inside(r, m[1]), r
# salvo maior que a tela e fora dela: puxado para dentro
m = mon(1366, 768); r = W(desk(m), saved=dict(w=1800, h=1200, x=3000, y=-500)); assert inside(r, m[1]), r
# dois monitores: principal 1366x768 (barra no topo) e um 1920x1080 à esquerda e mais alto, com a barra embaixo
prim, left = mon(1366, 768, 40, "top"), mon(1920, 1080, 40, "bottom", at=(-1920, -312))
two = desk(prim, left)
r = W(two, saved=dict(w=1000, h=700, x=-1500, y=-200)); assert r == (1000, 700, -1500, -200), r          # fica no monitor da esquerda
r = W(two, saved=dict(w=1800, h=1000, x=-1500, y=-250)); assert inside(r, left[1]) and r[0] > 1000, r        # grande demais: encaixa nele
r = W(two); assert inside(r, prim[1]) and r[3] >= 40, r                                                    # sem salvo: principal
r = W(desk(prim), saved=dict(w=1000, h=700, x=-1500, y=100)); assert inside(r, prim[1]), r                  # monitor da esquerda desligado
# janelas adicionais: centralizadas sobre a principal e dentro da área útil do monitor dela
F = G.fit_rect
r = F(prim[1], 1.0, 640, 520, 63 + (1240 - 640) // 2, 45 + (678 - 520) // 2, min_size=(0, 0)); assert inside(r, prim[1]) and r[:2] == (640, 520), r
r = F(prim[1], 1.0, 640, 520, 0, 0, min_size=(0, 0)); assert r[3] >= 40 and r[2] >= 0, r      # pedida em (0,0), sob a barra: desce
r = F(prim[1], 1.0, 4000, 3000, 0, 0, min_size=(0, 0)); assert inside(r, prim[1]), r           # maior que a tela: encolhe
# lixo é ignorado
m = mon(1920, 1080); base = W(desk(m))
for bad in (dict(w=5, h="a", x=0, y=0), "lixo", None, dict(w=True, h=True, x=True, y=True), {}):
    assert W(desk(m), saved=bad) == base, bad
# a consulta real (fora do Windows, a tela inteira) é coerente
app = G.AntigravityGateApp(); wait(app)
ar = G.work_area_at(app); assert ar[2] > 300 and ar[3] > 300 and ar == G.work_area_at(app, 100, 100), ar
# janelas adicionais reais: centralizadas sobre a principal, dentro da tela, depois de visíveis
app.geometry("1000x640+120+60"); app.update()
dlg = G.LimitDialog(app); app.update()
assert dlg.winfo_ismapped()
cx, cy = dlg.winfo_rootx() + dlg.winfo_width() // 2, dlg.winfo_rooty() + dlg.winfo_height() // 2
assert abs(cx - (120 + 500)) <= 30 and abs(cy - (60 + 320)) <= 60, (cx, cy, dlg.geometry())
dlg.destroy()
app.geometry("1000x640+0+0"); app.update()        # principal no canto: a janela adicional não passa da borda
dlg = G.LimitDialog(app); app.update()
assert dlg.winfo_rootx() >= 0 and dlg.winfo_rooty() >= 0, dlg.geometry(); dlg.destroy()
# janela de andamento do Auto-Run
app.open_autorun_window(1, True); app.update()
aw = app.auto_win[0]; assert aw.winfo_ismapped() and aw.winfo_width() == 780 and aw.winfo_height() == 420 and aw.winfo_rootx() >= 0 and aw.winfo_rooty() >= 0, aw.geometry()
aw.destroy(); app.destroy(); app = None

# app real: abre dentro da tela, sem estourar, e lembra o que o usuário fez
app = G.AntigravityGateApp(); wait(app)
sw, sh = app.winfo_screenwidth(), app.winfo_screenheight()
app.update(); ww, wh = app.winfo_width(), app.winfo_height()
assert ww <= sw and wh + 40 <= sh and app.winfo_x() >= 0 and app.winfo_y() >= 0, (ww, wh, sw, sh)
assert app.minsize() == (760, 520)
app.geometry("900x600+40+30"); app.update(); time.sleep(0.9); app.update()
assert app.settings['window'] == dict(w=900, h=600, x=40, y=30), app.settings.get('window')
app.on_close()
app = G.AntigravityGateApp(); app.update()
assert app.geometry().startswith("900x600+40+30"), app.geometry()
# fechar logo após mexer também salva
app.geometry("1000x640+60+20"); app.update(); app.on_close()
app = G.AntigravityGateApp(); app.update(); assert app.geometry().startswith("1000x640+60+20"), app.geometry()
app.destroy()
print("TODOS OS TESTES OK")
