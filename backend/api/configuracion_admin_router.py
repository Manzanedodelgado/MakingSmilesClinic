"""Configuración · ADMIN · Tablas — explorador de la BD (todas las tablas reales).

Lista todas las tablas del esquema public (menos backups/internas). Las que tienen
`centro_id` se leen/editan acotadas a ESTE centro (C2/C3 en AUDITORIA-CODIGO.md: antes
volcaban TODOS los centros). Las que no tienen `centro_id` (identidad global, catálogos,
tablas "línea" sin FK directa a centro) se sirven sin ese filtro — no hay columna que
filtrar; mismo comportamiento que antes de C2/C3 para esa clase de tabla.
Columnas PII/credenciales (`_COLUMNAS_OCULTAS_POR_TABLA`) se ocultan siempre, tenga o no
centro_id la tabla. Protegido por permiso config.editar y auditado (contiene PII).
"""
import csv
import io
from collections import defaultdict
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete, text
from sqlmodel import Session, select

from api.auth_deps import CurrentUser, get_current_centro, require_permission
from api.tablas_ocultas import _COLUMNAS_OCULTAS_POR_TABLA, _es_oculta
from application.services.auth_service import AuthService
from application.services.config_service import ConfigService
from domain.models.core import Tratamiento
from domain.models.economico import PresupuestoPredisenado, PresupuestoPredisenadoLinea
from infrastructure.config.db import get_session

router = APIRouter(prefix="/configuracion/admin", tags=["configuración · admin"])


def _tablas_validas(session: Session) -> list[str]:
    rows = session.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    )).all()
    return [r[0] for r in rows]


def _tiene_centro_id(session: Session, nombre: str) -> bool:
    return session.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t AND column_name='centro_id'"
    ), {"t": nombre}).first() is not None


def _tablas_navegables(session: Session) -> list[str]:
    """Todas las tablas reales (no backup/interna). El filtro por centro_id se aplica
    tabla a tabla en cada endpoint, no aquí — depende de si la tabla tiene esa columna."""
    return [n for n in _tablas_validas(session) if not _es_oculta(n)]


def _check_tabla(session: Session, nombre: str) -> None:
    if nombre not in _tablas_navegables(session):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tabla no encontrada")


def _tipos(session: Session, nombre: str) -> dict[str, str]:
    """{columna: tipo usable en CAST} (udt_name para enums/arrays). Excluye columnas ocultas."""
    ocultas = _COLUMNAS_OCULTAS_POR_TABLA.get(nombre, set())
    rows = session.execute(text(
        "SELECT column_name, data_type, udt_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t"
    ), {"t": nombre}).all()
    return {r[0]: (r[2] if r[1] in ("USER-DEFINED", "ARRAY") else r[1]) for r in rows if r[0] not in ocultas}


def _pk(session: Session, nombre: str) -> list[str]:
    rows = session.execute(text(
        "SELECT a.attname FROM pg_index i "
        "JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum = ANY(i.indkey) "
        "WHERE i.indrelid = (quote_ident(:t))::regclass AND i.indisprimary"
    ), {"t": nombre}).all()
    return [r[0] for r in rows]


@router.get("/tablas")
def listar_tablas(
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("config.editar")),
    session: Session = Depends(get_session),
) -> dict:
    nombres = _tablas_navegables(session)
    if not nombres:
        return {"tablas": []}
    # C2: si la tabla tiene centro_id, cuenta solo ESTE centro; si no, cuenta global (no hay columna que filtrar).
    partes = [
        f'SELECT \'{n}\' AS tabla, count(*)::bigint AS filas FROM "{n}" WHERE centro_id = :centro_id'
        if _tiene_centro_id(session, n) else
        f'SELECT \'{n}\' AS tabla, count(*)::bigint AS filas FROM "{n}"'
        for n in nombres
    ]
    filas = session.execute(text(" UNION ALL ".join(partes)), {"centro_id": centro_id}).mappings().all()
    conteo = {r["tabla"]: int(r["filas"]) for r in filas}
    return {"tablas": [{"nombre": n, "filas": conteo.get(n, 0)} for n in nombres]}


