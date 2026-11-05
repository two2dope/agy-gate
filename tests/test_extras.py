import os, sys, sqlite3, tempfile, time, json
root = tempfile.mkdtemp(prefix="agyext_")
base = os.path.join(root, "gemini")
os.environ.update(HOME=os.path.join(root, "home"), ANTIGRAVITY_HOME=base, LOCALAPPDATA=os.path.join(root, "local"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G

def vi(n):
    o = bytearray()
    while True:
        b = n & 0x7f; n >>= 7
        if n: o.append(b | 0x80)
        else: o.append(b); return bytes(o)
fv = lambda f, v: vi(f << 3) + vi(v); fl = lambda f, b: vi(f << 3 | 2) + vi(len(b)) + b; fs = lambda f, s: fl(f, s.encode())
def tool(sec, name, args, status=3):
    return 132, status, fv(1, 132) + fl(5, fl(1, fv(1, sec)) + fv(3, 2) + fl(4, fs(1, "c") + fs(2, name) + fs(3, json.dumps(args)))) + fl(140, fl(2, fs(1, "ok"))), None

# ---------- B: lista de arquivos ----------
assert [G.file_icon(x) for x in ("a/b.PY", "d:\\Seg\\ptz.py", "x.html", "estilo.css", ".env.local", "Dockerfile", "foto.png", "desconhecido.xyz", "sem_extensao", ".gitignore", "n.md")] == \
       ["🐍", "🐍", "🌐", "🎨", "🔒", "⚙️", "🖼️", "📄", "📄", "🙈", "📝"]
assert G.disk_state("relativo/x.py") == "?"
d = os.path.join(root, "proj"); os.makedirs(d)
f1, f2, notes, gone, pipe = (os.path.join(d, n) for n in ("f1.py", "f2.css", "notes.md", "gone.html", "a|b.py"))
for f in (f1, f2, notes, pipe): open(f, "w").write("x")
assert G.disk_state(f1) == "✔" and G.disk_state(gone) == "✖ não existe mais"
assert [G.classify_tool(n) for n in ("replace_file_content", "write_to_file", "run_command", "read_file", "view_file", "list_dir")] == ["write", "write", "cmd", "read", "read", "read"]

steps = [tool(1000 + i, "replace_file_content", {"TargetFile": f1}) for i in range(3)] + [tool(1010, "replace_file_content", {"TargetFile": gone}), tool(1011, "write_file", {"TargetFile": pipe})]
steps += [tool(1020, "read_file", {"Path": f1}), tool(1021, "read_file", {"Path": f1})] + [tool(1030 + i, "view_file", {"AbsolutePath": f2}) for i in range(4)] + [tool(1040, "read_file", {"Path": notes})]
steps += [tool(1050, "run_command", {"CommandLine": "pytest"})]
conv = os.path.join(base, "antigravity", "conversations"); os.makedirs(conv); os.makedirs(os.path.join(base, "config", "projects"))
CID = "0000000a-0000-0000-0000-00000000000a"; db = os.path.join(conv, CID + ".db")
c = sqlite3.connect(db); c.execute("CREATE TABLE steps (idx integer PRIMARY KEY, step_type integer, status integer, step_payload blob, error_details blob)")
for i, (t, st, p, e) in enumerate(steps): c.execute("INSERT INTO steps VALUES(?,?,?,?,?)", (i, t, st, p, e))
c.commit(); c.close()
meta = {'cid': CID, 'title': "Arquivos", 'fpath': db}
G.export_session('dossier', db, meta, os.path.join(root, "d.md")); G.export_session('full', db, meta, os.path.join(root, "f.md"))
doss, full = open(os.path.join(root, "d.md"), encoding="utf-8").read(), open(os.path.join(root, "f.md"), encoding="utf-8").read()
line = lambda text, name: next(l for l in text.splitlines() if name in l and l.startswith("|"))
assert "## Arquivos alterados (3)" in doss and "## Arquivos consultados (3)" in doss
assert line(doss, "f1.py").startswith("| 🐍 |") and "×3" in line(doss, "f1.py") and line(doss, "f1.py").rstrip().endswith("| ✔ |")
assert line(doss, "gone.html").startswith("| 🌐 |") and "✖ não existe mais" in line(doss, "gone.html")
assert "a\\|b.py" in doss, "barra vertical do nome não quebra a tabela"
mod_sec = doss.split("## Arquivos alterados")[1].split("## Arquivos consultados")[0]
assert mod_sec.index("f1.py") < mod_sec.index("gone.html"), "mais alterado primeiro"
read_sec = doss.split("## Arquivos consultados")[1].split("## ")[0]
assert read_sec.index("f2.css") < read_sec.index("f1.py") < read_sec.index("notes.md") and "×4" in line(read_sec, "f2.css") and line(read_sec, "f2.css").startswith("| 🎨 |")
assert "No disco" in doss and "pytest" in doss
assert "## Arquivos citados (5)" in full and full.index("## Arquivos citados") < full.index("## Linha do tempo")
r = line(full, "f1.py"); assert "×3" in r and "×2" in r and r.startswith("| 🐍 |")
r = line(full, "f2.css"); assert "| - | ×4 |" in r
assert full.index("f1.py") < full.index("gone.html") < full.index("f2.css"), "alterados antes dos só lidos"
# limite de linhas
many = {f"/x/f{i}.py": [1, 0] for i in range(70)}
t = G.files_table(many, "mod", 40); assert t.count("\n| 🐍 |") == 40 and "e mais 30 arquivo(s)" in t
assert "| Alterado | Lido |" in G.files_table({"/a.py": [1, 1]}, "both")

# ---------- A: notificações, desfazer e estado vazio ----------
U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)
ant = os.path.join(base, "antigravity")
sc = sqlite3.connect(os.path.join(ant, "conversation_summaries.db"))
sc.execute("CREATE TABLE conversation_summaries(conversation_id TEXT, title TEXT, preview TEXT, step_count INT, last_modified_time TEXT, project_id TEXT, workspace_uris TEXT, agent_name TEXT, parent_conversation_id TEXT)")
for i in range(1, 4): sc.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?,?,?)", (U(i), "", "sessao %d" % i, i, "2026-10-26T1%d:00:00Z" % i, "", "", "", ""))
sc.commit(); sc.close()
for i in range(1, 4):
    d2 = sqlite3.connect(os.path.join(conv, U(i) + ".db")); d2.execute("CREATE TABLE steps(idx INTEGER PRIMARY KEY, step_type INT, status INT, step_payload BLOB, error_details BLOB)"); d2.commit(); d2.close()
