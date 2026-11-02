"""Informes — editor de informes / tabla dinámica moderna sobre la BD.

El cliente arma la consulta eligiendo del CATÁLOGO (informes_catalogo): entidad,
columnas, filtros, orden. El motor traduce esa definición a SQL parametrizado:
  - tablas, columnas y expresiones SOLO salen del catálogo del servidor (allowlist);
  - los valores van como parámetros vinculados (:f0, :f1…);
  - operadores y unidades están en listas blancas.
→ imposible inyectar SQL. Scoping multi-tenant fijo por centro. Protegido por permiso
`informes.ver` (ejecutar/leer) e `informes.editar` (guardar/borrar). Acceso a PII auditado.
"""
import csv
import io
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session, select

from api.auth_deps import CurrentUser, get_current_centro, require_permission
from api.informes_catalogo import ENTIDADES, OPERADOR_META, OPERADORES
from api.informes_join import plan_joins
from api.tablas_ocultas import _es_oculta, _COLUMNAS_OCULTAS_POR_TABLA
from application.services.auth_service import AuthService
from domain.models.informes import Informe
from infrastructure.config.db import get_session

router = APIRouter(prefix="/informes", tags=["informes"])

LIMITE_DEF = 500
LIMITE_MAX = 5000
_UNIDADES = {"dias": "days", "meses": "months", "anios": "years"}
_CMP = {"=", "!=", ">", ">=", "<", "<="}
_AGGS = {"count": None, "sum": "SUM", "avg": "AVG", "min": "MIN", "max": "MAX"}
_AGG_LABEL = {"count": "Recuento", "sum": "Σ", "avg": "Media", "min": "Mín", "max": "Máx"}


# ───────────────────────────── motor (SQL seguro) ─────────────────────────────
def _entidad(key: str) -> dict:
    ent = ENTIDADES.get(key)
    if not ent:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Entidad desconocida: {key}")
    return ent


def _tablas_reales(session: Session) -> list[str]:
    rows = session.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    )).all()
    return [r[0] for r in rows if not _es_oculta(r[0])]


def _tipo_de(data_type: str) -> str:
    d = data_type.lower()
    if "bool" in d:
        return "bool"
    if any(x in d for x in ("int", "numeric", "double", "real", "decimal", "money")):
        return "numero"
    if d == "date" or "timestamp" in d:
        return "fecha"
    return "texto"


def _tabla_ent(session: Session, nombre: str) -> dict:
    """Construye una 'entidad' al vuelo desde una tabla real (columnas introspectadas).
    Identificadores citados, validados contra information_schema → seguro como el motor.
    C6: Filtra columnas sensibles (password_hash, email, config, etc.)"""
    if nombre not in set(_tablas_reales(session)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tabla no encontrada")
    filas = session.execute(text(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t ORDER BY ordinal_position"
    ), {"t": nombre}).all()
    campos, cols = {}, []
    ocultas = _COLUMNAS_OCULTAS_POR_TABLA.get(nombre, set())
    for col, dt in filas:
        if col in ocultas:
            continue  # C6: no exponer password_hash, config, email, etc.
        tipo = _tipo_de(dt)
        crudo = tipo in ("numero", "fecha", "bool") or dt in ("text", "character varying", "character")
        campos[col] = {"label": col, "tipo": tipo, "sql": f'"{col}"' if crudo else f'"{col}"::text'}
        cols.append(col)
    por_def = [c for c in cols if c not in ("created_at", "updated_at")][:6] or cols[:6]
    return {
        "label": nombre,
        "base": f'"{nombre}"',
        "where_base": '"centro_id" = :centro_id' if "centro_id" in campos else "TRUE",
        "joins": {},
        "campos": campos,
        "orden_def": f'"{cols[0]}"' if cols else "1",
        "por_defecto": por_def,
    }


def _resolver(session: Session, entidad: Optional[str], tabla: Optional[str]) -> dict:
    """Origen del informe: tabla cruda (introspección) o entidad curada del catálogo."""
    if tabla:
        return _tabla_ent(session, tabla)
    if entidad:
        return _entidad(entidad)
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indica una entidad o una tabla")


def _valida_origen(session: Session, definicion: dict, entidad: str) -> None:
    """Valida que el origen guardado exista (tabla real o entidad del catálogo)."""
    sel = (definicion or {}).get("sel") or {}
    if sel.get("tipo") == "multi":
        return   # multi-tabla: se valida al ejecutar (columnas de tablas reales)
    if sel.get("tipo") == "tab":
        _tabla_ent(session, sel.get("key") or entidad)
    else:
        _entidad(sel.get("key") or entidad)


# ───────────────────────── motor MULTI-TABLA (joins por FK) ─────────────────────────
def _cols_de_tablas(session: Session, tablas: set) -> dict:
    """{tabla: {col: {tipo, sql (cualificado)}}} introspectado; valida tablas reales.
    C6: Filtra columnas sensibles por tabla."""
    reales = set(_tablas_reales(session))
    info: dict = {}
    for t in tablas:
        if t not in reales:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Tabla no encontrada: {t}")
        filas = session.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=:t"
        ), {"t": t}).all()
        info[t] = {}
        ocultas = _COLUMNAS_OCULTAS_POR_TABLA.get(t, set())
        for col, dt in filas:
            if col in ocultas:
                continue  # C6: no exponer password_hash, config, email, etc.
            tipo = _tipo_de(dt)
            crudo = tipo in ("numero", "fecha", "bool") or dt in ("text", "character varying", "character")
            info[t][col] = {"tipo": tipo, "sql": f'"{t}"."{col}"' if crudo else f'"{t}"."{col}"::text'}
    return info


