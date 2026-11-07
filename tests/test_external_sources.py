"""Fontes externas (1.5.2): abrir à mão uma pasta com sessões salvas (cópia da instalação, backup, outro PC).
Regras: só leitura (nada é gravado na pasta), detecção da pasta com os .db (a própria ou a subpasta conversations),
persistência da lista, pasta indisponível não quebra, e nenhuma ação que grave estado por sessão
(aprovar, arquivar, pendente, lixeira, Auto-Run) numa fonte externa."""
import os, sys, sqlite3, tempfile, hashlib, shutil, time


def wait(a):
    end = time.time() + 30
    while a.loading and time.time() < end:
        a.update(); time.sleep(0.01)
    a.update()


root = tempfile.mkdtemp(prefix="agyext_")
home = os.path.join(root, "home"); os.makedirs(os.path.join(home, "Desktop"))
base = os.path.join(root, "gemini")
os.environ.update(HOME=home, ANTIGRAVITY_HOME=base, LOCALAPPDATA=os.path.join(root, "local"))
U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)
A, B, C, D = U(1), U(2), U(3), U(4)


def summ(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE conversation_summaries(conversation_id TEXT, title TEXT, preview TEXT, step_count INT, last_modified_time TEXT, project_id TEXT, workspace_uris TEXT)")
    for r in rows:
        c.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?)", r)
    c.commit(); c.close()


def sess(folder, cid, nsteps):
    os.makedirs(folder, exist_ok=True)
    c = sqlite3.connect(os.path.join(folder, cid + ".db"))
    c.execute("CREATE TABLE steps(idx INTEGER PRIMARY KEY, step_type INT DEFAULT 0, status INT DEFAULT 3, step_payload BLOB, error_details BLOB)")
    for i in range(nsteps):
        c.execute("INSERT INTO steps VALUES(?,?,?,?,?)", (i, 0, 3, b"x" * 50, None))
    c.commit(); c.close()


