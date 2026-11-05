import os, sys, sqlite3, tempfile, time, types
root = tempfile.mkdtemp(prefix="agym3b_")
home = os.path.join(root, "home"); os.makedirs(os.path.join(home, "Desktop"))
base = os.path.join(root, "gemini"); local = os.path.join(root, "local")
os.environ.update(HOME=home, ANTIGRAVITY_HOME=base, LOCALAPPDATA=local)
U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)
ant = os.path.join(base, "antigravity"); conv = os.path.join(ant, "conversations"); os.makedirs(conv); os.makedirs(os.path.join(base, "config", "projects"))
open(os.path.join(base, "config", "projects", "p.json"), "w").write('{"id":"p1","name":"Projeto Um","projectResources":{"resources":[{"folderUri":"file:///c%3A/work/um"}]}}')
c = sqlite3.connect(os.path.join(ant, "conversation_summaries.db"))
c.execute("""CREATE TABLE conversation_summaries(conversation_id TEXT, title TEXT, preview TEXT, step_count INT, last_modified_time TEXT,
             project_id TEXT, workspace_uris TEXT, agent_name TEXT, parent_conversation_id TEXT)""")
rows = [  # id, preview, steps, data, projeto, agente, pai
    (1, "migrar banco para postgres", 50, "2026-10-26T10:00:00Z", "p1", "DeepCoder", ""),
    (2, "worker: ajustar indices", 10, "2026-10-26T11:00:00Z", "p1", "DeepCoderWorkerL0", U(1)),
    (3, "worker: escrever testes", 30, "2026-10-26T12:00:00Z", "p1", "teamwork_preview_test_writer", U(1)),
    (4, "neto do worker", 5, "2026-10-26T13:00:00Z", "p1", "browser", U(2)),
    (5, "outra coisa solta", 99, "2026-10-25T09:00:00Z", "", "", ""),
    (6, "ciclo a", 1, "2026-10-24T09:00:00Z", "", "", U(7)),
    (7, "ciclo b", 2, "2026-10-24T10:00:00Z", "", "", U(6)),
]
for i, prev, steps, dt, pid, ag, par in rows:
    c.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?,?,?)", (U(i), "", prev, steps, dt, pid, "", ag, par))
# índice de conteúdo (FTS5) como o do Antigravity
c.execute("CREATE VIRTUAL TABLE conversations_fts USING fts5(conversation_id UNINDEXED, title, workspace, project, user_body, agent_body, tokenize='unicode61 remove_diacritics 2', prefix='1 2 3')")
c.execute("INSERT INTO conversations_fts VALUES(?,?,?,?,?,?)", (U(5), "", "", "", "preciso configurar o kubernetes no cluster", "usei helm e ingress"))
c.execute("INSERT INTO conversations_fts VALUES(?,?,?,?,?,?)", (U(3), "", "", "", "rode a suíte inteira", "pytest com cobertura"))
c.commit(); c.close()
for i in range(1, 8):
    d = sqlite3.connect(os.path.join(conv, U(i) + ".db")); d.execute("CREATE TABLE steps(idx INTEGER PRIMARY KEY, step_type INT, step_payload BLOB)"); d.commit(); d.close()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G
from tkinter import messagebox
info = []
messagebox.askyesno = lambda *a, **k: True
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, **k: info.append(a))
G.setup_logging()


def search(a, q=None):
    """Busca (a parte no conteúdo roda em thread desde a 1.5.0): espera terminar."""
    if q is not None: a.search_var.set(q)
    a.run_search()
    end = time.time() + 10
    while a.searching and time.time() < end: a.update(); time.sleep(0.01)
    a.update()

def wait(a):
    end = time.time() + 30
    while a.loading and time.time() < end: a.update(); time.sleep(0.01)
    a.update()
def iid(a, n): return next(i for i in a.iter_sessions() if a.cid_of(i) == U(n))
def kids(a, n): return [a.cid_of(k) for k in a.tree.get_children(iid(a, n))]
def top(a, proj): return [a.cid_of(k) for k in a.tree.get_children(proj)]
def projs(a): return {a.tree.item(p, "text").split(" (")[0].strip(): p for p in a.tree.get_children()}

