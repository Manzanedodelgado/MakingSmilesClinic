"""Motor de ejecución dinámica de capacidades (Sección 2 de la spec
docs/superpowers/specs/2026-09-23-agentes-ia-configuracion-design.md).

Arma la lista de herramientas (formato OpenAI function-calling) que se le
ofrece al LLM de un agente, leyendo qué capacidades tiene activas en
`agente_capacidades` — en vez de una lista Python fija por agente.
"""
from sqlmodel import Session, select

from domain.models.agentes import Agente, AgenteCapacidad, CapacidadCatalogo


def herramientas_base(session: Session, centro_id: int, audiencia: str) -> list[dict] | None:
    """Herramientas DB del agente base de (centro, audiencia), o None si no hay fila.

    Unifica el gate DB→legacy que estaba triplicado (Alex/Victor/Aura): si hay fila
    `agentes` manda la DB; si no (o si falla), el llamador aplica su fallback legacy.
    Devuelve [] solo si la fila existe pero no tiene capacidades activas.
    """
    try:
        ag = session.exec(select(Agente).where(
            Agente.centro_id == centro_id,
            Agente.audiencia == audiencia,
            Agente.es_agente_base == True,  # noqa: E712
        )).first()
    except Exception:  # raiz: consulta del agente base falla (BD/esquema); None cae al fallback legacy
        return None
    if ag is None:
        return None
    try:
        return herramientas_de(session, ag.id)
    except Exception:  # raiz: herramientas_de falla; None cae al fallback legacy
        return None


def herramientas_de(session: Session, agente_id: int) -> list[dict]:
    """Herramientas activas de un agente, listas para pasarle a un cliente LLM
    con function-calling (mismo formato que la constante `TOOLS` que hoy usan
    Alex/Victor/Aura escritas a mano en su fichero de servicio)."""
    filas = session.exec(
        select(CapacidadCatalogo)
        .join(AgenteCapacidad, AgenteCapacidad.capacidad_id == CapacidadCatalogo.id)
        .where(AgenteCapacidad.agente_id == agente_id, AgenteCapacidad.activa == True)  # noqa: E712
    ).all()
    codigo = _esquemas_del_codigo()
    salida = []
    for cap in filas:
        base = codigo.get(cap.clave, {}).get("function", {})
        salida.append({"type": "function", "function": {
            "name": cap.clave,
            # El catálogo de la BD no guarda ni descripción útil ni parámetros (los 45
            # `parametros` están a {}), así que manda la definición del código cuando existe.
            "description": base.get("description") or cap.descripcion,
            "parameters": _esquema_valido(cap.parametros, base.get("parameters")),
        }})
    return salida


def _esquema_valido(de_la_bd, del_codigo) -> dict:
    """Esquema de parámetros que un LLM acepta SIEMPRE.

    Ollama rechaza la petición entera con HTTP 500 ("properties must be an object") si una
    herramienta llega con `parameters: {}`, y el relé lo interpreta como "el motor local no
    responde" y manda la conversación a la nube. Pasó con Aura: sus 10 herramientas iban sin
    parámetros. Orden: lo que diga el código; si no, lo de la BD si es válido; si no, un
    esquema vacío correcto (herramienta sin argumentos)."""
    for cand in (del_codigo, de_la_bd):
        if isinstance(cand, dict) and isinstance(cand.get("properties"), dict):
            return cand
    return {"type": "object", "properties": {}}


def _esquemas_del_codigo() -> dict:
    """Definiciones escritas a mano de cada agente (nombre → herramienta), que sí traen
    descripción y parámetros. Import perezoso: estos módulos importan este fichero."""
    esquemas: dict = {}
    for modulo in ("application.services.agente_service",
                   "application.services.victor_agente",
                   "application.services.aura_agente"):
        try:
            import importlib
            tools = getattr(importlib.import_module(modulo), "TOOLS", None) or []
            for t in tools:
                nombre = (t.get("function") or {}).get("name")
                if nombre:
                    esquemas.setdefault(nombre, t)
        except Exception:  # raiz: un módulo de agente roto (import o TOOLS) no debe dejar sin herramientas al resto  # noqa: BLE001
            continue
    return esquemas
