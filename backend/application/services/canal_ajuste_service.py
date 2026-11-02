"""Sección 7 — ajuste fino por canal, generaliza VOZ_HINT."""
from typing import Optional

from sqlmodel import Session, select

from domain.models.agentes import AgenteCanalAjuste


def ajuste_para(session: Session, agente_id: int, canal: str) -> Optional[AgenteCanalAjuste]:
    return session.exec(
        select(AgenteCanalAjuste).where(AgenteCanalAjuste.agente_id == agente_id, AgenteCanalAjuste.canal == canal)
    ).first()


def upsert_ajuste(session: Session, agente_id: int, canal: str, **kwargs) -> AgenteCanalAjuste:
    obj = ajuste_para(session, agente_id, canal)
    if obj is None:
        obj = AgenteCanalAjuste(agente_id=agente_id, canal=canal, **kwargs)
    else:
        for k, v in kwargs.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def aplicar_ajuste(prompt_base: str, ajuste: Optional[AgenteCanalAjuste]) -> str:
    if not ajuste:
        return prompt_base
    hints: list[str] = []
    if ajuste.longitud_max is not None:
        hints.append(f"Responde en máximo {ajuste.longitud_max} caracteres.")
    if ajuste.usa_emojis is False:
        hints.append("No uses emojis.")
    elif ajuste.usa_emojis is True:
        hints.append("Puedes usar emojis con moderación.")
    if ajuste.ritmo:
        hints.append(ajuste.ritmo)
    if ajuste.extras:
        # extras es JSON libre para hints futuros
        extra_txt = ajuste.extras.get("hint") if isinstance(ajuste.extras, dict) else None
        if extra_txt:
            hints.append(str(extra_txt))
    if not hints:
        return prompt_base
    return f"{prompt_base}\n\n[Ajuste canal {ajuste.canal}] {' '.join(hints)}"
