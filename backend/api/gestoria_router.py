"""GESTORÍA — endpoints. 2 modos: Producción (liquidación/facturación) + Facturación.
Permisos: gestoria.ver / gestoria.editar. Auditado.
"""
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel
from sqlmodel import Session

from api.auth_deps import CurrentUser, get_current_centro, require_any_permission, require_permission
from api.audit_helper import _audit
from application.services.auth_service import AuthService
from application.services.gestoria_service import GestoriaService
from application.services.gmail_ingest_service import GmailIngestService
from application.services.produccion_service import ProduccionService
from infrastructure.config.db import get_session
from infrastructure.events import emit

router = APIRouter(prefix="/gestoria", tags=["gestoría"])
VER, EDITAR = "gestoria.ver", "gestoria.editar"
FACT = "gestoria.facturacion.ver"   # acceso restringido de Asesoría (solo Facturación + Debe/Haber, lectura)
# Lectura de Facturación: gestoría completa O el permiso Asesoría.
VER_FACT = require_any_permission(VER, FACT)


def _gestor_permisos(session: Session, centro_id: int) -> dict:
    from application.services.config_service import ConfigService
    cfg = ConfigService(session).resolve("gestor.config", centro_id=centro_id, sistema="gestor", default=None) or {}
    return cfg.get("permisos") or {}


def _gate_operar_gestor(session: Session, centro_id: int, user: CurrentUser) -> None:
    """Config→IA's→Gestor→Permisos→«Quién puede acceder» (`roles_acceso`): restringe QUIÉN puede
    disparar las acciones del Gestor IA, por ENCIMA del permiso base. Aditivo (nunca amplía) y el
    superuser SIEMPRE pasa (no hay riesgo de autobloqueo). 'gestoria'/None = sin extra;
    'admin' = exige config.editar; 'superadmin' = solo superuser (modo mantenimiento)."""
    tier = _gestor_permisos(session, centro_id).get("roles_acceso")
    if tier in (None, "", "gestoria", "todos"):
        return
    perms = AuthService(session).permisos_de(user.usuario_id, centro_id)
    if "superuser" in perms:
        return
    if tier == "admin" and "config.editar" in perms:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN,
                        "El Gestor IA está restringido en Config → IA's → Gestor → Permisos.")


def _gate_acceso_datos(session: Session, centro_id: int, requiere_pagos: bool) -> None:
    """Config→IA's→Gestor→Permisos→«Acceso a datos» (`acceso_datos`): 'facturas' = solo facturas/
    gastos (sin pagos/banco). La conciliación bancaria toca pagos → prohibida en ese ámbito."""
    if requiere_pagos and _gestor_permisos(session, centro_id).get("acceso_datos", "facturas_pagos") == "facturas":
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "El ámbito del Gestor es «Solo facturas» (Config → IA's → Gestor → Permisos): "
                            "la conciliación bancaria trabaja con pagos y queda fuera de ese ámbito.")


# ═══════════════ PRODUCCIÓN ═══════════════
@router.get("/produccion/doctores")
def prod_doctores(desde: date = Query(...), hasta: date = Query(...),
                  centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission(VER)),
                  session: Session = Depends(get_session)) -> dict:
    return ProduccionService(session).doctores(centro_id, desde, hasta)


@router.get("/produccion/tratamientos")
def prod_tratamientos(desde: Optional[date] = Query(None), hasta: Optional[date] = Query(None),
                      centro_id: int = Depends(get_current_centro),
                      user: CurrentUser = Depends(require_permission(VER)),
                      session: Session = Depends(get_session)) -> dict:
    # Sin rango (desde/hasta) → todos los años. Sin tope de filas.
    return ProduccionService(session).tratamientos(centro_id, desde, hasta)


@router.get("/produccion/pacientes/{paciente_id}/tratamientos")
def prod_pac_ttos(paciente_id: int,
                  centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission(VER)),
                  session: Session = Depends(get_session)) -> dict:
    return ProduccionService(session).patient_treatments(centro_id, paciente_id)


class PatientInvoiceIn(BaseModel):
    paciente_id: int
    tto_ids: list[int]


@router.post("/produccion/pacientes/factura")
def prod_pac_factura(data: PatientInvoiceIn, request: Request,
                     centro_id: int = Depends(get_current_centro),
                     user: CurrentUser = Depends(require_permission(EDITAR)),
                     session: Session = Depends(get_session)) -> dict:
    res = ProduccionService(session).create_patient_invoice(
        centro_id, data.paciente_id, data.tto_ids)
    _audit(session, user, centro_id, "gestoria.factura_paciente", res.get("numeroFactura", ""), request)
    emit("factura.emitida", {"numero": res.get("numeroFactura"), "centro_id": centro_id,
                             "paciente_id": data.paciente_id})
    return res


class AutofacturaIn(BaseModel):
    doctor_id: int
    desde: date
    hasta: date


@router.post("/produccion/autofactura")
def prod_autofactura(data: AutofacturaIn, request: Request,
                     centro_id: int = Depends(get_current_centro),
                     user: CurrentUser = Depends(require_permission(EDITAR)),
                     session: Session = Depends(get_session)) -> dict:
    res = ProduccionService(session).emitir_autofactura(centro_id, data.doctor_id, data.desde, data.hasta)
    _audit(session, user, centro_id, "gestoria.autofactura", f"col:{data.doctor_id}", request, res)
    return res


class TratamientoUpdateIn(BaseModel):
    descuento: Optional[float] = None
    descuento_aplica_doctor: Optional[bool] = None
    coste_laboratorio: Optional[float] = None


@router.patch("/produccion/tratamientos/{tid}")
def prod_tto_editar(tid: int, data: TratamientoUpdateIn, request: Request,
                    centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(require_permission(EDITAR)),
                    session: Session = Depends(get_session)) -> dict:
    res = ProduccionService(session).actualizar_tratamiento(
        centro_id, tid, descuento=data.descuento, descuento_aplica_doctor=data.descuento_aplica_doctor,
        coste_laboratorio=data.coste_laboratorio)
    _audit(session, user, centro_id, "gestoria.produccion.tratamiento", f"tto:{tid}", request, res)
    return res


# ═══════════════ FACTURACIÓN ═══════════════
def _svc(session) -> GestoriaService:
    return GestoriaService(session)


@router.get("/dashboard")
def dashboard(desde: date = Query(...), hasta: date = Query(...),
              centro_id: int = Depends(get_current_centro),
              user: CurrentUser = Depends(require_permission(VER)),
              session: Session = Depends(get_session)) -> dict:
    return _svc(session).dashboard(centro_id, desde, hasta)


@router.get("/facturas")
def facturas(anyo: Optional[int] = None, search: Optional[str] = None,
             centro_id: int = Depends(get_current_centro),
             user: CurrentUser = Depends(VER_FACT),
             session: Session = Depends(get_session)) -> dict:
    return _svc(session).facturas_emitidas(centro_id, anyo=anyo, search=search)


