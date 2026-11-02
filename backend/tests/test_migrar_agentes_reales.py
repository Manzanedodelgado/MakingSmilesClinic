from sqlmodel import Session, select

from application.services.config_service import ConfigService
from application.services.migrar_agentes_reales import migrar_los_cuatro_agentes_reales
from domain.models.agentes import Agente, AgenteCapacidad, CapacidadCatalogo
from domain.models.core import Centro


def _preparar_config_real(session: Session, centro_id: int):
    """Reproduce la config real de centro 1 capturada en esta planificación,
    con un subconjunto representativo (no las 45 claves completas, solo las
    que hacen falta para probar la clasificación real/muerta)."""
    ConfigService(session).set("agente.alex", {
        "activa": False,
        "capacidades": {
            "verificar_identidad": True,
            "crear_cita": True,
            "crear_presupuesto": False,
            "informar_cita": True,  # clave muerta real, verificada en el código
        },
    }, centro_id=centro_id, sistema="ia")
    ConfigService(session).set("agente.victor", {
        "activa": True,
        "capacidades": {
            "transcribir_consulta": True,
            "resumen_dia": True,  # clave muerta real
        },
    }, centro_id=centro_id, sistema="ia")
    ConfigService(session).set("aura.config", {
        "activa": True,
        "capacidades": {"consultar_metricas": True, "modificar_configuracion": False},
    }, centro_id=centro_id, sistema="aura")
    ConfigService(session).set("gestor.config", {
        "activa": True,
        "capacidades": {"clasificar_gastos": True, "leer_facturas": True},
    }, centro_id=centro_id, sistema="gestor")


def test_migra_los_cuatro_agentes_con_su_config_real(session: Session):
    centro = session.exec(select(Centro)).first()
    _preparar_config_real(session, centro.id)

    agentes = migrar_los_cuatro_agentes_reales(session, centro.id)

    assert {a.id for a in [
        session.exec(select(Agente).where(Agente.audiencia == aud)).first()
        for aud in ("paciente", "staff", "superuser", "facturacion")
    ]} == {a.id for a in agentes}

    alex = session.exec(select(Agente).where(Agente.audiencia == "paciente")).first()
    assert alex.activo is False
    assert alex.nombre == "Alex"
    assert alex.es_agente_base is True


def test_clave_real_tiene_ejecutor_de_verdad_y_clave_muerta_no(session: Session):
    centro = session.exec(select(Centro)).first()
    _preparar_config_real(session, centro.id)
    migrar_los_cuatro_agentes_reales(session, centro.id)

    crear_cita = session.exec(select(CapacidadCatalogo).where(CapacidadCatalogo.clave == "crear_cita")).first()
    assert crear_cita.ejecutor == "AgenteService.ejecutar_tool:crear_cita"

    informar_cita = session.exec(select(CapacidadCatalogo).where(CapacidadCatalogo.clave == "informar_cita")).first()
    assert informar_cita.ejecutor == "(sin código asociado — dato heredado de configuración anterior)"

    # Todas las claves de Gestor son muertas, verificado por grep en esta sesión
    leer_facturas = session.exec(select(CapacidadCatalogo).where(CapacidadCatalogo.clave == "leer_facturas")).first()
    assert leer_facturas.ejecutor == "(sin código asociado — dato heredado de configuración anterior)"


def test_estado_activa_refleja_la_config_real_del_centro(session: Session):
    centro = session.exec(select(Centro)).first()
    _preparar_config_real(session, centro.id)
    migrar_los_cuatro_agentes_reales(session, centro.id)

    alex = session.exec(select(Agente).where(Agente.audiencia == "paciente")).first()
    cap_crear_presu = session.exec(select(CapacidadCatalogo).where(CapacidadCatalogo.clave == "crear_presupuesto")).first()
    puente = session.exec(select(AgenteCapacidad).where(
        AgenteCapacidad.agente_id == alex.id, AgenteCapacidad.capacidad_id == cap_crear_presu.id
    )).first()
    assert puente.activa is False  # la config real de centro 1 lo tiene en False

    cap_verificar = session.exec(select(CapacidadCatalogo).where(CapacidadCatalogo.clave == "verificar_identidad")).first()
    puente2 = session.exec(select(AgenteCapacidad).where(
        AgenteCapacidad.agente_id == alex.id, AgenteCapacidad.capacidad_id == cap_verificar.id
    )).first()
    assert puente2.activa is True


