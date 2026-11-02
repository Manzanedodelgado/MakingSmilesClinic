#!/usr/bin/env python3
"""Migra TColabos→colaboradores(+especialidades,+centro) y Personal_reg→usuarios(+vínculo).
Emite SQL por stdout (para pipe a psql). FKs vacías (tratamiento_exento) → NULL.
"""
import openpyxl
from datetime import datetime, date

wb = openpyxl.load_workbook("/tmp/sheet.xlsx", read_only=True, data_only=True)

def q(v):
    if v is None or v == "": return "NULL"
    return "'" + str(v).replace("'", "''").strip() + "'"

def num(v):
    try: return str(int(float(v)))
    except (TypeError, ValueError): return "NULL"

def f(v):
    try: return str(float(v))
    except (TypeError, ValueError): return "NULL"

def dt(v):
    if isinstance(v, (datetime, date)): return "'" + v.strftime("%Y-%m-%d") + "'"
    return "NULL"

def yes(v):  # ✅ / Activo / Si → true
    s = str(v).lower()
    return "true" if ("✅" in s or "activo" in s or s.strip() in ("si","sí","x","true")) else "false"

def cell(r, hdr, name):
    i = hdr.get(name)
    return r[i] if (i is not None and i < len(r)) else None

print("BEGIN;")

# ---- COLABORADORES (TColabos) ----
ws = wb["TColabos"]; rows = list(ws.iter_rows(values_only=True))
hdr = {str(c).strip(): i for i, c in enumerate(rows[0]) if c is not None}
esp_links = []
for r in rows[1:]:
    idcol = cell(r, hdr, "IdCol")
    if idcol in (None, ""): continue
    cid = num(idcol)
    activo = yes(cell(r, hdr, "Activo"))
    print(f"INSERT INTO colaboradores (id,nombre,apellidos,nif,num_colegiado,"
          f"pct_produccion,aplica_laboratorio,aplica_irpf,ausencia_inicio,ausencia_fin,"
          f"precio_tratamiento_exento,activo,created_at,updated_at) VALUES "
          f"({cid},{q(cell(r,hdr,'Nombre'))},{q(cell(r,hdr,'Apellidos'))},{q(cell(r,hdr,'NIF'))},"
          f"{q(cell(r,hdr,'Nº Colegiado'))},{f(cell(r,hdr,'%Produccion'))},"
          f"{yes(cell(r,hdr,'%laboratorio'))},{yes(cell(r,hdr,'IRPF'))},"
          f"{dt(cell(r,hdr,'Ini_ausencia'))},{dt(cell(r,hdr,'Fin_ausencia'))},"
          f"{f(cell(r,hdr,'PrecioTto_exen'))},{activo},now(),now());")
    print(f"INSERT INTO colaborador_centro (colaborador_id,centro_id,created_at,updated_at) "
          f"VALUES ({cid},1,now(),now());")
    espv = cell(r, hdr, "idEspecia")
    if espv not in (None, ""):
        for part in str(espv).replace(".0", "").split(","):
            p = part.strip()
            if p.isdigit() and 1 <= int(p) <= 12:
                esp_links.append((cid, int(p)))
for cid, eid in esp_links:
    print(f"INSERT INTO colaborador_especialidad (colaborador_id,especialidad_id,created_at,updated_at) "
          f"VALUES ({cid},{eid},now(),now()) ON CONFLICT DO NOTHING;")

# ---- STAFF (Personal_reg) ----
ws = wb["Personal_reg"]; rows = list(ws.iter_rows(values_only=True))
hdr = {str(c).strip(): i for i, c in enumerate(rows[0]) if c is not None}
for r in rows[1:]:
    ids = cell(r, hdr, "IdStaff")
    if ids in (None, ""): continue
    sid = num(ids)
    fbaja = cell(r, hdr, "FecBaja")
    activo = "false" if fbaja not in (None, "") else "true"
    print(f"INSERT INTO usuarios (id,nombre,apellidos,email,username,telefono,tipo_contrato,"
          f"staff_tipo,fecha_alta,fecha_baja,activo,created_at,updated_at) VALUES "
          f"({sid},{q(cell(r,hdr,'Nombre'))},{q(cell(r,hdr,'Apellidos'))},{q(cell(r,hdr,'email'))},"
          f"{q(cell(r,hdr,'username'))},{q(cell(r,hdr,'tel'))},{q(cell(r,hdr,'Tipo Contrato'))},"
          f"{q(cell(r,hdr,'Staff_tipo'))},{dt(cell(r,hdr,'FecAlta'))},{dt(fbaja)},{activo},now(),now());")
    idcol = cell(r, hdr, "IdCol")
    if idcol not in (None, ""):
        print(f"INSERT INTO user_collaborator (usuario_id,colaborador_id,created_at,updated_at) "
              f"VALUES ({sid},{num(idcol)},now(),now()) ON CONFLICT DO NOTHING;")

# reajustar secuencias
print("SELECT setval(pg_get_serial_sequence('colaboradores','id'),(SELECT GREATEST(MAX(id),1) FROM colaboradores));")
print("SELECT setval(pg_get_serial_sequence('usuarios','id'),(SELECT GREATEST(MAX(id),1) FROM usuarios));")
print("COMMIT;")
