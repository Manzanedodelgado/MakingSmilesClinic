"""GESTOR IA conversacional — el equipo de administración le habla en lenguaje natural y él
consulta la gestoría con sus herramientas. Construido sobre `AgenteConversacional` (el mismo
motor de chat que Victor y Aura).

El Gestor del chat es de SOLO LECTURA: responde consultando el informe contable (Debe/Haber, facturas y pagos de pacientes), pero
no corrige, enlaza ni borra nada. Los cambios los hace una persona en la pantalla de Gestoría
(que sí aplica sus permisos de edición). Es la misma regla de Victor: "la IA propone, la persona
dispone", aquí llevada al extremo porque tocar contabilidad sin una persona delante es justo lo
que no se debe hacer.
"""
from __future__ import annotations

import json
import re
from datetime import date

from sqlalchemy import text
from sqlmodel import Session

from application.services.agente_conversacional import AgenteConversacional

SYSTEM = (
    "Eres el Gestor IA de una clínica dental: el asistente de la gestoría y la administración. "
    "Hablas con el EQUIPO de administración, nunca con pacientes. Tono directo y profesional, "
    "frases cortas, sin jerga técnica.\n\n"
    "PRESENTACIÓN: cuando saludan o preguntan qué puedes hacer, te presentas como el Gestor IA y "
    "das este desglose de lo que pueden pedirte: (a) Debe: lo que sale del banco, por mes y año; "
    "(b) Haber: lo que entra en el banco, por mes y año; (c) Facturas: totales por mes, año, "
    "forma de pago y estado; (d) Pagos de pacientes: totales por mes, año y forma de pago "
    "(efectivo, tarjeta, transferencia…); (e) comparar meses o años. Aclaras que solo consultas el informe contable, que se actualiza "
    "solo, y que no cambias nada.\n\n"
    "QUÉ HACES: respondes con datos reales sobre el banco (Debe y Haber), las facturas y los "
    "pagos de pacientes consultando el INFORME CONTABLE (herramienta "
    "informe_contable e informe_gastos): son informes ya hechos que se actualizan solos y son tu ÚNICA fuente. Nunca "
    "inventes importes ni fechas. Si el informe no tiene lo que piden (por ejemplo proveedores, "
    "descuadres o una factura concreta), dilo y di que eso se mira en la pantalla de Gestoría.\n\n"
    "VOCABULARIO (úsalo exacto):\n"
    "- APUNTE = una línea del banco. Los apuntes con importe negativo son el DEBE (salidas) y "
    "los positivos el HABER (entradas). Son datos del banco: no se editan ni se duplican.\n"
    "- FACTURA = el justificante de un apunte del Debe. Cada apunte del Debe tiene su "
    "justificante; a veces son varias facturas del mismo proveedor cuya suma completa el apunte.\n"
    "- Una factura repetida es la que coincide en fecha, importe, proveedor y número de factura.\n"
    "- Un gasto es todo lo que resta dinero de la cuenta (todo el Debe).\n\n"
    "REGLAS DURAS:\n"
    "(1) TÚ NO CAMBIAS NADA. No corriges, enlazas, borras ni creas facturas ni apuntes. Si "
    "algo hay que arreglar, lo explicas y dices qué haría una persona en la pantalla de "
    "Gestoría; nunca digas que ya está hecho.\n"
    "(1b) El Debe y el Haber son la verdad: NUNCA dudes de ellos, NUNCA digas que no los has "
    "podido comprobar ni propongas contrastarlos con el extracto o el saldo del banco, y NUNCA "
    "añadas apartados de 'lo que no pude comprobar' sobre ellos. Responde con las cifras del "
    "informe, sin disculpas ni reservas.\n"
    "(1c) PAGOS DE PACIENTES: solo informas de TOTALES por mes, año y forma de pago. NUNCA de "
    "pagos concretos (importe, fecha o recibo de un paciente) ni de nombres de pacientes. Si te "
    "piden el pago de un paciente, dices que solo das totales mensuales y por forma de pago, y "
    "que el detalle está en la pestaña Pagos de Gestoría.\n"
    "(1d) LIQUIDACIONES (cobros con tarjeta que el banco ingresa agrupados): cuando haya que "
    "verificarlas, di que FALTA EL DESGLOSE DE CADA LIQUIDACIÓN para poder comprobarlas; no "
    "supongas comisiones ni causas.\n"
    "(1e) GASTOS: se informan TODOS conciliados (cada gasto sale de un Debe; el efectivo y la "
    "tarjeta de Juan Antonio no pasan por el banco pero cuentan como gasto). Los das por año, "
    "mes, forma de pago y proveedor con la herramienta informe_gastos. Los gastos en metálico y "
    "con tarjeta son el único gasto que no está en el Debe.\n"
    "(1f) JUAN ANTONIO MANZANEDO: (a) es colaborador con facturas MENSUALES por su trabajo; "
    "(b) también tiene a su nombre facturas de internet e IA: cuentan como gasto y se pagan con "
    "su tarjeta; (c) puede aparecer como quien INGRESA el efectivo en la cuenta; (d) puede ser "
    "intermediario en transferencias para pagar ortodoncias, nóminas o facturas de otros "
    "doctores. Cuando pregunten por Juan Antonio, usa SIEMPRE pagos_juan_antonio y DETALLA cada pago: "
    "fecha, importe, tipo, concepto del banco y, si tiene, la factura; marca los justificantes "
    "provisionales (justificanteProvisional). Da el resumen por tipo y la lista de líneas "
    "(si hay más de las mostradas, dilo y ofrece filtrar por año o mes). No mezcles pagos que "
    "recibe con ingresos que hace. No inventes el motivo de una transferencia: si el tipo es "
    "'ver concepto', cita el concepto tal cual. Nunca pongas como 'total' una cifra filtrada por proveedor: para el total de gastos "
    "llama a informe_gastos SIN proveedor. No repitas avisos ni digas 'como te comenté'; da el "
    "aviso de Juan Antonio una sola vez y solo si la pregunta es sobre él.\n"
    "(1g) SITUACIÓN GLOBAL: si piden la situación de la clínica, resume por año o mes: Haber, "
    "Debe, gastos (informe_gastos sin filtros), y cobros de pacientes por forma de pago.\n"
    "(1h) ANTES de responder con cifras, LLAMA a las herramientas (informe_contable e "
    "informe_gastos) en ese mismo turno. NUNCA escribas marcadores como [Cifra del informe] ni "
    "digas 'voy a consultar': consulta y responde ya con los números. No preguntes si quieren "
    "el desglose: dalo.\n"
    "(2) Da las cifras con la unidad y el periodo (€ y fechas). Si hay muchos resultados, "
    "resume y ofrece el detalle.\n"
    "(3) No entras en agenda, pacientes ni datos clínicos: eso es de Victor y de Alex.\n"
    "(4) Las fechas se te dan ya resueltas en el contexto; si el usuario dice 'este año' o "
    "'el mes pasado', usa esas fechas, no las calcules tú.\n"
    "(5) Tu identidad es el Gestor IA de esta clínica — nada más. Si te preguntan qué modelo "
    "de IA eres o quién te creó, responde SIEMPRE que eres el Gestor IA; NUNCA digas que eres "
    "Claude, GPT, Gemini, Llama, Anthropic, OpenAI ni ningún otro modelo o empresa de IA."
)