@router.get("/tabla/{nombre}")
def ver_tabla(
    nombre: str,
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("config.editar")),
    session: Session = Depends(get_session),
) -> dict:
    _check_tabla(session, nombre)
    ocultas = _COLUMNAS_OCULTAS_POR_TABLA.get(nombre, set())
    columnas = [
        c for c in session.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=:t ORDER BY ordinal_position"
        ), {"t": nombre}).all()
        if c[0] not in ocultas
    ]
    cols_sql = ", ".join(f'"{c[0]}"' for c in columnas)
    scoped = _tiene_centro_id(session, nombre)
    where_sql = "WHERE centro_id = :centro_id " if scoped else ""
    params: dict[str, Any] = {"centro_id": centro_id, "l": limit, "o": offset} if scoped else {"l": limit, "o": offset}
    total = session.execute(
        text(f'SELECT count(*) FROM "{nombre}" {where_sql}'), params
    ).scalar() or 0
    datos = session.execute(
        text(f'SELECT {cols_sql} FROM "{nombre}" {where_sql}LIMIT :l OFFSET :o'), params
    ).mappings().all()
    rows: list[dict[str, Any]] = [dict(r) for r in datos]
    AuthService(session).audit("admin.tabla.ver", usuario_id=user.usuario_id, centro_id=centro_id,
                               recurso=nombre, ip=request.client.host if request.client else None)
    return {
        "nombre": nombre, "pk": _pk(session, nombre),
        "columnas": [{"nombre": c[0], "tipo": c[1]} for c in columnas],
        "filas": rows, "total": int(total), "limit": limit, "offset": offset,
    }


# ───────────────────────── EXPORTAR CSV ─────────────────────────
@router.get("/tabla/{nombre}/export")
def export_tabla(
    nombre: str, request: Request,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("config.editar")),
    session: Session = Depends(get_session),
):
    _check_tabla(session, nombre)
    ocultas = _COLUMNAS_OCULTAS_POR_TABLA.get(nombre, set())
    cols = [c[0] for c in session.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='public' "
        "AND table_name=:t ORDER BY ordinal_position"), {"t": nombre}).all() if c[0] not in ocultas]
    cols_sql = ", ".join(f'"{c}"' for c in cols)
    scoped = _tiene_centro_id(session, nombre)
    where_sql = "WHERE centro_id = :centro_id" if scoped else ""

    def filas():
        buf = io.StringIO(); w = csv.writer(buf)
        w.writerow(cols); yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        result = session.execute(
            text(f'SELECT {cols_sql} FROM "{nombre}" {where_sql}'),
            {"centro_id": centro_id} if scoped else {},
        )
        for r in result.mappings():
            w.writerow(["" if r[c] is None else r[c] for c in cols])
            yield buf.getvalue(); buf.seek(0); buf.truncate(0)

    AuthService(session).audit("admin.tabla.export", usuario_id=user.usuario_id, centro_id=centro_id,
                               recurso=nombre, ip=request.client.host if request.client else None)
    return StreamingResponse(filas(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{nombre}.csv"'})


# ───────────────────────── EDITAR FILA ─────────────────────────
class FilaIn(BaseModel):
    pk_valor: Any
    cambios: dict[str, Any]


@router.put("/tabla/{nombre}/fila")
def editar_fila(
    nombre: str, data: FilaIn, request: Request,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("config.editar")),
    session: Session = Depends(get_session),
) -> dict:
    _check_tabla(session, nombre)
    pks = _pk(session, nombre)
    if len(pks) != 1:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tabla sin clave primaria simple: edición no soportada")
    pk = pks[0]
    if pk == "centro_id":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tabla no editable desde aquí")
    tipos = _tipos(session, nombre)  # ya excluye columnas ocultas (PII/credenciales)
    if not data.cambios:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Sin cambios")
    scoped = _tiene_centro_id(session, nombre)
    if scoped and "centro_id" in data.cambios:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No se puede reasignar centro_id (moveria la fila a otro centro)")
    for c in data.cambios:
        if c not in tipos:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Columna inexistente o no editable: {c}")
    where_sql = 'WHERE "{pk}" = CAST(:pkv AS {t})'.format(pk=pk, t=tipos[pk])
    if scoped:
        where_sql += " AND centro_id = :centro_id"
        # C3: la fila debe pertenecer a ESTE centro — verificado antes Y forzado en el WHERE del UPDATE.
        actual = session.execute(
            text(f'SELECT 1 FROM "{nombre}" {where_sql}'), {"pkv": data.pk_valor, "centro_id": centro_id},
        ).first()
        if actual is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Fila no encontrada")
    sets = ", ".join(f'"{c}" = CAST(:v_{i} AS {tipos[c]})' for i, c in enumerate(data.cambios))
    params: dict[str, Any] = {f"v_{i}": (None if v == "" else v) for i, v in enumerate(data.cambios.values())}
    params["pkv"] = data.pk_valor
    if scoped:
        params["centro_id"] = centro_id
    sql = f'UPDATE "{nombre}" SET {sets} {where_sql}'
    try:
        res = session.execute(text(sql), params); session.commit()
    except Exception as exc:  # raiz: explorador de BD: SQL invalido/tabla ausente -> rollback + error controlado
        session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"No se pudo actualizar: {str(exc).splitlines()[0]}")
    AuthService(session).audit("admin.tabla.editar", usuario_id=user.usuario_id, centro_id=centro_id,
                               recurso=f"{nombre}#{data.pk_valor}", detalle=data.cambios,
                               ip=request.client.host if request.client else None)
    return {"actualizadas": res.rowcount}


