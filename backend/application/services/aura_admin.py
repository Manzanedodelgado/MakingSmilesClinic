"""Poder total de Aura, a registro — el área SuperUser entera, tras el PIN.

Decisión de jmd (14-oct-2026): Aura deja de ser de solo lectura. Puede crear y modificar
usuarios, configuración del centro, agentes e incluso disparar la revisión de Centinela
para apagar fuegos — pero con las dos barreras de siempre, ninguna se sustituye a otra:

  1. PIN de SuperUser (aura_pin): sin sesión desbloqueada no hay escritura.
  2. Permisos de la app: cada acción declara su permiso y la web sigue siendo la dueña —
     si SuperUser le quita `config.editar` a Aura en la pantalla, su herramienta corta
     igual que cortaría la API.

El registro es la fuente de verdad de QUÉ puede hacer: `listar_acciones` lo sirve al modelo
y a la pantalla, así que añadir poder nuevo es añadir una fila — el prompt no se reescribe.
Todo lo escrito queda auditado como `aura.admin.{modulo}.{accion}` (el PIN jamás).
"""
from __future__ import annotations

from typing import Any, Callable

import httpx
from sqlmodel import Session, select

from application.services.aura_pin import CLAVE_PIN, desbloqueada
from application.services.auth_service import AuthService
from application.services.config_service import ConfigService
from domain.config.settings import settings

Timeout = 15.0


# ──────────────────────────── llamadas al router interno ────────────────────────────
# Usuarios se mutan SIEMPRE por el router interno (mismo camino que usa el área SuperUser
# de la plataforma): una sola implementación del alta/baja, no un clon en Aura.
def _interno(method: str, path: str, **kwargs) -> dict:
    # Sin envoltorio (regla del gate): un fallo de red/JSON PROPAGA y lo recoge el
    # despachador, que envuelve su propia función. El detalle de error va por r.text,
    # que no lanza.
    r = httpx.request(method, f"{settings.internal_api_base_url}{path}",
                      headers={"X-Internal-Key": settings.internal_api_key},
                      timeout=Timeout, **kwargs)
    if r.status_code >= 400:
        return {"ok": False, "error": str(r.text)[:400]}
    return r.json() if r.content else {"ok": True}


# ──────────────────────────────────── USUARIOS ────────────────────────────────────
def _usuarios_listar(session: Session, centro_id: int, _datos: dict) -> dict:
    from domain.models.identidad import Rol, UserCenterRole, Usuario, UsuarioPeriodo
    filas = session.exec(select(UserCenterRole, Usuario, Rol).join(
        Usuario, UserCenterRole.usuario_id == Usuario.id).join(
        Rol, UserCenterRole.rol_id == Rol.id).where(
        UserCenterRole.centro_id == centro_id)).all()
    # `Usuario.activo` no existe: "activo" se deriva de tener un periodo laboral abierto
    # (fecha_baja vacía) — una sola consulta, sin N+1.
    abiertos = {p.usuario_id for p in session.exec(
        select(UsuarioPeriodo).where(UsuarioPeriodo.fecha_baja.is_(None))).all()}
    return {"personal": [{"usuario_id": u.id, "nombre": u.nombre, "email": u.email,
                          "rol": r.nombre, "activo": u.id in abiertos}
                         for _a, u, r in filas]}


def _usuarios_crear(session: Session, centro_id: int, datos: dict) -> dict:
    res = _interno("POST", f"/internal/tenant/{centro_id}/personal",
                   json={"nombre": (datos.get("nombre") or "").strip(),
                         "email": (datos.get("email") or "").strip().lower()})
    if not res.get("ok"):
        return res
    # Segundo paso natural del alta: enviar el enlace para que la persona fije su
    # contraseña en su lugar — Aura no reparte contraseñas por su cuenta.
    usuario_id = (res.get("usuario") or {}).get("usuario_id") or res.get("usuario_id")
    extra = _interno("POST", f"/internal/tenant/{centro_id}/personal/{usuario_id}/reset-password") \
        if usuario_id else {"ok": False}
    return {"ok": True, "alta": res, "enlace_fijar_password_enviado": bool(extra.get("ok")),
            "nota": "La persona recibirá un enlace para fijar su propia contraseña."}


