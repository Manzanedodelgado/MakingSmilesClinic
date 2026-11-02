"""DENTIA — análisis guiado de una radiografía en 4 pasos (Procesar · Patrones · Plan · Informe).

El estado (patrones marcados y plan por hallazgo) se guarda por (paciente, imagen de Multimedia).
La IA solo SUGIERE lo que sabe detectar (numeración FDI, dientes incluidos, canal dentario inferior,
seno maxilar); el resto de patrones los marca el doctor. Nada se guarda sin que el doctor lo confirme
en la pantalla, y el servicio de IA puede estar caído sin romper la ficha.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from api.auth_deps import CurrentUser, get_current_centro, require_permission
from api.paciente_helper import _get_paciente
from application.services.multimedia_service import MultimediaService
from domain.models.clinico import AnalisisDentia
from infrastructure.config.db import get_session
from infrastructure.ia_dental_client import IaDentalNoDisponible, analizar_ortopantomografia

router = APIRouter(prefix="/pacientes", tags=["dentia"])

# Categorías de patrón (las del panel «Patrones» de la pantalla) → grupo.
CATEGORIAS = {
    "linea_osea": "hueso", "linea_periodontal": "hueso", "l_osea_periodontal": "hueso",
    "senos_maxilares": "estructuras", "nervios_mandibulares": "estructuras", "atm": "estructuras",
    "radiolucencia": "lesion", "radiolucidez_periapical": "lesion",
    "ausencia": "pieza", "restos_radiculares": "pieza", "incluido_impactado": "pieza",
    "pontico": "restauracion", "corona": "restauracion", "implante": "restauracion",
    "obturacion": "restauracion", "endodoncia": "restauracion",
    "sano": "sano", "parte_diente": "sano", "pieza": "dientes",
}
MAX_PATRONES, MAX_PLAN, MAX_PUNTOS = 600, 200, 400
# Clase del servicio ia-dental → categoría de patrón.
_IA_A_CATEGORIA = {"impactado": "incluido_impactado", "canal_dentario_inferior": "nervios_mandibulares",
                   "seno_maxilar": "senos_maxilares"}


class Patron(BaseModel):
    id: str = Field(max_length=40)
    categoria: str
    origen: str = "doctor"                      # doctor | ia
    pieza: Optional[str] = Field(default=None, max_length=10)
    puntos: list[list[float]] = Field(default_factory=list)      # polígono/línea en px de la imagen
    confianza: Optional[float] = None
    nota: Optional[str] = Field(default=None, max_length=300)


class LineaPlan(BaseModel):
    patron_id: Optional[str] = Field(default=None, max_length=40)
    tratamiento_id: int
    tratamiento: str = Field(max_length=200)
    codigo: Optional[str] = Field(default=None, max_length=40)
    pieza: Optional[str] = Field(default=None, max_length=10)
    precio: float = Field(ge=0, le=1_000_000)
    cantidad: int = Field(default=1, ge=1, le=100)
    descuento: float = Field(default=0, ge=0)
    descuento_pct: bool = False
    nota: Optional[str] = Field(default=None, max_length=300)


class AnalisisIn(BaseModel):
    file_id: str = Field(min_length=1, max_length=500)
    paso: int = Field(default=1, ge=1, le=4)
    patrones: list[Patron] = Field(default_factory=list)
    plan: list[LineaPlan] = Field(default_factory=list)


def _validar(datos: AnalisisIn) -> None:
    if len(datos.patrones) > MAX_PATRONES or len(datos.plan) > MAX_PLAN:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Demasiados patrones o líneas de plan")
    for p in datos.patrones:
        if p.categoria not in CATEGORIAS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Categoría desconocida: {p.categoria}")
        if p.origen not in ("doctor", "ia"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Origen no válido")
        if len(p.puntos) > MAX_PUNTOS or any(len(pt) != 2 for pt in p.puntos):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Geometría no válida")


def _salida(a: Optional[AnalisisDentia], file_id: str) -> dict[str, Any]:
    return {"file_id": file_id, "existe": a is not None, "paso": a.paso if a else 1,
            "patrones": a.patrones_json if a else [], "plan": a.plan_json if a else [],
            "categorias": CATEGORIAS}


def _existente(session: Session, paciente_id: int, file_id: str) -> Optional[AnalisisDentia]:
    return session.exec(select(AnalisisDentia).where(
        AnalisisDentia.paciente_id == paciente_id, AnalisisDentia.file_id == file_id)).first()


@router.get("/{paciente_id}/dentia")
def obtener(paciente_id: int, file_id: str = Query(min_length=1, max_length=500),
            centro_id: int = Depends(get_current_centro),
            _u: CurrentUser = Depends(require_permission("pacientes.ver")),
            session: Session = Depends(get_session)) -> dict:
    _get_paciente(session, centro_id, paciente_id)                    # anti-IDOR: paciente ∈ centro
    return _salida(_existente(session, paciente_id, file_id), file_id)


@router.put("/{paciente_id}/dentia")
def guardar(paciente_id: int, datos: AnalisisIn,
            centro_id: int = Depends(get_current_centro),
            _u: CurrentUser = Depends(require_permission("pacientes.editar")),
            session: Session = Depends(get_session)) -> dict:
    p = _get_paciente(session, centro_id, paciente_id)
    _validar(datos)
    if not MultimediaService(session).media(centro_id, p, datos.file_id, True):   # la imagen es de este paciente
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Imagen no encontrada")
    a = _existente(session, paciente_id, datos.file_id) or AnalisisDentia(
        paciente_id=paciente_id, file_id=datos.file_id)
    a.paso = datos.paso
    a.patrones_json = [x.model_dump() for x in datos.patrones]
    a.plan_json = [x.model_dump() for x in datos.plan]
    session.add(a)
    session.commit()
    session.refresh(a)
    return _salida(a, datos.file_id)


class DetectarIn(BaseModel):
    file_id: str = Field(min_length=1, max_length=500)


@router.post("/{paciente_id}/dentia/detectar")
def detectar(paciente_id: int, datos: DetectarIn,
             centro_id: int = Depends(get_current_centro),
             _u: CurrentUser = Depends(require_permission("pacientes.editar")),
             session: Session = Depends(get_session)) -> dict:
    """Pide sugerencias a la IA y las devuelve como patrones (origen «ia») SIN guardarlas: la
    pantalla las muestra, el doctor las acepta/descarta y guarda con PUT. Reemplaza solo las
    sugerencias de IA anteriores, nunca lo que marcó el doctor."""
    p = _get_paciente(session, centro_id, paciente_id)
    res = MultimediaService(session).media(centro_id, p, datos.file_id, False)
    if not res:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Imagen no encontrada")
    try:
        ia = analizar_ortopantomografia(res[0])
    except IaDentalNoDisponible as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    patrones: list[dict] = []
    for e in ia.get("estructuras", []):
        cat = _IA_A_CATEGORIA.get(e.get("clase"))
        if not cat:
            continue
        for i, cont in enumerate(e.get("contornos") or []):
            patrones.append({"id": f"ia-{cat}-{len(patrones)}", "categoria": cat, "origen": "ia",
                             "pieza": e.get("fdi"), "puntos": [[float(x), float(y)] for x, y in cont][:MAX_PUNTOS],
                             "confianza": e.get("conf"), "nota": None})
    dientes = [{"fdi": d["fdi"], "conf": d["conf"], "bbox": d["bbox"]} for d in ia.get("dientes", [])]
    return {"ancho": ia.get("ancho"), "alto": ia.get("alto"), "patrones": patrones, "dientes": dientes,
            "aviso": ia.get("aviso"), "errores": ia.get("errores", [])}
