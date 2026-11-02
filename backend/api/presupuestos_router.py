"""PRESUPUESTOS — edición (crear/editar/borrar) + búsqueda de catálogo. Solo BBDD nueva.

Separado de pacientes_router por tamaño (CLAUDE.md: máx 500 líneas/fichero). El listado de
presupuestos vive en pacientes_router; aquí van las escrituras (permiso pacientes.editar, auditadas)
y el catálogo de tratamientos con precio de tarifa (para las líneas del editor).
"""
import base64
import mimetypes
from collections import defaultdict
import os
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from infrastructure.external_apis.documento_paciente_pdf import render_presupuesto_pdf
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlmodel import Session, select

from infrastructure.external_apis.evolution_api import EvolutionError

from api.auth_deps import CurrentUser, get_current_centro, require_permission
from api.paciente_helper import _get_paciente, get_presupuesto_autorizado
from api.audit_helper import _audit
from application.services.auth_service import AuthService
from application.services.authorization_service import AuthorizationService
from application.services.config_service import ConfigService
from application.services.consentimiento_service import vigente_para_tratamiento
from application.services.presupuesto_service import (
    _clave, aceptar_entero, anular_tratamientos_en_previos, volcar_a_previstos,
)
from domain.models.core import Centro, Colaborador, Paciente, RazonSocial, Tratamiento
from domain.models.economico import (
    EstadoPresupuesto, PacienteTarifa, Presupuesto, PresupuestoLinea,
    PresupuestoPredisenado, PresupuestoPredisenadoLinea, TarifaPrecio,
    TratamientoRealizado,
)
from domain.models.identidad import Usuario, UsuarioPeriodo
from infrastructure.config.db import get_session
from infrastructure.events import emit

router = APIRouter(prefix="/pacientes", tags=["pacientes · presupuestos (edición)"])

# Estados de presupuesto (estados_presupuesto) y de línea (presupuesto_lineas.estado).
# Protocolo completo: docs/PROTOCOLO-PRESUPUESTOS.md (fuente de verdad del ciclo de vida).
EST_NUEVO, EST_ENTREGADO, EST_ANULADO, EST_ACEPTADO = 0, 1, 2, 3
EST_EN_CURSO, EST_FINALIZADO, EST_PARCIAL, EST_CANCELADO = 4, 5, 6, 7
# ABIERTOS (editables/anulables): SOLO Nuevo y Entregado. Aceptado/Parcial exigen Reabrir
# (que retira el plan) antes de editar; Anular jamás alcanza un presupuesto aceptado (usa Cancelar).
ABIERTOS = (EST_NUEVO, EST_ENTREGADO)
from domain.models.economico import (LINEA_PENDIENTE as LIN_PENDIENTE, LINEA_ACEPTADA as LIN_ACEPTADA,  # noqa: E402
    LINEA_ANULADA as LIN_ANULADA, LINEA_CANCELADA as LIN_CANCELADA, LINEA_REALIZADA as LIN_REALIZADA,
    LINEA_MUERTAS as LIN_MUERTAS)


def _tarifa_paciente(session: Session, paciente_id: int) -> Optional[int]:
    """Primera tarifa activa del paciente (para sugerir precios en el editor)."""
    row = session.exec(
        select(PacienteTarifa.tarifa_id).where(
            PacienteTarifa.paciente_id == paciente_id, PacienteTarifa.activo == True)  # noqa: E712
    ).first()
    return row


# ─────────────────────────── CATÁLOGO DE TRATAMIENTOS (con precio) ───────────────────────────
@router.get("/{paciente_id}/catalogo-tratamientos")
def catalogo_tratamientos(paciente_id: int, q: str = Query(..., min_length=2),
                          centro_id: int = Depends(get_current_centro),
                          user: CurrentUser = Depends(require_permission("pacientes.ver")),
                          session: Session = Depends(get_session)) -> dict:
    # MIGRACIÓN PILOTO: Usar AuthorizationService como fuente canónica
    auth_service = AuthorizationService(session, centro_id, user.usuario_id)
    auth_service.get_paciente(paciente_id)
    tarifa_id = _tarifa_paciente(session, paciente_id)
    like = f"%{q}%"
    trats = session.exec(
        select(Tratamiento).where(
            Tratamiento.activo == True,  # noqa: E712
            (Tratamiento.nombre.ilike(like)) | (Tratamiento.codigo.ilike(f"{q}%")),
        ).order_by(Tratamiento.nombre).limit(20)
    ).all()
    precios: dict[int, float] = {}
    if tarifa_id and trats:
        ids = [t.id for t in trats]
        for tp in session.exec(select(TarifaPrecio).where(
                TarifaPrecio.tarifa_id == tarifa_id, TarifaPrecio.tratamiento_id.in_(ids))).all():
            precios[tp.tratamiento_id] = float(tp.precio or 0)
    return {"tratamientos": [{
        "id": t.id, "codigo": t.codigo, "nombre": t.nombre, "precio": precios.get(t.id, 0.0),
        # Ámbito del catálogo (fuente de verdad): diente|arcada|cuadrante|sextante|tratamiento.
        "tipo_actuacion": t.tipo_actuacion,
        # Mensualidad → en el editor Uds = nº de mensualidades (editable), no se deriva de piezas.
        "es_mensualidad": t.es_mensualidad,
    } for t in trats]}