def _usuarios_quitar(session: Session, centro_id: int, datos: dict) -> dict:
    uid = datos.get("usuario_id")
    if not uid:
        return {"ok": False, "error": "Falta usuario_id."}
    return _interno("DELETE", f"/internal/tenant/{centro_id}/personal/{uid}")


def _usuarios_reset(session: Session, centro_id: int, datos: dict) -> dict:
    uid = datos.get("usuario_id")
    if not uid:
        return {"ok": False, "error": "Falta usuario_id."}
    return _interno("POST", f"/internal/tenant/{centro_id}/personal/{uid}/reset-password")


# ────────────────────────────────── CONFIGURACIÓN ──────────────────────────────────
def _sistema_de_clave(clave: str) -> str:
    from application.services.agentes_config import SISTEMA
    return SISTEMA.get(clave, "ia")


def _config_consultar(session: Session, centro_id: int, datos: dict) -> dict:
    clave = datos.get("clave")
    if not clave:
        return {"ok": False, "error": "Falta la clave a consultar."}
    valor = ConfigService(session).resolve(clave, centro_id=centro_id,
                                           sistema=_sistema_de_clave(clave), default=None)
    return {"ok": True, "clave": clave, "valor": valor}


def _config_modificar(session: Session, centro_id: int, datos: dict) -> dict:
    clave = (datos.get("clave") or "").strip()
    if not clave or "valor" not in datos:
        return {"ok": False, "error": "Faltan clave y valor."}
    if clave == CLAVE_PIN:
        # Aura no se cambia su propio PIN por herramienta: un desbloqueo no debe poder
        # perpetuarse. Se cambia desde Config → Agentes IA, con SuperUser delante.
        return {"ok": False, "error": "El PIN de Aura solo se cambia desde Config → Agentes IA."}
    ConfigService(session).set(clave, datos["valor"], centro_id=centro_id,
                               sistema=_sistema_de_clave(clave))
    return {"ok": True, "clave": clave, "valor": datos["valor"]}


# ───────────────────────────────────── AGENTES ─────────────────────────────────────
def _agentes_consultar(session: Session, centro_id: int, _datos: dict) -> dict:
    from application.services.agentes_config import estado as estado_agentes
    return {"ok": True, "agentes": estado_agentes(session, centro_id)}


def _agentes_modificar(session: Session, centro_id: int, datos: dict) -> dict:
    from application.services.agentes_config import MAX_LIMITES, MAX_LIMITE_CHARS, SISTEMA
    from domain.config.agentes import POR_ID
    a = POR_ID.get((datos.get("agente") or "").strip())
    if not a:
        return {"ok": False, "error": "Agente desconocido."}
    sistema = SISTEMA.get(a.config_key, "ia")
    cfg = ConfigService(session)
    actual = cfg.resolve(a.config_key, centro_id=centro_id, sistema=sistema, default={}) or {}

    if datos.get("activa") is not None:
        if a.id == "gestor":
            # Mismo criterio que la pantalla: el interruptor real de Gestor es el watch de
            # Gmail — mentir "encendido" con el pipeline muerto es peor que una llamada de más.
            from infrastructure.external_apis import gmail_watch
            res = (gmail_watch.activar_watch(session, centro_id) if datos["activa"]
                   else gmail_watch.detener_watch(session, centro_id))
            if not res.get("ok"):
                return {"ok": False, "error": res.get("error") or "No se pudo cambiar el watch de Gmail"}
        actual["activa"] = bool(datos["activa"])

    if datos.get("capacidad") is not None:
        if datos["capacidad"] not in a.capacidades:
            return {"ok": False, "error": f"«{datos['capacidad']}» no es una capacidad de {a.nombre}."}
        caps = dict(actual.get("capacidades") or {})
        caps[datos["capacidad"]] = bool(datos.get("valor"))
        actual["capacidades"] = caps

    if datos.get("limites_texto") is not None:
        limites = [x.strip() for x in datos["limites_texto"] if isinstance(x, str) and x.strip()]
        if len(limites) > MAX_LIMITES:
            return {"ok": False, "error": f"Demasiados límites (máximo {MAX_LIMITES})."}
        if any(len(x) > MAX_LIMITE_CHARS for x in limites):
            return {"ok": False, "error": f"Cada límite puede tener como mucho {MAX_LIMITE_CHARS} caracteres."}
        actual["limites_texto"] = limites

    if datos.get("permisos_requiere") is not None:
        from domain.models.identidad import Permiso
        universo = {p.codigo for p in session.exec(select(Permiso)).all()}
        pedidos = [x.strip() for x in datos["permisos_requiere"] if isinstance(x, str)]
        if not set(pedidos) <= universo:
            return {"ok": False, "error": f"Permisos desconocidos: {sorted(set(pedidos) - universo)}"}
        actual.setdefault("permisos", {})["requiere"] = pedidos

    if not any(k in datos for k in ("activa", "capacidad", "limites_texto", "permisos_requiere")):
        return {"ok": False, "error": "Nada que cambiar: indica activa, capacidad, limites_texto o permisos_requiere."}
    cfg.set(a.config_key, actual, centro_id=centro_id, sistema=sistema)
    return {"ok": True, "agente": a.id, "cambiado": {k: datos[k] for k in
            ("activa", "capacidad", "valor", "limites_texto", "permisos_requiere") if k in datos}}


