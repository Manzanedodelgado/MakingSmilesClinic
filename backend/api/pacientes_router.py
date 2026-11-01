"""PACIENTES — ficha, filiación y tarifas del paciente. Solo BBDD nueva (makingsmiles).

Sirve el área "Pacientes" de la app: búsqueda, cabecera de ficha, filiación (campos
core de `pacientes`) y tarifas asignadas. Lectura: permiso pacientes.ver ·
escritura: pacientes.editar (auditada). PII = datos RGPD: no se reproducen en logs.
"""
import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from sqlalchemy import case, delete as sa_delete, func, or_, text

from domain.models.economico import LINEA_CODIGO, LINEA_MUERTAS
from api.auth_deps import CurrentUser, get_current_centro, require_permission
from api.paciente_helper import _get_paciente
from api.audit_helper import _audit
from domain.services.facturacion import facturado_al_doctor
from application.services.auth_service import AuthService
from application.services.config_service import ConfigService
from application.services.multimedia_service import MultimediaService
from infrastructure.ia_dental_client import IaDentalNoDisponible, analizar_ortopantomografia
from domain.config.anamnesis import ANAMNESIS_CATALOGO, anamnesis_items
from domain.models.clinico import AlertaPaciente
from domain.models.dental import OdontogramaEntrada, PeriodontogramaMedida
from domain.models.documentos import DocumentoAdmin, DocumentoPaciente
from domain.models.core import Colaborador, Paciente, PacienteSeguro, Tratamiento
from domain.models.economico import (
    Cliente, EstadoPresupuesto, EstadoTratamiento, PacienteTarifa, Pago, Presupuesto,
    PresupuestoLinea, Tarifa, TratamientoRealizado,
)
from domain.models.gestoria import Deuda, DeudaPago
from domain.models.identidad import Usuario, UsuarioPeriodo
from infrastructure.config.db import get_session

router = APIRouter(prefix="/pacientes", tags=["pacientes · ficha"])


def _edad(fnac: Optional[date]) -> Optional[int]:
    if not fnac:
        return None
    hoy = date.today()
    return hoy.year - fnac.year - ((hoy.month, hoy.day) < (fnac.month, fnac.day))


def _tarifas_dto(session: Session, centro_id: int, paciente_id: int) -> dict:
    """Catálogo de tarifas del centro + las asignadas al paciente (activas)."""
    # TODAS las tarifas creadas en el centro (no solo activas): el doctor las ve todas en
    # Filiación y elige; en el perfil del paciente (cabecera) solo salen las asignadas.
    catalogo = session.exec(
        select(Tarifa).where(Tarifa.centro_id == centro_id).order_by(Tarifa.nombre)
    ).all()
    asignadas = session.exec(
        select(PacienteTarifa).where(PacienteTarifa.paciente_id == paciente_id, PacienteTarifa.activo == True)  # noqa: E712
    ).all()
    return {
        "catalogo": [{"id": t.id, "nombre": t.nombre} for t in catalogo],
        "asignadas": [a.tarifa_id for a in asignadas],
    }


def _tarifa_label(session: Session, centro_id: int, ids: list[int]) -> Optional[str]:
    if not ids:
        return None
    nombres = session.exec(select(Tarifa.nombre).where(Tarifa.id.in_(ids))).all()
    return " / ".join(n for n in nombres if n) or None


# ─────────────────────────── BUSCAR PACIENTE (autocompletar) ───────────────────────────
@router.get("/formas-pago")
def listar_formas_pago(solo_caja: bool = Query(True),
                       user: CurrentUser = Depends(require_permission("pacientes.ver")),
                       session: Session = Depends(get_session)) -> dict:
    """Catálogo único de formas de pago de pacientes (tabla `formas_pago`)."""
    from application.services.formas_pago_service import como_dict, formas_pago
    return {"formas": [como_dict(f) for f in formas_pago(session, solo_caja=solo_caja)]}


@router.get("/financieras")
def listar_financieras(centro_id: int = Depends(get_current_centro),
                       user: CurrentUser = Depends(require_permission("pacientes.ver")),
                       session: Session = Depends(get_session)) -> dict:
    """Catálogo de entidades financieras del centro."""
    from domain.models.economico import Financiera
    fs = session.exec(select(Financiera).where(Financiera.centro_id == centro_id, Financiera.activo == True)).all()
    return {"financieras": [{"id": f.id, "nombre": f.nombre, "comision_pct": float(f.comision_pct)} for f in fs]}


class CobroDeudaIn(BaseModel):
    deuda_id: Optional[int] = None    # sin cargo → pago a cuenta (o al presupuesto indicado)
    fecha: date
    importe: float                 # BRUTO (100% que paga el paciente)
    forma_pago_id: int
    neto: Optional[float] = None   # lo que recibe la clínica (tras comisión financiera)
    presupuesto_id: Optional[int] = None
    # Campos de financiación
    financiera_id: Optional[int] = None
    entrada: Optional[float] = None
    num_cuotas: Optional[int] = None
    interes_pct: Optional[float] = None
    cuota_mensual: Optional[float] = None


@router.post("/{paciente_id}/pagos", status_code=status.HTTP_201_CREATED)
def registrar_cobro(paciente_id: int, data: CobroDeudaIn, request: Request,
                    centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(require_permission("pacientes.editar")),
                    session: Session = Depends(get_session)) -> dict:
    """Cobro de un cargo desde el Plan económico de la ficha (misma Caja que Inicio)."""
    from decimal import Decimal
    from application.services.caja_service import Aplicacion, CajaService
    imp = Decimal(str(data.importe))
    aplic = [Aplicacion(importe=imp, deuda_id=data.deuda_id)] if data.deuda_id else []
    r = CajaService(session, centro_id).cobrar(
        paciente_id, data.forma_pago_id, data.fecha, aplic,
        neto=Decimal(str(data.neto)) if data.neto is not None else None,
        importe=imp, presupuesto_id=data.presupuesto_id,
        financiera_id=data.financiera_id,
        entrada=Decimal(str(data.entrada)) if data.entrada is not None else None,
        num_cuotas=data.num_cuotas,
        interes_pct=Decimal(str(data.interes_pct)) if data.interes_pct is not None else None,
        cuota_mensual=Decimal(str(data.cuota_mensual)) if data.cuota_mensual is not None else None)
    _audit(session, user, centro_id, "pagos.cobrar", f"pago:{r['pago_id']}", request,
           {"paciente_id": paciente_id, "importe": r["importe"], "forma_pago": r["forma_pago"],
            "deuda_id": data.deuda_id, "presupuesto_id": data.presupuesto_id,
            "financiera_id": data.financiera_id})
    return {"ok": True, "pagoId": r["pago_id"], "costeFinanciero": r["coste_financiero"],
            "saldo": r["saldo"]}


class ReasignarPagoIn(BaseModel):
    presupuesto_id: Optional[int] = None


class OperacionSaldoIn(BaseModel):
    importe: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2)
    fecha: date


class TraspasarSaldoIn(OperacionSaldoIn):
    paciente_destino_id: int


class DevolverSaldoIn(OperacionSaldoIn):
    motivo: str = Field(min_length=1, max_length=250)


def _saldo_pago(session: Session, pago: Pago) -> float:
    """Saldo reasignable de un pago nuevo = importe - imputaciones; el historico no se reasigna."""
    if pago.origen is not None or pago.importe <= 0:
        return 0.0
    from decimal import Decimal
    usado = session.exec(
        select(func.coalesce(func.sum(DeudaPago.pagado), 0))
        .where(DeudaPago.pago_id == pago.id)
    ).first() or Decimal(0)
    return float(pago.importe - usado)