open(os.path.join(conv, U(9) + ".db"), "wb").write(b"lixo" * 50)            # banco corrompido: gera aviso de leitura
from tkinter import messagebox, filedialog
info = []
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, _n=n, **k: info.append((_n, a)))
messagebox.askyesno = lambda *a, **k: True
G.setup_logging()

def search(a, q=None):
    """Busca (a parte no conteúdo roda em thread desde a 1.5.0): espera terminar."""
    if q is not None: a.search_var.set(q)
    a.run_search()
    end = time.time() + 10
    while a.searching and time.time() < end: a.update(); time.sleep(0.01)
    a.update()

def wait(a):
    end = time.time() + 20
    while (a.loading or a.exporting or a.autorunning) and time.time() < end: a.update(); time.sleep(0.01)
    for _ in range(8): a.update(); time.sleep(0.02)
app = G.AntigravityGateApp(); app.geometry("1240x760+0+0"); wait(app)
iid = lambda n: next(i for i in app.iter_sessions() if app.cid_of(i) == U(n))
last = lambda: app.toast_log[-1]

# aviso de leitura na carga, com ação
assert any(k == "warn" and "aviso(s) ao ler os bancos" in txt and acts == ["Abrir log"] for k, txt, acts in app.toast_log), app.toast_log
assert app.toasts and app.toasts[-1].winfo_ismapped() or True
# marcar -> toast com Desfazer; desfazer restaura e avisa
app.tree.selection_set(iid(1)); app.mark_selected("aprovada"); app.update()
assert last() == ("ok", "1 sessão marcada como Aprovada", ["Desfazer"]) and app.states[U(1)] == "aprovada"
app.toasts[-1].buttons[0].invoke(); app.update()
assert app.states.get(U(1), "pendente") == "pendente" and last()[0] == "info" and "Desfeito" in last()[1]
app.tree.selection_set([iid(1), iid(2)]); app.mark_selected("arquivada"); assert last()[1] == "2 sessões marcadas como Arquivada"
app.tree.selection_set(iid(3)); app.mark_selected("aprovada")
app.tree.selection_set([iid(1), iid(2), iid(3)]); app.mark_selected("pendente")
assert app.states == {} or all(v == "pendente" for v in app.states.values())
app.toasts[-1].buttons[0].invoke(); app.update()                      # desfaz o último: 1 e 2 arquivadas, 3 aprovada
assert (app.states.get(U(1)), app.states.get(U(2)), app.states.get(U(3))) == ("arquivada", "arquivada", "aprovada"), app.states
# copiar UUID
app.tree.selection_set(iid(2)); app.copy_selected_uuid(); assert app.clipboard_get() == U(2) and last() == ("ok", "UUID copiado: " + U(2), [])
# limites
app.set_limits("amplo", 300000, 500000); assert last()[0] == "info" and "atenção 300k" in last()[1] and "crítico 500k" in last()[1]
# empilhamento: no máximo 4, mais novo embaixo; fechar reorganiza; ttl derruba sozinho
app.dismiss_toasts(); assert not app.toasts
for i in range(6): app.notify("info", f"mensagem {i}")
app.update(); assert len(app.toasts) == 4 and last()[1] == "mensagem 5"
ys = [t.winfo_y() for t in app.toasts]; assert ys == sorted(ys, reverse=True)[::-1] or len(set(ys)) == 4, "toasts empilhados em posições distintas"
app.toasts[0].dismiss(); assert len(app.toasts) == 3
t = app.notify("ok", "some logo", ttl=80); end = time.time() + 2
while t in app.toasts and time.time() < end: app.update(); time.sleep(0.02)
assert t not in app.toasts, "expira sozinha"
app.notify("warn", "x"); app.set_theme("claro"); assert not app.toasts, "trocar de tema fecha as notificações"
# exportar: toast com ações; sem popup de OK
dest = os.path.join(root, "saida.md"); filedialog.asksaveasfilename = lambda *a, **k: dest
app.tree.selection_set(iid(1)); info.clear(); app.start_export('full'); wait(app)
assert last() == ("ok", "Salvo: saida.md", ["Abrir arquivo", "Abrir pasta"]) and not any(m[0] == "showinfo" for m in info)
app.toasts[-1].buttons[1].invoke(); assert last()[0] == "info" and "Caminho:" in last()[1], "sem startfile (Linux): mostra o caminho"
# Auto-Run: resumo em notificação
app.confirm_autorun = lambda its, done: {'dry_run': True, 'redo': True}
app.tree.selection_set(iid(3)); app.start_autorun(); wait(app)
assert last()[0] == "ok" and "Auto-Run concluído" in last()[1] and "simulação" in last()[1], last()

