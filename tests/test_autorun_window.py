import os, sys, json, sqlite3, tempfile, time, threading, glob
root = tempfile.mkdtemp(prefix="agyauto_")
base = os.path.join(root, "gemini"); local = os.path.join(root, "local")
os.environ.update(HOME=os.path.join(root, "home"), ANTIGRAVITY_HOME=base, LOCALAPPDATA=local)
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
ws = os.path.join(root, "meu projeto"); os.makedirs(ws)
import urllib.parse
ws_uri = "file://" + urllib.parse.quote(ws)
for i in range(1, 6):
    c = sqlite3.connect(os.path.join(conv, U(i) + ".db"))
    c.execute("CREATE TABLE steps (idx integer PRIMARY KEY, step_type integer, status integer, step_payload blob, error_details blob)")
    c.execute("INSERT INTO steps VALUES(0,14,3,?,NULL)", (fv(1, 14) + fl(5, fl(1, fv(1, 1792916000)) + fv(3, 4)) + fl(19, fs(2, "pedido da sessão %d" % i)),))
    c.execute("INSERT INTO steps VALUES(1,15,3,?,NULL)", (fv(1, 15) + fl(5, fl(1, fv(1, 1792916005)) + fv(3, 2)) + fl(20, fs(3, "resposta final %d" % i)),))
    c.commit(); c.close()
sc = sqlite3.connect(os.path.join(base, "antigravity", "conversation_summaries.db"))
sc.execute("CREATE TABLE conversation_summaries(conversation_id TEXT, title TEXT, preview TEXT, step_count INT, last_modified_time TEXT, project_id TEXT, workspace_uris TEXT, agent_name TEXT, parent_conversation_id TEXT)")
for i in range(1, 6): sc.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?,?,?)", (U(i), "", "sessao %d" % i, 2, "2026-10-26T1%d:00:00Z" % i, "", ws_uri, "", ""))
sc.commit(); sc.close()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G

def calls(): return [json.loads(l) for l in open(LOG)] if os.path.exists(LOG) else []
def reset(seq):
    if os.path.exists(LOG): os.remove(LOG)
    os.environ["AGY_FAKE_SEQ"] = seq
def items(ids):
    out = []
    for i in ids:
        out.append({'cid': U(i), 'title': "sessao %d" % i, 'fpath': os.path.join(conv, U(i) + ".db"),
                    'meta': {'cid': U(i), 'title': "sessao %d" % i, 'fpath': os.path.join(conv, U(i) + ".db"), 'status': 'aprovada'}, 'workspace': ws_uri})
    return out
def store(): return G.StateStore(os.path.join(root, "st_%d.db" % time.time_ns()))

# --- janela única do Auto-Run (1.2) ---------------------------------------------------------
from tkinter import messagebox, filedialog
info = []
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, _n=n, **k: info.append((_n, a)))
G.STATE_DB = os.path.join(root, "ui_state.db")
os.environ["AGY_EXE"] = FAKE
def wait(a, secs=30):
    end = time.time() + secs
    while (a.loading or a.autorunning) and time.time() < end: a.update(); time.sleep(0.01)
    a.update()

# 0. AutoRunner: um evento por sessão, com o que se sabe dela, e os dossiês na pasta pedida
custom0 = os.path.join(root, "dossies_runner"); events = []
reset("ok,quota,ok"); st0 = store()
runner = G.AutoRunner(items([1, 2, 3]), st0, lambda line: None, agy=FAKE, dry_run=False, dossier_dir=custom0, item_cb=lambda kind, cid, i: events.append((kind, cid, i)))
summary = runner.run()
assert [(k, c, i.get("state")) for k, c, i in events] == [("start", U(1), None), ("done", U(1), "ok"), ("start", U(2), None), ("done", U(2), "erro"), ("skipped", U(3), None)], events
ok = events[1][2]
assert ok["new_cid"].startswith("aaaaaaaa-0000") and ok["duration"] == 3.2 and ok["turns"] == 1 and ok["usage"]["total_tokens"] == 1320 and ok["model"] == "" and "Entendi o objetivo" in ok["response"]
assert ok["project"].startswith("CLI Project") and os.path.samefile(ok["cwd"], ws) and os.path.dirname(ok["dossier"]) == custom0, ok
assert "quota" in events[3][2]["error"] and summary["ok"] == 1 and summary["skipped"] == 1 and len(glob.glob(os.path.join(custom0, "retomada_*.md"))) == 2
rec = st0.handoff_record(U(1)); assert rec["cwd"] == ok["cwd"] and rec["turns"] == 1 and rec["response"].startswith("Entendi") and st0.handoff_record(U(2)) is None

