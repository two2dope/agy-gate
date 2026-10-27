import os, sys, json, sqlite3, tempfile, time, threading, glob
# Etapa 2b da revisão final: teclado, Desfazer que pausa, janelas do Auto-Run no tema com lista marcável,
# janela que reabre maximizada.
root = tempfile.mkdtemp(prefix="agy2b_")
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

import types
from tkinter import messagebox
shown = []
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, **k: shown.append(a))
messagebox.askyesno = lambda *a, **k: True
def wait(a, secs=20):
    end = time.time() + secs
    while (a.loading or a.autorunning) and time.time() < end: a.update(); time.sleep(0.01)
    a.update()

zoomed = []
G.AntigravityGateApp.zoom = lambda self: zoomed.append(self.winfo_ismapped())
s = G.load_settings(); s["window"] = {"w": 900, "h": 600, "x": 40, "y": 30, "zoomed": True, "zx": 400, "zy": 300}; G.save_settings(s)
app = G.AntigravityGateApp(); wait(app)
for _ in range(20): app.update(); time.sleep(0.02)
# --- 1. maximizada: maximiza depois que a janela aparece (antes de aparecer o Windows ignora)
assert zoomed and zoomed[-1], ("zoom chamado com a janela já visível", zoomed)
sessions = list(app.iter_sessions())

# --- 2. menu de contexto pelo teclado (Shift+F10 e tecla Menu), na linha com foco
popups = []
import tkinter as tk
tk.Menu.tk_popup = lambda self, x, y, entry="": popups.append((self.entrycget(0, "label"), x, y))
app.tree.focus_set(); app.tree.focus(sessions[0]); app.tree.selection_set(sessions[0]); app.update()
app.tree.event_generate("<Shift-F10>"); app.update()
app.tree.event_generate("<KeyPress-App>") if False else app.menu_from_keyboard()
assert len(popups) == 2 and popups[0][0] == "Copiar UUID", popups
labels = []
m = app.build_menu(sessions[0])
for i in range(m.index("end") + 1):
    try: labels.append(m.entrycget(i, "label"))
    except Exception: pass
assert all(ord(ch) <= 0xFFFF for l in labels for ch in l), "sem emoji fora do BMP (Tk 8.6)"

# --- 3. painel de detalhes pelo teclado
bar = app.details_bar
assert str(bar.cget("takefocus")) in ("1", "True")
before = app.settings.get("details", True)
bar.focus_set(); app.update(); bar.event_generate("<Return>"); app.update()
assert app.settings["details"] != before
bar.event_generate("<space>"); app.update(); assert app.settings["details"] == before

# --- 4. dica aparece também com o foco do teclado
b = app.btn["refresh"]
b.event_generate("<FocusIn>"); app.update()
assert b.tooltip.job is not None, "foco agenda a dica"
b.event_generate("<FocusOut>"); app.update(); assert b.tooltip.job is None and b.tooltip.tip is None

# --- 5. notificação com Desfazer pausa com mouse/foco em cima
called = []
toast = app.notify("ok", "1 sessão marcada", [("Desfazer", lambda: called.append(1))], ttl=300)
toast.resume_ms = 300
app.update(); toast.event_generate("<Enter>"); app.update()
assert toast.job is None, "mouse em cima: relógio parado"
t0 = time.time()
while time.time() - t0 < 0.8: app.update(); time.sleep(0.02)
assert toast.winfo_exists() and toast in app.toasts, "com o mouse em cima não some"
toast.resume()
t0 = time.time()
while time.time() - t0 < 1.0 and toast in app.toasts: app.update(); time.sleep(0.02)
assert toast not in app.toasts, "sem o mouse, some depois"

# --- 6. confirmação do Auto-Run: no tema, com caixa por sessão; só as marcadas rodam
for i in sessions: app.tree.selection_add(i)
app.mark_selected("aprovada")
app.handoffs[app.cid_of(sessions[0])] = "aaaaaaaa"   # uma já retomada
real_confirm = app.confirm_autorun
seen = {}
def drive(its, done):
    def act():
        win = app.confirm_win
        seen['bg'] = str(win.cget("bg"))
        checks = app.confirm_checks
        seen['initial'] = {c: v.get() for c, v in checks.items()}
        app.confirm_redo.set(True); app.confirm_redo_changed(); seen['after_redo'] = {c: v.get() for c, v in checks.items()}
        skip = app.cid_of(sessions[1]); checks[skip].set(False); seen['skip'] = skip
        app.confirm_go()
    app.after(300, act)
    return real_confirm(its, done)
app.confirm_autorun = drive
app.start_autorun(); wait(app)
done_cid = app.cid_of(sessions[0])
assert seen['bg'] == app.t['panel'], seen['bg']
assert seen['initial'][done_cid] is False and all(v for c, v in seen['initial'].items() if c != done_cid), seen['initial']
assert seen['after_redo'][done_cid] is True
log_text = app.auto_win[1].get("1.0", "end")
assert f"{len(sessions) - 1} sessão(ões) na fila" in log_text and seen['skip'][:8] not in log_text, log_text
assert str(app.auto_win[1].cget("bg")) == app.t['panel'], "janela de andamento no tema"
assert isinstance(app.auto_win[2], G.IconButton) and app.auto_win[2].text == "Fechar"
app.cancel_autorun()

# nenhuma marcada: avisa e não roda
def none_checked(its, done):
    app.after(300, lambda: ([v.set(False) for v in app.confirm_checks.values()], app.confirm_go()))
    return real_confirm(its, done)
app.confirm_autorun = none_checked; shown.clear()
app.start_autorun(); app.update()
assert not app.autorunning and shown and "Nenhuma sessão marcada" in shown[-1][1], shown
app.destroy()
print("TODOS OS TESTES DA ETAPA 2B OK")