# ─────────────────────────── PRESUPUESTOS PREDISEÑADOS (plantillas) ───────────────────────────
@router.get("/{paciente_id}/presupuestos-predisenados")
def presupuestos_predisenados(paciente_id: int,
                              centro_id: int = Depends(get_current_centro),
                              user: CurrentUser = Depends(require_permission("pacientes.ver")),
                              session: Session = Depends(get_session)) -> dict:
    """Plantillas de presupuesto (prediseñados) con sus líneas y el precio según la tarifa del
    paciente, listas para volcar en el desglose. Origen: GELITE PresuTipo/PresuTipoTto."""
    # MIGRACIÓN PILOTO: Usar AuthorizationService como fuente canónica
    auth_service = AuthorizationService(session, centro_id, user.usuario_id)
    auth_service.get_paciente(paciente_id)
    plantillas = session.exec(select(PresupuestoPredisenado).where(
        PresupuestoPredisenado.centro_id == centro_id,
        PresupuestoPredisenado.activo == True,  # noqa: E712
    ).order_by(PresupuestoPredisenado.categoria, PresupuestoPredisenado.titulo)).all()
    if not plantillas:
        return {"predisenados": []}
    pids = [p.id for p in plantillas]
    lineas = session.exec(select(PresupuestoPredisenadoLinea).where(
        PresupuestoPredisenadoLinea.predisenado_id.in_(pids)).order_by(PresupuestoPredisenadoLinea.orden)).all()
    tids = {l.tratamiento_id for l in lineas}
    trats = {t.id: t for t in session.exec(select(Tratamiento).where(Tratamiento.id.in_(tids))).all()} if tids else {}
    # Precio según la tarifa del paciente (igual que el catálogo del editor).
    tarifa_id = _tarifa_paciente(session, paciente_id)
    precios: dict[int, float] = {}
    if tarifa_id and tids:
        for tp in session.exec(select(TarifaPrecio).where(
                TarifaPrecio.tarifa_id == tarifa_id, TarifaPrecio.tratamiento_id.in_(tids))).all():
            precios[tp.tratamiento_id] = float(tp.precio or 0)
    por_pre: dict[int, list] = defaultdict(list)
    for l in lineas:
        t = trats.get(l.tratamiento_id)
        if not t:
            continue
        por_pre[l.predisenado_id].append({
            "tratamiento_id": l.tratamiento_id, "tratamiento": t.nombre, "codigo": t.codigo,
            "precio": precios.get(l.tratamiento_id, 0.0), "tipo_actuacion": t.tipo_actuacion,
            "es_mensualidad": t.es_mensualidad,
        })
    return {"predisenados": [{
        "id": p.id, "titulo": p.titulo, "categoria": p.categoria or "Otros", "notas": p.notas,
        "lineas": por_pre.get(p.id, []),
    } for p in plantillas if por_pre.get(p.id)]}


# ─────────────────────────── CREAR / EDITAR / BORRAR PRESUPUESTO ───────────────────────────
class LineaIn(BaseModel):
    tratamiento_id: int
    pieza: Optional[str] = None          # diente concreto (FDI)
    # ámbito amplio: sextante_1..6 | cuadrante_1..4 | hemiarcada_derecha|izquierda |
    #                arcada_superior|inferior | boca_completa
    zona_boca: Optional[str] = None
    colaborador_id: Optional[int] = None  # doctor responsable de la línea
    precio: float = 0.0
    cantidad: int = 1
    descuento: float = 0.0     # valor del descuento: € si descuento_pct=False, % si True
    descuento_pct: bool = False  # True → `descuento` es un porcentaje sobre el bruto de la línea


class PresupuestoIn(BaseModel):
    titulo: Optional[str] = None
    notas: Optional[str] = None
    estado_id: Optional[int] = None
    fecha: Optional[str] = None
    colaborador_id: Optional[int] = None  # doctor de CABECERA: el que sale en el presupuesto impreso
    lineas: list[LineaIn] = []

    @field_validator("fecha")
    @classmethod
    def _fecha_iso_valida(cls, v: str | None) -> str | None:
        # Una fecha malformada antes se ignoraba en silencio (except ValueError:
        # pass) y el presupuesto conservaba la fecha vieja sin avisar. Falla
        # alto con 422: el front envía el estado completo y un typo no debe
        # parecer un guardado correcto.
        if v is None:
            return v
        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"fecha '{v}' no es ISO válida (YYYY-MM-DD)")
        return v


def _next_num(session: Session, centro_id: int, paciente_id: int) -> int:
    """Número de presupuesto INCREMENTAL POR PACIENTE: el siguiente al mayor de ESE paciente
    (no global del centro). Así cada paciente lleva su propia numeración 1, 2, 3…"""
    m = session.exec(select(Presupuesto.num_pre).where(
        Presupuesto.centro_id == centro_id,
        Presupuesto.paciente_id == paciente_id,
    ).order_by(Presupuesto.num_pre.desc())).first()
    return (m or 0) + 1


def _neto_linea_orm(l: "PresupuestoLinea") -> float:
    """Neto de una línea ya persistida (bruto − descuento, en € o %), nunca negativo."""
    bruto = float(l.precio_unitario or 0) * (l.cantidad or 1)
    desc_imp = (bruto * float(l.descuento or 0) / 100.0) if l.descuento_pct else float(l.descuento or 0)
    return max(0.0, bruto - min(desc_imp, bruto))


def _aplicar_lineas(session: Session, pre_id: int, lineas: list[LineaIn]) -> float:
    total = 0.0
    for i, ln in enumerate(lineas, start=1):
        bruto = ln.precio * (ln.cantidad or 1)
        desc_imp = (bruto * (ln.descuento or 0) / 100.0) if ln.descuento_pct else (ln.descuento or 0)
        total += max(0.0, bruto - min(desc_imp, bruto))
        session.add(PresupuestoLinea(
            presupuesto_id=pre_id, num_linea=i, tratamiento_id=ln.tratamiento_id,
            pieza=ln.pieza, zona_boca=ln.zona_boca, colaborador_id=ln.colaborador_id,
            cantidad=ln.cantidad or 1, precio_unitario=ln.precio,
            descuento=ln.descuento or 0, descuento_pct=ln.descuento_pct,
            estado=LIN_PENDIENTE,
        ))
    return round(total, 2)


@router.post("/{paciente_id}/presupuestos", status_code=201)
def crear_presupuesto(paciente_id: int, data: PresupuestoIn, request: Request,
                      centro_id: int = Depends(get_current_centro),
                      user: CurrentUser = Depends(require_permission("pacientes.editar")),
                      session: Session = Depends(get_session)) -> dict:
    # MIGRACIÓN PILOTO: Usar AuthorizationService como fuente canónica
    auth_service = AuthorizationService(session, centro_id, user.usuario_id)
    paciente = auth_service.get_paciente(paciente_id)
    pre = Presupuesto(centro_id=centro_id, paciente_id=paciente.id, fecha=date.today(),
                      num_pre=_next_num(session, centro_id, paciente.id), titulo=data.titulo, notas=data.notas,
                      colaborador_id=data.colaborador_id, estado_id=0)
    session.add(pre); session.commit(); session.refresh(pre)
    pre.total = _aplicar_lineas(session, pre.id, data.lineas)
    session.add(pre); session.commit()
    pid, num = pre.id, pre.num_pre
    # Regla re-presupuestar: lo propuesto aquí cancela su línea repetida (pendiente, no realizada)
    # en presupuestos anteriores vivos. Ver docs/PROTOCOLO-PRESUPUESTOS.md §Reglas 1.
    anuladas_previas = anular_tratamientos_en_previos(
        session, centro_id, paciente.id,
        [(ln.tratamiento_id, ln.pieza, ln.zona_boca) for ln in data.lineas], excluir_id=pid)
    _audit(session, user, centro_id, "presupuestos.crear", f"presupuesto:{pid}", request,
           {"num": num, "lineas": len(data.lineas), "anuladas_previas": anuladas_previas})
    emit("presupuesto.creado", {"presupuesto_id": pid, "centro_id": centro_id, "paciente_id": paciente.id})
    return {"id": pid, "num": num, "anuladas_previas": anuladas_previas}