# ─────────────── INGESTA GMAIL (facturas recibidas) ───────────────
class ImapConfigIn(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    usuario: Optional[str] = None
    password: Optional[str] = None
    carpeta: Optional[str] = None
    dias: Optional[int] = None
    activo: Optional[bool] = None


@router.get("/email-imap/config")
def imap_get(centro_id: int = Depends(get_current_centro),
             user: CurrentUser = Depends(require_permission(VER)),
             session: Session = Depends(get_session)) -> dict:
    return GmailIngestService(session).get_config(centro_id)


@router.put("/email-imap/config")
def imap_save(data: ImapConfigIn, request: Request,
              centro_id: int = Depends(get_current_centro),
              user: CurrentUser = Depends(require_permission(EDITAR)),
              session: Session = Depends(get_session)) -> dict:
    res = GmailIngestService(session).save_config(centro_id, data.model_dump(exclude_none=True))
    _audit(session, user, centro_id, "gestoria.imap.config", "email_imap", request)
    return res


@router.post("/email-imap/test")
def imap_test(request: Request,
              centro_id: int = Depends(get_current_centro),
              user: CurrentUser = Depends(require_permission(EDITAR)),
              session: Session = Depends(get_session)) -> dict:
    res = GmailIngestService(session).test(centro_id)
    _audit(session, user, centro_id, "gestoria.imap.test", "email_imap", request, res)
    return res


@router.get("/facturas/health")
def facturas_health(centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(VER_FACT),
                    session: Session = Depends(get_session)) -> dict:
    return GmailIngestService(session).health(centro_id)


# ═══════════════ GMAIL WEBHOOK (IA Multimodal Tiempo Real) ═══════════════
class GmailWebhookIn(BaseModel):
    message_id: str
    history_id: Optional[str] = None


@router.post("/gmail/webhook")
async def gmail_webhook(data: GmailWebhookIn, request: Request, background_tasks: BackgroundTasks,
                        centro_id: int = Depends(get_current_centro),
                        user: CurrentUser = Depends(require_permission(EDITAR)),
                        session: Session = Depends(get_session)) -> dict:
    """Recibe notificación push de Gmail (watch API) y procesa el email en background."""
    from application.services.gmail_ai_processor import procesar_email_webhook
    background_tasks.add_task(procesar_email_webhook, centro_id, data.message_id)
    return {"ok": True, "message": "Email encolado para procesamiento"}


@router.post("/gmail/watch")
def gmail_watch_activar(request: Request,
                        centro_id: int = Depends(get_current_centro),
                        user: CurrentUser = Depends(require_permission(EDITAR)),
                        session: Session = Depends(get_session)) -> dict:
    """Activa/renueva Gmail watch (push notifications). Expira a 7 días."""
    from infrastructure.external_apis import gmail_watch
    res = gmail_watch.activar_watch(session, centro_id)
    return res


@router.delete("/gmail/watch")
def gmail_watch_detener(request: Request,
                        centro_id: int = Depends(get_current_centro),
                        user: CurrentUser = Depends(require_permission(EDITAR)),
                        session: Session = Depends(get_session)) -> dict:
    """Detiene Gmail watch."""
    from infrastructure.external_apis import gmail_watch
    res = gmail_watch.detener_watch(session, centro_id)
    return res


@router.post("/gmail/watch/renovar")
def gmail_watch_renovar(request: Request,
                        centro_id: int = Depends(get_current_centro),
                        user: CurrentUser = Depends(require_permission(EDITAR)),
                        session: Session = Depends(get_session)) -> dict:
    """Renueva Gmail watch manualmente."""
    from infrastructure.external_apis import gmail_watch
    res = gmail_watch.activar_watch(session, centro_id)
    return res


@router.get("/gmail/watch/status")
def gmail_watch_status(centro_id: int = Depends(get_current_centro),
                       user: CurrentUser = Depends(require_permission(VER)),
                       session: Session = Depends(get_session)) -> dict:
    """Estado actual del Gmail watch."""
    from infrastructure.external_apis import gmail_watch
    return gmail_watch.estado_watch(session, centro_id)


# ═══════════════ IA MULTIMODAL CONFIG ═══════════════
class IAConfigIn(BaseModel):
    prompt_personalizado: str = ""
    few_shots: str = ""
    umbral_confianza: str = "media"
    proveedores_conocidos: dict = {}


@router.get("/ia/config")
def ia_config_get(centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission(VER)),
                  session: Session = Depends(get_session)) -> dict:
    """Obtiene configuración IA multimodal del centro."""
    from application.services.config_service import ConfigService
    cfg = ConfigService(session).resolve("gestor_multimodal.config", centro_id=centro_id, sistema="gestor", default=None) or {}
    return cfg


@router.put("/ia/config")
def ia_config_put(data: IAConfigIn, request: Request,
                  centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission(EDITAR)),
                  session: Session = Depends(get_session)) -> dict:
    """Guarda configuración IA multimodal."""
    from application.services.config_service import ConfigService
    ConfigService(session).set("gestor_multimodal.config", data.model_dump(), centro_id=centro_id)
    return {"ok": True}


@router.post("/gmail/reprocesar")
def gmail_reprocesar(data: dict, background_tasks: BackgroundTasks, request: Request,
                     centro_id: int = Depends(get_current_centro),
                     user: CurrentUser = Depends(require_permission(EDITAR)),
                     session: Session = Depends(get_session)) -> dict:
    """Reprocesa un email por message_id en background."""
    from application.services.gmail_ai_processor import procesar_email_webhook
    message_id = data.get("message_id")
    if not message_id:
        raise HTTPException(400, "message_id requerido")
    background_tasks.add_task(procesar_email_webhook, centro_id, message_id)
    return {"ok": True, "message": "Email encolado para reprocesamiento"}


@router.get("/gastos/{gid}/pdf")
def gasto_pdf(gid: int, centro_id: int = Depends(get_current_centro),
              user: CurrentUser = Depends(VER_FACT),
              session: Session = Depends(get_session)):
    from fastapi import Response
    contenido = GmailIngestService(session).pdf_gasto(centro_id, gid)
    if not contenido:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PDF no disponible")
    return Response(content=contenido, media_type="application/pdf",
                    headers={"Content-Disposition": "inline"})


@router.get("/gastos/{gid}/correo-pdf")
def gasto_correo_pdf(gid: int, centro_id: int = Depends(get_current_centro),
                     user: CurrentUser = Depends(VER_FACT),
                     session: Session = Depends(get_session)):
    """Captura del correo ORIGINAL renderizada a PDF (para facturas en revisar sin PDF adjunto)."""
    from fastapi import Response
    contenido = GmailIngestService(session).correo_pdf_gasto(centro_id, gid)
    if not contenido:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "No se pudo abrir el correo (sin IMAP válido o correo no encontrado)")
    return Response(content=contenido, media_type="application/pdf",
                    headers={"Content-Disposition": "inline"})


@router.get("/gastos/{gid}/paginas")
def gasto_paginas(gid: int, centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(VER_FACT),
                  session: Session = Depends(get_session)) -> dict:
    return GmailIngestService(session).paginas_gasto(centro_id, gid)