def _saldo_disponible_paciente(session: Session, centro_id: int, paciente_id: int) -> Decimal:
    pagos = session.exec(select(Pago).where(
        Pago.centro_id == centro_id, Pago.paciente_id == paciente_id, Pago.anulado == False  # noqa: E712
    )).all()
    disponible = sum((Decimal(str(_saldo_pago(session, pago))) for pago in pagos), Decimal("0"))
    salidas = sum((Decimal(str(-pago.importe)) for pago in pagos
                   if pago.importe < 0 and (pago.num_transaccion or "").startswith(("TRASPASO:", "DEVOLUCION:"))), Decimal("0"))
    creditos_tratamiento = session.exec(select(func.coalesce(func.sum(-Deuda.importe_pendiente), 0)).where(
        Deuda.centro_id == centro_id, Deuda.paciente_id == paciente_id,
        Deuda.importe_pendiente < 0, Deuda.liquidada == True,  # noqa: E712
        Deuda.tratamiento_realizado_id.in_(select(TratamientoRealizado.id).where(
            TratamientoRealizado.centro_id == centro_id, TratamientoRealizado.paciente_id == paciente_id,
            TratamientoRealizado.num_transaccion.like("ABONO_TTO:%")
        ))
    )).first() or Decimal("0")
    deudas_pendientes = session.exec(select(func.coalesce(func.sum(Deuda.importe_pendiente), 0)).where(
        Deuda.centro_id == centro_id, Deuda.paciente_id == paciente_id,
        Deuda.importe_pendiente > 0, Deuda.liquidada == False  # noqa: E712
    )).first() or Decimal("0")
    neto = disponible + Decimal(str(creditos_tratamiento)) - Decimal(str(deudas_pendientes)) - salidas
    return max(Decimal("0"), neto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _crear_movimiento_saldo(session: Session, *, centro_id: int, paciente: Paciente,
                            importe: Decimal, fecha: date, referencia: str,
                            motivo: Optional[str] = None) -> Pago:
    movimiento = Pago(centro_id=centro_id, cliente_id=paciente.cliente_id, paciente_id=paciente.id,
                      fecha=fecha, importe=importe, forma_pago_id=None, num_transaccion=referencia,
                      motivo=motivo, automatico=False, anulado=False, liquidado=False)
    session.add(movimiento)
    session.flush()
    return movimiento


@router.post("/{paciente_id}/saldo/traspasar", status_code=status.HTTP_201_CREATED)
def traspasar_saldo(paciente_id: int, data: TraspasarSaldoIn, request: Request,
                    centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(require_permission("pacientes.editar")),
                    session: Session = Depends(get_session)) -> dict:
    """Traspasa crédito no aplicado con dos apuntes enlazados, sin afectar caja bancaria."""
    origen = session.exec(select(Paciente).where(
        Paciente.id == paciente_id, Paciente.centro_id == centro_id, Paciente.activo == True  # noqa: E712
    ).with_for_update()).first()
    destino = session.exec(select(Paciente).where(
        Paciente.id == data.paciente_destino_id, Paciente.centro_id == centro_id,
        Paciente.activo == True  # noqa: E712
    ).with_for_update()).first()
    if not origen or not destino:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    if origen.id == destino.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El paciente de destino debe ser distinto")
    importe = data.importe.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    disponible = _saldo_disponible_paciente(session, centro_id, paciente_id)
    if importe > disponible:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El importe supera el saldo disponible ({disponible:.2f} €)")
    ref = f"TRASPASO:{uuid4().hex}"
    salida = _crear_movimiento_saldo(session, centro_id=centro_id, paciente=origen,
                                     importe=-importe, fecha=data.fecha, referencia=f"{ref}:OUT")
    entrada = _crear_movimiento_saldo(session, centro_id=centro_id, paciente=destino,
                                      importe=importe, fecha=data.fecha, referencia=f"{ref}:IN")
    from application.services.caja_service import CajaService
    CajaService(session, centro_id).aplicar_saldo(destino.id, commit=False)
    session.commit()
    _audit(session, user, centro_id, "pagos.traspasar_saldo", f"traspaso:{ref}", request,
           {"paciente_origen": origen.id, "paciente_destino": destino.id, "importe": str(importe)})
    return {"ok": True, "referencia": ref, "pago_salida_id": salida.id, "pago_entrada_id": entrada.id,
            "importe": float(importe), "saldo_restante": float(disponible - importe)}


@router.post("/{paciente_id}/saldo/devolver", status_code=status.HTTP_201_CREATED)
def devolver_saldo(paciente_id: int, data: DevolverSaldoIn, request: Request,
                   centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission("pacientes.editar")),
                   session: Session = Depends(get_session)) -> dict:
    """Registra devolución parcial o total del crédito no aplicado del paciente."""
    paciente = session.exec(select(Paciente).where(
        Paciente.id == paciente_id, Paciente.centro_id == centro_id, Paciente.activo == True  # noqa: E712
    ).with_for_update()).first()
    if not paciente:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    if not data.motivo.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indica el motivo de la devolución")
    importe = data.importe.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    disponible = _saldo_disponible_paciente(session, centro_id, paciente_id)
    if importe > disponible:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El importe supera el saldo disponible ({disponible:.2f} €)")
    ref = f"DEVOLUCION:{uuid4().hex}"
    movimiento = _crear_movimiento_saldo(session, centro_id=centro_id, paciente=paciente,
                                          importe=-importe, fecha=data.fecha, referencia=f"{ref}:OUT",
                                          motivo=data.motivo.strip())
    session.commit()
    _audit(session, user, centro_id, "pagos.devolver_saldo", f"devolucion:{ref}", request,
           {"paciente_id": paciente.id, "importe": str(importe), "motivo": data.motivo.strip()})
    return {"ok": True, "referencia": ref, "pago_id": movimiento.id, "importe": float(importe),
            "saldo_restante": float(disponible - importe)}


@router.post("/{paciente_id}/actos/{acto_id}/marcar-fracasado", status_code=status.HTTP_201_CREATED)
def marcar_tratamiento_fracasado(paciente_id: int, acto_id: int, request: Request,
                                 centro_id: int = Depends(get_current_centro),
                                 user: CurrentUser = Depends(require_permission("pacientes.editar")),
                                 session: Session = Depends(get_session)) -> dict:
    """Mantiene el acto original y crea el mismo tratamiento en negativo como abono
    (lo escribe CajaService: un solo dueño de los actos realizados fuera de clínico/presupuestos)."""
    from application.services.caja_service import CajaService
    r = CajaService(session, centro_id).abonar_tratamiento_fracasado(
        paciente_id, acto_id, factura_anulada=_factura_acto_anulada)
    _audit(session, user, centro_id, "pagos.marcar_tratamiento_fracasado", f"acto:{acto_id}", request,
           {"paciente_id": paciente_id, "acto_original_id": acto_id,
            "acto_abono_id": r["acto_abono_id"], "deuda_credito_id": r["deuda_credito_id"],
            "importe": str(r["importe_abonado"])})
    return {"ok": True, **r}


@router.patch("/{paciente_id}/pagos/{pago_id}/liberar")
def liberar_pago(paciente_id: int, pago_id: int,
                 centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission("pacientes.editar")),
                 request: Request = None,
                 session: Session = Depends(get_session)) -> dict:
    """Libera un pago de su presupuesto asociado, dejándolo como saldo a cuenta."""
    pago = session.get(Pago, pago_id)
    if not pago or pago.centro_id != centro_id or pago.paciente_id != paciente_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pago no encontrado")
    if pago.presupuesto_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El pago ya está libre (a cuenta)")
    saldo = _saldo_pago(session, pago)
    if saldo <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El pago no tiene saldo disponible para liberar")
    pago.presupuesto_id = None
    session.add(pago)
    from application.services.caja_service import CajaService
    CajaService(session, centro_id).aplicar_saldo(paciente_id, commit=False)
    session.commit()
    _audit(session, user, centro_id, "pagos.liberar", f"pago:{pago_id}", request,
           {"paciente_id": paciente_id, "saldo_liberado": saldo})
    return {"ok": True, "saldo": saldo}


@router.patch("/{paciente_id}/pagos/{pago_id}/reasignar")
def reasignar_pago(paciente_id: int, pago_id: int, data: ReasignarPagoIn,
                   centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission("pacientes.editar")),
                   request: Request = None,
                   session: Session = Depends(get_session)) -> dict:
    """Reasigna un pago a otro presupuesto (o lo deja a cuenta si presupuesto_id es null)."""
    pago = session.get(Pago, pago_id)
    if not pago or pago.centro_id != centro_id or pago.paciente_id != paciente_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pago no encontrado")
    saldo = _saldo_pago(session, pago)
    if saldo <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El pago no tiene saldo disponible para reasignar")
    if data.presupuesto_id is not None:
        pre = session.get(Presupuesto, data.presupuesto_id)
        if not pre or pre.centro_id != centro_id or pre.paciente_id != paciente_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Presupuesto no encontrado")
        if pre.estado_id not in (3, 4, 5, 6):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo se puede asociar a presupuestos aceptados")
    anterior = pago.presupuesto_id
    pago.presupuesto_id = data.presupuesto_id
    session.add(pago)
    from application.services.caja_service import CajaService
    CajaService(session, centro_id).aplicar_saldo(paciente_id, commit=False)
    session.commit()
    _audit(session, user, centro_id, "pagos.reasignar", f"pago:{pago_id}", request,
           {"paciente_id": paciente_id, "anterior": anterior, "nuevo": data.presupuesto_id, "saldo": saldo})
    return {"ok": True, "saldo": saldo}


@router.get("/buscar")
def buscar(q: str = Query(..., min_length=2),
           limite: int = Query(20, ge=1, le=200),
           centro_id: int = Depends(get_current_centro),
           user: CurrentUser = Depends(require_permission("pacientes.ver")),
           session: Session = Depends(get_session)) -> dict:
    # Tokeniza: cada palabra debe casar con ALGUNA columna (nombre/apellidos/NumPac/NIF/
    # teléfono) y se exigen TODAS (AND entre palabras). Así "manzanedo delgado juan" casa
    # aunque nombre y apellidos vivan en columnas distintas.
    def token_cond(t: str):
        like = f"%{t}%"
        return or_(
            Paciente.nombre.ilike(like), Paciente.apellidos.ilike(like),
            Paciente.num_historia.ilike(f"{t}%"), Paciente.nif.ilike(f"{t}%"),
            Paciente.telefono_movil.ilike(like), Paciente.telefono_fijo.ilike(like),
        )
    # Relevancia. Ordenar solo por apellido alfabético hacía que buscando "manuel"
    # salieran antes las MANUELA con apellido por la A que los MANUEL de verdad: para el
    # buscador todo "contiene manuel" valía lo mismo. Ahora el que coincide mejor va antes.
    def token_rank(t: str):
        esc = re.escape(t)
        return case(
            (func.lower(Paciente.nombre) == t.lower(), 0),          # se llama exactamente así
            (Paciente.nombre.op("~*")(rf"\m{esc}\M"), 1),           # …o lo lleva ("José Manuel")
            (Paciente.apellidos.op("~*")(rf"\m{esc}\M"), 2),        # apellido exacto
            (Paciente.nombre.ilike(f"{t}%"), 3),                    # solo empieza igual (Manuela)
            (Paciente.apellidos.ilike(f"{t}%"), 4),
            else_=5,                                                 # coincide por dentro / NIF / teléfono
        )

    tokens = [t for t in q.split() if t]
    conds = [token_cond(t) for t in tokens]
    filtro = (Paciente.centro_id == centro_id, Paciente.activo == True, *conds)  # noqa: E712
    relevancia = sum((token_rank(t) for t in tokens[1:]), token_rank(tokens[0]))
    # Cuántos hay DE VERDAD. El desplegable enseña un tramo, pero callarse el resto es
    # engañoso: buscar "manuel" devolvía 20 de 114 sin que nada lo dijera, y quien busca
    # da por hecho que su paciente no está.
    total = session.exec(select(func.count(Paciente.id)).where(*filtro)).one()
    rows = session.exec(
        select(Paciente).where(*filtro)
        .order_by(relevancia, Paciente.apellidos, Paciente.nombre).limit(limite)
    ).all()
    return {"pacientes": [{
        "id": p.id, "num_historia": p.num_historia, "nombre": p.nombre or "", "apellidos": p.apellidos or "",
        "nif": p.nif, "telefono": p.telefono_movil or p.telefono_fijo,
    } for p in rows], "total": total, "mostrados": len(rows)}


