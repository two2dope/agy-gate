"""1.5.0: recomendações da auditoria (R2, R8, R12, R13, R15) e datas sem horário (item 7). R3 e R4 estão em test_m4; R11 em test_m3b."""
import os, sys, sqlite3, tempfile, time, subprocess, json
root = tempfile.mkdtemp(prefix="agypol_")
base = os.path.join(root, "gemini")
os.environ.update(HOME=os.path.join(root, "home"), ANTIGRAVITY_HOME=base, LOCALAPPDATA=os.path.join(root, "local"))
U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)
ant = os.path.join(base, "antigravity"); conv = os.path.join(ant, "conversations"); os.makedirs(conv); os.makedirs(os.path.join(base, "config", "projects"))
c = sqlite3.connect(os.path.join(ant, "conversation_summaries.db"))
c.execute("CREATE TABLE conversation_summaries(conversation_id TEXT, title TEXT, preview TEXT, step_count INT, last_modified_time TEXT, project_id TEXT, workspace_uris TEXT, agent_name TEXT, parent_conversation_id TEXT)")
c.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?,?,?)", (U(1), "Retomada do SMT1 Watchdog... parte dois", "p", 40, "0001-01-01T00:00:00Z", "", "", "", ""))
c.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?,?,?)", (U(2), "Outra sessão longa", "p", 40, "2026-10-26T10:00:00Z", "", "", "", ""))
c.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?,?,?)", (U(3), "Sem arquivo e sem horário", "p", 0, "0001-01-01T00:00:00Z", "", "", "", ""))
c.commit(); c.close()
for i in (1, 2):
    d = sqlite3.connect(os.path.join(conv, U(i) + ".db")); d.execute("CREATE TABLE steps(idx INTEGER PRIMARY KEY, step_type INT, status INT, step_payload BLOB, error_details BLOB)"); d.commit(); d.close()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G
from tkinter import messagebox
shown = []
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, _n=n, **k: shown.append((_n, a)))
G.setup_logging()

# ---- item 7: data 0001-01-01 vira vazio (e "-" na tabela)
assert G.fmt_time("0001-01-01T00:00:00Z") == "" and G.fmt_time("2026-10-26 10:00:00") == "2026-10-26 10:00:00"

# ---- R2: maior prefixo vence, com fronteira de pasta
m = {"file:///c:/proj": "Curto", "file:///c:/proj/app": "Longo", "file:///c:/projetos": "Outro"}
assert G.project_by_uri('["file:///c:/proj/app/src"]', m) == "Longo"
assert G.project_by_uri("file:///c:/proj/x", m) == "Curto"
assert G.project_by_uri("file:///c:/projetos/x", m) == "Outro", "c:/proj não casa c:/projetos"
assert G.project_by_uri("file:///c:/projex", m) == "" and G.project_by_uri("", m) == ""
assert G.project_by_uri("file:///c:/proj/", m) == "Curto", "barra final"

# ---- R8: palavras para a busca do Antigravity
assert G.search_words("Retomada do SMT1 Watchdog... parte dois") == "Retomada do SMT1 Watchdog"
assert G.search_words("Curto") == "Curto" and G.search_words("") == ""

# ---- R12: encerra a árvore de processos
child = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); time.sleep(60)"
p = subprocess.Popen([sys.executable, "-c", child], creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
time.sleep(1.0)
G.kill_tree(p); p.wait(timeout=10)
assert p.poll() is not None
G.kill_tree(p); G.kill_tree(None)  # já encerrado ou ausente: nada a fazer

# ---- R13: --help
out = subprocess.run([sys.executable, "-X", "utf8", "-I", G.__file__, "--help"], capture_output=True, text=True, encoding="utf-8", timeout=30).stdout
assert out.startswith(f"AntigravityGate {G.__version__}") and "--selftest" in out and "ANTIGRAVITY_HOME" in out and "AGY_EXE" in out, out

# ---- R15: notas por sessão
st = G.StateStore(G.STATE_DB)
st.set_note(U(2), "  decidi usar o caminho A; falta o teste no Windows  ")
assert st.notes() == {U(2): "decidi usar o caminho A; falta o teste no Windows"}
st.set_note(U(2), "   "); assert st.notes() == {}, "nota vazia apaga"
st.set_note(U(2), "parei no M2; chave AIza" + "B" * 35)

def wait(a):
    end = time.time() + 20
    while a.loading and time.time() < end: a.update(); time.sleep(0.01)
    for _ in range(6): a.update(); time.sleep(0.02)
app = G.AntigravityGateApp(); wait(app)
leaf = {app.cid_of(i): i for i in app.iter_sessions()}
assert app.tree.item(leaf[U(3)], "values")[0] == "-", app.tree.item(leaf[U(3)], "values")   # sessão sem arquivo nem horário
assert "✎ nota" in app.tree.item(leaf[U(2)], "text") and "✎" not in app.tree.item(leaf[U(1)], "text")
labels = lambda m: [m.entrycget(i, "label") for i in range(m.index("end") + 1) if m.type(i) == "command"]
mm = labels(app.build_menu(leaf[U(1)]))
assert {"Copiar título para buscar", "Nota da sessão…", "Exportar diálogo sem máscara…"} <= set(mm), mm
app.copy_title(leaf[U(1)]); assert app.clipboard_get() == "Retomada do SMT1 Watchdog"
# a nota entra no dossiê, mascarada
out_d = os.path.join(root, "d.md"); G.export_session('dossier', app.meta_for(U(2))['fpath'], app.meta_for(U(2)), out_d)
doss = open(out_d, encoding="utf-8").read()
assert "## Notas do usuário" in doss and "parei no M2" in doss and "AIza" not in doss and "[REDACTED]" in doss
# janela da nota: editar e apagar
dlg = app.edit_note(U(1)); app.update()
dlg.text.insert("1.0", "nota nova"); dlg.save(); app.update()
assert app.notes.get(U(1)) == "nota nova" and "✎ nota" in app.tree.item(next(i for i in app.iter_sessions() if app.cid_of(i) == U(1)), "text")
dlg = app.edit_note(U(1)); app.update()
assert dlg.text.get("1.0", "end").strip() == "nota nova"
dlg.text.delete("1.0", "end"); dlg.save(); app.update()
assert U(1) not in app.notes and app.toast_log[-1][1] == "Nota apagada."
assert not shown, shown
app.destroy()
print("TODOS OS TESTES POLISH OK")