# 1. etapa Preparar (janela real, dirigida pelo teste) e simulação com a pasta dos dossiês escolhida
app = G.AntigravityGateApp(); wait(app)
def iid(n): return next(i for i in app.iter_sessions() if app.cid_of(i) == U(n))
for n in (1, 2, 3): app.tree.selection_set(iid(n)); app.mark_selected("aprovada")
app.handoffs[U(1)] = "aaaaaaaa-0000"          # uma já retomada
custom = os.path.join(root, "meus dossies")
seen = {}
real_confirm = app.confirm_autorun
def drive(its, done):
    def act():
        w = app.confirm_win
        seen['same'], seen['step'], seen['title'] = app.auto_win[0] is w, w.step, w.title()
        seen['bg'] = {k: str(l.cget("bg")) for k, l in w.step_labels.items()}
        seen['rows'] = list(w.tree.get_children())
        seen['marks'] = [w.tree.set(c, "sel") for c in seen['rows']]
        seen['states'] = [w.tree.set(c, "state") for c in seen['rows']]
        seen['status'], seen['opts'], seen['buttons'] = w.status.cget("text"), bool(w.opts.winfo_manager()), (w.primary.text, w.secondary.text)
        w.tree.selection_set(U(2)); w.update(); seen['detail'] = w.detail.get("1.0", "end")
        w.checks[U(3)].set(False); seen['marks2'] = [w.tree.set(c, "sel") for c in seen['rows']]; seen['status2'] = w.status.cget("text")
        filedialog.askdirectory = lambda **k: custom
        w.choose_dir(); seen['dir'], seen['detail_dir'] = w.dir_var.get(), w.detail.get("1.0", "end")
        w.reset_dir(); seen['dir_reset'] = w.dir_var.get(); w.choose_dir()
        w.dry.set(True)
        w.go()
    app.after(300, act)
    return real_confirm(its, done)
app.confirm_autorun = drive
app.start_autorun(); wait(app)
w = app.auto_win[0]; t = app.t
assert seen['same'] and seen['step'] == "prepare" and seen['title'] == "Auto-Run — preparar"
assert seen['bg']['prepare'] == t['sel_bg'] and seen['bg']['run'] == t['panel'] and seen['bg']['done'] == t['panel'], seen['bg']
assert seen['rows'] == [U(1), U(2), U(3)] and seen['marks'] == ["☐", "☑", "☑"] and seen['states'] == ["já retomada", "pronta", "pronta"], seen
assert seen['status'] == "2 de 3 sessões marcadas" and seen['opts'] and seen['buttons'] == ("Iniciar", "Cancelar")
assert "Nova sessão em" in seen['detail'] and "meu projeto" in seen['detail'] and "CLI Project (sem --project)" in seen['detail'] and G.HANDOFF_DIR in seen['detail'], seen['detail']
assert seen['marks2'] == ["☐", "☑", "☐"] and seen['status2'] == "1 de 3 sessões marcadas"
assert seen['dir'] == custom and custom in seen['detail_dir'] and seen['dir_reset'] == G.HANDOFF_DIR
# depois do Iniciar: a MESMA janela vira Executando e termina no Resumo
assert app.auto_win[0] is w and w.step == "done" and w.title() == "Auto-Run — concluído", w.title()
assert (w.primary.text, w.secondary.text) == ("Fechar", "Salvar relatório…") and w.secondary.winfo_manager() and not w.opts.winfo_manager()
assert w.tree.get_children() == (U(2),) and w.tree.set(U(2), "state") == "▤ dossiê gerado" and w.tree.cget("displaycolumns") != ("sel", "state", "title", "where")
assert len(glob.glob(os.path.join(custom, "retomada_*.md"))) == 1, "dossiê na pasta escolhida"
assert w.status.cget("text") == "✔ 0 retomadas · ▤ 1 dossiê · ✖ 0 falhas · » 0 não executadas", w.status.cget("text")
assert custom in w.detail.get("1.0", "end") and not w.btn_receipt.winfo_manager(), "simulação não tem recibo"
assert "Fim." in app.auto_win[1].get("1.0", "end") and app.settings.get("dossier_dir") == custom
assert G.gate_owned(custom) and not G.gate_owned(ws), "a pasta escolhida é do app, não workspace de projeto"
# relatório
md = w.report_markdown()
assert md.startswith("# Relatório do Auto-Run") and "simulação" in md and custom in md and U(2) in md and "sessao 2" in md and U(3) not in md, md
out = os.path.join(root, "relatorio.md"); filedialog.asksaveasfilename = lambda **k: out
w.save_report(); body = open(out, encoding="utf-8").read(); assert body.startswith("# Relatório do Auto-Run") and U(2) in body
os.remove(out); filedialog.asksaveasfilename = lambda **k: ""; w.save_report(); assert not os.path.exists(out), "cancelar não grava"

