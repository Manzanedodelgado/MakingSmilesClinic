"""Siembra el catálogo de capacidades con las capacidades reales de Alex,
verificadas contra el código de application/services/agente_service.py en la
sesión de trabajo previa a este plan. Idempotente: no duplica si ya existen.
"""
from sqlmodel import Session, select

from domain.models.agentes import CapacidadCatalogo

_CAPACIDADES_ALEX = [
    {
        "clave": "consultar_mis_citas",
        "descripcion": "Consultar las próximas citas del paciente",
        "ejecutor": "AgenteService.ejecutar_tool:consultar_mis_citas",
        "parametros": {"type": "object", "properties": {}},
    },
    {
        "clave": "consultar_tratamientos_pendientes",
        "descripcion": "Consultar tratamientos pendientes del paciente",
        "ejecutor": "AgenteService.ejecutar_tool:consultar_tratamientos_pendientes",
        "parametros": {"type": "object", "properties": {}},
    },
    {
        "clave": "crear_cita",
        "descripcion": "Crea una cita REAL en un hueco devuelto por consultar_disponibilidad.",
        "ejecutor": "AgenteService.ejecutar_tool:crear_cita",
        "parametros": {
            "type": "object",
            "properties": {
                "fecha": {"type": "string", "description": "YYYY-MM-DD de un hueco libre."},
                "hora": {"type": "string", "description": "HH:MM de un hueco libre."},
                "motivo": {"type": "string", "description": "Motivo/servicio (ej. revisión)."},
            },
            "required": ["fecha", "hora"],
        },
    },
    {
        "clave": "modificar_cita",
        "descripcion": "Cambia la fecha/hora de la próxima cita del paciente",
        "ejecutor": "AgenteService.ejecutar_tool:modificar_cita",
        "parametros": {
            "type": "object",
            "properties": {
                "fecha": {"type": "string", "description": "YYYY-MM-DD de un hueco libre."},
                "hora": {"type": "string", "description": "HH:MM de un hueco libre."},
            },
            "required": ["fecha", "hora"],
        },
    },
    {
        "clave": "enviar_presupuesto",
        "descripcion": "Pedir al equipo que envíe el presupuesto al paciente",
        "ejecutor": "AgenteService.ejecutar_tool:enviar_presupuesto",
        "parametros": {"type": "object", "properties": {}},
    },
    {
        "clave": "enviar_factura",
        "descripcion": "Pedir al equipo que envíe una factura al paciente",
        "ejecutor": "AgenteService.ejecutar_tool:enviar_factura",
        "parametros": {"type": "object", "properties": {}},
    },
    {
        "clave": "enviar_recibo",
        "descripcion": "Pedir al equipo que envíe un recibo al paciente",
        "ejecutor": "AgenteService.ejecutar_tool:enviar_recibo",
        "parametros": {"type": "object", "properties": {}},
    },
    {
        "clave": "enviar_justificante",
        "descripcion": "Pedir al equipo un justificante de asistencia",
        "ejecutor": "AgenteService.ejecutar_tool:enviar_justificante",
        "parametros": {"type": "object", "properties": {}},
    },
    {
        "clave": "escalar_a_humano",
        "descripcion": "Avisar a una persona del equipo (urgencia, queja, petición de humano)",
        "ejecutor": "AgenteService.ejecutar_tool:escalar_a_humano",
        "parametros": {
            "type": "object",
            "properties": {"motivo": {"type": "string"}},
            "required": ["motivo"],
        },
    },
]


def seed_capacidades_alex(session: Session) -> list[CapacidadCatalogo]:
    existentes = {c.clave for c in session.exec(select(CapacidadCatalogo)).all()}
    creadas = []
    for datos in _CAPACIDADES_ALEX:
        if datos["clave"] in existentes:
            continue
        fila = CapacidadCatalogo(**datos)
        session.add(fila)
        creadas.append(fila)
    session.commit()
    for fila in creadas:
        session.refresh(fila)
    return creadas
