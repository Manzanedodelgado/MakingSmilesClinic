"""DOCUMENTOS DEL PACIENTE — generación genérica (capa de interfaz). Solo BBDD nueva.

Sirve los datos para imprimir / enviar por WhatsApp CUALQUIER documento del catálogo
(factura, recibo, justificante, presupuesto, historia, receta, consentimiento,
primera visita) con la PLANTILLA configurada en Config › Admin › Documentos +
cabecera de la clínica + identidad del paciente. El render (HTML) lo hace el front con
el mismo motor (renderDoc) que la pantalla de configuración → un único documento.

El presupuesto «rico» (líneas + odontograma) sigue teniendo su flujo propio en la
pestaña Presupuestos; aquí el presupuesto se genera como plantilla con la cabecera.
"""
import base64
import logging
import html as _htmlmod
import mimetypes
import os
from datetime import date, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel
from sqlmodel import Session, select

from api.auth_deps import CurrentUser, get_current_centro, require_permission
from api.paciente_helper import _get_paciente
from application.services.auth_service import AuthService
from api.audit_helper import _audit
from application.services.comunicacion_service import ComunicacionService
from application.services.config_service import ConfigService
from domain.models.core import Centro, Colaborador, Paciente, RazonSocial
from domain.models.economico import TratamientoRealizado
from domain.models.documentos import DocumentoAdmin, DocumentoPaciente
from domain.models.identidad import Usuario
from infrastructure.config.db import get_session
from infrastructure.external_apis.evolution_api import EvolutionError
from infrastructure.external_apis.documento_plantilla_pdf import html_a_pdf, render_plantilla

router = APIRouter(prefix="/pacientes", tags=["pacientes · documentos"])

logger = logging.getLogger(__name__)

# Tipos del catálogo que admite el generador genérico (deben coincidir con DOC_DEFAULTS del front).
TIPOS = {"factura", "recibo", "justificante", "presupuesto", "historia",
         "receta", "consentimiento", "primeraVisita"}

