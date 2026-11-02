"""Aura v2 (14-oct-2026): poder total tras PIN de SuperUser + vigilancia de Centinela.

Decisión de jmd: Aura deja de ser solo lectura. Aquí se cubren las barreras y su ORDEN:
  · PIN (`aura_pin`): hash nunca en claro, sesión desbloqueada 15 min, anti-fuerza-bruta
    (3 fallos → bloqueo 15 min), cambio de PIN invalida desbloqueos vigentes, todo
    auditado sin que el valor aparezca jamás.
  · Registro (`aura_admin`): permiso de la web PRIMERO, PIN DESPUÉS, auditoría SIEMPRE;
    el PIN de Aura no se cambia a sí mismo por herramienta.
  · Centinela: Aura lo lee SIN ejecutar nada (bitácora de auditoría `centinela.*`) y la
    revisión completa (`centinela.revisar`, ciclo con remediación) exige PIN.
  · Catálogo == despachado: `AURA.capacidades` es exactamente lo que `ejecutar` sabe
    hacer, sus permisos_tools cubren todas ellas, y el prompt v2 habla de PIN y Centinela.
"""
import json
import time

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from application.services import aura_pin
from application.services.aura_admin import _centinela_estado, ejecutar, listar_acciones
from application.services.aura_agente import _IMPLEMENTADAS, SYSTEM, TOOLS, AuraAgente
from application.services.agentes_config import reconciliar
from application.services.auth_service import AuthService
from application.services.config_service import ConfigService
from domain.config.agentes import AURA
from domain.models.auditoria import Auditoria
from domain.models.core import Centro
from domain.models.identidad import Usuario

PIN = "482916"


@pytest.fixture(autouse=True)
def _sesiones_limpias():
    """El desbloqueo vive en memoria del proceso: sin esto, un test 'desbloqueado'
    envenena al siguiente."""
    aura_pin._desbloqueos.clear()
    aura_pin._intentos.clear()
    yield
    aura_pin._desbloqueos.clear()
    aura_pin._intentos.clear()


def _centro(session: Session) -> int:
    return session.exec(select(Centro)).first().id


def _admin(session: Session, centro_id: int) -> int:
    """El admin del seed. En producción el superuser vino de una migración; el seed del
    test no lo trae, así que se concede aquí (misma vía real: concesión directa en
    user_center_permisos, que es lo que lee permisos_de)."""
    from domain.models.identidad import Permiso, UserCenterPermiso
    u = session.exec(select(Usuario).where(Usuario.email == "admin@makingsmiles.local")).first()
    assert u, "el seed crea admin@makingsmiles.local"
    p = session.exec(select(Permiso).where(Permiso.codigo == "superuser")).first()
    if p is None:
        p = Permiso(codigo="superuser", descripcion="SuperUser (supercreador)")
        session.add(p)
        session.commit()
        session.refresh(p)
    if not session.exec(select(UserCenterPermiso).where(
            UserCenterPermiso.usuario_id == u.id,
            UserCenterPermiso.centro_id == centro_id,
            UserCenterPermiso.permiso_id == p.id)).first():
        session.add(UserCenterPermiso(usuario_id=u.id, centro_id=centro_id, permiso_id=p.id))
        session.commit()
    assert "superuser" in AuthService(session).permisos_de(u.id, centro_id), \
        "el admin del seed debe ser SuperUser para estas pruebas"
    return u.id


# ─────────────────────────────── PIN: SEGUNDO FACTOR ───────────────────────────────

def test_fijar_pin_guarda_hash_y_valida_formato(session: Session):
    c = _centro(session)
    assert aura_pin.fijar_pin(session, c, 1, "123")["ok"] is False         # muy corto
    assert aura_pin.fijar_pin(session, c, 1, "123456789")["ok"] is False    # muy largo
    assert aura_pin.fijar_pin(session, c, 1, "abcd")["ok"] is False         # no son dígitos
    assert aura_pin.fijar_pin(session, c, 1, PIN)["ok"] is True

    from infrastructure.security import verify_password
    guardado = ConfigService(session).resolve(aura_pin.CLAVE_PIN, centro_id=c, sistema="aura")
    assert guardado and guardado != PIN and PIN not in guardado   # nunca en claro
    assert verify_password(PIN, guardado)

    est = aura_pin.estado_pin(session, c)
    assert est == {"fijado": True, "ttl_minutos": 15, "intentos_max": 3}
    assert PIN not in json.dumps(est)                            # el estado no filtra el valor


