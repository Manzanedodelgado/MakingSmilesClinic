"""GESTOR IA — Motor de procesamiento de facturas con IA.

Endpoints consumidos por frontend/src/features/gestoria/services/motorFacturacionService.ts:
  GET  /gestoria/gestor/estado
  GET  /gestoria/gestor/facturas
  GET  /gestoria/gestor/proveedores
  GET  /gestoria/gestor/revision
  GET  /gestoria/gestor/revision/agrupada
  POST /gestoria/gestor/revision/resolver
  GET  /gestoria/gestor/descartes
  POST /gestoria/gestor/barrer
  POST /gestoria/gestor/revisadas

Los emails con la etiqueta 'gastos-2.-gastos-procesados' se procesan
individualmente con el modelo multimodal (GastoIAResponse) vía IA.
"""
import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlmodel import Session, func, select

from api.auth_deps import CurrentUser, get_current_centro, require_permission
from api.audit_helper import _audit
from domain.models.gestor_ia import (
    FacturaGestor, ProveedorGestor, RevisionGestor, DescarteGestor,
    ExcepcionGestor, PasadaGestor,
)
from infrastructure.config.db import get_session

router = APIRouter(prefix="/gestoria/gestor", tags=["gestor-ia"])
EDITAR = "gestoria.editar"
VER = "gestoria.ver"

# ── Etiqueta de Gmail a procesar por el motor IA ──
# 22-oct-2026: era "gastos-2.-gastos-procesados", que NO existe en el buzon (nombre
# normalizado de una nomenclatura anterior). /barrer devolvia 0 correos y 0 errores:
# fallaba en silencio. Se reusa CARPETA_ENTRADA (intake_service) para no volver a tener
# dos listas de carpetas que se contradigan.
from application.services.intake_service import CARPETA_ENTRADA as LABEL_PROCESAR
logger = logging.getLogger(__name__)


async def _no_mover(uid: str, destino: str) -> bool:
    """Sustituto de `_mover_email` cuando el barrido se pide con mover=false."""
    logger.info("Movimiento a %s omitido (mover=false)", destino)
    return False


# ════════════════════ ESTADO GLOBAL ════════════════════════════════════
@router.get("/estado")
def estado_motor(
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission(VER)),
    session: Session = Depends(get_session),
) -> dict:
    """Estado global del motor IA."""
    total_facturas = session.exec(select(func.count()).where(
        FacturaGestor.centro_id == centro_id,
        FacturaGestor.estado == "registrada")).all()[0]
    total_gastos = session.exec(select(func.sum(FacturaGestor.total)).where(
        FacturaGestor.centro_id == centro_id,
        FacturaGestor.estado == "registrada")).all()[0] or 0

    revisiones = session.exec(select(func.count()).where(
        RevisionGestor.centro_id == centro_id, RevisionGestor.resuelta == False)).all()[0]
    descartes_count = session.exec(select(func.count()).where(
        DescarteGestor.centro_id == centro_id)).all()[0]
    badge = session.exec(select(func.count()).where(
        FacturaGestor.centro_id == centro_id,
        FacturaGestor.estado == "registrada",
        FacturaGestor.estado == "registrada",
        FacturaGestor.categoria == None)).all()[0]

    revis_por_motivo = {}
    for motivo, n in session.exec(
        select(RevisionGestor.motivo, func.count()).where(
            RevisionGestor.centro_id == centro_id, RevisionGestor.resuelta == False
        ).group_by(RevisionGestor.motivo)
    ).all():
        revis_por_motivo[motivo] = n

    desc_por_motivo = {}
    for motivo, n in session.exec(
        select(DescarteGestor.motivo, func.count()).where(
            DescarteGestor.centro_id == centro_id
        ).group_by(DescarteGestor.motivo)
    ).all():
        desc_por_motivo[motivo] = n

    ultima = session.exec(
        select(PasadaGestor).where(PasadaGestor.centro_id == centro_id)
        .order_by(PasadaGestor.inicio.desc()).limit(1)
    ).first()
    ultima_pasada = None
    if ultima:
        ultima_pasada = {
            "id": ultima.id,
            "carpeta": ultima.carpeta,
            "inicio": ultima.inicio.isoformat() if ultima.inicio else None,
            "fin": ultima.fin.isoformat() if ultima.fin else None,
            "recuento": ultima.recuento,
            "llamadasIa": ultima.llamadas_ia,
            "cortada": ultima.cortada,
        }

    return {
        "facturas": total_facturas,
        "importeTotal": float(total_gastos),
        "revision": revis_por_motivo,
        "revisionTotal": revisiones,
        "descartes": desc_por_motivo,
        "badgeSinCategoria": badge,
        "ultimaPasada": ultima_pasada,
    }


