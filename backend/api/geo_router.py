"""Catálogo geográfico oficial (país → provincia → municipio → CP), fuente INE/ISO.
Ver migración 038 y domain/models/core.py (Pais/Provincia/Municipio/CodigoPostalGeo)
para el porqué de reemplazar `poblaciones`/`codigos_postales` (datos sucios legados)."""
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from api.auth_deps import CurrentUser, get_current_user
from domain.models.core import CodigoPostalGeo, Municipio, Pais, Provincia
from infrastructure.config.db import get_session

router = APIRouter(prefix="/geo", tags=["geo"])


@router.get("/paises")
def listar_paises(user: CurrentUser = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict]:
    paises = session.exec(select(Pais).order_by(Pais.nombre)).all()
    return [{"id": p.id, "iso2": p.iso2, "nombre": p.nombre} for p in paises]


@router.get("/provincias")
def listar_provincias(pais_id: int, user: CurrentUser = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict]:
    provs = session.exec(select(Provincia).where(Provincia.pais_id == pais_id).order_by(Provincia.nombre)).all()
    return [{"id": p.id, "nombre": p.nombre} for p in provs]


@router.get("/municipios")
def listar_municipios(provincia_id: int, q: str = "", user: CurrentUser = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict]:
    stmt = select(Municipio).where(Municipio.provincia_id == provincia_id)
    if q:
        stmt = stmt.where(Municipio.nombre.ilike(f"%{q}%"))
    muns = session.exec(stmt.order_by(Municipio.nombre)).all()
    return [{"id": m.id, "nombre": m.nombre} for m in muns]


@router.get("/cp")
def listar_cp_de_municipio(municipio_id: int, user: CurrentUser = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict]:
    cps = session.exec(select(CodigoPostalGeo).where(CodigoPostalGeo.municipio_id == municipio_id).order_by(CodigoPostalGeo.cp)).all()
    return [{"id": c.id, "cp": c.cp} for c in cps]


@router.get("/buscar-cp/{cp}")
def buscar_por_cp(cp: str, user: CurrentUser = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict]:
    """Dado un CP, resuelve municipio/provincia/país (puede haber más de un municipio por CP)."""
    filas = session.exec(
        select(CodigoPostalGeo, Municipio, Provincia, Pais)
        .join(Municipio, Municipio.id == CodigoPostalGeo.municipio_id)
        .join(Provincia, Provincia.id == Municipio.provincia_id)
        .join(Pais, Pais.id == Provincia.pais_id)
        .where(CodigoPostalGeo.cp == cp)
    ).all()
    return [
        {"pais_id": pa.id, "pais": pa.nombre, "provincia_id": pr.id, "provincia": pr.nombre, "municipio_id": m.id, "municipio": m.nombre}
        for (_, m, pr, pa) in filas
    ]