def test_sin_pin_fijado_lo_dice_claro(session: Session):
    c, u = _centro(session), None
    r = aura_pin.desbloquear(session, c, u, PIN)
    assert r["ok"] is False and "fijado" in r["motivo"]


def test_desbloqueo_dura_15_minutos_y_caduca(session: Session):
    c, u = _centro(session), 7
    aura_pin.fijar_pin(session, c, 1, PIN)
    assert aura_pin.desbloqueada(c, u) is False
    r = aura_pin.desbloquear(session, c, u, PIN)
    assert r["ok"] is True and r["escritura_habilitada_minutos"] == 15
    assert aura_pin.desbloqueada(c, u) is True
    # TTL puro: pasado el tiempo, la sesión vuelve a estar cerrada
    aura_pin._desbloqueos[(c, u)] = time.time() - 1
    assert aura_pin.desbloqueada(c, u) is False


def test_cambio_de_pin_invalida_desbloqueos_vigentes(session: Session):
    c, u = _centro(session), 7
    aura_pin.fijar_pin(session, c, 1, PIN)
    assert aura_pin.desbloquear(session, c, u, PIN)["ok"] is True
    assert aura_pin.desbloqueada(c, u) is True
    assert aura_pin.fijar_pin(session, c, 1, "771199")["ok"] is True
    assert aura_pin.desbloqueada(c, u) is False    # quien cambia el PIN, manda


def test_anti_fuerza_bruta_tres_fallos_bloquean_quince_minutos(session: Session):
    c, u = _centro(session), 7
    aura_pin.fijar_pin(session, c, 1, PIN)
    for _ in range(3):
        assert aura_pin.desbloquear(session, c, u, "000000")["ok"] is False
    # cuarto intento con el PIN BUENO: sigue bloqueado — el bloqueo es por ritmo, no por acierto
    r = aura_pin.desbloquear(session, c, u, PIN)
    assert r["ok"] is False and "15" in r["motivo"]
    assert aura_pin.desbloqueada(c, u) is False


# ───────────────────────── REGISTRO: PERMISO → PIN → ACCIÓN ─────────────────────────

def test_permiso_de_la_web_va_antes_que_el_pin(session: Session):
    c = _centro(session)
    res = ejecutar(session, c, None, "configuracion", "modificar",
                   {"clave": "prueba.sin_permiso", "valor": 1})
    assert "permiso" in res["error"] and "pin" not in res["error"].lower()


def test_administrar_pin_requerido_luego_ejecuta_y_audita(session: Session):
    c = _centro(session)
    u = _admin(session, c)
    cfg = ConfigService(session)

    # 1 · sin sesión desbloqueada: ni toca datos ni promete otra cosa que el PIN
    res = ejecutar(session, c, u, "configuracion", "modificar",
                   {"clave": "prueba.v2", "valor": 7})
    assert res["error"] == "pin_requerido" and res["accion"] == "configuracion.modificar"
    assert cfg.resolve("prueba.v2", centro_id=c, sistema="ia", default=None) is None

    # 2 · con PIN: la escritura sale
    assert aura_pin.fijar_pin(session, c, u, PIN)["ok"]
    assert aura_pin.desbloquear(session, c, u, PIN)["ok"]
    res = ejecutar(session, c, u, "configuracion", "modificar",
                   {"clave": "prueba.v2", "valor": 7})
    assert res.get("ok") is True
    assert cfg.resolve("prueba.v2", centro_id=c, sistema="ia") == 7

    # 3 · auditoría: bloqueo y escritura, con el detalle de lo hecho y SIN el PIN
    filas = session.exec(select(Auditoria).where(
        Auditoria.accion == "aura.admin.configuracion.modificar"
    ).order_by(Auditoria.id)).all()
    assert len(filas) == 2
    assert filas[0].exito is False and filas[0].detalle["motivo"] == "pin_requerido"
    assert filas[1].exito is True and filas[1].detalle["datos"] == {"clave": "prueba.v2", "valor": 7}
    assert PIN not in json.dumps([f.detalle for f in filas])


