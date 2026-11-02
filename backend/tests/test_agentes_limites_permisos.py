"""Config → Agentes IA: LÍMITES editables y PERMISOS de la app que cortan de verdad.

Cubre los dos huecos que tenía la pantalla:
  · `limites` del catálogo se servía en GET /agentes pero no lo leía ni el prompt ni la UI
    → ahora se siembra en config (`limites_texto`), es editable y entra en el prompt de los
    cuatro agentes (Alex en WhatsApp/entrenamiento, Victor/Aura en su bucle de chat y
    Gestor en su chat de entrenamiento y en la ingesta de facturas).
  · `permisos.requiere` se guardaba en config y jamás se comprobaba (decorativo)
    → ahora el mapa `permisos_tools` del catálogo decide: la herramienta sin su permiso no
    se ofrece (`_tools_para` / `_herramientas_permitidas`) ni se ejecuta (segunda barrera
    en `ejecutar_tool` y en el bucle de `AgenteConversacional`).
"""
import json

from sqlmodel import Session, select

from application.services.agentes_config import (
    MAX_LIMITES, herramienta_permitida, limites_de, permisos_efectivos, plantilla,
    reconciliar, sanitizar_limites,
)
from application.services.config_service import ConfigService
from domain.config.agentes import ALEX, VICTOR, POR_ID
from domain.models.core import Centro


def _centro(session: Session) -> int:
    return session.exec(select(Centro)).first().id


# ─────────────────────── SIEMBRA Y RECONCILIACIÓN ───────────────────────

def test_plantilla_sembra_limites_y_permisos_desde_catalogo():
    p = plantilla("alex")
    assert p["limites_texto"] == ALEX.limites          # la lista que antes era decorativa
    assert p["permisos"]["requiere"] == ALEX.permisos  # todo concedido → sin cambio de comportamiento
    # el universo de permisos de cada agente es subconjunto del catálogo `Permiso` real
    for a in POR_ID.values():
        assert set(a.permisos_tools.values()) <= set(a.permisos), (
            f"{a.id}: permisos_tools apunta a permisos fuera de su lista {a.permisos}")


def test_reconciliar_completa_limites_sin_pisar_lo_elegido(session: Session):
    centro_id = _centro(session)
    cfg = ConfigService(session)
    # Config "de antes": sin limites_texto y con elecciones del usuario que deben sobrevivir
    cfg.set("agente.alex", {"activa": True, "capacidades": {"crear_cita": False},
                            "permisos": {"requiere": ALEX.permisos}},
            centro_id=centro_id, sistema="ia")
    res = reconciliar(session, centro_id)
    assert "agente.alex" in res["completadas"]
    actual = cfg.resolve("agente.alex", centro_id=centro_id, sistema="ia")
    assert actual["limites_texto"] == ALEX.limites   # sembrado desde el catálogo
    assert actual["activa"] is True                  # lo elegido, intacto
    assert actual["capacidades"]["crear_cita"] is False
    # idempotente: segunda pasada no vuelve a tocarlo
    res2 = reconciliar(session, centro_id)
    assert "agente.alex" in res2["intactas"]


# ─────────────────────── SANEADO AL LEER ───────────────────────

def test_limites_de_sanea_y_falla_al_catalogo():
    assert limites_de(None, "alex") == ALEX.limites              # sin config → catálogo
    assert limites_de({}, "alex") == ALEX.limites                # clave ausente → catálogo
    assert limites_de({"limites_texto": ["Solo una"]}, "alex") == ["Solo una"]
    # basura descartada en vez de lanzar (la config es JSON de UI)
    assert limites_de({"limites_texto": ["  ok  ", "", 42, None, "dos  "]}, "alex") == ["ok", "dos"]
    assert limites_de({"limites_texto": []}, "alex") == []        # vacío a mano es legítimo
    assert sanitizar_limites("no soy una lista") == []
    assert len(sanitizar_limites(["x"] * (MAX_LIMITES + 5))) == MAX_LIMITES


