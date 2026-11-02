from sqlmodel import Session, select

from application.services.agente_permisos_service import grant, puede_editar, puede_ver
from application.services.canal_ajuste_service import ajuste_para, aplicar_ajuste, upsert_ajuste
from application.services.personalidad_service import prompt_para, upsert_personalidad
from domain.models.agentes import Agente
from domain.models.core import Centro


def _agente(session: Session) -> Agente:
    centro = session.exec(select(Centro)).first()
    ag = Agente(centro_id=centro.id, nombre="Aura", audiencia="superuser", config_key="aura.config", es_agente_base=True)
    session.add(ag); session.commit(); session.refresh(ag); return ag


def test_permisos_admin(session: Session):
    ag = _agente(session)
    grant(session, ag.id, "recepcion", puede_ver=True, puede_editar=False)
    grant(session, ag.id, "admin", puede_ver=True, puede_editar=True)
    assert puede_ver(session, ag.id, "recepcion") is True
    assert puede_editar(session, ag.id, "recepcion") is False
    assert puede_editar(session, ag.id, "admin") is True
    assert puede_ver(session, ag.id, "otro") is False
    # superuser wildcard
    assert puede_editar(session, ag.id, "superuser") is True


def test_canal_ajuste(session: Session):
    ag = _agente(session)
    upsert_ajuste(session, ag.id, "voz", longitud_max=200, usa_emojis=False, ritmo="Habla despacio.")
    aj = ajuste_para(session, ag.id, "voz")
    assert aj.longitud_max == 200
    assert aj.usa_emojis is False
    assert ajuste_para(session, ag.id, "whatsapp") is None

    base = "Prompt base"
    out = aplicar_ajuste(base, aj)
    assert "200 caracteres" in out
    assert "No uses emojis" in out
    assert "Habla despacio" in out
    assert out.startswith(base)
    # sin ajuste
    assert aplicar_ajuste(base, None) == base


def test_personalidad_prompt_integra_con_canal(session: Session):
    ag = _agente(session)
    upsert_personalidad(session, ag.id, "base", tono="Tono base")
    upsert_ajuste(session, ag.id, "voz", usa_emojis=False)
    prompt = prompt_para(session, ag.id)
    aj = ajuste_para(session, ag.id, "voz")
    final = aplicar_ajuste(prompt, aj)
    assert "Tono base" in final
    assert "No uses emojis" in final