@router.put("/{paciente_id}/presupuestos/{pre_id}")
def editar_presupuesto(paciente_id: int, pre_id: int, data: PresupuestoIn, request: Request,
                       centro_id: int = Depends(get_current_centro),
                       user: CurrentUser = Depends(require_permission("pacientes.editar")),
                       session: Session = Depends(get_session)) -> dict:
    pre = get_presupuesto_autorizado(session, centro_id, paciente_id, pre_id)
    # Editables: SOLO Nuevo y Entregado. Un Aceptado/Parcial tiene previstos enlazados a sus
    # líneas: editarlo las destruiría y dejaría el plan colgando → hay que Reabrir antes
    # (que retira el plan) y re-aceptar después. Protocolo: docs/PROTOCOLO-PRESUPUESTOS.md.
    if pre.estado_id not in ABIERTOS:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Solo se edita un presupuesto Nuevo o Entregado; reábrelo primero.")
    for ln in session.exec(select(PresupuestoLinea).where(PresupuestoLinea.presupuesto_id == pre_id)).all():
        session.delete(ln)
    if data.titulo is not None:
        pre.titulo = data.titulo
    if data.notas is not None:
        pre.notas = data.notas
    # Doctor de cabecera: se reemplaza siempre (el front envía el estado completo; null = sin doctor).
    pre.colaborador_id = data.colaborador_id
    if data.estado_id is not None:
        pre.estado_id = data.estado_id
    if data.fecha:
        pre.fecha = date.fromisoformat(data.fecha)  # ya validada en PresupuestoIn (422 si malformada)
    pre.total = _aplicar_lineas(session, pre_id, data.lineas)
    session.add(pre); session.commit()
    _audit(session, user, centro_id, "presupuestos.editar", f"presupuesto:{pre_id}", request,
           {"lineas": len(data.lineas), "estado_id": data.estado_id})
    return {"id": pre_id, "num": pre.num_pre}


@router.delete("/{paciente_id}/presupuestos/{pre_id}")
def borrar_presupuesto(paciente_id: int, pre_id: int, request: Request,
                       centro_id: int = Depends(get_current_centro),
                       user: CurrentUser = Depends(require_permission("pacientes.editar")),
                       session: Session = Depends(get_session)) -> dict:
    pre = get_presupuesto_autorizado(session, centro_id, paciente_id, pre_id)
    if pre.estado_id not in ABIERTOS:
        raise HTTPException(status.HTTP_409_CONFLICT,
                          "Solo se borran presupuestos Nuevo o Entregado. Reábrelo primero o usa Anular si es apropiado.")
    for ln in session.exec(select(PresupuestoLinea).where(PresupuestoLinea.presupuesto_id == pre_id)).all():
        session.delete(ln)
    session.delete(pre); session.commit()
    _audit(session, user, centro_id, "presupuestos.borrar", f"presupuesto:{pre_id}", request)
    return {"ok": True}


# ─────────────────────────── FLUJO: ENTREGAR / REABRIR / ANULAR / ACEPTAR ───────────────────────────


def _lineas(session: Session, pre_id: int) -> list[PresupuestoLinea]:
    return list(session.exec(select(PresupuestoLinea).where(
        PresupuestoLinea.presupuesto_id == pre_id).order_by(PresupuestoLinea.num_linea)).all())


@router.post("/{paciente_id}/presupuestos/{pre_id}/entregar")
def entregar_presupuesto(paciente_id: int, pre_id: int, request: Request,
                         centro_id: int = Depends(get_current_centro),
                         user: CurrentUser = Depends(require_permission("pacientes.editar")),
                         session: Session = Depends(get_session)) -> dict:
    """Marca el presupuesto como entregado (al imprimir o enviar por WhatsApp)."""
    pre = get_presupuesto_autorizado(session, centro_id, paciente_id, pre_id)
    pre.estado_id = EST_ENTREGADO
    session.add(pre); session.commit()
    _audit(session, user, centro_id, "presupuestos.entregar", f"presupuesto:{pre_id}", request)
    return {"id": pre_id, "estado_id": EST_ENTREGADO}


@router.post("/{paciente_id}/presupuestos/{pre_id}/reabrir")
def reabrir_presupuesto(paciente_id: int, pre_id: int, request: Request,
                        centro_id: int = Depends(get_current_centro),
                        user: CurrentUser = Depends(require_permission("pacientes.editar")),
                        session: Session = Depends(get_session)) -> dict:
    """Reabre un presupuesto no abierto (aceptado/parcial/en curso/finalizado/anulado/cancelado)
    → vuelve a Entregado, sus líneas a PENDIENTE y se RETIRA su plan (previstos): si ya no está
    aceptado, no hay nada planificado. Re-aceptar volverá a volcarlo (saltando lo ya realizado)."""
    pre = get_presupuesto_autorizado(session, centro_id, paciente_id, pre_id)
    if pre.estado_id in ABIERTOS:
        raise HTTPException(status.HTTP_409_CONFLICT, "El presupuesto ya está abierto.")
    pre.estado_id = EST_ENTREGADO
    ids = []
    for ln in _lineas(session, pre_id):
        ln.estado = LIN_PENDIENTE
        session.add(ln)
        ids.append(ln.id)
    if ids:
        session.connection().execute(
            text("DELETE FROM tratamientos_previstos WHERE presupuesto_linea_id = ANY(:ids)"), {"ids": ids})
    session.add(pre); session.commit()
    _audit(session, user, centro_id, "presupuestos.reabrir", f"presupuesto:{pre_id}", request)
    return {"id": pre_id, "estado_id": EST_ENTREGADO}