# ════════════════════ FACTURAS PROCESADAS ══════════════════════════════
@router.get("/facturas")
def listar_facturas(
    limite: int = Query(default=200, le=1000),
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission(VER)),
    session: Session = Depends(get_session),
) -> dict:
    """Lista facturas procesadas por el motor IA."""
    gastos = session.exec(
        select(FacturaGestor).where(
            FacturaGestor.centro_id == centro_id,
            FacturaGestor.estado == "registrada",
        ).order_by(FacturaGestor.fecha_emision.desc()).limit(limite)
    ).all()
    return {"items": [_factura_to_motor(g) for g in gastos]}


def _factura_to_motor(g: FacturaGestor) -> dict:
    """Convierte FacturaGestor -> formato FacturaMotor del frontend."""
    iva_desglose = g.iva_desglose or []
    irpf_pct = 0.0
    if g.base_total and float(g.base_total) > 0:
        irpf_pct = round(float(g.irpf_cuota) / float(g.base_total) * 100, 2)
    return {
        "id": g.id,
        "numero": g.numero_factura,
        "fecha": g.fecha_emision.isoformat() if g.fecha_emision else "",
        "proveedor": g.proveedor_nombre,
        "idFiscal": g.id_fiscal,
        "base": float(g.base_total),
        "iva": [{"base": str(float(d.get("base", 0))), "pct": str(d.get("pct", 0)),
                 "cuota": str(d.get("cuota", 0))} for d in iva_desglose] if iva_desglose else [],
        "irpfPct": irpf_pct,
        "irpfCuota": float(g.irpf_cuota),
        "total": float(g.total),
        "divisa": g.divisa or "EUR",
        "categoria": g.categoria,
        "origen": g.origen_dato,
        "driveUrl": g.drive_url,
        "reconstruida": g.reconstruida,
        "remitente": g.remitente,
    }


# ════════════════════ PROVEEDORES ════════════════════════════════════════
@router.get("/proveedores")
def listar_proveedores(
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission(VER)),
    session: Session = Depends(get_session),
) -> dict:
    provs = session.exec(
        select(ProveedorGestor).where(ProveedorGestor.centro_id == centro_id).order_by(ProveedorGestor.nombre)
    ).all()
    items = []
    sin_categoria = 0
    for p in provs:
        if not p.categoria:
            sin_categoria += 1
        items.append({
            "id": p.id,
            "nombre": p.nombre,
            "idFiscal": p.id_fiscal or "",
            "direccion": p.direccion,
            "telefono": p.telefono,
            "remitentes": p.remitentes or [],
            "categoria": p.categoria,
            "numFacturas": p.num_facturas or session.exec(
                select(func.count(FacturaGestor.id)).where(FacturaGestor.proveedor_id == p.id)
            ).all()[0],
        })
    return {"items": items, "sinCategoria": sin_categoria}


# ════════════════════ REVISIONES ═════════════════════════════════════════
@router.get("/revision")
def listar_revision(
    motivo: str = Query(default=None),
    limite: int = Query(default=100, le=500),
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission(VER)),
    session: Session = Depends(get_session),
) -> dict:
    """Correos que sí parecen facturas pero el motor no pudo resolver."""
    query = select(RevisionGestor).where(
        RevisionGestor.centro_id == centro_id, RevisionGestor.resuelta == False
    )
    if motivo:
        query = query.where(RevisionGestor.motivo == motivo)
    revs = session.exec(query.order_by(RevisionGestor.created_at.desc()).limit(limite)).all()
    return {"items": [
        {
            "id": r.id,
            "motivo": r.motivo,
            "detalle": r.detalle,
            "remitente": r.remitente,
            "asunto": r.asunto,
            "fecha": r.fecha_correo.isoformat() if r.fecha_correo else None,
            "origen": r.origen_dato,
            "campos": r.campos or {},
            "texto": r.texto_leido or "",
        }
        for r in revs
    ]}


