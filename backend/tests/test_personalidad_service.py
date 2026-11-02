from sqlmodel import Session, select

from application.services.personalidad_service import get_personalidad, prompt_para, upsert_personalidad
from domain.models.agentes import Agente, AgentePersonalidad
from domain.models.core import Centro


def _agente(session: Session) -> Agente:
    centro = session.exec(select(Centro)).first()
    ag = Agente(centro_id=centro.id, nombre="Alex", audiencia="paciente", config_key="agente.alex", es_agente_base=True)
    session.add(ag)
    session.commit()
    session.refresh(ag)
    return ag


def test_upsert_y_prompt_base_mas_aprendida(session: Session):
    ag = _agente(session)
    upsert_personalidad(session, ag.id, "base", tono="Tono base serio.", cercania=1, bienvenida="Hola, soy Alex")
    upsert_personalidad(session, ag.id, "aprendida", tono="Sé más cercano.", cercania=5, regla_extra="No uses emojis.")

    prompt = prompt_para(session, ag.id)
    assert "Tono base serio" in prompt
    assert "Sé más cercano" in prompt
    assert "No uses emojis" in prompt
    # base no se pisa al insertar aprendida
    base = get_personalidad(session, ag.id, "base")
    assert base.cercania == 1
    aprendida = get_personalidad(session, ag.id, "aprendida")
    assert aprendida.cercania == 5
    # base + aprendida con separador
    assert "[Aprendido]" in prompt


def test_prompt_solo_base_si_no_aprendida(session: Session):
    ag = _agente(session)
    upsert_personalidad(session, ag.id, "base", tono="Solo base")
    prompt = prompt_para(session, ag.id)
    assert prompt == "Solo base"
    assert "[Aprendido]" not in prompt


def test_upsert_actualiza_sin_duplicar(session: Session):
    ag = _agente(session)
    upsert_personalidad(session, ag.id, "base", tono="v1")
    upsert_personalidad(session, ag.id, "base", tono="v2")
    filas = session.exec(select(AgentePersonalidad).where(AgentePersonalidad.agente_id == ag.id, AgentePersonalidad.capa == "base")).all()
    assert len(filas) == 1
    assert filas[0].tono == "v2"


def test_prompt_vacio_si_sin_personalidad(session: Session):
    ag = _agente(session)
    assert prompt_para(session, ag.id) == ""