def _construir_multi(session: Session, columnas: list, filtros: list, orden: list, limite, centro_id: int):
    if not columnas:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Añade al menos una columna")
    needed = {c["tabla"] for c in columnas} | {f["tabla"] for f in (filtros or [])} | {o["tabla"] for o in (orden or [])}
    counts: dict = {}
    for c in columnas:
        counts[c["tabla"]] = counts.get(c["tabla"], 0) + 1
    base, joins, participantes = plan_joins(session, needed, counts)
    info = _cols_de_tablas(session, participantes)

    def campo(t, c):
        if t not in info or c not in info[t]:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Columna desconocida: {t}.{c}")
        return info[t][c]

    select_parts, col_meta = [], []
    for c in columnas:
        meta = campo(c["tabla"], c["campo"])
        alias = f'{c["tabla"]}__{c["campo"]}'
        select_parts.append(f'{meta["sql"]} AS "{alias}"')
        col_meta.append({"key": alias, "label": f'{c["tabla"]}.{c["campo"]}', "tipo": meta["tipo"],
                         "tabla": c["tabla"], "campo": c["campo"]})

    from_sql = f'"{base}"' + "".join(f' LEFT JOIN "{t}" ON {on}' for t, on in joins)
    params: dict = {"centro_id": centro_id}
    where = [f'"{t}"."centro_id" = :centro_id' for t in participantes if "centro_id" in info.get(t, {})]
    for i, f in enumerate(filtros or []):
        meta = campo(f["tabla"], f["campo"])
        where.append(_predicado(meta["sql"], f.get("op"), meta["tipo"], f, params, i))
    where_sql = " AND ".join(where) if where else "TRUE"

    order_parts = []
    for o in (orden or []):
        meta = campo(o["tabla"], o["campo"])
        d = "DESC" if str(o.get("dir", "asc")).lower() == "desc" else "ASC"
        order_parts.append(f'{meta["sql"]} {d}')
    order_sql = ", ".join(order_parts) or "1"
    lim = max(1, min(int(limite or LIMITE_DEF), LIMITE_MAX))

    sql = f'SELECT {", ".join(select_parts)} FROM {from_sql} WHERE {where_sql} ORDER BY {order_sql} LIMIT {lim}'
    count_sql = f"SELECT COUNT(*) FROM {from_sql} WHERE {where_sql}"
    return sql, count_sql, params, col_meta, lim, {"base": base, "tablas": sorted(participantes)}


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Valor numérico inválido: {v!r}")