def test_migracion_es_idempotente(session: Session):
    centro = session.exec(select(Centro)).first()
    _preparar_config_real(session, centro.id)
    migrar_los_cuatro_agentes_reales(session, centro.id)
    migrar_los_cuatro_agentes_reales(session, centro.id)

    agentes = session.exec(select(Agente).where(Agente.centro_id == centro.id)).all()
    assert len(agentes) == 4  # no duplica agentes en la segunda pasada


def test_transcribir_consulta_upgrade_sin_ejecutor_a_real(session: Session):
    """Si Aura crea primero transcribir_consulta como SIN_EJECUTOR, Victor debe upgradearla a real."""
    from application.services.migrar_agentes_reales import SIN_EJECUTOR, _capacidad_o_crear

    cap_aura = _capacidad_o_crear(session, "transcribir_consulta", "aura")
    assert cap_aura.ejecutor == SIN_EJECUTOR

    cap_victor = _capacidad_o_crear(session, "transcribir_consulta", "victor")
    assert cap_victor.ejecutor != SIN_EJECUTOR
    assert cap_victor.id == cap_aura.id  # misma fila, no duplicada

    cap_bd = session.exec(select(CapacidadCatalogo).where(CapacidadCatalogo.clave == "transcribir_consulta")).first()
    assert cap_bd.ejecutor == cap_victor.ejecutor
    assert cap_bd.ejecutor != SIN_EJECUTOR


def test_transcribir_consulta_real_no_se_degrada(session: Session):
    """Un ejecutor real no se degrada a SIN_EJECUTOR aunque Aura lo reclame después."""
    from application.services.migrar_agentes_reales import SIN_EJECUTOR, _capacidad_o_crear

    cap_victor = _capacidad_o_crear(session, "transcribir_consulta", "victor")
    assert cap_victor.ejecutor != SIN_EJECUTOR
    ejecutor_real = cap_victor.ejecutor

    cap_aura = _capacidad_o_crear(session, "transcribir_consulta", "aura")
    assert cap_aura.ejecutor == ejecutor_real
    assert cap_aura.ejecutor != SIN_EJECUTOR


def test_claves_reales_alex_coincide_con_cap_de_tool():
    """Si alguien cambia CAP_DE_TOOL sin actualizar _CLAVES_REALES, este test lo caza."""
    from application.services.agente_service import CAP_DE_TOOL
    from application.services.migrar_agentes_reales import _CLAVES_REALES

    claves_gate_real = set(CAP_DE_TOOL.values())
    claves_declaradas = set(_CLAVES_REALES["alex"].keys())
    faltan = claves_gate_real - claves_declaradas
    assert not faltan, f"CAP_DE_TOOL tiene claves que _CLAVES_REALES['alex'] no conoce: {faltan}"

    excepciones = {"verificar_identidad", "consultar_disponibilidad"}
    de_mas = claves_declaradas - claves_gate_real - excepciones
    assert not de_mas, f"_CLAVES_REALES['alex'] declara claves que no gatean nada real y no están documentadas como excepción: {de_mas}"


def test_claves_reales_victor_y_aura_son_exactas():
    from application.services.migrar_agentes_reales import _CLAVES_REALES

    assert set(_CLAVES_REALES["victor"].keys()) == {"transcribir_consulta"}
    assert set(_CLAVES_REALES["aura"].keys()) == {"consultar_metricas", "consultar_auditoria", "consultar_usuarios"}
    assert set(_CLAVES_REALES["gestor"].keys()) == set()