# ───────────────────────── IMPORTAR CSV ─────────────────────────
@router.post("/tabla/{nombre}/import")
async def import_csv(
    nombre: str, request: Request, file: UploadFile = File(...),
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("config.editar")),
    session: Session = Depends(get_session),
) -> dict:
    _check_tabla(session, nombre)
    tipos = _tipos(session, nombre)  # ya excluye columnas ocultas
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "CSV vacío o sin cabecera")
    scoped = _tiene_centro_id(session, nombre)
    cols = [c.strip() for c in reader.fieldnames if not (scoped and c.strip() == "centro_id")]  # C3: si es multi-tenant, centro_id se fuerza, no se importa
    desconocidas = [c for c in cols if c not in tipos]
    if desconocidas:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Columnas no existen en la tabla: {', '.join(desconocidas)}")
    # created_at/updated_at: si la tabla los tiene y no vienen en el CSV → valor por defecto en Python
    extras = [c for c in ("created_at", "updated_at") if c in tipos and c not in cols]
    collist_cols = cols + extras + (["centro_id"] if scoped else [])
    collist = ", ".join(f'"{c}"' for c in collist_cols)
    vallist = ", ".join([f'CAST(:{c} AS {tipos[c]})' for c in cols] + ["now()" for _ in extras] + ([":centro_id"] if scoped else []))
    sql = text(f'INSERT INTO "{nombre}" ({collist}) VALUES ({vallist})')
    insertadas = 0
    try:
        for i, row in enumerate(reader):
            if i >= 5000:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Máximo 5000 filas por importación")
            params = {c: (None if (row.get(c) or "") == "" else row.get(c)) for c in cols}
            if scoped:
                params["centro_id"] = centro_id
            session.execute(sql, params); insertadas += 1
        session.commit()
    except HTTPException:
        session.rollback(); raise
    except Exception as exc:  # raiz: operacion admin: error revierte la transaccion y se informa; nunca deja la BD a medias
        session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Fila {insertadas + 1}: {str(exc).splitlines()[0]}")
    AuthService(session).audit("admin.tabla.import", usuario_id=user.usuario_id, centro_id=centro_id,
                               recurso=nombre, detalle={"filas": insertadas},
                               ip=request.client.host if request.client else None)
    return {"insertadas": insertadas}