TOOLS = [
    {"type": "function", "function": {
        "name": "pagos_juan_antonio",
        "description": "Detalle LÍNEA A LÍNEA de Juan Antonio Manzanedo: transferencias del banco a su "
                       "favor (debe), lo que él ingresa en la cuenta (haber: efectivo o transferencia) y "
                       "sus gastos de internet/IA con su tarjeta (tarjeta). Cada línea trae fecha, "
                       "importe, tipo, concepto del banco y factura.",
        "parameters": {"type": "object", "properties": {
            "origen": {"type": "string", "enum": ["debe", "haber", "tarjeta"], "description": "Si se omite, los tres."},
            "anyo": {"type": "integer"}, "mes": {"type": "integer", "description": "1-12"},
            "limite": {"type": "integer", "description": "Máximo de líneas (30 por defecto, máx. 80)."}}}}},
    {"type": "function", "function": {
        "name": "informe_gastos",
        "description": "Gastos CONCILIADOS (todos salen del Debe, más efectivo y tarjeta de Juan "
                       "Antonio) por año, mes, proveedor y forma de pago.",
        "parameters": {"type": "object", "properties": {
            "agrupar_por": {"type": "string", "enum": ["anyo", "mes", "proveedor", "forma_pago", "categoria"],
                            "description": "Cómo agrupar. Por defecto, mes."},
            "anyo": {"type": "integer", "description": "Año. Si se omite, todos."},
            "mes": {"type": "integer", "description": "Mes 1-12."},
            "proveedor": {"type": "string", "description": "Parte del nombre del proveedor."},
            "forma_pago": {"type": "string", "description": "Forma de pago (Transferencia, Metálico…)."},
            "limite": {"type": "integer", "description": "Máximo de filas (por defecto 30, máx. 100)."}}}}},
    {"type": "function", "function": {
        "name": "informe_contable",
        "description": "Consulta el INFORME CONTABLE (siempre al día): totales por mes y año de Debe "
                       "(salidas del banco), Haber (entradas), facturas (por forma de pago y estado) y "
                       "pagos de pacientes (por forma de pago). Sin 'mes' devuelve un total por mes.",
        "parameters": {"type": "object", "properties": {
            "seccion": {"type": "string", "enum": ["debe", "haber", "facturas", "pagos_pacientes"],
                        "description": "Qué parte del informe. Si se omite, las cuatro."},
            "anyo": {"type": "integer", "description": "Año. Por defecto, el actual."},
            "mes": {"type": "integer", "description": "Mes 1-12. Si se omite, todos los meses del año."},
            "forma_pago": {"type": "string",
                           "description": "Filtra por forma de pago (Efectivo, Tarjeta, Transferencia, Bizum…). "
                                          "Solo facturas y pagos de pacientes."}}}}},
]


