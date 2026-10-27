import os, sys, json, sqlite3, tempfile, time, threading, glob
# Segunda rodada de teste no Windows (26/10): monitor da janela, X do Auto-Run, modelos recusados,
# sessões criadas por tentativas com erro e selos do rodapé como filtros.
root = tempfile.mkdtemp(prefix="agyr3_")
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

os.environ["AGY_FAKE_CONV"] = conv
def wait(a, secs=20):
    end = time.time() + secs
    while (a.loading or a.autorunning) and time.time() < end: a.update(); time.sleep(0.01)
    a.update()

# --- 1. janela maximizada num monitor à esquerda do principal reabre nele
left, primary = (-1920, 0, 1920, 1040), (0, 0, 1366, 728)
work_at = lambda x, y: left if (x is not None and x < 0) else primary
w, h, x, y = G.window_geometry(work_at, 1.0, {"w": 1240, "h": 820, "x": 100, "y": 50, "zoomed": True, "zx": -960, "zy": 520})
assert -1920 <= x and x + w <= 0, (w, h, x, y)
assert G.saved_zoomed({"zoomed": True, "zx": -960, "zy": 520}) and not G.saved_zoomed({"zoomed": False}) and not G.saved_zoomed(None)
w, h, x, y = G.window_geometry(work_at, 1.0, {"w": 1000, "h": 700, "x": -1500, "y": 100, "zoomed": True, "zx": -960, "zy": 520})
assert (x, y) == (-1500, 100), "posição normal salva no mesmo monitor é mantida"

app = G.AntigravityGateApp(); wait(app)
real_state = app.wm_state
app.wm_state = lambda *a: "zoomed"; app.save_window()
win = G.load_settings()["window"]
assert win["zoomed"] is True and isinstance(win["zx"], int) and isinstance(win["zy"], int), win
app.wm_state = real_state; app.save_window()
assert G.load_settings()["window"]["zoomed"] is False
app.destroy()
s = G.load_settings(); s["window"].update(zoomed=True, zx=200, zy=200); G.save_settings(s)
app = G.AntigravityGateApp(); wait(app)
assert app.start_zoomed, "maximizada ao fechar: reabre maximizada"

# --- 1b. coordenadas negativas no texto da geometria (o Windows informa "+-1928" no monitor à esquerda)
assert G.parse_geometry("1920x1017+-1928+-8") == (1920, 1017, -1928, -8)
assert G.parse_geometry("900x600+40+30") == (900, 600, 40, 30)
assert G.parse_geometry("900x600-10+30") is None, "'-N' conta da borda direita: não é posição absoluta"
assert G.parse_geometry("lixo") is None
real_geo, real_state = app.geometry, app.wm_state
app.wm_state = lambda *a: "zoomed"; app.geometry = lambda *a: "1920x1017+-1928+-8" if not a else real_geo(*a)
app.save_window(); win = G.load_settings()["window"]
assert win["zoomed"] is True and (win["zx"], win["zy"]) == (-968, 500), win
app.wm_state = lambda *a: "normal"; app.geometry = lambda *a: "900x600+-1500+40" if not a else real_geo(*a)
app.save_window(); win = G.load_settings()["window"]
assert (win["x"], win["y"], win["zoomed"]) == (-1500, 40, False), win
app.wm_state = real_state; app.geometry = real_geo

# --- 1c. número da montagem aparece no Sobre e no diagnóstico
assert G.__build__ and G.__build__ in G.about_info()

# --- 2. X da janela do Auto-Run = botão Cancelar/Fechar
from tkinter import messagebox
shown = []
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, **k: shown.append(a))
messagebox.askyesno = lambda *a, **k: True
for i in app.iter_sessions(): app.tree.selection_add(i)
app.mark_selected("aprovada")
os.environ["AGY_EXE"] = FAKE
app.confirm_autorun = lambda its, done: {'dry_run': False, 'redo': True, 'model': ''}
reset("hang"); app.start_autorun()
end = time.time() + 10
while not calls() and time.time() < end: app.update(); time.sleep(0.05)
win = app.auto_win[0]
shown.clear(); win.protocol("WM_DELETE_WINDOW")  # existe
app.tk.call(win.protocol("WM_DELETE_WINDOW")); app.update()
assert not shown and app.runner.cancelled, "X durante o lote cancela, sem aviso"
wait(app, 20); assert not app.autorunning
app.tk.call(win.protocol("WM_DELETE_WINDOW")); app.update()
assert app.auto_win is None and not win.winfo_exists(), "X depois do Fim fecha"

