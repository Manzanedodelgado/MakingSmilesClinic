"""Catálogo de ENTIDADES para el editor de informes.

Es la fuente de la verdad (allowlist) del editor: define qué tablas se pueden
consultar, con qué campos (crudos o CALCULADOS, p.ej. "última visita" = MAX de los
tratamientos realizados) y qué operadores admite cada tipo. El cliente NUNCA manda
SQL ni nombres de tabla/columna crudos: solo claves de este catálogo → cero inyección.

Cada campo tiene:
  - label : etiqueta para la UI
  - tipo  : texto | numero | fecha | bool   (determina los operadores y el input)
  - sql   : la EXPRESIÓN SQL (columna o subconsulta); solo viene de aquí, jamás del cliente
  - join  : (opcional) clave del join que necesita esa expresión

Cada entidad:
  - base       : cláusula FROM con alias
  - where_base : filtro fijo (scoping multi-tenant por :centro_id)
  - joins      : { clave_join: fragmento LEFT JOIN }  (se añaden solo si se usan)
  - campos     : { clave: {...} }
  - orden_def  : ORDER BY por defecto
  - por_defecto: columnas marcadas al abrir la entidad
"""

# ───────────────────────── operadores por tipo ─────────────────────────
OPERADORES = {
    "texto":  ["contiene", "no_contiene", "igual", "distinto", "empieza", "vacio", "no_vacio"],
    "numero": ["=", "!=", ">", ">=", "<", "<=", "entre", "vacio", "no_vacio"],
    "fecha":  ["antes_de", "despues_de", "entre", "hace_mas_de", "en_los_ultimos", "vacio", "no_vacio"],
    "bool":   ["es_si", "es_no"],
}

# meta para la UI: etiqueta, nº de valores (args) y si pide unidad (días/meses/años)
OPERADOR_META = {
    "contiene":       {"label": "contiene",          "args": 1},
    "no_contiene":    {"label": "no contiene",       "args": 1},
    "igual":          {"label": "es igual a",        "args": 1},
    "distinto":       {"label": "es distinto de",    "args": 1},
    "empieza":        {"label": "empieza por",       "args": 1},
    "=":              {"label": "=",                 "args": 1},
    "!=":             {"label": "≠",                 "args": 1},
    ">":              {"label": ">",                 "args": 1},
    ">=":             {"label": "≥",                 "args": 1},
    "<":              {"label": "<",                 "args": 1},
    "<=":             {"label": "≤",                 "args": 1},
    "entre":          {"label": "entre",             "args": 2},
    "antes_de":       {"label": "es anterior a",     "args": 1, "input": "fecha"},
    "despues_de":     {"label": "es posterior a",    "args": 1, "input": "fecha"},
    "hace_mas_de":    {"label": "hace más de",       "args": 1, "unidad": True},
    "en_los_ultimos": {"label": "en los últimos",    "args": 1, "unidad": True},
    "vacio":          {"label": "está vacío",        "args": 0},
    "no_vacio":       {"label": "no está vacío",     "args": 0},
    "es_si":          {"label": "Sí",                "args": 0},
    "es_no":          {"label": "No",                "args": 0},
}

# nombre del doctor desde usuarios (colaboradores.id == usuarios.id)
_DOCTOR = "TRIM(COALESCE(u.nombre,'') || ' ' || COALESCE(u.apellidos,''))"


def _paciente(alias_col="p"):
    return f"TRIM(COALESCE({alias_col}.apellidos,'') || ', ' || COALESCE({alias_col}.nombre,''))"


