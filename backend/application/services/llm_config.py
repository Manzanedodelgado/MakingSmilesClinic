"""Resolución del LLM efectivo por agente/tarea (Alex, La Consulta Viva, Gestor IA…).

Cada agente PUEDE tener su propia fila `integraciones` (tipo='llm', agente=<slot>) con el
modelo más adecuado para su tarea. Si no la tiene, cae al modelo COMPARTIDO (agente=NULL) —
retrocompatible: un centro que no configure nada por agente sigue funcionando exactamente
como antes de que existiera esta distinción.
"""
from typing import Optional

from sqlmodel import Session, select

from domain.models.config import Integracion

# Slots reconocidos. Los cuatro primeros son los agentes del catálogo
# (domain/config/agentes.py); los de gestoría son tareas internas del Gestor IA.
ALEX = "alex"
VICTOR = "victor"
AURA = "aura"
GESTOR = "gestor"
GESTOR_MULTIMODAL = "gestor_multimodal"
CONSULTA_VIVA = "consulta_viva"
GESTORIA_GASTOS = "gestoria_gastos"
GESTORIA_FACTURAS = "gestoria_facturas"

# Parte → agente del que forma parte (para heredar su modelo del catálogo).
DUENO_DE = {
    CONSULTA_VIVA: VICTOR,
    GESTORIA_GASTOS: GESTOR,
    GESTORIA_FACTURAS: GESTOR,
    GESTOR_MULTIMODAL: GESTOR,
}


def motor_compartido(session: Session) -> Optional[dict]:
    """Motor LLM compartido (agente=NULL) activo, con su `centro_id` incluido.

    Lo usa el relé de PLAN B (api/ollama_relay_router.py): los operadores de
    OpenJarvis no van por centro, así que toman el motor compartido vigente —
    exactamente el mismo que la web, con sus mismos `relevos` de rescate.
    """
    fila = session.exec(select(Integracion).where(
        Integracion.tipo == "llm",
        Integracion.activo == True, Integracion.agente.is_(None)  # noqa: E712
    ).order_by(Integracion.id)).first()
    if not fila or not fila.config:
        return None
    return {**fila.config, "centro_id": fila.centro_id}


def resolver_llm(session: Session, centro_id: int, agente: str) -> Optional[dict]:
    especifico = session.exec(select(Integracion).where(
        Integracion.centro_id == centro_id, Integracion.tipo == "llm",
        Integracion.activo == True, Integracion.agente == agente)).first()  # noqa: E712
    if especifico and especifico.config:
        return especifico.config
    compartido = session.exec(select(Integracion).where(
        Integracion.centro_id == centro_id, Integracion.tipo == "llm",
        Integracion.activo == True, Integracion.agente.is_(None))).first()
    base = compartido.config if (compartido and compartido.config) else None
    if not base:
        return None
    # El modelo del catálogo manda sobre el compartido: cada agente tiene uno elegido para
    # su tarea (Alex rápido porque el paciente espera; Victor/Aura capaces porque razonan).
    # Así un centro que no configure nada por agente NO acaba con todos usando el mismo.
    from domain.config.agentes import POR_ID
    # Hay ids que NO son agentes aparte, sino partes de uno (jmd, 18-oct-2026): La Consulta
    # Viva es la parte de consulta de Victor y gastos/facturas/multimodal son el motor del
    # Gestor IA. Sin esto heredaban el modelo de la integración compartida en vez del de su
    # dueño, y la misma GPU acababa con dos modelos distintos cargados.
    dueno = DUENO_DE.get(agente, agente)
    if dueno in POR_ID:
        base = {**base, "model": POR_ID[dueno].modelo}
    # Interruptor específico (Alex/Víctor/Aura, motor local compartido con Medit i500):
    # el general ya manda por sí solo (sin motor encendido, la llamada HTTP fallará), esto
    # añade el cierre lógico independiente por agente — ver ollama_switch_service.py.
    if agente in ("alex", "victor", "aura"):
        from application.services import ollama_switch_service
        if not ollama_switch_service.agente_activo(session, centro_id, agente):
            return None
    return base
