"""CASOS ORTODONCIA — análisis cefalométrico, diagnóstico y plan de tratamiento.

Endpoints para doctor app (Flutter): crear caso, subir fotos/RX, guardar mediciones,
generar diagnóstico (LLM), crear plan de tratamiento.
"""
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import Session, select

from api.auth_deps import CurrentUser, get_current_centro, require_permission
from api.audit_helper import _audit
from api.paciente_helper import _get_paciente
from domain.services.telefono import normalizar as normalizar_telefono
from application.services.estudio_ortodoncia_pdf import informe_estudio_pdf
from domain.models.ortodoncia import CasoOrtodoncia, EstudioOrtodoncia, FotoOrtodoncia
from domain.models.core import Paciente

_MEDIA = Path(__file__).resolve().parent.parent / "media"


def _estudio_o_404(session: Session, centro_id: int, paciente_id: int, estudio_id: int) -> EstudioOrtodoncia:
    e = session.get(EstudioOrtodoncia, estudio_id)
    if not e or e.centro_id != centro_id or e.paciente_id != paciente_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Estudio no encontrado")
    return e


def _pdf_estudio(session: Session, centro_id: int, paciente_id: int, e: EstudioOrtodoncia) -> bytes:
    pac = _get_paciente(session, centro_id, paciente_id)
    fotos = session.exec(select(FotoOrtodoncia).where(FotoOrtodoncia.estudio_id == e.id)
                         .order_by(FotoOrtodoncia.id)).all()
    nombre = " ".join(x for x in [pac.nombre, pac.apellidos] if x) or "—"
    return informe_estudio_pdf(
        paciente=nombre, num_historia=pac.num_historia or "—", etapa=e.etapa,
        fecha=e.fecha.isoformat() if e.fecha else None,
        fotos=[{"tipo": f.tipo, "archivo": f.archivo} for f in fotos], media_dir=_MEDIA)
from infrastructure.config.db import get_session

router = APIRouter(prefix="/pacientes", tags=["ortodoncia · casos"])


class CasoOrtodonciaIn(BaseModel):
    aparato: Optional[str] = None
    fecha_inicio: date


class MedicionesIn(BaseModel):
    mediciones_json: dict  # {SNA, SNB, ANB, IMPA, FMA, ...}


class DiagnosticoIn(BaseModel):
    texto: str
    clase: str  # I, II, III
    patron: str  # hipodivergente, normohipso, hiperdivergente


class PlanIn(BaseModel):
    plan_json: dict  # {fases: [{num, descripcion, duracion_meses}]}


@router.get("/{paciente_id}/estudios-ortodoncia")
def listar_estudios_web(paciente_id: int,
                        centro_id: int = Depends(get_current_centro),
                        _user: CurrentUser = Depends(require_permission("pacientes.ver")),
                        session: Session = Depends(get_session)) -> dict:
    """Estudios fotográficos de ortodoncia del paciente con sus fotos (para la WEB). Las fotos se
    sirven por /media/{archivo} (mismo origen, cookie de sesión)."""
    _get_paciente(session, centro_id, paciente_id)
    ests = session.exec(
        select(EstudioOrtodoncia).where(EstudioOrtodoncia.centro_id == centro_id,
                                        EstudioOrtodoncia.paciente_id == paciente_id)
        .order_by(EstudioOrtodoncia.fecha.desc())).all()
    salida = []
    for e in ests:
        fotos = session.exec(select(FotoOrtodoncia).where(FotoOrtodoncia.estudio_id == e.id)
                             .order_by(FotoOrtodoncia.id)).all()
        salida.append({
            "id": e.id, "etapa": e.etapa, "estado": e.estado,
            "fecha": e.fecha.isoformat() if e.fecha else None, "notas": e.notas,
            "fotos": [{"id": f.tipo, "tipo": f.tipo, "url": f"/media/{f.archivo}",
                       "ancho": f.ancho, "alto": f.alto} for f in fotos],
        })
    return {"estudios": salida}


@router.get("/{paciente_id}/estudios-ortodoncia/{estudio_id}/informe.pdf")
def informe_estudio(paciente_id: int, estudio_id: int,
                    centro_id: int = Depends(get_current_centro),
                    _user: CurrentUser = Depends(require_permission("pacientes.ver")),
                    session: Session = Depends(get_session)) -> Response:
    """Informe del estudio (serie fotográfica) en PDF, para imprimir o adjuntar."""
    e = _estudio_o_404(session, centro_id, paciente_id, estudio_id)
    pdf = _pdf_estudio(session, centro_id, paciente_id, e)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="estudio_orto_{estudio_id}.pdf"'})


