"""Centinela/Victor — piezas nuevas verificables sin Postgres real (SQLite de test):
migración de objetivos legados, whitelist de Docker, y el freno anti-fuerza-bruta
(bug real reproducido 24-jul-2026: bloqueaba por IP compartida, no solo por email)."""
import pytest


# ───────────────────── migración de objetivos legados (§2) ─────────────────────
def test_migrar_objetivos_propaga_legado_conectores():
    from application.services.centinela_service import _migrar_objetivos

    objetivos = {"conectores": False, "backend": True}
    resultado = _migrar_objetivos(dict(objetivos))
    assert resultado["whatsapp"] is False
    assert resultado["email_saliente"] is False
    assert resultado["email_imap"] is False
    assert resultado["orthanc"] is False
    assert resultado["google_drive"] is False
    assert resultado["backend"] is True   # no tocado


def test_migrar_objetivos_sin_legado_no_inventa_nada():
    from application.services.centinela_service import _migrar_objetivos

    resultado = _migrar_objetivos({"backend": True})
    assert "whatsapp" not in resultado   # el default True lo aplica `vigila()` después, no esto


# ───────────────────── web de la clínica (objetivo `frontend`) ─────────────────────
def test_host_gateway_lee_la_ruta_por_defecto(tmp_path, monkeypatch):
    """La IP del anfitrión se deduce de /proc/net/route (little-endian), NO se fija a mano:
    la subred del bridge de Docker cambia al recrear el stack."""
    from infrastructure import host_net

    ruta = tmp_path / "route"
    ruta.write_text(
        "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n"
        "eth0\t00000000\t010014AC\t0003\t0\t0\t0\t00000000\n"          # 172.20.0.1
        "eth0\t000014AC\t00000000\t0001\t0\t0\t0\t0000FFFF\n"
    )
    monkeypatch.setattr(host_net, "_CACHE", None)
    monkeypatch.setattr("builtins.open", lambda *a, **k: ruta.open())
    assert host_net.host_gateway() == "172.20.0.1"


def test_frontend_caido_se_reporta_como_error(session, monkeypatch):
    """Si la web no responde, Centinela lo marca en ERROR (no lo deja pasar en silencio)."""
    import httpx
    from application.services.centinela_service import CentinelaService

    def _boom(*a, **k):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", _boom)
    res = CentinelaService(session)._check_frontend()
    assert res["estado"] == "error"
    assert "respaldo" in res["detalle"]   # informa de que el paciente ve la página de respaldo


def test_frontend_sirviendo_es_ok_aunque_redirija(session, monkeypatch):
    """Un 307 al login es web EN PIE, no un fallo — el error sería no responder o dar 5xx."""
    import httpx
    from application.services.centinela_service import CentinelaService

    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(307))
    assert CentinelaService(session)._check_frontend()["estado"] == "ok"

    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(500))
    assert CentinelaService(session)._check_frontend()["estado"] == "error"


# ───────────────────── whitelist de contenedores reiniciables (§3) ─────────────────────
def test_docker_client_rechaza_contenedor_no_permitido():
    from infrastructure.docker_client import DockerError, restart_contenedor

    with pytest.raises(DockerError):
        restart_contenedor("makingsmiles-postgres")   # ni siquiera intenta hablar con el socket


def test_docker_client_whitelist_config_solo_restringe_nunca_amplia():
    from infrastructure.docker_client import DockerError, restart_contenedor

    # Aunque la config JSON "permita" un nombre fuera del techo duro de código, se rechaza.
    with pytest.raises(DockerError):
        restart_contenedor("makingsmiles-postgres", whitelist_config=["makingsmiles-postgres"])


# ───────────────────── whatsapp_monitor (§3) ─────────────────────
def test_whatsapp_monitor_cuenta_solo_fallos_recientes_del_centro(session):
    from infrastructure import whatsapp_monitor

    whatsapp_monitor.registrar_fallo(session, 1, "sendText", "Connection Closed")
    whatsapp_monitor.registrar_fallo(session, 1, "sendText", "Connection Closed")
    whatsapp_monitor.registrar_fallo(session, 2, "sendText", "otro centro, no debe contar")

    assert whatsapp_monitor.fallos_recientes(session, 1, 15) == 2
    assert whatsapp_monitor.fallos_recientes(session, 2, 15) == 1


