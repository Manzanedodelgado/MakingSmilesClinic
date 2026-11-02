"""🧿 MEMBRANA DOCTOR — gateway de la app nativa del profesional.

Prefix `/app/doctores/me/...`. Reutiliza la MISMA identidad y auth que el personal de
centro (JWT `tipo:"centro"`, Bearer + cabecera `X-Centro-Id`), por lo que NO duplica el
login: la app móvil del doctor usa `/auth/login` (que ya devuelve el token en el cuerpo)
y manda el centro activo en `X-Centro-Id`. Todo lo demás cuelga de `get_current_centro`,
así que el multi-tenant y el control de acceso son exactamente los del panel web.

Objeto de la app (petición del usuario): consultar la AGENDA del día y realizar la TOMA
DE FOTOS de los estudios de ortodoncia siguiendo un protocolo rutinario con guías de
calidad (ver domain/services/protocolo_ortodoncia.py — fuente de verdad compartida).

Las fotos clínicas son PII (R4/RGPD): el fichero vive en disco fuera de StaticFiles y se
sirve SIEMPRE por endpoint autenticado y con guard de `centro_id`.
"""
import asyncio
import json
import logging
import uuid
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import (APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status)
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from api.auth_deps import CurrentUser, get_current_centro, get_current_user
from api.paciente_helper import _get_paciente
from api.pacientes_router import _actos_data, _edad
from application.services.disponibilidad_service import estado_id_por_codigo
from application.services.multimedia_service import MultimediaService
from domain.models.agenda import EstadoCita, TipoCita
from domain.models.core import Cita, Colaborador, Paciente
from domain.models.identidad import Usuario, UsuarioPeriodo
from domain.models.ortodoncia import CasoOrtodoncia, EstudioOrtodoncia, FotoOrtodoncia
from domain.services import protocolo_ortodoncia as proto
from infrastructure.config.db import get_session, engine
from infrastructure.events import emit
from infrastructure.realtime import bus


def _subir_foto_orto_a_drive(paciente_id: int, centro_id: int, contenido: bytes, nombre: str) -> None:
    """Sube la foto del estudio a Google Drive (carpeta del paciente → subcarpeta Imágenes) tras
    responder. Best-effort: si Drive falla, no afecta a la subida de la foto."""
    try:
        from sqlmodel import Session as _S
        with _S(engine) as s:
            pac = _get_paciente(s, centro_id, paciente_id)
            MultimediaService(s).subir_a_drive(centro_id, pac, contenido, nombre, subcarpeta="Imágenes")
    except Exception:  # noqa: BLE001  # raiz: Drive best-effort, no debe tumbar la subida de la foto
        logger.warning("No se pudo subir a Drive la foto orto del paciente %s", paciente_id)

router = APIRouter(prefix="/app/doctores/me", tags=["app doctor · gateway"])
logger = logging.getLogger("membrana.doctor")

MEDIA = Path(__file__).resolve().parent.parent / "media"
_EXT_POR_MIME = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/webp": "webp"}
_MAX_FOTO_BYTES = 12 * 1024 * 1024   # 12 MB por foto clínica


def _colaborador_id_de(session: Session, usuario_id: int) -> Optional[int]:
    """El colaborador (doctor) del usuario logueado — para 'solo mis citas'."""
    return session.exec(
        select(Colaborador.id)
        .join(UsuarioPeriodo, UsuarioPeriodo.id == Colaborador.periodo_id)
        .where(UsuarioPeriodo.usuario_id == usuario_id)
        .order_by(UsuarioPeriodo.id.desc())
    ).first()


# ───────────────────────── perfil del doctor ─────────────────────────
@router.get("/perfil")
def perfil(user: CurrentUser = Depends(get_current_user),
           centro_id: int = Depends(get_current_centro),
           session: Session = Depends(get_session)) -> dict:
    u = session.get(Usuario, user.usuario_id)
    return {
        "usuario_id": user.usuario_id,
        "colaborador_id": _colaborador_id_de(session, user.usuario_id),
        "nombre": user.nombre,
        "apellidos": u.apellidos if u else None,
        "centro_id": centro_id,
        "accesos": user.accesos,
    }