# --- 3. modelo recusado sai da lista; erro numa linha no log
app.settings["agy_models"] = ["Gemini 3.8 Flash", "Gemini 3.8 Flash (Medium)"]; app.settings["agy_model"] = "Gemini 3.8 Flash"
st = store(); logs = []
reset("badmodel")
res = G.AutoRunner(items([1]), st, logs.append, agy=FAKE, dry_run=False, model="Gemini 3.8 Flash").run()
assert res['bad_model'] == "Gemini 3.8 Flash", res
err_lines = [l for l in logs if "✖" in l]
assert err_lines and "Available models" not in err_lines[0] and "\n" not in err_lines[0], err_lines
app.on_auto_event('auto_done', res)
s = G.load_settings()
assert "Gemini 3.8 Flash" not in s["agy_models"] and s["agy_model"] == "" and app.agy_model_choices()[0].endswith(")"), s
assert "Gemini 3.8 Flash" not in app.agy_model_choices()

# --- 4. sessão criada por tentativa com erro é arquivada; sucesso com sub-agente não arquiva nada
st = store(); reset("badmodel_creates")
res = G.AutoRunner(items([1]), st, [].append, agy=FAKE, dry_run=False, model="X").run()
junk = "bbbbbbbb-0000-0000-0000-000000000001"
assert junk in res['junk'] and st.load().get(junk) == "arquivada", (res, st.load())
st = store(); reset("ok_with_sub")
res = G.AutoRunner(items([1]), st, [].append, agy=FAKE, dry_run=False).run()
assert res['ok'] == 1 and res['junk'] == [] and st.load() == {}, (res, st.load())

# --- 5. selos do rodapé filtram a tabela; clicar de novo mostra tudo
app.refresh(); wait(app)
total = len(list(app.iter_sessions()))
app.state.set_many([U(1)], "arquivada"); app.states = app.state.load(); app.populate()
app.chips["arquivada"].event_generate("<Button-1>"); app.update()
shown_ids = [app.cid_of(i) for i in app.iter_sessions()]
assert U(1) in shown_ids and all(app.states.get(c) == "arquivada" for c in shown_ids), shown_ids
assert app.chip_filter == "arquivada" and "arquivadas" in app.status.cget("text")
assert app.chips["pendente"].cget("text").split()[1] != "0", "os outros selos continuam contando tudo"
app.chips["arquivada"].event_generate("<Button-1>"); app.update()
assert app.chip_filter is None and len(list(app.iter_sessions())) == total
app.chips["pendente"].focus_set(); app.chips["pendente"].event_generate("<Return>"); app.update()
assert app.chip_filter == "pendente" and U(1) not in [app.cid_of(i) for i in app.iter_sessions()]
app.search_var.set("s"); app.run_search(); assert app.chip_filter is None, "busca desliga o filtro do selo"
app.destroy()
# --- 6. dica não sai da janela (Sobre fica no canto direito)
win, area = (0, 0, 1366, 728), (0, 0, 1920, 1040)
assert G.tooltip_pos(win, area, 1320, 40, 34, 34, 200, 30) == (1366 - 200, 80), "encosta na borda direita da janela"
assert G.tooltip_pos(win, area, 100, 40, 34, 34, 200, 30) == (100, 80), "longe da borda: alinhada ao botão"
assert G.tooltip_pos(win, area, 100, 700, 34, 20, 200, 30) == (100, 700 - 30 - 6), "sem espaço embaixo: acima do botão"
assert G.tooltip_pos((-1920, 0, 1920, 1040), (-1920, 0, 1920, 1040), -40, 40, 34, 34, 200, 30)[0] == -200, "monitor à esquerda"
app = G.AntigravityGateApp(); wait(app)
app.geometry("1000x600+0+0"); app.update(); app._fit_all(); app.update()
b = app.btn["about"]
tip = G.Tooltip(b, app, lambda: "Sobre: versão, autor e diagnóstico (F1)")
tip._show(); app.update()
right = app.winfo_rootx() + app.winfo_width()
assert tip.tip.winfo_rootx() + tip.tip.winfo_width() <= right, (tip.tip.winfo_rootx(), tip.tip.winfo_width(), right)
tip._leave(); app.destroy()
print("TODOS OS TESTES DA RODADA 3 OK")
