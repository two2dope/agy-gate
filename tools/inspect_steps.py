"""Mostra a ESTRUTURA dos blobs protobuf de um .db do Antigravity (sem o conteúdo das conversas).

Uso:
    python inspect_steps.py CAMINHO.db            # estrutura apenas
    python inspect_steps.py CAMINHO.db --amostra 20   # inclui os 20 primeiros caracteres de cada texto
    python inspect_steps.py CAMINHO.db --idx 0,3,7 --amostra 40   # só estes passos, por idx

Aceita um banco de sessão (tabela `steps`) ou o conversation_summaries.db (coluna `raw_summary`).
Abre em modo somente-leitura.
"""
import sqlite3
import sys
from pathlib import Path

MAX_DEPTH = 8


def varint(b, i):
    x = shift = 0
    while True:
        if i >= len(b):
            raise ValueError("varint truncado")
        c = b[i]
        i += 1
        x |= (c & 0x7F) << shift
        if not c & 0x80:
            return x, i
        shift += 7
        if shift > 70:
            raise ValueError("varint longo demais")


def parse(b):
    """Decodifica protobuf genérico em [(campo, wire, valor)]. Levanta ValueError se não for protobuf."""
    i, out = 0, []
    while i < len(b):
        tag, i = varint(b, i)
        f, w = tag >> 3, tag & 7
        if f == 0 or f > 100000:
            raise ValueError("campo inválido")
        if w == 0:
            v, i = varint(b, i)
        elif w == 1 or w == 5:
            n = 8 if w == 1 else 4
            v = b[i:i + n]
            if len(v) < n:
                raise ValueError("fixo truncado")
            i += n
        elif w == 2:
            n, i = varint(b, i)
            v = b[i:i + n]
            if len(v) < n:
                raise ValueError("bloco truncado")
            i += n
        else:
            raise ValueError("wire type inválido")
        out.append((f, w, v))
    return out


def classify(v):
    """Para um bloco length-delimited: ('vazio'|'str'|'msg'|'bytes', dado)."""
    if not v:
        return "vazio", None
    try:
        s = v.decode("utf-8")
        if all(ch.isprintable() or ch in "\n\r\t" for ch in s):
            return "str", s
    except UnicodeDecodeError:
        pass
    try:
        fields = parse(v)
        if fields:
            return "msg", fields
    except ValueError:
        pass
    return "bytes", None


def sig(f, w, v, depth):
    if w == 0:
        return f"{f}:v"
    if w in (1, 5):
        return f"{f}:x"
    kind, data = classify(v)
    if kind == "msg" and depth < MAX_DEPTH:
        return f"{f}:{{" + ",".join(sig(*x, depth + 1) for x in data) + "}"
    return f"{f}:{kind}"


def dump(fields, depth, out, amostra):
    counts = {}
    for f, w, v in fields:
        s = sig(f, w, v, depth)
        counts[s] = counts.get(s, 0) + 1
    shown = set()
    pad = "  " * depth
    for f, w, v in fields:
        s = sig(f, w, v, depth)
        if s in shown:
            continue
        shown.add(s)
        rep = f"  (x{counts[s]})" if counts[s] > 1 else ""
        if w == 0:
            out.append(f"{pad}f{f} varint={v}{rep}")
        elif w in (1, 5):
            out.append(f"{pad}f{f} fixo{64 if w == 1 else 32}{rep}")
        else:
            kind, data = classify(v)
            if kind == "msg" and depth < MAX_DEPTH:
                out.append(f"{pad}f{f} msg{rep} {{")
                dump(data, depth + 1, out, amostra)
                out.append(f"{pad}}}")
            elif kind == "str":
                extra = ""
                if amostra:
                    extra = " amostra=" + repr(data[:amostra])
                out.append(f"{pad}f{f} texto len={len(v)}{extra}{rep}")
            else:
                out.append(f"{pad}f{f} {kind} len={len(v)}{rep}")


