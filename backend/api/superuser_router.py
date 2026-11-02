"""SUPERUSER — panel del supercreador (área SuperUser). Acceso EXCLUSIVO: permiso `superuser`.

Este router NUNCA importa modelos operativos (Centro, Usuario, Paciente, Cita...) ni abre
sesión contra la BBDD operativa de un centro — esa es la BBDD de PLATAFORMA
(`makingsmiles_platform`, sesión propia `get_platform_session`), físicamente separada.
Todo lo que sí necesita tocar datos operativos (provisionar un centro, personal, salud,
asociación) se delega vía HTTP al router interno `api/internal_tenant_router.py`
(`/internal/tenant/...`), protegido por clave compartida — el único punto de contacto.

Excepción deliberada: "Explorador de Base de Datos" y el dashboard de métricas SÍ leen la
BBDD operativa directamente — es una herramienta de inspección/depuración de solo lectura,
no parte del registro de tenants, y su función es precisamente esa (ver DB_SEPARACION.md
si se documenta más adelante)."""
import json
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session

from api.audit_helper import _audit

logger = logging.getLogger(__name__)
from api.auth_deps import CurrentUser, get_current_centro, require_permission
from application.services.config_service import ConfigService
from domain.config.settings import settings
from infrastructure.config.db import get_session
from infrastructure.config.platform_db import get_platform_session

router = APIRouter(prefix="/superuser", tags=["superuser"])

_SU = require_permission("superuser")   # dependencia: exige el permiso superuser
_MAX_FILAS = 1000                       # cap duro de filas devueltas por el explorador

# ── Catálogo de MÓDULOS (áreas de la web) y PLANES (réplica de la .37) ──────
# `fijo` = siempre disponible (no se contrata). El resto se activan por centro según el plan.
MODULOS = [
    {"id": "inicio", "label": "Inicio", "fijo": True},
    {"id": "agenda", "label": "Agenda", "pack": "lite"},
    {"id": "pacientes", "label": "Pacientes", "pack": "lite"},
    {"id": "whatsapp", "label": "WhatsApp", "pack": "connect"},
    {"id": "motion", "label": "Motion", "pack": "connect"},
    {"id": "ia", "label": "IAs", "pack": "connect"},
    {"id": "crm", "label": "CRM", "pack": "improve"},
    {"id": "gestoria", "label": "Gestoría", "pack": "improve"},
    {"id": "informes", "label": "Informes", "pack": "improve"},
    {"id": "config", "label": "Config", "fijo": True},
    {"id": "superuser", "label": "SuperUser", "fijo": True},
]
PLANES = {
    "lite": ["agenda", "pacientes"],
    "connect": ["agenda", "pacientes", "whatsapp", "motion", "ia"],
    "improve": ["agenda", "pacientes", "whatsapp", "motion", "ia", "crm", "gestoria", "informes"],
}
_MODULOS_CONTRATABLES = {m["id"] for m in MODULOS if not m.get("fijo")}
_ESTADOS = ("activo", "inactivo", "suspendido")


def _tablas_publicas(session: Session) -> list[str]:
    return [r[0] for r in session.exec(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"
    )).all()]


def _columnas(session: Session, tabla: str) -> list[dict]:
    rows = session.exec(text(
        "SELECT column_name, data_type, is_nullable, character_maximum_length "
        "FROM information_schema.columns WHERE table_schema='public' AND table_name=:t "
        "ORDER BY ordinal_position"
    ), params={"t": tabla}).all()
    return [{"nombre": r[0], "tipo": r[1], "nullable": r[2] == "YES", "longitud": r[3]} for r in rows]


def _tabla_valida(session: Session, tabla: str) -> str:
    """Valida que la tabla existe (whitelist del catálogo) → evita inyección por nombre."""
    if tabla not in _tablas_publicas(session):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Tabla no encontrada: {tabla}")
    return tabla