# ─────────────────────────── CABECERA DE FICHA ───────────────────────────
@router.get("/{paciente_id}")
def cabecera(paciente_id: int,
             centro_id: int = Depends(get_current_centro),
             user: CurrentUser = Depends(require_permission("pacientes.ver")),
             session: Session = Depends(get_session)) -> dict:
    p = _get_paciente(session, centro_id, paciente_id)
    tar = _tarifas_dto(session, centro_id, paciente_id)
    # Alertas para el doctor: ítems CRÍTICOS de anamnesis marcados (alergias, marcapasos…)
    # + alertas clínicas activas. La lista alimenta el emergente; el contador, el parpadeo.
    criticos = set(ANAMNESIS_CATALOGO.get("criticos", []))
    anam_criticos = [a for a in (p.anamnesis or []) if a in criticos]
    alert_textos = session.exec(
        select(AlertaPaciente.texto).where(
            AlertaPaciente.paciente_id == paciente_id, AlertaPaciente.activo == True)  # noqa: E712
    ).all()
    alertas_lista = anam_criticos + [t for t in alert_textos if t]
    return {
        "id": p.id, "num_historia": p.num_historia, "nombre": p.nombre or "", "apellidos": p.apellidos or "",
        "nif": p.nif, "edad": _edad(p.fecha_nacimiento), "telefono_movil": p.telefono_movil,
        "tarifa": _tarifa_label(session, centro_id, tar["asignadas"]),
        "alertas_activas": len(alertas_lista), "alertas_lista": alertas_lista, "activo": p.activo,
    }


# ─────────────────────────── FILIACIÓN (campos core) ───────────────────────────
# poblacion_id: legado, apunta a la tabla `poblaciones` (corrupta, ver auditoría
# 27-sep-2026) y no tiene endpoint de escritura (no está en PacienteUpdate) —
# se devuelve tal cual por compatibilidad pero ningún informe lo usa ya
# (informes_catalogo.py resuelve Población/Provincia por CP contra el catálogo
# oficial nuevo: municipios/provincias/codigos_postales_geo).
_CORE_FIELDS = (
    "num_historia", "nombre", "apellidos", "nif", "fecha_nacimiento", "direccion", "cp",
    "poblacion_id", "telefono_fijo", "telefono_fijo2", "telefono_movil", "email", "descuento",
    "campo_libre_1", "campo_libre_2", "campo_libre_3", "notas", "fecha_alta",
    "acepta_lopd", "acepta_info", "acepta_whatsapp", "acepta_bots", "activo",
    # Responsable legal + datos médicos (cada uno en su columna, no en bolsa).
    "responsable_nombre", "responsable_nif", "responsable_parentesco",
    "grupo_sanguineo", "peso", "altura", "medico_cabecera", "tel_medico", "especialista",
)


@router.get("/{paciente_id}/filiacion")
def filiacion(paciente_id: int,
              centro_id: int = Depends(get_current_centro),
              user: CurrentUser = Depends(require_permission("pacientes.ver")),
              session: Session = Depends(get_session)) -> dict:
    p = _get_paciente(session, centro_id, paciente_id)
    data = {f: getattr(p, f) for f in _CORE_FIELDS}
    data["id"] = p.id
    data["edad"] = _edad(p.fecha_nacimiento)
    data["tiene_foto"] = p.foto_url is not None
    data["tarifas"] = _tarifas_dto(session, centro_id, paciente_id)
    data["anamnesis"] = p.anamnesis or []
    # Facturación → tabla clientes (vía cliente_id). Seguro → tabla paciente_seguros.
    cli = session.get(Cliente, p.cliente_id) if p.cliente_id else None
    data["facturacion"] = {
        "razon_social": cli.razon_social if cli else None, "nif": cli.nif if cli else None,
        "direccion": cli.direccion if cli else None, "iban": cli.iban if cli else None,
        "titular_cuenta": cli.titular_cuenta if cli else None, "forma_pago": cli.forma_pago if cli else None,
    }
    seg = session.exec(select(PacienteSeguro).where(
        PacienteSeguro.paciente_id == p.id, PacienteSeguro.activo == True).order_by(PacienteSeguro.id)).first()  # noqa: E712
    data["seguro"] = {"aseguradora": seg.aseguradora, "num_poliza": seg.num_poliza, "num_ss": seg.num_ss} if seg else {}
    return data


class PacienteUpdate(BaseModel):
    """Parche de filiación. Todos opcionales — solo se aplican los campos enviados."""
    nombre: Optional[str] = None
    apellidos: Optional[str] = None
    nif: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    direccion: Optional[str] = None
    cp: Optional[str] = None
    telefono_fijo: Optional[str] = None
    telefono_fijo2: Optional[str] = None
    telefono_movil: Optional[str] = None
    email: Optional[str] = None
    descuento: Optional[float] = None
    notas: Optional[str] = None
    acepta_lopd: Optional[bool] = None
    acepta_info: Optional[bool] = None
    acepta_whatsapp: Optional[bool] = None
    acepta_bots: Optional[bool] = None
    responsable_nombre: Optional[str] = None
    responsable_nif: Optional[str] = None
    responsable_parentesco: Optional[str] = None
    grupo_sanguineo: Optional[str] = None
    peso: Optional[float] = None
    altura: Optional[float] = None
    medico_cabecera: Optional[str] = None
    tel_medico: Optional[str] = None
    especialista: Optional[str] = None


@router.put("/{paciente_id}")
def actualizar(paciente_id: int, data: PacienteUpdate, request: Request,
               centro_id: int = Depends(get_current_centro),
               user: CurrentUser = Depends(require_permission("pacientes.editar")),
               session: Session = Depends(get_session)) -> dict:
    p = _get_paciente(session, centro_id, paciente_id)
    cambios = data.model_dump(exclude_unset=True)
    if not cambios:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nada que actualizar")
    fnac = cambios.get("fecha_nacimiento")
    if fnac and fnac > date.today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La fecha de nacimiento no puede ser futura")
    if "descuento" in cambios and cambios["descuento"] is not None and not (0 <= cambios["descuento"] <= 100):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El descuento debe estar entre 0 y 100")
    for k, v in cambios.items():
        setattr(p, k, v)
    p.updated_by = user.usuario_id
    session.add(p); session.commit()
    # PII: auditamos QUÉ campos, nunca sus valores.
    _audit(session, user, centro_id, "pacientes.editar", f"paciente:{paciente_id}", request,
           {"campos": sorted(cambios.keys())})
    return {"id": paciente_id}


# ─────────────────────────── TARIFAS ───────────────────────────
@router.get("/{paciente_id}/tarifas")
def tarifas(paciente_id: int,
            centro_id: int = Depends(get_current_centro),
            user: CurrentUser = Depends(require_permission("pacientes.ver")),
            session: Session = Depends(get_session)) -> dict:
    _get_paciente(session, centro_id, paciente_id)
    return _tarifas_dto(session, centro_id, paciente_id)


class TarifasIn(BaseModel):
    tarifa_ids: list[int]


@router.put("/{paciente_id}/tarifas")
def set_tarifas(paciente_id: int, data: TarifasIn, request: Request,
                centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(require_permission("pacientes.editar")),
                session: Session = Depends(get_session)) -> dict:
    _get_paciente(session, centro_id, paciente_id)
    validas = {t.id for t in session.exec(
        select(Tarifa).where(Tarifa.centro_id == centro_id, Tarifa.activo == True)).all()}  # noqa: E712
    pedidas = set(data.tarifa_ids)
    if not pedidas.issubset(validas):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Alguna tarifa no existe en este centro")
    actuales = session.exec(select(PacienteTarifa).where(PacienteTarifa.paciente_id == paciente_id)).all()
    by_tarifa = {a.tarifa_id: a for a in actuales}
    for tid in pedidas:                                   # alta / reactivación
        a = by_tarifa.get(tid)
        if a:
            a.activo = True; session.add(a)
        else:
            session.add(PacienteTarifa(paciente_id=paciente_id, tarifa_id=tid, fecha_alta=date.today(), activo=True))
    for tid, a in by_tarifa.items():                      # baja de las que sobran
        if tid not in pedidas and a.activo:
            a.activo = False; session.add(a)
    session.commit()
    _audit(session, user, centro_id, "pacientes.tarifas", f"paciente:{paciente_id}", request,
           {"tarifa_ids": sorted(pedidas)})
    return _tarifas_dto(session, centro_id, paciente_id)


