import os, sys, json, sqlite3, tempfile, time, threading, glob
# Janela Sobre (F1 e botão no cabeçalho) e botões do painel de detalhes com largura uniforme.
root = tempfile.mkdtemp(prefix="agyabout_")
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

# --- dados do autor e diagnóstico
assert G.APP_AUTHOR == "Thominha" and G.APP_EMAIL == "twoo2dope@gmail.com"
assert G.APP_REPO == "https://github.com/two2dope/agy-gate" and G.APP_GITHUB == "https://github.com/two2dope"
info = G.about_info()
for piece in (f"AntigravityGate {G.__version__}", "Python ", "Tk ", "Sistema:", G.BASE_DIR, FAKE, G.LOG_DIR, G.LOG_FILE):
    assert piece in info, (piece, info)
os.environ["AGY_EXE"] = "/nao/existe"; assert "agy: não encontrado" in G.about_info(); os.environ["AGY_EXE"] = FAKE

def wait(a, secs=20):
    end = time.time() + secs
    while a.loading and time.time() < end: a.update(); time.sleep(0.01)
    a.update()
app = G.AntigravityGateApp(); wait(app)

# --- abrir pelo botão e por F1; uma janela só
assert "about" in app.btn and app.btn["about"].tooltip_text()
app.btn["about"].invoke(); app.update()
dlg = app.about_win
assert isinstance(dlg, G.AboutDialog) and dlg.winfo_exists()
texts = []
def walk(w):
    for c in w.winfo_children():
        try: texts.append(c.cget("text"))
        except Exception: pass
        walk(c)
walk(dlg); blob = " ".join(texts)
for piece in ("AntigravityGate", G.__version__, "Thominha", "twoo2dope@gmail.com", "github.com/two2dope/agy-gate", "sem vínculo"):
    assert piece in blob, (piece, blob)
app.event_generate("<F1>"); app.update(); assert app.about_win is dlg, "F1 com a janela aberta não abre outra"

# --- copiar informações
dlg.copy_info(); app.update()
assert app.clipboard_get() == G.about_info()
# --- Esc fecha; F1 reabre
dlg.event_generate("<Escape>"); app.update(); assert app.about_win is None
app.focus_force(); app.update(); app.event_generate("<F1>"); app.update()
assert app.about_win is not None and app.about_win.winfo_exists(); app.about_win.close(); app.update()

# --- tema: a janela segue a paleta
app.set_theme("claro"); app.btn["about"].invoke(); app.update()
assert app.about_win.cget("bg") == app.t['panel']; app.about_win.close()

# --- (b1) painel de detalhes: quatro botões com a mesma largura, desenho ocupando a largura toda
app.tree.selection_set(next(app.iter_sessions())); app.update()
names = ("d_copy", "d_folder", "d_export", "d_dossier")
widths = {n: app.btn[n].winfo_width() for n in names}
assert len(set(widths.values())) == 1, widths
for n in names:
    b = app.btn[n]; x1, _y1, x2, _y2 = b.bbox("all")
    assert x2 - x1 >= b.winfo_width() - 3, (n, b.bbox("all"), b.winfo_width())
assert G.ICONS["export"][0] != "\uE8A5", "ícone de exportar trocado"
app.destroy()
print("TODOS OS TESTES SOBRE OK")