def test_permisos_efectivos_falla_al_catalogo():
    assert permisos_efectivos(None, "alex") == ALEX.permisos
    assert permisos_efectivos({"permisos": {"requiere": ["citas.ver"]}}, "alex") == ["citas.ver"]
    assert permisos_efectivos({"permisos": {"requiere": ["no", 1]}}, "alex") == ["no"]
    assert permisos_efectivos({"permisos": {}}, "alex") == ALEX.permisos  # requiere ausente


def test_herramienta_permitida():
    assert herramienta_permitida(ALEX.permisos, "alex", "crear_cita")
    assert not herramienta_permitida(["citas.ver"], "alex", "crear_cita")   # falta citas.editar
    assert herramienta_permitida([], "alex", "verificar_identidad")         # sin mapa → siempre
    assert herramienta_permitida([], "desconocido", "cualquiera")           # id desconocido


# ─────────────────────── LOS LÍMITES ENTRAN EN EL PROMPT ───────────────────────

def test_alex_prompt_lleva_limites(session: Session):
    from application.services.agente_service import AgenteService
    centro_id = _centro(session)
    cfg = ConfigService(session)
    base = plantilla("alex")
    base["limites_texto"] = ["Prohíbete decir precios por WhatsApp"]
    cfg.set("agente.alex", base, centro_id=centro_id, sistema="ia")
    bloque = AgenteService(session)._limites_centro(centro_id, "alex")
    assert "LÍMITES DE LA CLÍNICA" in bloque
    assert "Prohíbete decir precios por WhatsApp" in bloque
    # centro sin config → límites del catálogo (antes no entraban NINGUNO)
    bloque2 = AgenteService(session)._limites_centro(9999, "alex")
    assert ALEX.limites[0] in bloque2


def test_victor_prompt_lleva_limites(session: Session):
    from application.services.victor_agente import VictorAgente
    centro_id = _centro(session)
    base = plantilla("victor")
    base["limites_texto"] = ["Nunca bloquees la agenda sin confirmar"]
    ConfigService(session).set("agente.victor", base, centro_id=centro_id, sistema="ia")
    bloque = VictorAgente(session, centro_id)._limites_extra()
    assert "LÍMITES DE LA CLÍNICA" in bloque
    assert "Nunca bloquees la agenda sin confirmar" in bloque


def test_gestor_prompt_lleva_limites(session: Session):
    from application.services.agente_service import AgenteService
    centro_id = _centro(session)
    base = plantilla("gestor")
    base["limites_texto"] = ["Facturas de más de 1000€ a revisión humana"]
    ConfigService(session).set("gestor.config", base, centro_id=centro_id, sistema="gestor")
    bloque = AgenteService(session)._limites_centro(centro_id, "gestor")
    assert "Facturas de más de 1000€ a revisión humana" in bloque


def test_gestor_ingesta_facturas_lleva_limites(session: Session):
    """El prompt de PRODUCCIÓN de facturas (gmail_ai_processor) incluye los límites."""
    from application.services.gmail_ai_processor import GmailAIProcessor
    centro_id = _centro(session)
    base = plantilla("gestor")
    base["limites_texto"] = ["Verifica el CIF de toda factura"]
    ConfigService(session).set("gestor.config", base, centro_id=centro_id, sistema="gestor")

    class _Stub:  # mismo contrato que usa _limites_ia, sin ejecutar el __init__ completo
        def __init__(self, ses, cid):
            self.session = ses
            self.centro_id = cid

    bloque = GmailAIProcessor._limites_ia(_Stub(session, centro_id))
    assert "Verifica el CIF de toda factura" in bloque


# ─────────────────────── PERMISOS QUE CORTAN DE VERDAD ───────────────────────