# ─────────────────────────── ANAMNESIS (cuestionario de salud) ───────────────────────────
@router.get("/anamnesis/catalogo")
def anamnesis_catalogo(centro_id: int = Depends(get_current_centro),
                       user: CurrentUser = Depends(require_permission("pacientes.ver")),
                       session: Session = Depends(get_session)) -> dict:
    """Catálogo de ítems (6 secciones + críticos). CONFIG es la fuente; default = canónico."""
    return ConfigService(session).resolve("clinica.anamnesis", centro_id=centro_id, default=ANAMNESIS_CATALOGO)


class AnamnesisIn(BaseModel):
    items: list[str]


@router.put("/{paciente_id}/anamnesis")
def set_anamnesis(paciente_id: int, data: AnamnesisIn, request: Request,
                  centro_id: int = Depends(get_current_centro),
                  user: CurrentUser = Depends(require_permission("pacientes.editar")),
                  session: Session = Depends(get_session)) -> dict:
    p = _get_paciente(session, centro_id, paciente_id)
    cat = ConfigService(session).resolve("clinica.anamnesis", centro_id=centro_id, default=ANAMNESIS_CATALOGO)
    validos = {i for s in cat.get("secciones", []) for i in s.get("items", [])} or anamnesis_items()
    marcados = [i for i in dict.fromkeys(data.items) if i in validos]   # dedup + valida contra catálogo
    p.anamnesis = marcados
    p.updated_by = user.usuario_id
    session.add(p); session.commit()
    # PII clínica: auditamos el nº de ítems, nunca cuáles.
    _audit(session, user, centro_id, "pacientes.anamnesis", f"paciente:{paciente_id}", request,
           {"n_items": len(marcados)})
    return {"id": paciente_id, "anamnesis": marcados}


# ─────────────────────────── DATOS EXTRA DE FILIACIÓN ───────────────────────────
class FacturacionIn(BaseModel):
    razon_social: Optional[str] = None
    nif: Optional[str] = None
    direccion: Optional[str] = None
    iban: Optional[str] = None
    titular_cuenta: Optional[str] = None
    forma_pago: Optional[str] = None


@router.put("/{paciente_id}/facturacion")
def set_facturacion(paciente_id: int, data: FacturacionIn, request: Request,
                    centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(require_permission("pacientes.editar")),
                    session: Session = Depends(get_session)) -> dict:
    """Datos de facturación → tabla clientes (vía pacientes.cliente_id). Crea el cliente si no existe."""
    p = _get_paciente(session, centro_id, paciente_id)
    cli = session.get(Cliente, p.cliente_id) if p.cliente_id else None
    if not cli:
        cli = Cliente(centro_id=centro_id, nombre=p.nombre, apellidos=p.apellidos)
        session.add(cli); session.commit(); session.refresh(cli)
        p.cliente_id = cli.id; session.add(p); session.commit()
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(cli, k, v if v != "" else None)
    if cli.razon_social:
        cli.es_empresa = True
    session.add(cli); session.commit()
    _audit(session, user, centro_id, "pacientes.facturacion", f"paciente:{paciente_id}", request,
           {"cliente_id": cli.id, "campos": sorted(data.model_dump(exclude_unset=True).keys())})
    return {"id": paciente_id, "cliente_id": cli.id}


class SeguroIn(BaseModel):
    aseguradora: Optional[str] = None
    num_poliza: Optional[str] = None
    num_ss: Optional[str] = None


@router.put("/{paciente_id}/seguro")
def set_seguro(paciente_id: int, data: SeguroIn, request: Request,
               centro_id: int = Depends(get_current_centro),
               user: CurrentUser = Depends(require_permission("pacientes.editar")),
               session: Session = Depends(get_session)) -> dict:
    """Seguro principal del paciente → tabla paciente_seguros (upsert del activo)."""
    p = _get_paciente(session, centro_id, paciente_id)
    seg = session.exec(select(PacienteSeguro).where(
        PacienteSeguro.paciente_id == p.id, PacienteSeguro.activo == True).order_by(PacienteSeguro.id)).first()  # noqa: E712
    if not seg:
        seg = PacienteSeguro(paciente_id=p.id)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(seg, k, v if v != "" else None)
    session.add(seg); session.commit()
    _audit(session, user, centro_id, "pacientes.seguro", f"paciente:{paciente_id}", request,
           {"campos": sorted(data.model_dump(exclude_unset=True).keys())})
    return {"id": paciente_id}


# ─────────────────────────── PLAN ECONÓMICO (movimientos + saldo) ───────────────────────────
def _estado_deuda(d: Deuda) -> str:
    if d.adeudo < 0:
        return "A FAVOR"
    if d.incobrable:
        return "INCOBRABLE"
    if d.liquidada or d.importe_pendiente <= 0:
        return "LIQUIDADO"
    if d.importe_pendiente < d.adeudo:
        return "PARCIAL"
    return "PENDIENTE"


@router.get("/{paciente_id}/plan")
def plan_economico(paciente_id: int,
                   centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission("pacientes.ver")),
                   session: Session = Depends(get_session)) -> dict:
    """Cuenta corriente del paciente: movimientos (deudas), pagos sueltos y saldo.
    Regla dura: tratamientos_realizados NO tiene líneas de cobro; el cobro vive en deudas/pagos."""
    p = _get_paciente(session, centro_id, paciente_id)
    deudas = session.exec(
        select(Deuda).where(Deuda.paciente_id == p.id).order_by(Deuda.fecha_plazo)
    ).all()
    # Conceptos: título del presupuesto asociado (si lo hay).
    pre_ids = {d.presupuesto_id for d in deudas if d.presupuesto_id}
    titulos = {}
    if pre_ids:
        for pr in session.exec(select(Presupuesto).where(Presupuesto.id.in_(pre_ids))).all():
            titulos[pr.id] = pr.titulo or (f"Presupuesto #{pr.num_pre}" if pr.num_pre else None)
    movimientos = []
    for d in deudas:
        adeudo = float(d.adeudo or 0)
        pend = float(d.importe_pendiente or 0)
        # modalidad puede ser un código numérico migrado (p.ej. "0"): no sirve de concepto.
        modal = d.modalidad if (d.modalidad and not d.modalidad.isdigit()) else None
        movimientos.append({
            "id": d.id,
            "concepto": ("Abono por tratamiento fracasado" if adeudo < 0
                         else titulos.get(d.presupuesto_id) or modal or "Movimiento"),
            "fecha": d.fecha_plazo.isoformat() if d.fecha_plazo else None,
            "num_factura": d.num_factura,
            "importe": adeudo, "abonado": round(adeudo - pend, 2), "pendiente": pend,
            "tratamiento_realizado_id": d.tratamiento_realizado_id,
            "estado": _estado_deuda(d),
        })
    pagos = session.exec(
        select(Pago).where(Pago.paciente_id == p.id, Pago.anulado == False).order_by(Pago.fecha)  # noqa: E712
    ).all()
    from application.services.formas_pago_service import mapa_formas, nombre_forma
    formas = mapa_formas(session)
    cargado = round(sum(max(0.0, float(d.adeudo or 0)) for d in deudas), 2)
    pendiente = round(sum(max(0.0, float(d.importe_pendiente or 0)) for d in deudas), 2)
    ids_credito_tratamiento = set(session.exec(select(TratamientoRealizado.id).where(
        TratamientoRealizado.centro_id == centro_id, TratamientoRealizado.paciente_id == p.id,
        TratamientoRealizado.num_transaccion.like("ABONO_TTO:%")
    )).all())
    credito_tratamientos = round(sum(-float(d.importe_pendiente or 0) for d in deudas
                                     if d.tratamiento_realizado_id in ids_credito_tratamiento
                                     and float(d.importe_pendiente or 0) < 0), 2)
    # Saldo de cada pago = importe − lo aplicado a cargos. Queda a cuenta o para su presupuesto.
    from application.services.caja_service import CajaService
    usado = CajaService(session, centro_id)._aplicado([pg.id for pg in pagos])
    def _saldo(pg) -> float:
        if pg.origen is not None or float(pg.importe or 0) <= 0:   # migrado: sin saldo en la app
            return 0.0
        return round(float(pg.importe or 0) - float(usado.get(pg.id, 0)), 2)
    pre_pagos = {pg.presupuesto_id for pg in pagos if pg.presupuesto_id} - set(titulos)
    if pre_pagos:
        for pr in session.exec(select(Presupuesto).where(Presupuesto.id.in_(pre_pagos))).all():
            titulos[pr.id] = pr.titulo or (f"Presupuesto #{pr.num_pre}" if pr.num_pre else None)
    lista_pagos = [{"id": pg.id, "fecha": pg.fecha.isoformat(), "importe": float(pg.importe or 0),
                    "forma_pago": nombre_forma(formas, pg.forma_pago_id), "num_recibo": pg.num_recibo,
                    "referencia": pg.num_transaccion,
                    "saldo": _saldo(pg), "presupuesto_id": pg.presupuesto_id,
                    "asociado_a": ("Ajuste contable" if (pg.origen or "").startswith("AJUSTE:")
                                   else "Histórico GELITE") if pg.origen is not None
                                  else (titulos.get(pg.presupuesto_id) or "Presupuesto") if pg.presupuesto_id
                                  else ("Tratamientos" if usado.get(pg.id) else "A cuenta")}
                   for pg in pagos]
    salidas_saldo = sum((float(-pg.importe) for pg in pagos if pg.importe < 0 and
                         (pg.num_transaccion or "").startswith(("TRASPASO:", "DEVOLUCION:"))), 0.0)
    saldo_a_favor = round(sum(x["saldo"] for x in lista_pagos) - salidas_saldo + credito_tratamientos, 2)
    for item, pg in zip(lista_pagos, pagos):
        ref = pg.num_transaccion or ""
        if ref.startswith("TRASPASO:"):
            item["forma_pago"] = "Traspaso de saldo"
            item["asociado_a"] = "Traspaso enviado" if pg.importe < 0 else "Traspaso recibido"
        elif ref.startswith("DEVOLUCION:"):
            item["forma_pago"] = "Devolución de saldo"
            item["asociado_a"] = pg.motivo or "Devolución al paciente"
    # El histórico se conserva como un saldo agregado y explícitamente separado. Su procedencia
    # evita duplicar el submayor nuevo; no inferimos imputaciones por coincidencia de fecha/importe.
    historico = session.execute(text("""
        SELECT
          COALESCE((SELECT SUM(COALESCE(importe, 0) - COALESCE(descuento, 0))
                    FROM tratamientos_realizados
                    WHERE paciente_id = :pid AND estado_id = 5 AND origen IS NOT NULL), 0)
          - COALESCE((SELECT SUM(importe) FROM pagos
                      WHERE paciente_id = :pid AND anulado = FALSE AND origen IS NOT NULL), 0)
    """), {"pid": p.id}).scalar_one()
    saldo_historico = round(float(historico or 0), 2)
    saldo_total = round(saldo_historico + pendiente - saldo_a_favor, 2)
    return {
        "movimientos": movimientos,
        "pagos": lista_pagos,
        "totales": {"cargado": cargado, "abonado": round(cargado - pendiente, 2), "pendiente": pendiente,
                    "saldo_a_favor": saldo_a_favor, "saldo_historico": saldo_historico,
                    "saldo_total": saldo_total},
    }


