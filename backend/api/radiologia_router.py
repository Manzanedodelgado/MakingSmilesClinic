"""RADIOLOGÍA — importación, clasificación por IA y hallazgos de imágenes radiológicas.

Sobre los modelos ya existentes `imagenes_rx` + `hallazgos_imagen`. Multi-tenant por paciente
(las imágenes no llevan centro_id: se valida que el paciente pertenezca al centro activo).
La clasificación de modalidad la propone la IA (best-effort) y el doctor la corrige a mano.
"""
from __future__ import annotations
import hmac

import logging
import uuid
from pathlib import Path
from typing import Optional

import logging as _logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from api.auth_deps import CurrentUser, get_current_centro, get_current_user
from api.paciente_helper import _get_paciente
from application.services.multimedia_service import MultimediaService
from application.services.radiologia_service import MODALIDADES, clasificar_modalidad
from application.services.radiologia_pptx import informe_pptx
from application.services.cefalometria_service import ANALISIS
from api.cefalometria_router import calcular as _calcular_cefalo, _custom as _custom_cefalo
from domain.models.clinico import AnotacionImagen, Cefalometria, HallazgoImagen, ImagenRx
from infrastructure.config.db import get_session, engine

_log_rad = _logging.getLogger("membrana.radiologia")


def _subir_rx_a_drive(imagen_id: int, centro_id: int, mime: str) -> None:
    """Sube la RX a Google Drive (carpeta del paciente → subcarpeta RX) tras responder. Best-effort."""
    try:
        with Session(engine) as s:
            img = s.get(ImagenRx, imagen_id)
            if not img:
                return
            ruta = MEDIA / img.archivo_url
            if not ruta.exists():
                return
            from api.paciente_helper import _get_paciente as _gp
            pac = _gp(s, centro_id, img.paciente_id)
            fid = MultimediaService(s).subir_a_drive(centro_id, pac, ruta.read_bytes(),
                                                     f"rx_{img.id}{ruta.suffix}", subcarpeta="RX", mime=mime)
            if fid:
                _log_rad.info("RX %s subida a Drive (%s)", imagen_id, fid)
    except Exception:  # raiz: subida a Drive best-effort, nunca romper la respuesta
        _log_rad.warning("No se pudo subir la RX %s a Drive", imagen_id)


def _clasificar_en_segundo_plano(imagen_id: int, centro_id: int, mime: str) -> None:
    """Clasifica la modalidad DESPUÉS de responder (no bloquea la subida). Best-effort."""
    try:
        with Session(engine) as s:
            img = s.get(ImagenRx, imagen_id)
            if not img:
                return
            ruta = MEDIA / img.archivo_url
            if not ruta.exists() or ruta.suffix == ".dcm":
                return
            modalidad, _conf = clasificar_modalidad(s, centro_id, ruta.read_bytes(), mime)
            if modalidad and modalidad != "sin_clasificar":
                img.modalidad = modalidad
                s.add(img)
                s.commit()
    except Exception:  # raiz: clasificación best-effort, nunca romper por la clasificación
        _log_rad.warning("Clasificación en segundo plano falló para imagen %s", imagen_id)

router = APIRouter(tags=["radiología"])
logger = logging.getLogger("membrana.radiologia")

MEDIA = Path(__file__).resolve().parent.parent / "media"
_EXT_POR_MIME = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png",
                 "image/webp": "webp", "application/dicom": "dcm"}
_MAX_BYTES = 60 * 1024 * 1024   # 60 MB (un CBCT/DICOM pesa)


# ───────────────────────── DTOs ─────────────────────────
class ImagenRxDTO(BaseModel):
    id: int
    paciente_id: int
    cita_id: Optional[int]
    modalidad: str
    modalidad_label: str
    archivo_url: str
    orthanc_study_id: Optional[str]
    hallazgos: list["HallazgoDTO"]


class HallazgoDTO(BaseModel):
    id: int
    descripcion: str
    pieza: Optional[str]
    confianza: Optional[float]


class ReclasificarIn(BaseModel):
    modalidad: str
    cita_id: Optional[int] = None


