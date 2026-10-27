import os, sys, sqlite3, tempfile, time, json
root = tempfile.mkdtemp(prefix="agylim_")
base = os.path.join(root, "gemini"); local = os.path.join(root, "local")
os.environ.update(HOME=os.path.join(root, "home"), ANTIGRAVITY_HOME=base, LOCALAPPDATA=local)
os.environ.pop("AGY_ROT_TOKENS", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G

# --- 1. leitura de números
P = G.parse_tokens
for text, want in [("120000", 120000), ("120.000", 120000), ("1.000.000", 1000000), ("120k", 120000), ("120 K", 120000), (" 80 k ", 80000),
                   ("1,5m", 1500000), ("1.5k", 1500), ("2M", 2000000), ("12_000", 12000), ("abc", None), ("", None), ("12.5", None), ("-5", None), ("1e5", None), (None, None)]:
    assert P(text) == want, (text, P(text), want)
# --- 2. validação
V = G.validate_limits
assert V("100k", "200k") == (100000, 200000, "")
assert "Use números" in V("abc", "200k")[2] and "Use números" in V("100k", "")[2]
assert "entre" in V("5k", "200k")[2] and "entre" in V("100k", "6m")[2]
assert "maior" in V("200k", "150k")[2] and "maior" in V("200k", "200k")[2]
assert V("10k", "5m") == (10000, 5000000, "")
# --- 3. níveis e fronteiras (padrão equilibrado 150k/250k)
assert G.CONTEXT_LIMITS == {"attention": 150000, "critical": 250000}
L = G.ctx_level
assert [L(x) for x in (0, 149999, 150000, 249999, 250000, 9999999)] == [0, 0, 1, 1, 2, 2]
assert L(120000, 100000, 150000) == 1 and L(120000, 200000, 300000) == 0, "faixas passadas por parâmetro não mexem nos globais"
assert G.CONTEXT_LIMITS["attention"] == 150000
# --- 4. rótulo
assert G.ctx_label(0) == "-" and "⚠" not in G.ctx_label(1000) and "‼" not in G.ctx_label(1000)
assert G.ctx_label(150000).endswith("⚠") and G.ctx_label(250000).endswith("‼") and G.ctx_label(250000).count("■") == 6
assert G.ctx_label(1000).count("■") == 1 and G.ctx_label(125000).count("■") == 3, "medidor é proporcional ao nível crítico"
# --- 5. preferências
os.environ.pop("AGY_ROT_TOKENS", None)
assert G.limits_from_settings({}) == ("equilibrado", 150000, 250000)
assert G.limits_from_settings({"context": {"preset": "conservador"}}) == ("conservador", 100000, 150000)
assert G.limits_from_settings({"context": {"preset": "amplo"}}) == ("amplo", 300000, 500000)
assert G.limits_from_settings({"context": {"preset": "personalizado", "attention": 120000, "critical": 200000}}) == ("personalizado", 120000, 200000)
assert G.limits_from_settings({"context": {"preset": "personalizado", "attention": 5, "critical": 4}})[0] == "equilibrado", "valores inválidos voltam ao padrão"
assert G.limits_from_settings({"context": "lixo"})[0] == "equilibrado" and G.limits_from_settings({"context": {"preset": "xyz"}})[0] == "equilibrado"
os.environ["AGY_ROT_TOKENS"] = "120k"; assert G.limits_from_settings({"context": {"preset": "amplo"}}) == ("personalizado", 120000, 180000), "variável antiga continua valendo"
os.environ["AGY_ROT_TOKENS"] = "lixo"; assert G.limits_from_settings({})[0] == "equilibrado"
os.environ.pop("AGY_ROT_TOKENS")
# --- 6. cabeçalho do dossiê
t = G.meta_table({'cid': 'x'}, {'models': [], 'started': None, 'ended': None, 'steps': 1, 'ctx': 260000})
assert "260000 tokens (crítico)" in t
assert "(atenção)" in G.meta_table({'cid': 'x'}, {'models': [], 'started': None, 'ended': None, 'steps': 1, 'ctx': 160000})
assert "tokens (" not in G.meta_table({'cid': 'x'}, {'models': [], 'started': None, 'ended': None, 'steps': 1, 'ctx': 1000})

# --- 7. tela
U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)
ant = os.path.join(base, "antigravity"); conv = os.path.join(ant, "conversations"); os.makedirs(conv); os.makedirs(os.path.join(base, "config", "projects"))
c = sqlite3.connect(os.path.join(ant, "conversation_summaries.db"))
c.execute("CREATE TABLE conversation_summaries(conversation_id TEXT, title TEXT, preview TEXT, step_count INT, last_modified_time TEXT, project_id TEXT, workspace_uris TEXT, agent_name TEXT, parent_conversation_id TEXT)")
CTX = {1: 90000, 2: 160000, 3: 260000, 4: 600000}
for i in CTX: c.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?,?,?)", (U(i), "", "sessao %d" % i, 5, "2026-10-26T1%d:00:00Z" % i, "", "", "", ""))
c.commit(); c.close()
def vi(n):
    o = bytearray()
    while True:
        b = n & 0x7f; n >>= 7
        if n: o.append(b | 0x80)
        else: o.append(b); return bytes(o)
