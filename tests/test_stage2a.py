import os, sys, types, json, sqlite3, tempfile, time, threading, glob
# Etapa 2a da revisão final: tabela (largura automática da coluna, Título à esquerda, duplo clique abre detalhes,
# exportação de uma sessão por vez) e dicas nos alertas.
root = tempfile.mkdtemp(prefix="agy2a_")
base = os.path.join(root, "gemini"); local = os.path.join(root, "local")
os.environ.update(HOME=os.path.join(root, "home"), ANTIGRAVITY_HOME=base, LOCALAPPDATA=local)
os.environ.pop("AGY_ROT_TOKENS", None)
FAKE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_agy.py")
LOG = os.path.join(root, "agy_calls.log"); os.environ["AGY_FAKE_LOG"] = LOG

def vi(n):
    o = bytearray()
    while True:
        b = n & 0x7f; n >>= 7
        if n: o.append(b | 0x80)
        else: o.append(b); return bytes(o)
fv = lambda f, v: vi(f << 3) + vi(v); fl = lambda f, b: vi(f << 3 | 2) + vi(len(b)) + b; fs = lambda f, s: fl(f, s.encode())
U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)
conv = os.path.join(base, "antigravity", "conversations"); os.makedirs(conv); os.makedirs(os.path.join(base, "config", "projects"))
for i in range(1, 4):
    c = sqlite3.connect(os.path.join(conv, U(i) + ".db"))
    c.execute("CREATE TABLE steps (idx integer PRIMARY KEY, step_type integer, status integer, step_payload blob, error_details blob)")
    c.execute("INSERT INTO steps VALUES(0,14,3,?,NULL)", (fv(1, 14) + fl(5, fl(1, fv(1, 1792916000)) + fv(3, 4)) + fl(19, fs(2, "pedido %d" % i)),))
    c.execute("INSERT INTO steps VALUES(1,15,3,?,NULL)", (fv(1, 15) + fl(5, fl(1, fv(1, 1792916005)) + fv(3, 2)) + fl(20, fs(3, "resposta %d" % i)),))
    c.commit(); c.close()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G
from tkinter import messagebox
os.environ["AGY_EXE"] = FAKE


def calls(): return [json.loads(l) for l in open(LOG)] if os.path.exists(LOG) else []
def reset(seq):
    if os.path.exists(LOG): os.remove(LOG)
    os.environ["AGY_FAKE_SEQ"] = seq
def items(ids):
    return [{'cid': U(i), 'title': "s%d" % i, 'fpath': os.path.join(conv, U(i) + ".db"),
             'meta': {'cid': U(i), 'title': "s%d" % i, 'fpath': os.path.join(conv, U(i) + ".db")}, 'workspace': ''} for i in ids]
def store(): return G.StateStore(os.path.join(root, "st_%d.db" % time.time_ns()))

def wait(a, secs=20):
    end = time.time() + secs
    while a.loading and time.time() < end: a.update(); time.sleep(0.01)
    a.update()
from tkinter import messagebox, filedialog
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, **k: None)
asked = []; filedialog.asksaveasfilename = lambda **k: (asked.append(k), "")[1]
app = G.AntigravityGateApp(); wait(app)
app.geometry("1300x760+0+0"); app.update()
sessions = list(app.iter_sessions())

# --- 1. Título logo depois de Projeto / Sessão
assert tuple(app.tree["displaycolumns"])[0] == "col_title", app.tree["displaycolumns"]

# --- 2. duplo clique no divisor do cabeçalho ajusta a largura da coluna ao conteúdo
app.tree.column("col_uuid", width=30); app.tree.column("col_title", width=30)
app.autofit_column("col_uuid")
need = app.f_ui.measure(U(1))
assert need <= app.tree.column("col_uuid", "width") <= need + app.px(40), (need, app.tree.column("col_uuid", "width"))
app.tree.identify_region = lambda x, y: "separator"
edge = next(r for c, l, r in app.cell_tips.edges() if c == "col_title")   # borda direita do Título
app.on_double_click(types.SimpleNamespace(x=edge + 1, y=5))
assert app.tree.column("col_title", "width") > 30
del app.tree.identify_region
app.autofit_column("#0"); assert app.tree.column("#0", "width") >= app.f_ui.measure(app.tree.item(sessions[0], "text"))