# ───────────────────────── agenda del día ─────────────────────────
def _cita_min_dto(c: Cita, estados: dict, tipos: dict, pac: dict) -> dict:
    e = estados.get(c.estado_id)
    p = pac.get(c.paciente_id) if c.paciente_id else None
    return {
        "id": c.id, "fecha": c.fecha.isoformat(), "hora": c.hora,
        "duracion_min": c.duracion_min or 30,
        "estado_nombre": e["nombre"] if e else None,
        "estado_color": (e["color"] if e else None) or "#065AED",
        "tipo_nombre": tipos.get(c.tipo_cita_id),
        "colaborador_id": c.colaborador_id,
        "paciente_id": c.paciente_id,
        "nombre": c.nombre or (p["nombre"] if p else "") or "",
        "apellidos": c.apellidos or (p["apellidos"] if p else "") or "",
        "num_historia": c.num_historia or (p["num_historia"] if p else None),
        "notas": c.notas,
    }


@router.get("/agenda")
def agenda(fecha: Optional[date] = Query(None), solo_mias: bool = Query(False),
           user: CurrentUser = Depends(get_current_user),
           centro_id: int = Depends(get_current_centro),
           session: Session = Depends(get_session)) -> dict:
    """Citas del día (por defecto hoy). `solo_mias` filtra por el doctor logueado."""
    dia = fecha or date.today()
    stmt = select(Cita).where(Cita.centro_id == centro_id, Cita.fecha == dia)
    if solo_mias:
        col_id = _colaborador_id_de(session, user.usuario_id)
        stmt = stmt.where(Cita.colaborador_id == col_id)
    citas = session.exec(stmt.order_by(Cita.hora)).all()
    anulada_id = estado_id_por_codigo(session, centro_id, "anulada")
    citas = [c for c in citas if c.estado_id != anulada_id]

    estados = {e.id: {"nombre": e.nombre, "color": e.color}
               for e in session.exec(select(EstadoCita).where(EstadoCita.centro_id == centro_id)).all()}
    tipos = {t.id: t.nombre for t in session.exec(select(TipoCita).where(TipoCita.centro_id == centro_id)).all()}
    pac_ids = {c.paciente_id for c in citas if c.paciente_id}
    pac: dict = {}
    if pac_ids:
        for p in session.exec(select(Paciente).where(Paciente.id.in_(pac_ids))).all():
            pac[p.id] = {"nombre": p.nombre or "", "apellidos": p.apellidos or "",
                         "num_historia": p.num_historia}
    return {"fecha": dia.isoformat(), "citas": [_cita_min_dto(c, estados, tipos, pac) for c in citas]}


# ───────────────────────── búsqueda / resumen de paciente ─────────────────────────
@router.get("/pacientes")
def buscar_pacientes(q: str = Query(..., min_length=2),
                     centro_id: int = Depends(get_current_centro),
                     _user: CurrentUser = Depends(get_current_user),
                     session: Session = Depends(get_session)) -> dict:
    from sqlalchemy import or_
    like = f"%{q}%"
    rows = session.exec(
        select(Paciente).where(
            Paciente.centro_id == centro_id, Paciente.activo == True,  # noqa: E712
            or_(Paciente.nombre.ilike(like), Paciente.apellidos.ilike(like),
                Paciente.num_historia.ilike(f"{q}%")),
        ).order_by(Paciente.apellidos, Paciente.nombre).limit(20)
    ).all()
    return {"pacientes": [{"id": p.id, "nombre": p.nombre or "", "apellidos": p.apellidos or "",
                           "num_historia": p.num_historia,
                           "edad": _edad(p.fecha_nacimiento)} for p in rows]}


@router.get("/pacientes/{paciente_id}")
def resumen_paciente(paciente_id: int,
                     centro_id: int = Depends(get_current_centro),
                     _user: CurrentUser = Depends(get_current_user),
                     session: Session = Depends(get_session)) -> dict:
    p = _get_paciente(session, centro_id, paciente_id)
    casos = session.exec(
        select(CasoOrtodoncia).where(CasoOrtodoncia.centro_id == centro_id,
                                     CasoOrtodoncia.paciente_id == paciente_id)
        .order_by(CasoOrtodoncia.fecha_inicio.desc())
    ).all()
    n_estudios = len(session.exec(
        select(EstudioOrtodoncia.id).where(EstudioOrtodoncia.centro_id == centro_id,
                                          EstudioOrtodoncia.paciente_id == paciente_id)
    ).all())
    return {
        "id": p.id, "nombre": p.nombre, "apellidos": p.apellidos,
        "num_historia": p.num_historia, "edad": _edad(p.fecha_nacimiento),
        "telefono": p.telefono_movil or p.telefono_fijo,
        "num_estudios": n_estudios,
        "casos_orto": [{"id": c.id, "aparato": c.aparato, "estado": c.estado,
                        "fecha_inicio": c.fecha_inicio.isoformat()} for c in casos],
    }