def _predicado(expr: str, op: str, tipo: str, f: dict, params: dict, i: int) -> str:
    """SQL de un filtro; rellena `params`. expr viene del catálogo (no del cliente)."""
    if op not in OPERADORES.get(tipo, []):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Operador '{op}' no válido para {tipo}")
    p, p2 = f"f{i}", f"f{i}b"
    v, v2 = f.get("valor"), f.get("valor2")

    if op == "vacio":
        return f"({expr} IS NULL OR {expr} = '')" if tipo == "texto" else f"{expr} IS NULL"
    if op == "no_vacio":
        return f"({expr} IS NOT NULL AND {expr} <> '')" if tipo == "texto" else f"{expr} IS NOT NULL"

    if tipo == "bool":
        return f"{expr} IS TRUE" if op == "es_si" else f"{expr} IS NOT TRUE"

    if tipo == "texto":
        if op == "contiene":    params[p] = f"%{v}%"; return f"{expr} ILIKE :{p}"
        if op == "no_contiene": params[p] = f"%{v}%"; return f"({expr} IS NULL OR {expr} NOT ILIKE :{p})"
        if op == "empieza":     params[p] = f"{v}%";  return f"{expr} ILIKE :{p}"
        if op == "igual":       params[p] = v;        return f"{expr} = :{p}"
        if op == "distinto":    params[p] = v;        return f"{expr} IS DISTINCT FROM :{p}"

    if tipo == "numero":
        if op == "entre":
            params[p], params[p2] = _num(v), _num(v2)
            return f"{expr} BETWEEN :{p} AND :{p2}"
        if op in _CMP:
            params[p] = _num(v)
            return f"{expr} {op} :{p}"

    if tipo == "fecha":
        if op == "antes_de":   params[p] = v; return f"{expr} < :{p}"
        if op == "despues_de": params[p] = v; return f"{expr} > :{p}"
        if op == "entre":      params[p], params[p2] = v, v2; return f"{expr} BETWEEN :{p} AND :{p2}"
        if op in ("hace_mas_de", "en_los_ultimos"):
            unidad = _UNIDADES.get(str(f.get("unidad") or "dias"))
            if not unidad:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unidad inválida (dias|meses|anios)")
            params[p] = int(_num(v))
            cmp = "<" if op == "hace_mas_de" else ">="
            return f"{expr} {cmp} (CURRENT_DATE - make_interval({unidad} => :{p}))"

    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Operador '{op}' no soportado")


def _existe_sql(ent: dict, rf: dict, params: dict, pi: int) -> tuple[str, int]:
    """Construye un [NOT] EXISTS correlacionado (filtro de relación) y avanza el contador."""
    rel = (ent.get("relaciones") or {}).get(rf.get("relacion"))
    if not rel or not ent.get("pk"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Relación desconocida: {rf.get('relacion')}")
    rcampos = rel["campos"]
    sjoins: set[str] = set()
    swhere = [f'{rel["fk"]} = {ent["pk"]}']
    for sf in (rf.get("subfiltros") or []):
        c = rcampos.get(sf.get("campo"))
        if not c:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Campo de relación desconocido: {sf.get('campo')}")
        if c.get("join"):
            sjoins.add(c["join"])
        swhere.append(_predicado(c["sql"], sf.get("op"), c["tipo"], sf, params, pi))
        pi += 1
    sjsql = " ".join(frag for j, frag in rel["joins"].items() if j in sjoins)
    base = f'{rel["base"]} {sjsql}'.strip()
    pref = "NOT " if rf.get("modo") == "no_tiene" else ""
    return f'{pref}EXISTS (SELECT 1 FROM {base} WHERE {" AND ".join(swhere)})', pi


def _construir(ent: dict, columnas: list, filtros: list, orden: list, limite, relaciones=None):
    """Devuelve (sql, count_sql, params, col_meta, limite_efectivo)."""
    campos = ent["campos"]
    cols = [c for c in (columnas or []) if c in campos] or list(ent["por_defecto"])
    joins: set[str] = set()
    select_parts, col_meta = [], []
    for k in cols:
        c = campos[k]
        if c.get("join"):
            joins.add(c["join"])
        select_parts.append(f'{c["sql"]} AS "{k}"')
        col_meta.append({"key": k, "label": c["label"], "tipo": c["tipo"]})

    params: dict[str, Any] = {}
    where = [ent["where_base"]]
    pi = 0
    for f in (filtros or []):
        c = campos.get(f.get("campo"))
        if not c:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Campo de filtro desconocido: {f.get('campo')}")
        if c.get("join"):
            joins.add(c["join"])
        where.append(_predicado(c["sql"], f.get("op"), c["tipo"], f, params, pi))
        pi += 1
    for rf in (relaciones or []):
        clause, pi = _existe_sql(ent, rf, params, pi)
        where.append(clause)

    order_parts = []
    for o in (orden or []):
        c = campos.get(o.get("campo"))
        if not c:
            continue
        if c.get("join"):
            joins.add(c["join"])
        d = "DESC" if str(o.get("dir", "asc")).lower() == "desc" else "ASC"
        order_parts.append(f'{c["sql"]} {d}')
    order_sql = ", ".join(order_parts) or ent["orden_def"]

    joins_sql = " ".join(frag for j, frag in ent["joins"].items() if j in joins)
    base_from = f'{ent["base"]} {joins_sql}'.strip()
    where_sql = " AND ".join(where)
    lim = max(1, min(int(limite or LIMITE_DEF), LIMITE_MAX))

    sql = f'SELECT {", ".join(select_parts)} FROM {base_from} WHERE {where_sql} ORDER BY {order_sql} LIMIT {lim}'
    count_sql = f"SELECT COUNT(*) FROM {base_from} WHERE {where_sql}"
    return sql, count_sql, params, col_meta, lim


def _ejecutar(ent: dict, q: "ConsultaIn", centro_id: int, session: Session):
    filtros = [f.model_dump() for f in q.filtros]
    orden = [o.model_dump() for o in q.orden]
    relaciones = [r.model_dump() for r in (q.relaciones or [])]
    sql, count_sql, params, col_meta, lim = _construir(ent, q.columnas, filtros, orden, q.limite, relaciones)
    params["centro_id"] = centro_id
    try:
        total = session.execute(text(count_sql), params).scalar() or 0
        rows = session.execute(text(sql), params).mappings().all()
    except HTTPException:
        raise
    except Exception as e:  # raiz: SQL inválido/BD caída al ejecutar el informe; 400 sin detalles de SQL  # noqa: BLE001
        session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"No se pudo ejecutar el informe ({type(e).__name__})")
    return col_meta, [dict(r) for r in rows], int(total), lim