@router.post("/facturas/reorganizar-drive")
def facturas_reorganizar_drive(request: Request,
                               centro_id: int = Depends(get_current_centro),
                               user: CurrentUser = Depends(require_permission(EDITAR)),
                               session: Session = Depends(get_session)) -> dict:
    res = GmailIngestService(session).reorganizar_drive_por_anyo(centro_id)
    _audit(session, user, centro_id, "gestoria.drive.reorganizar", "gmail", request, res)
    return res


class AsociarIn(BaseModel):
    movimiento_id: int


@router.post("/gastos/{gid}/asociar")
def gasto_asociar(gid: int, data: AsociarIn, request: Request,
                  centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission(EDITAR)),
                  session: Session = Depends(get_session)) -> dict:
    res = _svc(session).asociar_gasto_movimiento(centro_id, gid, data.movimiento_id)
    _audit(session, user, centro_id, "gestoria.gasto.asociar", "gastos", request, res)
    return res


@router.delete("/gastos/{gid}/asociar")
def gasto_desasociar(gid: int, request: Request,
                     centro_id: int = Depends(get_current_centro),
                     user: CurrentUser = Depends(require_permission(EDITAR)),
                     session: Session = Depends(get_session)) -> dict:
    res = _svc(session).desasociar_gasto(centro_id, gid)
    _audit(session, user, centro_id, "gestoria.gasto.desasociar", f"gasto:{gid}", request)
    return res


@router.post("/gastos/asociar-automatico")
def gastos_asociar_auto(request: Request, dias: int = 30,
                        centro_id: int = Depends(get_current_centro),
                        user: CurrentUser = Depends(require_permission(EDITAR)),
                        session: Session = Depends(get_session)) -> dict:
    res = _svc(session).asociar_facturas_auto(centro_id, dias=dias)
    _audit(session, user, centro_id, "gestoria.gasto.asociar_auto", "gastos", request, res)
    return res


@router.get("/movimientos/debe-libres")
def movimientos_debe_libres(centro_id: int = Depends(get_current_centro),
                            user: CurrentUser = Depends(require_permission(VER)),
                            session: Session = Depends(get_session)) -> dict:
    return _svc(session).movimientos_debe_libres(centro_id)


@router.get("/gastos/libres")
def gastos_libres(centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission(VER)),
                  session: Session = Depends(get_session)) -> dict:
    """Facturas sin apunte, para el modal de conciliación manual desde Debe/Haber."""
    return _svc(session).gastos_libres(centro_id)


@router.get("/movimientos/haber-libres")
def movimientos_haber_libres(centro_id: int = Depends(get_current_centro),
                             user: CurrentUser = Depends(require_permission(VER)),
                             session: Session = Depends(get_session)) -> dict:
    return _svc(session).movimientos_haber_libres(centro_id)


@router.get("/pagos-pacientes")
def pagos_pacientes(anyo: Optional[int] = None, forma: Optional[str] = None,
                    centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(require_permission(VER)),
                    session: Session = Depends(get_session)) -> dict:
    return _svc(session).list_pagos_pacientes(centro_id, anyo=anyo, forma=forma)


@router.post("/pagos-pacientes/{pid}/asociar")
def pago_asociar(pid: int, data: AsociarIn, request: Request,
                 centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission(EDITAR)),
                 session: Session = Depends(get_session)) -> dict:
    res = _svc(session).asociar_pago_movimiento(centro_id, pid, data.movimiento_id)
    _audit(session, user, centro_id, "gestoria.pago.asociar", "pagos", request, res)
    return res


@router.delete("/pagos-pacientes/{pid}/asociar")
def pago_desasociar(pid: int, request: Request,
                    centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(require_permission(EDITAR)),
                    session: Session = Depends(get_session)) -> dict:
    res = _svc(session).desasociar_pago(centro_id, pid)
    _audit(session, user, centro_id, "gestoria.pago.desasociar", f"pago:{pid}", request)
    return res


@router.get("/gastos")
def gastos(estado: Optional[str] = None, desde: Optional[date] = None, hasta: Optional[date] = None,
           centro_id: int = Depends(get_current_centro),
           user: CurrentUser = Depends(VER_FACT),
           session: Session = Depends(get_session)) -> dict:
    return _svc(session).list_gastos(centro_id, estado=estado, desde=desde, hasta=hasta)


@router.get("/gastos/export-excel")
def gastos_export_excel(desde: Optional[date] = None, hasta: Optional[date] = None,
                        centro_id: int = Depends(get_current_centro),
                        user: CurrentUser = Depends(VER_FACT),
                        session: Session = Depends(get_session)):
    """Export a Excel de gastos (vista de apoyo para la asesoría) — una pestaña por `estado`.
    No es fuente de verdad: solo lectura de lo que ya hay en BD."""
    import io

    from fastapi.responses import StreamingResponse

    from application.services.gastos_export_service import generar_excel_gastos

    contenido = generar_excel_gastos(session, centro_id, desde, hasta)
    return StreamingResponse(
        io.BytesIO(contenido),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="gastos.xlsx"'})


@router.get("/facturas-recibidas/pdfs-zip")
def facturas_pdfs_zip(estado: Optional[str] = None, desde: Optional[date] = None, hasta: Optional[date] = None,
                      centro_id: int = Depends(get_current_centro),
                      user: CurrentUser = Depends(VER_FACT),
                      session: Session = Depends(get_session)):
    """Descarga TODAS las facturas del listado de Facturación (mismos filtros) en un ZIP de PDFs.
    Pensado para la Asesoría: un clic → todas las facturas del periodo."""
    import io
    import re as _re
    import zipfile
    from fastapi.responses import Response

    listado = _svc(session).list_gastos(centro_id, estado=estado, desde=desde, hasta=hasta)
    svc_pdf = GmailIngestService(session)
    buf = io.BytesIO()
    n_ok = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in listado.get("data", []):
            contenido = svc_pdf.pdf_gasto(centro_id, f["id"])
            if not contenido:
                continue  # factura sin PDF adjunto (p.ej. solo apunte) → se omite, no rompe el ZIP
            prov = _re.sub(r"[^\w\- ]", "", (f.get("proveedor") or "proveedor")).strip()[:40] or "proveedor"
            num = _re.sub(r"[^\w\-]", "_", (f.get("numeroFactura") or str(f["id"])))[:30]
            zf.writestr(f"{f.get('fecha') or 's-f'}_{prov}_{num}.pdf", contenido)
            n_ok += 1
    if n_ok == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ninguna factura del filtro tiene PDF disponible")
    return Response(content=buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="facturas.zip"'})


@router.get("/contabilizacion")
def contabilizacion(anyo: Optional[int] = None,
                    centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(require_permission(VER)),
                    session: Session = Depends(get_session)) -> dict:
    return _svc(session).contabilizacion(centro_id, anyo)


class GastoIn(BaseModel):
    proveedor_id: Optional[int] = None
    fecha: date
    concepto: Optional[str] = None
    numero_factura: Optional[str] = None
    base_imponible: float = 0
    iva_pct: float = 0
    total: float = 0
    forma_pago: Optional[str] = None
    estado: str = "pendiente"


@router.post("/gastos", status_code=201)
def gasto_crear(data: GastoIn, request: Request,
                centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(require_permission(EDITAR)),
                session: Session = Depends(get_session)) -> dict:
    res = _svc(session).create_gasto(centro_id, data.model_dump())
    _audit(session, user, centro_id, "gestoria.gasto.crear", f"gasto:{res['id']}", request)
    return res


@router.patch("/gastos/{gid}")
def gasto_editar(gid: int, data: dict, request: Request,
                 centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission(EDITAR)),
                 session: Session = Depends(get_session)) -> dict:
    res = _svc(session).update_gasto(centro_id, gid, data)
    _audit(session, user, centro_id, "gestoria.gasto.editar", f"gasto:{gid}", request,
           {"campos": sorted(data.keys()), **res})
    return res


@router.delete("/gastos/{gid}")
def gasto_borrar(gid: int, request: Request,
                 centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission(EDITAR)),
                 session: Session = Depends(get_session)) -> dict:
    snap = _svc(session).delete_gasto(centro_id, gid)
    _audit(session, user, centro_id, "gestoria.gasto.borrar", f"gasto:{gid}", request, snap)
    return {"ok": True}


