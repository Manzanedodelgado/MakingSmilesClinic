"""CEFALOMETRÍA — trazado guiado sobre la telerradiografía lateral y cálculo del análisis.

El doctor coloca los landmarks (guiados por `/cefalometria/definicion`); el backend calcula las
medidas de Steiner con el motor de geometría (determinista) y guarda el trazado. Multi-tenant por
paciente (la imagen no lleva centro_id: se valida vía paciente).
"""
from __future__ import annotations

from typing import Optional

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import Session, select

from api.auth_deps import CurrentUser, get_current_centro, get_current_user
from api.paciente_helper import _get_paciente
from application.services.cefalometria_service import (
    ANALISIS, TIPOS_MEDIDA, analizar, analizar_definido,
)
from application.services.cefalometria_pdf import informe_pdf
from domain.models.clinico import AnalisisCefalo, Cefalometria, ImagenRx
from infrastructure.config.db import get_session

_MEDIA = Path(__file__).resolve().parent.parent / "media"

router = APIRouter(tags=["cefalometría"])


class DefinicionResp(BaseModel):
    analisis: str
    label: str
    landmarks: list[dict]
    normas: dict[str, dict]
    disponibles: list[dict]


class TrazadoIn(BaseModel):
    analisis: str = "steiner"
    landmarks: dict                       # {code: [x, y]} en píxeles de imagen
    calibracion: Optional[dict] = None    # {p1:[x,y], p2:[x,y], mm}


class TrazadoDTO(BaseModel):
    id: int
    imagen_id: int
    analisis: str
    landmarks: dict
    calibracion: Optional[dict]
    mediciones: dict
    interpretacion: dict
    calibrada: bool


def _get_imagen(session: Session, centro_id: int, imagen_id: int) -> ImagenRx:
    img = session.get(ImagenRx, imagen_id)
    if not img:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Imagen no encontrada")
    _get_paciente(session, centro_id, img.paciente_id)  # valida tenant
    return img


def _custom(session: Session, centro_id: int, slug: str) -> Optional[AnalisisCefalo]:
    return session.exec(select(AnalisisCefalo).where(
        AnalisisCefalo.centro_id == centro_id, AnalisisCefalo.slug == slug)).first()


def calcular(session: Session, centro_id: int, analisis: str, landmarks: dict,
             calibracion: Optional[dict]) -> Optional[dict]:
    """Calcula un análisis builtin (Steiner/Ricketts) o a medida del centro. None si no existe."""
    if analisis in ANALISIS:
        return analizar(analisis, landmarks, calibracion)
    cust = _custom(session, centro_id, analisis)
    if cust:
        return analizar_definido(cust.medidas_json or [], landmarks, calibracion)
    return None


def _disponibles(session: Session, centro_id: int) -> list[dict]:
    base = [{"analisis": k, "label": v["label"], "custom": False} for k, v in ANALISIS.items()]
    cust = session.exec(select(AnalisisCefalo).where(AnalisisCefalo.centro_id == centro_id)).all()
    return base + [{"analisis": c.slug, "label": c.nombre, "custom": True} for c in cust]


def _dto(session: Session, centro_id: int, c: Cefalometria) -> TrazadoDTO:
    calc = calcular(session, centro_id, c.analisis, c.landmarks_json or {}, c.calibracion_json) or {
        "mediciones": c.mediciones_json or {}, "interpretacion": {}, "calibrada": False}
    return TrazadoDTO(
        id=c.id, imagen_id=c.imagen_id, analisis=c.analisis,
        landmarks=c.landmarks_json or {}, calibracion=c.calibracion_json,
        mediciones=calc["mediciones"], interpretacion=calc["interpretacion"],
        calibrada=calc["calibrada"],
    )


@router.get("/cefalometria/definicion", response_model=DefinicionResp)
def definicion(analisis: str = "steiner", centro_id: int = Depends(get_current_centro),
               _user: CurrentUser = Depends(get_current_user),
               session: Session = Depends(get_session)) -> DefinicionResp:
    """Landmarks a colocar (orden guiado) y normas del análisis (builtin o a medida), para el trazador."""
    if analisis in ANALISIS:
        a = ANALISIS[analisis]
        landmarks, normas, label = a["landmarks"], a["normas"], a["label"]
    else:
        cust = _custom(session, centro_id, analisis)
        if not cust:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Análisis no disponible")
        landmarks, label = cust.landmarks_json, cust.nombre
        normas = {m["code"]: {"media": m.get("norma"), "sd": m.get("sd"),
                              "unidad": ("mm" if m.get("tipo") in ("distancia", "perpendicular") else "°"),
                              "label": m.get("label", m["code"])}
                  for m in (cust.medidas_json or []) if m.get("code")}
    return DefinicionResp(analisis=analisis, label=label, landmarks=landmarks,
                          normas=normas, disponibles=_disponibles(session, centro_id))