# ─────────────────────────── PRESUPUESTOS ───────────────────────────
def _cutoff_3_meses() -> date:
    """Fecha de hace 3 meses (regla de caducidad de presupuestos)."""
    t = date.today()
    y, m = t.year, t.month - 3
    if m <= 0:
        y, m = y - 1, m + 12
    return date(y, m, min(t.day, 28))


def _neto_linea(l) -> float:
    """Importe neto de una línea de presupuesto: bruto − descuento (% o € según descuento_pct)."""
    bruto = float(l.precio_unitario or 0) * (l.cantidad or 1)
    desc = (bruto * float(l.descuento or 0) / 100.0) if l.descuento_pct else float(l.descuento or 0)
    return max(0.0, bruto - min(desc, bruto))


def _presupuestos_caducados(pres: list) -> list:
    """Presupuestos Nuevo/Entregado cuya fecha supera los 3 meses sin haber progresado
    (aceptado/en curso/parcial/finalizado/cancelado) → caducan a Anulado (estado 2).
    SOLO para presupuestos del sistema nuevo (fecha ≈ created_at). La historia migrada de
    GELITE (fecha años anterior a su importación) NO se toca, para no falsear el histórico.

    Función PURA (no escribe en BD): calcula qué presupuestos están caducados para que el
    GET los muestre como tal sin mutar nada. La escritura real la hace el job programado
    `_caducar_presupuestos` (infrastructure/scheduler.py) — un GET nunca debe tener efectos
    secundarios. Reutilizada por el router de personal y por el gateway de la app paciente."""
    _cut = _cutoff_3_meses()
    return [pr for pr in pres
            if pr.estado_id in (0, 1) and pr.fecha and pr.fecha < _cut
            and pr.created_at and abs((pr.created_at.date() - pr.fecha).days) < 90]


def _presupuestos_data(session: Session, centro_id: int, paciente_id: int) -> dict:
    """Lista de presupuestos del paciente con sus líneas. El total se calcula de las
    líneas (precio_unitario × cantidad): el campo `total` de cabecera no es fiable tras
    migración. GET puro, sin efectos secundarios (ver _presupuestos_caducados)."""
    p = _get_paciente(session, centro_id, paciente_id)
    pres = session.exec(
        select(Presupuesto).where(Presupuesto.paciente_id == p.id).order_by(Presupuesto.num_pre.desc())
    ).all()
    caducados_ids = {pr.id for pr in _presupuestos_caducados(pres)}
    if not pres:
        return {"presupuestos": [], "total_presupuestado": 0.0, "total_pagado": 0.0, "total_pendiente": 0.0}
    estados = {e.id: e.nombre for e in session.exec(select(EstadoPresupuesto)).all()}
    pre_ids = [pr.id for pr in pres]
    lineas = session.exec(select(PresupuestoLinea).where(PresupuestoLinea.presupuesto_id.in_(pre_ids))).all()
    linea_ids = [l.id for l in lineas]
    # Líneas ya realizadas (tienen un acto realizado enlazado) → para marcar/proteger en la UI.
    realizadas_set = set(session.exec(select(TratamientoRealizado.presupuesto_linea_id).where(
        TratamientoRealizado.presupuesto_linea_id.in_(linea_ids), TratamientoRealizado.estado_id == 5)).all()) if linea_ids else set()
    trat_ids = {ln.tratamiento_id for ln in lineas if ln.tratamiento_id}
    _trats = session.exec(select(Tratamiento).where(Tratamiento.id.in_(trat_ids))).all() if trat_ids else []
    nombres = {t.id: t.nombre for t in _trats}
    tipos = {t.id: t.tipo_actuacion for t in _trats}   # ámbito por línea (lo dicta el catálogo)
    mensualidad = {t.id: t.es_mensualidad for t in _trats}   # mensualidad → Uds = nº de mensualidades
    por_pre: dict[int, list] = {}
    for ln in lineas:
        por_pre.setdefault(ln.presupuesto_id, []).append(ln)
    # Pendiente por presupuesto (de deudas vinculadas) + totales globales pagado/pendiente.
    deudas = session.exec(select(Deuda).where(Deuda.paciente_id == p.id)).all()
    pend_por_pre: dict[int, float] = {}
    pagado_global, pendiente_global = 0.0, 0.0
    for d in deudas:
        pend = float(d.importe_pendiente or 0)
        adeudo = float(d.adeudo or 0)
        if d.presupuesto_id:
            pend_por_pre[d.presupuesto_id] = pend_por_pre.get(d.presupuesto_id, 0.0) + pend
        pendiente_global += pend
        pagado_global += max(0.0, adeudo - pend)
    out, total_global = [], 0.0
    for pr in pres:
        lns = sorted(por_pre.get(pr.id, []), key=lambda x: x.num_linea or 0)
        # El total excluye las líneas anuladas (no aceptadas en una aceptación parcial).
        total = round(sum(_neto_linea(l) for l in lns if l.estado not in LINEA_MUERTAS), 2)
        total_global += total
        # Caducado (regla 3 meses): se muestra como Anulado aunque el estado en BD aún no
        # se haya escrito — el job programado lo persiste; el GET nunca escribe.
        estado_id_mostrado = 2 if pr.id in caducados_ids else pr.estado_id
        out.append({
            "id": pr.id, "num": pr.num_pre, "fecha": pr.fecha.isoformat() if pr.fecha else None,
            "titulo": pr.titulo, "notas": pr.notas, "colaborador_id": pr.colaborador_id,
            "estado": estados.get(estado_id_mostrado) or "—", "estado_id": estado_id_mostrado,
            "total": total, "pendiente": round(pend_por_pre.get(pr.id, 0.0), 2),
            "lineas": [{
                "id": l.id, "pieza": l.pieza, "zona_boca": l.zona_boca,
                "colaborador_id": l.colaborador_id, "estado": LINEA_CODIGO.get(l.estado),
                "tratamiento_id": l.tratamiento_id,
                "tratamiento": nombres.get(l.tratamiento_id) or "—",
                "tipo_actuacion": tipos.get(l.tratamiento_id),
                "es_mensualidad": bool(mensualidad.get(l.tratamiento_id)),
                "realizada": l.id in realizadas_set,
                "cantidad": l.cantidad or 1, "precio": float(l.precio_unitario or 0),
                "descuento": float(l.descuento or 0), "descuento_pct": bool(l.descuento_pct),
            } for l in lns],
        })
    colaboradores = _doctores_higienistas_activos(session)
    return {"presupuestos": out, "total_presupuestado": round(total_global, 2),
            "total_pagado": round(pagado_global, 2), "total_pendiente": round(pendiente_global, 2),
            "colaboradores": colaboradores}


@router.get("/{paciente_id}/presupuestos")
def presupuestos(paciente_id: int,
                 centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission("pacientes.ver")),
                 session: Session = Depends(get_session)) -> dict:
    return _presupuestos_data(session, centro_id, paciente_id)


