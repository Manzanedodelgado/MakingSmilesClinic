"""Migra la configuración REAL de Alex/Victor/Aura/Gestor (leída de
`configuraciones` vía ConfigService) a las tablas nuevas de Plan 1
(`agentes`, `capacidades_catalogo`, `agente_capacidades`).

No toca agente_service.py/victor_agente.py/aura_agente.py: es la fase de
convivencia de la Sección 3 de la spec — los datos nuevos existen para
comparar, el sistema real sigue respondiendo exactamente igual que antes.

Las claves de capacidad que existen en la config real pero que ningún
código comprueba hoy (verificado con grep en la sesión de trabajo del
23-sep-2026: ver docs/superpowers/plans/2026-09-23-agentes-ia-migracion-real.md,
sección "Hechos verificados") se migran igual —instrucción explícita del
usuario, no se pierde ningún dato— pero con un `ejecutor` que dice
literalmente que no hace nada, nunca un nombre de función inventado.
"""
from typing import Optional

from sqlmodel import Session, select

from application.services.config_service import ConfigService
from domain.models.agentes import Agente, AgenteCapacidad, CapacidadCatalogo

SIN_EJECUTOR = "(sin código asociado — dato heredado de configuración anterior)"

# Claves reales verificadas contra el código en la sesión de trabajo del
# 23-sep-2026 (ver el plan). Todo lo que NO esté aquí, para el agente que
# corresponda, se considera clave muerta y se migra con SIN_EJECUTOR.
_CLAVES_REALES = {
    "alex": {
        "verificar_identidad": "AgenteService.ejecutar_tool:verificar_identidad",
        "consultar_mis_citas": "AgenteService.ejecutar_tool:consultar_mis_citas",
        "consultar_tratamientos_pendientes": "AgenteService.ejecutar_tool:consultar_tratamientos_pendientes",
        "consultar_disponibilidad": "AgenteService.ejecutar_tool:consultar_disponibilidad",
        "crear_cita": "AgenteService.ejecutar_tool:crear_cita",
        "modificar_cita": "AgenteService.ejecutar_tool:modificar_cita",
        "enviar_presupuesto": "AgenteService.ejecutar_tool:enviar_presupuesto",
        "enviar_factura": "AgenteService.ejecutar_tool:enviar_factura",
        "enviar_recibo": "AgenteService.ejecutar_tool:enviar_recibo",
        "enviar_justificante": "AgenteService.ejecutar_tool:enviar_justificante",
        "escalar_a_humano": "AgenteService.ejecutar_tool:escalar_a_humano",
        "crear_presupuesto": "AgenteService.ejecutar_tool:crear_presupuesto",
    },
    "victor": {
        "transcribir_consulta": "capacidad_activa:victor:transcribir_consulta (api/consulta_router.py)",
    },
    "aura": {
        "consultar_metricas": "AuraAgente.ejecutar:consultar_metricas",
        "consultar_auditoria": "AuraAgente.ejecutar:consultar_auditoria",
        "consultar_usuarios": "AuraAgente.ejecutar:consultar_usuarios",
    },
    "gestor": {},  # verificado por grep: ninguna clave de Gestor tiene código asociado hoy
}

_DESCRIPCIONES = {
    "verificar_identidad": "Verifica el nombre completo antes de revelar datos personales",
    "consultar_mis_citas": "Consultar las próximas citas del paciente",
    "consultar_tratamientos_pendientes": "Consultar tratamientos pendientes del paciente",
    "consultar_disponibilidad": "Consultar huecos libres antes de crear/mover una cita",
    "crear_cita": "Crear una cita nueva en un hueco libre",
    "modificar_cita": "Cambiar la fecha/hora de la próxima cita",
    "enviar_presupuesto": "Pedir al equipo que envíe el presupuesto al paciente",
    "enviar_factura": "Pedir al equipo que envíe una factura al paciente",
    "enviar_recibo": "Pedir al equipo que envíe un recibo al paciente",
    "enviar_justificante": "Pedir al equipo un justificante de asistencia",
    "escalar_a_humano": "Avisar a una persona del equipo",
    "crear_presupuesto": "Crear presupuesto por dictado (staff/simulador)",
    "transcribir_consulta": "Escucha activa: transcribe la consulta y extrae el SOAP",
    "consultar_metricas": "Cifras y estado de cualquier área del sistema",
    "consultar_auditoria": "Últimas acciones registradas en el sistema",
    "consultar_usuarios": "Quién tiene acceso a este centro ahora mismo",
}


