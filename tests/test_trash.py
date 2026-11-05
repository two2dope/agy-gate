"""1.3: lixeira com prazo, candidatas sugeridas (o usuário confirma), lista para o agy e dossiês do Gate."""
import os, sys, sqlite3, tempfile, time, json
from datetime import datetime, timedelta
root = tempfile.mkdtemp(prefix="agytrash_")
base = os.path.join(root, "gemini")
os.environ.update(HOME=os.path.join(root, "home"), ANTIGRAVITY_HOME=base, LOCALAPPDATA=os.path.join(root, "local"))
U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)
ant = os.path.join(base, "antigravity"); conv = os.path.join(ant, "conversations"); os.makedirs(conv); os.makedirs(os.path.join(base, "config", "projects"))
# (título, passos): 1 trabalho real, 2 teste, 3 retomada curta, 4 trivial, 5 retomada longa (fica), 6 aprovada trivial (fica), 7 arquivada antiga, 8 arquivada recente
SESS = {1: ("Auditoria do ecossistema", 40), 2: ("Test Conversation", 3), 3: ("Retomada de Sessão Anterior", 6), 4: ("Acknowledge Command With Ok", 2),
        5: ("Retomada do SMT1", 30), 6: ("Ok rapido", 1), 7: ("Sessão velha", 20), 8: ("Sessão arquivada ontem", 20)}
c = sqlite3.connect(os.path.join(ant, "conversation_summaries.db"))
c.execute("CREATE TABLE conversation_summaries(conversation_id TEXT, title TEXT, preview TEXT, step_count INT, last_modified_time TEXT, project_id TEXT, workspace_uris TEXT, agent_name TEXT, parent_conversation_id TEXT)")
for i, (title, steps) in SESS.items():
    c.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?,?,?)", (U(i), title, "pedido %d" % i, steps, "2026-10-26T10:00:00Z", "", "", "", ""))
c.commit(); c.close()
for i in SESS:
    d = sqlite3.connect(os.path.join(conv, U(i) + ".db")); d.execute("CREATE TABLE steps(idx INTEGER PRIMARY KEY, step_type INT, status INT, step_payload BLOB, error_details BLOB)"); d.commit(); d.close()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G
from tkinter import messagebox, filedialog
asked, shown = [], []
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, _n=n, **k: shown.append((_n, a)))
messagebox.askyesno = lambda *a, **k: asked.append(a) or True
G.setup_logging()

# ---- regras puras
r = lambda title, steps, **kw: dict({'cid': 'x', 'title': title, 'steps': steps, 'hay': title.lower()}, **kw)
assert G.trash_reason(r("Test Conversation", 5), "pendente") == "teste"
assert G.trash_reason(r("teste3", 3), "pendente") == "teste"
assert G.trash_reason(r("Retomada De Sessão E Dossiê", 6), "pendente") == "retomada sem trabalho"
assert G.trash_reason(r("Qualquer", 5, hay=G.AGY_PROMPT_MARK.lower()), "pendente") == "retomada sem trabalho", "prompt do Auto-Run"
assert G.trash_reason(r("Ending Conversation Session", 3), "pendente") == "trivial"
assert G.trash_reason(r("Sessão Restaurada (stub vazio)", 0), "pendente") == "trivial"
assert G.trash_reason(r("Retomada longa", 7), "pendente") == "" and G.trash_reason(r("Auditoria", 40), "pendente") == ""
assert G.trash_reason(r("Teste", 3), "aprovada") == "" and G.trash_reason(r("Teste", 3), "arquivada") == "" and G.trash_reason(r("Teste", 3), "lixeira") == ""
assert G.trash_reason(r("Teste", 3, running=True), "pendente") == "", "sessão em execução nunca é sugerida"
md = G.trash_markdown([{'cid': U(1), 'title': "A|B", 'project': "P", 'steps': 3}])
assert "/resume" in md and "F4" in md and f"`{U(1)}`" in md and "A/B" in md and md.rstrip().endswith("```")

# ---- dossiês: só os do Auto-Run (nome retomada_<id>_<data>.md) e existentes
hd = os.path.join(root, "dossies"); os.makedirs(hd)
good = os.path.join(hd, "retomada_%s_20261105-091312.md" % U(3)[:8]); open(good, "w").write("x")
user_file = os.path.join(hd, "minhas_notas.md"); open(user_file, "w").write("x")
assert G.gate_dossiers([good, user_file, os.path.join(hd, "retomada_00000009_20261105-091312.md")]) == [good]