def show_blob(label, blob, cap, amostra):
    if blob is None:
        return
    print(f"  [{label}] {len(blob)} bytes")
    try:
        lines = []
        dump(parse(blob), 2, lines, amostra)
    except ValueError as e:
        print(f"    (não é protobuf válido: {e})")
        return
    for ln in lines[:cap]:
        print(ln)
    if len(lines) > cap:
        print(f"    ... (+{len(lines) - cap} linhas omitidas)")


def show_step(c, idx, amostra, titulo):
    print(f"\n== {titulo}")
    row = c.execute("SELECT metadata, step_payload, render_info, error_details, task_details, step_type, status FROM steps WHERE idx=?", (idx,)).fetchone()
    if row is None:
        print("  (idx inexistente)")
        return
    print(f"  step_type={row[5]} status={row[6]}")
    for label, blob, cap in zip(("step_payload", "metadata", "render_info", "error_details", "task_details"),
                                 (row[1], row[0], row[2], row[3], row[4]), (150, 40, 30, 20, 20)):
        show_blob(label, blob, cap, amostra)


def inspect_steps(c, amostra, idxs):
    if idxs:
        for idx in idxs:
            show_step(c, idx, amostra, f"PASSO idx={idx}")
        return
    print("== RESUMO POR step_type (qtd | status | tamanho do step_payload min/mediana/max)")
    types = [r[0] for r in c.execute("SELECT DISTINCT step_type FROM steps ORDER BY 1")]
    picks = []
    for t in types:
        rows = c.execute("SELECT idx, status, length(step_payload) FROM steps WHERE step_type=? ORDER BY length(step_payload)", (t,)).fetchall()
        st = sorted({r[1] for r in rows})
        mid = rows[len(rows) // 2]
        print(f"- step_type {t}: {len(rows)} passos | status {st} | {rows[0][2]} / {mid[2]} / {rows[-1][2]} bytes | idx de {min(r[0] for r in rows)} a {max(r[0] for r in rows)}")
        picks.append((t, mid[0]))
    print("\n== SEQUÊNCIA DE step_type (primeiros 40 passos, por idx)")
    seq = [r[0] for r in c.execute("SELECT step_type FROM steps ORDER BY idx LIMIT 40")]
    print("  " + " ".join(map(str, seq)))
    for t, idx in picks:
        show_step(c, idx, amostra, f"ESTRUTURA DE UM PASSO step_type={t} (idx={idx}, tamanho mediano)")
    for tbl in ("gen_metadata", "executor_metadata"):
        row = c.execute(f"SELECT idx, data FROM {tbl} ORDER BY length(data) LIMIT 1").fetchone()
        if row:
            print(f"\n== ESTRUTURA DE {tbl} (menor linha, idx={row[0]})")
            show_blob("data", row[1], 60, amostra)


def inspect_summaries(c, amostra):
    rows = c.execute("SELECT conversation_id, raw_summary FROM conversation_summaries WHERE raw_summary IS NOT NULL ORDER BY length(raw_summary)").fetchall()
    for label, r in (("mediana", rows[len(rows) // 2]), ("maior", rows[-1])):
        print(f"\n== ESTRUTURA DE raw_summary ({label})")
        show_blob("raw_summary", r[1], 80, amostra)


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    amostra = 0
    if "--amostra" in args:
        k = args.index("--amostra")
        amostra = int(args[k + 1])
        del args[k:k + 2]
    idxs = []
    if "--idx" in args:
        k = args.index("--idx")
        idxs = [int(x) for x in args[k + 1].split(",")]
        del args[k:k + 2]
    db = Path(args[0]).resolve()
    c = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=2)
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "steps" in tables:
        inspect_steps(c, amostra, idxs)
    if "conversation_summaries" in tables:
        inspect_summaries(c, amostra)
    if not tables & {"steps", "conversation_summaries"}:
        print("Banco sem tabela steps nem conversation_summaries.")


if __name__ == "__main__":
    main()