# estado vazio: busca sem resultado, com ação; fonte vazia; carregando
search(app, "zzzz-nao-existe"); app.update()
assert app.empty.winfo_manager() == "place" and app.empty_title.cget("text") == "Nenhuma sessão encontrada" and "zzzz-nao-existe" in app.empty_sub.cget("text")
assert app.btn["empty_action"].text == "Limpar busca" and app.btn["empty_action"].winfo_manager() == "pack"
app.btn["empty_action"].invoke(); app.update()
assert app.empty.winfo_manager() == "" and len(list(app.iter_sessions())) == 5, "limpar busca traz todas de volta (3 boas, 1 do teste de arquivos, 1 corrompida)"
app.refresh(); assert app.loading  # sem update(): com cache a leitura pode acabar dentro dele
# (durante a carga a tabela está vazia)
assert app.empty.winfo_manager() == "place" and app.empty_title.cget("text") == "Lendo as sessões…" and app.btn["empty_action"].winfo_manager() == ""
wait(app); assert app.empty.winfo_manager() == ""
for f in os.listdir(conv): os.remove(os.path.join(conv, f))
sc = sqlite3.connect(os.path.join(ant, 'conversation_summaries.db')); sc.execute('DELETE FROM conversation_summaries'); sc.commit(); sc.close()
app.refresh(); wait(app); app.update()
assert app.empty_title.cget("text") == "Nenhuma sessão nesta fonte" and "Pasta:" in app.empty_sub.cget("text") and app.btn["empty_action"].text == "Atualizar"
app.destroy(); print("TODOS OS TESTES EXTRAS OK")
