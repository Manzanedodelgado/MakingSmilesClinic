"""Consentimientos informados COEM — plantillas PDF, generación (relleno) y firma digital.

Las 9 plantillas COEM viven en backend/assets/consentimientos (PDF fijos; el contenedor
no ve frontend/, ver PLANTILLAS_DIR en consentimiento_service).
Generar = rellenar el PDF con clínica/doctor/paciente/fecha (application/services/
consentimiento_pdf) y guardar el resultado en media/consentimientos, creando la fila
`consentimientos` (estado pendiente). Firmar = incrustar la firma manuscrita y pasar a
'firmado'. Protegido por permisos de pacientes; PII → auditado.
"""
from typing import Optional

import base64
import logging

import fitz
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from api.auth_deps import CurrentUser, get_current_centro, require_permission
from application.services import consentimiento_service as consvc
from application.services.auth_service import AuthService
from application.services.consentimiento_pdf import firma_desde_datauri, incrustar_firma
from domain.models.core import Centro, Cita, Paciente
from domain.models.documentos import Consentimiento
from infrastructure.config.db import get_session

router = APIRouter(prefix="/consentimientos", tags=["consentimientos"])

logger = logging.getLogger(__name__)

_OUT_DIR = consvc.OUT_DIR
PLANTILLAS = consvc.PLANTILLAS   # catálogo COEM (fuente única en el servicio)


class GenerarIn(BaseModel):
    paciente_id: int
    plantilla: str
    colaborador_id: Optional[int] = None


class FirmarIn(BaseModel):
    firma: str   # data:image/png;base64,…


def _dto(c: Consentimiento) -> dict:
    return {"id": c.id, "tipo": c.tipo, "estado": c.estado,
            "archivo_url": c.archivo_url, "firma_url": c.firma_url,
            "signing_code": c.signing_code,
            "fecha": c.created_at.isoformat() if c.created_at else None,
            # Al firmar se actualiza la fila: su updated_at es la fecha de firma (vigencia: 3 meses).
            "firmadoAt": c.updated_at.isoformat() if c.estado == "firmado" and c.updated_at else None}


# ─────────────────── FIRMA PÚBLICA POR ENLACE (sin auth, protegida por el código) ───────────────────
@router.get("/firmar/{code}")
def firmar_info(code: str, session: Session = Depends(get_session)) -> dict:
    c = consvc.info_por_codigo(session, code)
    if not c or consvc.expirado(c):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enlace no válido")
    centro = session.get(Centro, c.centro_id)
    return {"tipo": c.tipo, "estado": c.estado, "firmado": c.estado == "firmado",
            # El PDF se sirve por la ruta gateada por el código (ya NO por /media crudo).
            "pdf_url": f"/consentimientos/firmar/{code}/pdf",
            "clinica": (centro.nombre if centro else "")}


@router.get("/firmar/{code}/pdf")
def firmar_pdf(code: str, session: Session = Depends(get_session)):
    """PDF del consentimiento para la página PÚBLICA de firma. SIN login, gateado por el
    `signing_code` del enlace (sustituye al servido crudo por /media, cerrado en C8)."""
    from fastapi.responses import FileResponse
    c = consvc.info_por_codigo(session, code)
    if not c or consvc.expirado(c):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enlace no válido")
    pdf = _OUT_DIR / f"consent_{c.id}.pdf"
    if not pdf.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PDF no disponible")
    return FileResponse(str(pdf), media_type="application/pdf",
                        headers={"Content-Disposition": "inline"})


@router.post("/firmar/{code}")
def firmar_publico(code: str, body: "FirmarIn", request: Request,
                   session: Session = Depends(get_session)) -> dict:
    try:
        c = consvc.firmar_por_codigo(session, code, body.firma)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Firma vacía")
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enlace no válido")
    # Acto con valor legal firmado por el PACIENTE (sin usuario de la app): rastro con IP.
    AuthService(session).audit("consentimiento.firmar_publico", usuario_id=None, centro_id=c.centro_id,
                               recurso=f"consentimiento:{c.id}", detalle={"via": "enlace", "tipo": c.tipo},
                               ip=request.client.host if request.client else None)
    return {"ok": True, "estado": c.estado}


@router.get("/plantillas")
def listar_plantillas(user: CurrentUser = Depends(require_permission("pacientes.ver"))) -> dict:
    return {"plantillas": [{"key": k, "label": v[0]} for k, v in PLANTILLAS.items()]}


