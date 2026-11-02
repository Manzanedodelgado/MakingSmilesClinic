#!/usr/bin/env python3
import os
"""Extracción READ-ONLY del esquema GELITE (SQL Server) → JSON.

Fuente: DENTALBOX1\\INFOMED @ 100.72.42.45:1433, base GELITE (login gesden_export).
Solo SELECT sobre catálogo (sys.* / INFORMATION_SCHEMA). NO toca datos.
Salida: un JSON por aspecto + un manifest. Materia prima para el modelo 2.0
(será curada/editada antes de aterrizar en destino).

Uso:  python3 scripts/extract_gelite.py [out_dir]
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pymssql

CFG = dict(server="100.72.42.45", port=1433, user="gesden_export",
           password="'+os.environ.get('GELITE_PWD','')+'", database="GELITE", login_timeout=15, timeout=300)

Q_TABLES = """
SELECT s.name AS sch, t.name AS tbl, SUM(p.rows) AS rows
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0,1)
GROUP BY s.name, t.name
ORDER BY SUM(p.rows) DESC
"""

Q_COLUMNS = """
SELECT s.name AS sch, t.name AS tbl, c.name AS col, c.column_id AS ord,
       ty.name AS data_type, c.max_length, c.precision, c.scale,
       c.is_nullable, c.is_identity, dc.definition AS default_def
FROM sys.columns c
JOIN sys.tables t ON t.object_id = c.object_id
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.types ty ON ty.user_type_id = c.user_type_id
LEFT JOIN sys.default_constraints dc ON dc.object_id = c.default_object_id
ORDER BY s.name, t.name, c.column_id
"""

Q_PKS = """
SELECT s.name AS sch, t.name AS tbl, i.name AS pk_name, c.name AS col, ic.key_ordinal AS ord
FROM sys.indexes i
JOIN sys.tables t ON t.object_id = i.object_id
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE i.is_primary_key = 1
ORDER BY s.name, t.name, ic.key_ordinal
"""

Q_FKS = """
SELECT fk.name AS fk_name,
       sp.name AS parent_sch, tp.name AS parent_tbl, cp.name AS parent_col,
       sr.name AS ref_sch, tr.name AS ref_tbl, cr.name AS ref_col,
       fkc.constraint_column_id AS ord
FROM sys.foreign_keys fk
JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
JOIN sys.tables tp ON tp.object_id = fk.parent_object_id
JOIN sys.schemas sp ON sp.schema_id = tp.schema_id
JOIN sys.columns cp ON cp.object_id = tp.object_id AND cp.column_id = fkc.parent_column_id
JOIN sys.tables tr ON tr.object_id = fk.referenced_object_id
JOIN sys.schemas sr ON sr.schema_id = tr.schema_id
JOIN sys.columns cr ON cr.object_id = tr.object_id AND cr.column_id = fkc.referenced_column_id
ORDER BY fk.name, fkc.constraint_column_id
"""

Q_INDEXES = """
SELECT s.name AS sch, t.name AS tbl, i.name AS idx_name, i.is_unique,
       c.name AS col, ic.key_ordinal AS ord
FROM sys.indexes i
JOIN sys.tables t ON t.object_id = i.object_id
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE i.is_primary_key = 0 AND i.type > 0 AND ic.is_included_column = 0
ORDER BY s.name, t.name, i.name, ic.key_ordinal
"""

Q_VIEWS = """
SELECT s.name AS sch, v.name AS vw, m.definition
FROM sys.views v
JOIN sys.schemas s ON s.schema_id = v.schema_id
LEFT JOIN sys.sql_modules m ON m.object_id = v.object_id
ORDER BY s.name, v.name
"""


def rows_as_dicts(cur, query):
    cur.execute(query)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else
               Path(__file__).resolve().parent.parent / "gelite-extract-20260618")
    out.mkdir(parents=True, exist_ok=True)

    conn = pymssql.connect(**CFG)
    cur = conn.cursor()

    tables = rows_as_dicts(cur, Q_TABLES)
    columns = rows_as_dicts(cur, Q_COLUMNS)
    pks = rows_as_dicts(cur, Q_PKS)
    fks = rows_as_dicts(cur, Q_FKS)
    indexes = rows_as_dicts(cur, Q_INDEXES)
    views = rows_as_dicts(cur, Q_VIEWS)
    conn.close()

    def dump(name, data):
        (out / f"{name}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return len(data)

    counts = {
        "tables": dump("tables", tables),
        "columns": dump("columns", columns),
        "primary_keys": dump("primary_keys", pks),
        "foreign_keys": dump("foreign_keys", fks),
        "indexes": dump("indexes", indexes),
        "views": dump("views", views),
    }
    manifest = {
        "source": "GELITE @ DENTALBOX1\\INFOMED (100.72.42.45:1433)",
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read-only (solo SELECT sobre catálogo)",
        "counts": counts,
        "top_tables_by_rows": tables[:15],
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print("EXTRACCIÓN COMPLETA →", out)
    for k, v in counts.items():
        print(f"  {k:<14}{v}")


if __name__ == "__main__":
    main()
