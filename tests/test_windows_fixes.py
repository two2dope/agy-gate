import os, sys, json, sqlite3, tempfile, time, threading, glob
# Ajustes do primeiro teste real no Windows (26/10): caminho do workspace, lista de tema em outro monitor,
# Sobre só com ícone e lista de modelos do agy.
root = tempfile.mkdtemp(prefix="agywin_")
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

# --- 1. workspace: file:///c%3A/... vira c:\... (antes saía \c:\..., e o Auto-Run não passava a pasta ao agy)
assert G.uri_to_path("file:///c%3A/Users/Thom%C3%A1z/Projetos/01_dev-systems/navigator-agy", nt=True) == r"c:\Users\Thomáz\Projetos\01_dev-systems\navigator-agy"
assert G.uri_to_path("file:///C:/x/meu%20projeto", nt=True) == r"C:\x\meu projeto"
assert G.uri_to_path("file:///home/u/meu%20projeto", nt=False) == "/home/u/meu projeto"
ws = os.path.join(root, "meu projeto"); os.makedirs(ws)
import urllib.parse
assert G.workspace_dirs("file://" + urllib.parse.quote(ws)) == [ws]
assert G.uri_paths('["file:///c%3A/a/b"]') == [G.uri_to_path("file:///c%3A/a/b")]

# --- 2. lista suspensa no monitor da janela, mesmo com coordenadas negativas (monitor à esquerda do principal)
area = (-1366, 0, 1366, 728)
x, y = G.dropdown_pos(area, -300, 40, 120, 34, 260, 400, gap=2)
assert (x, y) == (-440, 76), (x, y)                                  # alinhada à direita do botão, abaixo dele
x, y = G.dropdown_pos(area, -1360, 40, 60, 34, 260, 400, gap=2)
assert x == -1366, x                                                  # não sai pela esquerda do monitor
x, y = G.dropdown_pos((0, 0, 1366, 728), 1200, 600, 120, 34, 260, 400, gap=2)
assert x == 1200 + 120 - 260 and y == 600 - 400 - 2, (x, y)           # sem espaço embaixo: abre para cima
x, y = G.dropdown_pos((1366, 0, 1920, 1040), 3250, 40, 120, 34, 260, 400, gap=2)
assert x == 1366 + 1920 - 260, x                                      # não sai pela direita

def wait(a, secs=20):
    end = time.time() + secs
    while a.loading and time.time() < end: a.update(); time.sleep(0.01)
    a.update()
app = G.AntigravityGateApp(); wait(app)
calls_area = []
real_area = G.work_area_at
G.work_area_at = lambda root, x=None, y=None: (calls_area.append((x, y)), real_area(root, x, y))[1]
app.show_theme_menu(); app.update()
assert calls_area and calls_area[-1][0] is not None, "a lista consulta a área útil do monitor do botão"
app.theme_picker.close(); G.work_area_at = real_area

# --- 3. Sobre: só o ícone (texto vira dica); sem ícones, mostra o texto
b = app.btn["about"]
assert b.icon_only and b.compact and b.glyph() and "Sobre" in b.tooltip_text()
app.geometry("1600x800"); app.update(); app._fit_all(); assert b.compact, "janela larga não volta a mostrar o texto"
x1, _, x2, _ = b.bbox("all"); assert not [i for i in b.find_all() if b.type(i) == "text" and b.itemcget(i, "text") == "Sobre"]
app.set_icon_mode("none"); app._fit_all(); app.update()
assert [i for i in b.find_all() if b.type(i) == "text" and b.itemcget(i, "text") == "Sobre"], "sem ícones o botão mostra o texto"
app.set_icon_mode("symbol"); app.update()

# --- 4. modelos do agy: lista conhecida; a lista que o agy devolve no erro é aproveitada
err = ('invalid model selection (--model "Gemini 3.8 Flash" --effort ""): model Gemini 3.8 Flash is not recognized\n'
       'Available models:\n  Gemini 4 Argon (Medium)\n  Gemini 3.8 Flash (High)\n  Gemini 3.8 Flash (Medium)\n  Novo Modelo X (Low)\n')
assert G.parse_agy_models(err) == ["Gemini 4 Argon (Medium)", "Gemini 3.8 Flash (High)", "Gemini 3.8 Flash (Medium)", "Novo Modelo X (Low)"]
assert G.parse_agy_models("sem lista") == []
assert "Gemini 3.8 Flash (Medium)" in G.AGY_MODELS and "Claude Sonnet 5.5 (Medium)" in G.AGY_MODELS

reset("badmodel"); st = store(); logs = []
res = G.AutoRunner(items([1]), st, logs.append, agy=FAKE, dry_run=False, model="Gemini 3.8 Flash").run()
assert res['failed'] == 1 and res['models'] and "Novo Modelo X (Low)" in res['models'], res
assert any("Modelos aceitos pelo agy" in l and "Gemini 3.8 Flash (Medium)" in l for l in logs), logs

app.settings["agy_models_known"] = ["Novo Modelo X (Low)"]
assert app.agy_model_choices() == ["Novo Modelo X (Low)"], "a lista devolvida pelo agy substitui a embutida"
app.settings["agy_models_known"] = []
assert "Gemini 4 Argon (Medium)" in app.agy_model_choices(), "sem lista do agy, vale a embutida"
app.on_auto_event('auto_done', dict(ok=0, dossier=0, failed=1, skipped=0, quota='', aborted='', junk=[], models=["Outro (High)"]))
assert G.load_settings().get("agy_models_known") == ["Outro (High)"]
app.destroy()
print("TODOS OS TESTES DE AJUSTES DO WINDOWS OK")
