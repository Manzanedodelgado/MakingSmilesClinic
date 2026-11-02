"""Contrato de GESTORÍA: los invariantes que costaron horas de trabajo y no pueden
desaparecer en silencio.

Mismo espíritu que test_agentes_contrato.py: no comprueban "¿funciona la función?" sino
"¿sigue siendo verdad lo que decidimos?". Gestoría es donde más decisiones finas se han
tomado —el vínculo N:1 factura↔apunte, las formas de pago canónicas, la numeración por mes
producido, el concepto de banco inmutable—, así que es donde más caro sale perderlas por
un commit amplio que revierta un fichero.

Los que dependen del esquema de BD se comprueban contra el modelo SQLModel real, no contra
una base de test vacía: el riesgo es que alguien mueva una columna, y eso vive en el modelo.
"""
from decimal import Decimal

from domain.services.forma_pago import (
    CANONICAS, TRANSFERENCIA, DOMICILIACION, TARJETA, CHEQUE, METALICO, TARJETA_JAM,
    es_canonica, forma_pago_canonica,
)


# ─────────────── el vínculo factura ↔ apunte (N:1) ───────────────
def test_el_vinculo_vive_en_gasto_no_en_movimiento():
    """LA DECISIÓN RAÍZ. Una transferencia puede pagar VARIAS facturas (pago unificado),
    así que el vínculo cuelga del gasto (N facturas → 1 apunte). El viejo
    `movimientos_bancarios.gasto_id` (1:1, con índice único) hacía imposible el pago
    unificado y NO debe reaparecer."""
    from domain.models.gestoria import Gasto, MovimientoBancario
    assert "movimiento_id" in Gasto.model_fields, "gastos.movimiento_id es el vínculo"
    assert "gasto_id" not in MovimientoBancario.model_fields, \
        "movimientos_bancarios.gasto_id revive el modelo 1:1 que rompe el pago unificado"


def test_existe_el_helper_de_apuntes_sin_factura():
    """El motor de conciliación pregunta '¿este apunte no tiene NINGUNA factura?'. Al mover
    el vínculo, ese predicado dejó de ser `gasto_id IS NULL` y pasó a una función; si
    desaparece, la conciliación vuelve a colgar del modelo viejo."""
    from domain.models.gestoria import movimiento_sin_factura
    assert callable(movimiento_sin_factura)


# ─────────────── formas de pago canónicas ───────────────
def test_las_formas_canonicas_son_exactamente_seis():
    """El campo llegó a tener 119 valores distintos para 6 formas reales. La lista canónica
    es cerrada: seis. Añadir una forma es una decisión, no un descuido de OCR."""
    assert CANONICAS == {TRANSFERENCIA, DOMICILIACION, TARJETA, CHEQUE, METALICO, TARJETA_JAM}
    assert len(CANONICAS) == 6


def test_el_ruido_del_ocr_no_es_forma_de_pago():
    """Plazos, cuentas y coletillas NO son formas de pago. Si `es_canonica` empezara a
    aceptarlos, la columna volvería a llenarse de basura como 'A la vista' o un IBAN."""
    for ruido in ("A la vista", "Vencimiento 30 días", "Contado",
                  "ES80 0049 3157 8727 9410 8647", "PAGADO", "30 Dias Fecha Factura"):
        assert not es_canonica(ruido), f"«{ruido}» no es una forma de pago"
        assert forma_pago_canonica(ruido) is None, f"«{ruido}» no debe normalizarse a una forma"


def test_el_efectivo_se_unifica_bajo_un_solo_nombre():
    """EFECTIVO / METÁLICO / Efectivo / Metálico son el mismo dato escrito de cuatro
    maneras. Todos deben caer en 'Metálico'."""
    for variante in ("EFECTIVO", "METÁLICO", "Efectivo", "metalico", "en efectivo"):
        assert forma_pago_canonica(variante) == METALICO


def test_lo_canonico_se_reconoce_a_si_mismo():
    """Una forma ya canónica no se pierde al re-normalizar (idempotencia)."""
    for forma in CANONICAS:
        assert es_canonica(forma)


# ─────────────── concepto del banco inmutable ───────────────
def test_el_concepto_del_banco_no_se_sobrescribe():
    """El literal del extracto (`concepto_banco`) es la prueba documental Y parte de la
    identidad anti-duplicados al importar. Las correcciones van a `concepto_corregido`;
    si ese campo desaparece, corregir un rótulo obligaría a machacar el original y
    reimportar el mismo extracto lo duplicaría."""
    from domain.models.gestoria import MovimientoBancario
    assert "concepto_banco" in MovimientoBancario.model_fields
    assert "concepto_corregido" in MovimientoBancario.model_fields
    # `concepto_util` es lo que lee el resto del sistema: corregido si lo hay, si no el banco.
    assert hasattr(MovimientoBancario, "concepto_util")


# ─────────────── numeración de autofacturas por mes producido ───────────────
def test_el_motor_numera_por_mes_producido_no_por_fecha_de_pago():
    """La autofactura de un colaborador se numera por el mes que declara el concepto del
    banco ('Producción Noviembre' pagada el 22/12 es de noviembre), no por la fecha de la
    transferencia. Es lo que corrió toda la serie de Irene un mes. El método que lo decide
    debe seguir existiendo."""
    from application.services.conciliacion_service import ConciliacionService
    assert hasattr(ConciliacionService, "_periodo_producido")