class EnviarEstudioIn(BaseModel):
    canal: str  # "whatsapp" | "email"


@router.post("/{paciente_id}/estudios-ortodoncia/{estudio_id}/enviar")
def enviar_estudio(paciente_id: int, estudio_id: int, datos: EnviarEstudioIn, request: Request,
                   centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission("pacientes.ver")),
                   session: Session = Depends(get_session)) -> dict:
    """Envía el PDF del estudio al paciente por WhatsApp (Evolution) o email. Requiere que el canal
    esté configurado/conectado; si no, devuelve un error claro."""
    e = _estudio_o_404(session, centro_id, paciente_id, estudio_id)
    pac = _get_paciente(session, centro_id, paciente_id)
    pdf = _pdf_estudio(session, centro_id, paciente_id, e)
    _audit(session, user, centro_id, "estudio.enviar", f"estudio:{estudio_id}:{datos.canal}", request)

    fichero = f"estudio_orto_{estudio_id}.pdf"
    if datos.canal == "whatsapp":
        if not pac.telefono_movil:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El paciente no tiene móvil")
        import base64
        from application.services.comunicacion_service import ComunicacionService
        num = normalizar_telefono(pac.telefono_movil)  # núcleo: 9 dígitos → 34…
        try:
            cli = ComunicacionService(session)._client(centro_id)  # noqa: SLF001
            cli.send_media(num, media=base64.b64encode(pdf).decode(), media_type="document",
                           mimetype="application/pdf", filename=fichero, caption="Tu estudio de ortodoncia")
        except Exception as exc:  # raiz: WhatsApp/Evolution caído -> 502
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"WhatsApp no disponible: {exc}")
        return {"ok": True, "canal": "whatsapp"}

    if datos.canal == "email":
        if not pac.email:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El paciente no tiene email")
        from infrastructure.external_apis import smtp_mailer
        from domain.models.config import Integracion
        ig = session.exec(select(Integracion).where(
            Integracion.centro_id == centro_id, Integracion.tipo == "email_saliente")).first()
        if not ig or not ig.config:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Email saliente no configurado en el centro")
        try:
            smtp_mailer.send_html(ig.config, to=pac.email, subject="Tu estudio de ortodoncia",
                                  html="<p>Adjuntamos tu estudio de ortodoncia.</p>",
                                  attachments=[{"filename": fichero, "content": pdf, "mimetype": "application/pdf"}])
        except Exception as exc:  # raiz: SMTP caído -> 502
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Email no disponible: {exc}")
        return {"ok": True, "canal": "email"}

    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Canal no soportado")


@router.post("/{paciente_id}/casos-ortodoncia", status_code=201)
def crear_caso_ortodoncia(paciente_id: int, data: CasoOrtodonciaIn, request: Request,
                         centro_id: int = Depends(get_current_centro),
                         user: CurrentUser = Depends(require_permission("pacientes.editar")),
                         session: Session = Depends(get_session)) -> dict:
    """Crea un nuevo caso de ortodoncia para un paciente."""
    _get_paciente(session, centro_id, paciente_id)

    caso = CasoOrtodoncia(
        centro_id=centro_id,
        paciente_id=paciente_id,
        colaborador_id=user.colaborador_id,
        aparato=data.aparato,
        estado="activo",
        fecha_inicio=data.fecha_inicio,
    )
    session.add(caso)
    session.commit()
    session.refresh(caso)
    _audit(session, user, centro_id, "casos.crear", f"caso:{caso.id}", request)
    return {"id": caso.id, "paciente_id": paciente_id}


@router.get("/{paciente_id}/casos-ortodoncia")
def listar_casos(paciente_id: int,
                centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(require_permission("pacientes.ver")),
                session: Session = Depends(get_session)) -> dict:
    """Lista casos de ortodoncia del paciente."""
    _get_paciente(session, centro_id, paciente_id)

    casos = session.exec(
        select(CasoOrtodoncia).where(
            CasoOrtodoncia.centro_id == centro_id,
            CasoOrtodoncia.paciente_id == paciente_id
        ).order_by(CasoOrtodoncia.fecha_inicio.desc())
    ).all()

    return {
        "casos": [{
            "id": c.id,
            "aparato": c.aparato,
            "estado": c.estado,
            "fecha_inicio": c.fecha_inicio.isoformat(),
            "fecha_fin_prevista": c.fecha_fin_prevista.isoformat() if c.fecha_fin_prevista else None,
            "tiene_mediciones": c.mediciones_json is not None,
            "tiene_diagnostico": c.diagnostico_texto is not None,
            "tiene_plan": c.plan_tratamiento_json is not None,
        } for c in casos]
    }