class HallazgoIn(BaseModel):
    descripcion: str
    pieza: Optional[str] = None
    confianza: Optional[float] = None


class ModalidadesResp(BaseModel):
    modalidades: dict[str, str]


# ───────────────────────── helpers ─────────────────────────
def _dto(img: ImagenRx) -> ImagenRxDTO:
    return ImagenRxDTO(
        id=img.id, paciente_id=img.paciente_id, cita_id=img.cita_id,
        modalidad=img.modalidad, modalidad_label=MODALIDADES.get(img.modalidad, img.modalidad),
        archivo_url=img.archivo_url, orthanc_study_id=img.orthanc_study_id,
        hallazgos=[HallazgoDTO(id=h.id, descripcion=h.descripcion, pieza=h.pieza, confianza=h.confianza)
                   for h in img.hallazgos],
    )


def _get_imagen(session: Session, centro_id: int, imagen_id: int) -> ImagenRx:
    img = session.get(ImagenRx, imagen_id)
    if not img:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Imagen no encontrada")
    _get_paciente(session, centro_id, img.paciente_id)  # valida tenant (404 si no es del centro)
    return img


# ───────────────────────── endpoints ─────────────────────────
@router.post("/radiologia/detectar-rx")
def detectar_rx(centro_id: int = Depends(get_current_centro),
                _user: CurrentUser = Depends(get_current_user),
                session: Session = Depends(get_session)) -> dict:
    """Dispara YA el detector de RX nuevas en Orthanc → export a Drive (además del job cada 30s).
    Útil como botón «Sincronizar RX» o para que el feeder avise tras subir una imagen a Orthanc."""
    from application.services.radiologia_export_service import detectar_y_exportar
    return detectar_y_exportar(session, centro_id)


@router.post("/radiologia/detectar-rx-interno")
def detectar_rx_interno(x_internal_key: Optional[str] = Header(default=None),
                        session: Session = Depends(get_session)) -> dict:
    """Igual que /radiologia/detectar-rx pero autenticado por clave interna: lo llama el feeder
    (rx_watcher) tras subir una imagen a Orthanc para que el export sea inmediato. Todos los centros."""
    from domain.config.settings import settings
    if not x_internal_key or not hmac.compare_digest(x_internal_key, settings.internal_api_key or ""):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Clave interna inválida")
    from application.services.radiologia_export_service import detectar_y_exportar
    return detectar_y_exportar(session)


@router.get("/radiologia/rx-export")
def rx_export_log(centro_id: int = Depends(get_current_centro),
                  _user: CurrentUser = Depends(get_current_user),
                  session: Session = Depends(get_session)) -> dict:
    """Últimas RX procesadas por el detector (exportada / sin_paciente / error) — para auditoría/UI."""
    from domain.models.clinico import RxExportada
    filas = session.exec(select(RxExportada).where(RxExportada.centro_id == centro_id)
                         .order_by(RxExportada.created_at.desc()).limit(50)).all()
    return {"items": [{
        "id": r.id, "instance_id": r.instance_id, "num_historia": r.num_historia,
        "paciente_id": r.paciente_id, "modalidad": r.modalidad, "estado": r.estado,
        "drive_file_id": r.drive_file_id, "detalle": r.detalle,
        "fecha": r.created_at.isoformat() if r.created_at else None,
    } for r in filas]}


@router.get("/radiologia/modalidades", response_model=ModalidadesResp)
def modalidades() -> ModalidadesResp:
    """Catálogo cerrado de modalidades (para el selector de corrección manual)."""
    return ModalidadesResp(modalidades=MODALIDADES)


@router.get("/pacientes/{paciente_id}/radiologia", response_model=list[ImagenRxDTO])
def listar(paciente_id: int, centro_id: int = Depends(get_current_centro),
           _user: CurrentUser = Depends(get_current_user),
           session: Session = Depends(get_session)) -> list[ImagenRxDTO]:
    _get_paciente(session, centro_id, paciente_id)
    imgs = session.exec(select(ImagenRx).where(ImagenRx.paciente_id == paciente_id)
                        .order_by(ImagenRx.created_at.desc())).all()
    return [_dto(i) for i in imgs]


