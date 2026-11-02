"""Imputación pago → deuda (capa de aplicación).

`deuda_pago` es la tabla puente que dice QUÉ PAGO SALDÓ QUÉ DEUDA. Existe en el esquema
desde la migración de GELITE pero nunca se pobló: ningún servicio la escribía. Sin ella,
`Deuda.importe_pendiente` no se actualiza nunca (13.281 de 13.528 deudas marcadas "no
liquidadas" tienen pendiente 0) y no hay forma de saber qué queda por cobrar.

QUÉ IMPUTA Y QUÉ NO
-------------------
Solo el caso INEQUÍVOCO: un pago y una deuda del MISMO paciente, con la MISMA fecha y el
MISMO importe, y que además sean el único candidato el uno del otro (1:1). Medido sobre el
archivo real: 7.138 emparejamientos, 592.460,95 €.

Lo demás NO se imputa. Un pago que podría saldar tres deudas distintas, o una deuda que
encaja con dos pagos, exige una regla contable (FIFO, proporcional, criterio del usuario)
que este motor no decide por su cuenta: repartir dinero entre deudas es una decisión de
negocio, y adivinarla mete un dato falso que después nadie vuelve a mirar.

Idempotente: no duplica imputaciones ya registradas. `execute=False` (por defecto)
previsualiza sin escribir nada.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text, update
from sqlmodel import Session, select

from domain.models.gestoria import Deuda, DeudaPago
from domain.models.economico import Pago

# Emparejamiento inequívoco: mismo paciente + misma fecha + mismo importe, y ÚNICO
# candidato por ambos lados (rn_d = rn_p = 1). El filtro `adeudo > 0` deja fuera las
# deudas a cero, que no son un cobro pendiente.
_SQL_PARES = text("""
WITH pares AS (
  SELECT d.id AS deuda_id, p.id AS pago_id, d.adeudo, p.fecha,
         (SELECT f.nombre FROM formas_pago f WHERE f.id = p.forma_pago_id) AS forma_pago,
         ROW_NUMBER() OVER (PARTITION BY d.id ORDER BY p.id) AS rn_d,
         ROW_NUMBER() OVER (PARTITION BY p.id ORDER BY d.id) AS rn_p
    FROM deudas d
    JOIN pagos p
      ON p.paciente_id = d.paciente_id
     AND p.anulado = false
     AND p.fecha = d.fecha_plazo
     AND ABS(p.importe - d.adeudo) < 0.01
   WHERE d.centro_id = :centro AND d.adeudo > 0
)
SELECT deuda_id, pago_id, adeudo, fecha, forma_pago
  FROM pares
 WHERE rn_d = 1 AND rn_p = 1
""")


class ImputacionService:
    def __init__(self, session: Session, centro_id: int) -> None:
        self.session = session
        self.centro_id = centro_id

    def imputar_inequivocos(self, *, execute: bool = False) -> dict:
        """Registra en `deuda_pago` los emparejamientos que no admiten duda.

        Devuelve el recuento y el importe. Con `execute=False` solo informa: es la misma
        pauta que el resto de motores del área (conciliación, buzón, tarjetas).
        """
        filas = self.session.connection().execute(
            _SQL_PARES, {"centro": self.centro_id}).mappings().all()

        # Ya imputados: la tabla es la fuente de verdad de lo hecho, así que re-ejecutar
        # no duplica (idempotencia).
        ya = {(r.deuda_id, r.pago_id) for r in self.session.exec(select(DeudaPago)).all()}

        nuevos = [f for f in filas if (f["deuda_id"], f["pago_id"]) not in ya]
        importe = sum((Decimal(str(f["adeudo"])) for f in nuevos), Decimal("0"))

        res = {
            "execute": execute,
            "candidatos": len(filas),
            "yaImputados": len(filas) - len(nuevos),
            "aImputar": len(nuevos),
            "importe": float(round(importe, 2)),
            "imputados": 0,
            "deudasLiquidadas": 0,
        }
        if not execute or not nuevos:
            return res

        # En BLOQUE, no fila a fila: con 7.138 pares, un `session.get(Deuda, …)` por
        # emparejamiento son ~7 s solo en lecturas (medido) y el endpoint superaba el
        # tiempo del cliente HTTP. Un INSERT masivo + un UPDATE por lista de ids hace lo
        # mismo en dos sentencias.
        self.session.bulk_insert_mappings(DeudaPago, [{
            "deuda_id": f["deuda_id"], "pago_id": f["pago_id"],
            "pagado": Decimal(str(f["adeudo"])), "fecha_pago": f["fecha"],
            "subtipo_pago": (f["forma_pago"] or None),
        } for f in nuevos])

        # El pago cubre la deuda entera (es la condición del emparejamiento), así que
        # queda saldada: pendiente 0 y liquidada. No se toca ninguna otra.
        ids = [f["deuda_id"] for f in nuevos]
        actualizadas = self.session.execute(
            update(Deuda).where(Deuda.id.in_(ids))
            .values(importe_pendiente=Decimal("0"), liquidada=True)
        ).rowcount

        self.session.commit()
        res["imputados"] = len(nuevos)
        res["deudasLiquidadas"] = int(actualizadas or 0)
        return res

    def pendientes_de_regla(self) -> dict:
        """Lo que NO se imputa y por qué: el resto necesita una regla contable del usuario.

        No propone ningún reparto: solo cuenta y separa los casos, para que la decisión se
        tome sobre cifras y no sobre una impresión.
        """
        total_deudas = self.session.exec(
            select(Deuda).where(Deuda.centro_id == self.centro_id, Deuda.adeudo > 0)).all()
        imputadas = {dp.deuda_id for dp in self.session.exec(select(DeudaPago)).all()}
        sin_imputar = [d for d in total_deudas if d.id not in imputadas]
        return {
            "deudasConAdeudo": len(total_deudas),
            "imputadas": len(total_deudas) - len(sin_imputar),
            "sinImputar": len(sin_imputar),
            "importeSinImputar": float(round(
                sum((d.adeudo or Decimal("0")) for d in sin_imputar), 2)),
            "motivo": ("Requieren una regla de imputación (FIFO, proporcional u otra): el "
                       "pago y la deuda no casan 1:1 por paciente+fecha+importe."),
        }
