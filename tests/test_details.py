import os, sys, sqlite3, tempfile, time, json
from datetime import datetime, timedelta
root = tempfile.mkdtemp(prefix="agydet_")
base = os.path.join(root, "gemini")
os.environ.update(HOME=os.path.join(root, "home"), ANTIGRAVITY_HOME=base, LOCALAPPDATA=os.path.join(root, "local"), TZ="America/Sao_Paulo")
time.tzset()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G

# 1. datas: o banco guarda UTC; a lista mostra o horário local
assert G.fmt_time("2026-10-26T15:00:00Z") == "2026-10-26 12:00:00"
assert G.fmt_time("2026-10-26 15:05:01.123456789+00:00") == "2026-10-26 12:05:01"
assert G.fmt_time("2026-10-26T12:00:00-03:00") == "2026-10-26 12:00:00" and G.fmt_time("2026-10-26T12:00:00+02:00") == "2026-10-26 07:00:00"
assert G.fmt_time("2026-10-26 09:00:00") == "2026-10-26 09:00:00", "sem fuso: não converte"
assert G.fmt_time(1792916056) == datetime.fromtimestamp(1792916056).strftime("%Y-%m-%d %H:%M:%S") and G.fmt_time(None) == "" and G.fmt_time("lixo") == "lixo"
# 2. tempo relativo e corte de caminhos
now = datetime(2026, 10, 26, 12, 0, 0); R = lambda d: G.rel_time(d, now)
assert [R("2026-10-26 11:59:30"), R("2026-10-26 11:30:00"), R("2026-10-26 09:00:00"), R("2026-10-25 11:00:00"), R("2026-10-20 12:00:00"), R("2026-08-26 12:00:00"),
        R("2025-10-26 12:00:00"), R("2024-01-01 00:00:00"), R("lixo"), R("2026-10-27 12:00:00")] == ["agora", "há 30 min", "há 3 h", "há 1 dia", "há 6 dias", "há 2 meses", "há 1 ano", "há 2 anos", "", "agora"]
long = "C:\\Users\\Thomáz\\Projetos\\01_dev-systems\\01_skills-dev\\claudin-mod\\subpasta\\mais"
e = G.ellipsize(long, 40); assert len(e) <= 40 and "…" in e and e.startswith("C:\\Users") and e.endswith("mais") and G.ellipsize("curto", 40) == "curto"

U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)
ant = os.path.join(base, "antigravity"); conv = os.path.join(ant, "conversations"); os.makedirs(conv); os.makedirs(os.path.join(base, "config", "projects"))
ws_ok = os.path.join(root, "meu projeto"); os.makedirs(ws_ok)
import urllib.parse
uri = lambda p: json.dumps(["file://" + urllib.parse.quote(p)])
c = sqlite3.connect(os.path.join(ant, "conversation_summaries.db"))
c.execute("""CREATE TABLE conversation_summaries(conversation_id TEXT, title TEXT, preview TEXT, step_count INT, last_modified_time TEXT, project_id TEXT,
             workspace_uris TEXT, agent_name TEXT, parent_conversation_id TEXT, status TEXT, killed INT, source TEXT)""")
recent = (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
rows = [(1, "sessão com workspace ok e falhas", 42, recent, uri(ws_ok), "DeepCoder", "", "CASCADE_RUN_STATUS_IDLE", 0, "CORTEX_TRAJECTORY_SOURCE_CLI"),
        (2, "workspace que não existe mais", 7, "2026-09-01T10:00:00Z", uri("/nao/existe/mais/aqui"), "", "", "CASCADE_RUN_STATUS_RUNNING", 0, ""),
        (3, "sem workspace e encerrada", 3, "2026-10-20T10:00:00Z", "", "browser", "", "CASCADE_RUN_STATUS_IDLE", 1, "")]
for i, prev, steps, dt, ws, ag, par, status, killed, src in rows:
    c.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (U(i), "", prev, steps, dt, "", ws, ag, par, status, killed, src))
c.commit(); c.close()
def vi(n):
    o = bytearray()
    while True:
        b = n & 0x7f; n >>= 7
        if n: o.append(b | 0x80)
        else: o.append(b); return bytes(o)
fv = lambda f, v: vi(f << 3) + vi(v); fl = lambda f, b: vi(f << 3 | 2) + vi(len(b)) + b
CTX = {1: 160000, 2: 300000, 3: 0}
for i in (1, 2, 3):
    d = sqlite3.connect(os.path.join(conv, U(i) + ".db")); d.execute("CREATE TABLE steps(idx INTEGER PRIMARY KEY, step_type INT, status INT, step_payload BLOB, error_details BLOB)")
    if CTX[i]: d.execute("INSERT INTO steps VALUES(0,15,3,?,NULL)", (fv(1, 15) + fl(5, fl(9, fv(2, CTX[i]))),))
    if i == 1:
        for k in range(1, 4): d.execute("INSERT INTO steps VALUES(?,132,?,NULL,NULL)", (k, 7 if k < 3 else 3))
    d.commit(); d.close()
from tkinter import messagebox
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, **k: None)
messagebox.askyesno = lambda *a, **k: True
G.setup_logging()
def wait(a):
    end = time.time() + 20
    while a.loading and time.time() < end: a.update(); time.sleep(0.01)
    for _ in range(8): a.update(); time.sleep(0.02)