_MESES = ("", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def _fecha_larga(d: date) -> str:
    return f"{d.day} de {_MESES[d.month]} de {d.year}"


def _data_url(url: Optional[str]) -> Optional[str]:
    """Fichero de /media → data URL base64 (documento autónomo: sirve para imprimir y PDF)."""
    if not url:
        return None
    try:
        p = Path(__file__).resolve().parents[1] / url.lstrip("/")
        if not p.exists():
            return None
        mt = mimetypes.guess_type(p.name)[0] or "image/png"
        return f"data:{mt};base64," + base64.b64encode(p.read_bytes()).decode()
    except Exception:  # raiz: archivo local ilegible -> None; el documento sale sin ese adjunto
        return None


def _clinic(session: Session, centro_id: int) -> dict:
    centro = session.get(Centro, centro_id)
    razon = session.exec(select(RazonSocial).where(RazonSocial.centro_id == centro_id)).first()
    return {
        "nombre": centro.nombre if centro else "",
        "fiscal": f"{razon.nombre}{' · ' + razon.cif if razon and razon.cif else ''}" if razon else "",
        "dir": ", ".join(x for x in [centro.direccion, centro.cp, centro.poblacion, centro.provincia] if x) if centro else "",
        "tel": " · ".join(x for x in [centro.telefono, centro.telefono_movil] if x) if centro else "",
        "email": centro.email if centro else "",
        "web": centro.web if centro else "",
        "logo_url": centro.logo_url if centro else None,
        "sello_url": razon.sello_url if razon else None,
        "logo_data": _data_url(centro.logo_url if centro else None),
        "sello_data": _data_url(razon.sello_url if razon else None),
    }


def _datos_paciente(pac: Paciente) -> dict:
    hoy = date.today()
    nombre = f"{pac.nombre or ''} {pac.apellidos or ''}".strip()
    info = " · ".join(x for x in [f"Hª {pac.num_historia}" if pac.num_historia else "",
                                  f"NIF {pac.nif}" if pac.nif else ""] if x)
    return {
        "paciente": nombre or "—",
        "pacienteInfo": info,
        "nif": pac.nif or "",
        "fechaNac": pac.fecha_nacimiento.strftime("%d/%m/%Y") if pac.fecha_nacimiento else "",
        "numPaciente": str(pac.num_historia or ""),
        "numHistoria": str(pac.num_historia or ""),
        "telefono": pac.telefono_movil or pac.telefono_fijo or "",
        "email": pac.email or "",
        "direccion": pac.direccion or "",
        "fecha": hoy.strftime("%d/%m/%Y"),
        "fechaLarga": _fecha_larga(hoy),
        "validezFecha": (hoy + timedelta(days=90)).strftime("%d/%m/%Y"),
        # Campos que algunas plantillas usan; se dejan vacíos para rellenar a mano si no hay dato.
        "doctor": "", "numColegiado": "", "horaIni": "", "horaFin": "", "numero": "",
        "alergias": "", "piezas": "", "tratamiento": "",
    }


@router.get("/{paciente_id}/documento/{tipo}")
def documento(paciente_id: int, tipo: str,
              centro_id: int = Depends(get_current_centro),
              user: CurrentUser = Depends(require_permission("pacientes.ver")),
              session: Session = Depends(get_session)) -> dict:
    """Datos para imprimir/enviar un documento del catálogo con la plantilla configurada."""
    if tipo not in TIPOS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tipo de documento no válido")
    pac = _get_paciente(session, centro_id, paciente_id)
    plantillas = ConfigService(session).resolve("documentos.plantillas", centro_id=centro_id, default={}) or {}
    clinic = _clinic(session, centro_id)
    datos = _datos_paciente(pac)
    _firmar_como_profesional(session, datos, user.usuario_id, sello_url=clinic.get("sello_url"))
    return {
        "plantilla": plantillas.get(tipo),    # None → el front usa la plantilla por defecto
        "clinic": clinic,
        "datos": datos,
    }


def _firmar_como_profesional(session: Session, datos: dict, usuario_id: Optional[int],
                             sello_url: Optional[str] = None) -> None:
    """El profesional que GENERA el documento lo firma con la firma que tenga subida en
    Config → Colaboradores (regla del usuario: cada documento con firma de doctor plasma la
    del colaborador). La firma va como `datos.firma` = <img> para SUPERPONERSE encima del texto
    (cuño de tinta), sin alterar la maqueta. Rellena también prescriptor/colegiado.
    Mientras no haya firma subida, se estampa el SELLO del centro (fallback)."""
    if usuario_id:
        usu = session.get(Usuario, usuario_id)
        col = session.get(Colaborador, usuario_id)            # colaborador.id == usuario.id
        if usu:
            nombre = f"{usu.nombre or ''} {usu.apellidos or ''}".strip()
            if nombre:
                datos["doctor"] = datos.get("doctor") or nombre
                datos["prescriptor"] = datos.get("prescriptor") or nombre
        if col:
            if col.num_colegiado:
                datos["numColegiado"] = datos.get("numColegiado") or col.num_colegiado
            firma = _cuno_data_url(col.firma_url)
            if firma:
                datos["firma"] = _img_cuno(firma)
    # Sin firma del colaborador → sello del centro (de momento).
    if not datos.get("firma") and sello_url:
        cuno = _cuno_data_url(sello_url)
        if cuno:
            datos["firma"] = _img_cuno(cuno)


def _cuno_data_url(url: Optional[str]) -> Optional[str]:
    """Data-URL PNG de una firma/sello con el fondo BLANCO hecho TRANSPARENTE (alfa 0 en los
    píxeles casi-blancos). Transparencia de VERDAD → el cuño no tapa el texto y funciona en
    pantalla, impresión y PDF (mix-blend-mode fallaba al imprimir)."""
    if not url:
        return None
    try:
        p = Path(__file__).resolve().parents[1] / url.lstrip("/")
        if not p.exists():
            return None
        from PIL import Image
        import io
        im = Image.open(p).convert("RGBA")
        im.putdata([(r, g, b, 0) if min(r, g, b) > 235 else (r, g, b, a)
                    for (r, g, b, a) in im.getdata()])
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:  # raiz: sin firma -> el documento sale sin cuño, no rompe
        return None


def _img_cuno(src: str) -> str:
    """<img> del cuño ya transparente, superpuesto sobre el texto (la plantilla lo posiciona)."""
    return f'<img src="{src}" style="max-height:100%;max-width:100%">'


class EnviarWhatsappIn(BaseModel):
    pdf_base64: str
    filename: Optional[str] = None
    caption: Optional[str] = None


@router.post("/{paciente_id}/documento/{tipo}/enviar-whatsapp")
def enviar_whatsapp(paciente_id: int, tipo: str, data: EnviarWhatsappIn, request: Request,
                    centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(require_permission("pacientes.editar")),
                    session: Session = Depends(get_session)) -> dict:
    """Envía el PDF del documento (generado en cliente con la plantilla) por WhatsApp al
    móvil del paciente."""
    if tipo not in TIPOS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tipo de documento no válido")
    pac = _get_paciente(session, centro_id, paciente_id)
    telefono = pac.telefono_movil or pac.telefono_fijo
    if not telefono:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El paciente no tiene teléfono")
    b64 = data.pdf_base64.split(",", 1)[1] if "," in data.pdf_base64 else data.pdf_base64
    filename = data.filename or f"{tipo}.pdf"
    caption = data.caption or "Le enviamos el documento solicitado."
    try:
        res = ComunicacionService(session).enviar_documento(centro_id, telefono, b64, filename, caption)
    except EvolutionError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"WhatsApp no disponible: {e}")
    _audit(session, user, centro_id, "documento.enviar_whatsapp", f"paciente:{paciente_id}/{tipo}", request)
    return {"enviado": True, "messageId": res.get("messageId")}