@router.get("/revision/agrupada")
def revision_agrupada(
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission(VER)),
    session: Session = Depends(get_session),
) -> dict:
    """Revisión agrupada por proveedor/motivo."""
    revs = session.exec(
        select(RevisionGestor).where(
            RevisionGestor.centro_id == centro_id, RevisionGestor.resuelta == False
        )
    ).all()
    grupos = {}
    for r in revs:
        key = r.remitente or r.motivo
        grp = grupos.setdefault(key, {"motivo": r.motivo, "correos": 0, "muestraId": r.id})
        grp["correos"] += 1
    return {"grupos": [
        {"motivo": v["motivo"], "remitente": k, "correos": v["correos"], "muestraId": v["muestraId"]}
        for k, v in grupos.items()
    ]}


class ResolverRevisionIn(BaseModel):
    ids: list[int]
    accion: str          # "descartar" | "reprocesar"


@router.post("/revision/resolver")
def resolver_revision(
    data: ResolverRevisionIn,
    request: Request,
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission(EDITAR)),
    session: Session = Depends(get_session),
) -> dict:
    """Resolver revisiones: desechar o devolver al motor IA."""
    revs = session.exec(
        select(RevisionGestor).where(RevisionGestor.id.in_(data.ids), RevisionGestor.centro_id == centro_id)
    ).all()
    if not revs:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No se encontraron correos de revisión")
    n = 0
    for r in revs:
        if data.accion == "descartar":
            d = DescarteGestor(
                centro_id=centro_id,
                gmail_message_id=r.gmail_message_id,
                remitente=r.remitente,
                asunto=r.asunto,
                fecha_correo=r.fecha_correo,
                motivo=r.motivo,
                senales=[],
            )
            session.add(d)
            session.delete(r)
        elif data.accion == "reprocesar":
            r.resuelta = True
            session.add(r)      # solo aquí: en "descartar" la fila se BORRA (antes se
                                # re-añadía tras el delete, anulándolo)
        n += 1
    session.commit()
    _audit(session, user, centro_id, "gestoria.gestor.resolver", "revision", request,
           {"ids": data.ids, "accion": data.accion, "afectadas": n})
    return {"ok": True, "accion": data.accion, "afectadas": n}


# ════════════════════ DESCARTES ══════════════════════════════════════════
@router.get("/descartes")
def listar_descartes(
    con_senales: bool = Query(default=False),
    limite: int = Query(default=200, le=1000),
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission(VER)),
    session: Session = Depends(get_session),
) -> dict:
    """Correos descartados (no facturables)."""
    ds = session.exec(
        select(DescarteGestor).where(DescarteGestor.centro_id == centro_id)
        .order_by(DescarteGestor.created_at.desc()).limit(limite)
    ).all()
    return {"items": [
        {
            "id": d.id,
            "motivo": d.motivo,
            "remitente": d.remitente,
            "asunto": d.asunto,
            "senales": d.senales if con_senales else [],
            "fecha": d.fecha_correo.isoformat() if d.fecha_correo else None,
        }
        for d in ds
    ]}