@router.post("/{paciente_id}/presupuestos/{pre_id}/anular")
def anular_presupuesto(paciente_id: int, pre_id: int, request: Request,
                       centro_id: int = Depends(get_current_centro),
                       user: CurrentUser = Depends(require_permission("pacientes.editar")),
                       session: Session = Depends(get_session)) -> dict:
    """Anula el presupuesto completo (no se borra: queda como histórico). SOLO una oferta
    Nueva/Entregada puede decaer: un presupuesto aceptado (3/4/6), finalizado (5) o cancelado (7)
    NO se anula — para abortar el resto de un aceptado existe /cancelar (Anulado ≠ Cancelado)."""
    pre = get_presupuesto_autorizado(session, centro_id, paciente_id, pre_id)
    if pre.estado_id not in ABIERTOS:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Solo se anula un presupuesto Nuevo o Entregado; "
                            "para abortar un aceptado usa Cancelar (resto no realizado).")
    pre.estado_id = EST_ANULADO
    for ln in _lineas(session, pre_id):
        ln.estado = LIN_ANULADA
        session.add(ln)
    session.add(pre); session.commit()
    _audit(session, user, centro_id, "presupuestos.anular", f"presupuesto:{pre_id}", request)
    return {"id": pre_id, "estado_id": EST_ANULADO}


class AceptarIn(BaseModel):
    lineas_aceptadas: list[int] = []        # ids de PresupuestoLinea aceptadas
    # En una aceptación PARCIAL el resto SIEMPRE pasa a un presupuesto nuevo.
    # `resto` decide el estado de ESE nuevo: 'mantener' (Entregado, activo) | 'anular' (Anulado).
    resto: str = "mantener"


@router.post("/{paciente_id}/presupuestos/{pre_id}/aceptar")
def aceptar_presupuesto(paciente_id: int, pre_id: int, data: AceptarIn, request: Request,
                        centro_id: int = Depends(get_current_centro),
                        user: CurrentUser = Depends(require_permission("pacientes.editar")),
                        session: Session = Depends(get_session)) -> dict:
    """Acepta el presupuesto. Si se aceptan TODAS las líneas → Aceptado.
    Si es PARCIAL: el original SIEMPRE queda 'Aceptado parcial' y las líneas NO aceptadas
    SIEMPRE pasan a un presupuesto NUEVO (del propio paciente). `resto` decide el estado de ese
    nuevo: 'mantener' (Entregado, activo, regla de los 3 meses) | 'anular' (Anulado)."""
    pre = get_presupuesto_autorizado(session, centro_id, paciente_id, pre_id)
    if pre.estado_id not in ABIERTOS:
        raise HTTPException(status.HTTP_409_CONFLICT,
                          "Solo se aceptan presupuestos Nuevo o Entregado. Reábrelo primero si está en Aceptado/Parcial/Finalizado.")
    lineas = _lineas(session, pre_id)
    if not lineas:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El presupuesto no tiene líneas")
    acc = set(data.lineas_aceptadas) & {l.id for l in lineas}
    if not acc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Selecciona al menos una línea a aceptar")
    no_acc = [l for l in lineas if l.id not in acc]
    aceptadas = [l for l in lineas if l.id in acc]
    for l in aceptadas:
        l.estado = LIN_ACEPTADA
        session.add(l)
    # Las líneas ACEPTADAS pasan a Tratamientos Previstos (planificado).
    volcar_a_previstos(session, centro_id, paciente_id, aceptadas)

    pre.fecha_aceptacion = date.today()
    nuevo_id = None
    if not no_acc:                                  # aceptado TOTAL
        pre.estado_id = EST_ACEPTADO
    else:                                           # aceptado PARCIAL → el resto SIEMPRE a un presupuesto nuevo
        estado_nuevo = EST_ANULADO if data.resto == "anular" else EST_ENTREGADO
        nuevo = Presupuesto(centro_id=centro_id, paciente_id=paciente_id, fecha=date.today(),
                            num_pre=_next_num(session, centro_id, paciente_id),
                            titulo=f"{pre.titulo or 'Presupuesto'} (resto no aceptado)",
                            colaborador_id=pre.colaborador_id, estado_id=estado_nuevo)
        session.add(nuevo); session.commit(); session.refresh(nuevo)
        for i, l in enumerate(no_acc, start=1):
            session.add(PresupuestoLinea(
                presupuesto_id=nuevo.id, num_linea=i, tratamiento_id=l.tratamiento_id,
                tarifa_precio_id=l.tarifa_precio_id, pieza=l.pieza, zona_boca=l.zona_boca,
                colaborador_id=l.colaborador_id, cantidad=l.cantidad, precio_unitario=l.precio_unitario,
                descuento=l.descuento, descuento_pct=l.descuento_pct, estado=LIN_PENDIENTE))
            session.delete(l)
        nuevo.total = round(sum(_neto_linea_orm(l) for l in no_acc), 2)
        session.add(nuevo)
        pre.estado_id = EST_PARCIAL                 # el original SIEMPRE queda Aceptado parcial
        nuevo_id = nuevo.id
    session.add(pre); session.commit()
    _audit(session, user, centro_id, "presupuestos.aceptar", f"presupuesto:{pre_id}", request,
           {"aceptadas": len(acc), "no_aceptadas": len(no_acc), "resto": data.resto})
    return {"id": pre_id, "estado_id": pre.estado_id, "nuevo_presupuesto_id": nuevo_id}