def test_alex_sin_citas_editar_no_ofrece_ni_ejecuta(session: Session, monkeypatch):
    from application.services import capacidades_service
    monkeypatch.setattr(capacidades_service, "herramientas_base", lambda *a, **k: None)
    from application.services.agente_service import AgenteService
    centro_id = _centro(session)
    cfg = ConfigService(session)
    svc = AgenteService(session)

    # Control positivo: capacidades de cita ON y todos los permisos → la ofrece
    base = plantilla("alex")
    base["capacidades"]["crear_cita"] = True
    base["capacidades"]["modificar_cita"] = True
    cfg.set("agente.alex", base, centro_id=centro_id, sistema="ia")
    nombres = {t["function"]["name"] for t in svc._tools_para(centro_id, es_staff=True)}
    assert {"crear_cita", "modificar_cita"} <= nombres

    # Sin citas.editar (y con las capacidades igual de ON) → no las ofrece
    base["permisos"]["requiere"] = [p for p in ALEX.permisos if p != "citas.editar"]
    cfg.set("agente.alex", base, centro_id=centro_id, sistema="ia")
    nombres = {t["function"]["name"] for t in svc._tools_para(centro_id, es_staff=True)}
    assert "crear_cita" not in nombres
    assert "modificar_cita" not in nombres
    assert "consultar_mis_citas" in nombres        # citas.ver sigue concedido
    assert "verificar_identidad" in nombres        # la guarda de identidad no se puede apagar

    # Segunda barrera: aunque alguien la llame a mano, no se ejecuta
    ctx = {"centro_id": centro_id, "telefono": "34600000000", "paciente": None,
           "nombres": [], "identidad": True, "simular": True, "es_staff": True}
    out = json.loads(svc.ejecutar_tool("crear_cita",
                                       {"fecha": "2026-10-20", "hora": "10:00", "tipo_cita_id": 1}, ctx))
    assert out["error"] == "permiso_insuficiente"
    assert out["permiso_requerido"] == "citas.editar"
    # una herramienta SIN permiso exigible pasa la barrera (y sigue su propia lógica)
    out2 = json.loads(svc.ejecutar_tool("consultar_mis_citas", {}, ctx))
    assert out2.get("error") != "permiso_insuficiente"


def test_victor_sin_citas_editar_no_ofrece_agenda(session: Session, monkeypatch):
    from application.services import capacidades_service
    monkeypatch.setattr(capacidades_service, "herramientas_base", lambda *a, **k: None)
    from application.services.victor_agente import VictorAgente
    centro_id = _centro(session)
    base = plantilla("victor")
    base["permisos"]["requiere"] = ["citas.ver", "pacientes.ver"]  # sin citas.editar
    ConfigService(session).set("agente.victor", base, centro_id=centro_id, sistema="ia")

    ag = VictorAgente(session, centro_id)
    nombres = {t["function"]["name"] for t in ag._herramientas_permitidas(ag.herramientas())}
    assert "bloquear_agenda" not in nombres   # exige citas.editar
    assert "liberar_agenda" not in nombres
    assert "resumen_dia" in nombres           # solo exige citas.ver, sigue concedido


def test_alex_sin_config_conserva_comportamiento_historico():
    """Sin BD (session=None, patrón de los tests ligeros) → catálogo: nada se corta y el
    prompt sigue recibiendo los límites del catálogo (que antes no entraban nunca)."""
    from application.services.agente_service import AgenteService
    svc = AgenteService.__new__(AgenteService)
    svc.session = None
    assert svc._permisos_efectivos(1, "alex") == ALEX.permisos
    bloque = svc._limites_centro(1, "alex")
    assert "LÍMITES DE LA CLÍNICA" in bloque and ALEX.limites[0] in bloque


# ─────────────────────── PANTALLA (endpoints) ───────────────────────