# ─────────────────── ARCHIVO DE DOCUMENTOS (subir / listar / borrar por tipo) ───────────────────
# Cada documento (subido o generado) se guarda en `documentos_paciente` con tipo_doc = categoría,
# y el fichero en media/documentos_paciente/ (servido por /media). El histórico se lista por tipo.
_DOCS_MEDIA = Path(__file__).resolve().parents[1] / "media" / "documentos_paciente"
_MAX_BYTES = 15 * 1024 * 1024   # 15 MB
_EXT_OK = {"pdf", "jpg", "jpeg", "png", "webp", "gif", "doc", "docx", "odt", "xls", "xlsx"}


def _doc_dto(d: DocumentoPaciente) -> dict:
    return {"id": d.id, "tipo": d.tipo_doc, "descripcion": d.descripcion, "archivo_url": d.archivo_url,
            "factura_origen_id": d.factura_origen_id, "motivo_rectificacion": d.motivo_rectificacion,
            "fecha": (d.fecha.isoformat() if d.fecha else (d.created_at.date().isoformat() if d.created_at else None))}


@router.get("/{paciente_id}/documentos/facturas-vinculadas")
def facturas_vinculadas(paciente_id: int,
                         centro_id: int = Depends(get_current_centro),
                         user: CurrentUser = Depends(require_permission("pacientes.ver")),
                         session: Session = Depends(get_session)) -> list[dict]:
    """Facturas asociadas a actos de este paciente, para gestionarlas desde su ficha."""
    _get_paciente(session, centro_id, paciente_id)
    actos = session.exec(select(TratamientoRealizado).where(
        TratamientoRealizado.centro_id == centro_id,
        TratamientoRealizado.paciente_id == paciente_id,
        TratamientoRealizado.num_factura_e.is_not(None),
    )).all()
    docs = session.exec(select(DocumentoAdmin).where(
        DocumentoAdmin.centro_id == centro_id, DocumentoAdmin.num_doc.is_not(None)
    )).all()
    by_number: dict[str, list[DocumentoAdmin]] = {}
    for d in docs:
        by_number.setdefault(f"{d.serie or ''}{d.num_doc}", []).append(d)
    facturas: dict[int, DocumentoAdmin] = {}
    pendientes: dict[tuple[str, str], dict] = {}
    for acto in actos:
        numero = (acto.num_factura_e or "").strip()
        if not numero:
            continue
        doc = next((d for d in docs if d.id == acto.factura_documento_id), None) if acto.factura_documento_id else None
        if doc:
            facturas[doc.id] = doc
            continue
        matches = by_number.get(numero, [])
        if len(matches) == 1:
            facturas[matches[0].id] = matches[0]
        else:
            key = (numero, "ambiguo" if len(matches) > 1 else "sin_registro")
            pendientes[key] = {"numero": numero, "factura_id": None,
                               "estado": "referencia_ambigua" if len(matches) > 1 else "sin_registro",
                               "verifactu": False}
    result = list(pendientes.values())
    for doc in facturas.values():
        rect = session.exec(select(DocumentoPaciente).where(
            DocumentoPaciente.factura_origen_id == doc.id).order_by(DocumentoPaciente.id.desc())).first()
        numero = f"{doc.serie or ''}{doc.num_doc}"
        tiene_rectificativa = bool(rect and rect.archivo_url)
        result.append({"numero": numero, "factura_id": doc.id,
                       "fecha": doc.fecha.isoformat() if doc.fecha else None,
                       "estado": "rectificada" if doc.anulada and tiene_rectificativa else ("anulada_sin_rectificativa" if doc.anulada else "emitida"),
                       "verifactu": bool(doc.hash_factura),
                       "rectificativa_documento_id": rect.id if rect else None,
                       "rectificativa_url": rect.archivo_url if rect else None,
                       "rectificativa_descripcion": rect.descripcion if rect else None})
    return sorted(result, key=lambda f: (f.get("fecha") or "", f["numero"]))