def _num_o_none(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def _construir_pivot(ent: dict, filtros: list, filas: list, columna, medida: dict):
    """SQL agregado (GROUP BY) para la tabla dinámica. Devuelve (sql, params, dim_meta, col_campo, medida_label)."""
    campos = ent["campos"]
    fila_keys = [k for k in (filas or []) if k in campos]
    if not fila_keys:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Elige al menos un campo de fila")
    joins: set[str] = set()
    dim_select, dim_meta, group_exprs = [], [], []
    for idx, k in enumerate(fila_keys):
        c = campos[k]
        if c.get("join"):
            joins.add(c["join"])
        alias = f"d{idx}"
        dim_select.append(f'{c["sql"]} AS "{alias}"')
        group_exprs.append(c["sql"])
        dim_meta.append({"key": k, "label": c["label"], "tipo": c["tipo"], "alias": alias})

    col_campo = None
    if columna and columna in campos:
        c = campos[columna]
        if c.get("join"):
            joins.add(c["join"])
        dim_select.append(f'{c["sql"]} AS "__col"')
        group_exprs.append(c["sql"])
        col_campo = {"key": columna, "label": c["label"], "tipo": c["tipo"]}

    agg = (medida or {}).get("agg", "count")
    if agg not in _AGGS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Agregación inválida")
    if agg == "count":
        val_expr, medida_label, medida_tipo = "COUNT(*)", "Recuento", "numero"
    else:
        mc = campos.get((medida or {}).get("campo"))
        if not mc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Elige el campo de la medida")
        if agg in ("sum", "avg") and mc["tipo"] != "numero":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "La suma/media necesita un campo numérico")
        if mc.get("join"):
            joins.add(mc["join"])
        val_expr = f'{_AGGS[agg]}({mc["sql"]})'
        if agg == "sum":
            val_expr = f"COALESCE({val_expr}, 0)"
        medida_label = f'{_AGG_LABEL[agg]} {mc["label"]}'
        medida_tipo = "numero"

    params: dict[str, Any] = {}
    where = [ent["where_base"]]
    for i, f in enumerate(filtros or []):
        c = campos.get(f.get("campo"))
        if not c:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Campo de filtro desconocido: {f.get('campo')}")
        if c.get("join"):
            joins.add(c["join"])
        where.append(_predicado(c["sql"], f.get("op"), c["tipo"], f, params, i))

    joins_sql = " ".join(frag for j, frag in ent["joins"].items() if j in joins)
    base_from = f'{ent["base"]} {joins_sql}'.strip()
    sql = (f'SELECT {", ".join(dim_select)}, {val_expr} AS "__val" '
           f'FROM {base_from} WHERE {" AND ".join(where)} GROUP BY {", ".join(group_exprs)}')
    return sql, params, dim_meta, col_campo, medida_label, medida_tipo