# ════════════════════ BARRER EMAILS (procesa 'gastos-2.-gastos-procesados') ═
@router.post("/barrer")
def barrer(
    request: Request,
    carpeta: str = Query(default=None),
    tope: int = Query(default=None),
    max_llamadas: int = Query(default=None),
    mover: bool = Query(default=True),
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission(EDITAR)),
    session: Session = Depends(get_session),
) -> dict:
    """Barrido de emails con IA multimodal.

    Procesa individualmente cada email de la etiqueta especificada
    (por defecto 'gastos-2.-gastos-procesados') con el modelo IA multimodal.
    Cada email se analiza individualmente: texto + adjuntos + enlaces.
    """
    from application.services.gmail_ai_processor import GmailAIProcessor
    from infrastructure.external_apis import gmail_imap

    carpeta_final = carpeta or LABEL_PROCESAR
    processor = GmailAIProcessor(session, centro_id)

    if not processor.imap_config:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="Gmail IMAP no configurado en este centro")

    # `mover=false` → se procesa y se registra en BD, pero NO se toca el buzón real.
    # Antes el parámetro se declaraba y se ignoraba por completo.
    if not mover:
        processor._mover_email = _no_mover

    correos = gmail_imap.listar_carpeta_msgids(processor.imap_config, carpeta_final)
    recuento = {"gasto": 0, "incidencia": 0, "descartado": 0, "error": 0}
    detalle = []
    llamadas = 0
    pasada = PasadaGestor(
        centro_id=centro_id, carpeta=carpeta_final, inicio=datetime.now()
    )
    session.add(pasada)
    session.flush()

    for c in correos[:tope or 1000]:
        if max_llamadas and llamadas >= max_llamadas:
            pasada.cortada = True
            break
        mid = c.get("msg_id") or c.get("uid")
        if not mid:
            continue
        llamadas += 1
        try:
            result = asyncio.run(processor.procesar_webhook(mid))
            accion_norm = "gasto" if result.accion == "gasto" else result.accion
            recuento[accion_norm] = recuento.get(accion_norm, 0) + 1
            detalle.append({
                "message_id": mid, "asunto": c.get("asunto", ""),
                "remitente": c.get("remitente", ""), "caja": result.accion,
                "motivo": result.error or "", "factura_id": result.gasto_id,
                "senales": [],
            })
        except Exception as e:  # raiz: fallo procesando ese correo con la IA (IMAP, LLM o parseo del mensaje); se cuenta como error y se sigue con el resto
            logger.exception(f"Error procesando {mid}")
            recuento["error"] += 1
            detalle.append({
                "message_id": mid, "asunto": c.get("asunto", ""),
                "remitente": c.get("remitente", ""), "caja": "error",
                "motivo": str(e)[:200], "factura_id": None, "senales": [],
            })

    pasada.fin = datetime.now()
    pasada.recuento = recuento
    pasada.llamadas_ia = llamadas
    session.commit()
    _audit(session, user, centro_id, "gestoria.gestor.barrer", "gastos", request,
           {"carpeta": carpeta_final, "recuento": recuento})
    return {
        "pasadaId": pasada.id,
        "carpeta": carpeta_final,
        "recuento": recuento,
        "llamadas_ia": llamadas,
        "cortada": pasada.cortada,
        "badge_sin_categoria": session.exec(
            select(func.count()).where(
                FacturaGestor.centro_id == centro_id,
                FacturaGestor.categoria == None)).all()[0],
        "detalle": detalle,
    }


@router.post("/revisadas")
def reprocesar_revisadas(
    request: Request,
    tope: int = Query(default=None),
    centro_id: int = Depends(get_current_centro),
    user: CurrentUser = Depends(require_permission(EDITAR)),
    session: Session = Depends(get_session),
) -> dict:
    """Reprocesar los emails en estado 'revisar' con IA."""
    from application.services.gmail_ai_processor import GmailAIProcessor

    revs = session.exec(
        select(RevisionGestor).where(
            RevisionGestor.centro_id == centro_id, RevisionGestor.resuelta == False
        ).limit(tope or 50)
    ).all()
    processor = GmailAIProcessor(session, centro_id)
    reprocesados = 0
    for r in revs:
        try:
            result = asyncio.run(processor.procesar_webhook(r.gmail_message_id or ""))
            if result.ok:
                reprocesados += 1
        except Exception:  # raiz: fallo reprocesando la revisión con la IA (mensaje o LLM); se registra y se sigue con las demás
            logger.exception("gestor-ia: reproceso falló para revisión %s", r.id)
    session.commit()
    _audit(session, user, centro_id, "gestoria.gestor.revisadas", "gastos", request,
           {"reprocesados": reprocesados})
    return {"reprocesados": reprocesados}


__all__ = ["router"]
