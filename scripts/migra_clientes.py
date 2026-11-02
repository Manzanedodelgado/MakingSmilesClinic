#!/usr/bin/env python3
import os
"""Migra GELITE.Clientes → clientes (2.0) y genera mapas para backfill de cliente_id."""
import csv, pymssql
from datetime import datetime, date
MIG = "2026-06-19 00:00:00"
c = pymssql.connect(server='100.72.42.45', port=1433, user='gesden_export',
                    password=os.environ['GELITE_PWD'], database='GELITE', login_timeout=10, timeout=120).cursor(as_dict=True)

def s(v): return "" if v is None else str(v).strip()
def D(v): return v.strftime("%Y-%m-%d") if isinstance(v, (datetime, date)) else ""

c.execute("""SELECT IdCli, Nombre, Apellidos, RazonSocial, NIF, Direccion, IdPoblacio, CP,
  Tel1, TelMovil, Email, CodIBAN, FecAlta, Inactivo FROM Clientes""")
n = 0
with open("/tmp/clientes.csv", "w", newline="") as f:
    w = csv.writer(f)
    for r in c.fetchall():
        rs = s(r["RazonSocial"])
        es_empresa = "true" if rs else "false"
        activo = "false" if r["Inactivo"] not in (None, "") else "true"
        tel = s(r["TelMovil"]) or s(r["Tel1"])
        w.writerow([r["IdCli"], 1, s(r["Nombre"]), s(r["Apellidos"]), rs, es_empresa,
            s(r["NIF"]), s(r["Direccion"]), s(r["CP"]),
            (r["IdPoblacio"] if r["IdPoblacio"] else ""), tel, s(r["Email"]),
            s(r["CodIBAN"]), D(r["FecAlta"]), activo, MIG, MIG])
        n += 1
print("clientes:", n)

# mapa paciente→cliente (IdCliPac)
c.execute("SELECT IdPac, IdCliPac FROM Pacientes WHERE IdCliPac IS NOT NULL AND IdCliPac>0")
with open("/tmp/pac_cli.csv", "w", newline="") as f:
    w = csv.writer(f)
    for r in c.fetchall(): w.writerow([r["IdPac"], r["IdCliPac"]])

# mapa pago→cliente (PagoCli.IdCli)
c.execute("SELECT IdPagoCli, IdCli FROM PagoCli WHERE IdCli IS NOT NULL AND IdCli>0")
with open("/tmp/pago_cli.csv", "w", newline="") as f:
    w = csv.writer(f)
    for r in c.fetchall(): w.writerow([r["IdPagoCli"], r["IdCli"]])

# mapa deuda→cliente (DeudaCli.IdCli)
c.execute("SELECT IdDeudaCli, IdCli FROM DeudaCli WHERE IdCli IS NOT NULL AND IdCli>0")
with open("/tmp/deuda_cli.csv", "w", newline="") as f:
    w = csv.writer(f)
    for r in c.fetchall(): w.writerow([r["IdDeudaCli"], r["IdCli"]])
print("mapas backfill generados")