def _ejecutar_pivot(ent, p: "PivoteIn", centro_id, session):
    filtros = [f.model_dump() for f in p.filtros]
    medida = p.medida.model_dump() if p.medida else {"agg": "count"}
    sql, params, dim_meta, col_campo, medida_label, medida_tipo = _construir_pivot(
        ent, filtros, p.filas, p.columna, medida)
    params["centro_id"] = centro_id
    try:
        rows = session.execute(text(sql), params).mappings().all()
    except HTTPException:
        raise
    except Exception as e:  # raiz: SQL de la tabla dinámica inválido/BD caída; 400 sin detalles de SQL  # noqa: BLE001
        session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"No se pudo ejecutar la tabla dinámica ({type(e).__name__})")

    fmt = lambda v: "(vacío)" if v is None or v == "" else str(v)
    if col_campo:
        # valores de columna distintos (ordenados) → cabeceras
        col_vals = sorted({r["__col"] for r in rows}, key=lambda x: (x is None, str(x)))
        agrupado: dict = {}
        for r in rows:
            key = tuple(r[d["alias"]] for d in dim_meta)
            agrupado.setdefault(key, {})[r["__col"]] = _num_o_none(r["__val"])
        filas_out = []
        for key, celdas in agrupado.items():
            fila = {d["key"]: key[i] for i, d in enumerate(dim_meta)}
            valores = {fmt(cv): celdas.get(cv) for cv in col_vals}
            nums = [v for v in celdas.values() if isinstance(v, (int, float))]
            fila["__celdas"] = valores
            fila["__total"] = sum(nums) if nums else None
            filas_out.append(fila)
        filas_out.sort(key=lambda f: tuple(str(f[d["key"]]) for d in dim_meta))
        columnas_out = [{"valor": fmt(cv), "label": fmt(cv)} for cv in col_vals]
    else:
        filas_out = []
        for r in rows:
            fila = {d["key"]: r[d["alias"]] for d in dim_meta}
            fila["__val"] = _num_o_none(r["__val"])
            filas_out.append(fila)
        filas_out.sort(key=lambda f: tuple(str(f[d["key"]]) for d in dim_meta))
        columnas_out = None

    return {"dimensiones": [{"key": d["key"], "label": d["label"]} for d in dim_meta],
            "columnas": columnas_out, "medida_label": medida_label, "medida_tipo": medida_tipo,
            "filas": filas_out, "n_filas": len(filas_out)}


# ───────────────────────────── esquemas ─────────────────────────────
class FiltroIn(BaseModel):
    campo: str
    op: str
    valor: Optional[Any] = None
    valor2: Optional[Any] = None
    unidad: Optional[str] = None


class OrdenIn(BaseModel):
    campo: str
    dir: str = "asc"


class RelacionIn(BaseModel):
    relacion: str                        # clave de la relación (citas, realizados, …)
    modo: str = "tiene"                  # tiene | no_tiene
    subfiltros: list[FiltroIn] = []


class ConsultaIn(BaseModel):
    entidad: Optional[str] = None
    tabla: Optional[str] = None          # tabla cruda (alternativa a entidad)
    columnas: list[str] = []
    filtros: list[FiltroIn] = []
    orden: list[OrdenIn] = []
    relaciones: list[RelacionIn] = []    # filtros TIENE / NO TIENE … que cumplen …
    limite: Optional[int] = None


class MedidaIn(BaseModel):
    agg: str = "count"               # count | sum | avg | min | max
    campo: Optional[str] = None      # requerido salvo en count


class PivoteIn(BaseModel):
    entidad: Optional[str] = None
    tabla: Optional[str] = None      # tabla cruda (alternativa a entidad)
    filas: list[str] = []            # dimensiones de fila (group by)
    columna: Optional[str] = None    # dimensión de columna (cruce); None = agrupado simple
    medida: Optional[MedidaIn] = None
    filtros: list[FiltroIn] = []


class MultiColIn(BaseModel):
    tabla: str
    campo: str


class MultiFiltroIn(BaseModel):
    tabla: str
    campo: str
    op: str
    valor: Optional[Any] = None
    valor2: Optional[Any] = None
    unidad: Optional[str] = None


class MultiOrdenIn(BaseModel):
    tabla: str
    campo: str
    dir: str = "asc"