@router.post("/pacientes/{paciente_id}/radiologia", response_model=ImagenRxDTO,
             status_code=status.HTTP_201_CREATED)
async def importar(paciente_id: int, background: BackgroundTasks, file: UploadFile = File(...),
                   cita_id: Optional[int] = Query(default=None),
                   clasificar: bool = Query(default=True),
                   centro_id: int = Depends(get_current_centro),
                   _user: CurrentUser = Depends(get_current_user),
                   session: Session = Depends(get_session)) -> ImagenRxDTO:
    """Importa una imagen radiológica y la guarda. La clasificación por IA se hace DESPUÉS de
    responder (en segundo plano) para que la subida sea instantánea y no dependa de la IA."""
    _get_paciente(session, centro_id, paciente_id)
    ext = _EXT_POR_MIME.get((file.content_type or "").lower())
    if not ext:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Formato no admitido (jpg, png, webp, dcm)")
    # FastAPI ya escribe cargas grandes a fichero temporal. Leer como máximo el límite
    # más un byte evita que una petición sin Content-Length fiable agote la memoria.
    contenido = await file.read(_MAX_BYTES + 1)
    if not contenido:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Archivo vacío")
    if len(contenido) > _MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "La imagen supera el máximo (60 MB)")

    destino_dir = MEDIA / "radiologia" / str(paciente_id)
    destino_dir.mkdir(parents=True, exist_ok=True)
    nombre = f"{uuid.uuid4().hex}.{ext}"
    (destino_dir / nombre).write_bytes(contenido)
    rel = f"radiologia/{paciente_id}/{nombre}"

    img = ImagenRx(paciente_id=paciente_id, cita_id=cita_id, modalidad="sin_clasificar", archivo_url=rel)
    session.add(img)
    session.commit()
    session.refresh(img)

    # Replica a la carpeta del paciente (subcarpeta «RX») para que aparezca en Multimedia (misma
    # ubicación que lee la ficha web). Vincula Radiología ↔ web matriz, como las fotos de la app.
    try:
        pac = _get_paciente(session, centro_id, paciente_id)
        MultimediaService(session).guardar_foto_paciente(pac, contenido, f"rx_{img.id}.{ext}", subcarpeta="RX")
    except Exception:  # raiz: réplica a la carpeta del paciente best-effort
        _log_rad.warning("No se pudo replicar la RX %s a la carpeta del paciente", img.id)

    # En segundo plano (no bloquean la respuesta): subir la RX a Google Drive y clasificar por IA.
    mime = file.content_type or "image/jpeg"
    background.add_task(_subir_rx_a_drive, img.id, centro_id, mime)
    if clasificar and ext != "dcm":
        background.add_task(_clasificar_en_segundo_plano, img.id, centro_id, mime)

    return _dto(img)


@router.get("/radiologia/{imagen_id}/archivo")
def archivo(imagen_id: int, centro_id: int = Depends(get_current_centro),
            _user: CurrentUser = Depends(get_current_user),
            session: Session = Depends(get_session)) -> FileResponse:
    img = _get_imagen(session, centro_id, imagen_id)
    ruta = MEDIA / img.archivo_url
    if not ruta.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fichero no encontrado")
    return FileResponse(ruta)


@router.patch("/radiologia/{imagen_id}", response_model=ImagenRxDTO)
def reclasificar(imagen_id: int, datos: ReclasificarIn,
                 centro_id: int = Depends(get_current_centro),
                 _user: CurrentUser = Depends(get_current_user),
                 session: Session = Depends(get_session)) -> ImagenRxDTO:
    """Corrección manual de la modalidad (y opcional vínculo a la cita)."""
    if datos.modalidad not in MODALIDADES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Modalidad fuera del catálogo")
    img = _get_imagen(session, centro_id, imagen_id)
    img.modalidad = datos.modalidad
    if datos.cita_id is not None:
        img.cita_id = datos.cita_id
    session.add(img)
    session.commit()
    session.refresh(img)
    return _dto(img)


