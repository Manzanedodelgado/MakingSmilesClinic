from sqlmodel import Session, select

from application.services.seed_capacidades import seed_capacidades_alex
from domain.models.agentes import CapacidadCatalogo


CLAVES_ALEX_ESPERADAS = {
    "consultar_mis_citas",
    "consultar_tratamientos_pendientes",
    "crear_cita",
    "modificar_cita",
    "enviar_presupuesto",
    "enviar_factura",
    "enviar_recibo",
    "enviar_justificante",
    "escalar_a_humano",
}


def test_seed_crea_las_nueve_capacidades_reales_de_alex(session: Session):
    creadas = seed_capacidades_alex(session)
    assert {c.clave for c in creadas} == CLAVES_ALEX_ESPERADAS
    assert len(creadas) == 9

    en_bd = session.exec(select(CapacidadCatalogo)).all()
    assert {c.clave for c in en_bd} == CLAVES_ALEX_ESPERADAS


def test_seed_no_crea_presupuesto_por_dictado(session: Session):
    # Alex no crea presupuestos en producción, solo los envía — confirmado
    # explícitamente por el usuario en la sesión de trabajo previa.
    seed_capacidades_alex(session)
    en_bd = session.exec(select(CapacidadCatalogo)).all()
    assert "crear_presupuesto" not in {c.clave for c in en_bd}


def test_seed_es_idempotente(session: Session):
    seed_capacidades_alex(session)
    seed_capacidades_alex(session)
    en_bd = session.exec(select(CapacidadCatalogo)).all()
    assert len(en_bd) == 9


def test_seed_segunda_llamada_no_reporta_nada_creado(session: Session):
    # La función debe devolver lo que ELLA crea en esta llamada, no el
    # catálogo completo: si ya existen las 9 capacidades, una segunda
    # llamada no crea nada y debe devolver una lista vacía.
    primera = seed_capacidades_alex(session)
    assert len(primera) == 9

    segunda = seed_capacidades_alex(session)
    assert segunda == []