def _capacidad_o_crear(session: Session, clave: str, agente_id_catalogo: str) -> CapacidadCatalogo:
    ejecutor_nuevo = _CLAVES_REALES.get(agente_id_catalogo, {}).get(clave, SIN_EJECUTOR)
    descripcion = _DESCRIPCIONES.get(clave, clave.replace("_", " ").capitalize())

    existente = session.exec(select(CapacidadCatalogo).where(CapacidadCatalogo.clave == clave)).first()
    if existente:
        # Nunca degradar: un ejecutor real no se sustituye por SIN_EJECUTOR, y unos
        # parametros ya rellenos (ej. por seed_capacidades_alex, Plan 1) no se vacían.
        # Sí se ACTUALIZA si la llamada actual trae mejor información que la que había
        # (evita que el orden de migración de los 4 agentes decida arbitrariamente qué
        # dato "gana" cuando una clave es compartida, como transcribir_consulta entre Victor y Aura).
        cambiado = False
        if existente.ejecutor == SIN_EJECUTOR and ejecutor_nuevo != SIN_EJECUTOR:
            existente.ejecutor = ejecutor_nuevo
            cambiado = True
        # No aplica hoy (esta migración siempre escribe parametros={}), pero se deja
        # explícito: no vaciar parametros reales ya existentes (defensa contra orden
        # migration vs seeder). Si esta función alguna vez recibe parametros reales,
        # la regla sería: upgradear {} -> real, nunca real -> {}.
        if cambiado:
            session.add(existente)
            session.commit()
            session.refresh(existente)
        return existente

    fila = CapacidadCatalogo(clave=clave, descripcion=descripcion, ejecutor=ejecutor_nuevo, parametros={})
    session.add(fila)
    session.commit()
    session.refresh(fila)
    return fila


def migrar_agente_real(
    session: Session, centro_id: int, agente_id: str, nombre: str, audiencia: str,
    config_key: str, sistema: str, agente_id_catalogo: str,
) -> Agente:
    agente = session.exec(select(Agente).where(
        Agente.centro_id == centro_id, Agente.audiencia == audiencia, Agente.es_agente_base == True  # noqa: E712
    )).first()
    if not agente:
        agente = Agente(
            centro_id=centro_id, nombre=nombre, audiencia=audiencia,
            config_key=config_key, es_agente_base=True, activo=False, modo_activacion="manual",
        )
        session.add(agente)
        session.commit()
        session.refresh(agente)

    cfg = ConfigService(session).resolve(config_key, centro_id=centro_id, sistema=sistema, default={}) or {}
    agente.activo = bool(cfg.get("activa", False))
    session.add(agente)
    session.commit()

    capacidades_reales: dict = cfg.get("capacidades") or {}
    for clave, activa in capacidades_reales.items():
        cap = _capacidad_o_crear(session, clave, agente_id_catalogo)
        puente = session.exec(select(AgenteCapacidad).where(
            AgenteCapacidad.agente_id == agente.id, AgenteCapacidad.capacidad_id == cap.id
        )).first()
        if puente:
            puente.activa = bool(activa)
            session.add(puente)
        else:
            session.add(AgenteCapacidad(agente_id=agente.id, capacidad_id=cap.id, activa=bool(activa)))
        session.commit()

    return agente


def migrar_los_cuatro_agentes_reales(session: Session, centro_id: int) -> list[Agente]:
    return [
        migrar_agente_real(session, centro_id, "alex", "Alex", "paciente", "agente.alex", "ia", "alex"),
        migrar_agente_real(session, centro_id, "victor", "Victor", "staff", "agente.victor", "ia", "victor"),
        migrar_agente_real(session, centro_id, "aura", "Aura", "superuser", "aura.config", "aura", "aura"),
        migrar_agente_real(session, centro_id, "gestor", "Gestor IA", "facturacion", "gestor.config", "gestor", "gestor"),
    ]