# ───────────────────────── PRESUPUESTOS PREDISEÑADOS (plantillas · Config → Presupuestos) ─────
# CRUD de administración de las plantillas (título + líneas de catálogo). Distinto del
# endpoint de solo-lectura en presupuestos_router.py (GET /pacientes/{id}/presupuestos-predisenados),
# que sirve solo las ACTIVAS con precio ya resuelto por la tarifa de un paciente concreto,
# para "Cargar plantilla" en el editor. Aquí se gestiona el catálogo en sí.
class PredLineaIn(BaseModel):
    tratamiento_id: int
    pieza: Optional[str] = None
    zona_boca: Optional[str] = None
    precio: Optional[float] = None
    cantidad: int = 1
    descuento: Optional[float] = 0
    descuento_pct: bool = False
    orden: int = 0


class PredisenadoIn(BaseModel):
    titulo: str
    categoria: Optional[str] = None
    notas: Optional[str] = None
    activo: bool = True
    lineas: list[PredLineaIn] = []


def _predisenado_out(p: PresupuestoPredisenado, lineas: list[PresupuestoPredisenadoLinea],
                     trats: dict[int, Tratamiento]) -> dict:
    return {
        "id": p.id, "titulo": p.titulo, "categoria": p.categoria, "notas": p.notas, "activo": p.activo,
        "lineas": [{
            "tratamiento_id": l.tratamiento_id,
            "nombre": t.nombre if (t := trats.get(l.tratamiento_id)) else (l.nombre or ""),
            "codigo": t.codigo if (t := trats.get(l.tratamiento_id)) else None,
            "tipo_actuacion": t.tipo_actuacion if (t := trats.get(l.tratamiento_id)) else None,
            "es_mensualidad": bool(t.es_mensualidad) if (t := trats.get(l.tratamiento_id)) else False,
            "pieza": l.pieza, "zona_boca": l.zona_boca,
            "precio": float(l.precio) if l.precio is not None else None,
            "cantidad": l.cantidad, "descuento": float(l.descuento) if l.descuento is not None else 0,
            "descuento_pct": l.descuento_pct, "orden": l.orden,
        } for l in sorted(lineas, key=lambda x: x.orden)],
    }


@router.get("/predisenados-tratamientos")
def buscar_tratamientos_predisenados(
    q: str = Query(..., min_length=2),
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("config.editar")),
    session: Session = Depends(get_session),
) -> dict:
    """Typeahead de catálogo para añadir líneas a una plantilla (sin precio: aquí no hay paciente)."""
    like = f"%{q}%"
    trats = session.exec(
        select(Tratamiento).where(
            Tratamiento.activo == True,  # noqa: E712
            (Tratamiento.nombre.ilike(like)) | (Tratamiento.codigo.ilike(f"{q}%")),
        ).order_by(Tratamiento.nombre).limit(20)
    ).all()
    return {"tratamientos": [{
        "id": t.id, "codigo": t.codigo, "nombre": t.nombre,
        "tipo_actuacion": t.tipo_actuacion, "es_mensualidad": t.es_mensualidad,
    } for t in trats]}


@router.get("/presupuestos-predisenados")
def listar_predisenados(
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("config.editar")),
    session: Session = Depends(get_session),
) -> dict:
    plantillas = session.exec(select(PresupuestoPredisenado).where(
        PresupuestoPredisenado.centro_id == centro_id,
    ).order_by(PresupuestoPredisenado.categoria, PresupuestoPredisenado.titulo)).all()
    pids = [p.id for p in plantillas]
    lineas = session.exec(select(PresupuestoPredisenadoLinea).where(
        PresupuestoPredisenadoLinea.predisenado_id.in_(pids))).all() if pids else []
    tids = {l.tratamiento_id for l in lineas}
    trats = {t.id: t for t in session.exec(select(Tratamiento).where(Tratamiento.id.in_(tids))).all()} if tids else {}
    por_pre: dict[int, list[PresupuestoPredisenadoLinea]] = defaultdict(list)
    for l in lineas:
        por_pre[l.predisenado_id].append(l)
    categorias = sorted({p.categoria for p in plantillas if p.categoria})
    return {
        "categorias": categorias,
        "predisenados": [_predisenado_out(p, por_pre.get(p.id, []), trats) for p in plantillas],
    }