app = G.AntigravityGateApp(); app.geometry("1240x760+0+0"); wait(app)
iid = lambda n: next(i for i in app.iter_sessions() if app.cid_of(i) == U(n))
F = lambda k: app.fact_vals[k].cget("text")
for p in app.tree.get_children(): app.tree.item(p, open=True)

# 3. sem seleção
app.tree.selection_set(()); app.update()
assert app.d_title.cget("text") == "Nenhuma sessão selecionada" and "Selecione uma sessão" in app.d_note.cget("text") and app.gauge.winfo_manager() == "" and app.d_facts.winfo_manager() == ""
assert not app.btn["d_copy"].enabled and not app.btn["d_export"].enabled
# 4. sessão com workspace válido, falhas, origem CLI e contexto em atenção
app.tree.selection_set(iid(1)); app.update()
assert app.d_title.cget("text") == "sessão com workspace ok e falhas" and "DeepCoder" in app.d_sub.cget("text") and "CLI" in app.d_sub.cget("text")
assert F("uuid") == U(1) and F("state") == "Pendente" and F("steps") == "42" and F("origin") == "CLI" and F("agent") == "DeepCoder"
assert F("ws").startswith("✔ ") and "meu projeto" in F("ws") and app.fact_vals["ws"].cget("fg") == app.t["fg"], F("ws")
assert F("fails") == "⚠ 2 ferramenta(s)" and app.fact_vals["fails"].cget("fg") == app.t["warning"]
assert "há 3 h" in F("date") and F("handoff") == "-"
assert app.gauge.winfo_manager() == "pack" and app.d_facts.winfo_manager() == "pack" and app.d_note.winfo_manager() == ""
texts = [app.gauge.itemcget(i, "text") for i in app.gauge.find_all() if app.gauge.type(i) == "text"]
assert any("160.000 tokens · atenção" in x for x in texts) and any("atenção 150k" in x for x in texts) and any("crítico 250k" in x for x in texts), texts
fills = {app.gauge.itemcget(i, "fill") for i in app.gauge.find_all() if app.gauge.type(i) == "polygon"}
assert app.t["warning"] in fills, "barra no nível de atenção usa a cor de atenção"
assert app.btn["d_copy"].enabled and app.btn["d_export"].enabled and app.btn["d_folder"].enabled
# 5. workspace inexistente, sessão em execução, nível crítico
app.tree.selection_set(iid(2)); app.update()
assert F("ws").startswith("⚠ ") and app.fact_vals["ws"].cget("fg") == app.t["warning"] and F("state") == "Pendente · em execução" and F("origin") == "-"
texts = [app.gauge.itemcget(i, "text") for i in app.gauge.find_all() if app.gauge.type(i) == "text"]
assert any("300.000 tokens · crítico" in x for x in texts)
assert app.t["danger"] in {app.gauge.itemcget(i, "fill") for i in app.gauge.find_all() if app.gauge.type(i) == "polygon"}
# 6. sem contexto, sem workspace, encerrada à força
app.tree.selection_set(iid(3)); app.update()
assert F("ws") == "não informado" and "encerrada à força" in F("state") and F("fails") == "nenhuma"
assert any("Sem dado de contexto" in app.gauge.itemcget(i, "text") for i in app.gauge.find_all() if app.gauge.type(i) == "text")
# 7. várias sessões e pasta de projeto
app.tree.selection_set([iid(1), iid(2)]); app.update()
assert app.d_title.cget("text") == "2 sessões selecionadas" and "falhas de ferramenta: 2" in app.d_note.cget("text") and "1 críticas" in app.d_note.cget("text") and app.gauge.winfo_manager() == ""
app.tree.selection_set(app.tree.get_children()[0]); app.update()
assert "3 sessões" in app.d_sub.cget("text") and "pendentes" in app.d_note.cget("text") and not app.btn["d_export"].enabled
# 8. estado e retomada refletem no painel; mudar de tema redesenha
app.tree.selection_set(iid(1)); app.mark_selected("aprovada"); app.handoffs[U(1)] = "bbbbbbbb-1111"; app.refresh_labels(); app.update_details()
assert F("state") == "Aprovada" and F("handoff") == "↪ bbbbbbbb"
old = app.gauge.itemcget(app.gauge.find_all()[0], "fill"); app.set_theme("cyber"); app.update()
assert app.gauge.itemcget(app.gauge.find_all()[0], "fill") != old
# 9. botões do painel
app.copy_selected_uuid(); assert app.clipboard_get() == U(1)
# 10. recolher e expandir, com preferência salva
assert app.details_body.winfo_manager() == "pack" and "▾" in app.details_toggle.cget("text")
app.toggle_details(); app.update(); assert app.details_body.winfo_manager() == "" and "▸" in app.details_toggle.cget("text") and json.load(open(G.SETTINGS_FILE))["details"] is False
app.destroy(); app = G.AntigravityGateApp(); wait(app); assert app.details_body.winfo_manager() == "", "recolhido continua recolhido"
app.toggle_details(); app.update(); assert app.details_body.winfo_manager() == "pack"
app.destroy(); print("TODOS OS TESTES DE DETALHES OK")