# ───────────────────────── protocolo fotográfico (guías) ─────────────────────────
GUIAS_DIR = MEDIA / "protocolo" / "guias"


def _referencia_guia(codigo: str) -> str:
    """Ruta ABSOLUTA de API de la guía de una ranura (la app la pide con auth)."""
    return f"/app/doctores/me/protocolo/guias/{codigo}.png"


@router.get("/protocolo")
def protocolo(_user: CurrentUser = Depends(get_current_user)) -> dict:
    """Serie fotográfica estándar con guías de encuadre y criterios de calidad."""
    return {
        "protocolo": [{**s, "referencia": _referencia_guia(s["codigo"])} for s in proto.PROTOCOLO],
        "obligatorias": proto.CODIGOS_OBLIGATORIOS,
    }


@router.get("/protocolo/guias/{codigo}")
def guia_protocolo(codigo: str,
                   centro_id: int = Depends(get_current_centro),
                   _user: CurrentUser = Depends(get_current_user)):
    """Sirve la imagen esquemática (PNG) de una ranura. Autenticado y multi-tenant, igual
    que el resto de ficheros clínicos: NO se exponen por StaticFiles.

    Acepta el código con o sin extensión: la referencia que se publica en /protocolo
    incluye ".png" (para que el cliente pueda pedirla tal cual), así que aquí se
    normaliza antes de validar."""
    codigo = codigo[:-4] if codigo.endswith(".png") else codigo
    if not proto.es_codigo_valido(codigo):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Guía no encontrada")
    ruta = GUIAS_DIR / f"{codigo}.png"
    if not ruta.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Guía no encontrada")
    return FileResponse(str(ruta), media_type="image/png")


# ───────────────────────── estudios (sesión de fotos) ─────────────────────────
class CrearEstudioIn(BaseModel):
    paciente_id: int
    etapa: str = "inicial"          # inicial | progreso | final
    caso_id: Optional[int] = None


_ETAPAS = {"inicial", "progreso", "final"}


def _foto_dto(f: FotoOrtodoncia) -> dict:
    return {"id": f.id, "tipo": f.tipo, "url": f"/app/doctores/me/fotos/{f.id}",
            "ancho": f.ancho, "alto": f.alto, "creada": f.created_at.isoformat()}


def _estudio_dto(e: EstudioOrtodoncia, con_fotos: bool = False) -> dict:
    d = {"id": e.id, "paciente_id": e.paciente_id, "caso_id": e.caso_id,
         "etapa": e.etapa, "estado": e.estado, "fecha": e.fecha.isoformat(),
         "notas": e.notas}
    if con_fotos:
        d["fotos"] = [_foto_dto(f) for f in sorted(e.fotos, key=lambda x: x.id or 0)]
    return d


@router.post("/estudios", status_code=status.HTTP_201_CREATED)
def crear_estudio(data: CrearEstudioIn,
                  user: CurrentUser = Depends(get_current_user),
                  centro_id: int = Depends(get_current_centro),
                  session: Session = Depends(get_session)) -> dict:
    if data.etapa not in _ETAPAS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Etapa inválida ({', '.join(_ETAPAS)})")
    p = _get_paciente(session, centro_id, data.paciente_id)  # valida pertenencia al centro
    if data.caso_id is not None:
        caso = session.get(CasoOrtodoncia, data.caso_id)
        if not caso or caso.centro_id != centro_id or caso.paciente_id != p.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El caso no pertenece a este paciente")
    est = EstudioOrtodoncia(
        centro_id=centro_id, paciente_id=p.id, caso_id=data.caso_id,
        colaborador_id=_colaborador_id_de(session, user.usuario_id),
        etapa=data.etapa, fecha=date.today(), estado="en_progreso",
    )
    session.add(est)
    session.commit()
    session.refresh(est)
    return _estudio_dto(est, con_fotos=True)


