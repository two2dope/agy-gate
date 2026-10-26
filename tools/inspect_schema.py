import sqlite3, sys, zlib, gzip
from pathlib import Path

db = Path(sys.argv[1]).resolve()
c = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=2)

print("== SCHEMA")
for name, typ, sql in c.execute("SELECT name, type, sql FROM sqlite_master"):
    print(typ, name, "|", sql)

def unpack(b):
    for fn, label in ((gzip.decompress, "gzip"), (zlib.decompress, "zlib")):
        try:
            return label, len(fn(b))
        except Exception:
            pass
    return "nenhum", None

for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
    cols = [r[1] for r in c.execute(f'PRAGMA table_info("{t}")')]
    n = c.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    print(f"\n== {t}: {n} linhas")
    for col in cols:
        q = f'"{col}"'
        print(f"- {col}: (typeof, qtd, len_min, len_max) =",
              c.execute(f'SELECT typeof({q}), COUNT(*), MIN(length({q})), MAX(length({q})) FROM "{t}" GROUP BY 1').fetchall())
        if c.execute(f'SELECT COUNT(DISTINCT {q}) FROM "{t}"').fetchone()[0] <= 15:
            vals = [r[0] for r in c.execute(f'SELECT DISTINCT {q} FROM "{t}"')
                    if isinstance(r[0], (int, float)) or (isinstance(r[0], str) and len(r[0]) <= 30)]
            print(f"    valores distintos (curtos): {vals}")
        for (b,) in c.execute(f'SELECT {q} FROM "{t}" WHERE typeof({q})="blob" LIMIT 3'):
            print(f"    blob: 3 primeiros bytes={b[:3].hex()}  compressao={unpack(b)}")