fv = lambda f, v: vi(f << 3) + vi(v); fl = lambda f, b: vi(f << 3 | 2) + vi(len(b)) + b
for i, ctx in CTX.items():
    d = sqlite3.connect(os.path.join(conv, U(i) + ".db")); d.execute("CREATE TABLE steps(idx INTEGER PRIMARY KEY, step_type INT, status INT, step_payload BLOB, error_details BLOB)")
    d.execute("INSERT INTO steps VALUES(0,15,3,?,NULL)", (fv(1, 15) + fl(5, fl(9, fv(2, ctx))),)); d.commit(); d.close()
from tkinter import messagebox
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, **k: None)
messagebox.askyesno = lambda *a, **k: True
G.setup_logging()
def wait(a):
    end = time.time() + 20
    while a.loading and time.time() < end: a.update(); time.sleep(0.01)
    for _ in range(6): a.update(); time.sleep(0.02)
def iid(a, n): return next(i for i in a.iter_sessions() if a.cid_of(i) == U(n))
def shown(a): return {a.cid_of(i) for i in a.iter_sessions()}

app = G.AntigravityGateApp(); app.geometry("1240x720+0+0"); wait(app)
assert app.limit_preset == "equilibrado" and "Equilibrado" in app.btn["limits"].tooltip_text() and "150k" in app.btn["limits"].tooltip_text() and "250k" in app.btn["limits"].tooltip_text()
tags = lambda n: app.tree.item(iid(app, n), "tags")
assert not tags(1) and tags(2) == ("rot",) and tags(3) == ("crit",) and tags(4) == ("crit",)
assert app.chips["rot"].cget("text") == "⚠ 1 em atenção" and app.chips["crit"].cget("text") == "‼ 2 críticas"
assert app.banner.winfo_manager() == "pack" and "2 sessão(ões) acima do nível crítico (250k tokens)" in app.banner_msg.cget("text")
# faixa crítica em destaque (1.0.2): vermelho forte do tema, texto claro, título com o nível, botão do nível
assert app.banner_level == 2 and app.banner_msg.cget("text").startswith("CRÍTICO · ") and app.banner.cget("bg") == G.banner_colors(app.t, 2)['bg']
assert app.banner_msg.cget("fg") == "#ffffff" and app.btn["banner_view"].text == "Ver críticas" and app.banner_detail.cget("text")
vals = lambda n: app.tree.item(iid(app, n), "values")[2]
assert vals(2).endswith("⚠") and vals(3).endswith("‼") and vals(1) == G.ctx_label(90000)
# dica do contexto como janela de alerta (1.0.2): crítico e atenção com as cores da faixa, ícone e título; normal segue comum
def walk(w): return [w] + [d for c in w.winfo_children() for d in walk(c)]
def ctx_tip(n):
    app.cell_tips.hide(); key = (iid(app, n), "col_ctx")
    app.cell_tips.key, app.cell_tips.text = key, app.tree_cell_tip(*key)
    app.cell_tips.show_now(); app.update()
    ws = walk(app.cell_tips.tip)[1:]
    return ws[0].cget("bg"), [w.cget("text") for w in ws if isinstance(w, G.tk.Label)]
