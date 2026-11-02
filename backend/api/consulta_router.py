"""CONSULTA VIVA — cerebro del flujo: enruta una evidencia hablada al mapa de incógnitas (LLM).

Lectura/escritura: pacientes.editar. Si el LLM no está disponible, responde 503 y el frontend
cae a su enrutador heurístico local (nunca bloquea la consulta).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session, select

from api.audit_helper import _audit
from api.auth_deps import CurrentUser, get_current_centro, require_permission
from api.paciente_helper import _get_paciente
from application.services import consulta_service
from application.services.config_service import ConfigService
from domain.models.documentos import RecetaFrecuente, RecomendacionPaciente
from domain.config.recomendaciones import RECOMENDACIONES_CATALOGO
from infrastructure.config.db import get_session
from infrastructure.external_apis.llm_client import LLMError

router = APIRouter(prefix="/pacientes", tags=["pacientes · consulta"])


class IncognitaIn(BaseModel):
    id: str
    pregunta: str
    pieza: Optional[str] = None
    confianza: int = 0
    propuesta: Optional[str] = None


class AnalizarIn(BaseModel):
    evidencia: str
    incognitas: list[IncognitaIn] = []


@router.post("/{paciente_id}/consulta/analizar")
def analizar_evidencia(
    paciente_id: int,
    data: AnalizarIn,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("pacientes.editar")),
    session: Session = Depends(get_session),
) -> dict:
    if not data.evidencia.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "evidencia vacía")
    try:
        return consulta_service.analizar(
            session, centro_id, data.evidencia.strip(),
            [i.model_dump() for i in data.incognitas],
        )
    except LLMError as exc:
        # 503 → el frontend usa su heurístico de respaldo
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except Exception as exc:  # noqa: BLE001 — nunca 500: la consulta no se bloquea por el copiloto
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"consulta: {exc}")


class TratamientoCierre(BaseModel):
    texto: str
    pieza: Optional[str] = None
    precio: Optional[float] = None


class CerrarIn(BaseModel):
    nota: Optional[str] = None
    tratamientos: list[TratamientoCierre] = []


@router.post("/{paciente_id}/consulta/cerrar", status_code=201)
def cerrar_visita(
    paciente_id: int,
    data: CerrarIn,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("pacientes.editar")),
    session: Session = Depends(get_session),
) -> dict:
    try:
        return consulta_service.cerrar(
            session, centro_id, user.usuario_id, paciente_id,
            [t.model_dump() for t in data.tratamientos],
            (data.nota or "").strip() or None,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


# ─────────────────────────── ESCUCHA ACTIVA (Caminos 2 y 3) ───────────────────────────


class EscuchaIn(BaseModel):
    texto: str


@router.post("/{paciente_id}/consulta/escucha")
def escucha_activa(
    paciente_id: int,
    data: EscuchaIn,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("pacientes.editar")),
    session: Session = Depends(get_session),
) -> dict:
    if not data.texto.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "texto vacío")
    # Escucha activa = las capacidades de VICTOR "transcribir_consulta" + "extraer_soap"
    # (catálogo en domain/config/agentes.py). Antes esta función no pasaba por ningún
    # interruptor: apagar a Victor en Config·Agentes IA no la afectaba en nada.
    from application.services.agentes_config import capacidad_activa
    if not capacidad_activa(session, centro_id, "victor", "transcribir_consulta"):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                             "La escucha activa está desactivada para Victor en este centro.")
    try:
        return consulta_service.escuchar_visita(
            session, centro_id, paciente_id, data.texto.strip()
        )
    except LLMError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"escucha: {exc}")


class SoapIn(BaseModel):
    subjetivo: Optional[str] = None
    objetivo: Optional[str] = None
    analisis: Optional[str] = None
    plan: Optional[str] = None


@router.post("/{paciente_id}/consulta/soap", status_code=201)
def guardar_soap(
    paciente_id: int,
    data: SoapIn,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("pacientes.editar")),
    session: Session = Depends(get_session),
) -> dict:
    try:
        return consulta_service.guardar_soap(
            session, centro_id, paciente_id, data.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"soap: {exc}")


class RecetaLinea(BaseModel):
    medicamento: str
    posologia: Optional[str] = None
    pauta: Optional[str] = None
    duracion: Optional[str] = None
    envases: Optional[int] = None
    unidades: Optional[int] = None


class RecetaIn(BaseModel):
    medicamentos: list[RecetaLinea] = []
    diagnostico: Optional[str] = None
    instrucciones: Optional[str] = None
    urgencia: bool = False
    desabastecimiento: bool = False
    motivo_sustitucion: Optional[str] = None


@router.post("/{paciente_id}/consulta/receta", status_code=201)
def guardar_receta(
    paciente_id: int,
    data: RecetaIn,
    request: Request,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("pacientes.editar")),
    session: Session = Depends(get_session),
) -> dict:
    if not data.medicamentos:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "receta sin medicamentos")
    try:
        res = consulta_service.guardar_receta(
            session, centro_id, user.usuario_id, paciente_id,
            [m.model_dump() for m in data.medicamentos],
            data.diagnostico, data.instrucciones, data.urgencia,
            data.desabastecimiento, data.motivo_sustitucion,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"receta: {exc}")
    _audit(session, user, centro_id, "recetas.crear", f"receta:{res['receta_id']}", request, {
        "paciente_id": paciente_id, "diagnostico": data.diagnostico,
        "medicamentos": [m.model_dump() for m in data.medicamentos],
        "instrucciones": data.instrucciones, "urgencia": data.urgencia,
        "desabastecimiento": data.desabastecimiento, "motivo_sustitucion": data.motivo_sustitucion,
    })
    return res


@router.get("/{paciente_id}/consulta/recetas-frecuentes")
def recetas_frecuentes(
    paciente_id: int,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("pacientes.editar")),
    session: Session = Depends(get_session),
) -> dict:
    """Lista recetas frecuentes del doctor (plantillas reutilizables)."""
    frecuentes = session.exec(
        select(RecetaFrecuente).where(
            RecetaFrecuente.centro_id == centro_id,
            RecetaFrecuente.colaborador_id == user.usuario_id,
            RecetaFrecuente.activo == True,
        ).order_by(RecetaFrecuente.nombre)
    ).all()

    return {
        "recetas_frecuentes": [
            {
                "id": rf.id,
                "nombre": rf.nombre,
                "medicamentos": rf.medicamentos or []
            }
            for rf in frecuentes
        ]
    }


class RecetaFrecuenteIn(BaseModel):
    nombre: str
    medicamentos: list[RecetaLinea] = []


@router.post("/{paciente_id}/consulta/recetas-frecuentes", status_code=201)
def crear_receta_frecuente(
    paciente_id: int,
    data: RecetaFrecuenteIn,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("pacientes.editar")),
    session: Session = Depends(get_session),
) -> dict:
    """Crear una nueva plantilla de receta frecuente."""
    if not data.nombre.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "nombre vacío")

    rf = RecetaFrecuente(
        centro_id=centro_id,
        colaborador_id=user.usuario_id,
        nombre=data.nombre.strip(),
        medicamentos=[m.model_dump() for m in data.medicamentos],
        activo=True,
    )
    session.add(rf)
    session.commit()
    session.refresh(rf)

    return {
        "ok": True,
        "id": rf.id,
        "nombre": rf.nombre,
        "medicamentos": rf.medicamentos or []
    }


@router.put("/{paciente_id}/consulta/recetas-frecuentes/{receta_id}")
def actualizar_receta_frecuente(
    paciente_id: int,
    receta_id: int,
    data: RecetaFrecuenteIn,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("pacientes.editar")),
    session: Session = Depends(get_session),
) -> dict:
    """Actualizar una plantilla de receta frecuente."""
    rf = session.get(RecetaFrecuente, receta_id)
    if not rf or rf.centro_id != centro_id or rf.colaborador_id != user.usuario_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Receta frecuente no encontrada")

    rf.nombre = data.nombre.strip()
    rf.medicamentos = [m.model_dump() for m in data.medicamentos]
    session.add(rf)
    session.commit()
    session.refresh(rf)

    return {
        "ok": True,
        "id": rf.id,
        "nombre": rf.nombre,
        "medicamentos": rf.medicamentos or []
    }


@router.delete("/{paciente_id}/consulta/recetas-frecuentes/{receta_id}")
def borrar_receta_frecuente(
    paciente_id: int,
    receta_id: int,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("pacientes.editar")),
    session: Session = Depends(get_session),
) -> dict:
    """Borrar una plantilla de receta frecuente (soft delete)."""
    rf = session.get(RecetaFrecuente, receta_id)
    if not rf or rf.centro_id != centro_id or rf.colaborador_id != user.usuario_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Receta frecuente no encontrada")

    rf.activo = False
    session.add(rf)
    session.commit()

    return {"ok": True}


# ─────────────────────────── RECOMENDACIONES ─────────────────────────────


@router.get("/{paciente_id}/consulta/camino")
def detectar_camino(
    paciente_id: int,
    cita_id: Optional[int] = None,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("pacientes.ver")),
    session: Session = Depends(get_session),
) -> dict:
    """Detecta qué tipo de consulta es (1: ejecución, 2: primera visita, 3: revisión)."""
    from sqlmodel import select
    from domain.models.core import Cita, Paciente

    p = session.get(Paciente, paciente_id)
    if not p or p.centro_id != centro_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Paciente {paciente_id} no encontrado")

    cita = None
    if cita_id:
        cita = session.get(Cita, cita_id)
        if cita and (cita.centro_id != centro_id or cita.paciente_id != paciente_id):
            cita = None
    else:
        # Buscar cita de hoy del paciente
        from datetime import date
        cita = session.exec(
            select(Cita).where(
                Cita.centro_id == centro_id,
                Cita.paciente_id == paciente_id,
                Cita.fecha == date.today(),
            ).order_by(Cita.id.desc())
        ).first()

    cita_confirmada = cita.confirmada if cita else False

    # ¿Paciente es nuevo? (sin citas previas o sin anamnesis)
    num_citas = session.exec(
        select(Cita).where(
            Cita.centro_id == centro_id,
            Cita.paciente_id == paciente_id,
        )
    ).all()
    es_nuevo = len(num_citas) <= 1  # Primera cita (o solo hoy)
    anamnesis_completa = bool(p.anamnesis)  # Array no vacío

    # ¿Tiene tratamientos previstos para hoy/esta cita?
    tiene_previstos = False
    if cita:
        # Los previstos se BORRAN al realizarse: si queda alguno, hay tratamiento por ejecutar.
        # (Antes: SQL crudo con "%s" + lista → ArgumentError en SQLAlchemy 2 → 500 siempre
        # que había cita, y la ficha caía a Escucha: el Camino 1 no se abría nunca.)
        # Sin modelo ORM para tratamientos_previstos: SQL parametrizado directo.
        tiene_previstos = session.connection().execute(
            text("SELECT 1 FROM tratamientos_previstos WHERE centro_id = :cid AND paciente_id = :pid LIMIT 1"),
            {"cid": centro_id, "pid": paciente_id},
        ).first() is not None

    # Lógica de detección: Camino 1 > Camino 2 > Camino 3
    if tiene_previstos:
        camino = 1
    elif es_nuevo:
        camino = 2
    else:
        camino = 3

    return {
        "camino": camino,
        "es_nuevo": es_nuevo,
        "anamnesis_completa": anamnesis_completa,
        "cita_confirmada": cita_confirmada,
        "tiene_previstos": tiene_previstos,
    }


@router.get("/recomendaciones/catalogo")
def catalogo_recomendaciones(
    centro_id: int = Depends(get_current_centro),
    session: Session = Depends(get_session),
) -> dict:
    """Catálogo de recomendaciones: mismo patrón que anamnesis (config-driven, editable por centro)."""
    catalogo = ConfigService(session).resolve(
        "clinica.recomendaciones", centro_id=centro_id, default=RECOMENDACIONES_CATALOGO
    )
    return {"secciones": catalogo.get("secciones", [])}


class RecomendacionesIn(BaseModel):
    items: list[str] = []  # claves seleccionadas del catálogo
    cita_id: Optional[int] = None


@router.post("/{paciente_id}/consulta/recomendaciones", status_code=201)
def guardar_recomendaciones(
    paciente_id: int,
    data: RecomendacionesIn,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("pacientes.editar")),
    session: Session = Depends(get_session),
) -> dict:
    """Guardar recomendaciones seleccionadas al final de la consulta."""
    p = _get_paciente(session, centro_id, paciente_id)

    # Cargar catálogo para generar texto
    catalogo = ConfigService(session).resolve(
        "clinica.recomendaciones", centro_id=centro_id, default=RECOMENDACIONES_CATALOGO
    )

    # Mapear claves seleccionadas a items completos
    items_mapa = {}
    for seccion in catalogo.get("secciones", []):
        for item in seccion.get("items", []):
            items_mapa[item] = item

    # Generar texto: concatenación de items seleccionados
    texto_generado = "\n".join([items_mapa.get(k, k) for k in data.items if k in items_mapa])

    # Crear registro
    rec = RecomendacionPaciente(
        centro_id=centro_id,
        paciente_id=p.id,
        cita_id=data.cita_id,
        items={k: True for k in data.items},  # diccionario de items seleccionados
        texto_generado=texto_generado if texto_generado else None,
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)

    return {
        "ok": True,
        "recomendacion_id": rec.id,
        "items_count": len(data.items),
        "texto_generado": rec.texto_generado,
    }


@router.get("/{paciente_id}/recomendaciones/{rec_id}/pdf")
def pdf_recomendaciones(
    paciente_id: int,
    rec_id: int,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission("pacientes.ver")),
    session: Session = Depends(get_session),
):
    """Genera PDF de recomendaciones guardadas."""
    from fastapi.responses import StreamingResponse
    from io import BytesIO
    try:
        from PyPDF2 import PdfWriter
    except ImportError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "PDF generator no disponible")

    p = _get_paciente(session, centro_id, paciente_id)
    rec = session.get(RecomendacionPaciente, rec_id)
    if not rec or rec.paciente_id != p.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recomendación no encontrada")

    # Generar PDF simple (líneas de texto)
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.pdfgen import canvas
        from reportlab.lib.colors import HexColor

        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        w, h = A4

        # Header
        c.setFont("Helvetica-Bold", 16)
        c.drawString(2*cm, h - 2*cm, f"Recomendaciones de Consulta")
        c.setFont("Helvetica", 10)
        c.setFillColor(HexColor("#666666"))
        c.drawString(2*cm, h - 2.8*cm, f"Paciente: {p.apellidos}, {p.nombre}")

        # Contenido
        c.setFont("Helvetica", 11)
        y = h - 4*cm
        if rec.texto_generado:
            for line in rec.texto_generado.split("\n"):
                c.drawString(2*cm, y, line.strip()[:70])  # truncar línea larga
                y -= 0.5*cm
                if y < 2*cm:
                    c.showPage()
                    y = h - 2*cm

        c.save()
        buffer.seek(0)
        return StreamingResponse(buffer, media_type="application/pdf",
                                 headers={"Content-Disposition": f'inline; filename="recomendaciones_{rec_id}.pdf"'})
    except Exception as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Error generando PDF: {str(e)}")
