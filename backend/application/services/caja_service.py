"""Caja de recepción: lo que el paciente tiene por pagar y el registro del cobro.

Modelo: el acto clínico (tratamientos_realizados) NO lleva líneas de cobro. Lo cobrable vive
en `deudas`; el dinero recibido en `pagos`; y qué pago liquidó qué deuda en `deuda_pago`.
Un acto realizado que aún no tiene deuda se carga (crea su deuda) en el mismo momento
de cobrarlo, para que pago y deuda queden siempre enlazados.

CUENTA ECONÓMICA — un pago entra de una de tres maneras:
  1. Asociado a un TRATAMIENTO concreto (aplicación a su cargo): puede cubrir solo una parte,
     pero nunca más de lo que queda pendiente de ese tratamiento.
  2. Asociado a un PRESUPUESTO aceptado (`pagos.presupuesto_id`): queda como saldo y se va
     descontando de los tratamientos de ESE presupuesto según se realizan. Nunca paga
     tratamientos de otro presupuesto.
  3. A CUENTA, sin asociación: queda como saldo y de él se descuenta cualquier tratamiento.
Saldo de un pago = importe − lo ya aplicado en `deuda_pago`. Al realizar un tratamiento o al
recibir un pago con saldo, `aplicar_saldo` descuenta: primero del saldo del presupuesto del
tratamiento, después del saldo a cuenta; siempre en orden de fecha.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlmodel import Session, select

from domain.models.core import Paciente, Tratamiento
from application.services.formas_pago_service import como_dict, formas_pago
from domain.models.economico import FormaPago, Pago, Presupuesto, PresupuestoLinea, TratamientoRealizado
from domain.models.gestoria import Deuda, DeudaPago

_CENT = Decimal("0.01")

# Presupuesto que admite pagos asociados: Aceptado, En curso, Finalizado, Aceptado parcial.
PRESUPUESTO_ACEPTADO = (3, 4, 5, 6)


class CajaError(ValueError):
    """Cobro no válido → 422 (handler en main.py)."""


class CajaNoEncontrado(LookupError):
    """Paciente, cargo o acto ajeno o inexistente → 404 (handler en main.py)."""


def _q(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(_CENT, rounding=ROUND_HALF_UP)


@dataclass
class Aplicacion:
    importe: Decimal
    deuda_id: Optional[int] = None
    acto_id: Optional[int] = None


class CajaService:
    def __init__(self, session: Session, centro_id: int):
        self.s = session
        self.centro_id = centro_id

    def _anula(self, error: Exception) -> Exception:
        """Deshace lo pendiente del cobro (p. ej. una deuda recién creada) antes de fallar."""
        self.s.rollback()
        return error

    def _paciente(self, paciente_id: int) -> Paciente:
        p = self.s.get(Paciente, paciente_id)
        if not p or p.centro_id != self.centro_id:
            raise CajaNoEncontrado("Paciente no encontrado")
        return p

    def _actos_sin_cargo(self, paciente_id: int) -> list[TratamientoRealizado]:
        con_deuda = select(Deuda.tratamiento_realizado_id).where(
            Deuda.paciente_id == paciente_id, Deuda.tratamiento_realizado_id.is_not(None))
        return list(self.s.exec(select(TratamientoRealizado).where(
            TratamientoRealizado.centro_id == self.centro_id,
            TratamientoRealizado.paciente_id == paciente_id,
            TratamientoRealizado.estado_id == 5,
            TratamientoRealizado.importe > 0,
            # Con num_tto viene de GELITE: su cargo se importa en `deudas` sin enlazar al acto.
            TratamientoRealizado.num_tto.is_(None),
            TratamientoRealizado.id.not_in(con_deuda),
        ).order_by(TratamientoRealizado.fecha_inicio.desc())).all())

    def _deudas_abiertas(self, paciente_id: int) -> list[Deuda]:
        return list(self.s.exec(select(Deuda).where(
            Deuda.centro_id == self.centro_id, Deuda.paciente_id == paciente_id,
            Deuda.incobrable == False, Deuda.liquidada == False,  # noqa: E712
            Deuda.importe_pendiente > 0,
        ).order_by(Deuda.fecha_plazo, Deuda.id)).all())

    def _cargar(self, a: TratamientoRealizado, fecha: date) -> Deuda:
        """El cargo de un acto: lo devuelve si existe, si no lo crea (con su presupuesto)."""
        d = self.s.exec(select(Deuda).where(Deuda.tratamiento_realizado_id == a.id)).first()
        if d is not None:
            return d
        importe = _q(a.importe)
        if importe <= 0:
            raise CajaError("Ese tratamiento no tiene importe")
        pre_id = None
        if a.presupuesto_linea_id:
            linea = self.s.get(PresupuestoLinea, a.presupuesto_linea_id)
            pre_id = linea.presupuesto_id if linea else None
        nombre = self.s.get(Tratamiento, a.tratamiento_id).nombre if a.tratamiento_id else None
        d = Deuda(centro_id=self.centro_id, paciente_id=a.paciente_id, tratamiento_realizado_id=a.id,
                  presupuesto_id=pre_id, fecha_plazo=a.fecha_inicio or fecha, adeudo=importe,
                  importe_pendiente=importe, modalidad=(nombre or "Tratamiento")[:40])
        self.s.add(d)
        self.s.flush()
        return d

    def _aplicado(self, pago_ids: list[int]) -> dict[int, Decimal]:
        if not pago_ids:
            return {}
        filas = self.s.exec(select(DeudaPago).where(DeudaPago.pago_id.in_(pago_ids))).all()
        usado: dict[int, Decimal] = {}
        for dp in filas:
            usado[dp.pago_id] = usado.get(dp.pago_id, Decimal(0)) + _q(dp.pagado)
        return usado

    def saldo(self, pago: Pago) -> Decimal:
        """Lo que queda de un pago sin aplicar a ningún cargo. Un pago migrado no tiene saldo."""
        if pago.origen is not None:
            return Decimal("0.00")
        return _q(pago.importe) - self._aplicado([pago.id]).get(pago.id, Decimal(0))

    def _pagos_con_saldo(self, paciente_id: int) -> list[list]:
        pagos = list(self.s.exec(select(Pago).where(
            Pago.centro_id == self.centro_id, Pago.paciente_id == paciente_id,
            Pago.anulado == False, Pago.importe > 0,  # noqa: E712
            # Solo dinero nacido en la app. Los pagos migrados (origen GELITE:…) ya pagaron sus
            # tratamientos en GELITE y esa imputación aún no está aquí: no son saldo disponible.
            Pago.origen.is_(None),
        ).order_by(Pago.fecha, Pago.id)).all())
        usado = self._aplicado([p.id for p in pagos])
        return [[p, _q(p.importe) - usado.get(p.id, Decimal(0))] for p in pagos
                if _q(p.importe) - usado.get(p.id, Decimal(0)) > 0]

    def aplicar_saldo(self, paciente_id: int, *, commit: bool = True) -> dict:
        """Crea los cargos de actos realizados y aplica el saldo disponible.

        Para cada cargo abierto, por orden de fecha: primero el saldo de los pagos asociados a
        SU presupuesto, después el de los pagos a cuenta. Un pago asociado a un presupuesto
        nunca paga un cargo de otro. `commit=False` permite incluir esta operación en la
        transacción que creó los actos.
        """
        # El plan económico necesita el cargo aunque el paciente no tenga saldo a favor.
        for a in self._actos_sin_cargo(paciente_id):
            self._cargar(a, a.fecha_inicio or date.today())
        saldos = self._pagos_con_saldo(paciente_id)
        if not saldos:
            if commit:
                self.s.commit()
            return {"aplicado": 0.0, "imputaciones": 0}
        formas = {f.id: f.nombre for f in self.s.exec(select(FormaPago)).all()}
        aplicado, n = Decimal(0), 0
        for d in self._deudas_abiertas(paciente_id):
            orden = ([x for x in saldos if d.presupuesto_id and x[0].presupuesto_id == d.presupuesto_id]
                     + [x for x in saldos if x[0].presupuesto_id is None])
            for x in orden:
                pendiente = _q(d.importe_pendiente)
                if pendiente <= 0:
                    break
                if x[1] <= 0:
                    continue
                imp = min(x[1], pendiente)
                self.s.add(DeudaPago(deuda_id=d.id, pago_id=x[0].id, pagado=imp, fecha_pago=x[0].fecha,
                                     subtipo_pago=formas.get(x[0].forma_pago_id)))
                x[1] -= imp
                d.importe_pendiente = pendiente - imp
                if d.importe_pendiente <= 0:
                    d.importe_pendiente = Decimal("0.00")
                    d.liquidada = True
                self.s.add(d)
                aplicado += imp
                n += 1
        if commit:
            self.s.commit()
        return {"aplicado": float(aplicado), "imputaciones": n}

    def estado(self, paciente_id: int, desde: Optional[date] = None) -> dict:
        """Pendiente de cobro. `desde` limita los actos sin cargo (p. ej. los de hoy)."""
        self._paciente(paciente_id)
        actos = [a for a in self._actos_sin_cargo(paciente_id)
                 if desde is None or (a.fecha_inicio and a.fecha_inicio >= desde)]
        tto_ids = {a.tratamiento_id for a in actos if a.tratamiento_id}
        ttos = {t.id: t.nombre for t in self.s.exec(select(Tratamiento).where(Tratamiento.id.in_(tto_ids))).all()} if tto_ids else {}
        deudas = self._deudas_abiertas(paciente_id)
        return {
            "actos": [{
                "acto_id": a.id, "fecha": a.fecha_inicio.isoformat() if a.fecha_inicio else None,
                "concepto": ttos.get(a.tratamiento_id) or (a.notas or "Tratamiento")[:120],
                "piezas": a.piezas or a.zona_boca, "colaborador_id": a.colaborador_id,
                "importe": float(_q(a.importe)),
            } for a in actos],
            "deudas": [{
                "deuda_id": d.id, "fecha": d.fecha_plazo.isoformat() if d.fecha_plazo else None,
                "concepto": (d.modalidad if d.modalidad and not d.modalidad.isdigit() else None) or "Cargo pendiente",
                "adeudo": float(_q(d.adeudo)), "pendiente": float(_q(d.importe_pendiente)),
            } for d in deudas],
            "total": float(sum((_q(a.importe) for a in actos), Decimal(0)) + sum((_q(d.importe_pendiente) for d in deudas), Decimal(0))),
            "formas": [como_dict(f) for f in formas_pago(self.s, solo_caja=True)],
        }

    def cobrar(self, paciente_id: int, forma_pago_id: int, fecha: date, aplicaciones: list[Aplicacion],
               neto: Optional[Decimal] = None, importe: Optional[Decimal] = None,
               presupuesto_id: Optional[int] = None,
               financiera_id: Optional[int] = None, entrada: Optional[Decimal] = None,
               num_cuotas: Optional[int] = None, interes_pct: Optional[Decimal] = None,
               cuota_mensual: Optional[Decimal] = None) -> dict:
        """`neto`: solo financiación (lo que recibe la clínica; coste = importe − neto).
        `importe`: total del pago. Lo que no se aplique a los conceptos queda de saldo: a cuenta,
        o asociado a `presupuesto_id` si se indica (solo presupuestos aceptados del paciente)."""
        p = self._paciente(paciente_id)
        forma = self.s.get(FormaPago, forma_pago_id) if forma_pago_id else None
        if not forma or not forma.activo or not forma.en_caja:
            raise self._anula(CajaError("Forma de pago no válida"))
        if not aplicaciones and importe is None:
            raise self._anula(CajaError("Elige al menos un concepto a cobrar o indica un importe a cuenta"))
        if presupuesto_id is not None:
            pre = self.s.get(Presupuesto, presupuesto_id)
            if not pre or pre.centro_id != self.centro_id or pre.paciente_id != p.id:
                raise self._anula(CajaNoEncontrado("Presupuesto no encontrado"))
            if pre.estado_id not in PRESUPUESTO_ACEPTADO:
                raise self._anula(CajaError("Solo se puede asociar un pago a un presupuesto aceptado"))
        vistos: set[tuple[str, int]] = set()
        plan: list[tuple[Deuda, Decimal]] = []
        for ap in aplicaciones:
            imp = _q(ap.importe)
            if imp <= 0:
                raise self._anula(CajaError("Cada importe debe ser mayor que cero"))
            if (ap.deuda_id is None) == (ap.acto_id is None):
                raise self._anula(CajaError("Cada concepto es una deuda o un acto, no ambos"))
            clave = ("d", ap.deuda_id) if ap.deuda_id else ("a", ap.acto_id)
            if clave in vistos:
                raise self._anula(CajaError("Concepto repetido"))
            vistos.add(clave)
            if ap.deuda_id:
                # FOR UPDATE: dos cobros a la vez sobre el mismo cargo no pueden leer el mismo
                # pendiente y pagarlo dos veces; el segundo espera y ve lo que dejó el primero.
                d = self.s.exec(select(Deuda).where(Deuda.id == ap.deuda_id).with_for_update()).first()
                if not d or d.centro_id != self.centro_id or d.paciente_id != p.id:
                    raise self._anula(CajaNoEncontrado("Cargo no encontrado"))
                if d.incobrable or d.liquidada:
                    raise self._anula(CajaError("Ese cargo ya no admite cobros"))
            else:
                a = self.s.get(TratamientoRealizado, ap.acto_id)
                if not a or a.centro_id != self.centro_id or a.paciente_id != p.id or a.estado_id != 5:
                    raise self._anula(CajaNoEncontrado("Tratamiento no encontrado"))
                if a.num_tto is not None:
                    raise self._anula(CajaError("Ese tratamiento viene de GELITE: se cobra por su cargo importado"))
                try:
                    d = self._cargar(a, fecha)
                except CajaError as e:
                    raise self._anula(e)
            if imp > _q(d.importe_pendiente):
                raise self._anula(CajaError(f"El importe supera lo pendiente ({_q(d.importe_pendiente)} €)"))
            plan.append((d, imp))

        aplicado = sum((imp for _, imp in plan), Decimal(0))
        total = _q(importe) if importe is not None else aplicado
        if total <= 0:
            raise self._anula(CajaError("El importe del pago debe ser mayor que cero"))
        if total < aplicado:
            raise self._anula(CajaError(f"El pago ({total} €) es menor que lo aplicado a los conceptos ({aplicado} €)"))
        if neto is not None and not (Decimal(0) <= _q(neto) <= total):
            raise self._anula(CajaError("El neto financiado debe estar entre 0 y el importe del pago"))
        if financiera_id is not None:
            from domain.models.economico import Financiera
            fin = self.s.get(Financiera, financiera_id)
            if not fin or fin.centro_id != self.centro_id:
                raise self._anula(CajaNoEncontrado("Financiera no encontrada"))
        pago = Pago(centro_id=self.centro_id, paciente_id=p.id, cliente_id=p.cliente_id, fecha=fecha, importe=total,
                    neto=_q(neto) if neto is not None else total, forma_pago_id=forma.id,
                    presupuesto_id=presupuesto_id,
                    financiera_id=financiera_id,
                    entrada=_q(entrada) if entrada is not None else None,
                    num_cuotas=num_cuotas,
                    interes_pct=_q(interes_pct) if interes_pct is not None else None,
                    cuota_mensual=_q(cuota_mensual) if cuota_mensual is not None else None)
        self.s.add(pago)
        self.s.flush()
        for d, imp in plan:
            self.s.add(DeudaPago(deuda_id=d.id, pago_id=pago.id, pagado=imp, fecha_pago=fecha, subtipo_pago=forma.nombre))
            d.importe_pendiente = _q(d.importe_pendiente) - imp
            if d.importe_pendiente <= 0:
                d.importe_pendiente = Decimal("0.00")
                d.liquidada = True
            self.s.add(d)
        self.s.commit()
        if total > aplicado:
            self.aplicar_saldo(p.id)       # el sobrante se descuenta de lo que ya esté realizado
        return {"pago_id": pago.id, "importe": float(total), "saldo": float(self.saldo(pago)),
                "presupuesto_id": presupuesto_id, "forma_pago": forma.nombre,
                "forma_pago_id": forma.id, "conceptos": len(plan),
                "coste_financiero": float(total - _q(neto)) if neto is not None else 0.0}

    # ── Tratamiento fracasado: abono en negativo (antes vivía en pacientes_router) ──
    def abonar_tratamiento_fracasado(self, paciente_id: int, acto_id: int, *, factura_anulada) -> dict:
        """Mantiene el acto original y crea el mismo tratamiento en negativo, con su crédito
        a favor del paciente. `factura_anulada(session, centro_id, acto)` dice si la factura del
        acto ya está anulada con rectificativa (solo entonces se puede abonar un acto facturado).
        Mismos códigos HTTP que tenía la ruta: 404, 400 y 409."""
        from uuid import uuid4

        from fastapi import HTTPException, status
        from sqlalchemy import func

        paciente = self.s.exec(select(Paciente).where(
            Paciente.id == paciente_id, Paciente.centro_id == self.centro_id, Paciente.activo == True  # noqa: E712
        ).with_for_update()).first()
        original = self.s.exec(select(TratamientoRealizado).where(
            TratamientoRealizado.id == acto_id, TratamientoRealizado.paciente_id == paciente_id,
            TratamientoRealizado.centro_id == self.centro_id, TratamientoRealizado.estado_id == 5
        ).with_for_update()).first()
        if not paciente or not original:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Tratamiento realizado no encontrado")
        if Decimal(str(original.importe or 0)) <= 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Solo se puede marcar un tratamiento realizado con importe positivo")
        if original.num_factura_e and not factura_anulada(self.s, self.centro_id, original):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"El tratamiento está asociado a la factura {original.num_factura_e}. "
                                "Anula primero la factura.")
        prefijo = f"ABONO_TTO:{original.id}:"
        abonado_previo = self.s.exec(select(func.coalesce(func.sum(-TratamientoRealizado.importe), 0)).where(
            TratamientoRealizado.centro_id == self.centro_id, TratamientoRealizado.paciente_id == paciente_id,
            TratamientoRealizado.importe < 0, TratamientoRealizado.num_transaccion.like(f"{prefijo}%")
        )).first() or Decimal("0")
        importe = (Decimal(str(original.importe)) - Decimal(str(abonado_previo))).quantize(Decimal("0.01"))
        if importe <= 0:
            raise HTTPException(status.HTTP_409_CONFLICT, "El tratamiento ya tiene el abono completo")
        espejo = TratamientoRealizado(
            centro_id=original.centro_id, paciente_id=original.paciente_id, cliente_id=original.cliente_id,
            tratamiento_id=original.tratamiento_id, tarifa_precio_id=original.tarifa_precio_id,
            colaborador_id=original.colaborador_id, colaborador_aux_id=original.colaborador_aux_id,
            piezas=original.piezas, zona_boca=original.zona_boca, estado_id=original.estado_id,
            fecha_inicio=date.today(), fecha_fin=date.today(), actos=original.actos,
            tiempo_min=original.tiempo_min, importe=-importe, descuento=Decimal("0"),
            importe_descuento=Decimal("0"), importe_privado=-importe, importe_mutua=Decimal("0"),
            pendiente=-importe, num_transaccion=f"{prefijo}{uuid4().hex}",
            notas=f"Tratamiento fracasado; abono del acto original #{original.id}")
        self.s.add(espejo)
        self.s.flush()
        credito = Deuda(centro_id=self.centro_id, paciente_id=paciente_id, cliente_id=paciente.cliente_id,
                        tratamiento_realizado_id=espejo.id, fecha_plazo=date.today(),
                        adeudo=-importe, importe_pendiente=-importe,
                        modalidad="Abono tratamiento", liquidada=True)
        self.s.add(credito)
        self.s.commit()
        return {"acto_abono_id": espejo.id, "deuda_credito_id": credito.id,
                "importe_abonado": float(importe), "saldo_generado": float(importe)}