ENTIDADES = {
    # ───────────────────────────── PACIENTES ─────────────────────────────
    "pacientes": {
        "label": "Pacientes",
        "base": "pacientes p",
        "where_base": "p.centro_id = :centro_id",
        "joins": {
            # Población/provincia se resuelven por CP contra el catálogo oficial INE
            # (municipios/provincias), NO contra `poblaciones` (legado corrupto —
            # ver auditoría 27-sep-2026) ni contra p.poblacion_id (huérfano, sin
            # endpoint que lo escriba).
            "geografia_cp": "LEFT JOIN codigos_postales_geo cpg ON cpg.cp = p.cp LEFT JOIN municipios mun ON mun.id = cpg.municipio_id LEFT JOIN provincias prov ON prov.id = mun.provincia_id",
        },
        "campos": {
            "num_historia":    {"label": "Nº historia",       "tipo": "texto",  "sql": "p.num_historia"},
            "nombre":          {"label": "Nombre",            "tipo": "texto",  "sql": "p.nombre"},
            "apellidos":       {"label": "Apellidos",         "tipo": "texto",  "sql": "p.apellidos"},
            "nif":             {"label": "NIF",               "tipo": "texto",  "sql": "p.nif"},
            "telefono_movil":  {"label": "Teléfono",          "tipo": "texto",  "sql": "p.telefono_movil"},
            "email":           {"label": "Email",             "tipo": "texto",  "sql": "p.email"},
            "edad":            {"label": "Edad",              "tipo": "numero", "sql": "date_part('year', age(p.fecha_nacimiento))::int"},
            "fecha_nacimiento":{"label": "Fecha nacimiento",  "tipo": "fecha",  "sql": "p.fecha_nacimiento"},
            "fecha_alta":      {"label": "Fecha de alta",     "tipo": "fecha",  "sql": "p.fecha_alta"},
            "poblacion":       {"label": "Población",         "tipo": "texto",  "sql": "mun.nombre", "join": "geografia_cp"},
            "provincia":       {"label": "Provincia",         "tipo": "texto",  "sql": "prov.nombre", "join": "geografia_cp"},
            "cp":              {"label": "Código postal",     "tipo": "texto",  "sql": "p.cp"},
            "activo":          {"label": "Activo",            "tipo": "bool",   "sql": "p.activo"},
            "acepta_whatsapp": {"label": "Acepta WhatsApp",   "tipo": "bool",   "sql": "p.acepta_whatsapp"},
            "acepta_lopd":     {"label": "Acepta LOPD",       "tipo": "bool",   "sql": "p.acepta_lopd"},
            "ultima_visita":   {"label": "Última visita",     "tipo": "fecha",  "sql": "(SELECT MAX(tr.fecha_inicio) FROM tratamientos_realizados tr WHERE tr.paciente_id = p.id AND tr.estado_id = 5)"},
            "ultima_cita":     {"label": "Última cita",       "tipo": "fecha",  "sql": "(SELECT MAX(c.fecha) FROM citas c WHERE c.paciente_id = p.id)"},
            "proxima_cita":    {"label": "Próxima cita",      "tipo": "fecha",  "sql": "(SELECT MIN(c.fecha) FROM citas c WHERE c.paciente_id = p.id AND c.fecha >= CURRENT_DATE)"},
            "deuda_pendiente": {"label": "Deuda pendiente",   "tipo": "numero", "sql": "COALESCE((SELECT SUM(d.importe_pendiente) FROM deudas d WHERE d.paciente_id = p.id AND d.liquidada = false AND d.incobrable = false), 0)"},
            "total_facturado": {"label": "Total facturado",   "tipo": "numero", "sql": "COALESCE((SELECT SUM(tr.importe) FROM tratamientos_realizados tr WHERE tr.paciente_id = p.id AND tr.estado_id = 5), 0)"},
            "num_tratamientos":{"label": "Nº tratamientos",   "tipo": "numero", "sql": "(SELECT COUNT(*) FROM tratamientos_realizados tr WHERE tr.paciente_id = p.id AND tr.estado_id = 5)"},
        },
        "orden_def": "p.apellidos, p.nombre",
        "por_defecto": ["num_historia", "apellidos", "nombre", "telefono_movil", "ultima_visita"],
        # ── RELACIONES (para filtros TIENE / NO TIENE … que cumplen …) ──
        "pk": "p.id",
        "relaciones": {
            "citas": {
                "label": "Citas",
                "base": "citas ch",
                "fk": "ch.paciente_id",
                "joins": {
                    "tipo": "LEFT JOIN tipos_cita tc ON tc.id = ch.tipo_cita_id",
                    "estado": "LEFT JOIN estados_cita ec ON ec.id = ch.estado_id",
                    "doctor": "LEFT JOIN usuarios u ON u.id = ch.colaborador_id",
                },
                "campos": {
                    "tipo_cita":  {"label": "Tipo de cita", "tipo": "texto", "sql": "tc.nombre", "join": "tipo"},
                    "fecha":      {"label": "Fecha",        "tipo": "fecha", "sql": "ch.fecha"},
                    "estado":     {"label": "Estado",       "tipo": "texto", "sql": "ec.nombre", "join": "estado"},
                    "doctor":     {"label": "Doctor",       "tipo": "texto", "sql": _DOCTOR, "join": "doctor"},
                    "confirmada": {"label": "Confirmada",   "tipo": "bool",  "sql": "ch.confirmada"},
                    "asistio":    {"label": "Asistió",      "tipo": "bool",  "sql": "(ch.hora_llegada IS NOT NULL AND ch.hora_llegada <> '')"},
                },
            },
            "realizados": {
                "label": "Tratamientos realizados",
                "base": "tratamientos_realizados ch",
                "fk": "ch.paciente_id",
                "joins": {"tto": "LEFT JOIN tratamientos t ON t.id = ch.tratamiento_id"},
                "campos": {
                    "tratamiento": {"label": "Tratamiento", "tipo": "texto",  "sql": "t.nombre", "join": "tto"},
                    "fecha":       {"label": "Fecha",       "tipo": "fecha",  "sql": "ch.fecha_inicio"},
                    "importe":     {"label": "Importe",     "tipo": "numero", "sql": "ch.importe"},
                    "pieza":       {"label": "Pieza",       "tipo": "texto",  "sql": "ch.piezas"},
                },
            },
            "presupuestos": {
                "label": "Presupuestos",
                "base": "presupuestos ch",
                "fk": "ch.paciente_id",
                "joins": {"estado": "LEFT JOIN estados_presupuesto ep ON ep.id = ch.estado_id"},
                "campos": {
                    "titulo":   {"label": "Título",   "tipo": "texto",  "sql": "ch.titulo"},
                    "estado":   {"label": "Estado",   "tipo": "texto",  "sql": "ep.nombre", "join": "estado"},
                    "total":    {"label": "Total",    "tipo": "numero", "sql": "ch.total"},
                    "fecha":    {"label": "Fecha",    "tipo": "fecha",  "sql": "ch.fecha"},
                    "aprobado": {"label": "Aprobado", "tipo": "bool",   "sql": "ch.aprobado"},
                },
            },
            "pagos": {
                "label": "Pagos",
                "base": "pagos ch",
                "fk": "ch.paciente_id",
                "joins": {},
                "campos": {
                    "importe":    {"label": "Importe",      "tipo": "numero", "sql": "ch.importe"},
                    "forma_pago": {"label": "Forma de pago","tipo": "texto",  "sql": "(SELECT f.nombre FROM formas_pago f WHERE f.id = ch.forma_pago_id)"},
                    "fecha":      {"label": "Fecha",        "tipo": "fecha",  "sql": "ch.fecha"},
                },
            },
            "deudas": {
                "label": "Deudas",
                "base": "deudas ch",
                "fk": "ch.paciente_id",
                "joins": {},
                "campos": {
                    "importe_pendiente": {"label": "Importe pendiente", "tipo": "numero", "sql": "ch.importe_pendiente"},
                    "liquidada":         {"label": "Liquidada",         "tipo": "bool",   "sql": "ch.liquidada"},
                    "incobrable":        {"label": "Incobrable",        "tipo": "bool",   "sql": "ch.incobrable"},
                    "fecha_plazo":       {"label": "Fecha plazo",       "tipo": "fecha",  "sql": "ch.fecha_plazo"},
                },
            },
        },
    },

    # ─────────────────────────────── CITAS ───────────────────────────────
    "citas": {
        "label": "Citas",
        "base": "citas c",
        "where_base": "c.centro_id = :centro_id",
        "joins": {
            "doctor":   "LEFT JOIN usuarios u ON u.id = c.colaborador_id",
            "estado":   "LEFT JOIN estados_cita ec ON ec.id = c.estado_id",
            "gabinete": "LEFT JOIN gabinetes g ON g.id = c.gabinete_id",
            "tipo":     "LEFT JOIN tipos_cita tc ON tc.id = c.tipo_cita_id",
        },
        "campos": {
            "fecha":        {"label": "Fecha",         "tipo": "fecha",  "sql": "c.fecha"},
            "mes":          {"label": "Mes (AAAA-MM)", "tipo": "texto",  "sql": "to_char(c.fecha, 'YYYY-MM')"},
            "anio":         {"label": "Año",           "tipo": "numero", "sql": "date_part('year', c.fecha)::int"},
            "hora":         {"label": "Hora",          "tipo": "texto",  "sql": "c.hora"},
            "paciente":     {"label": "Paciente",      "tipo": "texto",  "sql": "TRIM(COALESCE(c.apellidos,'') || ', ' || COALESCE(c.nombre,''))"},
            "num_historia": {"label": "Nº historia",   "tipo": "texto",  "sql": "c.num_historia"},
            "doctor":       {"label": "Doctor",        "tipo": "texto",  "sql": _DOCTOR, "join": "doctor"},
            "estado":       {"label": "Estado",        "tipo": "texto",  "sql": "ec.nombre", "join": "estado"},
            "tipo_cita":    {"label": "Tipo de cita",  "tipo": "texto",  "sql": "tc.nombre", "join": "tipo"},
            "gabinete":     {"label": "Gabinete",      "tipo": "texto",  "sql": "g.nombre", "join": "gabinete"},
            "duracion_min": {"label": "Duración (min)","tipo": "numero", "sql": "c.duracion_min"},
            "retraso_min":  {"label": "Retraso (min)", "tipo": "numero", "sql": "c.retraso_min"},
            "asistio":      {"label": "Asistió",       "tipo": "bool",   "sql": "(c.hora_llegada IS NOT NULL AND c.hora_llegada <> '')"},
            "confirmada":   {"label": "Confirmada",    "tipo": "bool",   "sql": "c.confirmada"},
            "aceptada":     {"label": "Aceptada",      "tipo": "bool",   "sql": "c.aceptada"},
            "gratuita":     {"label": "Gratuita",      "tipo": "bool",   "sql": "c.gratuita"},
        },
        "orden_def": "c.fecha DESC, c.hora",
        "por_defecto": ["fecha", "hora", "paciente", "doctor", "estado"],
    },

    # ──────────────────────── TRATAMIENTOS REALIZADOS ────────────────────────
    "realizados": {
        "label": "Tratamientos realizados",
        "base": "tratamientos_realizados tr",
        "where_base": "tr.centro_id = :centro_id",
        "joins": {
            "paciente":    "LEFT JOIN pacientes p ON p.id = tr.paciente_id",
            "doctor":      "LEFT JOIN usuarios u ON u.id = tr.colaborador_id",
            "tratamiento": "LEFT JOIN tratamientos t ON t.id = tr.tratamiento_id",
            "estado":      "LEFT JOIN estados_tratamiento et ON et.id = tr.estado_id",
            "deuda":       "LEFT JOIN deudas deu ON deu.tratamiento_realizado_id = tr.id",
        },
        "campos": {
            "fecha":        {"label": "Fecha",        "tipo": "fecha",  "sql": "tr.fecha_inicio"},
            "mes":          {"label": "Mes (AAAA-MM)","tipo": "texto",  "sql": "to_char(tr.fecha_inicio, 'YYYY-MM')"},
            "anio":         {"label": "Año",          "tipo": "numero", "sql": "date_part('year', tr.fecha_inicio)::int"},
            "paciente":     {"label": "Paciente",     "tipo": "texto",  "sql": _paciente("p"), "join": "paciente"},
            "num_historia": {"label": "Nº historia",  "tipo": "texto",  "sql": "p.num_historia", "join": "paciente"},
            "tratamiento":  {"label": "Tratamiento",  "tipo": "texto",  "sql": "t.nombre", "join": "tratamiento"},
            "doctor":       {"label": "Doctor",       "tipo": "texto",  "sql": _DOCTOR, "join": "doctor"},
            "piezas":       {"label": "Piezas",       "tipo": "texto",  "sql": "tr.piezas"},
            "importe":      {"label": "Importe",      "tipo": "numero", "sql": "tr.importe"},
            "descuento":    {"label": "Descuento",    "tipo": "numero", "sql": "tr.descuento"},
            "pendiente":    {"label": "Pendiente",    "tipo": "numero", "sql": "COALESCE(deu.importe_pendiente, tr.pendiente)", "join": "deuda"},
            "abonado":      {"label": "Abonado",      "tipo": "bool",   "sql": "CASE WHEN deu.id IS NOT NULL THEN (deu.liquidada OR deu.importe_pendiente = 0) ELSE (COALESCE(tr.pendiente, 0) = 0) END", "join": "deuda"},
            "tiempo_min":   {"label": "Tiempo (min)", "tipo": "numero", "sql": "tr.tiempo_min"},
            "estado":       {"label": "Estado",       "tipo": "texto",  "sql": "et.nombre", "join": "estado"},
        },
        "orden_def": "tr.fecha_inicio DESC",
        "por_defecto": ["fecha", "paciente", "tratamiento", "doctor", "importe"],
    },

    # ───────────────────────────── PRESUPUESTOS ─────────────────────────────
    "presupuestos": {
        "label": "Presupuestos",
        "base": "presupuestos pr",
        "where_base": "pr.centro_id = :centro_id",
        "joins": {
            "paciente": "LEFT JOIN pacientes p ON p.id = pr.paciente_id",
            "doctor":   "LEFT JOIN usuarios u ON u.id = pr.colaborador_id",
            "estado":   "LEFT JOIN estados_presupuesto ep ON ep.id = pr.estado_id",
        },
        "campos": {
            "num_pre":          {"label": "Nº",               "tipo": "numero", "sql": "pr.num_pre"},
            "fecha":            {"label": "Fecha",            "tipo": "fecha",  "sql": "pr.fecha"},
            "mes":              {"label": "Mes (AAAA-MM)",    "tipo": "texto",  "sql": "to_char(pr.fecha, 'YYYY-MM')"},
            "anio":             {"label": "Año",              "tipo": "numero", "sql": "date_part('year', pr.fecha)::int"},
            "fecha_aceptacion": {"label": "Fecha aceptación", "tipo": "fecha",  "sql": "pr.fecha_aceptacion"},
            "paciente":         {"label": "Paciente",         "tipo": "texto",  "sql": _paciente("p"), "join": "paciente"},
            "num_historia":     {"label": "Nº historia",      "tipo": "texto",  "sql": "p.num_historia", "join": "paciente"},
            "titulo":           {"label": "Título",           "tipo": "texto",  "sql": "pr.titulo"},
            "doctor":           {"label": "Doctor",           "tipo": "texto",  "sql": _DOCTOR, "join": "doctor"},
            "estado":           {"label": "Estado",           "tipo": "texto",  "sql": "ep.nombre", "join": "estado"},
            "total":            {"label": "Total",            "tipo": "numero", "sql": "pr.total"},
            "aprobado":         {"label": "Aprobado",         "tipo": "bool",   "sql": "pr.aprobado"},
        },
        "orden_def": "pr.fecha DESC, pr.num_pre DESC",
        "por_defecto": ["num_pre", "fecha", "paciente", "titulo", "total", "estado"],
    },

    # ─────────────────────────────── PAGOS ───────────────────────────────
    "pagos": {
        "label": "Pagos",
        "base": "pagos pg",
        "where_base": "pg.centro_id = :centro_id",
        "joins": {
            "paciente": "LEFT JOIN pacientes p ON p.id = pg.paciente_id",
        },
        "campos": {
            "fecha":        {"label": "Fecha",        "tipo": "fecha",  "sql": "pg.fecha"},
            "mes":          {"label": "Mes (AAAA-MM)","tipo": "texto",  "sql": "to_char(pg.fecha, 'YYYY-MM')"},
            "anio":         {"label": "Año",          "tipo": "numero", "sql": "date_part('year', pg.fecha)::int"},
            "paciente":     {"label": "Paciente",     "tipo": "texto",  "sql": _paciente("p"), "join": "paciente"},
            "num_historia": {"label": "Nº historia",  "tipo": "texto",  "sql": "p.num_historia", "join": "paciente"},
            "importe":      {"label": "Importe",      "tipo": "numero", "sql": "pg.importe"},
            "forma_pago":   {"label": "Forma de pago","tipo": "texto",  "sql": "(SELECT f.nombre FROM formas_pago f WHERE f.id = pg.forma_pago_id)"},
            "num_recibo":   {"label": "Nº recibo",    "tipo": "texto",  "sql": "pg.num_recibo"},
            "num_factura":  {"label": "Nº factura",   "tipo": "texto",  "sql": "pg.num_factura"},
            "anulado":      {"label": "Anulado",      "tipo": "bool",   "sql": "pg.anulado"},
            "liquidado":    {"label": "Liquidado",    "tipo": "bool",   "sql": "pg.liquidado"},
        },
        "orden_def": "pg.fecha DESC",
        "por_defecto": ["fecha", "paciente", "importe", "forma_pago"],
    },

    # ─────────────────────────────── DEUDAS ───────────────────────────────
    "deudas": {
        "label": "Deudas",
        "base": "deudas d",
        "where_base": "d.centro_id = :centro_id",
        "joins": {
            "paciente": "LEFT JOIN pacientes p ON p.id = d.paciente_id",
        },
        "campos": {
            "fecha_plazo":       {"label": "Fecha plazo",       "tipo": "fecha",  "sql": "d.fecha_plazo"},
            "mes":               {"label": "Mes (AAAA-MM)",     "tipo": "texto",  "sql": "to_char(d.fecha_plazo, 'YYYY-MM')"},
            "anio":              {"label": "Año",               "tipo": "numero", "sql": "date_part('year', d.fecha_plazo)::int"},
            "paciente":          {"label": "Paciente",          "tipo": "texto",  "sql": _paciente("p"), "join": "paciente"},
            "num_historia":      {"label": "Nº historia",       "tipo": "texto",  "sql": "p.num_historia", "join": "paciente"},
            "adeudo":            {"label": "Adeudo",            "tipo": "numero", "sql": "d.adeudo"},
            "importe_pendiente": {"label": "Importe pendiente", "tipo": "numero", "sql": "d.importe_pendiente"},
            "modalidad":         {"label": "Modalidad",         "tipo": "texto",  "sql": "d.modalidad"},
            "num_factura":       {"label": "Nº factura",        "tipo": "texto",  "sql": "d.num_factura"},
            "liquidada":         {"label": "Liquidada",         "tipo": "bool",   "sql": "d.liquidada"},
            "incobrable":        {"label": "Incobrable",        "tipo": "bool",   "sql": "d.incobrable"},
        },
        "orden_def": "d.fecha_plazo",
        "por_defecto": ["fecha_plazo", "paciente", "importe_pendiente", "liquidada"],
    },
}
