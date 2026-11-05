"""1.4: diagnóstico do ecossistema (só leitura) e C2 (junções não viram fonte de backup)."""
import os, sys, sqlite3, tempfile, time, json, shutil
root = tempfile.mkdtemp(prefix="agydoc_")
base = os.path.join(root, "gemini")
os.environ.update(HOME=os.path.join(root, "home"), ANTIGRAVITY_HOME=base, LOCALAPPDATA=os.path.join(root, "local"))
U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)
ant = os.path.join(base, "antigravity"); conv = os.path.join(ant, "conversations"); brain = os.path.join(ant, "brain")
projects = os.path.join(base, "config", "projects")
for d in (conv, brain, projects): os.makedirs(d)
summ = os.path.join(ant, "conversation_summaries.db")

def write_summaries(rows, with_source=True):
    if os.path.exists(summ): os.remove(summ)
    c = sqlite3.connect(summ)
    c.execute("CREATE TABLE conversation_summaries(conversation_id TEXT, title TEXT, preview TEXT, step_count INT, last_modified_time TEXT, "
              "project_id TEXT, workspace_uris TEXT, agent_name TEXT, parent_conversation_id TEXT" + (", source TEXT" if with_source else "") + ")")
    for cid, pid, src in rows:
        vals = (cid, "t", "p", 5, "2026-10-26T10:00:00Z", pid, "", "", "") + ((src,) if with_source else ())
        c.execute(f"INSERT INTO conversation_summaries VALUES({','.join('?' * len(vals))})", vals)
    c.commit(); c.close()

def manifest(name, pid, ids):
    with open(os.path.join(projects, name + ".json"), "w", encoding="utf-8") as fh:
        json.dump({"id": pid, "name": name, "projectConversations": {"conversations": [{"conversationId": i} for i in ids]}}, fh)

for i in (1, 2, 3, 4):
    d = sqlite3.connect(os.path.join(conv, U(i) + ".db")); d.execute("CREATE TABLE steps(idx INTEGER PRIMARY KEY, step_type INT, status INT, step_payload BLOB, error_details BLOB)"); d.commit(); d.close()
CLI = "CORTEX_TRAJECTORY_SOURCE_CLI"
write_summaries([(U(1), "pA", CLI), (U(2), "pA", ""), (U(3), "pB", "CORTEX_TRAJECTORY_SOURCE_JETBOX"), (U(4), "", "CORTEX_TRAJECTORY_SOURCE_CASCADE_CLIENT")])
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G
from tkinter import messagebox, filedialog
shown = []
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, _n=n, **k: shown.append((_n, a)))
G.setup_logging()

def link(target, at):
    """Junção no Windows (mklink /J não pede privilégio), link simbólico no resto."""
    if os.name == "nt":
        import subprocess
        subprocess.run(["cmd", "/c", "mklink", "/J", at, target], check=True, capture_output=True)
    else:
        os.symlink(target, at)

# ---- junções
cli = os.path.join(base, "antigravity-cli")
c = G.check_junctions(); assert c['level'] is None and "não foi configurado" in c['summary'], c
os.makedirs(os.path.join(cli, "conversations"))
for i in (1, 2): open(os.path.join(cli, "conversations", U(i) + ".db"), "w").write("")
c = G.check_junctions()
assert c['level'] == 2 and "2 pasta(s)" in c['summary'], c
assert any("pasta separada, com 2 sessão(ões)" in x for x in c['lines']) and any("brain: não existe" in x for x in c['lines']), c['lines']
assert c['action'].count("mklink /J") == 2 and c['action'].count("\nren ") == 1, c['action']   # só a pasta que existe é renomeada
shutil.rmtree(os.path.join(cli, "conversations"))
link(conv, os.path.join(cli, "conversations")); link(brain, os.path.join(cli, "brain"))
c = G.check_junctions(); assert c['level'] == 0 and all(x.startswith("✔") for x in c['lines']) and not c['action'], c

