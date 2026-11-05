"""1.2.2: resposta visível x raciocínio interno, nome do modelo, artefatos da sessão e arquivos temporários no dossiê."""
import os, sys, sqlite3, tempfile, json
root = tempfile.mkdtemp(prefix="agydf_")
base = os.path.join(root, "gemini")
os.environ.update(HOME=os.path.join(root, "home"), ANTIGRAVITY_HOME=base, LOCALAPPDATA=os.path.join(root, "local"))

def vi(n):
    o = bytearray()
    while True:
        b = n & 0x7f; n >>= 7
        if n: o.append(b | 0x80)
        else: o.append(b); return bytes(o)
fv = lambda f, v: vi(f << 3) + vi(v)
fl = lambda f, b: vi(f << 3 | 2) + vi(len(b)) + b
fs = lambda f, s: fl(f, s.encode())
T0 = 1792916000
head = lambda sec, t: fv(1, t) + fl(5, fl(1, fv(1, sec) + fv(2, 5)) + fv(3, 2))

def model(sec, text="", thinking="", calls=()):
    """Formato real (conferido em 05/11): f20.1 resposta visível, f20.3 raciocínio, f20.8 cópia da resposta."""
    body = (fs(1, text) if text else b"") + (fs(3, thinking) if thinking else b"") + (fs(8, text) if text else b"")
    body += b"".join(fl(7, fs(1, c) + fs(2, n) + fs(3, a)) for c, n, a in calls)
    return 15, 3, head(sec, 15) + fl(20, body), None
def user(sec, text): return 14, 3, head(sec, 14) + fl(19, fs(2, text)), None
def tool(sec, name, args):
    return 132, 3, fv(1, 132) + fl(5, fl(1, fv(1, sec) + fv(2, 5)) + fv(3, 2) + fl(4, fs(1, "c") + fs(2, name) + fs(3, args))) + fl(140, fl(2, fs(1, "ok"))), None

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G

conv = os.path.join(base, "antigravity", "conversations"); os.makedirs(conv)

def make(cid, steps, gen_rows):
    db = os.path.join(conv, cid + ".db")
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE steps (idx integer PRIMARY KEY, step_type integer, status integer, step_payload blob, error_details blob)")
    c.execute("CREATE TABLE gen_metadata (idx integer PRIMARY KEY, data blob, size integer)")
    for i, (t, st, p, e) in enumerate(steps): c.execute("INSERT INTO steps VALUES(?,?,?,?,?)", (i, t, st, p, e))
    for i, blob in enumerate(gen_rows): c.execute("INSERT INTO gen_metadata VALUES(?,?,0)", (i, blob))
    c.commit(); c.close()
    return db

def dossier(cid, db):
    out = os.path.join(root, cid[:8] + ".md")
    G.export_session('dossier', db, {'cid': cid, 'title': "t", 'fpath': db}, out)
    return open(out, encoding="utf-8").read()

def full(cid, db):
    out = os.path.join(root, cid[:8] + "_full.md")
    G.export_session('full', db, {'cid': cid, 'title': "t", 'fpath': db}, out)
    return open(out, encoding="utf-8").read()

# ---- decode_step separa resposta e raciocínio
d = G.decode_step(0, *model(T0, "Resposta visível", "pensando em silêncio")[:3])
assert d['text'] == "Resposta visível" and d['thinking'] == "pensando em silêncio", d
d = G.decode_step(0, 15, 3, head(T0, 15) + fl(20, fs(8, "só na cópia")))
assert d['text'] == "só na cópia" and d['thinking'] == ""
d = G.decode_step(0, 15, 3, head(T0, 15) + fl(20, fs(3, "só raciocínio")))
assert d['text'] == "" and d['thinking'] == "só raciocínio"