# ── Dashboard global ───────────────────────────────────────────────────────
@router.get("/dashboard")
def dashboard(_su: CurrentUser = Depends(_SU), session: Session = Depends(get_session)) -> dict:
    def _n(tabla: str) -> int:
        try:
            return int(session.exec(text(f'SELECT count(*) FROM "{tabla}"')).one()[0])
        except Exception:  # raiz: tabla ausente en esta instalación (métrica best-effort); se cuenta como 0
            logger.warning("superuser: dashboard sin tabla %s", tabla, exc_info=True)
            return 0
    return {"metricas": {
        "pacientes": _n("pacientes"), "citas": _n("citas"), "presupuestos": _n("presupuestos"),
        "tratamientos_realizados": _n("tratamientos_realizados"), "usuarios": _n("usuarios"),
        "colaboradores": _n("colaboradores"),
    }}


# ── Apariencia de plataforma (favicon/logo/icono globales) ─────────────────
# Excepción deliberada (igual que Dashboard/Explorador de BD arriba): lee/escribe la BBDD
# operativa vía ConfigService en ámbito plataforma (centro_id=None, clave="plataforma.apariencia").
class AparienciaSet(BaseModel):
    favicon_url: Optional[str] = None
    logo_url: Optional[str] = None
    icono_url: Optional[str] = None


@router.get("/apariencia")
def apariencia_get(_su: CurrentUser = Depends(_SU), session: Session = Depends(get_session)) -> dict:
    return ConfigService(session).resolve("plataforma.apariencia", default={}) or {}


@router.put("/apariencia")
def apariencia_set(data: AparienciaSet, request: Request, su: CurrentUser = Depends(_SU),
                    session: Session = Depends(get_session)) -> dict:
    valor = data.model_dump()
    row = ConfigService(session).set("plataforma.apariencia", valor)
    _audit(session, su, None, "superuser.apariencia.set", "apariencia", request, detalle=valor)
    return row.valor


# ── Explorador de BD (solo lectura) ────────────────────────────────────────
@router.get("/db/tables")
def db_tables(_su: CurrentUser = Depends(_SU), session: Session = Depends(get_session)) -> dict:
    rows = session.exec(text("""
        SELECT t.table_name,
               COALESCE(s.n_live_tup, 0)                                AS filas,
               pg_total_relation_size(format('%I', t.table_name))       AS bytes
        FROM information_schema.tables t
        LEFT JOIN pg_stat_user_tables s ON s.relname = t.table_name
        WHERE t.table_schema='public' AND t.table_type='BASE TABLE'
        ORDER BY t.table_name
    """)).all()
    return {"tablas": [{"nombre": r[0], "filas": int(r[1] or 0), "bytes": int(r[2] or 0)} for r in rows]}


@router.get("/db/tables/{tabla}/schema")
def db_schema(tabla: str, _su: CurrentUser = Depends(_SU), session: Session = Depends(get_session)) -> dict:
    _tabla_valida(session, tabla)
    return {"tabla": tabla, "columnas": _columnas(session, tabla)}


@router.get("/db/tables/{tabla}/rows")
def db_rows(tabla: str, page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200),
            search: str = "", orderBy: str = "", dir: str = "asc",
            _su: CurrentUser = Depends(_SU), session: Session = Depends(get_session)) -> dict:
    _tabla_valida(session, tabla)
    cols = _columnas(session, tabla)
    col_names = {c["nombre"] for c in cols}
    params: dict = {}
    where = ""
    if search.strip():
        # ILIKE sobre TODAS las columnas casteadas a texto (búsqueda simple y segura por parámetro)
        ors = " OR ".join(f'CAST("{c}" AS text) ILIKE :q' for c in col_names)
        where = f" WHERE ({ors})"
        params["q"] = f"%{search.strip()}%"
    orden = ""
    if orderBy and orderBy in col_names:
        d = "DESC" if dir.lower() == "desc" else "ASC"
        orden = f' ORDER BY "{orderBy}" {d}'
    total = int(session.exec(text(f'SELECT count(*) FROM "{tabla}"{where}'), params=params).one()[0])
    params2 = {**params, "lim": min(limit, _MAX_FILAS), "off": (page - 1) * limit}
    filas = session.exec(text(
        f'SELECT * FROM "{tabla}"{where}{orden} LIMIT :lim OFFSET :off'
    ), params=params2).mappings().all()
    return {"tabla": tabla, "total": total, "page": page, "limit": limit,
            "columnas": [c["nombre"] for c in cols], "filas": [dict(f) for f in filas]}