@router.get("/radiologia/{imagen_id}/cefalometria", response_model=list[TrazadoDTO])
def listar(imagen_id: int, centro_id: int = Depends(get_current_centro),
           _user: CurrentUser = Depends(get_current_user),
           session: Session = Depends(get_session)) -> list[TrazadoDTO]:
    _get_imagen(session, centro_id, imagen_id)
    trazados = session.exec(select(Cefalometria).where(Cefalometria.imagen_id == imagen_id)).all()
    return [_dto(session, centro_id, t) for t in trazados]


@router.post("/radiologia/{imagen_id}/cefalometria", response_model=TrazadoDTO,
             status_code=status.HTTP_201_CREATED)
def guardar(imagen_id: int, datos: TrazadoIn,
            centro_id: int = Depends(get_current_centro),
            _user: CurrentUser = Depends(get_current_user),
            session: Session = Depends(get_session)) -> TrazadoDTO:
    """Calcula el análisis desde los landmarks y guarda el trazado (upsert por imagen+análisis)."""
    img = _get_imagen(session, centro_id, imagen_id)
    calc = calcular(session, centro_id, datos.analisis, datos.landmarks or {}, datos.calibracion)
    if calc is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Análisis no soportado")

    prev = session.exec(select(Cefalometria).where(
        Cefalometria.imagen_id == imagen_id, Cefalometria.analisis == datos.analisis)).first()
    if prev:
        prev.landmarks_json = datos.landmarks or {}
        prev.calibracion_json = datos.calibracion
        prev.mediciones_json = calc["mediciones"]
        cef = prev
    else:
        cef = Cefalometria(
            imagen_id=imagen_id, paciente_id=img.paciente_id, analisis=datos.analisis,
            landmarks_json=datos.landmarks or {}, calibracion_json=datos.calibracion,
            mediciones_json=calc["mediciones"],
        )
    session.add(cef)
    session.commit()
    session.refresh(cef)
    return _dto(session, centro_id, cef)


# ───────────────────────── Constructor de análisis a medida ─────────────────────────
_N_PUNTOS = {"angulo3": 3, "lineas": 4, "distancia": 2, "perpendicular": 3}


class MedidaDef(BaseModel):
    code: str
    label: str
    tipo: str
    puntos: list[str]
    norma: Optional[float] = None
    sd: Optional[float] = None


class AnalisisCustomIn(BaseModel):
    nombre: str
    landmarks: list[dict]          # [{code, label, hint?}]
    medidas: list[MedidaDef]


class AnalisisCustomDTO(BaseModel):
    id: int
    slug: str
    nombre: str
    landmarks: list[dict]
    medidas: list[dict]


def _validar_custom(datos: AnalisisCustomIn) -> None:
    codes = {str(l.get("code") or "").strip() for l in datos.landmarks if l.get("code")}
    if not codes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Define al menos un punto")
    for m in datos.medidas:
        if m.tipo not in TIPOS_MEDIDA:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Tipo de medida no válido: {m.tipo}")
        if len(m.puntos) != _N_PUNTOS[m.tipo]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"«{m.label}» ({m.tipo}) requiere {_N_PUNTOS[m.tipo]} puntos")
        for p in m.puntos:
            if p not in codes:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"El punto «{p}» no está definido")


@router.get("/cefalometria/analisis", response_model=list[AnalisisCustomDTO])
def listar_custom(centro_id: int = Depends(get_current_centro),
                  _user: CurrentUser = Depends(get_current_user),
                  session: Session = Depends(get_session)) -> list[AnalisisCustomDTO]:
    filas = session.exec(select(AnalisisCefalo).where(AnalisisCefalo.centro_id == centro_id)).all()
    return [AnalisisCustomDTO(id=c.id, slug=c.slug, nombre=c.nombre,
                              landmarks=c.landmarks_json or [], medidas=c.medidas_json or []) for c in filas]


@router.post("/cefalometria/analisis", response_model=AnalisisCustomDTO, status_code=status.HTTP_201_CREATED)
def crear_custom(datos: AnalisisCustomIn, centro_id: int = Depends(get_current_centro),
                 _user: CurrentUser = Depends(get_current_user),
                 session: Session = Depends(get_session)) -> AnalisisCustomDTO:
    """Crea un análisis cefalométrico definido por el centro (puntos + fórmulas)."""
    if not datos.nombre.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Falta el nombre")
    _validar_custom(datos)
    c = AnalisisCefalo(centro_id=centro_id, slug="pendiente", nombre=datos.nombre.strip(),
                       landmarks_json=datos.landmarks, medidas_json=[m.model_dump() for m in datos.medidas])
    session.add(c)
    session.commit()
    session.refresh(c)
    c.slug = f"custom_{c.id}"          # slug estable único (no colisiona con builtin)
    session.add(c)
    session.commit()
    session.refresh(c)
    return AnalisisCustomDTO(id=c.id, slug=c.slug, nombre=c.nombre,
                             landmarks=c.landmarks_json, medidas=c.medidas_json)