@router.post("/radiologia/{imagen_id}/clasificar", response_model=ImagenRxDTO)
def reclasificar_ia(imagen_id: int, centro_id: int = Depends(get_current_centro),
                    _user: CurrentUser = Depends(get_current_user),
                    session: Session = Depends(get_session)) -> ImagenRxDTO:
    """Vuelve a pedir a la IA la modalidad de una imagen ya importada."""
    img = _get_imagen(session, centro_id, imagen_id)
    ruta = MEDIA / img.archivo_url
    if not ruta.exists() or ruta.suffix == ".dcm":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No clasificable (sin fichero o DICOM)")
    mime = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ruta.suffix.lstrip("."), "image/jpeg")
    modalidad, _conf = clasificar_modalidad(session, centro_id, ruta.read_bytes(), mime)
    img.modalidad = modalidad
    session.add(img)
    session.commit()
    session.refresh(img)
    return _dto(img)


@router.delete("/radiologia/{imagen_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar(imagen_id: int, centro_id: int = Depends(get_current_centro),
           _user: CurrentUser = Depends(get_current_user),
           session: Session = Depends(get_session)) -> None:
    img = _get_imagen(session, centro_id, imagen_id)
    for h in list(img.hallazgos):
        session.delete(h)
    # También trazados cefalométricos y anotaciones (FK a esta imagen) para no violar integridad.
    for cef in session.exec(select(Cefalometria).where(Cefalometria.imagen_id == imagen_id)).all():
        session.delete(cef)
    for ano in session.exec(select(AnotacionImagen).where(AnotacionImagen.imagen_id == imagen_id)).all():
        session.delete(ano)
    ruta = MEDIA / img.archivo_url
    if ruta.exists():
        ruta.unlink(missing_ok=True)
    # Quita también la réplica en la carpeta del paciente (subcarpeta RX) que ve Multimedia.
    try:
        pac = _get_paciente(session, centro_id, img.paciente_id)
        carpeta = MultimediaService(session)._carpeta_local(pac)  # noqa: SLF001
        if carpeta:
            ext = Path(img.archivo_url).suffix.lstrip(".")
            (carpeta / "RX" / f"rx_{img.id}.{ext}").unlink(missing_ok=True)
    except Exception:  # raiz: réplica RX huérfana en disco, best-effort
        logger.warning("radiología: réplica RX huérfana en disco (imagen %s)", img.id, exc_info=True)
    session.delete(img)
    session.commit()


@router.post("/radiologia/{imagen_id}/hallazgos", response_model=HallazgoDTO,
             status_code=status.HTTP_201_CREATED)
def crear_hallazgo(imagen_id: int, datos: HallazgoIn,
                   centro_id: int = Depends(get_current_centro),
                   _user: CurrentUser = Depends(get_current_user),
                   session: Session = Depends(get_session)) -> HallazgoDTO:
    _get_imagen(session, centro_id, imagen_id)
    h = HallazgoImagen(imagen_id=imagen_id, descripcion=datos.descripcion.strip(),
                       pieza=datos.pieza, confianza=datos.confianza)
    session.add(h)
    session.commit()
    session.refresh(h)
    return HallazgoDTO(id=h.id, descripcion=h.descripcion, pieza=h.pieza, confianza=h.confianza)


# ───────────────────────── Anotaciones sobre la imagen ─────────────────────────
class AnotacionesIn(BaseModel):
    items: list                            # [{tipo, puntos, texto?, color?}]


class AnotacionesResp(BaseModel):
    imagen_id: int
    items: list


@router.get("/radiologia/{imagen_id}/anotaciones", response_model=AnotacionesResp)
def get_anotaciones(imagen_id: int, centro_id: int = Depends(get_current_centro),
                    _user: CurrentUser = Depends(get_current_user),
                    session: Session = Depends(get_session)) -> AnotacionesResp:
    _get_imagen(session, centro_id, imagen_id)
    a = session.exec(select(AnotacionImagen).where(AnotacionImagen.imagen_id == imagen_id)).first()
    return AnotacionesResp(imagen_id=imagen_id, items=a.items_json if a else [])


