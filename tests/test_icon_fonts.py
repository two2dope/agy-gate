import os, sys, sqlite3, tempfile, time, json
root = tempfile.mkdtemp(prefix="agyicons_")
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

# 1. os 3 conjuntos cobrem todos os ícones, com glifos da área privada, e as fontes e licenças estão em fonts/
for mode, (family, fname, glyphs) in G.ICON_FONTS.items():
    assert set(glyphs) == set(G.ICONS), (mode, set(G.ICONS) ^ set(glyphs))
    assert all(len(g) == 1 and 0xE000 <= ord(g) <= 0xF8FF for g in glyphs.values()), mode
    assert os.path.getsize(os.path.join(G.font_dir(), fname)) > 100_000, fname
for fn in ("Inter-Regular.ttf", "Inter-Bold.ttf", "JetBrainsMono-Regular.ttf", "JetBrainsMono-Bold.ttf"):
    assert os.path.getsize(os.path.join(G.font_dir(), fn)) > 20_000, fn
assert len([f for f in os.listdir(G.font_dir()) if f.endswith(".ttf")]) == 7, "o CI espera 7 fontes registradas"
for lic in ("LICENSE-font-awesome.txt", "LICENSE-bootstrap-icons.txt", "LICENSE-material-icons.txt", "LICENSE-inter.txt", "LICENSE-jetbrains-mono.txt"):
    assert os.path.isfile(os.path.join(G.font_dir(), lic)), lic

# 2. escolha do glifo: com a fonte, o do conjunto; sem ela, o símbolo Unicode; sem ícones, nada
assert G.icon_glyph("fa", "approve", {"Font Awesome 6 Free Solid"}) == chr(0xF00C)
assert G.icon_glyph("material", "warn", {"Material Icons"}) == chr(0xE002)
assert G.icon_glyph("bootstrap", "search", set()) == G.ICONS["search"][1]
assert G.icon_glyph("mdl2", "copy", set()) == G.ICONS["copy"][0]
assert G.icon_glyph("none", "copy", {"Material Icons"}) == "" and G.icon_glyph("fa", "inexistente", set()) == ""
if os.name != "nt":
    assert G.register_fonts() == [], "fora do Windows não registra nada"

# 3. no app: os modos novos aparecem no menu, valem para botões e lupa, e são lembrados
menu_modes = [m for m, _ in next(v for v in vars(G).values() if isinstance(v, type) and hasattr(v, "ICON_MODES")).ICON_MODES]
assert menu_modes == ["mdl2", "fa", "bootstrap", "material", "symbol", "none"], menu_modes
def wait(a):
    end = time.time() + 20
    while a.loading and time.time() < end: a.update(); time.sleep(0.01)
    a.update()
app = G.AntigravityGateApp(); wait(app)
for mode in ("fa", "bootstrap", "material"):
    app.set_icon_mode(mode); app.update()
    fam = G.ICON_FONTS[mode][0]
    expect = G.ICON_FONTS[mode][2]["approve"] if fam in app.families else G.ICONS["approve"][1]
    assert app.btn["approve"].glyph() == expect, mode
    assert app.search_icon.cget("text") == (G.icon_glyph(mode, "search", app.families) or G.ICONS["search"][1]), mode
    assert G.alert_glyph(app)[0] == G.icon_glyph(mode, "warn", app.families), mode
    assert json.load(open(G.SETTINGS_FILE))["icons"] == mode
app.destroy()
app = G.AntigravityGateApp(); wait(app)
assert app.icon_mode == "material", "estilo de ícones lembrado ao reabrir"
assert "Material Icons (Apache 2.0)" in G.about_info() and "Inter e JetBrains Mono" in G.about_info()
app.destroy(); print("TODOS OS TESTES DE FONTES DE ICONES OK")