@router.post("/{paciente_id}/documentos/rectificar-factura")
async def rectificar_factura_paciente(paciente_id: int, request: Request,
                                      factura_id: int = Form(...), motivo: str = Form(...),
                                      file: UploadFile = File(...),
                                      centro_id: int = Depends(get_current_centro),
                                      user: CurrentUser = Depends(require_permission("pacientes.editar")),
                                      session: Session = Depends(get_session)) -> dict:
    """Archiva la rectificativa ya emitida y enlaza/anula la factura desde Pacientes.

    No emite el documento fiscal: exige subir el PDF rectificativo emitido por el sistema
    de facturación. Las facturas con hash VeriFactu requieren su flujo fiscal específico.
    """
    _get_paciente(session, centro_id, paciente_id)
    motivo = (motivo or "").strip()
    if not motivo or len(motivo) > 500:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Indica el motivo de la rectificación (máx. 500 caracteres)")
    factura = session.exec(select(DocumentoAdmin).where(
        DocumentoAdmin.id == factura_id, DocumentoAdmin.centro_id == centro_id
    ).with_for_update()).first()
    if not factura or factura.num_doc is None or factura.tipo_documento != "factura":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Factura no encontrada")
    numero = f"{factura.serie or ''}{factura.num_doc}"
    actos = session.exec(select(TratamientoRealizado).where(
        TratamientoRealizado.centro_id == centro_id, TratamientoRealizado.paciente_id == paciente_id,
        TratamientoRealizado.num_factura_e == numero)).all()
    linked = [a for a in actos if a.factura_documento_id == factura.id]
    if not linked:
        docs_mismo_numero = session.exec(select(DocumentoAdmin).where(
            DocumentoAdmin.centro_id == centro_id, DocumentoAdmin.num_doc.is_not(None)
        )).all()
        coincidentes = [d for d in docs_mismo_numero if f"{d.serie or ''}{d.num_doc}" == numero]
        if len(coincidentes) == 1 and coincidentes[0].id == factura.id:
            linked = actos
    if not linked:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La factura no está vinculada de forma inequívoca a actos de este paciente")
    existente = session.exec(select(DocumentoPaciente.id).where(
        DocumentoPaciente.factura_origen_id == factura.id).limit(1)).first()
    if existente:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una rectificativa archivada para esta factura")
    if factura.anulada:
        raise HTTPException(status.HTTP_409_CONFLICT, "La factura ya figura anulada")
    if factura.hash_factura:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta factura tiene registro VeriFactu; debe rectificarse en el sistema fiscal antes de archivarla aquí")
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext != "pdf":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La rectificativa debe adjuntarse en PDF")
    contenido = await file.read()
    if not contenido or len(contenido) > _MAX_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El PDF está vacío o supera 15 MB")
    if not contenido.lstrip()[:5] == b"%PDF-":   # la extensión la pone quien sube; el contenido no miente
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El fichero no es un PDF")
    d = DocumentoPaciente(paciente_id=paciente_id, tipo_doc="Facturas", fecha=date.today(),
                          descripcion=f"Rectificativa de {numero}", usuario_id=user.usuario_id,
                          factura_origen_id=factura.id, motivo_rectificacion=motivo)
    session.add(d)
    session.flush()
    _DOCS_MEDIA.mkdir(parents=True, exist_ok=True)
    nombre = f"doc_{d.id}.pdf"
    path = _DOCS_MEDIA / nombre
    try:
        path.write_bytes(contenido)
        d.archivo_url = f"/media/documentos_paciente/{nombre}"
        factura.anulada = True
        session.add(d)
        session.add(factura)
        session.commit()
    except Exception:  # raiz: fallo al anular: rollback + borrado del PDF temporal; nunca deja estado a medias
        session.rollback()
        path.unlink(missing_ok=True)
        raise
    session.refresh(d)
    _audit(session, user, centro_id, "documento.rectificar_factura", f"factura:{numero}", request,
           detalle={"paciente_id": paciente_id, "documento_id": d.id, "motivo": motivo})
    return _doc_dto(d)