# ───────────────────── freno anti-fuerza-bruta — bug real de IP compartida ─────────────────────
def test_login_bloquea_por_email_no_por_ip_compartida(client, session):
    """Reproduce el incidente real: Irene falla 5 veces con su contraseña → su cuenta se
    bloquea. Juan Antonio, MISMA IP (mismo TestClient), contraseña CORRECTA → debe poder
    entrar sin problema (antes de este fix, el `OR ip==...` lo bloqueaba también a él)."""
    from datetime import date
    from domain.models.identidad import Usuario, UsuarioPeriodo
    from infrastructure.security import hash_password

    otro = Usuario(email="otro@demo.local", nombre="Otro", password_hash=hash_password("otro1234"))
    session.add(otro); session.commit(); session.refresh(otro)
    session.add(UsuarioPeriodo(usuario_id=otro.id, centro_id=1, orden=0,
                               staff_tipo="RECEPCION", fecha_alta=date(2026, 1, 1)))
    session.commit()

    for _ in range(5):
        r = client.post("/auth/login", json={"email": "admin@makingsmiles.local", "password": "MAL"})
        assert r.status_code == 401

    bloqueado = client.post("/auth/login", json={"email": "admin@makingsmiles.local", "password": "admin1234"})
    assert bloqueado.status_code == 401
    assert "intentos fallidos" in bloqueado.json()["detail"].lower()

    # Misma IP (mismo cliente de test), OTRA cuenta, contraseña correcta → debe entrar.
    otro_ok = client.post("/auth/login", json={"email": "otro@demo.local", "password": "otro1234"})
    assert otro_ok.status_code == 200


def test_intentos_fallidos_por_ip_cuenta_emails_distintos_sin_bloquear(client, session):
    """`intentos_fallidos_por_ip` es SOLO para detección (objetivo `autenticacion`) — nunca
    bloquea. Comprueba que cuenta EMAILS DISTINTOS, no el nº de fallos en bruto."""
    from application.services.auth_service import AuthService

    client.post("/auth/login", json={"email": "a@demo.local", "password": "MAL"})
    client.post("/auth/login", json={"email": "a@demo.local", "password": "MAL"})
    client.post("/auth/login", json={"email": "b@demo.local", "password": "MAL"})

    res = AuthService(session).intentos_fallidos_por_ip("testclient", 15)
    assert res["intentos"] == 3
    assert res["emails_distintos"] == 2


# ───────────────── reparación de WhatsApp: 500 de sendText con instancia "open" (29-oct-2026) ─────────────────
@pytest.fixture
def wa(session, monkeypatch):
    """Centinela con Evolution falso: connection_state siempre 'open' (el zombi real)."""
    from application.services import centinela_service as cs
    from application.services.auth_service import AuthService
    from domain.models.config import Integracion

    llamadas = {"instance": 0, "docker": 0}

    class FakeEvo:
        def __init__(self, cfg): ...
        def connection_state(self): return {"instance": {"state": "open"}}
        def restart_instance(self): llamadas["instance"] += 1

    monkeypatch.setattr(cs, "EvolutionClient", FakeEvo)
    monkeypatch.setattr(cs, "restart_contenedor", lambda *a, **k: llamadas.__setitem__("docker", llamadas["docker"] + 1))
    session.add(Integracion(centro_id=1, tipo="whatsapp", config={"url_api": "x"}, activo=True))
    session.commit()
    svc = cs.CentinelaService(session)
    audit = lambda accion, rec=None, det=None, exito=True: AuthService(session).audit(  # noqa: E731
        accion, centro_id=1, recurso=rec, detalle=det, exito=exito)
    return svc, session, llamadas, audit


def _fallo(session):
    from infrastructure import whatsapp_monitor
    whatsapp_monitor.registrar_fallo(session, 1, "sendText", "500 Internal Server Error")


def test_whatsapp_un_solo_fallo_no_repara(wa):
    svc, session, llamadas, audit = wa
    _fallo(session)
    assert svc._check_whatsapp(1, True, audit)["estado"] == "ok"
    assert llamadas == {"instance": 0, "docker": 0}


def test_whatsapp_dos_fallos_con_instancia_open_reinician_instancia(wa):
    svc, session, llamadas, audit = wa
    _fallo(session); _fallo(session)
    r = svc._check_whatsapp(1, True, audit)
    assert r["estado"] == "warn" and llamadas["instance"] == 1


def test_whatsapp_un_fallo_tras_reparar_escala_a_contenedor(wa):
    from datetime import datetime, timedelta
    from sqlmodel import select
    from domain.models.auditoria import Auditoria
    svc, session, llamadas, audit = wa
    _fallo(session); _fallo(session)
    svc._check_whatsapp(1, True, audit)                       # instance_restart
    rep = session.exec(select(Auditoria).where(Auditoria.accion == "centinela.reparar.whatsapp")).one()
    rep.created_at = datetime.utcnow() - timedelta(seconds=60)   # ya pasó ESPERA_SOFT_SEG
    session.add(rep); session.commit()
    _fallo(session)                                           # UN fallo posterior basta
    svc._check_whatsapp(1, True, audit)
    assert llamadas["docker"] == 1