# ─────────── REPROCESO MANUAL DEL BACKLOG (buckets A/B/C/E/F) ───────────
# Ruta REAL: /gestoria/gastos/{id}/reprocesar (el router cuelga de prefix='/gestoria';
# no hay prefijo '/api' en esta API — el del prompt era orientativo). Mismo auth que el resto.
class ReprocesarIn(BaseModel):
    bucket: str


class ReprocesarLoteIn(BaseModel):
    ids: list[int]
    bucket: str


@router.post("/gastos/reprocesar-lote")
def gastos_reprocesar_lote(data: ReprocesarLoteIn, request: Request,
                           centro_id: int = Depends(get_current_centro),
                           user: CurrentUser = Depends(require_permission(EDITAR)),
                           session: Session = Depends(get_session)) -> dict:
    from application.services.intake_service import IntakeService
    svc = IntakeService(session, centro_id)
    procesados, errores = 0, []
    for gid in data.ids:
        r = svc.reprocesar_gasto(gid, data.bucket)
        if r.get("ok"):
            procesados += 1
        else:
            errores.append({"id": gid, "error": r.get("error") or r.get("detalle") or ""})
    _audit(session, user, centro_id, "gestoria.gasto.reprocesar_lote", "gastos", request,
           {"procesados": procesados, "errores": len(errores)})
    return {"procesados": procesados, "errores": errores}


@router.post("/gastos/{gid}/reprocesar")
def gasto_reprocesar(gid: int, data: ReprocesarIn, request: Request,
                     centro_id: int = Depends(get_current_centro),
                     user: CurrentUser = Depends(require_permission(EDITAR)),
                     session: Session = Depends(get_session)) -> dict:
    from application.services.intake_service import IntakeService
    res = IntakeService(session, centro_id).reprocesar_gasto(gid, data.bucket)
    _audit(session, user, centro_id, "gestoria.gasto.reprocesar", f"gasto:{gid}", request, res)
    return {"ok": bool(res.get("ok")), "estado_anterior": res.get("estadoAnterior"),
            "estado_nuevo": res.get("estadoNuevo"),
            "detalle": res.get("detalle") or res.get("error") or ""}


# ═══════════════ MOTORES (intake · conciliación · IA) ═══════════════
# Delegan en los servicios ya existentes (IntakeService / ConciliacionService / GestoriaService).
# Los que ejecutan escrituras auditan SOLO cuando execute=True (la previsualización no muta nada).
class ExecuteIn(BaseModel):
    execute: bool = False


@router.post("/gastos/upload")
async def gasto_upload(request: Request, file: UploadFile = File(...),
                       centro_id: int = Depends(get_current_centro),
                       user: CurrentUser = Depends(require_permission(EDITAR)),
                       session: Session = Depends(get_session)) -> dict:
    """Sube una factura (foto/escaneo/PDF) → pipeline de intake (lee, dedup por identidad, archiva)."""
    from application.services.intake_service import IntakeService
    contenido = await file.read()
    res = IntakeService(session, centro_id).procesar_archivo_subido(contenido, file.filename or "")
    _audit(session, user, centro_id, "gestoria.gasto.upload", f"gasto:{res.get('id', '')}", request, res)
    return res


@router.post("/gastos/clasificar-ia")
def gastos_clasificar_ia(data: ExecuteIn, request: Request,
                         centro_id: int = Depends(get_current_centro),
                         user: CurrentUser = Depends(require_permission(EDITAR)),
                         session: Session = Depends(get_session)) -> dict:
    _gate_operar_gestor(session, centro_id, user)
    res = _svc(session).clasificar_gastos_ia(centro_id, execute=data.execute)
    if data.execute and res.get("ok"):
        from application.services.config_service import ConfigService
        gcfg = ConfigService(session).resolve("gestor.config", centro_id=centro_id, sistema="gestor", default=None) or {}
        # Config→IA's→Gestor→Permisos→"Auditoría de acciones": si está apagada, no se registra.
        if (gcfg.get("permisos") or {}).get("auditoria", True):
            _audit(session, user, centro_id, "gestoria.gasto.clasificar_ia", "gastos", request,
                   {"aplicados": res.get("aplicados"), "revisar": res.get("revisar"),
                    "pendientesConfirmacion": res.get("pendientesConfirmacion")})
    return res


@router.post("/buzon/procesar")
def buzon_procesar(data: ExecuteIn, request: Request,
                   centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission(EDITAR)),
                   session: Session = Depends(get_session)) -> dict:
    _gate_operar_gestor(session, centro_id, user)
    from application.services.intake_service import IntakeService, CARPETA_ENTRADA, ETIQUETA_REVISADAS
    cfg = GmailIngestService(session).get_config(centro_id).get("config", {})
    carpeta = cfg.get("carpeta") or CARPETA_ENTRADA
    svc = IntakeService(session, centro_id)
    res = svc.procesar_buzon(carpeta, execute=data.execute)
    # Facturas/Facturas revisadas: correos que el usuario confirmó a mano tras revisar
    # Incidencias. Mismo botón, misma pasada — se registran siempre, nunca se descartan.
    res["revisadas"] = svc.procesar_revisadas(ETIQUETA_REVISADAS, execute=data.execute)
    if data.execute and res.get("ok"):
        _audit(session, user, centro_id, "gestoria.buzon.procesar", carpeta, request,
               {"facturasNuevas": res.get("facturasNuevas"), "incidencias": res.get("incidencias"),
                "revisadasRegistradas": res["revisadas"].get("registradas")})
    return res


@router.post("/buzon/reintentar-incidencias")
def buzon_reintentar_incidencias(data: ExecuteIn, request: Request,
                                 limite: Optional[int] = Query(None, ge=1, le=500),
                                 centro_id: int = Depends(get_current_centro),
                                 user: CurrentUser = Depends(require_permission(EDITAR)),
                                 session: Session = Depends(get_session)) -> dict:
    """Vuelve a leer las incidencias que falló la IA. Sin execute solo informa."""
    _gate_operar_gestor(session, centro_id, user)
    from application.services.intake_service import IntakeService
    res = IntakeService(session, centro_id).reintentar_incidencias(limite=limite, execute=data.execute)
    if data.execute and res.get("ok"):
        _audit(session, user, centro_id, "gestoria.buzon.reintentar_incidencias", "gastos", request,
               {k: res.get(k) for k in ("procesadas", "recuperadas", "enlazadas", "siguenMal", "errores")})
    return res