# ---- StateStore: prazo e dossiês registrados
st = G.StateStore(G.STATE_DB)
st.set_many([U(6)], "aprovada")
st.set_many([U(7), U(8)], "arquivada")
with sqlite3.connect(G.STATE_DB) as c:  # U(7) arquivada há 40 dias, U(8) ontem
    c.execute("UPDATE session_state SET updated_at=? WHERE cid=?", ((datetime.now() - timedelta(days=40)).strftime('%Y-%m-%d %H:%M:%S'), U(7)))
    c.execute("UPDATE session_state SET updated_at=? WHERE cid=?", ((datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S'), U(8)))
assert st.sweep_trash(0) == [], "0 desliga"
st.add_handoff(U(3), "", good, "dossie", "simulação")
st.add_handoff(U(3), "", user_file, "dossie", "caminho estranho")  # registrado, mas não tem nome de dossiê: nunca é apagado
assert st.dossiers_for([U(3), U(1)]) == [good, user_file]

# ---- app: ao abrir, a arquivada antiga vai para a lixeira e as candidatas são sugeridas (sem mudar nada sozinhas)
def wait(a):
    end = time.time() + 20
    while a.loading and time.time() < end: a.update(); time.sleep(0.01)
    for _ in range(6): a.update(); time.sleep(0.02)
app = G.AntigravityGateApp(); wait(app)
assert app.trash_days() == 30
assert app.states.get(U(7)) == "lixeira" and app.states.get(U(8)) == "arquivada", app.states
texts = [x[1] for x in app.toast_log]
assert any("arquivada(s) há 30 dias" in x for x in texts) and any("3 sessão(ões) de teste ou sem trabalho sugerida(s)" in x for x in texts), texts
cands = {r['cid']: why for r, why in app.trash_candidates()}
assert cands == {U(2): "teste", U(3): "retomada sem trabalho", U(4): "trivial"}, cands
for i in (2, 3, 4): assert app.states.get(U(i)) is None, "sugestão não muda o estado"
# a sessão na lixeira some de Todas e aparece no filtro Lixeira
listed = lambda: {app.cid_of(i) for p in app.tree.get_children() for i in app.iter_sessions(p)}
assert U(7) not in listed() and U(1) in listed()
assert app.side_items["lixeira"].count.cget("text") == "1" and app.tabs["lixeira"].count == 1
app.set_filter("lixeira"); app.update()
assert listed() == {U(7)} and app.tabs["lixeira"].on
app.set_filter(None); app.update()
assert U(7) not in listed()
# busca também não traz a lixeira
app.search_var.set("Sessão velha"); app.run_search(); app.update()
assert U(7) not in listed()
app.clear_search()

# ---- janela da lixeira
win = app.open_trash(); app.update()
assert app.open_trash() is win, "uma janela só"
assert set(win.sug.get_children()) == {U(2), U(3), U(4)} and set(win.sug.selection()) == {U(2), U(3), U(4)}, "sugestões vêm marcadas"
assert win.sug_head.cget("text") == "Sugeridas (3)" and win.bin_head.cget("text") == "Na lixeira (1)"
win.sug.selection_remove(U(4))  # o usuário mantém a trivial
win.move_selected(); app.update()
assert app.states.get(U(2)) == "lixeira" and app.states.get(U(3)) == "lixeira" and app.states.get(U(4)) is None
assert set(win.bin.get_children()) == {U(2), U(3), U(7)} and set(win.sug.get_children()) == {U(4)}
assert U(2) not in listed() and U(3) not in listed()
assert app.tabs["lixeira"].count == 3
# copiar UUIDs
win.copy_ids(); assert set(app.clipboard_get().split()) == {U(2), U(3), U(7)}
# salvar lista
out = os.path.join(root, "lista.md"); filedialog.asksaveasfilename = lambda *a, **k: out
win.save_list(); txt = open(out, encoding="utf-8").read()
assert all(U(i) in txt for i in (2, 3, 7)) and "F4" in txt
# apagar dossiês do Gate: só o retomada_….md; a nota do usuário fica
assert "(1)" in win.b_dossiers.text, win.b_dossiers.text
asked.clear(); win.delete_dossiers(); app.update()
assert asked and not os.path.exists(good) and os.path.exists(user_file)
assert "(0)" in win.b_dossiers.text
# restaurar: volta como arquivada, com o prazo recomeçando
win.bin.selection_set(U(7)); win.restore_selected(); app.update()
assert app.states.get(U(7)) == "arquivada" and U(7) in listed()
assert st.sweep_trash(30) == [], "restaurada hoje: o prazo recomeça"
# prazo ajustável e lembrado
win.days.set("7"); win.save_days(); assert app.trash_days() == 7 and G.load_settings()['trash_days'] == 7
win.days.set("abc"); win.save_days(); assert app.trash_days() == 7 and win.days.get() == "7"
win.destroy()
# menu da sessão tem "Mover para a lixeira"
app.tree.selection_set(next(app.iter_sessions(app.tree.get_children()[0])))
m = app.build_menu(app.tree.selection()[0]); labels = [m.entrycget(i, "label") for i in range(m.index("end") + 1) if m.type(i) == "command"]
assert "✖ Mover para a lixeira" in labels, labels
assert not shown, shown
app.destroy()
print("TODOS OS TESTES TRASH OK")
