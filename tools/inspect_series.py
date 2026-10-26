"""Tabelas numéricas de uma sessão do Antigravity (sem o conteúdo das conversas).

Uso:  python inspect_series.py CAMINHO.db
Precisa estar na mesma pasta que inspect_steps.py. Abre em modo somente-leitura.

Mostra: contagem de (step_type, origem), linha do tempo dos primeiros passos e a série de uso de
tokens de cada resposta do modelo (campos numéricos de step_payload.f5.f9), mais os nomes de modelo.
"""
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from inspect_steps import parse


def dig(fields, path):
    """Segue `path` (lista de números de campo) em protobuf já decodificado; devolve (wire, valor) ou None."""
    cur = fields
    for k, f in enumerate(path):
        hit = next(((w, v) for ff, w, v in cur if ff == f), None)
        if hit is None:
            return None
        if k == len(path) - 1:
            return hit
        if hit[0] != 2:
            return None
        try:
            cur = parse(hit[1])
        except ValueError:
            return None
    return None


def num(fields, path):
    r = dig(fields, path)
    return r[1] if r and r[0] == 0 else None


def text(fields, path):
    r = dig(fields, path)
    if not r or r[0] != 2:
        return None
    try:
        return r[1].decode("utf-8")
    except UnicodeDecodeError:
        return None


def hora(sec):
    if sec is None:
        return "-"
    return datetime.fromtimestamp(sec, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    db = Path(sys.argv[1]).resolve()
    c = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=2)
    rows = c.execute("SELECT idx, step_type, status, step_payload FROM steps ORDER BY idx").fetchall()
    parsed = []
    for idx, t, st, blob in rows:
        try:
            fields = parse(blob) if blob else []
        except ValueError:
            fields = []
        parsed.append((idx, t, st, len(blob or b""), fields))

    print(f"== {len(rows)} passos")
    print("\n== CONTAGEM por (step_type, origem=f5.f3)")
    cont = {}
    for idx, t, st, n, fields in parsed:
        k = (t, num(fields, [5, 3]))
        cont[k] = cont.get(k, 0) + 1
    for (t, o), n in sorted(cont.items(), key=lambda x: (x[0][0], x[0][1] or -1)):
        print(f"- step_type {t} | origem {o}: {n}")

    print("\n== LINHA DO TEMPO (primeiros 25 passos): idx | step_type | status | origem | criado_em (UTC) | bytes")
    for idx, t, st, n, fields in parsed[:25]:
        print(f"{idx} | {t} | {st} | {num(fields, [5, 3])} | {hora(num(fields, [5, 1, 1]))} | {n}")

    resp = [p for p in parsed if p[1] == 15]
    print(f"\n== USO DE TOKENS por resposta do modelo (step_type 15): {len(resp)} respostas")
    print("idx | criado_em | f1 | f2 | f3 | f5 | f6 | f9 | f10   (campos de step_payload.f5.f9)")
    if len(resp) > 40:
        pick = [resp[round(i * (len(resp) - 1) / 39)] for i in range(40)]
    else:
        pick = resp
    modelos = set()
    for idx, t, st, n, fields in resp:
        for path in ([5, 9, 7], [5, 9, 8, 1], [5, 9, 8, 2], [5, 9, 11]):
            v = text(fields, path)
            if v:
                modelos.add(v)
    for idx, t, st, n, fields in pick:
        vals = [num(fields, [5, 9, f]) for f in (1, 2, 3, 5, 6, 9, 10)]
        print(f"{idx} | {hora(num(fields, [5, 1, 1]))} | " + " | ".join("-" if v is None else str(v) for v in vals))

    print("\n== TEXTOS CURTOS DE IDENTIFICAÇÃO em f5.f9 (nomes de modelo/provedor)")
    for m in sorted(modelos):
        print(f"- {m}")

    n_gen = c.execute("SELECT COUNT(*) FROM gen_metadata").fetchone()[0]
    print(f"\n== gen_metadata: {n_gen} linhas | respostas do modelo (step_type 15): {len(resp)}")


if __name__ == "__main__":
    main()
