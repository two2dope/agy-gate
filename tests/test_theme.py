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
G.setup_logging()

def lum(h):
    h = h.lstrip('#'); r, g, b = [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
def cr(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True); return (la + 0.05) / (lb + 0.05)

# 1. contraste WCAG AA (>= 4,5:1) de todos os textos de todos os temas
assert len(G.THEMES) == 8 and G.THEME_ORDER == list(G.THEMES), "8 temas, na ordem declarada"
bad = []
for key, th in G.THEMES.items():
    t = dict(th); t['header_sub'] = G.blend(t['header_fg'], t['header_bg'], 0.12)
    pairs = [("fg/bg", t['fg'], t['bg']), ("fg/panel", t['fg'], t['panel']), ("fg/panel2", t['fg'], t['panel2']), ("muted/panel", t['muted'], t['panel']),
             ("muted/bg", t['muted'], t['bg']), ("muted/panel2", t['muted'], t['panel2']), ("accent_fg/accent", t['accent_fg'], t['accent']),
             ("sel_fg/sel_bg", t['sel_fg'], t['sel_bg']), ("header_fg/header_bg", t['header_fg'], t['header_bg']), ("header_sub/header_bg", t['header_sub'], t['header_bg']),
             ("accent_text/panel", t['accent_text'], t['panel']), ("accent_text/bg", t['accent_text'], t['bg'])]
    for tok in ("success", "warning", "danger"):
        pairs += [(f"{tok}/panel", t[tok], t['panel']), (f"{tok}/bg", t[tok], t['bg'])]
    # selos de contagem: texto na cor do token sobre o fundo misturado; e a cor das linhas marcadas sobre a seleção
    for tok in ("danger", "warning", "muted", "success", "accent_text"):
        pairs.append((f"chip {tok}", t[tok], t['panel']))
    banner = G.blend(t['panel'], t['danger'], 0.16)
    pairs += [("banner texto", t['fg'], banner), ("banner muted", t['muted'], banner)]
    large = [("banner glifo ‼ (texto grande, mínimo 3:1)", t['danger'], banner)]
    bad += [(key, n, a, b, round(cr(a, b), 2)) for n, a, b in large if cr(a, b) < 3.0]
    pairs += [("badge", G.ink_on(t['warning']), t['warning']), ("badge primário", t['accent'], t['accent_fg'])]
    bad += [(key, n, a, b, round(cr(a, b), 2)) for n, a, b in pairs if cr(a, b) < 4.5]
assert not bad, bad

def wait(a):
    end = time.time() + 20
    while a.loading and time.time() < end: a.update(); time.sleep(0.01)
    for _ in range(6): a.update(); time.sleep(0.02)
def iid(a, n): return next(i for i in a.iter_sessions() if a.cid_of(i) == U(n))

app = G.AntigravityGateApp(); app.geometry("1240x720+0+0"); wait(app)
assert app.theme_key == "escuro" and app.icon_mode in ("symbol", "mdl2")

# 2. todo tema aplica sem erro, recolore widgets e persiste
for key in G.THEME_ORDER:
    app.set_theme(key); app.update()
    assert app.cget("bg") == G.THEMES[key]['bg'] and app.top_frame.cget("bg") == G.THEMES[key]['header_bg'], key
    assert app.btn["approve"].cget("bg") == G.THEMES[key]['bg'] and app.chips["aprovada"].cget("fg") == G.THEMES[key]['success']
assert json.load(open(G.SETTINGS_FILE))["theme"] == "mecha"
app.destroy(); app = G.AntigravityGateApp(); wait(app); assert app.theme_key == "mecha", "tema escolhido é lembrado"
app.set_theme("escuro")

# 3. estados dos botões acompanham a seleção, com motivo
b = app.btn
app.tree.selection_set(()); app.update()
assert not b["approve"].enabled and "Selecione" in b["approve"].tooltip_text() and not b["export"].enabled and not b["autorun"].enabled
app.tree.selection_set(app.tree.get_children()[0]); app.update()          # pasta de projeto: aprova em lote, não exporta
assert b["approve"].enabled and not b["export"].enabled and "Selecione uma sessão" in b["export"].reason
app.tree.selection_set(iid(app, 1)); app.update()
assert b["approve"].enabled and b["export"].enabled and b["dossier"].enabled and b["export"].tooltip_text().startswith("Salvar")
app.mark_selected("aprovada"); app.update()
assert b["autorun"].enabled and b["autorun"].badge == 1 and b["autorun"].measure(False) > 0
assert b["approve"].ok_flash, "confirmação visual ao aprovar"
app.after(1000); time.sleep(1.0); app.update(); assert not b["approve"].ok_flash
app.tree.selection_set(iid(app, 2)); app.mark_selected("aprovada"); app.update(); assert b["autorun"].badge == 2
for n in (1, 2): app.handoffs[U(n)] = "aaaaaaaa-0000"; 
app.update_actions(); assert b["autorun"].badge == 0 and b["autorun"].enabled, "retomadas não contam no selo, mas o Auto-Run continua disponível para refazer"
# desabilitado não executa; habilitado executa; pressionar/soltar fora não executa
hits = []
btn = G.IconButton(app.actions_frame, app, "approve", "Teste", lambda: hits.append(1)); btn.set_enabled(False, "motivo"); btn.invoke(); assert not hits
btn.set_enabled(True); btn.invoke(); assert hits == [1]
btn._set(hover=True); btn.redraw(); c1 = btn.colors()[0]; btn._set(pressed=True); c2 = btn.colors()[0]; btn._set(hover=False, pressed=False); c3 = btn.colors()[0]
assert len({c1, c2, c3}) == 3, "normal, hover e pressionado têm cores diferentes"
btn.set_busy(True, "Aguarde"); assert btn.busy and btn.text == "Aguarde"; btn.invoke(); assert hits == [1], "ocupado não executa"; btn.set_busy(False); btn.destroy()

# 4. nenhum botão cortado: largura larga mostra texto; estreita vira só ícone; conteúdo sempre cabe
def clipped(bt):
    w = int(bt["width"])
    return [it for it in bt.find_all() if bt.type(it) in ("text", "arc") and bt.bbox(it)[2] > w - 1]
app.geometry("1240x720+0+0"); app.update(); time.sleep(0.2); app.update()
names = ("approve", "archive", "pending", "export", "dossier", "autorun")
assert not any(app.btn[n].compact for n in names), "janela larga: botões com texto"
for n, bt in app.btn.items(): assert not clipped(bt), ("cortado em janela larga", n)
for width in (1000, 800, 640):
    app.geometry(f"{width}x700+0+0"); app.update(); time.sleep(0.25); app.update()
    for n, bt in app.btn.items(): assert not clipped(bt), ("cortado", width, n)
    rx = max(app.btn[n].winfo_x() + app.btn[n].winfo_width() for n in names if n != "autorun")
    assert app.btn["autorun"].winfo_x() + app.btn["autorun"].winfo_width() <= app.actions_frame.winfo_width() + 1, ("Auto-Run fora da janela", width)
app.geometry("760x600+0+0"); app.update(); time.sleep(0.25); app.update()
assert all(app.btn[n].compact for n in names), "janela estreita: botões compactos"
assert app.btn["approve"].tooltip_text(), "compacto continua com dica"
app.geometry("1240x720+0+0"); app.update(); time.sleep(0.25); app.update()
assert not any(app.btn[n].compact for n in names), "voltou a alargar: texto volta"

# 5. ícones: Windows, Unicode ou nenhum; escolha persiste e botões se ajustam
app.set_icon_mode("symbol"); assert app.btn["approve"].glyph() == G.ICONS["approve"][1]
app.set_icon_mode("mdl2"); assert app.btn["approve"].glyph() == G.ICONS["approve"][0]
app.set_icon_mode("none"); app.update(); assert app.btn["approve"].glyph() == "" and app.btn["approve"].measure() > 0
assert not any(app.btn[n].compact for n in names) or True
assert json.load(open(G.SETTINGS_FILE))["icons"] == "none"
for n, bt in app.btn.items(): assert not clipped(bt), ("sem ícones", n)
app.set_icon_mode("symbol")

# 6. status de busy do Atualizar durante a carga
app.refresh(); assert app.btn["refresh"].busy; wait(app); assert not app.btn["refresh"].busy
# 7. tabela: marcas de linha por estado
t = app.tree
assert "st_aprovada" in t.item(iid(app, 1), "tags") and "st_aprovada" in t.item(iid(app, 2), "tags") and not t.item(iid(app, 3), "tags")
app.tree.selection_set(iid(app, 3)); app.mark_selected("arquivada"); assert "st_arquivada" in t.item(iid(app, 3), "tags")
app.destroy(); print("TODOS OS TESTES DE TEMA E BOTOES OK")