@router.get("/buzon/incidencias-count")
def buzon_incidencias_count(centro_id: int = Depends(get_current_centro),
                            user: CurrentUser = Depends(require_permission(VER)),
                            session: Session = Depends(get_session)) -> dict:
    """Recuento EN VIVO de correos en Facturas/Incidencias — para el badge de la web. El
    usuario resuelve cada incidencia moviendo o borrando el correo en Gmail, así que la
    cuenta se lee ahí mismo, no de una tabla que habría que mantener sincronizada."""
    from application.services.intake_service import ETIQUETA_INCIDENCIAS
    from infrastructure.external_apis import gmail_imap
    cfg = GmailIngestService(session).get_config(centro_id).get("config", {})
    if not cfg:
        return {"count": 0}
    try:
        correos = gmail_imap.listar_carpeta_msgids(cfg, ETIQUETA_INCIDENCIAS)
        return {"count": len(correos)}
    except Exception:  # raiz: IMAP/Gmail no disponible o mal configurado al contar incidencias; el badge cae a 0 y no rompe la pantalla  # noqa: BLE001
        return {"count": 0}


@router.post("/banco/cuadrar")
def banco_cuadrar(data: ExecuteIn, request: Request,
                  centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission(EDITAR)),
                  session: Session = Depends(get_session)) -> dict:
    _gate_operar_gestor(session, centro_id, user)
    _gate_acceso_datos(session, centro_id, requiere_pagos=True)
    from application.services.conciliacion_service import ConciliacionService
    res = ConciliacionService(session, centro_id).cuadrar(execute=data.execute)
    if data.execute:
        _audit(session, user, centro_id, "gestoria.banco.cuadrar", "movimientos", request, res)
    return res


@router.get("/gastos/propuesta-eliminar")
def gastos_propuesta_eliminar(centro_id: int = Depends(get_current_centro),
                              user: CurrentUser = Depends(require_permission(VER)),
                              session: Session = Depends(get_session)) -> dict:
    """Facturas sin Debe asociado en meses ya cerrados: PROPUESTA de eliminación (no borra nada)."""
    from application.services.conciliacion_service import ConciliacionService
    return ConciliacionService(session, centro_id).facturas_sin_debe()


class BorrarPropuestaIn(BaseModel):
    ids: list[int]


@router.post("/gastos/propuesta-eliminar/borrar")
def gastos_propuesta_eliminar_borrar(data: BorrarPropuestaIn, request: Request,
                                     centro_id: int = Depends(get_current_centro),
                                     user: CurrentUser = Depends(require_permission("superuser")),
                                     session: Session = Depends(get_session)) -> dict:
    """Solo el superuser borra, y solo ids que SIGAN en la propuesta (se revalida en el momento)."""
    from application.services.conciliacion_service import ConciliacionService
    vigentes = {d["id"] for d in ConciliacionService(session, centro_id).facturas_sin_debe()["data"]}
    fuera = sorted(set(data.ids) - vigentes)
    if fuera:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya no están en la propuesta: {fuera}")
    snaps = {gid: _svc(session).delete_gasto(centro_id, gid) for gid in sorted(set(data.ids))}
    _audit(session, user, centro_id, "gestoria.gasto.borrar_propuesta", f"gastos:{len(snaps)}", request,
           {"ids": sorted(snaps), "detalle": snaps})
    return {"ok": True, "borradas": len(snaps)}


@router.post("/gastos/enlazar-proveedores")
def gastos_enlazar_proveedores(request: Request,
                               centro_id: int = Depends(get_current_centro),
                               user: CurrentUser = Depends(require_permission(EDITAR)),
                               session: Session = Depends(get_session)) -> dict:
    """Enlaza al directorio las facturas con CIF que quedaron sin proveedor."""
    res = _svc(session).enlazar_proveedores(centro_id)
    _audit(session, user, centro_id, "gestoria.gasto.enlazar_proveedores", "gastos", request, res)
    return res


@router.post("/gastos/completar-formas-pago")
def gastos_completar_formas_pago(request: Request,
                                 centro_id: int = Depends(get_current_centro),
                                 user: CurrentUser = Depends(require_permission(EDITAR)),
                                 session: Session = Depends(get_session)) -> dict:
    """Rellena la forma de pago de las facturas ya conciliadas leyéndola del extracto."""
    res = _svc(session).completar_formas_pago(centro_id)
    _audit(session, user, centro_id, "gestoria.gasto.formas_pago", "gastos", request, res)
    return res


class RenumerarIn(BaseModel):
    cif: str
    execute: bool = False
    desde: Optional[date] = None    # no tocar ejercicios ya presentados salvo que se pida


@router.post("/colaboradores/renumerar-autofacturas")
def colaborador_renumerar(data: RenumerarIn, request: Request,
                          centro_id: int = Depends(get_current_centro),
                          user: CurrentUser = Depends(require_permission(EDITAR)),
                          session: Session = Depends(get_session)) -> dict:
    """Re-numera las autofacturas de un colaborador por el mes producido (execute=false: solo propone)."""
    from application.services.conciliacion_service import ConciliacionService
    res = ConciliacionService(session, centro_id).renumerar_autofacturas(
        data.cif, execute=data.execute, desde=data.desde)
    if data.execute:
        _audit(session, user, centro_id, "gestoria.colaborador.renumerar", f"cif:{data.cif}", request, res)
    return res


@router.post("/colaboradores/reemitir-autofacturas")
def colaborador_reemitir(data: RenumerarIn, request: Request,
                         centro_id: int = Depends(get_current_centro),
                         user: CurrentUser = Depends(require_permission(EDITAR)),
                         session: Session = Depends(get_session)) -> dict:
    """Regenera el PDF de las autofacturas con los datos actuales (nº e importes vigentes)."""
    from application.services.conciliacion_service import ConciliacionService
    res = ConciliacionService(session, centro_id).reemitir_autofacturas(data.cif, desde=data.desde)
    _audit(session, user, centro_id, "gestoria.colaborador.reemitir", f"cif:{data.cif}", request, res)
    return res


class ConceptoIn(BaseModel):
    concepto: Optional[str] = None   # vacío = deshacer la corrección


@router.patch("/movimientos/{mid}/concepto")
def movimiento_corregir_concepto(mid: int, data: ConceptoIn, request: Request,
                                 centro_id: int = Depends(get_current_centro),
                                 user: CurrentUser = Depends(require_permission(EDITAR)),
                                 session: Session = Depends(get_session)) -> dict:
    """Corrige la lectura de un apunte mal rotulado. El texto del extracto no se altera."""
    res = _svc(session).corregir_concepto_movimiento(centro_id, mid, data.concepto)
    _audit(session, user, centro_id, "gestoria.movimiento.concepto", f"mov:{mid}", request, res)
    return res


