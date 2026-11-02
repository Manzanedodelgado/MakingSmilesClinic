from sqlmodel import Session, select

from application.services.agente_service import AgenteService
from application.services.aura_agente import AuraAgente
from application.services.victor_agente import VictorAgente
from domain.models.agentes import Agente, CapacidadCatalogo, AgenteCapacidad
from domain.models.core import Centro


def _seed_alex_tools(session: Session, centro_id: int, activas: list[str]) -> Agente:
    ag = Agente(centro_id=centro_id, nombre="Alex", audiencia="paciente", config_key="agente.alex", es_agente_base=True, activo=True)
    session.add(ag); session.commit(); session.refresh(ag)
    for clave in activas:
        cap = session.exec(select(CapacidadCatalogo).where(CapacidadCatalogo.clave == clave)).first()
        if not cap:
            cap = CapacidadCatalogo(clave=clave, descripcion=clave, ejecutor=f"x:{clave}", parametros={"type":"object","properties":{}})
            session.add(cap); session.commit(); session.refresh(cap)
        session.add(AgenteCapacidad(agente_id=ag.id, capacidad_id=cap.id, activa=True))
    session.commit()
    return ag


def test_tools_para_db_vs_fallback(session: Session):
    centro = session.exec(select(Centro)).first()
    svc = AgenteService(session)
    # Sin Agente en DB -> fallback legacy (todas)
    tools_fallback = svc._tools_para(centro.id, es_staff=True)
    assert len(tools_fallback) > 0

    # Con Agente y solo 1 capacidad activa -> DB manda
    _seed_alex_tools(session, centro.id, ["crear_cita"])
    tools_db = svc._tools_para(centro.id, es_staff=True)
    nombres = {t["function"]["name"] for t in tools_db}
    assert "crear_cita" in nombres
    # crear_cita activa arrastra consultar_disponibilidad como derivada (ver agente_service.py:347-353)
    # igual que en fallback legacy — DB debe devolver ambas.
    assert len(tools_db) == 2
    assert nombres == {"crear_cita", "consultar_disponibilidad"}


def test_victor_y_aura_herramientas_db(session: Session):
    centro = session.exec(select(Centro)).first()
    # Victor sin DB -> TOOLS fijas
    v = VictorAgente(session, centro.id)
    assert len(v.herramientas()) == 3
    # Aura sin DB -> su catálogo del código entero
    a = AuraAgente(session, centro.id)
    from application.services.aura_agente import TOOLS as AURA_TOOLS
    assert len(a.herramientas()) == len(AURA_TOOLS)

    # Si creamos Agente Aura con solo 1 capacidad, DB manda
    from domain.models.agentes import Agente as Ag
    ag = Ag(centro_id=centro.id, nombre="Aura", audiencia="superuser", config_key="aura.config", es_agente_base=True)
    session.add(ag); session.commit(); session.refresh(ag)
    cap = session.exec(select(CapacidadCatalogo).where(CapacidadCatalogo.clave == "consultar_metricas")).first()
    if not cap:
        cap = CapacidadCatalogo(clave="consultar_metricas", descripcion="x", ejecutor="x", parametros={"type":"object","properties":{}})
        session.add(cap); session.commit(); session.refresh(cap)
    session.add(AgenteCapacidad(agente_id=ag.id, capacidad_id=cap.id, activa=True))
    session.commit()
    a2 = AuraAgente(session, centro.id)
    tools = a2.herramientas()
    assert {t["function"]["name"] for t in tools} == {"consultar_metricas"}