class MultiConsultaIn(BaseModel):
    columnas: list[MultiColIn] = []
    filtros: list[MultiFiltroIn] = []
    orden: list[MultiOrdenIn] = []
    limite: Optional[int] = None


class GuardarIn(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    entidad: str
    definicion: dict = {}


# ───────────────────────────── catálogo ─────────────────────────────
@router.get("/entidades")
def listar_entidades(user: CurrentUser = Depends(require_permission("informes.ver"))) -> dict:
    entidades = [{
        "key": key,
        "label": ent["label"],
        "por_defecto": ent["por_defecto"],
        "campos": [{"key": k, "label": c["label"], "tipo": c["tipo"], "operadores": OPERADORES[c["tipo"]]}
                   for k, c in ent["campos"].items()],
        "relaciones": [{
            "key": rk,
            "label": rel["label"],
            "campos": [{"key": k, "label": c["label"], "tipo": c["tipo"], "operadores": OPERADORES[c["tipo"]]}
                       for k, c in rel["campos"].items()],
        } for rk, rel in (ent.get("relaciones") or {}).items()],
    } for key, ent in ENTIDADES.items()]
    return {"entidades": entidades, "operadores": OPERADOR_META}


@router.get("/tablas")
def listar_tablas(
    user: CurrentUser = Depends(require_permission("informes.ver")),
    session: Session = Depends(get_session),
) -> dict:
    """Todas las tablas reales (sin respaldos/internas) para elegir libremente."""
    return {"tablas": [{"nombre": n, "label": n} for n in _tablas_reales(session)]}


@router.get("/tabla/{nombre}/campos")
def campos_de_tabla(
    nombre: str,
    user: CurrentUser = Depends(require_permission("informes.ver")),
    session: Session = Depends(get_session),
) -> dict:
    ent = _tabla_ent(session, nombre)
    campos = [{"key": k, "label": c["label"], "tipo": c["tipo"], "operadores": OPERADORES[c["tipo"]]}
              for k, c in ent["campos"].items()]
    return {"campos": campos, "por_defecto": ent["por_defecto"]}


# ───────────────────────────── ejecutar / exportar ─────────────────────────────
@router.post("/ejecutar")
def ejecutar(
    q: ConsultaIn,
    request: Request,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("informes.ver")),
    session: Session = Depends(get_session),
) -> dict:
    ent = _resolver(session, q.entidad, q.tabla)
    col_meta, filas, total, lim = _ejecutar(ent, q, centro_id, session)
    AuthService(session).audit("informes.ejecutar", usuario_id=user.usuario_id, centro_id=centro_id,
                               recurso=q.tabla or q.entidad, ip=request.client.host if request.client else None)
    return {"columnas": col_meta, "filas": filas, "total": total, "limite": lim, "truncado": total > len(filas)}


@router.post("/exportar")
def exportar(
    q: ConsultaIn,
    request: Request,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("informes.ver")),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    ent = _resolver(session, q.entidad, q.tabla)
    q.limite = LIMITE_MAX
    col_meta, filas, _total, _lim = _ejecutar(ent, q, centro_id, session)
    AuthService(session).audit("informes.exportar", usuario_id=user.usuario_id, centro_id=centro_id,
                               recurso=q.tabla or q.entidad, ip=request.client.host if request.client else None)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([c["label"] for c in col_meta])
    for r in filas:
        w.writerow(["" if r[c["key"]] is None else r[c["key"]] for c in col_meta])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="informe_{q.tabla or q.entidad}.csv"'})


@router.post("/pivote")
def pivote(
    p: PivoteIn,
    request: Request,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("informes.ver")),
    session: Session = Depends(get_session),
) -> dict:
    ent = _resolver(session, p.entidad, p.tabla)
    out = _ejecutar_pivot(ent, p, centro_id, session)
    AuthService(session).audit("informes.pivote", usuario_id=user.usuario_id, centro_id=centro_id,
                               recurso=p.tabla or p.entidad, ip=request.client.host if request.client else None)
    return out