@router.get("/{paciente_id}/documentos")
def listar_documentos(paciente_id: int, tipo: Optional[str] = None,
                      centro_id: int = Depends(get_current_centro),
                      user: CurrentUser = Depends(require_permission("pacientes.ver")),
                      session: Session = Depends(get_session)) -> list[dict]:
    """Histórico de documentos archivados del paciente (opcionalmente filtrado por tipo)."""
    _get_paciente(session, centro_id, paciente_id)
    q = select(DocumentoPaciente).where(DocumentoPaciente.paciente_id == paciente_id)
    if tipo and tipo != "Todos":
        q = q.where(DocumentoPaciente.tipo_doc == tipo)
    rows = session.exec(q.order_by(DocumentoPaciente.id.desc())).all()
    return [_doc_dto(d) for d in rows]


@router.post("/{paciente_id}/documentos")
async def subir_documento(paciente_id: int, request: Request,
                          tipo: str = Form(...), descripcion: str = Form(""),
                          file: UploadFile = File(...),
                          centro_id: int = Depends(get_current_centro),
                          user: CurrentUser = Depends(require_permission("pacientes.editar")),
                          session: Session = Depends(get_session)) -> dict:
    """Archiva un fichero (subido o el PDF generado) bajo la categoría `tipo`."""
    _get_paciente(session, centro_id, paciente_id)
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext not in _EXT_OK:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Tipo de fichero no permitido (.{ext})")
    contenido = await file.read()
    if not contenido:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Fichero vacío")
    if len(contenido) > _MAX_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El fichero supera 15 MB")

    d = DocumentoPaciente(paciente_id=paciente_id, tipo_doc=tipo, fecha=date.today(),
                          descripcion=(descripcion or file.filename or "Documento")[:300],
                          usuario_id=user.usuario_id)
    session.add(d)
    session.commit()
    session.refresh(d)

    _DOCS_MEDIA.mkdir(parents=True, exist_ok=True)
    nombre = f"doc_{d.id}.{ext}"
    (_DOCS_MEDIA / nombre).write_bytes(contenido)
    d.archivo_url = f"/media/documentos_paciente/{nombre}"
    session.add(d)
    session.commit()

    _audit(session, user, centro_id, "documento.archivar", f"documento:{d.id}", request,
          detalle={"paciente_id": paciente_id, "tipo": tipo, "descripcion": d.descripcion,
                    "archivo_url": d.archivo_url})
    return _doc_dto(d)


@router.delete("/{paciente_id}/documentos/{doc_id}")
def borrar_documento(paciente_id: int, doc_id: int, request: Request,
                     centro_id: int = Depends(get_current_centro),
                     user: CurrentUser = Depends(require_permission("pacientes.editar")),
                     session: Session = Depends(get_session)) -> dict:
    _get_paciente(session, centro_id, paciente_id)
    d = session.get(DocumentoPaciente, doc_id)
    if not d or d.paciente_id != paciente_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado")
    if d.factura_origen_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No se puede borrar una rectificativa enlazada a una factura")
    snap = {"paciente_id": paciente_id, "tipo": d.tipo_doc, "descripcion": d.descripcion,
            "archivo_url": d.archivo_url}
    if d.archivo_url:
        try:
            (_DOCS_MEDIA / Path(d.archivo_url).name).unlink(missing_ok=True)
        except OSError:
            logger.warning("documentos: fichero huérfano en disco (%s)", d.archivo_url, exc_info=True)
    session.delete(d)
    session.commit()
    _audit(session, user, centro_id, "documento.borrar", f"documento:{doc_id}", request, snap)
    return {"ok": True}