def test_el_pin_de_aura_no_se_cambia_a_si_mismo_por_herramienta(session: Session):
    c = _centro(session)
    u = _admin(session, c)
    assert aura_pin.fijar_pin(session, c, u, PIN)["ok"]
    assert aura_pin.desbloquear(session, c, u, PIN)["ok"]
    res = ejecutar(session, c, u, "configuracion", "modificar",
                   {"clave": aura_pin.CLAVE_PIN, "valor": "hacked"})
    assert res.get("ok") is False and "Agentes IA" in res.get("error", "")
    from infrastructure.security import verify_password
    guardado = ConfigService(session).resolve(aura_pin.CLAVE_PIN, centro_id=c, sistema="aura")
    assert verify_password(PIN, guardado)    # intacto


def test_registro_cubre_el_poder_total_y_marca_quien_pide_pin():
    acc = {(a["modulo"], a["accion"]): a for a in listar_acciones()}
    # lo prometido: crear y modificar de todo
    assert ("usuarios", "crear") in acc and ("usuarios", "quitar") in acc
    assert ("configuracion", "modificar") in acc and ("agentes", "modificar") in acc
    assert ("centinela", "estado") in acc and ("centinela", "revisar") in acc
    # lecturas sin PIN; escrituras —y la remediación de Centinela— con PIN
    assert acc[("usuarios", "listar")]["requiere_pin"] is False
    assert acc[("centinela", "estado")]["requiere_pin"] is False
    assert acc[("centinela", "revisar")]["requiere_pin"] is True
    assert acc[("usuarios", "crear")]["requiere_pin"] is True
    # cada acción exige SU permiso de la web (la web sigue mandando)
    assert acc[("configuracion", "modificar")]["permiso"] == "config.editar"
    assert acc[("usuarios", "crear")]["permiso"] == "superuser"


# ─────────────────────────────── CENTINELA A LA MIRADA ───────────────────────────────

def test_centinela_estado_lee_la_bitacora_sin_ejecutar_nada(session: Session):
    c = _centro(session)
    u = _admin(session, c)
    AuthService(session).audit(
        "centinela.tick", usuario_id=u, centro_id=c,
        detalle={"nivel": "error", "origen": "heartbeat_diario"})
    AuthService(session).audit(
        "centinela.alerta", usuario_id=u, centro_id=c,
        detalle={"nivel": "error", "canales_enviados": ["email"],
                 "checks": [{"label": "WhatsApp (Evolution)", "estado": "error",
                             "detalle": "contenedor caído"},
                            {"label": "Backend", "estado": "ok", "detalle": "200"}]})
    est = _centinela_estado(session, c, {"dias": 2})
    assert est["ok"] is True and est["nivel_actual"] == "error"
    assert est["ultima_revision"] and est["origen"] == "heartbeat_diario"
    assert est["avisos"][0]["fallando"][0]["sistema"] == "WhatsApp (Evolution)"
    assert est["avisos"][0]["enviados"] == ["email"]
    # solo lectura: no dispara el ciclo (eso es `revisar`, con PIN)
    assert est["nivel_actual"] == "error"


