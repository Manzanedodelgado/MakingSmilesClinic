from sqlmodel import Session, select

from application.services.capacidades_service import herramientas_de
from domain.models.agentes import Agente, CapacidadCatalogo, AgenteCapacidad
from domain.models.core import Centro


def _crear_agente_con_dos_capacidades(session: Session, activa_segunda: bool) -> int:
    centro = session.exec(select(Centro)).first()
    agente = Agente(
        centro_id=centro.id, nombre="Alex", audiencia="paciente", activo=True,
        modo_activacion="manual", config_key="agente.alex", es_agente_base=True,
    )
    session.add(agente)
    session.commit()
    session.refresh(agente)

    cap1 = CapacidadCatalogo(
        clave="crear_cita", descripcion="Crea una cita real.",
        ejecutor="AgenteService.ejecutar_tool:crear_cita",
        parametros={"type": "object", "properties": {"fecha": {"type": "string"}}, "required": ["fecha"]},
    )
    cap2 = CapacidadCatalogo(
        clave="enviar_factura", descripcion="Pide al equipo que envíe una factura.",
        ejecutor="agente_service.enviar_factura", parametros={"type": "object", "properties": {}},
    )
    session.add(cap1)
    session.add(cap2)
    session.commit()
    session.refresh(cap1)
    session.refresh(cap2)

    session.add(AgenteCapacidad(agente_id=agente.id, capacidad_id=cap1.id, activa=True))
    session.add(AgenteCapacidad(agente_id=agente.id, capacidad_id=cap2.id, activa=activa_segunda))
    session.commit()
    return agente.id


def test_herramientas_de_solo_devuelve_capacidades_activas(session: Session):
    agente_id = _crear_agente_con_dos_capacidades(session, activa_segunda=False)

    tools = herramientas_de(session, agente_id)

    nombres = {t["function"]["name"] for t in tools}
    assert nombres == {"crear_cita"}
    assert tools[0]["type"] == "function"
    from application.services.capacidades_service import _esquemas_del_codigo
    esperada = _esquemas_del_codigo().get("crear_cita", {}).get("function", {}).get("description") or "Crea una cita real."
    assert tools[0]["function"]["description"] == esperada   # manda el código si la define
    requeridos = (_esquemas_del_codigo().get("crear_cita", {}).get("function", {})
                  .get("parameters", {}).get("required")) or ["fecha"]
    assert tools[0]["function"]["parameters"]["required"] == requeridos   # esquema del código


def test_herramientas_de_devuelve_ambas_si_ambas_activas(session: Session):
    agente_id = _crear_agente_con_dos_capacidades(session, activa_segunda=True)

    tools = herramientas_de(session, agente_id)

    nombres = {t["function"]["name"] for t in tools}
    assert nombres == {"crear_cita", "enviar_factura"}


def test_herramientas_de_agente_sin_capacidades_devuelve_lista_vacia(session: Session):
    centro = session.exec(select(Centro)).first()
    agente = Agente(
        centro_id=centro.id, nombre="Nuevo", audiencia="staff", activo=True,
        modo_activacion="manual", config_key="agente.nuevo",
    )
    session.add(agente)
    session.commit()
    session.refresh(agente)

    assert herramientas_de(session, agente.id) == []