def _validar_select(sql: str) -> str:
    s = sql.strip().rstrip(";").strip()
    low = s.lower()
    if not (low.startswith("select") or low.startswith("with")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo se permiten consultas SELECT (debe comenzar por SELECT o WITH)")
    if ";" in s:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo una sentencia (sin ';')")
    prohibidas = ("insert", "update", "delete", "drop", "alter", "truncate", "create",
                  "grant", "revoke", "copy", "merge", "call")
    palabras = set(low.replace("(", " ").replace(")", " ").replace(",", " ").split())
    mala = palabras & set(prohibidas)
    if mala:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Sentencia no permitida (solo lectura): {', '.join(sorted(mala))}")
    return s


@router.post("/db/query")
def db_query(body: dict, request: Request, _su: CurrentUser = Depends(_SU),
             centro_id: int = Depends(get_current_centro),
             session: Session = Depends(get_session)) -> dict:
    sql = (body or {}).get("sql")
    if not isinstance(sql, str) or not sql.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, 'Falta el campo "sql" con una sentencia SELECT')
    s = _validar_select(sql)
    res = session.exec(text(s)).mappings().fetchmany(_MAX_FILAS)
    filas = [dict(r) for r in res]
    columnas = list(filas[0].keys()) if filas else []
    # Consulta directa a la BD (accede a PII): SIEMPRE con rastro de quién y qué ejecutó.
    _audit(session, _su, centro_id, "superuser.db.query", "db", request,
           {"sql": s[:500], "filas": len(filas)})
    return {"columnas": columnas, "filas": filas, "n": len(filas), "cap": _MAX_FILAS}


# ── Centros: registro de tenants — BBDD DE PLATAFORMA, separada de la operativa ──
def _internal_call(method: str, path: str, **kwargs) -> dict:
    """Único punto por el que SuperUser toca datos operativos de un centro: HTTP al router
    interno (`internal_tenant_router.py`), nunca una query directa desde aquí."""
    try:
        r = httpx.request(method, f"{settings.internal_api_base_url}{path}",
                          headers={"X-Internal-Key": settings.internal_api_key}, timeout=15.0, **kwargs)
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"No se pudo contactar con la API interna del centro: {e}") from e
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:  # raiz: la API interna no devolvió JSON (respuesta no esperada); se usa el texto plano como detalle
            logger.debug("superuser: proxy sin JSON, se usa texto", exc_info=True)
            detail = r.text
        raise HTTPException(r.status_code, detail)
    return r.json()


def _registro_dto(row) -> dict:
    return {"id": row["centro_operativo_id"], "nombre": row["nombre"], "codigo": row["codigo"],
            "estado": row["estado"], "plan": row["plan"], "modulos_activos": row["modulos_activos"] or []}


@router.get("/centros")
def centros_list(_su: CurrentUser = Depends(_SU), pf: Session = Depends(get_platform_session)) -> dict:
    rows = pf.exec(text(
        "SELECT centro_operativo_id, nombre, codigo, estado, plan, modulos_activos FROM platform_centros ORDER BY id"
    )).mappings().all()
    return {"centros": [_registro_dto(r) for r in rows],
            "modulos": MODULOS, "planes": {k: v for k, v in PLANES.items()}}