# ─────────────────────────── FICHA · PREVISTOS ───────────────────────────
@router.get("/{paciente_id}/previstos")
def previstos(paciente_id: int,
              centro_id: int = Depends(get_current_centro),
              user: CurrentUser = Depends(require_permission("pacientes.ver")),
              session: Session = Depends(get_session)) -> dict:
    """Tratamientos previstos (plan tras aceptar presupuesto), agrupados por presupuesto."""
    from domain.models.economico import TratamientoPrevisto
    p = _get_paciente(session, centro_id, paciente_id)
    filas = session.exec(
        select(TratamientoPrevisto).where(TratamientoPrevisto.paciente_id == p.id)
    ).all()
    if not filas:
        return {"presupuestos": []}
    linea_ids = [f.presupuesto_linea_id for f in filas if f.presupuesto_linea_id]
    lineas = {pl.id: pl for pl in session.exec(select(PresupuestoLinea).where(PresupuestoLinea.id.in_(linea_ids))).all()} if linea_ids else {}
    presu_ids = {l.presupuesto_id for l in lineas.values() if l.presupuesto_id}
    presus = {pr.id: pr for pr in session.exec(select(Presupuesto).where(Presupuesto.id.in_(presu_ids))).all()} if presu_ids else {}
    estados = {e.id: e.nombre for e in session.exec(select(EstadoPresupuesto)).all()}
    nombres_tto = {t.id: (t.nombre, t.tipo_actuacion) for t in session.exec(select(Tratamiento)).all()}
    # Agrupar por presupuesto
    por_presu: dict[int, list] = {}
    for f in filas:
        linea = lineas.get(f.presupuesto_linea_id)
        presu_id = linea.presupuesto_id if linea else None
        if presu_id:
            por_presu.setdefault(presu_id, []).append(f)
    out = []
    for presu_id, items in por_presu.items():
        presu = presus.get(presu_id)
        previstos_items = []
        for f in items:
            nom, tipo_act = nombres_tto.get(f.tratamiento_id, ("Sin tratamiento", None))
            linea = lineas.get(f.presupuesto_linea_id)
            previstos_items.append({
                "id": f.id,
                "tratamiento_id": f.tratamiento_id,
                "tratamiento": nom,
                "tipo_actuacion": tipo_act,
                "pieza": f.piezas,
                "zona_boca": f.zona_boca,
                "importe": float(f.importe or 0),
                "colaborador_id": f.colaborador_id,
                "etiqueta": None,
                "linea_id": f.presupuesto_linea_id or 0,
            })
        out.append({
            "id": presu_id,
            "num": presu.num_pre if presu else None,
            "estado": estados.get(presu.estado_id) if presu else "—",
            "fecha": str(presu.fecha) if presu and presu.fecha else None,
            "previstos": previstos_items,
        })
    return {"presupuestos": out}


# ─────────────────────────── FICHA · ACTOS CLÍNICOS ───────────────────────────
_RE_HIGIENE = re.compile(r"HIGIENE|LIMPIEZ|TARTRECT|CURETAJ|PERIO|MANTENIMIENTO", re.I)
_RE_PANO = re.compile(r"RADIO|PANORAM|ORTOPANT|CBCT|TAC", re.I)


def _doctores_map(session: Session) -> dict[int, str]:
    """colaborador_id → 'Nombre Apellidos' (vía periodo→usuario)."""
    rows = session.exec(
        select(Colaborador.id, Usuario.nombre, Usuario.apellidos)
        .join(UsuarioPeriodo, UsuarioPeriodo.id == Colaborador.periodo_id)
        .join(Usuario, Usuario.id == UsuarioPeriodo.usuario_id)
    ).all()
    return {cid: f"{nom} {ape or ''}".strip() for cid, nom, ape in rows}


def _doctores_higienistas_activos(session: Session) -> list[dict]:
    """Opciones del selector de doctor: solo PERSONAL CLÍNICO ACTIVO = doctores e higienistas
    (`usuario_periodos.staff_tipo` ∈ DOCTOR/HIGIENISTA). Quedan fuera recepción/auxiliar/dirección
    y los dados de baja (ex-doctores). `_doctores_map` sí conserva a todos para resolver el nombre
    del doctor en datos históricos (actos ya realizados)."""
    rows = session.exec(
        select(Colaborador.id, Usuario.nombre, Usuario.apellidos, UsuarioPeriodo.staff_tipo)
        .join(UsuarioPeriodo, UsuarioPeriodo.id == Colaborador.periodo_id)
        .join(Usuario, Usuario.id == UsuarioPeriodo.usuario_id)
        .where(Colaborador.activo == True,  # noqa: E712 (SQLAlchemy necesita ==)
               UsuarioPeriodo.staff_tipo.in_(["DOCTOR", "HIGIENISTA"]))
        .order_by(Usuario.nombre, Usuario.apellidos)
    ).all()
    # es_doctor=True solo los DOCTOR → el titular del presupuesto (doctor impreso) se limita a ellos;
    # las líneas admiten también HIGIENISTA (es_doctor=False).
    # `corto` = nombre + inicial del 1er apellido (para la columna estrecha de las líneas).
    def _corto(nom: str, ape: Optional[str]) -> str:
        ini = (ape or "").strip()[:1]
        return f"{nom} {ini}.".strip() if ini else (nom or "")
    return [{"id": cid, "nombre": f"{nom} {ape or ''}".strip(),
             "corto": _corto(nom, ape), "es_doctor": st == "DOCTOR"}
            for cid, nom, ape, st in rows]


def _factura_acto_anulada(session: Session, centro_id: int, acto: TratamientoRealizado) -> bool:
    """Solo desbloquea si hay factura anulada y rectificativa archivada enlazada."""
    invoice = None
    if getattr(acto, "factura_documento_id", None):
        invoice = session.exec(select(DocumentoAdmin).where(
            DocumentoAdmin.id == acto.factura_documento_id, DocumentoAdmin.centro_id == centro_id
        )).first()
    elif (acto.num_factura_e or "").strip():
        numero = acto.num_factura_e.strip()
        docs = session.exec(select(DocumentoAdmin).where(
            DocumentoAdmin.centro_id == centro_id, DocumentoAdmin.num_doc.is_not(None)
        )).all()
        matches = [d for d in docs if f"{d.serie or ''}{d.num_doc}" == numero]
        if len(matches) == 1:
            invoice = matches[0]
    if not invoice or not invoice.anulada:
        return False
    rect = session.exec(select(DocumentoPaciente.id).where(
        DocumentoPaciente.paciente_id == acto.paciente_id,
        DocumentoPaciente.factura_origen_id == invoice.id,
        DocumentoPaciente.archivo_url.is_not(None)
    ).limit(1)).first()
    return rect is not None

def _actos_data(session: Session, centro_id: int, paciente_id: int) -> dict:
    """Historial de actos clínicos REALIZADOS (tratamientos_realizados, estado=Realizado).
    Se excluyen los marcadores de cobro (sin importe) y los estados Previsto/Presupuestado/
    Previo-otra-clínica (esos no son 'realizados con nosotros'). Regla dura: aquí NO hay líneas de pago.
    Reutilizada por el router de personal y por el gateway de la app paciente."""
    p = _get_paciente(session, centro_id, paciente_id)
    filas = session.exec(
        select(TratamientoRealizado).where(
            TratamientoRealizado.paciente_id == p.id, TratamientoRealizado.importe.is_not(None),
            TratamientoRealizado.estado_id == 5,   # 5 = Realizado (mismo valor que pone crear_acto)
        ).order_by(TratamientoRealizado.fecha_inicio.desc())
    ).all()
    nombres = {t.id: t.nombre for t in session.exec(select(Tratamiento)).all()}
    actos_abono = [f.num_transaccion for f in filas if (f.num_transaccion or "").startswith("ABONO_TTO:")]
    ids_abonados = {int(ref.split(":")[1]) for ref in actos_abono
                    if len(ref.split(":")) > 2 and ref.split(":")[1].isdigit()}
    estados = {e.id: e.nombre for e in session.exec(select(EstadoTratamiento)).all()}
    factura_docs = session.exec(select(DocumentoAdmin).where(
        DocumentoAdmin.centro_id == centro_id, DocumentoAdmin.num_doc.is_not(None)
    )).all()
    factura_por_id = {d.id: d for d in factura_docs}
    facturas_por_numero: dict[str, list[DocumentoAdmin]] = {}
    for documento in factura_docs:
        facturas_por_numero.setdefault(f"{documento.serie or ''}{documento.num_doc}", []).append(documento)
    rectificadas_ids = set(session.exec(select(DocumentoPaciente.factura_origen_id).where(
        DocumentoPaciente.paciente_id == p.id, DocumentoPaciente.factura_origen_id.is_not(None),
        DocumentoPaciente.archivo_url.is_not(None)
    )).all())
    def factura_activa(acto: TratamientoRealizado) -> bool:
        if not acto.num_factura_e:
            return False
        invoice = factura_por_id.get(acto.factura_documento_id) if acto.factura_documento_id else None
        if invoice is None:
            matches = facturas_por_numero.get(acto.num_factura_e.strip(), [])
            invoice = matches[0] if len(matches) == 1 else None
        return not (invoice and invoice.anulada and invoice.id in rectificadas_ids)
    docs = _doctores_map(session)
    actos = []
    for f in filas:
        nombre = nombres.get(f.tratamiento_id)
        actos.append({
            "id": f.id, "fecha": f.fecha_inicio.isoformat() if f.fecha_inicio else None,
            "piezas": f.piezas, "zona_boca": f.zona_boca, "doctor": docs.get(f.colaborador_id) or "Inactivo",
            "tratamiento": nombre or (f.notas or "—"),
            "observaciones": f.notas if nombre else None,
            "importe": float(f.importe or 0), "estado": estados.get(f.estado_id) or "—",
            "facturado": facturado_al_doctor(f.fecha_inicio),
            "fracasado": f.id in ids_abonados,
            "factura_numero": f.num_factura_e,
            "factura_activa": factura_activa(f),
        })

    def _ultima(rx) -> Optional[str]:
        for a in actos:  # ya vienen ordenados por fecha desc
            if a["fecha"] and rx.search(a["tratamiento"] or ""):
                return a["fecha"]
        return None

    indicadores = {
        "ultima_higiene": _ultima(_RE_HIGIENE),
        "ultima_panoramica": _ultima(_RE_PANO),
        "ultima_visita": next((a["fecha"] for a in actos if a["fecha"]), None),
    }
    return {"actos": actos, "indicadores": indicadores}