@router.put("/radiologia/{imagen_id}/anotaciones", response_model=AnotacionesResp)
def put_anotaciones(imagen_id: int, datos: AnotacionesIn,
                    centro_id: int = Depends(get_current_centro),
                    _user: CurrentUser = Depends(get_current_user),
                    session: Session = Depends(get_session)) -> AnotacionesResp:
    """Guarda TODAS las anotaciones de la imagen (upsert por imagen)."""
    img = _get_imagen(session, centro_id, imagen_id)
    a = session.exec(select(AnotacionImagen).where(AnotacionImagen.imagen_id == imagen_id)).first()
    if a:
        a.items_json = datos.items
    else:
        a = AnotacionImagen(imagen_id=imagen_id, paciente_id=img.paciente_id, items_json=datos.items)
    session.add(a)
    session.commit()
    return AnotacionesResp(imagen_id=imagen_id, items=datos.items)


# ───────────────────────── Presentación del caso (PPTX) ─────────────────────────
@router.get("/pacientes/{paciente_id}/radiologia/informe.pptx")
def informe_presentacion(paciente_id: int, centro_id: int = Depends(get_current_centro),
                         _user: CurrentUser = Depends(get_current_user),
                         session: Session = Depends(get_session)) -> Response:
    """Presentación PPTX del caso: portada + una diapositiva por RX (con hallazgos) + cefalometrías."""
    pac = _get_paciente(session, centro_id, paciente_id)

    def _bytes(img: ImagenRx):
        ruta = MEDIA / img.archivo_url
        return ruta.read_bytes() if ruta.exists() and ruta.suffix != ".dcm" else None

    imgs = session.exec(select(ImagenRx).where(ImagenRx.paciente_id == paciente_id)
                        .order_by(ImagenRx.created_at)).all()
    radiografias = [{
        "titulo": MODALIDADES.get(img.modalidad, img.modalidad),
        "imagen_bytes": _bytes(img),
        "hallazgos": [h.descripcion + (f" ({h.pieza})" if h.pieza else "") for h in img.hallazgos],
    } for img in imgs]

    cefs = session.exec(
        select(Cefalometria, ImagenRx).join(ImagenRx, ImagenRx.id == Cefalometria.imagen_id)
        .where(Cefalometria.paciente_id == paciente_id).order_by(ImagenRx.created_at)).all()
    cefalometrias = []
    for cef, img in cefs:
        calc = _calcular_cefalo(session, centro_id, cef.analisis, cef.landmarks_json or {}, cef.calibracion_json) or {"mediciones": {}, "interpretacion": {}}
        cust = _custom_cefalo(session, centro_id, cef.analisis)
        label = ANALISIS.get(cef.analisis, {}).get("label") or (cust.nombre if cust else cef.analisis)
        cefalometrias.append({
            "titulo": f"Cefalometría · {label}",
            "imagen_bytes": _bytes(img), "mediciones": calc["mediciones"], "interpretacion": calc["interpretacion"],
        })

    nombre = " ".join(x for x in [pac.nombre, pac.apellidos] if x) or "—"
    pptx = informe_pptx(paciente=nombre, num_historia=pac.num_historia or "—",
                        radiografias=radiografias, cefalometrias=cefalometrias)
    return Response(content=pptx,
                    media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    headers={"Content-Disposition": f'attachment; filename="caso_{paciente_id}.pptx"'})


# ───────────────────────── DICOM (visor de cortes vía Orthanc) ─────────────────────────
class SerieDicomDTO(BaseModel):
    series_id: str
    modalidad: str
    descripcion: str
    fecha: Optional[str]
    instancias: list[str]


@router.get("/pacientes/{paciente_id}/dicom/series", response_model=list[SerieDicomDTO])
def dicom_series(paciente_id: int, centro_id: int = Depends(get_current_centro),
                 _user: CurrentUser = Depends(get_current_user),
                 session: Session = Depends(get_session)) -> list[SerieDicomDTO]:
    """Series DICOM del paciente en el PACS (Orthanc), con instancias ordenadas para el visor."""
    pac = _get_paciente(session, centro_id, paciente_id)
    return [SerieDicomDTO(**s) for s in MultimediaService(session).series_dicom(centro_id, pac)]