@router.get("/banco/revision")
def banco_revision(centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission(VER)),
                   session: Session = Depends(get_session)) -> dict:
    from application.services.conciliacion_service import ConciliacionService
    return ConciliacionService(session, centro_id).pendientes_revision()


class PrestamoIn(BaseModel):
    interes: float


@router.post("/banco/revision/{mid}/prestamo")
def banco_prestamo(mid: int, data: PrestamoIn, request: Request,
                   centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission(EDITAR)),
                   session: Session = Depends(get_session)) -> dict:
    from application.services.conciliacion_service import ConciliacionService
    try:
        res = ConciliacionService(session, centro_id).resolver_prestamo(mid, data.interes)
    except ValueError as e:  # raiz: la conciliación rechaza el interés del préstamo (valor no válido); se devuelve 400 con el motivo
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    _audit(session, user, centro_id, "gestoria.banco.prestamo", f"mov:{mid}", request, res)
    return res


@router.post("/pagos/conciliar-tarjetas")
def pagos_conciliar_tarjetas(data: ExecuteIn, request: Request,
                             centro_id: int = Depends(get_current_centro),
                             user: CurrentUser = Depends(require_permission(EDITAR)),
                             session: Session = Depends(get_session)) -> dict:
    from application.services.conciliacion_service import ConciliacionService
    res = ConciliacionService(session, centro_id).conciliar_tarjetas(execute=data.execute)
    if data.execute:
        _audit(session, user, centro_id, "gestoria.pagos.conciliar_tarjetas", "pagos", request,
               {"conciliadas": res.get("conciliadas"), "pagos_marcados": res.get("pagos_marcados")})
    return res


# ─────────── IMPUTACIÓN PAGO → DEUDA (tabla puente deuda_pago) ───────────
@router.post("/deudas/imputar")
def deudas_imputar(data: ExecuteIn, request: Request,
                   centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission(EDITAR)),
                   session: Session = Depends(get_session)) -> dict:
    """Registra en `deuda_pago` los emparejamientos INEQUÍVOCOS pago↔deuda.

    Solo el caso sin duda (mismo paciente, fecha e importe, y único candidato por ambos
    lados). El resto exige una regla contable y NO se toca. execute=false previsualiza."""
    from application.services.imputacion_service import ImputacionService
    res = ImputacionService(session, centro_id).imputar_inequivocos(execute=data.execute)
    if data.execute:
        _audit(session, user, centro_id, "gestoria.deudas.imputar", "deuda_pago", request, res)
    return res


@router.get("/deudas/sin-imputar")
def deudas_sin_imputar(centro_id: int = Depends(get_current_centro),
                       user: CurrentUser = Depends(require_permission(VER)),
                       session: Session = Depends(get_session)) -> dict:
    """Lo que queda fuera del emparejamiento inequívoco y por qué."""
    from application.services.imputacion_service import ImputacionService
    return ImputacionService(session, centro_id).pendientes_de_regla()


@router.get("/duplicados")
def duplicados(centro_id: int = Depends(get_current_centro),
               user: CurrentUser = Depends(require_permission(VER)),
               session: Session = Depends(get_session)) -> dict:
    return _svc(session).duplicados_gastos(centro_id)


@router.get("/proveedores")
def proveedores(centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(require_permission(VER)),
                session: Session = Depends(get_session)) -> dict:
    return _svc(session).list_proveedores(centro_id)


@router.get("/proveedores/catalogos")
def proveedores_catalogos(user: CurrentUser = Depends(require_permission(VER)),
                          session: Session = Depends(get_session)) -> dict:
    return _svc(session).catalogos_proveedor()


@router.get("/proveedores/sin-categoria")
def proveedores_sin_categoria(centro_id: int = Depends(get_current_centro),
                              user: CurrentUser = Depends(require_permission(VER)),
                              session: Session = Depends(get_session)) -> dict:
    """Recuento para el badge del icono de Proveedores en Facturas."""
    return _svc(session).proveedores_sin_categoria_count(centro_id)


@router.post("/proveedores/unificar-cif")
def proveedores_unificar_cif(request: Request,
                             centro_id: int = Depends(get_current_centro),
                             user: CurrentUser = Depends(require_permission(EDITAR)),
                             session: Session = Depends(get_session)) -> dict:
    res = _svc(session).unificar_por_cif(centro_id)
    _audit(session, user, centro_id, "gestoria.proveedor.unificar_cif", "proveedores", request, res)
    return res


class FusionIn(BaseModel):
    canonico_id: int
    ids: list[int]


@router.post("/proveedores/fusionar")
def proveedores_fusionar(data: FusionIn, request: Request,
                         centro_id: int = Depends(get_current_centro),
                         user: CurrentUser = Depends(require_permission(EDITAR)),
                         session: Session = Depends(get_session)) -> dict:
    res = _svc(session).fusionar_proveedores(centro_id, data.canonico_id, data.ids)
    _audit(session, user, centro_id, "gestoria.proveedor.fusionar", "proveedores", request, res)
    return res


class ProveedorIn(BaseModel):
    nombre: str
    cif: Optional[str] = None
    email_contacto: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    iban: Optional[str] = None
    categoria: Optional[str] = None
    forma_pago: Optional[str] = None
    es_laboratorio: Optional[bool] = None


@router.post("/proveedores", status_code=201)
def proveedor_crear(data: ProveedorIn, request: Request,
                    centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(require_permission(EDITAR)),
                    session: Session = Depends(get_session)) -> dict:
    from domain.services.invoice_extractor import normalizar_cif
    if data.cif:
        cif_n = normalizar_cif(data.cif)
        if not cif_n:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "CIF/identificación fiscal inválido.")
        data_dict = data.model_dump(exclude_none=True)
        data_dict['cif'] = cif_n
    else:
        data_dict = data.model_dump(exclude_none=True)
    res = _svc(session).crear_proveedor(centro_id, data_dict)
    _audit(session, user, centro_id, "gestoria.proveedor.crear", "proveedores", request, res)
    return res


@router.patch("/proveedores/{pid}")
def proveedor_editar(pid: int, data: dict, request: Request,
                     centro_id: int = Depends(get_current_centro),
                     user: CurrentUser = Depends(require_permission(EDITAR)),
                     session: Session = Depends(get_session)) -> dict:
    res = _svc(session).update_proveedor(centro_id, pid, data)
    _audit(session, user, centro_id, "gestoria.proveedor.editar", "proveedores", request, res)
    return res


@router.delete("/proveedores/{pid}")
def proveedor_borrar(pid: int, request: Request,
                     centro_id: int = Depends(get_current_centro),
                     user: CurrentUser = Depends(require_permission(EDITAR)),
                     session: Session = Depends(get_session)) -> dict:
    res = _svc(session).delete_proveedor(centro_id, pid)
    _audit(session, user, centro_id, "gestoria.proveedor.borrar", "proveedores", request, res)
    return res