@router.post("/centros", status_code=201)
def centros_create(body: dict, _su: CurrentUser = Depends(_SU), pf: Session = Depends(get_platform_session)) -> dict:
    """Provisiona un centro OPERATIVO llamando a la API interna (razón social, agenda +
    catálogos, rol admin, primer usuario) y da de alta su registro en la BBDD de plataforma."""
    body = body or {}
    nombre = body.get("nombre", "")
    plan = body.get("plan")
    mods = PLANES.get(plan, []) if plan else []
    res = _internal_call("POST", "/internal/tenant/provisionar", json={
        "nombre": nombre, "admin_nombre": body.get("admin_nombre", ""), "admin_email": body.get("admin_email", ""),
        "actor_usuario_id": _su.usuario_id, "asociado_a_centro_id": body.get("asociado_a_centro_id"),
        "comparte_personal": bool(body.get("comparte_personal")),
        "comparte_razon_social": bool(body.get("comparte_razon_social")),
        "comparte_pacientes": bool(body.get("comparte_pacientes")),
    })
    pf.exec(text(
        "INSERT INTO platform_centros (centro_operativo_id, nombre, estado, plan, modulos_activos) "
        "VALUES (:cid, :n, 'activo', :p, CAST(:m AS jsonb))"
    ), params={"cid": res["centro_id"], "n": nombre, "p": plan, "m": json.dumps(mods)})
    pf.commit()
    return {"id": res["centro_id"], "admin_email": res["admin_email"], "password_temporal": res["password_temporal"],
            "razon_social_compartida_id": res["razon_social_compartida_id"], "personal_compartido": res["personal_compartido"]}


@router.get("/centros/{centro_id}")
def centro_detalle(centro_id: int, _su: CurrentUser = Depends(_SU), pf: Session = Depends(get_platform_session)) -> dict:
    """Ficha completa: el registro (estado/plan/módulos) sale de la BBDD de plataforma;
    datos/razón social/asociación/personal/salud vienen de la API interna del centro."""
    reg = pf.exec(text(
        "SELECT centro_operativo_id, nombre, codigo, estado, plan, modulos_activos FROM platform_centros WHERE centro_operativo_id=:id"
    ), params={"id": centro_id}).mappings().first()
    if not reg:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Centro no encontrado en el registro")
    det = _internal_call("GET", f"/internal/tenant/{centro_id}/detalle")
    return {
        "centro": {**det["centro"], "estado": reg["estado"], "plan": reg["plan"],
                  "modulos_activos": reg["modulos_activos"] or []},
        "razon_social": det["razon_social"], "asociacion": det["asociacion"],
        "personal": det["personal"], "salud": det["salud"],
    }


@router.put("/centros/{centro_id}")
def centros_update(centro_id: int, body: dict, _su: CurrentUser = Depends(_SU),
                   pf: Session = Depends(get_platform_session)) -> dict:
    """Editor real: los campos propios del centro se delegan a la API interna; el nombre,
    si cambia, se refleja también en el registro de plataforma."""
    body = body or {}
    _internal_call("PUT", f"/internal/tenant/{centro_id}", json={**body, "actor_usuario_id": _su.usuario_id})
    if "nombre" in body:
        pf.exec(text("UPDATE platform_centros SET nombre=:n, updated_at=now() WHERE centro_operativo_id=:id"),
               params={"n": body["nombre"], "id": centro_id})
        pf.commit()
    if "codigo" in body:
        pf.exec(text("UPDATE platform_centros SET codigo=:c, updated_at=now() WHERE centro_operativo_id=:id"),
               params={"c": body["codigo"] or None, "id": centro_id})
        pf.commit()
    return {"id": centro_id}