# 2. nova rodada reaproveita a janela (uma só); X na etapa Preparar cancela e fecha
def drive_cancel(its, done):
    def act():
        c = app.confirm_win
        seen.update(same2=c is w, step2=c.step, rows2=list(c.tree.get_children()), cancel_btn=c.secondary.text)
        app.close_autorun(c)
    app.after(300, act)
    return real_confirm(its, done)
app.confirm_autorun = drive_cancel
app.start_autorun(); app.update()
assert seen['same2'] and seen['step2'] == "prepare" and len(seen['rows2']) == 3 and seen['cancel_btn'] == "Cancelar"
assert app.auto_win is None and not w.winfo_exists() and not app.autorunning and not app._confirming

# 3. retomada de verdade (agy simulado): ok, cota, não executada; detalhe por sessão, recibo e relatório
custom2 = os.path.join(root, "dossies_reais")
app.confirm_autorun = lambda its, done: {'dry_run': False, 'redo': True, 'model': '', 'cids': {U(1), U(2), U(3)}, 'dossier_dir': custom2}
reset("ok,quota,ok"); app.start_autorun(); wait(app)
w = app.auto_win[0]
assert w.step == "done" and w.title() == "Auto-Run — concluído com problemas" and [w.tree.set(c, "state") for c in w.tree.get_children()] == ["✔ retomada", "✖ falhou", "» não executada"]
assert w.status.cget("text").startswith("✔ 1 retomada · ▤ 0 dossiês · ✖ 1 falha · » 1 não executada") and "motivo: cota esgotada" in w.status.cget("text"), w.status.cget("text")
w.tree.selection_set(U(1)); w.update(); d1 = w.detail.get("1.0", "end")
assert "Sessão nova" in d1 and "aaaaaaaa-0000" in d1 and "Modelo" in d1 and "3,2 s" in d1 and "total 1.320" in d1 and "O que aconteceu" in d1 and "Resposta do agy" in d1 and "Entendi o objetivo" in d1, d1
assert w.btn_receipt.winfo_manager(), "sessão retomada tem o botão do recibo"
w.tree.selection_set(U(2)); w.update(); d2 = w.detail.get("1.0", "end")
assert "Motivo" in d2 and "quota" in d2.lower() and "Cota do modelo esgotada" in d2 and not w.btn_receipt.winfo_manager(), d2
w.tree.selection_set(U(3)); w.update(); assert "não executada" in w.detail.get("1.0", "end")
w.tree.selection_set(U(1)); w.update(); w.open_receipt(); app.update()
dialogs = [c for c in app.winfo_children() if isinstance(c, G.ReceiptDialog)]; assert len(dialogs) == 1 and U(1) in dialogs[0].text.get("1.0", "end"); dialogs[0].destroy()
rec = app.state.handoff_record(U(1)); assert rec["cwd"] and rec["model"] == "" and rec["project"].startswith("CLI Project") and os.path.dirname(rec["dossier_path"]) == custom2
md = w.report_markdown(); assert "retomada real" in md and "Cota esgotada" in md and "Entendi o objetivo" in md and "não executada" in md and md.count("## ") == 3, md
app.close_autorun(w); assert app.auto_win is None and not w.winfo_exists()
app.destroy(); print("TODOS OS TESTES DA JANELA DO AUTO-RUN OK")