# ---- sessão A: resposta final visível, depois um passo só de raciocínio; modelo em f3.f28 a partir da 2ª linha
A = "aaaaaaaa-0000-0000-0000-00000000000a"
scratch = os.path.join(base, "antigravity", "brain", A, "scratch"); os.makedirs(scratch)
sysgen = os.path.join(base, "antigravity", "brain", A, ".system_generated", "steps", "4"); os.makedirs(sysgen)
open(os.path.join(scratch, "vivo.py"), "w").write("x")
brain = os.path.join(base, "antigravity", "brain", A)
open(os.path.join(brain, "session-report.md"), "w", encoding="utf-8").write("# Relatório\n" * 100)
open(os.path.join(brain, "session-report.md.metadata.json"), "w").write("{}")
gone = os.path.join(scratch, "apagado.py")
steps_a = [
    user(T0, "audite tudo"),
    model(T0 + 1, "", "vou escrever um script", [("c1", "write_file", json.dumps({"TargetFile": gone}))]),
    tool(T0 + 2, "write_file", json.dumps({"TargetFile": gone})),
    tool(T0 + 3, "write_file", json.dumps({"TargetFile": os.path.join(scratch, "vivo.py")})),
    tool(T0 + 4, "read_file", json.dumps({"Path": os.path.join(sysgen, "output.txt")})),
    tool(T0 + 5, "write_file", json.dumps({"TargetFile": "C:\\proj\\README.md"})),
    model(T0 + 6, "RELATÓRIO FINAL VISÍVEL", "raciocínio antes da resposta"),
    model(T0 + 7, "", "PENSAMENTO DEPOIS DA RESPOSTA"),
]
gen_a = [fl(3, fv(1, 1)), fl(3, fv(1, 2) + fs(28, "gemini-3.8-flash-high")), fl(3, fs(28, "gemini-3.8-flash-medium"))]
db_a = make(A, steps_a, gen_a)
doss = dossier(A, db_a)
assert "| Modelo(s) | gemini-3.8-flash-high, gemini-3.8-flash-medium |" in doss, "modelo em f3.f28, procurado além da 1ª linha"
fin = doss.split("## Última resposta do modelo", 1)[1]
assert fin.index("RELATÓRIO FINAL VISÍVEL") < fin.index("PENSAMENTO DEPOIS DA RESPOSTA"), "resposta visível primeiro"
assert "> PENSAMENTO DEPOIS DA RESPOSTA" in fin and "sem resposta visível" in fin
assert "raciocínio antes da resposta" not in doss, "raciocínio que precede a resposta fica fora do dossiê"
# artefatos: o .md entra, o .metadata.json e as subpastas não
assert "## Artefatos da sessão (1)" in doss and "session-report.md`" in doss and "metadata.json" not in doss
assert doss.index("## Artefatos da sessão") < doss.index("## Pedidos do usuário"), "artefatos no topo"
import re
assert re.search(r"session-report\.md` \| 1\.\d KB \|", doss), doss
# temporários recolhidos; arquivo real continua na tabela
assert "## Arquivos alterados (1)" in doss and "`C:\\proj\\README.md`" in doss
assert "apagado.py" not in doss and "vivo.py" not in doss and "output.txt" not in doss
assert "_Mais 3 arquivo(s) temporário(s) do agente" in doss and "1 ainda no disco" in doss, doss
assert "## Arquivos consultados" not in doss, "só havia leitura temporária"
# diálogo completo mostra os dois, com o raciocínio marcado
fu = full(A, db_a)
assert "_Raciocínio interno do modelo:_" in fu and "> raciocínio antes da resposta" in fu and "RELATÓRIO FINAL VISÍVEL" in fu
assert "apagado.py" in fu, "diálogo completo segue com a lista inteira"

# ---- sessão B: só raciocínio, sem resposta visível; modelo no formato antigo (f21); sem pasta brain
B = "bbbbbbbb-0000-0000-0000-00000000000b"
db_b = make(B, [user(T0, "oi"), model(T0 + 1, "", "PENSEI E PAREI")], [fs(21, "Gemini 3.8 Flash (High)")])
doss = dossier(B, db_b)
assert "| Modelo(s) | Gemini 3.8 Flash (High) |" in doss
assert "_Sem resposta visível. Último raciocínio interno do modelo:_" in doss and "> PENSEI E PAREI" in doss
assert "## Artefatos da sessão" not in doss and "temporário" not in doss

# ---- sessão C: sem gen_metadata e sem texto nenhum
C = "cccccccc-0000-0000-0000-00000000000c"
db = os.path.join(conv, C + ".db"); c = sqlite3.connect(db)
c.execute("CREATE TABLE steps (idx integer PRIMARY KEY, step_type integer, status integer, step_payload blob, error_details blob)")
c.execute("INSERT INTO steps VALUES(0,?,3,?,NULL)", (user(T0, "x")[0], user(T0, "x")[2])); c.commit(); c.close()
doss = dossier(C, db)
assert "| Modelo(s) | - |" in doss and "_(sem texto de resposta)_" in doss

# ---- auxiliares
assert G.is_temp_path("C:\\Users\\x\\.gemini\\antigravity\\brain\\" + A + "\\scratch\\a.py")
assert G.is_temp_path("/h/.gemini/antigravity/brain/" + A + "/.system_generated/steps/1/output.txt")
assert not G.is_temp_path("C:\\Users\\x\\.gemini\\antigravity\\brain\\" + A + "\\handoff.md")
assert not G.is_temp_path("C:\\proj\\scratch\\a.py")
assert G.fmt_size(500) == "500 B" and G.fmt_size(2048) == "2.0 KB" and G.fmt_size(3 * 1024 * 1024) == "3.0 MB"
assert G.quote("a\n\nb") == "> a\n>\n> b\n"
assert G.session_artifacts("", A) == [] and G.session_artifacts(db_b, B) == []
print("TODOS OS TESTES DOSSIER_FIELDS OK")
