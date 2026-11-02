"""Personalidad en dos capas — Sección 4 spec.

capa base = fijada al crear el agente; capa aprendida = ajustes acumulados vía chat de entrenamiento.
Prompt final = base + aprendida (base nunca se sobrescribe).
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

from sqlmodel import Session, select

from domain.models.agentes import AgentePersonalidad

_CAPAS_VALIDAS = {"base", "aprendida"}


def get_personalidad(session: Session, agente_id: int, capa: str) -> Optional[AgentePersonalidad]:
    if capa not in _CAPAS_VALIDAS:
        raise ValueError(f"capa debe ser base|aprendida, no {capa!r}")
    return session.exec(
        select(AgentePersonalidad).where(
            AgentePersonalidad.agente_id == agente_id, AgentePersonalidad.capa == capa
        )
    ).first()


def upsert_personalidad(
    session: Session, agente_id: int, capa: str, **kwargs
) -> AgentePersonalidad:
    if capa not in _CAPAS_VALIDAS:
        raise ValueError(f"capa debe ser base|aprendida, no {capa!r}")
    obj = get_personalidad(session, agente_id, capa)
    if obj is None:
        obj = AgentePersonalidad(agente_id=agente_id, capa=capa, **kwargs)
        session.add(obj)
    else:
        for k, v in kwargs.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def _render_capa(p: Optional[AgentePersonalidad]) -> str:
    if not p:
        return ""
    partes: list[str] = []
    if p.idioma and p.idioma != "es":
        partes.append(f"Idioma: {p.idioma}.")
    if p.tono:
        partes.append(p.tono.strip())
    if p.cercania is not None:
        try:
            v = int(p.cercania)
            if v >= 4:
                partes.append("Sé cercano y cálido.")
            elif v <= 1:
                partes.append("Mantén tono neutro y sobrio.")
        except Exception:  # raiz: valor de escala de personalidad no numérico; se ignora esa parte del prompt
            logger.warning("personalidad: valor no numérico ignorado", exc_info=True)
    if p.proactividad is not None:
        try:
            v = int(p.proactividad)
            if v >= 4:
                partes.append("Anticípate y ofrece ayuda.")
            elif v <= 1:
                partes.append("No te adelantes.")
        except Exception:  # raiz: valor de escala de personalidad no numérico; se ignora esa parte del prompt
            logger.warning("personalidad: valor no numérico ignorado", exc_info=True)
    if p.formalidad is not None:
        try:
            v = int(p.formalidad)
            if v >= 4:
                partes.append("Usa registro formal.")
            elif v <= 1:
                partes.append("Usa registro relajado.")
        except Exception:  # raiz: valor de escala de personalidad no numérico; se ignora esa parte del prompt
            logger.warning("personalidad: valor no numérico ignorado", exc_info=True)
    if p.bienvenida:
        partes.append(f"Bienvenida: «{p.bienvenida.strip()}»")
    if p.despedida:
        partes.append(f"Despedida: «{p.despedida.strip()}»")
    if p.acento:
        partes.append(f"Acento: {p.acento}")
    if p.velocidad:
        partes.append(f"Velocidad voz: {p.velocidad}")
    if p.regla_extra:
        partes.append(p.regla_extra.strip())
    return " ".join(partes)


def prompt_para(session: Session, agente_id: int) -> str:
    """Prompt final = base + aprendida. Base nunca se pierde."""
    base = get_personalidad(session, agente_id, "base")
    aprendida = get_personalidad(session, agente_id, "aprendida")
    b = _render_capa(base)
    a = _render_capa(aprendida)
    if b and a:
        return f"{b}\n\n[Aprendido] {a}"
    return b or a