app = G.AntigravityGateApp(); wait(app)
P = projs(app); print(list(P))
# 1. hierarquia: filhos sob o pai, neto sob o filho; sessões soltas na raiz; ciclo não some
assert "Projeto Um" in P and "Outside of Project" in P
assert top(app, P["Projeto Um"]) == [U(1)] and sorted(kids(app, 1)) == sorted([U(2), U(3)]) and kids(app, 2) == [U(4)]
assert set(top(app, P["Outside of Project"])) == {U(5), U(6), U(7)} or {U(5)} <= set(top(app, P["Outside of Project"]))
assert {U(6), U(7)} <= {app.cid_of(i) for i in app.iter_sessions()}, "ciclo de parentesco não pode sumir"
assert "+2 sub-agentes" in app.tree.item(iid(app, 1), "text") and "+1 sub-agente" in app.tree.item(iid(app, 2), "text")
assert app.tree.item(iid(app, 3), "values")[6] == "teamwork_preview_test_writer" and app.tree.item(iid(app, 5), "values")[6] == "-"

# 2. ordenação: padrão data desc; clique alterna; numérica; por texto
order = lambda: [app.cid_of(i) for i in app.tree.get_children(P_()) ]
P_ = lambda: projs(app)["Projeto Um"]
assert kids(app, 1) == [U(3), U(2)]                       # 12h antes de 11h
app.sort_by("col_date"); assert kids(app, 1) == [U(2), U(3)] and "▲" in app.tree.heading("col_date", "text")   # alterna p/ asc
app.sort_by("col_steps"); assert kids(app, 1) == [U(3), U(2)] and "▼" in app.tree.heading("col_steps", "text") and "▲" not in app.tree.heading("col_date", "text")
app.sort_by("col_title"); assert kids(app, 1) == [U(2), U(3)]                       # "worker: ajustar" < "worker: escrever"
app.sort_by("col_title"); assert kids(app, 1) == [U(3), U(2)]

# 3. busca por metadados (título/agente/projeto) -> lista plana
search(app, "postgres")
flat = [app.cid_of(i) for i in app.iter_sessions()]; assert flat == [U(1)], flat
assert app.tree.get_children(iid(app, 1)) == (), "com busca ativa a lista é plana"
search(app, "deepcoderworker"); assert [app.cid_of(i) for i in app.iter_sessions()] == [U(2)]
search(app, "projeto um"); assert {app.cid_of(i) for i in app.iter_sessions()} == {U(1), U(2), U(3), U(4)}
# 4. busca por CONTEÚDO (índice FTS do Antigravity), com prefixo e sem acento
search(app, "kubern"); assert [app.cid_of(i) for i in app.iter_sessions()] == [U(5)], [app.cid_of(i) for i in app.iter_sessions()]
assert "1 resultado" in app.status.cget("text")
search(app, "suite"); assert [app.cid_of(i) for i in app.iter_sessions()] == [U(3)]     # "suíte" casa "suite"
search(app, "inexistente-xyz"); assert list(app.iter_sessions()) == [] and "0 resultado" in app.status.cget("text")
# 5. limpar volta à árvore com hierarquia
app.clear_search(); assert kids(app, 1) and app.search_var.get() == ""
# 6. entrada mal-formada não quebra o FTS
for q in ('"', "a OR", "foo*", "(", "NEAR(", "'; DROP"): search(app, q)
app.clear_search()

# 7. marcar o pai não marca os filhos; pasta marca todos, inclusive netos
app.tree.selection_set(iid(app, 1)); app.mark_selected("aprovada")
assert "Aprovada" in app.tree.item(iid(app, 1), "text") and "Pendente" in app.tree.item(iid(app, 2), "text")
app.tree.selection_set(projs(app)["Projeto Um"]); app.mark_selected("arquivada")
assert all("Arquivada" in app.tree.item(iid(app, n), "text") for n in (1, 2, 3, 4)) and "+2 sub-agentes" in app.tree.item(iid(app, 1), "text")

# 8. duplo clique em sessão filha abre os detalhes; copiar UUID; abrir pasta sem arquivo
opened = []; app.open_details = lambda: opened.append(1)
app.tree.item(projs(app)["Projeto Um"], open=True); app.tree.item(iid(app, 1), open=True); app.update()
app.on_double_click(types.SimpleNamespace(y=app.tree.bbox(iid(app, 2))[1] + 5)); assert opened
app.copy_uuid(iid(app, 4)); assert app.clipboard_get() == U(4)
app.db_files.pop(U(4)); info.clear(); app.open_folder(iid(app, 4)); assert info and "não tem arquivo" in info[0][1]

# 9. recarregar zera a busca; tema não mexe nos dados
search(app, "postgres"); app.refresh(); wait(app)
assert app.search_var.get() == "" and len(list(app.iter_sessions())) == 7
app.destroy(); print("TODOS OS TESTES M3b OK")