@router.put("/centros/{centro_id}/asociacion")
def centro_asociacion_set(centro_id: int, body: dict, _su: CurrentUser = Depends(_SU)) -> dict:
    """Crear, editar o quitar la asociación DESPUÉS de creado el centro — delegado a la
    API interna (toca personal/razón social operativos, ajenos al registro de plataforma)."""
    body = body or {}
    return _internal_call("PUT", f"/internal/tenant/{centro_id}/asociacion",
                          json={**body, "actor_usuario_id": _su.usuario_id})


@router.post("/centros/{centro_id}/personal")
def centro_personal_add(centro_id: int, body: dict, _su: CurrentUser = Depends(_SU)) -> dict:
    body = body or {}
    return _internal_call("POST", f"/internal/tenant/{centro_id}/personal",
                          json={**body, "actor_usuario_id": _su.usuario_id})


@router.delete("/centros/{centro_id}/personal/{usuario_id}")
def centro_personal_quitar(centro_id: int, usuario_id: int, _su: CurrentUser = Depends(_SU)) -> dict:
    return _internal_call("DELETE", f"/internal/tenant/{centro_id}/personal/{usuario_id}",
                          params={"actor_usuario_id": _su.usuario_id})


@router.post("/centros/{centro_id}/personal/{usuario_id}/reset-password")
def centro_personal_reset_password(centro_id: int, usuario_id: int, _su: CurrentUser = Depends(_SU)) -> dict:
    return _internal_call("POST", f"/internal/tenant/{centro_id}/personal/{usuario_id}/reset-password",
                          json={"actor_usuario_id": _su.usuario_id})


@router.put("/centros/{centro_id}/personal/{usuario_id}/email")
def centro_personal_email(centro_id: int, usuario_id: int, body: dict, _su: CurrentUser = Depends(_SU)) -> dict:
    body = body or {}
    return _internal_call("PUT", f"/internal/tenant/{centro_id}/personal/{usuario_id}/email",
                          json={**body, "actor_usuario_id": _su.usuario_id})


@router.patch("/centros/{centro_id}/estado")
def centros_estado(centro_id: int, body: dict, request: Request, _su: CurrentUser = Depends(_SU),
                   pf: Session = Depends(get_platform_session)) -> dict:
    """Puramente registro de plataforma — nada operativo depende de este campo hoy."""
    estado = (body or {}).get("estado")
    if estado not in _ESTADOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"estado debe ser uno de {_ESTADOS}")
    pf.exec(text("UPDATE platform_centros SET estado=:e, updated_at=now() WHERE centro_operativo_id=:id"),
           params={"e": estado, "id": centro_id})
    pf.commit()
    return {"id": centro_id, "estado": estado}


@router.patch("/centros/{centro_id}/modulos")
def centros_modulos(centro_id: int, body: dict, _su: CurrentUser = Depends(_SU),
                    pf: Session = Depends(get_platform_session)) -> dict:
    """Puramente registro de plataforma — ningún módulo operativo lee este campo hoy."""
    mods = (body or {}).get("modulos", [])
    if not isinstance(mods, list):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "modulos debe ser una lista")
    limpios = [m for m in mods if m in _MODULOS_CONTRATABLES]
    pf.exec(text("UPDATE platform_centros SET modulos_activos=CAST(:m AS jsonb), updated_at=now() WHERE centro_operativo_id=:id"),
           params={"m": json.dumps(limpios), "id": centro_id})
    pf.commit()
    return {"id": centro_id, "modulos_activos": limpios}


# ── Centinela: salud REAL de esta instalación — lógica en application/services/centinela_service.py
# (compartida con el tick programado de infrastructure/scheduler.py; este endpoint es el
# disparador manual, envoltorio fino).
@router.get("/centinela")
def centinela(request: Request, _su: CurrentUser = Depends(_SU), centro_id: int = Depends(get_current_centro),
              session: Session = Depends(get_session)) -> dict:
    from application.services.centinela_service import CentinelaService
    ip = request.client.host if request.client else None
    return CentinelaService(session).ejecutar(centro_id, origen="manual", usuario_id=_su.usuario_id, ip=ip)