# ---- C2: a junção não vira fonte "Backup/outros"; um backup de verdade continua
bkp = os.path.join(base, "backups", "2026-10-28_bkp"); os.makedirs(bkp); shutil.copy(os.path.join(conv, U(1) + ".db"), bkp)
labels = [s[0] for s in G.discover_sources()]
assert labels[0] == G.ACTIVE_LABEL and "Backup/outros: backups/2026-10-28_bkp" in labels, labels
assert not any("antigravity-cli" in x for x in labels), labels

# ---- origem escondida na barra do IDE
c = G.check_cli_source()
assert c['level'] == 1 and c['summary'].startswith("2 de 4 sessões"), c   # CLI e CASCADE_CLIENT ficam fora; '' e JETBOX entram
assert "regrava a origem" in c['action'] and f"{CLI}: 1" in c['lines']
write_summaries([(U(1), "pA", ""), (U(2), "pA", "CORTEX_TRAJECTORY_SOURCE_UNSPECIFIED")])
assert G.check_cli_source()['level'] == 0
write_summaries([(U(1), "pA", "")], with_source=False)
assert G.check_cli_source()['level'] is None
assert G.check_cli_source(os.path.join(root, "nao_existe.db"))['level'] is None

# ---- manifestos
write_summaries([(U(1), "pA", ""), (U(2), "pA", ""), (U(3), "pB", ""), (U(4), "outside-of-project", "")])
manifest("Alfa", "pA", [U(1), U(1), U(1), U(9)])          # 2 repetidas, 1 órfã, U(2) fora do manifesto
manifest("Beta", "pB", [U(3)])                            # em dia
manifest("Fora", "outside-of-project", [U(4), U(4)])       # ignorado
c = G.check_manifests()
assert c['level'] == 1 and c['summary'].startswith("1 projeto(s)"), c
assert c['lines'] == ["▲ Alfa: 4 entradas; 2 repetida(s), 1 sem sessão no índice, 1 do índice fora do manifesto."], c['lines']
open(os.path.join(projects, "quebrado.json"), "w").write("{nao é json")
c = G.check_manifests(); assert c['level'] == 1 and any("quebrado.json: JSON ilegível" in x for x in c['lines'])
os.remove(os.path.join(projects, "quebrado.json")); manifest("Alfa", "pA", [U(1), U(2)])
assert G.check_manifests()['level'] == 0

# ---- relatório
md = G.doctor_markdown(G.doctor_checks())
assert md.startswith("# Diagnóstico do ecossistema") and "Só leitura" in md and "## Junções do remote control: ok" in md

# ---- app: linha na barra lateral e janela
manifest("Alfa", "pA", [U(1), U(1), U(2)])
def wait(a):
    end = time.time() + 20
    while a.loading and time.time() < end: a.update(); time.sleep(0.01)
    for _ in range(6): a.update(); time.sleep(0.02)
app = G.AntigravityGateApp(); wait(app)
assert [s[0] for s in app.sources].count(G.ACTIVE_LABEL) == 1
assert app.doctor_level() == 1 and app.env_doc.cget("text") == "▲ diagnóstico: 1 alerta(s)", app.env_doc.cget("text")
win = app.open_doctor(); app.update()
assert app.open_doctor() is win, "uma janela só"
body = win.text.get("1.0", "end")
assert "Manifestos de projeto: atenção" in body and "Alfa: 3 entradas; 1 repetida(s)" in body and "Junções do remote control: ok" in body, body
manifest("Alfa", "pA", [U(1), U(2)])
win.rerun(); app.update()
assert app.env_doc.cget("text") == "● diagnóstico: tudo ok" and "Manifestos de projeto: ok" in win.text.get("1.0", "end")
win.copy(); assert app.clipboard_get().startswith("# Diagnóstico do ecossistema")
out = os.path.join(root, "diag.md"); filedialog.asksaveasfilename = lambda *a, **k: out
win.save(); assert open(out, encoding="utf-8").read().startswith("# Diagnóstico")
win.destroy()
# F5 roda de novo
manifest("Alfa", "pA", [U(1)])
app.refresh(); wait(app)
assert app.env_doc.cget("text").startswith("▲"), app.env_doc.cget("text")
assert not shown, shown
app.destroy()
print("TODOS OS TESTES DOCTOR OK")