def digest(folder):
    """{caminho relativo: sha256} de todos os arquivos: prova que a pasta não foi alterada nem ganhou arquivos (-wal, -shm)."""
    out = {}
    for d, _dirs, files in os.walk(folder):
        for f in files:
            p = os.path.join(d, f)
            out[os.path.relpath(p, folder)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out


# instalação ativa: A e B
ant = os.path.join(base, "antigravity")
summ(os.path.join(ant, "conversation_summaries.db"), [(A, "", "ativa A", 5, "2026-10-26T10:00:00Z", "", ""), (B, "", "ativa B", 9, "2026-10-26T11:00:00Z", "", "")])
sess(os.path.join(ant, "conversations"), A, 5); sess(os.path.join(ant, "conversations"), B, 9)
os.makedirs(os.path.join(base, "config", "projects"))

# cópia exata de uma instalação anterior (com acento e espaço no caminho): A (mesmo id da ativa) e C (só nela)
old = os.path.join(root, "Cópia antiga", "antigravity")
summ(os.path.join(old, "conversation_summaries.db"), [(A, "", "A da cópia", 3, "2026-10-01T08:00:00Z", "", ""), (C, "", "C da cópia", 7, "2026-10-02T08:00:00Z", "", "")])
sess(os.path.join(old, "conversations"), A, 3); sess(os.path.join(old, "conversations"), C, 7)
# pasta solta só com .db, sem summaries
flat = os.path.join(root, "solta"); sess(flat, D, 2)
empty = os.path.join(root, "vazia"); os.makedirs(empty)
a_file = os.path.join(root, "arquivo.txt"); open(a_file, "w").write("x")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G
from tkinter import messagebox, filedialog

shown, asked = [], []
for n in ("showinfo", "showwarning", "showerror"):
    setattr(messagebox, n, lambda *a, _n=n, **k: shown.append((_n, a)))
answer = {"v": True}
messagebox.askyesno = lambda *a, **k: (asked.append(a), answer["v"])[1]
OUT = os.path.join(root, "saida.md")
filedialog.asksaveasfilename = lambda *a, **k: OUT
G.setup_logging()

# ---- resolve_session_folder: a pasta escolhida vira (pasta com os .db, summaries, problema) ----
conv, sdb, why = G.resolve_session_folder(old)                      # a pasta-mãe (cópia inteira de antigravity)
assert why == "" and os.path.samefile(conv, os.path.join(old, "conversations")) and os.path.samefile(sdb, os.path.join(old, "conversation_summaries.db")), (conv, sdb, why)
conv, sdb, why = G.resolve_session_folder(os.path.join(old, "conversations"))   # a própria pasta conversations
assert why == "" and os.path.samefile(conv, os.path.join(old, "conversations")) and sdb and os.path.samefile(sdb, os.path.join(old, "conversation_summaries.db"))
conv, sdb, why = G.resolve_session_folder(flat)                     # pasta solta: sem summaries é permitido
assert why == "" and os.path.samefile(conv, flat) and sdb is None
conv, sdb, why = G.resolve_session_folder(empty)
assert conv is None and "nenhuma sessão" in why.lower(), why
conv, sdb, why = G.resolve_session_folder(os.path.join(root, "nao-existe"))
assert conv is None and why, why
conv, sdb, why = G.resolve_session_folder(a_file)
assert conv is None and why, why
# um nível só: .db dentro de conversations/x/ não é achado (sem varredura recursiva)
deep = os.path.join(root, "fundo"); sess(os.path.join(deep, "a", "b"), D, 1)
assert G.resolve_session_folder(deep)[0] is None
print("resolve_session_folder ok")

# ---- rótulo ----
assert G.external_label(os.path.join("x", "Cópia antiga", "antigravity"), set()) == "Externa: Cópia antiga/antigravity"
assert G.external_label("antigravity", set()) == "Externa: antigravity"
taken = {"Externa: Cópia antiga/antigravity"}
assert G.external_label(os.path.join("x", "Cópia antiga", "antigravity"), taken).startswith("Externa: ") and G.external_label(os.path.join("x", "Cópia antiga", "antigravity"), taken) not in taken

# ---- StateStore: lista persistida ----
st = G.StateStore(os.path.join(root, "st.db"))
assert st.external_sources() == []
st.add_external_source("/a/b"); st.add_external_source("/a/b"); st.add_external_source("/c")
assert st.external_sources() == ["/a/b", "/c"], st.external_sources()
st.remove_external_source("/a/b"); assert st.external_sources() == ["/c"]
st.remove_external_source("/nao/existe")
print("StateStore ok")

# ---- app ----
old_before, ant_before, flat_before = digest(os.path.join(root, "Cópia antiga")), digest(ant), digest(flat)
app = G.AntigravityGateApp(); wait(app)
leaves = lambda: {app.tree.item(c, "values")[7]: app.tree.item(c, "values") for p in app.tree.get_children() for c in app.tree.get_children(p)}
assert len(app.sources) == 1 and not app.source_readonly()
vals = list(app.src_box.cget("values"))
assert vals[:-1] == [s[0] for s in app.sources] and "Abrir pasta" in vals[-1], vals          # entrada de ação no fim do seletor
assert len(vals) == 2, "sem fonte externa selecionada não há 'Remover'"

# a fonte ativa: aprovar A (o mesmo id existe na cópia: estado por sessão é compartilhado)
app.tree.selection_set([c for p in app.tree.get_children() for c in app.tree.get_children(p) if app.tree.item(c, "values")[7] == A][0])
app.mark_selected("aprovada"); assert app.states[A] == "aprovada"

# abrir a pasta-mãe da cópia
label = app.add_external_source(old); wait(app)
assert label and label.startswith("Externa: ") and "Cópia antiga" in label, label
assert app.sources[app.source_idx][0] == label and app.source_readonly()
L = leaves(); print("externa:", {k[:8]: v[5] for k, v in L.items()})
assert set(L) == {A, C} and L[A][5] == "A da cópia" and L[C][5] == "C da cópia", L
assert "somente leitura" in app.status.cget("text").lower(), app.status.cget("text")
assert app.state.external_sources() == [os.path.abspath(old)], app.state.external_sources()
vals = list(app.src_box.cget("values"))
assert len(vals) == len(app.sources) + 2 and "Remover" in vals[-1], vals                       # agora há 'Remover'
assert app.src_box.current() == app.source_idx and app.src_box_top.current() == app.source_idx

# somente leitura: nada que grave estado por sessão
before_states = dict(app.state.load())
sel = [c for p in app.tree.get_children() for c in app.tree.get_children(p) if app.tree.item(c, "values")[7] == C][0]
app.tree.selection_set(sel); app.update_actions()
for name in ("approve", "archive", "pending", "autorun", "trash"):
    assert not app.btn[name].enabled and "externa" in app.btn[name].reason.lower(), (name, app.btn[name].enabled, app.btn[name].reason)
for name in ("export", "dossier"):
    assert app.btn[name].enabled, (name, app.btn[name].reason)
shown.clear()
for status in ("aprovada", "arquivada", "pendente", "lixeira"):
    app.mark_selected(status)
assert app.state.load() == before_states and len(shown) == 4, (app.state.load(), shown)
menu = app.build_menu(sel)
disabled = {menu.entrycget(i, "label"): menu.entrycget(i, "state") for i in range(menu.index("end") + 1) if menu.type(i) == "command"}
for text, state in disabled.items():
    if any(k in text for k in ("Aprovar", "Arquivar", "Pendente", "lixeira")):
        assert state == "disabled", (text, state)
    if "Exportar diálogo" in text or "Dossiê" in text:
        assert state == "normal", (text, state)
# A está aprovada (veio da fonte ativa), mas na externa não vira candidata ao Auto-Run
assert app.states[A] == "aprovada" and app.autorun_candidates() == []
shown.clear(); app.start_autorun()
assert not app.autorunning and not app._confirming and shown, "Auto-Run não pode abrir numa fonte externa"
app.open_trash(); assert getattr(app, "trash_win", None) is None, "lixeira não abre numa fonte externa"
print("somente leitura ok")

# exportar o dossiê de uma sessão da fonte externa funciona
app.tree.selection_set(sel); app.start_export("dossier")
end = time.time() + 20
while app.exporting and time.time() < end:
    app.update(); time.sleep(0.01)
app.update()
md = open(OUT, encoding="utf-8").read()
assert C in md and "Externa:" in md, md[:400]

# a pasta não foi tocada: mesmos arquivos, mesmo conteúdo, nenhum -wal/-shm novo
assert digest(os.path.join(root, "Cópia antiga")) == old_before, "a pasta externa foi alterada"
assert digest(ant) == ant_before
print("pasta intacta ok")

# a mesma pasta de novo (por outro caminho: a subpasta conversations): seleciona a existente, não duplica
n = len(app.sources); shown.clear()
again = app.add_external_source(os.path.join(old, "conversations")); wait(app)
assert again == label and len(app.sources) == n and len(app.state.external_sources()) == 1 and shown, (again, shown)
# a pasta ativa: avisa e não adiciona
shown.clear(); r = app.add_external_source(ant); wait(app)
assert r is None and app.source_idx == 0 and len(app.state.external_sources()) == 1 and shown and "ativa" in str(shown[-1]).lower(), shown
# pasta sem sessões e pasta inexistente: avisam e não adicionam
for bad in (empty, os.path.join(root, "nao-existe")):
    shown.clear(); assert app.add_external_source(bad) is None and shown and len(app.state.external_sources()) == 1
# uma pasta já listada como backup automático também não duplica
bk = os.path.join(base, "antigravity-ide.bak"); sess(os.path.join(bk, "conversations"), B, 1)
app.refresh(); wait(app)
shown.clear(); r = app.add_external_source(bk); wait(app)
assert r and r.startswith("Backup/outros") and len(app.state.external_sources()) == 1, r
print("duplicadas ok")

# fonte automática (Backup/outros) segue como antes: não é somente leitura por esta regra
assert not app.source_readonly()

# pela entrada do seletor: o diálogo de pasta é aberto e o seletor volta para a fonte atual
filedialog.askdirectory = lambda *a, **k: flat
app.source_idx = 0
box = app.src_box
box.current(len(app.sources)); app.on_source_change(); wait(app)
assert app.sources[app.source_idx][0].startswith("Externa: ") and "solta" in app.sources[app.source_idx][0], app.sources[app.source_idx][0]
assert set(leaves()) == {D} and app.source_readonly() and box.current() == app.source_idx
assert app.state.external_sources() == [os.path.abspath(old), os.path.abspath(flat)]
# cancelar o diálogo: nada muda
filedialog.askdirectory = lambda *a, **k: ""
cur = app.source_idx; box.current(len(app.sources)); app.on_source_change(); wait(app)
assert app.source_idx == cur and box.current() == cur
print("seletor ok")
app.destroy()

# ---- persistência: reabrir o app traz as fontes ----
app = G.AntigravityGateApp(); wait(app)
labels = [s[0] for s in app.sources]
assert len(labels) == 4 and sum(l.startswith("Externa:") for l in labels) == 2 and sum(l.startswith("Backup/outros") for l in labels) == 1, labels
app.src_box.current(labels.index(next(l for l in labels if "solta" in l))); app.on_source_change(); wait(app)
assert set(leaves()) == {D}

# ---- pasta indisponível (HD desconectado): fica na lista, sem erro, com aviso claro ----
gone = flat + "_off"; os.rename(flat, gone)
app.refresh(); wait(app)
assert any("solta" in s[0] for s in app.sources) and app.source_readonly()
assert leaves() == {} and "indispon" in app.status.cget("text").lower(), app.status.cget("text")
app.update_actions()
assert not app.btn["approve"].enabled
os.rename(gone, flat)
app.refresh(); wait(app)
assert set(leaves()) == {D} and "indispon" not in app.status.cget("text").lower()
print("indisponível ok")

# ---- remover da lista: só tira da lista, nada é apagado ----
asked.clear(); answer["v"] = False
app.remove_external_source(); wait(app)
assert len(app.state.external_sources()) == 2 and asked, "recusar a confirmação não remove"
answer["v"] = True
app.remove_external_source(); wait(app)
assert app.state.external_sources() == [os.path.abspath(old)] and app.source_idx == 0 and not app.source_readonly()
assert os.path.isdir(flat) and digest(flat) == flat_before, "remover da lista não apaga arquivos"
assert not any("solta" in s[0] for s in app.sources)
shown.clear(); app.remove_external_source()  # fonte ativa selecionada: não há o que remover
assert len(app.state.external_sources()) == 1
app.destroy()

# ---- ações automáticas continuam valendo na fonte ativa ----
app = G.AntigravityGateApp(); wait(app)
assert app.source_idx == 0 and not app.source_readonly()
app.tree.selection_set([c for p in app.tree.get_children() for c in app.tree.get_children(p) if app.tree.item(c, "values")[7] == B][0]); app.update_actions()
for name in ("approve", "archive", "pending", "trash"):
    assert app.btn[name].enabled, name
app.mark_selected("arquivada"); assert app.states[B] == "arquivada"
app.destroy()
shutil.rmtree(root, ignore_errors=True)
print("TODOS OS TESTES DE FONTES EXTERNAS OK")