@router.get("/estudios")
def listar_estudios(paciente_id: int = Query(...),
                    centro_id: int = Depends(get_current_centro),
                    _user: CurrentUser = Depends(get_current_user),
                    session: Session = Depends(get_session)) -> dict:
    ests = session.exec(
        select(EstudioOrtodoncia).where(EstudioOrtodoncia.centro_id == centro_id,
                                        EstudioOrtodoncia.paciente_id == paciente_id)
        .order_by(EstudioOrtodoncia.fecha.desc(), EstudioOrtodoncia.id.desc())
    ).all()
    return {"estudios": [_estudio_dto(e, con_fotos=True) for e in ests]}


def _get_estudio(session: Session, centro_id: int, estudio_id: int) -> EstudioOrtodoncia:
    est = session.get(EstudioOrtodoncia, estudio_id)
    if not est or est.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estudio no encontrado")
    return est


@router.get("/estudios/{estudio_id}")
def detalle_estudio(estudio_id: int,
                    centro_id: int = Depends(get_current_centro),
                    _user: CurrentUser = Depends(get_current_user),
                    session: Session = Depends(get_session)) -> dict:
    est = _get_estudio(session, centro_id, estudio_id)
    d = _estudio_dto(est, con_fotos=True)
    hechas = {f.tipo for f in est.fotos}
    d["faltan_obligatorias"] = [c for c in proto.CODIGOS_OBLIGATORIOS if c not in hechas]
    return d


class CompletarEstudioIn(BaseModel):
    notas: Optional[str] = None
    forzar: bool = False          # true = cierra aunque falten tomas obligatorias


@router.post("/estudios/{estudio_id}/completar")
def completar_estudio(estudio_id: int, data: CompletarEstudioIn,
                      centro_id: int = Depends(get_current_centro),
                      _user: CurrentUser = Depends(get_current_user),
                      session: Session = Depends(get_session)):
    est = _get_estudio(session, centro_id, estudio_id)
    hechas = {f.tipo for f in est.fotos}
    faltan = [c for c in proto.CODIGOS_OBLIGATORIOS if c not in hechas]
    if faltan and not data.forzar:
        # 409 con la lista para que la app abra el asistente de tomas que faltan.
        return JSONResponse(status_code=status.HTTP_409_CONFLICT,
                            content={"detail": "Faltan tomas obligatorias",
                                     "faltan_obligatorias": faltan})
    if data.notas is not None:
        est.notas = data.notas
    est.estado = "completado"
    session.add(est)
    session.commit()
    session.refresh(est)
    return _estudio_dto(est, con_fotos=True)


# ───────────────────────── fotos: subir / servir / borrar ─────────────────────────
@router.post("/estudios/{estudio_id}/fotos", status_code=status.HTTP_201_CREATED)
async def subir_foto(estudio_id: int, background: BackgroundTasks, tipo: str = Query(...),
                     file: UploadFile = File(...),
                     centro_id: int = Depends(get_current_centro),
                     _user: CurrentUser = Depends(get_current_user),
                     session: Session = Depends(get_session)) -> dict:
    """Guarda (o REEMPLAZA) la foto de una ranura del protocolo en el estudio."""
    if not proto.es_codigo_valido(tipo):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tipo de foto no está en el protocolo")
    ext = _EXT_POR_MIME.get((file.content_type or "").lower())
    if not ext:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Formato no admitido (jpg, png, webp)")
    est = _get_estudio(session, centro_id, estudio_id)
    contenido = await file.read()
    if not contenido:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Archivo vacío")
    if len(contenido) > _MAX_FOTO_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "La foto supera el máximo (12 MB)")

    destino_dir = MEDIA / "ortodoncia" / str(est.id)
    destino_dir.mkdir(parents=True, exist_ok=True)
    nombre = f"{tipo}_{uuid.uuid4().hex[:8]}.{ext}"
    (destino_dir / nombre).write_bytes(contenido)
    rel = f"ortodoncia/{est.id}/{nombre}"
    ancho, alto = _dimensiones(contenido)

    # Una ranura por estudio: si ya había foto de este tipo, se reemplaza (borra el fichero viejo).
    previa = session.exec(
        select(FotoOrtodoncia).where(FotoOrtodoncia.estudio_id == est.id, FotoOrtodoncia.tipo == tipo)
    ).first()
    if previa:
        _borrar_fichero(previa.archivo)
        session.delete(previa)
        session.flush()

    foto = FotoOrtodoncia(estudio_id=est.id, centro_id=centro_id, paciente_id=est.paciente_id,
                          tipo=tipo, archivo=rel, ancho=ancho, alto=alto)
    session.add(foto)
    session.commit()
    session.refresh(foto)

    # 🔗 Vincula con la WEB MATRIZ: deja también la foto en la carpeta «Imágenes» del paciente
    # (media/pacientes/«{num_historia} — …»), que es lo que lee la ficha web y se replica a Drive.
    # Nombre estable por (estudio, vista) → re-tomar una vista REEMPLAZA su foto también ahí.
    nombre_pac = f"orto_{est.id}_{tipo}.{ext}"
    try:
        pac = _get_paciente(session, centro_id, est.paciente_id)
        MultimediaService(session).guardar_foto_paciente(pac, contenido, nombre_pac)
    except Exception:  # raiz: replica a la carpeta del paciente best-effort, no tumbar la subida
        logger.warning("No se pudo replicar la foto orto a la carpeta del paciente %s", est.paciente_id)

    # Subida a Google Drive (subcarpeta Imágenes) en segundo plano — no bloquea la respuesta.
    background.add_task(_subir_foto_orto_a_drive, est.paciente_id, centro_id, contenido, nombre_pac)

    emit("estudio.foto", {"estudio_id": est.id, "centro_id": centro_id,
                          "paciente_id": est.paciente_id, "tipo": tipo, "foto_id": foto.id})
    return _foto_dto(foto)