@router.get("/pacientes/{paciente_id}/dicom/slice/{instance_id}")
def dicom_slice(paciente_id: int, instance_id: str, thumb: bool = Query(default=False),
                centro_id: int = Depends(get_current_centro),
                _user: CurrentUser = Depends(get_current_user),
                session: Session = Depends(get_session)) -> Response:
    """Un corte renderizado (PNG/JPEG) del PACS. Guard anti-IDOR: la instancia debe ser del paciente."""
    pac = _get_paciente(session, centro_id, paciente_id)
    res = MultimediaService(session).media(centro_id, pac, f"orthanc:{instance_id}", thumb)
    if not res:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Corte no disponible")
    contenido, mime = res
    return Response(content=contenido, media_type=mime, headers={"Cache-Control": "private, max-age=300"})


@router.delete("/radiologia/hallazgos/{hallazgo_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_hallazgo(hallazgo_id: int, centro_id: int = Depends(get_current_centro),
                    _user: CurrentUser = Depends(get_current_user),
                    session: Session = Depends(get_session)) -> None:
    h = session.get(HallazgoImagen, hallazgo_id)
    if not h:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hallazgo no encontrado")
    _get_imagen(session, centro_id, h.imagen_id)  # valida tenant
    session.delete(h)
    session.commit()


ImagenRxDTO.model_rebuild()


# ── Importación desde Romexis (bridge) ──────────────────────────────────────────────────
_ROMEXIS_MAX_BYTES = 40 * 1024 * 1024
_ROMEXIS_MAGIC = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")   # JPEG / PNG ya convertidos por el bridge


@router.post("/radiologia/importar-romexis-interno")
async def importar_romexis_interno(
        request: Request,
        x_internal_key: Optional[str] = Header(default=None),
        x_num_historia: Optional[str] = Header(default=None),
        x_filename: Optional[str] = Header(default=None),
        centro_id: int = Query(default=1),
        session: Session = Depends(get_session)) -> dict:
    """Recibe UNA imagen de Romexis (ya convertida a JPG/PNG por el bridge) y la guarda en la
    subcarpeta «RX» de la carpeta del paciente (la que lee Multimedia). Se identifica al paciente
    por `X-Num-Historia` (= external_id de Romexis). Auth: clave interna. Idempotente: si ya existe
    un fichero con ese nombre no lo sobrescribe. No toca Romexis."""
    from domain.config.settings import settings
    if not x_internal_key or not hmac.compare_digest(x_internal_key, settings.internal_api_key or ""):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Clave interna inválida")
    nh = (x_num_historia or "").strip()
    nombre = Path(x_filename or "").name
    if not nh or not nombre:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Faltan X-Num-Historia o X-Filename")
    datos = await request.body()
    if not datos or len(datos) > _ROMEXIS_MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Imagen vacía o demasiado grande")
    if not datos.startswith(_ROMEXIS_MAGIC):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Solo JPEG o PNG")
    from domain.models.core import Paciente
    pac = session.exec(select(Paciente).where(Paciente.num_historia == nh,
                                              Paciente.centro_id == centro_id)).first()
    if not pac:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Sin paciente con num_historia {nh}")
    svc = MultimediaService(session)
    carpeta = svc._carpeta_local(pac, crear=True)
    if carpeta and (carpeta / "RX" / nombre).exists():
        return {"ok": True, "estado": "ya_existe", "num_historia": nh, "archivo": nombre}
    destino = svc.guardar_foto_paciente(centro_id, pac, datos, nombre, subcarpeta="RX")
    if not destino:
        raise HTTPException(status.HTTP_409_CONFLICT, "No se pudo guardar (num_historia en varios centros)")
    return {"ok": True, "estado": "guardada", "num_historia": nh, "archivo": nombre}
