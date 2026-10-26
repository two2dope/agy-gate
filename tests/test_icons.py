import os, sys, sqlite3, tempfile, time, zlib, struct, base64
root = tempfile.mkdtemp(prefix="agyicon_")
base = os.path.join(root, "gemini")
os.environ.update(HOME=os.path.join(root, "home"), ANTIGRAVITY_HOME=base, LOCALAPPDATA=os.path.join(root, "local"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G

def decode(png):
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, ihdr = 8, b"", None
    while pos < len(png):
        n, tag = struct.unpack(">I4s", png[pos:pos + 8]); data = png[pos + 8:pos + 8 + n]
        assert struct.unpack(">I", png[pos + 8 + n:pos + 12 + n])[0] == zlib.crc32(tag + data) & 0xFFFFFFFF, "CRC do chunk"
        if tag == b"IHDR": ihdr = struct.unpack(">IIBBBBB", data)
        if tag == b"IDAT": idat += data
        pos += 12 + n
    w, h, depth, ctype = ihdr[:4]
    assert (depth, ctype) == (8, 6)
    raw = zlib.decompress(idat); stride = 1 + w * 4
    assert len(raw) == h * stride
    return w, h, [[tuple(raw[y * stride + 1 + x * 4: y * stride + 5 + x * 4]) for x in range(w)] for y in range(h)]

# 1. todo ícone em todo tema: PNG válido, centro opaco, cantos transparentes, bordas suavizadas
names = ["pending", "approved", "ok", "archived", "folder", "warn", "error", "info", "sub"]
for key, th in G.THEMES.items():
    t = dict(th)
    for name in names:
        for handoff in (False, True):
            w, h, px = decode(G.render_icon(G.icon_layers(name, t, handoff), 16))
            assert (w, h) == (16, 16)
            assert px[0][0][3] == 0 and px[15][0][3] == 0, (key, name, "canto deve ser transparente")
            alphas = [p[3] for row in px for p in row]
            assert max(alphas) == 255 and 0 < sum(1 for a in alphas if 0 < a < 255), (key, name, "precisa de pixels opacos e suavizados")
            assert sum(1 for a in alphas if a) > 14, (key, name, "ícone não pode ser vazio")
# 2. cores: aprovada é verde do tema; pendente usa o destaque; arquivada é o tom neutro
def dominant(name, key):
    t = dict(G.THEMES[key]); _, _, px = decode(G.render_icon(G.icon_layers(name, t), 16))
    from collections import Counter
    c = Counter(p[:3] for row in px for p in row if p[3] == 255)
    return "#%02x%02x%02x" % c.most_common(1)[0][0]
for key in G.THEMES:
    assert dominant("approved", key) == G.THEMES[key]['success'], key
    assert dominant("pending", key) == G.THEMES[key]['accent_text'], key
    assert dominant("archived", key) == G.THEMES[key]['muted'], key
# 3. tamanho em dpi alto: mesmo desenho em 24 px
w, h, _ = decode(G.render_icon(G.icon_layers("approved", dict(G.THEMES["escuro"])), 24)); assert (w, h) == (24, 24)
# 4. selo de retomada muda o desenho
a = G.render_icon(G.icon_layers("approved", dict(G.THEMES["escuro"]), False), 16); b = G.render_icon(G.icon_layers("approved", dict(G.THEMES["escuro"]), True), 16)
assert a != b

# 5. na tela: imagens nas linhas, selo de retomada, troca de tema refaz as imagens
U = lambda n: "%08x-0000-0000-0000-%012x" % (n, n)
ant = os.path.join(base, "antigravity"); conv = os.path.join(ant, "conversations"); os.makedirs(conv); os.makedirs(os.path.join(base, "config", "projects"))
c = sqlite3.connect(os.path.join(ant, "conversation_summaries.db"))
c.execute("CREATE TABLE conversation_summaries(conversation_id TEXT, title TEXT, preview TEXT, step_count INT, last_modified_time TEXT, project_id TEXT, workspace_uris TEXT, agent_name TEXT, parent_conversation_id TEXT)")
for i in range(1, 4): c.execute("INSERT INTO conversation_summaries VALUES(?,?,?,?,?,?,?,?,?)", (U(i), "", "sessao %d" % i, i, "2026-10-26T1%d:00:00Z" % i, "", "", "", ""))
c.commit(); c.close()
for i in range(1, 4):
    d = sqlite3.connect(os.path.join(conv, U(i) + ".db")); d.execute("CREATE TABLE steps(idx INTEGER PRIMARY KEY, step_type INT, status INT, step_payload BLOB, error_details BLOB)")
    d.execute("INSERT INTO steps VALUES(0,132,7,NULL,NULL)"); d.execute("INSERT INTO steps VALUES(1,132,3,NULL,NULL)"); d.commit(); d.close()
from tkinter import messagebox
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, **k: None)
messagebox.askyesno = lambda *a, **k: True
def wait(a):
    end = time.time() + 20
    while a.loading and time.time() < end: a.update(); time.sleep(0.01)
    for _ in range(6): a.update(); time.sleep(0.02)
app = G.AntigravityGateApp(); app.geometry("1240x720+0+0"); wait(app)
iid = lambda n: next(i for i in app.iter_sessions() if app.cid_of(i) == U(n))
def img(i):
    v = app.tree.item(i, "image")
    return v[0] if isinstance(v, (tuple, list)) and v else v
proj = app.tree.get_children()[0]
assert img(proj) and img(iid(1)), "projeto e sessão têm imagem"
assert str(img(iid(1))) == str(app.icon("pending"))
app.tree.selection_set(iid(1)); app.mark_selected("aprovada"); app.update()
assert str(img(iid(1))) == str(app.icon("approved")) and str(img(iid(2))) == str(app.icon("pending"))
app.tree.selection_set(iid(2)); app.mark_selected("arquivada"); assert str(img(iid(2))) == str(app.icon("archived"))
app.handoffs[U(1)] = "aaaaaaaa-0000"; app.refresh_labels(); assert str(img(iid(1))) == str(app.icon("approved", True)) and app.icon("approved", True) is not app.icon("approved")
before = str(img(iid(3))); app.set_theme("cyber"); app.update()
after = str(img(iid(3))); assert before != after, "troca de tema gera ícones novos"
assert app.icon("pending").width() == app.px(16) and app.icon("pending").height() == app.px(16), "tamanho segue o DPI"
# 6. coluna de falhas: conta passos de ferramenta (tipo 132) com status diferente de 3
v = app.tree.item(iid(1), "values"); assert v[4] == "⚠ 1" and v[7] == U(1), v
assert G.HEADINGS["col_fail"] == "Falhas" and app.tree.heading("col_fail", "text") == "Falhas"
app.sort_by("col_fail"); app.update()
app.destroy(); print("TODOS OS TESTES DE ICONES OK")
