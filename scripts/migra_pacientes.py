#!/usr/bin/env python3
"""Migración Pacientes_reg (Google Sheet) → tabla pacientes 2.0. Genera CSV para \\copy.

Preserva IdPac como id (integridad referencial para futuras migraciones).
FKs aún sin datos (cliente/agenda/tutor) → NULL. centro_id → 1 (único centro).
"""
import csv, sys
from datetime import datetime, date
import openpyxl

SRC = "/tmp/pac.xlsx"
OUT = "/tmp/pacientes.csv"
MIG = "2026-06-13 00:00:00"

wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
ws = wb["Pacientes_reg"]
rows = list(ws.iter_rows(values_only=True))
# fila 2 (idx) = nombres de columna
hdr = [("" if c is None else str(c)).strip() for c in rows[2]]
idx = {name: i for i, name in enumerate(hdr)}

def g(r, name):
    i = idx.get(name)
    return r[i] if (i is not None and i < len(r)) else None

def d(v):  # fecha → ISO date
    if v is None or v == "": return ""
    if isinstance(v, (datetime, date)): return v.strftime("%Y-%m-%d")
    return str(v)[:10]

def ts(v):  # datetime → ISO
    if v is None or v == "": return ""
    if isinstance(v, (datetime, date)): return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)

def b(v):
    return "true" if str(v).strip().lower() in ("true", "1", "si", "sí", "x", "verdadero") else "false"

def i_(v):
    try: return str(int(float(v)))
    except (TypeError, ValueError): return ""

def s(v):
    return "" if v is None else str(v)

COLS = ["id","centro_id","num_historia","nombre","apellidos","nif","fecha_nacimiento",
    "direccion","poblacion_id","cp","telefono_fijo","telefono_fijo2","telefono_movil",
    "email","foto_url","descuento","campo_libre_1","campo_libre_2","campo_libre_3","notas",
    "fecha_alta","acepta_lopd","acepta_info","acepta_whatsapp","acepta_bots","app_usuario",
    "app_password_hash","app_email_registro","app_fecha_registro","app_fecha_modificacion",
    "app_version","app_fecha_instalacion","activo","fecha_inactivo","motivo_inactivo",
    "updated_by","created_at","updated_at"]

n = 0
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    for r in rows[4:]:
        idpac = i_(g(r, "IdPac"))
        if not idpac:  # fila vacía / sin id
            continue
        inactivo = g(r, "Inactivo")
        activo = "false" if (inactivo not in (None, "")) else "true"
        w.writerow([
            idpac, "1", s(g(r,"NumPac")), s(g(r,"Nombre")), s(g(r,"Apellidos")), s(g(r,"NIF")),
            d(g(r,"FecNacim")), s(g(r,"Direccion")), i_(g(r,"IdPoblacio")), s(g(r,"CP")),
            s(g(r,"Tel1")), s(g(r,"Tel2")), s(g(r,"TelMovil")), s(g(r,"Email")), s(g(r,"Foto")),
            (s(g(r,"Descuento")) or ""), s(g(r,"Comodin1")), s(g(r,"Comodin2")), s(g(r,"Comodin3")),
            s(g(r,"Notas")), d(g(r,"FecAlta")), b(g(r,"AceptaLOPD")), b(g(r,"AceptaInfo")),
            b(g(r,"AceptaWhatsapp")), b(g(r,"AceptaBots")), s(g(r,"Usuarioapp")),
            s(g(r,"Contraseñaapp")), s(g(r,"Mailreg_app")), ts(g(r,"Fechareg_app")),
            ts(g(r,"Fechamod_app")), s(g(r,"Version")), d(g(r,"Fecha_Instalacion")),
            activo, d(inactivo), s(g(r,"MotivoInactivo")), i_(g(r,"_idUserModif")), MIG, MIG,
        ])
        n += 1

print(f"CSV generado: {OUT} · {n} pacientes · columnas: {len(COLS)}")
print(",".join(COLS))