def test_whatsapp_fallos_anteriores_a_la_reparacion_no_cuentan(wa):
    from datetime import datetime, timedelta
    from sqlmodel import select
    from domain.models.auditoria import Auditoria
    svc, session, llamadas, audit = wa
    _fallo(session); _fallo(session)
    svc._check_whatsapp(1, True, audit)                       # instance_restart
    rep = session.exec(select(Auditoria).where(Auditoria.accion == "centinela.reparar.whatsapp")).one()
    rep.created_at = datetime.utcnow() + timedelta(seconds=1)    # la reparación es posterior a los fallos
    session.add(rep); session.commit()
    r = svc._check_whatsapp(1, True, audit)
    assert r["estado"] == "ok" and llamadas["docker"] == 0


def test_frontend_no_alcanzable_en_directo_pero_publico_ok(session, monkeypatch):
    """La web escucha en 127.0.0.1: desde el contenedor la sonda directa falla aunque la web esté bien.
    Si por la dirección pública responde la web real (firma Next.js), es OK, no falsa alarma."""
    import httpx
    from application.services.centinela_service import CentinelaService

    def _get(url, *a, **k):
        if "/login" in url:
            return httpx.Response(200, headers={"x-powered-by": "Next.js"})
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", _get)
    res = CentinelaService(session)._check_frontend()
    assert res["estado"] == "ok" and "pública" in res["detalle"]


def test_frontend_publico_con_pagina_de_respaldo_es_error(session, monkeypatch):
    """Caddy sirve su página de respaldo con 200 cuando la web cae: sin firma de Next.js = ERROR."""
    import httpx
    from application.services.centinela_service import CentinelaService

    def _get(url, *a, **k):
        if "/login" in url:
            return httpx.Response(200, headers={})
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", _get)
    res = CentinelaService(session)._check_frontend()
    assert res["estado"] == "error" and "respaldo" in res["detalle"]

    monkeypatch.setattr(httpx, "get", lambda url, *a, **k: httpx.Response(503) if "/login" in url else (_ for _ in ()).throw(httpx.ConnectError("x")))
    assert CentinelaService(session)._check_frontend()["estado"] == "error"



# ───────────── IA de radiografías (ia-dental + OralGPT en pc-escaner) ─────────────
def _ia(monkeypatch, num, oral, oral_url="http://pc/health"):
    """num/oral: dict (200 con ese JSON), int (código HTTP) o Exception."""
    import httpx
    from domain.config.settings import settings
    from infrastructure import ia_dental_client

    monkeypatch.setattr(ia_dental_client, "IA_DENTAL_URL", "http://ia-dental:8100")
    monkeypatch.setattr(settings, "oralgpt_health_url", oral_url)

    def _get(url, *a, **k):
        v = oral if url == oral_url else num
        if isinstance(v, Exception):
            raise v
        if isinstance(v, int):
            return httpx.Response(v, request=httpx.Request("GET", url))
        return httpx.Response(200, json=v, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", _get)


def test_ia_dental_todo_bien(session, monkeypatch):
    from application.services.centinela_service import CentinelaService
    _ia(monkeypatch, {"ok": True}, {"ok": True, "modelos": ["canal_seno", "11clases"], "cuda": True})
    r = CentinelaService(session)._check_ia_dental()
    assert r["estado"] == "ok" and "nervio/seno OK" in r["detalle"]


def test_ia_dental_pc_escaner_caido_es_aviso_no_error(session, monkeypatch):
    import httpx
    from application.services.centinela_service import CentinelaService
    _ia(monkeypatch, {"ok": True}, httpx.ConnectError("sin ruta"))
    r = CentinelaService(session)._check_ia_dental()
    assert r["estado"] == "warn" and "pc-escaner" in r["detalle"] and "solo la numeración" in r["detalle"]


def test_ia_dental_sin_gpu_o_sin_modelos_es_aviso(session, monkeypatch):
    from application.services.centinela_service import CentinelaService
    _ia(monkeypatch, {"ok": True}, {"ok": True, "modelos": ["canal_seno", "11clases"], "cuda": False})
    assert "SIN GPU" in CentinelaService(session)._check_ia_dental()["detalle"]
    _ia(monkeypatch, {"ok": True}, {"ok": True, "modelos": ["canal_seno"], "cuda": True})
    r = CentinelaService(session)._check_ia_dental()
    assert r["estado"] == "warn" and "11clases" in r["detalle"]


def test_ia_dental_numeracion_caida_es_error(session, monkeypatch):
    import httpx
    from application.services.centinela_service import CentinelaService
    _ia(monkeypatch, httpx.ConnectError("caído"), {"ok": True, "modelos": ["canal_seno", "11clases"], "cuda": True})
    r = CentinelaService(session)._check_ia_dental()
    assert r["estado"] == "error" and "ia-dental" in r["detalle"]


def test_ia_dental_sin_url_de_vigilancia_no_inventa_nada(session, monkeypatch):
    from application.services.centinela_service import CentinelaService
    _ia(monkeypatch, {"ok": True}, {"ok": True}, oral_url="")
    r = CentinelaService(session)._check_ia_dental()
    assert r["estado"] == "ok" and "sin vigilar" in r["detalle"]