@router.post("/{paciente_id}/presupuestos/{pre_id}/duplicar", status_code=201)
def duplicar_presupuesto(paciente_id: int, pre_id: int, request: Request,
                         centro_id: int = Depends(get_current_centro),
                         user: CurrentUser = Depends(require_permission("pacientes.editar")),
                         session: Session = Depends(get_session)) -> dict:
    """Duplica un presupuesto (en CUALQUIER estado) → copia nueva en estado Nuevo, con sus líneas
    en PENDIENTE y la numeración per-paciente que toque. No toca el original."""
    pre = get_presupuesto_autorizado(session, centro_id, paciente_id, pre_id)
    lineas = _lineas(session, pre_id)
    copia = Presupuesto(centro_id=centro_id, paciente_id=pre.paciente_id, fecha=date.today(),
                        num_pre=_next_num(session, centro_id, pre.paciente_id),
                        titulo=pre.titulo, notas=pre.notas, colaborador_id=pre.colaborador_id, estado_id=EST_NUEVO)
    session.add(copia); session.commit(); session.refresh(copia)
    for i, l in enumerate(lineas, start=1):
        session.add(PresupuestoLinea(
            presupuesto_id=copia.id, num_linea=i, tratamiento_id=l.tratamiento_id,
            tarifa_precio_id=l.tarifa_precio_id, pieza=l.pieza, zona_boca=l.zona_boca,
            colaborador_id=l.colaborador_id, cantidad=l.cantidad, precio_unitario=l.precio_unitario,
            descuento=l.descuento, descuento_pct=l.descuento_pct, estado=LIN_PENDIENTE))
    copia.total = round(sum(_neto_linea_orm(l) for l in lineas), 2)
    session.add(copia); session.commit()
    _audit(session, user, centro_id, "presupuestos.duplicar", f"presupuesto:{copia.id}", request,
           {"origen": pre_id, "num": copia.num_pre})
    return {"id": copia.id, "num": copia.num_pre}


class RealizarEnCitaIn(BaseModel):
    lineas: list[LineaIn]
    colaborador_id: int      # doctor de la cita (regla del centro: NO hay realizado sin doctor)


@router.post("/{paciente_id}/presupuestos/realizar-en-cita", status_code=201)
def realizar_en_cita(paciente_id: int, data: RealizarEnCitaIn, request: Request,
                     centro_id: int = Depends(get_current_centro),
                     user: CurrentUser = Depends(require_permission("pacientes.editar")),
                     session: Session = Depends(get_session)) -> dict:
    """"Realizado en esta cita" (Escucha). REGLA: si lo realizado pertenece a un presupuesto del
    paciente aún NO aceptado (Nuevo/Entregado — p.ej. el generado en esta misma cita), ese
    presupuesto pasa a ACEPTADO ENTERO → todas sus líneas al plan (tratamientos_previstos) → el
    tratamiento realizado consume su previsto → cabecera En curso (o Finalizado si no queda plan).
    Solo lo que NO casa con ningún presupuesto pendiente sigue el ciclo atómico en un presupuesto
    propio (Entregado→Aceptado→Previsto→Realizado→Finalizado). Ver docs/PROTOCOLO-PRESUPUESTOS.md."""
    # MIGRACIÓN PILOTO: Usar AuthorizationService como fuente canónica
    auth_service = AuthorizationService(session, centro_id, user.usuario_id)
    paciente = auth_service.get_paciente(paciente_id)
    p = paciente   # el resto de la función usa `p`: sin esto, NameError en la primera consulta
    if not data.lineas:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indica al menos un tratamiento realizado")

    # Validación de consentimiento: cada tratamiento a realizarse debe tener consentimiento vigente
    for ln in data.lineas:
        if ln.tratamiento_id and not vigente_para_tratamiento(session, paciente.id, ln.tratamiento_id):
            tto = session.get(Tratamiento, ln.tratamiento_id)
            consent_key = tto.consentimiento_tipo if tto else None
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "consentimiento_requerido",
                    "tratamiento_id": ln.tratamiento_id,
                    "consentimiento_tipo": consent_key,
                }
            )

    hoy = date.today()

    # 1) Casar lo realizado contra líneas PENDIENTES de presupuestos Nuevo/Entregado (el más
    #    reciente primero: el generado en esta cita gana). Identidad clínica = _clave.
    filas = session.exec(
        select(PresupuestoLinea, Presupuesto)
        .join(Presupuesto, PresupuestoLinea.presupuesto_id == Presupuesto.id)
        .where(Presupuesto.centro_id == centro_id, Presupuesto.paciente_id == p.id,
               Presupuesto.estado_id.in_(ABIERTOS),
               PresupuestoLinea.estado.notin_(LIN_MUERTAS))).all()
    idx: dict[tuple, tuple] = {}
    for linea, pr in sorted(filas, key=lambda f: f[1].id, reverse=True):
        idx.setdefault(_clave(linea.tratamiento_id, linea.pieza, linea.zona_boca), (linea, pr))
    casadas: list[tuple] = []          # (linea, presupuesto)
    restantes: list[LineaIn] = []
    for ln in data.lineas:
        hit = idx.pop(_clave(ln.tratamiento_id, ln.pieza, ln.zona_boca), None)
        if hit:
            casadas.append(hit)
        else:
            restantes.append(ln)

    # 2) Los presupuestos con línea casada se ACEPTAN ENTEROS (todas sus líneas → previstos)…
    aceptados: dict[int, Presupuesto] = {}
    for _linea, pr in casadas:
        if pr.id not in aceptados:
            aceptar_entero(session, centro_id, p.id, pr)
            aceptados[pr.id] = pr
    # …y la línea realizada consume su previsto (todas sus fases: se hizo hoy).
    for linea, _pr in casadas:
        session.add(TratamientoRealizado(
            centro_id=centro_id, paciente_id=p.id, tratamiento_id=linea.tratamiento_id,
            piezas=linea.pieza, zona_boca=linea.zona_boca, fecha_inicio=hoy,
            importe=_neto_linea_orm(linea), presupuesto_linea_id=linea.id,
            colaborador_id=data.colaborador_id, estado_id=5))      # 5 = Realizado
        session.connection().execute(
            text("DELETE FROM tratamientos_previstos WHERE presupuesto_linea_id = :lid"), {"lid": linea.id})
        linea.estado = LIN_REALIZADA
        session.add(linea)
    session.commit()
    for pr in aceptados.values():      # En curso si queda plan; Finalizado si no queda nada
        queda = session.connection().execute(text("""
            SELECT 1 FROM tratamientos_previstos tp
            JOIN presupuesto_lineas pl ON pl.id = tp.presupuesto_linea_id
            WHERE pl.presupuesto_id = :pid LIMIT 1"""), {"pid": pr.id}).first()
        pr.estado_id = EST_EN_CURSO if queda else EST_FINALIZADO
        session.add(pr)
    session.commit()

    # 3) Lo NO casado: ciclo atómico en un presupuesto propio, como hasta ahora.
    pre = None
    anuladas = 0
    if restantes:
        pre = Presupuesto(centro_id=centro_id, paciente_id=p.id, fecha=hoy,
                          num_pre=_next_num(session, centro_id, p.id),
                          titulo="Realizado en cita", colaborador_id=data.colaborador_id,
                          estado_id=EST_ENTREGADO)
        session.add(pre); session.commit(); session.refresh(pre)
        pre.total = _aplicar_lineas(session, pre.id, restantes)
        lineas = _lineas(session, pre.id)
        for l in lineas:
            l.estado = LIN_ACEPTADA
            session.add(l)
        pre.fecha_aceptacion = hoy
        volcar_a_previstos(session, centro_id, p.id, lineas)       # el plan existe un instante…
        for l in lineas:                                           # …y se consume al realizarse
            session.add(TratamientoRealizado(
                centro_id=centro_id, paciente_id=p.id, tratamiento_id=l.tratamiento_id,
                piezas=l.pieza, zona_boca=l.zona_boca, fecha_inicio=hoy,
                importe=_neto_linea_orm(l), presupuesto_linea_id=l.id,
                colaborador_id=data.colaborador_id, estado_id=5))  # 5 = Realizado
            session.connection().execute(
                text("DELETE FROM tratamientos_previstos WHERE presupuesto_linea_id = :lid"), {"lid": l.id})
            l.estado = LIN_REALIZADA
            session.add(l)
        pre.estado_id = EST_FINALIZADO
        session.add(pre); session.commit()
        anuladas = anular_tratamientos_en_previos(
            session, centro_id, p.id,
            [(ln.tratamiento_id, ln.pieza, ln.zona_boca) for ln in restantes], excluir_id=pre.id)

    principal = next(iter(aceptados.values()), None) or pre
    _audit(session, user, centro_id, "presupuestos.realizar_en_cita", f"presupuesto:{principal.id}", request,
           {"num": principal.num_pre, "realizados": len(data.lineas), "casadas": len(casadas),
            "aceptados": list(aceptados), "anuladas_previas": anuladas})
    # Cuenta económica: lo realizado se descuenta del saldo del paciente (presupuesto / a cuenta).
    from application.services.caja_service import CajaService
    CajaService(session, centro_id).aplicar_saldo(p.id)
    return {"id": principal.id, "num": principal.num_pre, "estado_id": principal.estado_id,
            "realizados": len(data.lineas), "aceptados": list(aceptados), "anuladas_previas": anuladas}