# ───────────────────────── multi-tabla (columnas de varias tablas, joins por FK) ─────────────────────────
def _ejecutar_multi(q: "MultiConsultaIn", centro_id: int, session: Session):
    cols = [c.model_dump() for c in q.columnas]
    filt = [f.model_dump() for f in q.filtros]
    ordn = [o.model_dump() for o in q.orden]
    sql, count_sql, params, col_meta, lim, plan = _construir_multi(session, cols, filt, ordn, q.limite, centro_id)
    try:
        total = session.execute(text(count_sql), params).scalar() or 0
        rows = session.execute(text(sql), params).mappings().all()
    except HTTPException:
        raise
    except Exception as e:  # raiz: SQL multi-tabla inválido/BD caída; 400 sin detalles de SQL  # noqa: BLE001
        session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"No se pudo ejecutar el informe ({type(e).__name__})")
    return col_meta, [dict(r) for r in rows], int(total), lim, plan


@router.post("/multi/ejecutar")
def multi_ejecutar(
    q: MultiConsultaIn,
    request: Request,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("informes.ver")),
    session: Session = Depends(get_session),
) -> dict:
    col_meta, filas, total, lim, plan = _ejecutar_multi(q, centro_id, session)
    AuthService(session).audit("informes.ejecutar", usuario_id=user.usuario_id, centro_id=centro_id,
                               recurso="+".join(plan["tablas"]), ip=request.client.host if request.client else None)
    return {"columnas": col_meta, "filas": filas, "total": total, "limite": lim,
            "truncado": total > len(filas), "plan": plan}


@router.post("/multi/exportar")
def multi_exportar(
    q: MultiConsultaIn,
    request: Request,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("informes.ver")),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    q.limite = LIMITE_MAX
    col_meta, filas, _total, _lim, plan = _ejecutar_multi(q, centro_id, session)
    AuthService(session).audit("informes.exportar", usuario_id=user.usuario_id, centro_id=centro_id,
                               recurso="+".join(plan["tablas"]), ip=request.client.host if request.client else None)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([c["label"] for c in col_meta])
    for r in filas:
        w.writerow(["" if r[c["key"]] is None else r[c["key"]] for c in col_meta])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="informe_multi.csv"'})


# ───────────────────────────── informes guardados (CRUD) ─────────────────────────────
@router.get("/guardados")
def listar_guardados(
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("informes.ver")),
    session: Session = Depends(get_session),
) -> list[dict]:
    rows = session.exec(select(Informe).where(Informe.centro_id == centro_id).order_by(Informe.nombre)).all()
    return [{"id": r.id, "nombre": r.nombre, "descripcion": r.descripcion, "entidad": r.entidad,
             "actualizado": r.updated_at.isoformat() if r.updated_at else None} for r in rows]


@router.get("/guardados/{informe_id}")
def obtener_guardado(
    informe_id: int,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("informes.ver")),
    session: Session = Depends(get_session),
) -> dict:
    inf = session.get(Informe, informe_id)
    if not inf or inf.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Informe no encontrado")
    return {"id": inf.id, "nombre": inf.nombre, "descripcion": inf.descripcion,
            "entidad": inf.entidad, "definicion": inf.definicion or {}}


@router.post("/guardados")
def crear_guardado(
    body: GuardarIn,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("informes.editar")),
    session: Session = Depends(get_session),
) -> dict:
    _valida_origen(session, body.definicion, body.entidad)
    if not body.nombre.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El informe necesita un nombre")
    inf = Informe(centro_id=centro_id, nombre=body.nombre.strip()[:160],
                  descripcion=(body.descripcion or None), entidad=body.entidad,
                  definicion=body.definicion, creado_por=user.usuario_id)
    session.add(inf)
    session.commit()
    session.refresh(inf)
    return {"id": inf.id}


@router.put("/guardados/{informe_id}")
def actualizar_guardado(
    informe_id: int,
    body: GuardarIn,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("informes.editar")),
    session: Session = Depends(get_session),
) -> dict:
    inf = session.get(Informe, informe_id)
    if not inf or inf.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Informe no encontrado")
    _valida_origen(session, body.definicion, body.entidad)
    inf.nombre = body.nombre.strip()[:160] or inf.nombre
    inf.descripcion = body.descripcion or None
    inf.entidad = body.entidad
    inf.definicion = body.definicion
    session.add(inf)
    session.commit()
    return {"id": inf.id}


@router.delete("/guardados/{informe_id}")
def borrar_guardado(
    informe_id: int,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("informes.editar")),
    session: Session = Depends(get_session),
) -> dict:
    inf = session.get(Informe, informe_id)
    if not inf or inf.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Informe no encontrado")
    session.delete(inf)
    session.commit()
    return {"ok": True}