class GestorAgente(AgenteConversacional):
    agente_id = "gestor"
    config_key = "gestor.config"
    config_sistema = "gestor"
    exige_consulta = True

    def respuesta_sin_consultar(self, texto: str) -> bool:
        """Importes inventados o 'consultando…' sin haber llamado al informe."""
        return bool(re.search(r"\d[\d.,]*\s*€|\[[^\]]*cifra|consultando|voy a consultar", texto or "", re.I))

    def __init__(self, session: Session, centro_id: int):
        super().__init__(session, centro_id)

    def system(self) -> str:
        hoy = date.today()
        contexto = (f"\n\nFECHAS: hoy = {hoy.isoformat()}; este año = {hoy.year}-01-01 a {hoy.isoformat()}.")
        return SYSTEM + contexto

    def herramientas(self) -> list[dict]:
        return TOOLS

    # ── consultas (todas de solo lectura y acotadas al centro) ──────────────────
    def _q(self, sql: str, **p) -> list[dict]:
        r = self.s.execute(text(sql), {"c": self.centro_id, **p})
        return [dict(x._mapping) for x in r]

    def _pagos_juan_antonio(self, a: dict) -> dict:
        origen = a.get("origen")
        if origen not in (None, "debe", "haber", "tarjeta"):
            return {"error": "origen debe ser debe, haber o tarjeta."}
        try:
            anyo = int(a["anyo"]) if a.get("anyo") else None
            mes = int(a["mes"]) if a.get("mes") else None
            lim = max(1, min(int(a.get("limite") or 30), 80))
        except (TypeError, ValueError):  # raiz: año/mes/límite de pagos_juan_antonio no numéricos; se devuelve error de parámetros al LLM
            return {"error": "Año, mes o límite no válidos."}
        w = ("centro_id = :c AND (CAST(:o AS text) IS NULL OR origen = :o) AND (CAST(:y AS int) IS NULL OR anyo = :y) "
             "AND (CAST(:m AS int) IS NULL OR mes = :m)")
        p = dict(o=origen, y=anyo, m=mes)
        tot = self._q(f"SELECT origen, tipo, COUNT(*) AS n, SUM(importe) AS t FROM informe_juan_antonio WHERE {w} "
                      "GROUP BY 1, 2 ORDER BY 1, 4 DESC", **p)
        filas = self._q(f"SELECT origen, fecha, importe, tipo, concepto, apunte_id, factura, es_simulacion "
                        f"FROM informe_juan_antonio WHERE {w} ORDER BY fecha DESC LIMIT :l", l=lim, **p)
        return {"resumenPorTipo": [{"origen": x["origen"], "tipo": x["tipo"], "n": int(x["n"]),
                                    "total": round(float(x["t"] or 0), 2)} for x in tot],
                "lineas": [{"origen": x["origen"], "fecha": str(x["fecha"]), "importe": round(float(x["importe"] or 0), 2),
                            "tipo": x["tipo"], "concepto": (x["concepto"] or "")[:140], "apunte": x["apunte_id"],
                            "factura": x["factura"], "justificanteProvisional": bool(x["es_simulacion"])} for x in filas],
                "mostradas": len(filas)}

    def _informe_gastos(self, a: dict) -> dict:
        col = {"anyo": "anyo", "mes": "mes", "proveedor": "proveedor",
               "forma_pago": "forma_pago", "categoria": "categoria"}.get(a.get("agrupar_por") or "mes")
        if not col:
            return {"error": "agrupar_por debe ser anyo, mes, proveedor, forma_pago o categoria."}
        try:
            anyo = int(a["anyo"]) if a.get("anyo") else None
            mes = int(a["mes"]) if a.get("mes") else None
            lim = max(1, min(int(a.get("limite") or 30), 100))
        except (TypeError, ValueError):  # raiz: año/mes/límite del informe de gastos no numéricos; se devuelve error de parámetros al LLM
            return {"error": "Año, mes o límite no válidos."}
        prov = f"%{str(a.get('proveedor') or '').strip().lower()}%" if a.get("proveedor") else None
        forma = str(a.get("forma_pago") or "").strip().lower() or None
        where = ("centro_id = :c AND (CAST(:y AS int) IS NULL OR anyo = :y) AND (CAST(:m AS int) IS NULL OR mes = :m) "
                 "AND (CAST(:p AS text) IS NULL OR LOWER(proveedor) LIKE :p) "
                 "AND (CAST(:f AS text) IS NULL OR LOWER(forma_pago) = :f)")
        orden = "importe DESC" if col in ("proveedor", "forma_pago", "categoria") else "1"
        filas = self._q(f"SELECT {col} AS clave, SUM(n) AS n, SUM(importe) AS importe FROM informe_gastos "
                        f"WHERE {where} GROUP BY 1 ORDER BY {orden} LIMIT :l", y=anyo, m=mes, p=prov, f=forma, l=lim)
        tot = self._q(f"SELECT COALESCE(SUM(n), 0) AS n, COALESCE(SUM(importe), 0) AS t FROM informe_gastos WHERE {where}",
                      y=anyo, m=mes, p=prov, f=forma)[0]
        return {"agrupadoPor": col, "gastosTotal": round(float(tot["t"]), 2), "facturas": int(tot["n"]),
                "filas": [{"clave": x["clave"], "n": int(x["n"]), "importe": round(float(x["importe"] or 0), 2)} for x in filas]}

    def _informe_contable(self, a: dict) -> dict:
        hoy = date.today()
        try:
            anyo = int(a.get("anyo") or hoy.year)
            mes = int(a["mes"]) if a.get("mes") else None
        except (TypeError, ValueError):  # raiz: año o mes del informe contable no numéricos; se devuelve error de parámetros al LLM
            return {"error": "Año o mes no válidos."}
        if mes is not None and not 1 <= mes <= 12:
            return {"error": "El mes debe ser de 1 a 12."}
        seccion = a.get("seccion")
        if seccion not in (None, "debe", "haber", "facturas", "pagos_pacientes"):
            return {"error": "Sección no válida: debe, haber, facturas o pagos_pacientes."}
        forma = str(a.get("forma_pago") or "").strip().lower() or None
        filas = self._q(
            "SELECT seccion, mes, forma_pago, SUM(n) AS n, SUM(importe) AS importe FROM informe_contable "
            "WHERE centro_id = :c AND anyo = :y AND (CAST(:m AS int) IS NULL OR mes = :m) "
            "AND (CAST(:s AS text) IS NULL OR seccion = :s) "
            "AND (CAST(:f AS text) IS NULL OR LOWER(COALESCE(forma_pago, '')) = :f) "
            "GROUP BY seccion, mes, forma_pago ORDER BY seccion, mes, forma_pago",
            y=anyo, m=mes, s=seccion, f=forma)
        totales: dict[str, float] = {}
        for x in filas:
            totales[x["seccion"]] = round(totales.get(x["seccion"], 0.0) + float(x["importe"] or 0), 2)
        return {"anyo": anyo, "mes": mes, "totalesPorSeccion": totales,
                "filas": [{"seccion": x["seccion"], "mes": x["mes"], "formaPago": x["forma_pago"],
                           "n": int(x["n"]), "importe": round(float(x["importe"] or 0), 2)} for x in filas[:200]],
                "truncado": len(filas) > 200}

    def ejecutar(self, nombre: str, args: dict) -> str:
        """Despacha la herramienta. Todas son lecturas: no hay ninguna que escriba."""
        try:
            fn = {"informe_contable": self._informe_contable, "informe_gastos": self._informe_gastos,
                  "pagos_juan_antonio": self._pagos_juan_antonio}.get(nombre)
            r = fn(args or {}) if fn else {"error": f"herramienta desconocida: {nombre}"}
        except Exception as e:  # raiz: fallo ejecutando la herramienta (SQL, informe o argumentos); el error vuelve al LLM sin tumbar la conversación  # noqa: BLE001
            r = {"error": str(e)}
        return json.dumps(r, ensure_ascii=False, default=str)
