import os, sys, sqlite3, tempfile, time, json
root = tempfile.mkdtemp(prefix="agyreceipt_")
base = os.path.join(root, "gemini")
os.environ.update(HOME=os.path.join(root, "home"), ANTIGRAVITY_HOME=base, LOCALAPPDATA=os.path.join(root, "local"))
U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)
ant = os.path.join(base, "antigravity"); conv = os.path.join(ant, "conversations"); os.makedirs(conv); os.makedirs(os.path.join(base, "config", "projects"))
c = sqlite3.connect(os.path.join(ant, "conversation_summaries.db"))
c.execute("CREATE TABLE conversation_summaries(conversation_id TEXT, title TEXT, preview TEXT, step_count INT, last_modified_time TEXT, project_id TEXT, workspace_uris TEXT, agent_name TEXT, parent_conversation_id TEXT)")
for i in (1, 2, 3): c.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?,?,?)", (U(i), "", "sessao %d" % i, i, "2026-10-26T1%d:00:00Z" % i, "", "", "", ""))
c.commit(); c.close()
for i in (1, 2, 3):
    d = sqlite3.connect(os.path.join(conv, U(i) + ".db")); d.execute("CREATE TABLE steps(idx INTEGER PRIMARY KEY, step_type INT, status INT, step_payload BLOB, error_details BLOB)"); d.commit(); d.close()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G
from tkinter import messagebox, filedialog
shown = []
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, **k: shown.append((n, a)))
G.setup_logging()

# 1. migração: banco antigo (sem as colunas do recibo) ganha as colunas e continua legível
old = os.path.join(root, "antigo.db"); c = sqlite3.connect(old)
c.execute("CREATE TABLE handoffs(id INTEGER PRIMARY KEY AUTOINCREMENT, src_cid TEXT NOT NULL, new_cid TEXT, dossier_path TEXT, status TEXT NOT NULL, detail TEXT, at TEXT NOT NULL)")
c.execute("INSERT INTO handoffs(src_cid, new_cid, dossier_path, status, detail, at) VALUES('s1','n1','/x/d.md','ok','resposta curta','2026-10-26 22:55:36')"); c.commit(); c.close()
st = G.StateStore(old); rec = st.handoff_record("s1")
assert rec["model"] is None and rec["response"] is None and rec["detail"] == "resposta curta" and st.handoffs_ok() == {"s1": "n1"}
fields, response, note = G.receipt_fields(rec)
assert dict(fields)["Modelo"].startswith("não registrado") and dict(fields)["Duração"].startswith("não registrado") and response == "resposta curta" and "300 caracteres" in note
st.add_handoff("s2", "n2", "/x/e.md", "ok", "r", model="", cwd="/p", project="Alpha (--project)", duration=12.34, turns=3, usage={"input_tokens": 1500, "output_tokens": 20, "total_tokens": 1520}, response="resposta completa\n" * 40)
r2 = st.handoff_record("s2"); f2 = dict(G.receipt_fields(r2)[0])
assert f2["Modelo"] == "padrão do agy" and f2["Pasta de trabalho"] == "/p" and f2["Projeto na retomada"] == "Alpha (--project)" and f2["Duração"] == "12,3 s" and f2["Turnos"] == "3"
assert f2["Tokens"] == "entrada 1.500, saída 20, total 1.520" and G.receipt_fields(r2)[2] == "", f2
assert st.handoff_record("nao-existe") is None
md = G.receipt_markdown(r2); assert md.startswith("# Recibo de retomada") and "- **Sessão nova:** n2" in md and "## Resposta do agy" in md and md.count("resposta completa") == 40
secret = "AIza" + "A" * 35
assert secret not in G.receipt_markdown(dict(r2, response=f"chave {secret} fim")), "a resposta passa pela máscara de segredos"

def wait(a):
    end = time.time() + 20
    while a.loading and time.time() < end: a.update(); time.sleep(0.01)
    for _ in range(6): a.update(); time.sleep(0.02)
def iid(a, n): return next(i for i in a.iter_sessions() if a.cid_of(i) == U(n))

# 2. no app: sem retomada avisa; com retomada abre o recibo e o clique no campo da retomada também
app = G.AntigravityGateApp(); app.geometry("1240x760+0+0"); wait(app)
app.tree.selection_set(iid(app, 1)); app.update(); app.update_details()
assert app.fact_vals["handoff"].cget("text") == "-" and app.show_receipt() is None and shown and "ainda não foi retomada" in shown[-1][1][1]
app.state.add_handoff(U(1), U(9), os.path.join(root, "dossie.md"), "ok", "resp", model="Gemini 3.8 Flash (Medium)", cwd=root, project="CLI Project (sem --project)",
                      duration=7.5, turns=2, usage={"total_tokens": 900}, response="Entendi o objetivo.\nFalta testar.")
open(os.path.join(root, "dossie.md"), "w").write("x")
app.handoffs = app.state.handoffs_ok(); app.update_details(); app.update()
assert app.fact_vals["handoff"].cget("text").endswith("ver recibo") and app.fact_vals["handoff"].cget("fg") == app.t["accent_text"]
m = app.build_menu(iid(app, 1)); labels = [m.entrycget(i, "label") for i in range(m.index("end") + 1) if m.type(i) == "command"]
m2 = app.build_menu(iid(app, 2)); labels2 = [m2.entrycget(i, "label") for i in range(m2.index("end") + 1) if m2.type(i) == "command"]
assert "Ver recibo da retomada" in labels and "Ver recibo da retomada" not in labels2
dlg = app.fact_vals["handoff"].event_generate("<Button-1>") or app.show_receipt(); app.update()
assert isinstance(dlg, G.ReceiptDialog) and dlg.winfo_exists() and str(dlg.transient()) == str(app)
body = dlg.text.get("1.0", "end"); assert "Gemini 3.8 Flash (Medium)" in body and U(9) in body and "Entendi o objetivo." in body and "7,5 s" in body and "(arquivo não encontrado)" not in body

# 3. copiar, salvar e abrir a pasta
dlg.copy(); app.update(); assert app.clipboard_get() == dlg.md
out = os.path.join(root, "recibo.md"); filedialog.asksaveasfilename = lambda **k: out
dlg.save(); assert open(out, encoding="utf-8").read() == dlg.md
filedialog.asksaveasfilename = lambda **k: ""; os.remove(out); dlg.save(); assert not os.path.exists(out), "cancelar não grava"
opened = []; app.open_path = lambda p: opened.append(p); dlg.open_dossier(); assert opened == [root]
dlg.destroy(); app.update()
# o texto da janela é só leitura
dlg = app.show_receipt(); before = dlg.text.get("1.0", "end"); dlg.text.focus_force(); dlg.text.event_generate("<Key-x>"); dlg.update(); assert dlg.text.get("1.0", "end") == before
dlg.destroy(); app.destroy(); print("TODOS OS TESTES DO RECIBO OK")