@router.get("/movimientos")
def movimientos(tipo: Optional[str] = None, anyo: Optional[int] = None,
                centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(VER_FACT),
                session: Session = Depends(get_session)) -> dict:
    return _svc(session).list_movimientos(centro_id, tipo=tipo, anyo=anyo)


class MovRow(BaseModel):
    iban_cuenta: str
    fecha_operacion: date
    concepto_banco: str
    importe: float
    saldo_posterior: Optional[float] = None


class MovNuevo(BaseModel):
    fecha_operacion: date
    concepto_banco: str
    importe: float
    iban_cuenta: Optional[str] = None
    categoria: Optional[str] = None


@router.post("/movimientos", status_code=201)
def mov_crear(data: MovNuevo, request: Request,
              centro_id: int = Depends(get_current_centro),
              user: CurrentUser = Depends(require_permission(EDITAR)),
              session: Session = Depends(get_session)) -> dict:
    res = _svc(session).crear_movimiento(centro_id, data.model_dump())
    _audit(session, user, centro_id, "gestoria.banco.crear", "movimientos", request, res)
    return res


@router.delete("/movimientos/{mid}")
def mov_borrar(mid: int, request: Request,
               centro_id: int = Depends(get_current_centro),
               user: CurrentUser = Depends(require_permission(EDITAR)),
               session: Session = Depends(get_session)) -> dict:
    snap = _svc(session).delete_movimiento(centro_id, mid)
    _audit(session, user, centro_id, "gestoria.banco.borrar", f"mov:{mid}", request, snap)
    return {"ok": True}


@router.post("/movimientos/import")
def mov_import(rows: list[MovRow], request: Request,
               centro_id: int = Depends(get_current_centro),
               user: CurrentUser = Depends(require_permission(EDITAR)),
               session: Session = Depends(get_session)) -> dict:
    res = _svc(session).import_movimientos(centro_id, [r.model_dump() for r in rows])
    _audit(session, user, centro_id, "gestoria.banco.import", "movimientos", request, res)
    return res


@router.post("/movimientos/import-xlsx")
async def mov_import_xlsx(request: Request, file: UploadFile = File(...),
                          iban: str = Form(""),
                          centro_id: int = Depends(get_current_centro),
                          user: CurrentUser = Depends(require_permission(EDITAR)),
                          session: Session = Depends(get_session)) -> dict:
    contenido = await file.read()
    res = _svc(session).importar_movimientos_archivo(centro_id, contenido,
                                                     filename=file.filename or "", iban_default=iban)
    # Conciliar EN EL ACTO lo recién subido: casa facturas existentes y genera los
    # recurrentes (autofacturas de colaborador, alquiler, renting…). Acotado a los apuntes
    # nuevos (`solo_ids`): subir un extracto no debe remover ejercicios ya cerrados.
    nuevos_ids = res.pop("ids", [])
    if nuevos_ids:
        try:
            from application.services.conciliacion_service import ConciliacionService
            res["conciliacion"] = ConciliacionService(session, centro_id).cuadrar(
                execute=True, solo_ids=nuevos_ids)
        except Exception as e:  # raiz: la conciliación de los apuntes recién importados falló (datos o servicio); se registra y la importación ya commiteada se mantiene  # noqa: BLE001
            logging.getLogger("gestoria").exception("Conciliación tras importar falló")
            res["conciliacion_error"] = str(e)
    # Archivar el fichero TAL CUAL: soporte documental para la asesoría. Si fallara el
    # guardado, la importación (que ya está hecha y commiteada) no se deshace: se avisa.
    try:
        from application.services.extracto_archivo import archivar_extracto
        reg = archivar_extracto(session, centro_id, contenido,
                                nombre_original=file.filename or "extracto",
                                usuario_id=user.usuario_id,
                                importados=int(res.get("importados") or 0),
                                omitidos=int(res.get("omitidos") or 0))
        res["archivo_id"] = reg.id
    except Exception as e:  # raiz: no se pudo archivar el extracto subido (disco o BD); se avisa sin deshacer la importación  # noqa: BLE001
        logging.getLogger("gestoria").warning("No se pudo archivar el extracto: %s", e)
        res["archivo_error"] = "Los apuntes se importaron, pero no se pudo archivar el fichero."
    _audit(session, user, centro_id, "gestoria.banco.import", "movimientos", request, res)
    return res


@router.get("/extractos")
def extractos_listar(centro_id: int = Depends(get_current_centro),
                     user: CurrentUser = Depends(VER_FACT),
                     session: Session = Depends(get_session)) -> dict:
    """Ficheros de extracto subidos, tal cual se entregaron. Accesible también al acceso
    restringido de Asesoría (misma lógica que los CSV de Debe/Haber)."""
    from sqlmodel import select
    from domain.models.gestoria import ExtractoSubido
    from domain.models.identidad import Usuario
    regs = session.exec(select(ExtractoSubido).where(
        ExtractoSubido.centro_id == centro_id).order_by(ExtractoSubido.id.desc()).limit(500)).all()
    nombres = {u.id: f"{u.nombre or ''} {u.apellidos or ''}".strip()
               for u in session.exec(select(Usuario)).all()}
    return {"extractos": [{
        "id": r.id, "nombre": r.nombre_original,
        "fecha": r.created_at.isoformat() if r.created_at else None,
        "tamano": r.tamano_bytes, "mime": r.mime,
        "subidoPor": nombres.get(r.subido_por) or "—",
        "importados": r.apuntes_importados, "omitidos": r.apuntes_omitidos,
    } for r in regs]}


@router.get("/extractos/{eid}/descargar")
def extracto_descargar(eid: int, centro_id: int = Depends(get_current_centro),
                       user: CurrentUser = Depends(VER_FACT),
                       session: Session = Depends(get_session)):
    """Devuelve el fichero ORIGINAL, byte a byte, con su nombre real."""
    from pathlib import Path as _Path
    from fastapi.responses import FileResponse
    from domain.models.gestoria import ExtractoSubido
    reg = session.get(ExtractoSubido, eid)
    if not reg or reg.centro_id != centro_id:          # guard anti-IDOR (multi-centro)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Extracto no encontrado")
    base = _Path(__file__).resolve().parents[1] / "media" / "extractos"
    ruta = (base / _Path(reg.archivo_url).name).resolve()
    if base.resolve() not in ruta.parents or not ruta.is_file():   # anti-traversal
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fichero no disponible")
    return FileResponse(str(ruta), media_type=reg.mime or "application/octet-stream",
                        filename=reg.nombre_original)


@router.get("/modelos-fiscales")
def modelos(ejercicio: Optional[int] = None,
            centro_id: int = Depends(get_current_centro),
            user: CurrentUser = Depends(require_permission(VER)),
            session: Session = Depends(get_session)) -> dict:
    return _svc(session).list_modelos(centro_id, ejercicio)


class ModeloIn(BaseModel):
    modelo: str
    ejercicio: int
    periodo: str
    estado: Optional[str] = None
    fecha_limite: Optional[date] = None
    cuota_resultante: Optional[float] = None