class CancelarIn(BaseModel):
    lineas: list[int] = []   # líneas (no realizadas) a cancelar; vacío = TODO el resto no realizado


@router.post("/{paciente_id}/presupuestos/{pre_id}/cancelar")
def cancelar_presupuesto(paciente_id: int, pre_id: int, data: CancelarIn, request: Request,
                         centro_id: int = Depends(get_current_centro),
                         user: CurrentUser = Depends(require_permission("pacientes.editar")),
                         session: Session = Depends(get_session)) -> dict:
    """Cancela parte o el total del RESTO no realizado de un presupuesto Aceptado / En curso /
    Aceptado parcial → estado Cancelado. Las líneas ya realizadas NO se tocan."""
    pre = get_presupuesto_autorizado(session, centro_id, paciente_id, pre_id)
    if pre.estado_id not in (EST_ACEPTADO, EST_EN_CURSO, EST_PARCIAL):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Solo se cancela el resto de un presupuesto Aceptado, En curso o Aceptado parcial.")
    lineas = _lineas(session, pre_id)
    ids = [l.id for l in lineas]
    realizadas = set(session.exec(select(TratamientoRealizado.presupuesto_linea_id).where(
        TratamientoRealizado.presupuesto_linea_id.in_(ids), TratamientoRealizado.estado_id == 5)).all())
    # Candidatas = no anuladas y NO realizadas. sel = lo pedido (∩ candidatas) o TODAS las candidatas.
    candidatas = {l.id for l in lineas if l.estado not in LIN_MUERTAS and l.id not in realizadas}
    sel = (set(data.lineas) & candidatas) if data.lineas else candidatas
    if not sel:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No hay líneas no realizadas que cancelar.")
    for l in lineas:
        if l.id in sel:
            l.estado = LIN_CANCELADA
            session.add(l)
    session.connection().execute(
        text("DELETE FROM tratamientos_previstos WHERE presupuesto_linea_id = ANY(:ids)"), {"ids": list(sel)})
    # Cabecera: → Cancelado (7) SOLO si no queda ninguna línea viva PENDIENTE de realizar
    # ("se cancela DICHO tratamiento, no el presupuesto"). Si quedan aceptadas sin realizar,
    # el presupuesto sigue vivo en su estado real (3/6, o 4 si hay algo ya realizado).
    vivas = [l for l in lineas if l.estado not in LIN_MUERTAS]
    pendientes = [l for l in vivas if l.id not in realizadas]
    if not pendientes:
        pre.estado_id = EST_CANCELADO
    elif any(l.id in realizadas for l in vivas):
        pre.estado_id = EST_EN_CURSO
    elif pre.estado_id not in (EST_ACEPTADO, EST_PARCIAL):
        pre.estado_id = EST_ACEPTADO
    session.add(pre); session.commit()
    _audit(session, user, centro_id, "presupuestos.cancelar", f"presupuesto:{pre_id}", request,
           {"canceladas": len(sel), "estado_id": pre.estado_id})
    return {"id": pre_id, "estado_id": pre.estado_id, "canceladas": len(sel)}


