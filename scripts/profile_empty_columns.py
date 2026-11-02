#!/usr/bin/env python3
import os
"""Perfila columnas 100% NULL (vacías) en las tablas con datos. READ-ONLY.

Para cada tabla incluida que tiene filas, una sola consulta cuenta los no-nulos
de cada columna; las que dan 0 están totalmente vacías. Salida: JSON + resumen.
"""
import json
from pathlib import Path

import pymssql

CFG = dict(server="100.72.42.45", port=1433, user="gesden_export",
           password="'+os.environ.get('GELITE_PWD','')+'", database="GELITE", login_timeout=15, timeout=600)
base = Path(__file__).resolve().parent.parent / "gelite-extract-20260618"

incl = json.loads((base / "tablas_incluidas_2.0.json").read_text())["incluidas"]
rows_by = {t["tbl"]: (t["rows"] or 0) for t in json.loads((base / "tables.json").read_text())}
cols_by = {}
for c in json.loads((base / "columns.json").read_text()):
    cols_by.setdefault(c["tbl"], []).append(c["col"])

targets = [t for t in incl if rows_by.get(t, 0) > 0]

conn = pymssql.connect(**CFG)
cur = conn.cursor()
report = {}
for t in targets:
    cols = cols_by.get(t, [])
    if not cols:
        continue
    sel = "COUNT(*) AS _total, " + ", ".join(
        f"SUM(CASE WHEN [{c}] IS NULL THEN 0 ELSE 1 END) AS [{c}]" for c in cols)
    cur.execute(f"SELECT {sel} FROM [{t}]")
    names = [d[0] for d in cur.description]
    vals = dict(zip(names, cur.fetchone()))
    total = vals.pop("_total")
    empties = [c for c in cols if vals.get(c, 0) == 0]
    report[t] = {"filas": total, "columnas": len(cols),
                 "vacias": empties, "n_vacias": len(empties)}
conn.close()

(base / "columnas_vacias.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

tot_cols = sum(r["columnas"] for r in report.values())
tot_empty = sum(r["n_vacias"] for r in report.values())
print(f"Tablas con datos analizadas: {len(report)}")
print(f"Columnas totales: {tot_cols} · columnas 100% vacías: {tot_empty} ({tot_empty*100//tot_cols}%)")
print("\n=== Tablas con más columnas vacías ===")
for t, r in sorted(report.items(), key=lambda x: -x[1]["n_vacias"])[:20]:
    print(f"  {t:<26} {r['n_vacias']:>3}/{r['columnas']:<3} vacías  ({r['filas']} filas)")
print("\nDetalle completo -> gelite-extract-20260618/columnas_vacias.json")