def test_endpoint_espejo_de_centinela_en_panel_superuser(session: Session, client, token):
    """GET /agentes/aura/centinela: el espejo que muestra SuperUser en la pestaña Aura.
    Mismo lector que su herramienta de chat (bitácora, sin ciclos) y MISMA barrera: la
    capacidad `consultar_centinela` es interruptor también en REST — apagada, 403."""
    c = _centro(session)
    u = _admin(session, c)                          # el admin del seed no trae superuser
    cfg = ConfigService(session)
    reconciliar(session, c)                         # siembra config desde el catálogo
    actual = cfg.resolve("aura.config", centro_id=c, sistema="aura", default={}) or {}
    actual["activa"] = True                         # capacidad_activa exige activa+operativa
    caps = dict(actual.get("capacidades") or {})
    caps["consultar_centinela"] = True
    actual["capacidades"] = caps
    cfg.set("aura.config", actual, centro_id=c, sistema="aura")
    AuthService(session).audit(
        "centinela.tick", usuario_id=u, centro_id=c,
        detalle={"nivel": "warn", "origen": "heartbeat_diario"})

    r = client.get("/agentes/aura/centinela", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] and d["nivel_actual"] == "warn"
    assert d["ultima_revision"] and d["origen"] == "heartbeat_diario"

    caps["consultar_centinela"] = False
    actual["capacidades"] = caps
    cfg.set("aura.config", actual, centro_id=c, sistema="aura")
    r = client.get("/agentes/aura/centinela", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403, r.text


# ───────────── REST del PIN: la pantalla de SuperUser lo fija y lo consulta por aquí ─────────────

def test_rest_pin_estado_y_fijar(client: TestClient, session: Session, token: str):
    c = _centro(session)
    _admin(session, c)
    h = {"Authorization": f"Bearer {token}"}
    r = client.get("/agentes/aura/pin", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["fijado"] is False
    r = client.put("/agentes/aura/pin", json={"pin": "12"}, headers=h)        # formato inválido
    assert r.status_code == 400 and "4 y 8" in r.json()["detail"]
    r = client.put("/agentes/aura/pin", json={"pin": PIN}, headers=h)
    assert r.status_code == 200 and r.json() == {"ok": True}
    r = client.get("/agentes/aura/pin", headers=h)
    assert r.json()["fijado"] is True
    assert PIN not in r.text                                                    # el valor jamás sale
    assert aura_pin.CLAVE_PIN not in r.text


def test_rest_pin_exige_superuser(client: TestClient, session: Session, token: str):
    """Sin el permiso `superuser` ni se consulta ni se fija (el admin del seed no lo trae)."""
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/agentes/aura/pin", headers=h).status_code == 403
    assert client.put("/agentes/aura/pin", json={"pin": PIN}, headers=h).status_code == 403


# ───────────── CATÁLOGO == DESPACHADO, Y EL PROMPT CUENTA LA V2 COMPLETA ─────────────

def test_catalogo_y_despachador_dicen_lo_mismo():
    assert set(AURA.capacidades) == _IMPLEMENTADAS
    assert set(AURA.permisos_tools) == set(AURA.capacidades)
    assert set(AURA.permisos_tools.values()) <= set(AURA.permisos)
    assert AURA.permisos_tools["administrar"] == "superuser"
    # el prompt v2: protocolo de PIN, Centinela como vigilante, y ya NO es solo lectura
    assert "PIN" in SYSTEM and "desbloquear_escritura" in SYSTEM
    assert "CENTINELA" in SYSTEM and "pin_requerido" in SYSTEM
    assert "SOLO LECTURA" not in SYSTEM
    assert any("PIN" in lim for lim in AURA.limites)


def test_aura_agente_pasarela_pin_end_to_end(session: Session):
    c = _centro(session)
    reconciliar(session, c)                       # siembra config desde el catálogo
    cfg = ConfigService(session)
    actual = cfg.resolve("aura.config", centro_id=c, sistema="aura", default={}) or {}
    actual["activa"] = True                        # su interruptor: capacidad_activa exige los tres verdes
    caps = dict(actual.get("capacidades") or {})
    caps.update({"consultar_centinela": True, "listar_acciones": True,
                 "desbloquear_escritura": True, "administrar": True})
    actual["capacidades"] = caps
    cfg.set("aura.config", actual, centro_id=c, sistema="aura")

    ag = AuraAgente(session, c, usuario_id=_admin(session, c))

    # la oferta son las 7 del catálogo, con ESQUEMA real de código (la BD guarda {})
    tools = {t["function"]["name"]: t for t in ag.herramientas()}
    assert set(tools) == _IMPLEMENTADAS
    assert tools["desbloquear_escritura"]["function"]["parameters"].get("required") == ["pin"]
    assert "modulo" in tools["administrar"]["function"]["parameters"]["properties"]

    # escritura end-to-end: bloqueada sin PIN, y el catálogo de acciones es real
    out = json.loads(ag.ejecutar("administrar", {
        "modulo": "configuracion", "accion": "modificar",
        "datos": {"clave": "prueba.e2e", "valor": 1}}))
    assert out["error"] == "pin_requerido"
    assert cfg.resolve("prueba.e2e", centro_id=c, sistema="ia", default=None) is None

    out = json.loads(ag.ejecutar("listar_acciones", {}))
    mods = {(a["modulo"], a["accion"]) for a in out["acciones"]}
    assert ("centinela", "revisar") in mods and ("usuarios", "crear") in mods

    out = json.loads(ag.ejecutar("desbloquear_escritura", {"pin": PIN}))
    assert out["ok"] is False    # sin PIN fijado: la herramienta explica cómo fijarlo