bg, texts = ctx_tip(3); assert bg == G.banner_colors(app.t, 2)['bg'] and "CRÍTICO" in texts and any("260.000 tokens" in x for x in texts), (bg, texts)
bg, texts = ctx_tip(2); assert bg == G.banner_colors(app.t, 1)['bg'] and "ATENÇÃO" in texts, (bg, texts)
bg, texts = ctx_tip(1); assert bg == app.t['panel2'] and not {"CRÍTICO", "ATENÇÃO"} & set(texts), (bg, texts)
app.cell_tips.hide()
assert app.cell_level(app.row_by_cid[U(3)], "col_ctx") == 2 and app.cell_level(app.row_by_cid[U(3)], "col_fail") == 0
# arquivar uma crítica: sai do aviso, fica esmaecida, o selo continua contando o nível
app.tree.selection_set(iid(app, 4)); app.mark_selected("arquivada"); app.update()
assert tags(4) == ("st_arquivada",) and "1 sessão(ões) acima" in app.banner_msg.cget("text")
# dispensar esconde; mudar o limite traz de volta
app.dismiss_banner(); assert app.banner.winfo_manager() == ""
app.set_limits("conservador", 100000, 150000); app.update()
assert app.banner.winfo_manager() == "pack" and "2 sessão(ões) acima do nível crítico (150k tokens)" in app.banner_msg.cget("text"), app.banner_msg.cget("text")
assert tags(2) == ("crit",) and not tags(1) and G.CONTEXT_LIMITS == {"attention": 100000, "critical": 150000}
assert "Conservador" in app.btn["limits"].tooltip_text()
st = json.load(open(G.SETTINGS_FILE)); assert st["context"] == {"preset": "conservador", "attention": 100000, "critical": 150000}
# ver críticas: lista plana só com as críticas ativas; o aviso some durante o filtro; limpar volta
app.show_critical(); app.update()
assert shown(app) == {U(2), U(3)} and app.banner.winfo_manager() == "" and "2 sessão(ões) críticas" in app.status.cget("text")
app.clear_search(); app.update(); assert shown(app) == {U(1), U(2), U(3), U(4)} and app.banner.winfo_manager() == "pack"
# faixa ampla: ninguém crítico, aviso some, tags mudam
app.set_limits("amplo", 300000, 500000); app.update()
assert app.banner.winfo_manager() == "" and not tags(3) and not tags(2) and app.chips["crit"].cget("text") == "‼ 1 críticas"
# faixa de atenção (1.0.2): só quando não há críticas; âmbar suave, botão próprio; dispensar vale para o nível
app.set_limits(G.CONTEXT_CUSTOM, 150000, 700000); app.update()   # 2 e 3 em atenção; a 4 também, mas está arquivada
assert app.banner.winfo_manager() == "pack" and app.banner_level == 1, app.banner_level
assert app.banner_msg.cget("text") == "ATENÇÃO · 2 sessão(ões) acima do nível de atenção (150k tokens)", app.banner_msg.cget("text")
assert app.banner.cget("bg") == G.banner_colors(app.t, 1)['bg'] and app.btn["banner_view"].text == "Ver em atenção"
app.btn["banner_view"].invoke(); app.update()
assert shown(app) == {U(2), U(3)} and "2 sessão(ões) em atenção" in app.status.cget("text") and app.banner.winfo_manager() == ""
app.clear_search(); app.update(); assert app.banner.winfo_manager() == "pack"
app.dismiss_banner(); assert app.banner.winfo_manager() == ""
app.set_theme("claro"); app.update(); assert app.banner.winfo_manager() == "", "dispensada continua dispensada ao trocar o tema"
app.set_theme("escuro"); app.set_limits("amplo", 300000, 500000); app.update()

# --- 8. diálogo
dlg = G.LimitDialog(app); dlg.update()
assert dlg.values()[:3] == ("amplo", 300000, 500000) and "0 em atenção · 1 críticas" in dlg.preview.cget("text")
dlg.var.set("conservador"); dlg.refresh(); assert dlg.values()[:3] == ("conservador", 100000, 150000) and "0 em atenção · 3 críticas" in dlg.preview.cget("text")
dlg.att_var.set("abc"); dlg.update()
assert dlg.var.get() == "personalizado", "digitar nos campos seleciona Personalizado"
assert "Use números" in dlg.error.cget("text") and not dlg.ok_btn.enabled and dlg.preview.cget("text") == ""
dlg.att_var.set("200k"); dlg.crit_var.set("100k"); dlg.update(); assert "maior" in dlg.error.cget("text") and not dlg.ok_btn.enabled
dlg.ok_btn.invoke(); assert dlg.winfo_exists() and app.limit_preset == "amplo", "inválido não aplica"
dlg.att_var.set("120k"); dlg.crit_var.set("200.000"); dlg.update()
assert dlg.error.cget("text") == "" and dlg.ok_btn.enabled and "em atenção" in dlg.preview.cget("text")
dlg.apply(); app.update()
assert app.limit_preset == "personalizado" and G.CONTEXT_LIMITS == {"attention": 120000, "critical": 200000} and app.limits_custom == (120000, 200000)
assert "Personalizado" in app.btn["limits"].tooltip_text() and "200k" in app.btn["limits"].tooltip_text()
try: gone = not dlg.winfo_exists()
except Exception: gone = True
assert gone, "diálogo fecha ao aplicar"
# --- 9. persistência entre execuções
app.destroy()
G.set_context_limits(150000, 250000)
app = G.AntigravityGateApp(); wait(app)
assert app.limit_preset == "personalizado" and G.CONTEXT_LIMITS == {"attention": 120000, "critical": 200000} and app.limits_custom == (120000, 200000)
dlg = G.LimitDialog(app); dlg.update(); assert dlg.var.get() == "personalizado" and dlg.att_var.get() == "120000"; dlg.destroy()
for n, b in app.btn.items():
    assert int(b["width"]) >= 1
app.destroy(); print("TODOS OS TESTES DE LIMITES OK")
