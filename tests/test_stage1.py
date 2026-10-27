import os, sys, json, tempfile, threading, glob, logging, logging.handlers
# Etapa 1 da revisão final: máscara de segredos, estado em memória entre threads, preferências atômicas, log com rotação.
root = tempfile.mkdtemp(prefix="agys1_")
os.environ.update(HOME=os.path.join(root, "home"), ANTIGRAVITY_HOME=os.path.join(root, "g"), LOCALAPPDATA=os.path.join(root, "local"))
os.environ.pop("AGY_ROT_TOKENS", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import AntigravityGate as G

# --- 1. máscara: formatos que vazavam na auditoria + outros comuns
leaks = ["sk_live_51HxAbCdEfGhIjKlMnOpQrStUv", "rk_test_51HxAbCdEfGhIjKlMnOpQr", "postgres://admin:S3nhaForte@db:5432/x",
         "mysql://root:pa55word@localhost/app", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcDEFghiJKLmnoPQR",
         "xoxb-123456789012-123456789012-abcdefghijklmnopqrstuvwx", "Authorization: Basic dXNlcjpwYXNzd29yZA==",
         "ya29.a0AfH6SMBxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "github_pat_11ABCDEFG0123456789_abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOP",
         "sk-ant-api03-abcdefghijklmnopqrstuvwxyz", "api_key = 'abcdef123456'"]
for s in leaks:
    out = G.redact(s)
    assert "[REDACTED]" in out, s
assert G.redact("postgres://admin:S3nhaForte@db:5432/x") == "postgres://admin:[REDACTED]@db:5432/x", "usuário e host continuam legíveis"
assert "S3nhaForte" not in G.redact("conexão: postgres://admin:S3nhaForte@db:5432/x ok")
for benign in ("Contexto na última resposta | 145624 tokens |", "https://github.com/two2dope/agy-gate", "postgres://localhost:5432/db",
               "Basic usage of the API", "file:///C:/Users/Thomáz/Projetos/x.py", "C:\\Users\\Thomáz\\.gemini\\antigravity"):
    assert G.redact(benign) == benign, benign

# --- 2. estado em memória (sem disco gravável) funciona a partir de outra thread
blocker = os.path.join(root, "arquivo")
open(blocker, "w").close()
st = G.StateStore(os.path.join(blocker, "sub", "state.db"))  # a "pasta" é um arquivo: cai para memória
assert not st.persistent
errors = []
def work():
    try:
        st.add_handoff("a", "b", "p", "ok", "resposta")
        st.set_many(["c1", "c2"], "arquivada")
    except Exception as e:
        errors.append(repr(e))
threads = [threading.Thread(target=work) for _ in range(4)]
for t in threads: t.start()
for t in threads: t.join()
assert not errors, errors
assert st.handoffs_ok() == {"a": "b"} and st.load() == {"c1": "arquivada", "c2": "arquivada"}

# --- 3. preferências: gravação atômica (erro no meio não estraga o arquivo nem deixa sobra)
G.save_settings({"theme": "mecha", "n": 1})
G.save_settings({"theme": "claro", "ruim": object()})  # não serializável: falha no meio do json.dump
assert G.load_settings() == {"theme": "mecha", "n": 1}, G.load_settings()
assert glob.glob(G.SETTINGS_FILE + ".*") == [], glob.glob(G.SETTINGS_FILE + ".*")
G.save_settings({"theme": "claro"}); assert G.load_settings() == {"theme": "claro"}

# --- 4. log com rotação
G.setup_logging()
hs = [h for h in G.log.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
assert hs and hs[0].maxBytes == G.LOG_MAX_BYTES and hs[0].backupCount >= 2, G.log.handlers
G.setup_logging()
assert len([h for h in G.log.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]) == 1, "chamar de novo não duplica"
print("TODOS OS TESTES DA ETAPA 1 OK")
