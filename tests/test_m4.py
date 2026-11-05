import os, sys, sqlite3, tempfile, time, json
root = tempfile.mkdtemp(prefix="agym4_")
base = os.path.join(root, "gemini"); local = os.path.join(root, "local")
os.environ.update(HOME=os.path.join(root, "home"), ANTIGRAVITY_HOME=base, LOCALAPPDATA=local)

def vi(n):
    o = bytearray()
    while True:
        b = n & 0x7f; n >>= 7
        if n: o.append(b | 0x80)
        else: o.append(b); return bytes(o)
fv = lambda f, v: vi(f << 3) + vi(v)
fl = lambda f, b: vi(f << 3 | 2) + vi(len(b)) + b
fs = lambda f, s: fl(f, s.encode())
ts = lambda sec, org: fl(5, fl(1, fv(1, sec) + fv(2, 5)) + fv(3, org))
T0 = 1792916000

def user(sec, text, skill=None):
    body = fs(2, text)
    if skill: body += fl(3, fl(2, fl(27, fl(1, fs(1, skill)))))
    return 14, 3, fv(1, 14) + fl(5, fl(1, fv(1, sec) + fv(2, 5)) + fv(3, 4)) + fl(19, body), None
def model(sec, text, calls=(), f2=None, f5=None):
    f9 = (fl(9, fv(1, 1318) + fv(2, f2) + (fv(5, f5) if f5 else b"")) if f2 is not None else b"")
    body = fs(1, text) + fs(3, "raciocínio: " + text) + fs(8, text) + b"".join(fl(7, fs(1, cid) + fs(2, name) + fs(3, args)) for cid, name, args in calls)
    return 15, 3, fv(1, 15) + fl(5, fl(1, fv(1, sec) + fv(2, 5)) + fv(3, 2) + f9) + fl(20, body), None
def tool(sec, name, args, result, status=3, err=None):
    p = fv(1, 132) + fl(5, fl(1, fv(1, sec) + fv(2, 5)) + fv(3, 2) + fl(4, fs(1, "call_1") + fs(2, name) + fs(3, args))) + fl(140, fl(2, fs(1, result)))
    return 132, status, p, (fl(2, fs(1, err)) if err else None)
def syshook(sec, text): return 101, 3, fv(1, 101) + fl(5, fl(1, fv(1, sec) + fv(2, 5)) + fv(3, 6)) + fl(114, fs(1, text) + fs(3, "hook_json_SessionStart")), None
def agentmsg(sec, label, text): return 101, 3, fv(1, 101) + fl(5, fl(1, fv(1, sec) + fv(2, 5)) + fv(3, 5)) + fl(114, fs(1, "[Message] x") + fl(2, fs(1, label) + fl(10, fs(1, text))) + fs(3, "agent_message")), None
def marker(sec): return 90, 3, fv(1, 90) + fl(5, fl(1, fv(1, sec) + fv(2, 5)) + fv(3, 5)) + fl(103, b""), None