@router.get("/paciente/{paciente_id}")
def listar_paciente(
    paciente_id: int,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("pacientes.ver")),
    session: Session = Depends(get_session),
) -> list[dict]:
    rows = session.exec(
        select(Consentimiento).where(
            Consentimiento.paciente_id == paciente_id,
            Consentimiento.centro_id == centro_id,
        ).order_by(Consentimiento.id.desc())
    ).all()
    return [_dto(c) for c in rows]


@router.post("")
def generar(
    body: GenerarIn,
    request: Request,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("pacientes.editar")),
    session: Session = Depends(get_session),
) -> dict:
    if body.plantilla not in PLANTILLAS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Plantilla desconocida")
    pac = session.get(Paciente, body.paciente_id)
    if not pac or pac.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    try:
        c = consvc.generar(session, centro_id, body.paciente_id, body.plantilla, body.colaborador_id)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Plantilla PDF no encontrada en el servidor")
    AuthService(session).audit("consentimiento.generar", usuario_id=user.usuario_id, centro_id=centro_id,
                               recurso=f"consentimiento:{c.id}", ip=request.client.host if request.client else None,
                               detalle={"paciente_id": body.paciente_id, "plantilla": body.plantilla, "tipo": c.tipo})
    return _dto(c)


@router.post("/{cid}/firmar")
def firmar(
    cid: int,
    body: FirmarIn,
    request: Request,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("pacientes.editar")),
    session: Session = Depends(get_session),
) -> dict:
    c = session.get(Consentimiento, cid)
    if not c or c.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consentimiento no encontrado")
    if c.estado == "firmado":
        # Firmar otra vez estamparía una segunda firma sobre el documento ya firmado.
        raise HTTPException(status.HTTP_409_CONFLICT, "Este consentimiento ya está firmado")
    firma = firma_desde_datauri(body.firma)
    if not firma:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Firma no válida")
    pdf_path = _OUT_DIR / f"consent_{c.id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PDF del consentimiento no encontrado")
    firmado = incrustar_firma(str(pdf_path), firma)
    pdf_path.write_bytes(firmado)
    (_OUT_DIR / f"firma_{c.id}.png").write_bytes(firma)
    c.firma_url = f"/media/consentimientos/firma_{c.id}.png"
    c.estado = "firmado"
    session.add(c)
    session.commit()
    AuthService(session).audit("consentimiento.firmar", usuario_id=user.usuario_id, centro_id=centro_id,
                               recurso=f"consentimiento:{c.id}", ip=request.client.host if request.client else None)
    return _dto(c)


@router.delete("/{cid}")
def borrar(
    cid: int,
    request: Request,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("pacientes.editar")),
    session: Session = Depends(get_session),
) -> dict:
    c = session.get(Consentimiento, cid)
    if not c or c.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consentimiento no encontrado")
    snap = {"tipo": c.tipo, "estado": c.estado, "pacienteId": c.paciente_id}
    for f in (_OUT_DIR / f"consent_{c.id}.pdf", _OUT_DIR / f"firma_{c.id}.png"):
        try:
            f.unlink(missing_ok=True)
        except OSError:
            logger.warning("consentimientos: fichero huérfano (%s)", f, exc_info=True)
    session.delete(c)
    session.commit()
    AuthService(session).audit("consentimiento.borrar", usuario_id=user.usuario_id, centro_id=centro_id,
                               recurso=f"consentimiento:{cid}", detalle=snap,
                               ip=request.client.host if request.client else None)
    return {"ok": True}


# ─────────────────── Desde Inicio: leer, imprimir, enviar y saber si la cita lo pide ───────────────────
def _del_centro(session: Session, centro_id: int, cid: int) -> Consentimiento:
    c = session.get(Consentimiento, cid)
    if not c or c.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consentimiento no encontrado")
    return c


@router.get("/requerido")
def requerido(cita_id: int = Query(...),
              centro_id: int = Depends(get_current_centro),
              user: CurrentUser = Depends(require_permission("pacientes.ver")),
              session: Session = Depends(get_session)) -> dict:
    """Si el tipo de la cita requiere consentimiento y si el paciente ya lo tiene firmado y vigente."""
    cita = session.get(Cita, cita_id)
    if not cita or cita.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cita no encontrada")
    return {"requerido": consvc.requerido_para_cita(session, cita)}


@router.get("/firma-profesional")
def firma_profesional(colaborador_id: Optional[int] = Query(None),
                      centro_id: int = Depends(get_current_centro),
                      user: CurrentUser = Depends(require_permission("pacientes.ver")),
                      session: Session = Depends(get_session)) -> dict:
    """Con qué firma profesional saldría el consentimiento para ese doctor."""
    return {"tipo": consvc.firma_profesional(session, centro_id, colaborador_id)}