def _set_lineas(session: Session, predisenado_id: int, lineas: list[PredLineaIn]) -> None:
    session.execute(sa_delete(PresupuestoPredisenadoLinea)
                    .where(PresupuestoPredisenadoLinea.predisenado_id == predisenado_id))
    for i, l in enumerate(lineas):
        session.add(PresupuestoPredisenadoLinea(
            predisenado_id=predisenado_id, tratamiento_id=l.tratamiento_id, pieza=l.pieza,
            zona_boca=l.zona_boca, precio=l.precio, cantidad=l.cantidad or 1,
            descuento=l.descuento, descuento_pct=l.descuento_pct, orden=l.orden or i,
        ))


@router.post("/presupuestos-predisenados", status_code=201)
def crear_predisenado(
    data: PredisenadoIn, request: Request,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("config.editar")),
    session: Session = Depends(get_session),
) -> dict:
    if not data.titulo.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El título es obligatorio")
    p = PresupuestoPredisenado(centro_id=centro_id, titulo=data.titulo.strip(),
                               categoria=data.categoria or None, notas=data.notas, activo=data.activo)
    session.add(p)
    session.flush()
    _set_lineas(session, p.id, data.lineas)
    session.commit()
    AuthService(session).audit("admin.predisenado.crear", usuario_id=user.usuario_id, centro_id=centro_id,
                               recurso=f"presupuestos_predisenados#{p.id}", detalle={"titulo": p.titulo},
                               ip=request.client.host if request.client else None)
    return {"id": p.id}


@router.put("/presupuestos-predisenados/{pid}")
def editar_predisenado(
    pid: int, data: PredisenadoIn, request: Request,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("config.editar")),
    session: Session = Depends(get_session),
) -> dict:
    if not data.titulo.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El título es obligatorio")
    p = session.get(PresupuestoPredisenado, pid)
    if not p or p.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plantilla no encontrada")
    p.titulo = data.titulo.strip()
    p.categoria = data.categoria or None
    p.notas = data.notas
    p.activo = data.activo
    session.add(p)
    _set_lineas(session, pid, data.lineas)
    session.commit()
    AuthService(session).audit("admin.predisenado.editar", usuario_id=user.usuario_id, centro_id=centro_id,
                               recurso=f"presupuestos_predisenados#{pid}", detalle={"titulo": p.titulo},
                               ip=request.client.host if request.client else None)
    return {"id": pid}


@router.delete("/presupuestos-predisenados/{pid}", status_code=204)
def borrar_predisenado(
    pid: int, request: Request,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("config.editar")),
    session: Session = Depends(get_session),
) -> None:
    p = session.get(PresupuestoPredisenado, pid)
    if not p or p.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plantilla no encontrada")
    session.execute(sa_delete(PresupuestoPredisenadoLinea).where(PresupuestoPredisenadoLinea.predisenado_id == pid))
    session.delete(p)
    session.commit()
    AuthService(session).audit("admin.predisenado.borrar", usuario_id=user.usuario_id, centro_id=centro_id,
                               recurso=f"presupuestos_predisenados#{pid}",
                               ip=request.client.host if request.client else None)


# ───────────────────────── DOCUMENTOS (plantillas) ─────────────────────────
class DocsIn(BaseModel):
    plantillas: dict[str, Any]


@router.get("/documentos")
def get_documentos(
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("config.editar")),
    session: Session = Depends(get_session),
) -> dict:
    """Plantillas de documentos (viven en el cerebro: configuraciones · documentos.plantillas)."""
    val = ConfigService(session).resolve("documentos.plantillas", centro_id=centro_id, default={})
    return {"plantillas": val or {}}


@router.put("/documentos")
def set_documentos(
    data: DocsIn, request: Request,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("config.editar")),
    session: Session = Depends(get_session),
) -> dict:
    ConfigService(session).set("documentos.plantillas", data.plantillas, centro_id=centro_id)
    AuthService(session).audit("admin.documentos.guardar", usuario_id=user.usuario_id, centro_id=centro_id,
                               recurso="documentos.plantillas", detalle={"tipos": len(data.plantillas)},
                               ip=request.client.host if request.client else None)
    return {"ok": True}
