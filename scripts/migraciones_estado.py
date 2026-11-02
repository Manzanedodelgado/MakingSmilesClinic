"""Siembra migraciones_aplicadas comprobando el ESQUEMA REAL, no suponiendo.

Para cada .sql lee qué objetos declara crear (tabla.columna, tabla, índice) y pregunta al
information_schema si están. Solo marca como aplicada la que tiene TODOS sus objetos.
Lo que no se puede decidir se deja fuera y se informa: un registro con cosas inventadas
es peor que no tener registro.
"""
import os, re, sys
from sqlalchemy import text
from infrastructure.config.db import engine

# El argumento MANDA. Si no se da, se busca donde suelen estar. Una carpeta que existe pero
# está vacía no vale: devolvería "0 pendientes", que parece una buena noticia y es un fallo.
MIG = sys.argv[1] if len(sys.argv) > 1 else next(
    (d for d in ("backend/migrations", "/app/migrations", "migrations") if os.path.isdir(d)), None)
if not MIG or not os.path.isdir(MIG):
    sys.exit(f"No encuentro la carpeta de migraciones. Pásala como argumento: {sys.argv[0]} <carpeta>")
_sql = [f for f in os.listdir(MIG) if f.endswith(".sql")]
if not _sql:
    sys.exit(f"{MIG} no tiene ningún .sql: no hay nada que comprobar (y '0 pendientes' aquí "
             f"significaría que no se ha mirado, no que todo esté al día).")
print(f"Comprobando {len(_sql)} migraciones de {MIG} contra el esquema real.\n")


def objetos(sql: str):
    """(columnas, tablas, indices) que el fichero declara crear."""
    cols, tablas, indices = set(), set(), set()
    # ALTER TABLE x ... ADD COLUMN [IF NOT EXISTS] y   (varias ADD por sentencia)
    for m in re.finditer(r'ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?'
                         r'(?:["\']?\w+["\']?\.)?["\']?(\w+)["\']?(.*?)(?=;)', sql,
                         re.I | re.S):
        tabla, cuerpo = m.group(1).lower(), m.group(2)
        for c in re.finditer(r'ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?["\']?(\w+)["\']?',
                             cuerpo, re.I):
            cols.add((tabla, c.group(1).lower()))
    for m in re.finditer(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?'
                         r'(?:["\']?\w+["\']?\.)?["\']?(\w+)["\']?', sql, re.I):
        tablas.add(m.group(1).lower())
    for m in re.finditer(r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?'
                         r'(?:IF\s+NOT\s+EXISTS\s+)?["\']?(\w+)["\']?', sql, re.I):
        indices.add(m.group(1).lower())
    return cols, tablas, indices

with engine.begin() as cx:
    cols_bd = {(t, c) for t, c in cx.execute(text(
        "select table_name, column_name from information_schema.columns where table_schema='public'"))}
    tablas_bd = {r[0] for r in cx.execute(text(
        "select table_name from information_schema.tables where table_schema='public'"))}
    idx_bd = {r[0] for r in cx.execute(text(
        "select indexname from pg_indexes where schemaname='public'"))}

    aplicadas, faltan, indecisas = [], [], []
    for f in sorted(os.listdir(MIG)):
        if not f.endswith(".sql"):
            continue
        sql = open(os.path.join(MIG, f), encoding="utf-8", errors="replace").read()
        cols, tablas, indices = objetos(sql)
        if not (cols or tablas or indices):
            indecisas.append(f)          # solo UPDATE/INSERT/función: el esquema no lo delata
            continue
        falta = ([f"{t}.{c}" for t, c in sorted(cols - cols_bd)]
                 + sorted(tablas - tablas_bd) + sorted(indices - idx_bd))
        (aplicadas if not falta else faltan).append((f, falta))

    for f, _ in aplicadas:
        cx.execute(text("insert into migraciones_aplicadas (nombre, origen, nota) "
                        "values (:n, :o, :t) on conflict (nombre) do nothing"),
                   {"n": f, "o": "retroactiva",
                    "t": "Objetos presentes en el esquema al crear el registro."})

    print(f"APLICADAS (sembradas): {len(aplicadas)}")
    print(f"NO APLICADAS: {len(faltan)}")
    for f, falta in faltan:
        print(f"   {f} -> falta: {', '.join(falta[:5])}{' …' if len(falta) > 5 else ''}")
    print(f"NO DECIDIBLES por esquema (no sembradas): {len(indecisas)}")
    for f in indecisas:
        print(f"   {f}")