KEY = "AIza" + "A" * 35
steps = [
    syshook(T0, "O hook injetou esta mensagem"),
    user(T0 + 1, "/gdrive lista meus 10 ultimos arquivos\ne o que mais houver", skill="gdrive"),
    marker(T0 + 2),
    model(T0 + 3, "Vou ler a skill.", [("c1", "read_file", json.dumps({"Path": "C:\\Users\\Thomáz\\.gemini\\skill.md"}))], f2=3000, f5=100000),
    tool(T0 + 4, "read_file", json.dumps({"Path": "C:\\Users\\Thomáz\\.gemini\\skill.md"}), "conteúdo da skill\n```py\nprint(1)\n```\nchave " + KEY),
    model(T0 + 5, "Agora edito o arquivo.", [("c2", "replace_file_content", json.dumps({"TargetFile": "C:\\proj\\a.py"}))], f2=3500, f5=104000),
    tool(T0 + 6, "replace_file_content", json.dumps({"TargetFile": "C:\\proj\\a.py", "x": 1}), "ok"),
    tool(T0 + 7, "run_command", json.dumps({"CommandLine": "pytest -q"}), "1 failed", status=7, err="AssertionError: esperado 2, veio 3"),
    agentmsg(T0 + 8, "Message from Parent Agent", "Acesse a URL https://exemplo.test/x"),
    (17, 3, fv(1, 17) + fl(5, fl(1, fv(1, T0 + 9)) + fv(3, 5)), None),
    user(T0 + 100, "agora rode de novo com password=hunter2abc"),
    tool(T0 + 101, "run_command", json.dumps({"CommandLine": "pytest -q"}), "ok", status=3),
    model(T0 + 102, "Tudo passou. Resumo final aqui.", f2=4000, f5=108000),
]
conv = os.path.join(base, "antigravity", "conversations"); os.makedirs(conv); os.makedirs(os.path.join(base, "config", "projects"))
CID = "0000000a-0000-0000-0000-00000000000a"
db = os.path.join(conv, CID + ".db")
c = sqlite3.connect(db)
c.execute("CREATE TABLE steps (idx integer PRIMARY KEY, step_type integer, status integer, step_payload blob, error_details blob)")
c.execute("CREATE TABLE gen_metadata (idx integer PRIMARY KEY, data blob)")
for i, (t, st, p, e) in enumerate(steps): c.execute("INSERT INTO steps VALUES(?,?,?,?,?)", (i, t, st, p, e))
c.execute("INSERT INTO gen_metadata VALUES(0,?)", (fs(21, "Gemini 3.8 Flash (High)"),))
c.commit(); c.close()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G

meta = {'cid': CID, 'title': "Teste de export", 'project': "Proj", 'workspace': "file:///c:/proj", 'agent': "DeepCoder", 'parent': "",
        'status': "aprovada", 'source': "Ativas", 'fpath': db}
out_full, out_doss = os.path.join(root, "full.md"), os.path.join(root, "doss.md")
prog = []
G.export_session('full', db, meta, out_full, progress=lambda n, t: prog.append((n, t)))
G.export_session('dossier', db, meta, out_doss)
full, doss = open(out_full, encoding="utf-8").read(), open(out_doss, encoding="utf-8").read()

# ---- diálogo completo: ordem, papéis, conteúdo, marcador omitido, tipo 17 honesto
order = [full.index(x) for x in ("#0 ·", "#1 ·", "#3 ·", "#4 ·", "#5 ·", "#6 ·", "#7 ·", "#8 ·", "#9 ·", "#10 ·", "#11 ·", "#12 ·")]
assert order == sorted(order), "passos fora de ordem"
assert "#2 ·" not in full, "marcador (tipo 90) não deve aparecer"
assert "👤 Usuário" in full and "🤖 Modelo" in full and "🛠 Ferramenta" in full and "⚙ Sistema" in full and "📨 Mensagem de agente" in full
assert "/gdrive lista meus 10 ultimos arquivos\ne o que mais houver" in full and "_Skill invocada: gdrive_" in full
assert "Chamada de ferramenta `read_file`" in full and "`read_file` · ok" in full and "⚠ status 7" in full
assert "AssertionError: esperado 2, veio 3" in full and "Message from Parent Agent" in full and "Acesse a URL https://exemplo.test/x" in full
assert "Passo de tipo 17 não interpretado" in full
assert "Gemini 3.8 Flash (High)" in full and "112000 tokens" in full and "| Passos | 13 |" in full
assert "````" in full, "texto com ``` dentro precisa de cerca maior"
assert KEY not in full and "hunter2abc" not in full and "[REDACTED]" in full, "diálogo completo sai mascarado por padrão (1.5.0, R4)"
assert "foram mascarados como [REDACTED]" in full
out_raw = os.path.join(root, "full_raw.md"); G.export_session('full', db, meta, out_raw, mask=False)
raw = open(out_raw, encoding="utf-8").read()
assert KEY in raw and "hunter2abc" in raw and "Exportado SEM máscara" in raw, "sem máscara só quando pedido"
assert G.redact("chave AQ." + "Ab3_-" * 8 + " fim") == "chave [REDACTED] fim", "R3: chave AQ.…"
assert G.redact("AQ.curta") == "AQ.curta"
assert prog == [] or prog[-1][1] == 13
# horário local no formato esperado
from datetime import datetime
assert datetime.fromtimestamp(T0 + 1).strftime('%d/%m %H:%M:%S') in full