# ──────────────────────────────────── CENTINELA ────────────────────────────────────
def _centinela_estado(session: Session, centro_id: int, datos: dict) -> dict:
    """Lo que Centinela ha dicho ÚLTIMAMENTE, sin ejecutar nada: su bitácora es auditoría
    (`centinela.tick` en cada cambio de nivel y `centinela.alerta` por alerta enviada)."""
    from datetime import datetime, timedelta
    from domain.models.auditoria import Auditoria
    dias = int(datos.get("dias") or 2)
    desde = datetime.utcnow() - timedelta(days=dias)
    tick = session.exec(select(Auditoria).where(
        Auditoria.accion == "centinela.tick", Auditoria.centro_id == centro_id
    ).order_by(Auditoria.created_at.desc())).first()
    alertas = session.exec(select(Auditoria).where(
        Auditoria.accion == "centinela.alerta", Auditoria.centro_id == centro_id,
        Auditoria.created_at > desde
    ).order_by(Auditoria.created_at.desc())).all()
    avisos = []
    for al in alertas[:10]:
        d = al.detalle or {}
        no_ok = [c for c in (d.get("checks") or []) if isinstance(c, dict) and c.get("estado") != "ok"]
        avisos.append({"cuando": al.created_at.isoformat() if al.created_at else None,
                       "nivel": d.get("nivel"), "enviados": d.get("canales_enviados") or [],
                       "fallando": [{"sistema": c.get("label") or c.get("sistema"),
                                     "estado": c.get("estado"), "detalle": str(c.get("detalle"))[:200]}
                                    for c in no_ok[:8]]})
    t = (tick.detalle or {}) if tick else {}
    return {"ok": True,
            "nivel_actual": t.get("nivel", "desconocido"),
            "ultima_revision": tick.created_at.isoformat() if tick and tick.created_at else None,
            "origen": t.get("origen"),
            "avisos": avisos}


def _centinela_revisar(session: Session, centro_id: int, _datos: dict) -> dict:
    """Ejecuta un ciclo de Centinela al momento — con su remediación (reinicios, cambio de
    modelo caído). Es apagar el fuego, no solo mirarlo."""
    from application.services.centinela_service import CentinelaService
    return CentinelaService(session).ejecutar(centro_id, origen="aura")