@router.put("/modelos-fiscales")
def modelo_upsert(data: ModeloIn, request: Request,
                  centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission(EDITAR)),
                  session: Session = Depends(get_session)) -> dict:
    res = _svc(session).upsert_modelo(centro_id, data.model_dump(exclude_none=True))
    _audit(session, user, centro_id, "gestoria.modelo.upsert",
           f"{data.modelo}-{data.periodo}-{data.ejercicio}", request)
    return res


@router.get("/calendario-tributario")
def calendario_tributario(ejercicio: int,
                          centro_id: int = Depends(get_current_centro),
                          user: CurrentUser = Depends(require_permission(VER)),
                          session: Session = Depends(get_session)) -> dict:
    from datetime import date as _date
    return _svc(session).calendario_tributario(centro_id, ejercicio, _date.today())


class GenerarModeloIn(BaseModel):
    modelo: str
    periodo: str
    ejercicio: int


@router.post("/modelos-fiscales/generar")
def modelo_generar(data: GenerarModeloIn, request: Request,
                   centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission(EDITAR)),
                   session: Session = Depends(get_session)) -> dict:
    res = _svc(session).generar_modelo(centro_id, data.modelo, data.periodo, data.ejercicio)
    _audit(session, user, centro_id, "gestoria.modelo.generar", "modelos", request, res)
    return res


@router.get("/envio/config")
def envio_config(centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission(VER)),
                 session: Session = Depends(get_session)) -> dict:
    return _svc(session).config_envio(centro_id)


class EnvioAutoIn(BaseModel):
    activo: bool
    dia: int
    tablas: list[str] = []


@router.put("/envio/config")
def envio_config_guardar(data: EnvioAutoIn, request: Request,
                         centro_id: int = Depends(get_current_centro),
                         user: CurrentUser = Depends(require_permission(EDITAR)),
                         session: Session = Depends(get_session)) -> dict:
    res = _svc(session).set_envio_auto(centro_id, activo=data.activo, dia=data.dia, tablas=data.tablas)
    _audit(session, user, centro_id, "gestoria.envio.config", "envio_auto", request, res)
    return res


class EnvioIn(BaseModel):
    tablas: list[str] = []
    anyo: int
    destino: Optional[str] = None


@router.post("/envio")
def envio(data: EnvioIn, request: Request,
          centro_id: int = Depends(get_current_centro),
          user: CurrentUser = Depends(require_permission(EDITAR)),
          session: Session = Depends(get_session)) -> dict:
    res = _svc(session).enviar_gestoria(centro_id, tablas=data.tablas, anyo=data.anyo, destino=data.destino)
    _audit(session, user, centro_id, "gestoria.envio", data.destino or "-", request, res)
    return res


# Secciones que puede descargar el acceso Asesoría (las DOS que ve: Facturas y Debe/Haber).
_SECCIONES_FACT = {"gastos", "bancos"}


@router.get("/envio/csv")
def envio_csv(tabla: str, anyo: int,
              centro_id: int = Depends(get_current_centro),
              user: CurrentUser = Depends(VER_FACT),
              session: Session = Depends(get_session)):
    """El MISMO CSV que Envío adjunta al email de la asesoría (misma fuente, mismas columnas,
    mismo nombre de fichero). Una sola verdad: descargar en la app ≡ recibirlo por correo."""
    from fastapi.responses import Response
    if tabla not in _SECCIONES_FACT:
        # el resto de secciones del envío (facturas emitidas, modelos, producción) exigen gestoría completa
        permisos = AuthService(session).permisos_de(user.usuario_id, centro_id)
        if VER not in permisos:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Permiso requerido: {VER}")
    svc = _svc(session)
    csv_bytes = svc._csv_de(svc._datos_seccion(centro_id, tabla, anyo))
    if not csv_bytes:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sin datos para ese año")
    return Response(content=csv_bytes, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{tabla}_{anyo}.csv"'})


# ═══════════════ ARCHIVO HISTÓRICO DE FACTURAS (2019-2024, solo consulta) ═══════════════
# Tabla facturas_historico AISLADA: ningún total/informe de Gestoría la lee (los números
# de años cerrados no cambian). Solo gestoría COMPLETA (no entra en el acceso Asesoría).

@router.get("/historico")
def historico_facturas(q: Optional[str] = Query(default=None),
                       anio: Optional[int] = Query(default=None),
                       centro_id: int = Depends(get_current_centro),
                       user: CurrentUser = Depends(require_permission(VER)),
                       session: Session = Depends(get_session)) -> dict:
    """Buscador del archivo documental: proveedor / NIF / nº factura / detalle, filtro por año."""
    from sqlalchemy import text
    where, params = ["centro_id = :centro"], {"centro": centro_id}
    if anio:
        where.append("anio = :anio")
        params["anio"] = anio
    if q and q.strip():
        where.append("(proveedor ILIKE :q OR nif ILIKE :q OR num_factura ILIKE :q OR detalle ILIKE :q)")
        params["q"] = f"%{q.strip()}%"
    sql = f"""SELECT id, anio, mes, num_factura, fecha, abonada, area_gasto, proveedor, nif,
                     detalle, base, iva, retencion, total, forma_pago, origen,
                     (pdf_ruta IS NOT NULL) AS tiene_pdf
              FROM facturas_historico WHERE {' AND '.join(where)}
              ORDER BY fecha DESC NULLS LAST, anio DESC, mes DESC NULLS LAST LIMIT 300"""
    rows = session.connection().execute(text(sql), params).mappings().all()
    anios = [r[0] for r in session.connection().execute(
        text("SELECT DISTINCT anio FROM facturas_historico WHERE centro_id=:centro ORDER BY 1 DESC"),
        {"centro": centro_id}).all()]
    return {"total": len(rows), "anios": anios, "data": [{
        "id": r["id"], "anio": r["anio"], "mes": r["mes"], "numFactura": r["num_factura"],
        "fecha": r["fecha"].isoformat() if r["fecha"] else None, "abonada": r["abonada"],
        "areaGasto": r["area_gasto"], "proveedor": r["proveedor"], "nif": r["nif"],
        "detalle": r["detalle"], "base": float(r["base"]) if r["base"] is not None else None,
        "iva": float(r["iva"]) if r["iva"] is not None else None,
        "retencion": float(r["retencion"]) if r["retencion"] is not None else None,
        "total": float(r["total"]) if r["total"] is not None else None,
        "formaPago": r["forma_pago"], "origen": r["origen"], "tienePdf": r["tiene_pdf"],
    } for r in rows]}


@router.get("/historico/{hid}/pdf")
def historico_pdf(hid: int, centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission(VER)),
                  session: Session = Depends(get_session)):
    from pathlib import Path as _Path

    from fastapi.responses import FileResponse

    from domain.models.economico import FacturaHistorico
    fh = session.get(FacturaHistorico, hid)
    if not fh or fh.centro_id != centro_id or not fh.pdf_ruta:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PDF no disponible")
    base = (_Path(__file__).resolve().parent.parent / "media").resolve()
    destino = (base / fh.pdf_ruta).resolve()
    if base not in destino.parents or not destino.is_file():   # guard anti path-traversal
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PDF no disponible")
    return FileResponse(destino, media_type="application/pdf",
                        headers={"Content-Disposition": "inline"})