# ---- dossiê: seções, agregação, mascaramento
for sec in ("## Origem", "## Pedidos do usuário (2)", "## Última resposta do modelo", "## Arquivos alterados (1)", "## Arquivos consultados (1)",
            "## Comandos executados", "## Falhas de ferramenta (últimas 1 de 1)", "## Tarefa recebida do agente pai", "## Ferramentas usadas", "## Instrução para quem retomar"):
    assert sec in doss or sec.replace(" (1)", " (2)") in doss or sec.split(" (")[0] in doss, sec
assert "Tudo passou. Resumo final aqui." in doss
assert "`C:\\proj\\a.py`" in doss and "skill.md" in doss and "`pytest -q`" in doss
assert "(status 7): AssertionError: esperado 2, veio 3" in doss, "resumo do erro sem prefixo de protobuf"
assert "/gdrive lista meus 10 ultimos arquivos" in doss and "skill: gdrive" in doss
assert "Acesse a URL https://exemplo.test/x" in doss                     # tarefa do agente pai
assert KEY not in doss and "hunter2abc" not in doss and "[REDACTED]" in doss, "dossiê precisa mascarar segredos"
assert "O hook injetou" not in doss, "hook de sistema fora do dossiê"
assert "nenhum modelo foi usado" in doss
assert len(doss) < len(full) * 1.5
open(os.path.join(root, 'ex_full.md'), 'w', encoding='utf-8').write(full); open(os.path.join(root, 'ex_doss.md'), 'w', encoding='utf-8').write(doss)
print("tamanhos: completo=%d dossiê=%d" % (len(full), len(doss)))

# ---- redact isolado
assert G.redact("Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123") == "Authorization: [REDACTED]"
assert G.redact("api_key = 'abcdef123456'") == "api_key = '[REDACTED]'" or "[REDACTED]" in G.redact("api_key = 'abcdef123456'")
assert G.redact("sem segredo aqui") == "sem segredo aqui"
assert "[REDACTED]" in G.redact("-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----")

# ---- truncamento
big = G.clip("x" * 7000, 6000); assert big.endswith("[… 1000 caracteres omitidos]")

# ---- esquema inválido não vira exceção solta no app (testado pela UI abaixo)
import tkinter
from tkinter import messagebox, filedialog
info = []
for n in ("showinfo", "showwarning", "showerror"): setattr(messagebox, n, lambda *a, _n=n, **k: info.append((_n, a)))
G.setup_logging()
def wait(a):
    end = time.time() + 30
    while (a.loading or a.exporting) and time.time() < end: a.update(); time.sleep(0.01)
    a.update()
app = G.AntigravityGate = None
app = G.AntigravityGateApp(); wait(app)
leaf = next(app.iter_sessions())
# cancelar o diálogo não exporta
filedialog.asksaveasfilename = lambda *a, **k: ""
app.tree.selection_set(leaf); app.start_export('full'); assert not app.exporting
# exportar pela UI, completo e dossiê
dest = os.path.join(root, "ui.md"); filedialog.asksaveasfilename = lambda *a, **k: dest
app.start_export('dossier'); assert app.exporting; info.clear()
app.start_export('full'); assert info and "em andamento" in info[0][1][1]       # segunda exportação simultânea é barrada
info.clear()
wait(app); assert not app.exporting and not any(m[0] == "showinfo" for m in info), "sucesso não abre mais janela de OK"
assert app.toast_log[-1] == ("ok", "Salvo: ui.md", ["Abrir arquivo", "Abrir pasta"]), app.toast_log[-1]
assert "## Instrução para quem retomar" in open(dest, encoding="utf-8").read()
app.start_export('full'); wait(app); assert "# Diálogo completo" in open(dest, encoding="utf-8").read()
# pasta de projeto não exporta
app.tree.selection_set(app.tree.get_children()[0]); info.clear(); app.start_export('full'); assert info and "Clique numa conversa" in info[0][1][1]
# destino inválido vira erro visível
filedialog.asksaveasfilename = lambda *a, **k: "/proc/nao_pode/x.md"
app.tree.selection_set(leaf); info.clear(); app.start_export('full'); wait(app)
assert not app.exporting and info[-1][0] == "showerror"
app.destroy(); print("TODOS OS TESTES M4 OK")