@router.put("/{paciente_id}/casos-ortodoncia/{caso_id}/mediciones")
def guardar_mediciones(paciente_id: int, caso_id: int, data: MedicionesIn, request: Request,
                      centro_id: int = Depends(get_current_centro),
                      user: CurrentUser = Depends(require_permission("pacientes.editar")),
                      session: Session = Depends(get_session)) -> dict:
    """Guarda mediciones cefalométricas del caso."""
    _get_paciente(session, centro_id, paciente_id)

    caso = session.get(CasoOrtodoncia, caso_id)
    if not caso or caso.centro_id != centro_id or caso.paciente_id != paciente_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Caso no encontrado")

    caso.mediciones_json = data.mediciones_json
    session.add(caso)
    session.commit()
    _audit(session, user, centro_id, "casos.mediciones", f"caso:{caso_id}", request)
    return {"id": caso_id, "guardado": True}


@router.put("/{paciente_id}/casos-ortodoncia/{caso_id}/diagnostico")
def guardar_diagnostico(paciente_id: int, caso_id: int, data: DiagnosticoIn, request: Request,
                       centro_id: int = Depends(get_current_centro),
                       user: CurrentUser = Depends(require_permission("pacientes.editar")),
                       session: Session = Depends(get_session)) -> dict:
    """Guarda diagnóstico ortodóntico."""
    _get_paciente(session, centro_id, paciente_id)

    caso = session.get(CasoOrtodoncia, caso_id)
    if not caso or caso.centro_id != centro_id or caso.paciente_id != paciente_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Caso no encontrado")

    caso.diagnostico_texto = data.texto
    caso.diagnostico_clase = data.clase
    caso.diagnostico_patron = data.patron
    session.add(caso)
    session.commit()
    _audit(session, user, centro_id, "casos.diagnostico", f"caso:{caso_id}", request)
    return {"id": caso_id, "guardado": True}


@router.put("/{paciente_id}/casos-ortodoncia/{caso_id}/plan")
def guardar_plan(paciente_id: int, caso_id: int, data: PlanIn, request: Request,
                centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(require_permission("pacientes.editar")),
                session: Session = Depends(get_session)) -> dict:
    """Guarda plan de tratamiento."""
    _get_paciente(session, centro_id, paciente_id)

    caso = session.get(CasoOrtodoncia, caso_id)
    if not caso or caso.centro_id != centro_id or caso.paciente_id != paciente_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Caso no encontrado")

    caso.plan_tratamiento_json = data.plan_json
    session.add(caso)
    session.commit()
    _audit(session, user, centro_id, "casos.plan", f"caso:{caso_id}", request)
    return {"id": caso_id, "guardado": True}


@router.get("/{paciente_id}/casos-ortodoncia/{caso_id}")
def obtener_caso(paciente_id: int, caso_id: int,
                centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(require_permission("pacientes.ver")),
                session: Session = Depends(get_session)) -> dict:
    """Obtiene detalle completo del caso."""
    _get_paciente(session, centro_id, paciente_id)

    caso = session.get(CasoOrtodoncia, caso_id)
    if not caso or caso.centro_id != centro_id or caso.paciente_id != paciente_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Caso no encontrado")

    return {
        "id": caso.id,
        "paciente_id": caso.paciente_id,
        "aparato": caso.aparato,
        "estado": caso.estado,
        "fecha_inicio": caso.fecha_inicio.isoformat(),
        "fecha_fin_prevista": caso.fecha_fin_prevista.isoformat() if caso.fecha_fin_prevista else None,
        "mediciones": caso.mediciones_json,
        "diagnostico": {
            "texto": caso.diagnostico_texto,
            "clase": caso.diagnostico_clase,
            "patron": caso.diagnostico_patron,
        } if caso.diagnostico_texto else None,
        "plan": caso.plan_tratamiento_json,
    }