# ─────────────── Generar documento en PDF (servidor, con la plantilla del centro) ───────────────
class GenerarDocIn(BaseModel):
    tipo: str
    datos: Optional[dict] = None       # valores extra que aporte el cliente (sobrescriben los del paciente)
    html: Optional[str] = None         # HTML ya renderizado por el cliente (render pixel-perfect opcional)


@router.post("/{paciente_id}/documentos/generar")
def generar_documento(paciente_id: int, body: GenerarDocIn, request: Request,
                      centro_id: int = Depends(get_current_centro),
                      user: CurrentUser = Depends(require_permission("pacientes.ver")),
                      session: Session = Depends(get_session)):
    """Devuelve el PDF del documento `tipo` del paciente.

    Usa LA MISMA plantilla que el centro tiene configurada (Config › Admin ·
    `documentos.plantillas`), con su firma y su sello — no un PDF genérico. Si el cliente
    manda `html` ya renderizado, se respeta ese (render del navegador); si no, se rellena
    la plantilla en servidor. Así el documento sale igual se pida desde donde se pida.
    """
    if body.tipo not in TIPOS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tipo de documento no válido")
    pac = _get_paciente(session, centro_id, paciente_id)
    plantillas = ConfigService(session).resolve("documentos.plantillas", centro_id=centro_id, default={}) or {}
    plantilla = plantillas.get(body.tipo) or {}
    clinic = _clinic(session, centro_id)
    datos = _datos_paciente(pac)
    _firmar_como_profesional(session, datos, user.usuario_id, sello_url=clinic.get("sello_url"))
    if body.datos:
        datos.update({k: v for k, v in body.datos.items() if v is not None})
    # Cabecera de clínica: mismas claves que `clinicKeys()` en el front (docBase.ts).
    logo = clinic.get("logo_data") or clinic.get("logo_url") or ""
    sello = clinic.get("sello_data") or clinic.get("sello_url") or ""
    datos.update({
        "clinicName": clinic.get("nombre") or "", "clinicFiscal": clinic.get("fiscal") or "",
        "clinicDir": clinic.get("dir") or "", "clinicTel": clinic.get("tel") or "",
        "clinicEmail": clinic.get("email") or "",
        "clinicWeb": f"<br>{_html_escape(clinic.get('web'))}" if clinic.get("web") else "",
        "clinicLogo": f'<img src="{_html_escape(logo)}" style="height:36px;vertical-align:middle;margin-right:10px">' if logo else "",
        "sello": f'<img src="{_html_escape(sello)}" style="height:64px;opacity:.9">' if sello else "",
    })

    if body.html:
        documento_html = body.html                      # el cliente ya lo renderizó con su plantilla
    else:
        html_plantilla = plantilla.get("html")
        if not html_plantilla:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"El centro no tiene plantilla configurada para '{body.tipo}'")
        documento_html = render_plantilla(html_plantilla, plantilla.get("campos") or {}, datos)

    with NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf_path = Path(tmp.name)
    try:
        html_a_pdf(documento_html, pdf_path)
    except Exception as e:  # raiz: plantilla con CSS que fitz no digiere -> 422 explicito, nunca 500 crudo
        os.unlink(pdf_path)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"No se pudo componer el PDF de la plantilla: {e}")
    _audit(session, user, centro_id, "documentos.generar", f"paciente:{paciente_id}/{body.tipo}", request,
          detalle={"paciente_id": paciente_id, "tipo": body.tipo, "datos": body.datos,
                    "html_personalizado": bool(body.html)})
    return FileResponse(str(pdf_path), media_type="application/pdf",
                        filename=f"{body.tipo}_{pac.num_historia or paciente_id}.pdf",
                        background=BackgroundTask(os.unlink, str(pdf_path)))


def _html_escape(v) -> str:
    return _htmlmod.escape(str(v or ""), quote=True)