@router.get("/{cid}/pdf")
def ver_pdf(cid: int,
            centro_id: int = Depends(get_current_centro),
            user: CurrentUser = Depends(require_permission("pacientes.ver")),
            session: Session = Depends(get_session)):
    """El PDF (para leerlo antes de firmar o imprimirlo), con la firma si ya está firmado."""
    c = _del_centro(session, centro_id, cid)
    pdf = _OUT_DIR / f"consent_{c.id}.pdf"
    if not pdf.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PDF del consentimiento no encontrado")
    return FileResponse(str(pdf), media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="consentimiento_{c.id}.pdf"'})


@router.get("/{cid}/paginas")
def paginas(cid: int,
            centro_id: int = Depends(get_current_centro),
            user: CurrentUser = Depends(require_permission("pacientes.ver")),
            session: Session = Depends(get_session)) -> dict:
    """Nº de páginas del consentimiento (para leerlo página a página en cualquier pantalla)."""
    c = _del_centro(session, centro_id, cid)
    pdf = _OUT_DIR / f"consent_{c.id}.pdf"
    if not pdf.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PDF del consentimiento no encontrado")
    with fitz.open(str(pdf)) as doc:
        return {"paginas": doc.page_count}


@router.get("/{cid}/pagina/{n}")
def pagina(cid: int, n: int,
           centro_id: int = Depends(get_current_centro),
           user: CurrentUser = Depends(require_permission("pacientes.ver")),
           session: Session = Depends(get_session)):
    """Una página como imagen PNG. Se lee igual en un PC, una tableta o un móvil (un PDF dentro
    de la página no: en iPad solo enseña la primera hoja, y sin visor no enseña nada)."""
    c = _del_centro(session, centro_id, cid)
    pdf = _OUT_DIR / f"consent_{c.id}.pdf"
    if not pdf.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PDF del consentimiento no encontrado")
    with fitz.open(str(pdf)) as doc:
        if n < 1 or n > doc.page_count:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Página no encontrada")
        png = doc[n - 1].get_pixmap(dpi=110).tobytes("png")
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/{cid}/enviar")
def enviar(cid: int, request: Request,
           centro_id: int = Depends(get_current_centro),
           user: CurrentUser = Depends(require_permission("pacientes.editar")),
           session: Session = Depends(get_session)) -> dict:
    """Envía al móvil del paciente el PDF y, si está pendiente, el enlace para firmarlo en su móvil."""
    from application.services.comunicacion_service import ComunicacionService
    from domain.config.settings import settings
    c = _del_centro(session, centro_id, cid)
    pac = session.get(Paciente, c.paciente_id)
    telefono = (pac.telefono_movil if pac else None)
    if not telefono:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El paciente no tiene móvil")
    pdf = _OUT_DIR / f"consent_{c.id}.pdf"
    if not pdf.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PDF del consentimiento no encontrado")
    svc = ComunicacionService(session)
    nombre = (pac.nombre or "").split(" ")[0]
    enlace = None
    try:
        svc.enviar_documento(centro_id, telefono, base64.b64encode(pdf.read_bytes()).decode(),
                             f"Consentimiento {c.tipo}.pdf",
                             f"Hola {nombre}, te enviamos tu consentimiento informado de {c.tipo}.")
        if c.estado != "firmado" and c.signing_code:
            # La dirección pública de la app es desde la que se está usando (Origin del navegador,
            # p.ej. https://app.rubiogarciadental.com); la configurada es solo el respaldo.
            origen = (request.headers.get("origin") or "").rstrip("/")
            base = origen if origen.startswith("https://") else settings.public_frontend_url.rstrip("/")
            enlace = f"{base}/firmar/{c.signing_code}"
            svc.enviar_texto(centro_id, telefono, f"Puedes leerlo y firmarlo con el dedo aquí:\n\n{enlace}")
    except Exception as e:  # raiz: Evolution caido / numero invalido -> se informa al llamador; el consentimiento no se pierde
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"WhatsApp no ha podido enviarlo: {e}")
    AuthService(session).audit("consentimiento.enviar", usuario_id=user.usuario_id, centro_id=centro_id,
                               recurso=f"consentimiento:{c.id}", ip=request.client.host if request.client else None,
                               detalle={"con_enlace": bool(enlace)})
    return {"ok": True, "enlace": enlace}