@router.delete("/cefalometria/analisis/{analisis_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_custom(analisis_id: int, centro_id: int = Depends(get_current_centro),
                  _user: CurrentUser = Depends(get_current_user),
                  session: Session = Depends(get_session)) -> None:
    c = session.get(AnalisisCefalo, analisis_id)
    if not c or c.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Análisis no encontrado")
    session.delete(c)
    session.commit()


class PuntoEvolucion(BaseModel):
    imagen_id: int
    fecha: str
    mediciones: dict


class ComparativaResp(BaseModel):
    analisis: str
    serie: list[PuntoEvolucion]
    delta: dict                            # {code: {inicial, final, cambio, label, unidad}}


@router.get("/pacientes/{paciente_id}/cefalometria/comparar", response_model=ComparativaResp)
def comparar(paciente_id: int, analisis: str = "steiner",
             centro_id: int = Depends(get_current_centro),
             _user: CurrentUser = Depends(get_current_user),
             session: Session = Depends(get_session)) -> ComparativaResp:
    """Evolución longitudinal: los trazados del mismo análisis del paciente, por fecha, con el
    cambio (final − inicial) de cada medida presente en ambos extremos."""
    _get_paciente(session, centro_id, paciente_id)
    trazados = session.exec(
        select(Cefalometria, ImagenRx)
        .join(ImagenRx, ImagenRx.id == Cefalometria.imagen_id)
        .where(Cefalometria.paciente_id == paciente_id, Cefalometria.analisis == analisis)
        .order_by(ImagenRx.created_at)
    ).all()

    serie: list[PuntoEvolucion] = []
    for cef, img in trazados:
        calc = calcular(session, centro_id, analisis, cef.landmarks_json or {}, cef.calibracion_json) or {"mediciones": {}}
        serie.append(PuntoEvolucion(
            imagen_id=img.id, fecha=img.created_at.date().isoformat() if img.created_at else "",
            mediciones=calc["mediciones"]))

    delta: dict = {}
    if len(serie) >= 2:
        ini, fin = serie[0].mediciones, serie[-1].mediciones
        for code, mf in fin.items():
            mi = ini.get(code)
            if mi and mi.get("valor") is not None and mf.get("valor") is not None:
                delta[code] = {
                    "label": mf.get("label", code), "unidad": mf.get("unidad", ""),
                    "inicial": mi["valor"], "final": mf["valor"],
                    "cambio": round(mf["valor"] - mi["valor"], 1),
                }
    return ComparativaResp(analisis=analisis, serie=serie, delta=delta)


@router.get("/radiologia/{imagen_id}/cefalometria/{analisis}/informe.pdf")
def informe(imagen_id: int, analisis: str,
            centro_id: int = Depends(get_current_centro),
            _user: CurrentUser = Depends(get_current_user),
            session: Session = Depends(get_session)) -> Response:
    """Informe cefalométrico en PDF (imagen con trazado + medidas + interpretación)."""
    img = _get_imagen(session, centro_id, imagen_id)
    cef = session.exec(select(Cefalometria).where(
        Cefalometria.imagen_id == imagen_id, Cefalometria.analisis == analisis)).first()
    if not cef:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No hay trazado de ese análisis para la imagen")
    ruta = _MEDIA / img.archivo_url
    if not ruta.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fichero de imagen no encontrado")
    calc = calcular(session, centro_id, analisis, cef.landmarks_json or {}, cef.calibracion_json) or {
        "mediciones": cef.mediciones_json or {}, "interpretacion": {}, "calibrada": False}
    pac = _get_paciente(session, centro_id, img.paciente_id)
    nombre = " ".join(x for x in [pac.nombre, pac.apellidos] if x) or "—"
    cust = _custom(session, centro_id, analisis)
    label = ANALISIS.get(analisis, {}).get("label") or (cust.nombre if cust else analisis)
    pdf = informe_pdf(
        imagen_bytes=ruta.read_bytes(), analisis_label=label, analisis=analisis,
        landmarks=cef.landmarks_json or {}, mediciones=calc["mediciones"],
        interpretacion=calc["interpretacion"], paciente=nombre,
        num_historia=pac.num_historia or "—", calibrada=calc["calibrada"],
    )
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="cefalometria_{analisis}_{imagen_id}.pdf"'})


@router.delete("/cefalometria/{trazado_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar(trazado_id: int, centro_id: int = Depends(get_current_centro),
           _user: CurrentUser = Depends(get_current_user),
           session: Session = Depends(get_session)) -> None:
    cef = session.get(Cefalometria, trazado_id)
    if not cef:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trazado no encontrado")
    _get_imagen(session, centro_id, cef.imagen_id)  # valida tenant
    session.delete(cef)
    session.commit()