# ─────────────────────────── DOCUMENTO (plantilla configurada en Config › Admin) ───────────────────────────
def _esc(v) -> str:
    """Escapa texto de BBDD antes de meterlo en el HTML del documento (evita stored-XSS al
    imprimir/generar PDF: un nombre/pieza con '<' no inyecta)."""
    return (str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


def _eur(x: float) -> str:
    s = f"{x:,.2f}"                     # 1,234.56
    return s.replace(",", "·").replace(".", ",").replace("·", ".") + " €"   # → 1.234,56 €


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
    except Exception:   # raiz: archivo local ilegible -> None; el PDF sale sin ese adjunto
        return None


def _una_zona_label(zona: str) -> str:
    if zona.startswith("sextante_"):
        return f"Sextante {zona.split('_')[1]}"
    if zona.startswith("cuadrante_"):
        return f"Cuadrante {zona.split('_')[1]}"
    if zona == "hemiarcada_derecha":
        return "Hemiarc. der."
    if zona == "hemiarcada_izquierda":
        return "Hemiarc. izq."
    if zona == "arcada_superior":
        return "Arcada sup."
    if zona == "arcada_inferior":
        return "Arcada inf."
    if zona == "boca_completa":
        return "Boca completa"
    return zona


def _zona_label(pieza: Optional[str], zona: Optional[str]) -> str:
    if pieza:
        return pieza
    if not zona:
        return "—"
    # varias zonas separadas por coma → "Cuadrante 1, Cuadrante 3"
    return ", ".join(_una_zona_label(z) for z in zona.split(",") if z)


@router.get("/{paciente_id}/presupuestos/{pre_id}/documento")
def documento_presupuesto(paciente_id: int, pre_id: int,
                          centro_id: int = Depends(get_current_centro),
                          user: CurrentUser = Depends(require_permission("pacientes.ver")),
                          session: Session = Depends(get_session)) -> dict:
    """Datos para imprimir el presupuesto con la PLANTILLA configurada en Config › Admin
    (configuraciones · documentos.plantillas · 'presupuesto'). El render (HTML) lo hace el
    front con el mismo motor que la pantalla de configuración → un único documento."""
    pac = _get_paciente(session, centro_id, paciente_id)
    pre = get_presupuesto_autorizado(session, centro_id, paciente_id, pre_id)
    lineas = [l for l in _lineas(session, pre_id) if l.estado not in LIN_MUERTAS]
    nombres = {t.id: t.nombre for t in session.exec(
        select(Tratamiento).where(Tratamiento.id.in_({l.tratamiento_id for l in lineas}))).all()} if lineas else {}
    # Profesional impreso: el doctor de CABECERA del presupuesto; si no se fijó, se cae al
    # primer colaborador con línea (presupuestos antiguos sin cabecera). Vía periodo → usuario.
    profesional = ""
    col_id = pre.colaborador_id or next((l.colaborador_id for l in lineas if l.colaborador_id), None)
    if col_id:
        row = session.exec(
            select(Usuario.nombre, Usuario.apellidos)
            .join(UsuarioPeriodo, UsuarioPeriodo.usuario_id == Usuario.id)
            .join(Colaborador, Colaborador.periodo_id == UsuarioPeriodo.id)
            .where(Colaborador.id == col_id)).first()
        if row:
            profesional = f"{row[0]} {row[1] or ''}".strip()

    filas, bruto_total, desc_total = [], 0.0, 0.0
    for l in lineas:
        bruto = float(l.precio_unitario or 0) * (l.cantidad or 1)
        dval = float(l.descuento or 0)
        es_pct = bool(l.descuento_pct)
        desc_imp = min((bruto * dval / 100.0) if es_pct else dval, bruto)   # € efectivos, sin pasar del bruto
        bruto_total += bruto
        desc_total += desc_imp
        # Etiqueta del descuento tal como se introdujo: "10 %" o "50,00 €"
        dto_txt = "—" if not dval else (f"{dval:g}".replace(".", ",") + " %" if es_pct else _eur(dval))
        filas.append(
            f"<tr><td>{_esc(_zona_label(l.pieza, l.zona_boca))}</td>"
            f"<td class='d' style='font-size:10.5px;line-height:1.2'>{_esc(nombres.get(l.tratamiento_id) or '—')}</td>"
            f"<td class='r'>{l.cantidad or 1}</td>"
            f"<td class='r'>{_eur(float(l.precio_unitario or 0))}</td>"
            f"<td class='r'>{dto_txt}</td><td class='r'>{_eur(max(0.0, bruto - desc_imp))}</td></tr>")
    total = round(bruto_total - desc_total, 2)

    estados = {e.id: e.nombre for e in session.exec(select(EstadoPresupuesto)).all()}
    centro = session.get(Centro, centro_id)
    razon = session.exec(select(RazonSocial).where(RazonSocial.centro_id == centro_id)).first()
    plantillas = ConfigService(session).resolve("documentos.plantillas", centro_id=centro_id, default={}) or {}

    return {
        "plantilla": plantillas.get("presupuesto"),     # None → el front usa la de por defecto
        "clinic": {
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
        },
        "datos": {
            # Nº de presupuesto formateado: PRERGD0000 + número real (per-paciente) → referencia legible.
            "numero": f"PRERGD0000{pre.num_pre or pre.id}", "fecha": pre.fecha.strftime("%d/%m/%Y") if pre.fecha else "",
            "estado": estados.get(pre.estado_id) or "—", "profesional": profesional or "—",
            "paciente": f"{pac.nombre or ''} {pac.apellidos or ''}".strip(),
            "numHistoria": str(pac.num_historia or ""),
            "pacienteInfo": " · ".join(x for x in [f"Hª {pac.num_historia}" if pac.num_historia else "",
                                                   f"NIF {pac.nif}" if pac.nif else ""] if x),
            "lineas": "".join(filas) or "<tr><td colspan='6' class='c'>Sin líneas</td></tr>",
            "subtotal": _eur(bruto_total), "descuento": _eur(desc_total) if desc_total else "—", "cobrado": _eur(0.0),
            "pendiente": _eur(total), "total": _eur(total),
            "titulo": pre.titulo or "", "notas": pre.notas or "", "odontograma": "",
        },
    }


# ─────────────────── PDF del presupuesto (generado en servidor) ───────────────────
def _presupuesto_pdf_datos(session: Session, centro_id: int, paciente_id: int, pre_id: int) -> dict:
    """Reúne los datos del presupuesto para el PDF de servidor. MISMO cálculo de importes
    que `/documento` (bruto − descuento, con descuento en % o en €), para que el PDF del
    servidor y el que pinta el navegador cuadren al céntimo."""
    pac = _get_paciente(session, centro_id, paciente_id)
    pre = get_presupuesto_autorizado(session, centro_id, paciente_id, pre_id)
    lineas = [l for l in _lineas(session, pre_id) if l.estado not in LIN_MUERTAS]
    nombres = {t.id: t.nombre for t in session.exec(
        select(Tratamiento).where(Tratamiento.id.in_({l.tratamiento_id for l in lineas}))).all()} if lineas else {}

    profesional = ""
    col_id = pre.colaborador_id or next((l.colaborador_id for l in lineas if l.colaborador_id), None)
    if col_id:
        row = session.exec(
            select(Usuario.nombre, Usuario.apellidos)
            .join(UsuarioPeriodo, UsuarioPeriodo.usuario_id == Usuario.id)
            .join(Colaborador, Colaborador.periodo_id == UsuarioPeriodo.id)
            .where(Colaborador.id == col_id)).first()
        if row:
            profesional = f"{row[0]} {row[1] or ''}".strip()

    filas, bruto_total, desc_total = [], 0.0, 0.0
    for l in lineas:
        bruto = float(l.precio_unitario or 0) * (l.cantidad or 1)
        dval = float(l.descuento or 0)
        desc_imp = min((bruto * dval / 100.0) if bool(l.descuento_pct) else dval, bruto)
        bruto_total += bruto
        desc_total += desc_imp
        filas.append({
            "concepto": nombres.get(l.tratamiento_id) or "—",
            "pieza": _zona_label(l.pieza, l.zona_boca),
            "cantidad": l.cantidad or 1,
            "precio": float(l.precio_unitario or 0),
            "descuento": desc_imp,
            "neto": max(0.0, bruto - desc_imp),
        })

    centro = session.get(Centro, centro_id)
    razon = session.exec(select(RazonSocial).where(RazonSocial.centro_id == centro_id)).first()
    return {
        "centro": {"nombre": centro.nombre if centro else None,
                   "direccion": centro.direccion if centro else None,
                   "poblacion": centro.poblacion if centro else None,
                   "cif": razon.cif if razon else None},
        "paciente": {"nombre": f"{pac.nombre or ''} {pac.apellidos or ''}".strip(), "nif": pac.nif},
        "numero": f"PRERGD0000{pre.num_pre or pre.id}",
        "fecha": pre.fecha, "profesional": profesional,
        "lineas": filas, "bruto": round(bruto_total, 2), "descuento": round(desc_total, 2),
        "total": round(bruto_total - desc_total, 2), "notas": pre.notas,
        "_pre": pre, "_pac": pac,
    }


def _generar_presupuesto_pdf(session: Session, centro_id: int, paciente_id: int, pre_id: int) -> Path:
    d = _presupuesto_pdf_datos(session, centro_id, paciente_id, pre_id)
    with NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf_path = Path(tmp.name)
    render_presupuesto_pdf(
        pdf_path, centro=d["centro"], paciente=d["paciente"], numero=d["numero"],
        fecha=d["fecha"] or date.today(), profesional=d["profesional"], lineas=d["lineas"],
        bruto=d["bruto"], descuento=d["descuento"], total=d["total"], notas=d["notas"],
    )
    return pdf_path


@router.get("/{paciente_id}/presupuestos/{pre_id}/pdf")
def presupuesto_pdf(paciente_id: int, pre_id: int,
                    centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(require_permission("pacientes.ver")),
                    session: Session = Depends(get_session)):
    """PDF del presupuesto generado en SERVIDOR (ReportLab). El endpoint `/documento`
    sigue existiendo y sirve al render HTML del navegador con plantilla configurable;
    este devuelve un PDF binario listo para imprimir o enviar."""
    pdf_path = _generar_presupuesto_pdf(session, centro_id, paciente_id, pre_id)
    pre = get_presupuesto_autorizado(session, centro_id, paciente_id, pre_id)
    return FileResponse(str(pdf_path), media_type="application/pdf",
                        filename=f"Presupuesto-{pre.num_pre or pre.id}.pdf",
                        background=BackgroundTask(os.unlink, str(pdf_path)))


class EnviarWhatsappIn(BaseModel):
    # pdf_base64 llega cuando el PDF lo genera el navegador (plantilla configurable + odontograma).
    # Si no llega, el servidor genera el PDF con render_presupuesto_pdf (apps nativas / cliente nuevo).
    pdf_base64: Optional[str] = None
    telefono: Optional[str] = None      # si no se indica, se usa el del paciente
    filename: Optional[str] = None
    caption: Optional[str] = None


@router.post("/{paciente_id}/presupuestos/{pre_id}/enviar-whatsapp")
def enviar_whatsapp(paciente_id: int, pre_id: int, data: EnviarWhatsappIn, request: Request,
                    centro_id: int = Depends(get_current_centro),
                    user: CurrentUser = Depends(require_permission("pacientes.editar")),
                    session: Session = Depends(get_session)) -> dict:
    """Envía el PDF del presupuesto (generado en cliente con la plantilla configurada +
    odontograma) por WhatsApp al móvil del paciente; marca el presupuesto Entregado."""
    pac = _get_paciente(session, centro_id, paciente_id)
    pre = get_presupuesto_autorizado(session, centro_id, paciente_id, pre_id)
    telefono = data.telefono or pac.telefono_movil or pac.telefono_fijo
    if not telefono:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El paciente no tiene teléfono móvil")
    if data.pdf_base64:
        # El navegador ya generó el PDF (plantilla configurable + odontograma): se usa tal cual.
        b64 = data.pdf_base64.split(",", 1)[1] if "," in data.pdf_base64 else data.pdf_base64
    else:
        # Sin PDF en la petición: lo genera el servidor (cliente nuevo / apps nativas).
        pdf_path = _generar_presupuesto_pdf(session, centro_id, paciente_id, pre_id)
        try:
            b64 = base64.b64encode(pdf_path.read_bytes()).decode()
        finally:
            os.unlink(pdf_path)
    filename = data.filename or f"Presupuesto-{pre.num_pre or pre.id}.pdf"
    caption = data.caption or f"Le enviamos su presupuesto Nº {pre.num_pre or pre.id}."
    from application.services.comunicacion_service import ComunicacionService
    try:
        res = ComunicacionService(session).enviar_documento(centro_id, telefono, b64, filename, caption)
    except EvolutionError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"WhatsApp no disponible: {e}")
    if pre.estado_id == EST_NUEVO:
        pre.estado_id = EST_ENTREGADO
        session.add(pre); session.commit()
    _audit(session, user, centro_id, "presupuestos.enviar_whatsapp", f"presupuesto:{pre_id}", request)
    return {"enviado": True, "estado_id": pre.estado_id, "messageId": res.get("messageId")}