# --- 3. duplo clique numa sessão abre os detalhes (sem "Salvar como")
app.settings["details"] = False; app.apply_details_visibility()
app.tree.item(app.tree.get_children()[0], open=True); app.update()
y = app.tree.bbox(sessions[0])[1] + 5
app.on_double_click(types.SimpleNamespace(x=300, y=y)); app.update()
assert not asked and app.settings["details"] is True and app.details_body.winfo_manager(), "detalhes abertos"
assert app.tree.selection() == (sessions[0],)

# --- 4. várias sessões selecionadas: exportar fica desabilitado com motivo
app.tree.selection_set(sessions[:2]); app.update()
for b in ("export", "dossier", "d_export", "d_dossier"):
    assert not app.btn[b].enabled and "uma sessão" in app.btn[b].reason, (b, app.btn[b].reason)
app.tree.selection_set(sessions[:1]); app.update(); assert app.btn["export"].enabled

# --- 5. dicas nos alertas (tabela e painel)
row = dict(cid=U(1), ctx=129032, failures=35, title="t", workspace="c:\\x", ws_ok=False, running=False, killed=False)
tip = app.cell_tip(row, "col_ctx")
assert "129.032 tokens" in tip and "normal" in tip and "150k" in tip and "250k" in tip, tip
assert "atenção" in app.cell_tip(dict(row, ctx=160000), "col_ctx") and "Dossiê" in app.cell_tip(dict(row, ctx=160000), "col_ctx")
assert "crítico" in app.cell_tip(dict(row, ctx=300000), "col_ctx") and "sessão nova" in app.cell_tip(dict(row, ctx=300000), "col_ctx")
tip = app.cell_tip(row, "col_fail")
assert "35" in tip and "Exportar diálogo" in tip and "Falhas de ferramenta" in tip, tip
assert app.cell_tip(dict(row, failures=0), "col_fail") == ""
app.handoffs[U(1)] = "0b49637d-35c2"
assert "0b49637d" in app.cell_tip(row, "#0") and "Auto-Run" in app.cell_tip(row, "#0")
assert "não existe" in app.cell_tip(row, "ws") and "✖ c:\\x" in app.cell_tip(row, "ws")
two = dict(row, workspace=root + ", c:\\sumiu")
tip = app.cell_tip(two, "ws")
assert "1 de 2" in tip and ("✔ " + root) in tip and "✖ c:\\sumiu" in tip, tip
long_title = "Verifica as alterações recentes nos ficheiros do projeto e resume tudo"
assert app.cell_tip(dict(row, title=long_title), "col_title") == long_title
assert app.cell_tip(dict(row, title="curto"), "col_title") == ""

# dica aparece sobre a célula ao passar o mouse
r1 = app.row_by_cid[app.cid_of(sessions[0])]
r1['failures'] = 7; app.populate(); app.update()
sid = next(i for i in app.iter_sessions() if app.cid_of(i) == r1['cid'])
app.tree.see(sid); app.update()
x, y, w, h = app.tree.bbox(sid, "col_fail")
assert app.cell_tips.column_at(x + 3) == "col_fail" and app.cell_tips.column_at(app.tree.bbox(sid, "col_title")[0] + 3) == "col_title"
app.cell_tips.on_motion(types.SimpleNamespace(x=x + 3, y=y + 3)); app.cell_tips.show_now(); app.update()
assert app.cell_tips.tip is not None and "7" in app.cell_tips.text, app.cell_tips.text
app.cell_tips.on_motion(types.SimpleNamespace(x=x + 3, y=9000)); assert app.cell_tips.tip is None
# painel de detalhes: falhas e workspace com dica
app.tree.selection_set(sid); app.update()
r1.update(workspace="c:\\sumiu", ws_ok=False)
assert "7" in app.fact_tips["fails"].fn() and "não existe" in app.fact_tips["ws"].fn()
app.destroy()
print("TODOS OS TESTES DA ETAPA 2A OK")