@router.get("/{paciente_id}/actos")
def actos_clinicos(paciente_id: int,
                   centro_id: int = Depends(get_current_centro),
                   user: CurrentUser = Depends(require_permission("pacientes.ver")),
                   session: Session = Depends(get_session)) -> dict:
    return _actos_data(session, centro_id, paciente_id)


# ─────────────────────────── MULTIMEDIA (fotos/RX desde Google Drive) ───────────────────────────
@router.get("/{paciente_id}/multimedia")
def multimedia(paciente_id: int,
               centro_id: int = Depends(get_current_centro),
               user: CurrentUser = Depends(require_permission("pacientes.ver")),
               session: Session = Depends(get_session)) -> dict:
    """Lista las imágenes de la carpeta de Drive del paciente (separadas fotos / RX).
    Solo metadatos; el contenido se sirve por el endpoint /multimedia/{file_id}."""
    p = _get_paciente(session, centro_id, paciente_id)
    return MultimediaService(session).listar(centro_id, p)


@router.get("/{paciente_id}/multimedia/{file_id}")
def multimedia_archivo(paciente_id: int, file_id: str,
                       thumb: bool = Query(False),
                       centro_id: int = Depends(get_current_centro),
                       user: CurrentUser = Depends(require_permission("pacientes.ver")),
                       session: Session = Depends(get_session)) -> Response:
    """Proxy autenticado de una imagen del paciente (miniatura si ?thumb=1; si no, full).
    Solo sirve ficheros que cuelgan de la carpeta del paciente (anti-IDOR)."""
    p = _get_paciente(session, centro_id, paciente_id)
    res = MultimediaService(session).media(centro_id, p, file_id, thumb)
    if not res:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Imagen no encontrada")
    content, mime = res
    return Response(content=content, media_type=mime or "image/jpeg",
                    headers={"Cache-Control": "private, max-age=300"})


@router.post("/{paciente_id}/multimedia/{file_id}/analizar-ia")
def multimedia_analizar_ia(paciente_id: int, file_id: str,
                           centro_id: int = Depends(get_current_centro),
                           user: CurrentUser = Depends(require_permission("pacientes.ver")),
                           session: Session = Depends(get_session)) -> dict:
    """Analiza con IA una ortopantomografia del paciente (numeracion FDI, impactados, canal dentario
    inferior, seno maxilar). Misma guarda anti-IDOR que el proxy de imagenes. Solo sugerencias."""
    p = _get_paciente(session, centro_id, paciente_id)
    res = MultimediaService(session).media(centro_id, p, file_id, False)
    if not res:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Imagen no encontrada")
    try:
        return analizar_ortopantomografia(res[0])
    except IaDentalNoDisponible as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))


# ─────────────────────────── FOTO DE PERFIL ───────────────────────────
# Vive en media/pacientes/{id}/ (igual que Multimedia) → el guard de media_router la
# rechaza si se pide cruda; solo sale por este proxy, que sí comprueba paciente∈centro.
_FOTOS_DIR = Path(__file__).resolve().parent.parent / "media" / "pacientes"
_FOTO_EXT_OK = {"png", "jpg", "jpeg", "webp"}
_FOTO_MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}
_FOTO_MAX_BYTES = 5 * 1024 * 1024


def _foto_es_imagen(contenido: bytes, ext: str) -> bool:
    if ext == "png":
        return contenido.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in {"jpg", "jpeg"}:
        return contenido.startswith(b"\xff\xd8\xff")
    if ext == "webp":
        return len(contenido) >= 12 and contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP"
    return False


def _guardar_foto_perfil(session: Session, p: Paciente, user: CurrentUser, contenido: bytes, ext: str) -> None:
    carpeta = _FOTOS_DIR / str(p.id)
    carpeta.mkdir(parents=True, exist_ok=True)
    for viejo in carpeta.glob("foto.*"):   # solo puede haber una — evita huérfanas de otra extensión
        viejo.unlink(missing_ok=True)
    nombre = f"foto.{ext}"
    (carpeta / nombre).write_bytes(contenido)
    p.foto_url = nombre
    p.updated_by = user.usuario_id
    session.add(p); session.commit()


@router.post("/{paciente_id}/foto", status_code=201)
async def subir_foto(paciente_id: int, request: Request, file: UploadFile = File(...),
                      centro_id: int = Depends(get_current_centro),
                      user: CurrentUser = Depends(require_permission("pacientes.editar")),
                      session: Session = Depends(get_session)) -> dict:
    p = _get_paciente(session, centro_id, paciente_id)
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in _FOTO_EXT_OK:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Formato no admitido ({', '.join(sorted(_FOTO_EXT_OK))})")
    if file.size is not None and file.size > _FOTO_MAX_BYTES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La imagen no puede superar 5 MB")
    partes: list[bytes] = []
    total = 0
    while parte := await file.read(64 * 1024):
        total += len(parte)
        if total > _FOTO_MAX_BYTES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La imagen no puede superar 5 MB")
        partes.append(parte)
    contenido = b"".join(partes)
    if not _foto_es_imagen(contenido, ext):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El archivo no es una imagen válida")
    _guardar_foto_perfil(session, p, user, contenido, ext)
    _audit(session, user, centro_id, "pacientes.foto.subir", f"paciente:{p.id}", request,
           {"origen": "archivo", "formato": ext})
    return {"ok": True}


@router.post("/{paciente_id}/foto/drive", status_code=201)
def foto_desde_drive(paciente_id: int, request: Request,
                      centro_id: int = Depends(get_current_centro),
                      user: CurrentUser = Depends(require_permission("pacientes.editar")),
                      session: Session = Depends(get_session)) -> dict:
    """Busca «cara.jpeg» (o .jpg/.png/.webp) en la carpeta raíz de Drive del paciente y la
    usa como foto de perfil. 404 si no hay integración Drive activa o no existe el fichero."""
    p = _get_paciente(session, centro_id, paciente_id)
    res = MultimediaService(session).buscar_foto_cara(centro_id, p)
    if not res:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No se encontró CARA.JPEG en la carpeta de Drive del paciente")
    contenido, mime = res
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(mime, "jpg")
    if len(contenido) > _FOTO_MAX_BYTES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La imagen no puede superar 5 MB")
    if not _foto_es_imagen(contenido, ext):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El archivo de Drive no es una imagen válida")
    _guardar_foto_perfil(session, p, user, contenido, ext)
    _audit(session, user, centro_id, "pacientes.foto.subir", f"paciente:{p.id}", request,
           {"origen": "drive", "formato": ext})
    return {"ok": True}


@router.delete("/{paciente_id}/foto", status_code=204)
def borrar_foto(paciente_id: int, request: Request,
                 centro_id: int = Depends(get_current_centro),
                 user: CurrentUser = Depends(require_permission("pacientes.editar")),
                 session: Session = Depends(get_session)) -> None:
    p = _get_paciente(session, centro_id, paciente_id)
    if p.foto_url:
        for viejo in (_FOTOS_DIR / str(paciente_id)).glob("foto.*"):
            viejo.unlink(missing_ok=True)
        p.foto_url = None
        p.updated_by = user.usuario_id
        session.add(p); session.commit()
        _audit(session, user, centro_id, "pacientes.foto.borrar", f"paciente:{p.id}", request,
               {"origen": "perfil"})


@router.get("/{paciente_id}/foto")
def foto_perfil(paciente_id: int,
                centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(require_permission("pacientes.ver")),
                session: Session = Depends(get_session)) -> Response:
    p = _get_paciente(session, centro_id, paciente_id)
    if not p.foto_url:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sin foto")
    if p.foto_url not in {f"foto.{ext}" for ext in _FOTO_EXT_OK}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sin foto")
    ruta = _FOTOS_DIR / str(paciente_id) / p.foto_url
    if not ruta.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sin foto")
    mime = _FOTO_MIME.get(ruta.suffix.lstrip("."), "application/octet-stream")
    return Response(content=ruta.read_bytes(), media_type=mime,
                    headers={"Cache-Control": "private, max-age=300"})


def _fecha_es(d) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def _parse_fecha_es(s) -> date:
    """dd/mm/yyyy → date; vacío/'—'/inválido → hoy."""
    try:
        dd, mm, yy = str(s).split("/")
        return date(int(yy), int(mm), int(dd))
    except Exception:
        return date.today()


@router.get("/{paciente_id}/odontograma")
def odontograma(paciente_id: int,
                centro_id: int = Depends(get_current_centro),
                user: CurrentUser = Depends(require_permission("pacientes.ver")),
                session: Session = Depends(get_session)) -> dict:
    """Hallazgos del odontograma (editable). Contrato `teeth` idéntico al .37."""
    p = _get_paciente(session, centro_id, paciente_id)
    entradas = session.exec(
        select(OdontogramaEntrada).where(OdontogramaEntrada.paciente_id == p.id).order_by(OdontogramaEntrada.fecha)
    ).all()
    teeth = [{
        "pieza": e.pieza, "cara": e.cara or "-", "estado": e.estado,
        "obs": e.obs or "", "tipoRegistro": e.tipo_registro or "INICIAL",
        "fecha": _fecha_es(e.fecha),
    } for e in entradas]
    # Tratamientos REALIZADOS (solo lectura) → se pintan en el chart junto a los hallazgos.
    nombres = {t.id: t.nombre for t in session.exec(select(Tratamiento)).all()}
    realizados = session.exec(
        select(TratamientoRealizado).where(
            TratamientoRealizado.paciente_id == p.id, TratamientoRealizado.importe.is_not(None),
            TratamientoRealizado.estado_id == 5,   # 5 = Realizado (los previstos viven en tratamientos_previstos)
        ).order_by(TratamientoRealizado.fecha_inicio)
    ).all()
    rea = [{
        "piezas": r.piezas, "tratamiento": nombres.get(r.tratamiento_id) or (r.notas or ""),
        "fecha": _fecha_es(r.fecha_inicio),
    } for r in realizados if (nombres.get(r.tratamiento_id) or r.piezas)]
    return {"teeth": teeth, "realizados": rea}