@router.get("/fotos/{foto_id}")
def servir_foto(foto_id: int,
                centro_id: int = Depends(get_current_centro),
                _user: CurrentUser = Depends(get_current_user),
                session: Session = Depends(get_session)):
    foto = session.get(FotoOrtodoncia, foto_id)
    if not foto or foto.centro_id != centro_id:   # guard multi-tenant (anti-IDOR)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foto no encontrada")
    ruta = MEDIA / foto.archivo
    if not ruta.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fichero no encontrado")
    return FileResponse(str(ruta))


@router.delete("/fotos/{foto_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_foto(foto_id: int,
                centro_id: int = Depends(get_current_centro),
                _user: CurrentUser = Depends(get_current_user),
                session: Session = Depends(get_session)):
    foto = session.get(FotoOrtodoncia, foto_id)
    if not foto or foto.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foto no encontrada")
    est_pac_id, est_id, tipo_foto = foto.paciente_id, foto.estudio_id, foto.tipo
    _borrar_fichero(foto.archivo)
    session.delete(foto)
    session.commit()
    emit("estudio.foto_borrada", {"estudio_id": est_id, "centro_id": centro_id,
                                  "paciente_id": est_pac_id, "tipo": tipo_foto})


# ───────────────────────── helpers de fichero ─────────────────────────
def _borrar_fichero(rel: str) -> None:
    try:
        (MEDIA / rel).unlink(missing_ok=True)
    except OSError:
        logger.warning("doctor: fichero huérfano en disco (%s)", rel, exc_info=True)


def _dimensiones(contenido: bytes):
    """Ancho/alto si Pillow está disponible; si no, None (no es crítico)."""
    try:
        import io
        from PIL import Image
        with Image.open(io.BytesIO(contenido)) as img:
            return img.width, img.height
    except Exception:  # raiz: Pillow opcional, dimensiones no criticas
        return None, None


# ───────────────────────── TIEMPO REAL (SSE) ─────────────────────────
# El doctor ve TODOS los eventos de agenda y estudios de su centro (no se filtra por
# paciente). Filtramos solo por tipo.
_EVENTOS_DOCTOR = {
    "cita.solicitada", "cita.creada", "cita.actualizada", "cita.movida", "cita.anulada",
    "estudio.foto", "estudio.foto_borrada",
}


@router.get("/stream")
async def stream(centro_id: int = Depends(get_current_centro),
                 _user: CurrentUser = Depends(get_current_user)) -> StreamingResponse:
    """SSE: empuja al movil del profesional los cambios de agenda y de estudios
    fotograficos de su centro mientras la app este abierta. Heartbeat cada 15s. La app,
    al (re)conectar, hace refetch completo de la pantalla visible."""
    async def gen():
        q = await bus.subscribe(centro_id)
        try:
            yield ": ok\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                if ev.get("tipo") not in _EVENTOS_DOCTOR:
                    continue
                yield f"event: {ev['tipo']}\ndata: {json.dumps(ev)}\n\n"
        finally:
            bus.unsubscribe(centro_id, q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