def test_patch_limites_y_permisos(client, token):
    h = {"Authorization": f"Bearer {token}"}
    # límites: se guardan saneados (recortados, sin vacíos)
    r = client.patch("/agentes/alex/config", json={"limites_texto": ["  No des precios  ", ""]}, headers=h)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    val = client.get("/config?sistema=ia", headers=h).json()["valores"]["agente.alex"]
    assert val["limites_texto"] == ["No des precios"]
    # tope de líneas
    r = client.patch("/agentes/alex/config", json={"limites_texto": ["x"] * (MAX_LIMITES + 1)}, headers=h)
    assert r.json()["ok"] is False and "Demasiados" in r.json()["motivo"]
    # código que no existe en la tabla `permisos` de la app → rechazado con motivo claro
    r = client.patch("/agentes/alex/config", json={"permisos_requiere": ["no.existe"]}, headers=h)
    assert r.json()["ok"] is False and "no.existe" in r.json()["motivo"]
    # permiso real fuera de la semilla del catálogo → concedible (la pantalla puede crear,
    # el universo es la tabla `permisos`, no la lista por defecto del agente)
    r = client.patch("/agentes/alex/config", json={"permisos_requiere": ["citas.ver", "informes.ver"]}, headers=h)
    assert r.json()["ok"] is True, r.text
    val = client.get("/config?sistema=ia", headers=h).json()["valores"]["agente.alex"]
    assert val["permisos"]["requiere"] == ["citas.ver", "informes.ver"]
    # subconjunto válido → guardado tal cual (y sin tocar el resto del bloque permisos)
    r = client.patch("/agentes/alex/config", json={"permisos_requiere": ["citas.ver"]}, headers=h)
    assert r.json()["ok"] is True, r.text
    val = client.get("/config?sistema=ia", headers=h).json()["valores"]["agente.alex"]
    assert val["permisos"]["requiere"] == ["citas.ver"]
    assert val["permisos"]["auditoria"] is True  # el resto del bloque, intacto


def test_victor_guarda_su_lista_hereditaria(client, token):
    """Regresión: la config viva de Victor trae códigos válidos fuera de su semilla de
    catálogo (informes.ver + comunicacion.ver, heredados). Guardar sin tocar nada en la
    pantalla NO debe fallar — solo se rechazan códigos que la app no tiene."""
    r = client.patch("/agentes/victor/config",
                     json={"permisos_requiere": ["citas.ver", "citas.editar", "pacientes.ver",
                                                 "informes.ver", "comunicacion.ver"]},
                     headers={"Authorization": f"Bearer {token}"})
    assert r.json()["ok"] is True, r.text


def test_get_permisos_catalogo(client, token):
    r = client.get("/agentes/permisos/catalogo",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    codigos = [p["codigo"] for p in r.json()["permisos"]]
    assert "citas.editar" in codigos and "config.editar" in codigos


# ─────────────────────── AURA: LA OFERTA ES LO IMPLEMENTADO ───────────────────────

def test_aura_ofrece_solo_lo_que_sabe_despachar(session: Session, monkeypatch):
    """La config de la BD puede arrastrar herramientas del roster antiguo (extraer_soap,
    preparar_consulta, transcribir_consulta) que el despachador de Aura no implementa:
    se ofrecían igual y el modelo acababa recibiendo «herramienta desconocida». La oferta
    es SIEMPRE intersección con lo que `ejecutar` sabe despachar."""
    from application.services import capacidades_service
    from application.services.aura_agente import _IMPLEMENTADAS, AuraAgente

    nombres = ["consultar_metricas", "consultar_auditoria", "consultar_usuarios",
               "extraer_soap", "preparar_consulta", "transcribir_consulta"]
    db = [{"type": "function", "function": {"name": n, "description": "", "parameters": {}}}
          for n in nombres]
    monkeypatch.setattr(capacidades_service, "herramientas_base", lambda _s, _c, _a: db)

    ofrecidas = {t["function"]["name"]
                 for t in AuraAgente(session, _centro(session)).herramientas()}
    assert ofrecidas == {"consultar_metricas", "consultar_auditoria", "consultar_usuarios"}
    assert ofrecidas <= _IMPLEMENTADAS