class HallazgoIn(BaseModel):
    pieza: str
    estado: str
    cara: Optional[str] = None
    obs: Optional[str] = None
    tipoRegistro: Optional[str] = "INICIAL"
    fecha: Optional[str] = None


class OdontogramaIn(BaseModel):
    teeth: list[HallazgoIn] = []


@router.put("/{paciente_id}/odontograma")
def guardar_odontograma(paciente_id: int, data: OdontogramaIn, request: Request,
                        centro_id: int = Depends(get_current_centro),
                        user: CurrentUser = Depends(require_permission("pacientes.editar")),
                        session: Session = Depends(get_session)) -> dict:
    """Reemplaza el odontograma del paciente con la lista de hallazgos (autosave del editor)."""
    p = _get_paciente(session, centro_id, paciente_id)
    session.execute(sa_delete(OdontogramaEntrada).where(OdontogramaEntrada.paciente_id == p.id))
    for h in data.teeth:
        if not (h.pieza or "").strip() or not (h.estado or "").strip():
            continue
        session.add(OdontogramaEntrada(
            paciente_id=p.id, pieza=h.pieza.strip()[:10],
            cara=(h.cara if h.cara and h.cara != "-" else None),
            estado=h.estado.strip()[:60], obs=(h.obs or None),
            tipo_registro=(h.tipoRegistro or "INICIAL")[:20], fecha=_parse_fecha_es(h.fecha),
        ))
    session.commit()
    _audit(session, user, centro_id, "paciente.odontograma.guardar", f"paciente:{p.id}", request,
           {"hallazgos": len(data.teeth)})
    return {"ok": True, "n": len(data.teeth)}


# ─────────────────────────── PERIODONTOGRAMA ───────────────────────────
def _sitio(ps, rec, ss, ip) -> dict:
    return {"ps": int(ps or 0), "rec": int(rec or 0), "ss": bool(ss), "ip": bool(ip)}


# Orden de exploración GELITE (índice 0-31) → numeración FDI. Sup 18→28, Inf 48→38.
_PERIO_FDI = ["18", "17", "16", "15", "14", "13", "12", "11", "21", "22", "23", "24", "25", "26", "27", "28",
              "48", "47", "46", "45", "44", "43", "42", "41", "31", "32", "33", "34", "35", "36", "37", "38"]


def _pieza_fdi(pieza: str) -> str:
    """La BBDD migró pieza como índice 0-31; si ya es FDI (11-48) se respeta."""
    s = str(pieza).strip()
    if s.isdigit():
        n = int(s)
        if 0 <= n <= 31:
            return _PERIO_FDI[n]
    return s


def _perio_clave(m):
    return (m.fecha.isoformat() if m.fecha else "", m.exploracion_id or 0)


def _perio_response(rows) -> dict:
    """Construye el payload de un estudio (piezas por sitio + BOP% + bolsas≥4)."""
    piezas, bop_cnt, bop_tot, bolsas4 = {}, 0, 0, 0
    for m in rows:
        v = [_sitio(m.bolsa_1, m.recesion_1, m.sangrado_1, m.placa_1),
             _sitio(m.bolsa_2, m.recesion_2, m.sangrado_2, m.placa_2),
             _sitio(m.bolsa_3, m.recesion_3, m.sangrado_3, m.placa_3)]
        pal = [_sitio(m.bolsa_4, m.recesion_4, m.sangrado_4, m.placa_4),
               _sitio(m.bolsa_5, m.recesion_5, False, False),
               _sitio(m.bolsa_6, m.recesion_6, False, False)]
        piezas[_pieza_fdi(m.pieza)] = {"v": v, "p": pal, "mob": int(m.movilidad or 0)}
        for s in v + pal:
            bop_tot += 1
            if s["ss"]:
                bop_cnt += 1
            if s["ps"] >= 4:
                bolsas4 += 1
    bop = round((bop_cnt / bop_tot) * 100) if bop_tot else 0
    fecha = next((m.fecha.isoformat() for m in rows if m.fecha), None)
    return {"piezas": piezas, "bop": bop, "bolsas4": bolsas4, "fecha": fecha}


@router.get("/{paciente_id}/periodontograma")
def periodontograma(paciente_id: int,
                    exploracion_id: Optional[int] = Query(None),
                    centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(require_permission("pacientes.ver")),
                    session: Session = Depends(get_session)) -> dict:
    """Exploración periodontal por pieza (6 sitios). Por defecto la más reciente;
    con `exploracion_id` devuelve ese estudio concreto."""
    p = _get_paciente(session, centro_id, paciente_id)
    filas = session.exec(
        select(PeriodontogramaMedida).where(PeriodontogramaMedida.paciente_id == p.id)
    ).all()
    if not filas:
        return {"piezas": {}, "bop": 0, "bolsas4": 0, "fecha": None, "exploracion_id": None}
    if exploracion_id is not None:
        rows = [m for m in filas if (m.exploracion_id or 0) == exploracion_id]
        if not rows:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Estudio periodontal no encontrado")
    else:
        ultima = max(_perio_clave(m) for m in filas)
        rows = [m for m in filas if _perio_clave(m) == ultima]
    resp = _perio_response(rows)
    resp["exploracion_id"] = rows[0].exploracion_id
    return resp


@router.get("/{paciente_id}/periodontograma/estudios")
def periodontograma_estudios(paciente_id: int,
                             centro_id: int = Depends(get_current_centro),
                             user: CurrentUser = Depends(require_permission("pacientes.ver")),
                             session: Session = Depends(get_session)) -> dict:
    """Historial de estudios periodontales del paciente (uno por exploración)."""
    p = _get_paciente(session, centro_id, paciente_id)
    filas = session.exec(
        select(PeriodontogramaMedida).where(PeriodontogramaMedida.paciente_id == p.id)
    ).all()
    grupos: dict[int, list] = {}
    for m in filas:
        grupos.setdefault(m.exploracion_id or 0, []).append(m)
    estudios = []
    for eid, rows in grupos.items():
        r = _perio_response(rows)
        estudios.append({"exploracion_id": eid, "fecha": r["fecha"], "bop": r["bop"],
                         "bolsas4": r["bolsas4"], "n_piezas": len(rows)})
    estudios.sort(key=lambda e: (e["fecha"] or "", e["exploracion_id"]), reverse=True)
    return {"estudios": estudios}


class PerioSitioIn(BaseModel):
    ps: int = 0
    rec: int = 0
    ss: bool = False
    ip: bool = False


class PerioPiezaIn(BaseModel):
    v: list[PerioSitioIn] = []
    p: list[PerioSitioIn] = []
    mob: int = 0


class PerioStudyIn(BaseModel):
    piezas: dict[str, PerioPiezaIn]


@router.post("/{paciente_id}/periodontograma", status_code=201)
def crear_periodontograma(paciente_id: int, data: PerioStudyIn, request: Request,
                          centro_id: int = Depends(get_current_centro),
                          user: CurrentUser = Depends(require_permission("pacientes.editar")),
                          session: Session = Depends(get_session)) -> dict:
    """Registra un NUEVO estudio periodontal (nuevo exploracion_id, fecha de hoy)."""
    p = _get_paciente(session, centro_id, paciente_id)
    maxid = session.exec(
        select(func.max(PeriodontogramaMedida.exploracion_id)).where(PeriodontogramaMedida.paciente_id == p.id)
    ).first()
    nuevo_id = int(maxid or 0) + 1
    hoy = date.today()
    z = PerioSitioIn()
    n = 0
    for fdi, pz in data.piezas.items():
        v = (list(pz.v) + [z, z, z])[:3]
        pal = (list(pz.p) + [z, z, z])[:3]
        session.add(PeriodontogramaMedida(
            paciente_id=p.id, exploracion_id=nuevo_id, pieza=str(fdi), fecha=hoy,
            bolsa_1=v[0].ps, bolsa_2=v[1].ps, bolsa_3=v[2].ps,
            bolsa_4=pal[0].ps, bolsa_5=pal[1].ps, bolsa_6=pal[2].ps,
            recesion_1=v[0].rec, recesion_2=v[1].rec, recesion_3=v[2].rec,
            recesion_4=pal[0].rec, recesion_5=pal[1].rec, recesion_6=pal[2].rec,
            sangrado_1=v[0].ss, sangrado_2=v[1].ss, sangrado_3=v[2].ss, sangrado_4=pal[0].ss,
            placa_1=v[0].ip, placa_2=v[1].ip, placa_3=v[2].ip, placa_4=pal[0].ip,
            movilidad=max(0, min(3, pz.mob or 0)),
        ))
        n += 1
    session.commit()
    _audit(session, user, centro_id, "periodontograma.crear", f"perio:{p.id}:{nuevo_id}", request,
           {"exploracion_id": nuevo_id, "piezas": n})
    return {"exploracion_id": nuevo_id, "n": n}
