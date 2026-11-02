#!/usr/bin/env python3
import os
"""Corrige tarifa_precios (id=IdTratamientoTarifa) y re-migra TtosMed con AMBOS enlaces:
   tratamiento_id (catálogo) + tarifa_precio_id (tarifa/precio). Genera 3 CSV."""
import csv, pymssql
from datetime import datetime, date

P = set(int(x) for x in open("/tmp/pac_ids.txt") if x.strip())
T = set(int(x) for x in open("/tmp/tto_ids.txt") if x.strip())
TAR = set(int(x) for x in open("/tmp/tarifa_ids.txt") if x.strip())
COL = set(int(x) for x in open("/tmp/col_ids.txt") if x.strip())
MIG = "2026-06-19 00:00:00"

c = pymssql.connect(server='100.72.42.45', port=1433, user='gesden_export',
                    password=os.environ['GELITE_PWD'], database='GELITE', login_timeout=10, timeout=300).cursor(as_dict=True)

def tar(idt):  # IdTarifa GELITE → tarifa 2.0 (3→Privada=1)
    v = 1 if idt == 3 else idt
    return v if v in TAR else None

def D(v):
    return v.strftime("%Y-%m-%d") if isinstance(v, (datetime, date)) else ""

# ── tarifa_precios: id = IdTratamientoTarifa, + precio
c.execute("""SELECT tt.IdTratamientoTarifa id, tt.IdTratamiento, tt.IdTarifa,
  p.PrecioPrivado, p.PrecioColaborador
  FROM Tratamientos_Tarifas tt
  LEFT JOIN Tratamientos_Tarifas_Precios p ON p.IdTratamientoTarifa = tt.IdTratamientoTarifa""")
tp_map = {}   # IdTratamientoTarifa -> IdTratamiento (catálogo)
n_tp = 0
with open("/tmp/tarifa_precios.csv", "w", newline="") as f:
    w = csv.writer(f)
    for r in c.fetchall():
        tarid = tar(r["IdTarifa"])
        ttoid = r["IdTratamiento"] if r["IdTratamiento"] in T else None
        if tarid is None or ttoid is None:
            continue
        tp_map[r["id"]] = ttoid
        precio = r["PrecioPrivado"] if r["PrecioPrivado"] is not None else 0
        clab = r["PrecioColaborador"] if r["PrecioColaborador"] is not None else ""
        w.writerow([r["id"], tarid, ttoid, precio, clab, MIG, MIG])
        n_tp += 1
print(f"tarifa_precios: {n_tp} (id=IdTratamientoTarifa preservado)")

# ── tratamientos_realizados (TtosMed) + fases
c.execute("""SELECT Ident, IdPac, IdTto, NumTto, IdCol, IdColAux, StaTto, FecIni, FecFin,
  Importe, Dto, ImporteDto, ImportePrivado, ImporteMutua, Pendiente, Actos, Tiempo,
  PiezasNum, ZonasBoca, Notas, NFacturaEl, NumTransaccion
  FROM TtosMed""")
n_tm = 0; omit = 0
with open("/tmp/ttosmed.csv", "w", newline="") as f:
    w = csv.writer(f)
    for r in c.fetchall():
        pac = r["IdPac"] or 0
        if pac not in P:
            omit += 1; continue
        idtto = r["IdTto"]
        tarprecio = idtto if (idtto in tp_map) else ""
        ttocat = tp_map.get(idtto, "")          # catálogo vía la línea de tarifa
        col = r["IdCol"] if r["IdCol"] in COL else ""
        colaux = r["IdColAux"] if r["IdColAux"] in COL else ""
        def money(x): return x if x is not None else ""
        w.writerow([r["Ident"], 1, pac, ttocat, tarprecio, r["NumTto"], col, colaux,
            (r["StaTto"] if r["StaTto"] is not None else ""), D(r["FecIni"]), D(r["FecFin"]),
            money(r["Importe"]), money(r["Dto"]), money(r["ImporteDto"]),
            money(r["ImportePrivado"]), money(r["ImporteMutua"]), money(r["Pendiente"]),
            (r["Actos"] if r["Actos"] is not None else ""), (r["Tiempo"] if r["Tiempo"] is not None else ""),
            (r["PiezasNum"] or ""), (r["ZonasBoca"] or ""), (r["Notas"] or ""),
            (r["NFacturaEl"] or ""), (r["NumTransaccion"] or ""), MIG, MIG])
        n_tm += 1
print(f"tratamientos_realizados: {n_tm}  (omitidas por paciente inexistente: {omit})")

# fases (enlazan por Ident)
idents = set()
c.execute("SELECT Ident FROM TtosMed"); idents = {r["Ident"] for r in c.fetchall()}
c.execute("""SELECT IdTtosMedFase, IdTtosMed, NumFase, Estado, Fecha, TpcFacturar, IdCol, Notas
  FROM TtosMedFases""")
n_f = 0
with open("/tmp/ttosmed_fases.csv", "w", newline="") as f:
    w = csv.writer(f)
    for r in c.fetchall():
        if r["IdTtosMed"] not in idents:
            continue
        col = r["IdCol"] if r["IdCol"] in COL else ""
        w.writerow([r["IdTtosMedFase"], r["IdTtosMed"], (r["NumFase"] if r["NumFase"] is not None else ""),
            (r["Estado"] if r["Estado"] is not None else ""), D(r["Fecha"]),
            (r["TpcFacturar"] if r["TpcFacturar"] is not None else ""), col, (r["Notas"] or ""), MIG, MIG])
        n_f += 1
print(f"tratamientos_realizados_fases: {n_f}")