# ───────────────────────────────────── REGISTRO ─────────────────────────────────────
# pin=False es consulta; pin=True exige PIN. `requiere` es el permiso de la app que la web
# exige para la misma acción — Aura no es una puerta trasera de nadie.
ACCIONES: dict[str, dict[str, dict[str, Any]]] = {
    "usuarios": {
        "listar":         {"fn": _usuarios_listar,   "pin": False, "requiere": "superuser",
                           "desc": "Quién tiene acceso a este centro (nombre, email, rol, activo)."},
        "crear":          {"fn": _usuarios_crear,    "pin": True,  "requiere": "superuser",
                           "desc": "Alta de persona: nombre + email; le llega el enlace para fijar contraseña."},
        "quitar":         {"fn": _usuarios_quitar,   "pin": True,  "requiere": "superuser",
                           "desc": "Baja del centro por usuario_id (no borra a la persona, le quita el acceso)."},
        "reset_password": {"fn": _usuarios_reset,    "pin": True,  "requiere": "superuser",
                           "desc": "Reenviar el enlace de fijar contraseña por usuario_id."},
    },
    "configuracion": {
        "consultar":      {"fn": _config_consultar,  "pin": False, "requiere": "config.ver",
                           "desc": "Valor de una clave de configuración del centro."},
        "modificar":      {"fn": _config_modificar,  "pin": True,  "requiere": "config.editar",
                           "desc": "Cambiar una clave de configuración del centro (cualquiera salvo el PIN de Aura)."},
    },
    "agentes": {
        "consultar":      {"fn": _agentes_consultar, "pin": False, "requiere": "config.ver",
                           "desc": "Estado de los agentes de Config → Agentes IA (encendidos, modelo, capacidades)."},
        "modificar":      {"fn": _agentes_modificar, "pin": True,  "requiere": "config.editar",
                           "desc": "Cambiar un agente: activa, capacidad+valor, limites_texto o permisos_requiere."},
    },
    "centinela": {
        "estado":         {"fn": _centinela_estado,  "pin": False, "requiere": "superuser",
                           "desc": "Nivel actual de Centinela y avisos recientes (qué está fallando)."},
        "revisar":        {"fn": _centinela_revisar, "pin": True,  "requiere": "superuser",
                           "desc": "Ejecutar un ciclo de Centinela AHORA, con remediación (reinicia lo caído)."},
    },
}


def listar_acciones() -> list[dict]:
    return [{"modulo": m, "accion": a, "requiere_pin": meta["pin"],
             "permiso": meta["requiere"], "descripcion": meta["desc"]}
            for m, acciones in ACCIONES.items() for a, meta in acciones.items()]


def _audit_admin(session: Session, usuario_id: int | None, centro_id: int,
                 modulo: str, accion: str, datos: dict | None, *, exito: bool,
                 detalle: dict | None = None) -> None:
    # Sin envoltorio (regla del gate): si la auditoría falla, la operación falla — un
    # cambio sin registro no es un cambio, es un agujero. AuthService.audit normaliza
    # el detalle a JSON por su cuenta.
    AuthService(session).audit(f"aura.admin.{modulo}.{accion}", usuario_id=usuario_id,
                               centro_id=centro_id, exito=exito,
                               detalle={"datos": datos, **(detalle or {})})


def ejecutar(session: Session, centro_id: int, usuario_id: int | None,
             modulo: str, accion: str, datos: dict | None) -> dict:
    """Barreras en orden: registro → permiso de la app → PIN → acción. Audita el intento
    y el resultado; los parámetros entran en el detalle, el PIN nunca."""
    meta = (ACCIONES.get(modulo) or {}).get(accion)
    if not meta:
        return {"error": f"No existe la acción «{accion}» del módulo «{modulo}».",
                "acciones": listar_acciones()}
    permisos = AuthService(session).permisos_de(usuario_id, centro_id) if usuario_id else set()
    if meta["requiere"] not in permisos:
        _audit_admin(session, usuario_id, centro_id, modulo, accion, datos, exito=False,
                     detalle={"motivo": f"permiso_insuficiente:{meta['requiere']}"})
        return {"error": f"La web exige el permiso «{meta['requiere']}» para {modulo}.{accion} "
                         "y Aura no lo tiene concedido."}
    if meta["pin"] and not desbloqueada(centro_id, usuario_id):
        # Intento de escritura sin sesión desbloqueada: se audita igual que un fallo de
        # login — que Aura cuente con precisión quién ha pedido escribir sin PIN.
        _audit_admin(session, usuario_id, centro_id, modulo, accion, datos, exito=False,
                     detalle={"motivo": "pin_requerido"})
        return {"error": "pin_requerido",
                "mensaje": f"Escritura bloqueada: {modulo}.{accion} pide el PIN de SuperUser. "
                           "Pídeselo en este chat y usa desbloquear_escritura(pin); queda "
                           "desbloqueado 15 minutos.",
                "accion": f"{modulo}.{accion}"}
    try:
        res = meta["fn"](session, centro_id, datos or {})
    except Exception as e:  # raiz: error de acción vuelve al LLM como herramienta, no tumba la charla
        _audit_admin(session, usuario_id, centro_id, modulo, accion, datos, exito=False,
                     detalle={"motivo": f"excepcion:{type(e).__name__}"})
        return {"error": str(e)[:400]}
    exito = bool(res.get("ok", True)) if isinstance(res, dict) else True
    _audit_admin(session, usuario_id, centro_id, modulo, accion, datos, exito=exito)
    return res
