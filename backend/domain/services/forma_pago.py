"""Cómo se pagó una factura, deducido del apunte del banco.

`Gasto.forma_pago` se rellenaba SOLO con lo que el OCR leía del documento del proveedor,
que es lo que el proveedor *pide* ("Vencimiento 30 días", un IBAN, "RECIBO 15 DIAS F/F"…),
no lo que la clínica *hizo*. Consecuencia: las autofacturas que emitimos nosotros salían
siempre sin forma de pago, porque no hay documento ajeno del que copiarla.

Cuando la factura tiene apunte bancario el dato deja de ser una suposición: el extracto
dice literalmente si fue transferencia, recibo domiciliado o tarjeta. Esta función traduce
ese texto a las formas canónicas que usa la UI (FORMAS_PAGO_GASTO en FacturacionViews).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

# OJO, no confundir con `normalizar_forma_pago` de gestoria_service: aquélla es para PAGOS
# DE PACIENTES y tiene otro vocabulario (Efectivo, Mutua, Talón, Eurodent…). Ésta es para
# FACTURAS RECIBIDAS y usa el de la UI de gastos. Son dos listas distintas a propósito.
#
# Formas canónicas: deben coincidir EXACTAMENTE con FORMAS_PAGO_GASTO del frontend.
TRANSFERENCIA = "Transferencia"
DOMICILIACION = "Domiciliación / Recibo"
TARJETA = "Tarjeta"
CHEQUE = "Cheque / Pagaré"
METALICO = "Metálico"
TARJETA_JAM = "Tarjeta Deb. Juan A. Manzanedo"   # fuera de la cuenta de la clínica

# El orden importa: se aplica el primer patrón que casa. "Transferencia" va antes que
# "recibo" porque hay conceptos del tipo "Transferencia ... recibo nº X".
_PATRONES: list[tuple[str, str]] = [
    # Tarjeta personal de Juan A. Manzanedo: va antes que "tarjeta" a secas porque es un
    # caso propio (pago fuera de la cuenta de la clínica, se concilia como apunte externo).
    (r"manzanedo", TARJETA_JAM),
    # "TF Pago a STERICYCLE", "TF ES90208552…": abreviatura de transferencia usada en las facturas.
    (r"transferencia|transfer\b|transf\.|bizum|\btf\b", TRANSFERENCIA),
    # "domic" y no "domicili": las facturas abrevian ("DOMIC. BANCARIA"). SDD = SEPA Direct Debit.
    (r"recibo|adeudo|domic|sepa|\bsdd\b|giro\b|cargo en cuenta|liquidacion periodica|mandato", DOMICILIACION),
    (r"tarjeta|compra en|\bvisa\b|mastercard|\btpv\b|contactless", TARJETA),
    (r"cheque|pagare|talon", CHEQUE),
    (r"efectivo|metalico|cajero|reintegro|ventanilla|contra ?reembolso", METALICO),
]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


CANONICAS = {TRANSFERENCIA, DOMICILIACION, TARJETA, CHEQUE, METALICO, TARJETA_JAM}


def es_canonica(forma: Optional[str]) -> bool:
    """¿El valor guardado es de verdad una forma de pago?

    El campo se venía rellenando con lo que el OCR pillaba de la factura del proveedor, que
    casi nunca es la forma de pago: son PLAZOS ("Vencimiento 30 días", "A la vista",
    "Contado"), números de cuenta ("Transf. a c.c. no. ES88…") o coletillas. Eso no se puede
    tratar como dato del usuario que haya que preservar: es ruido con formato de dato."""
    return (forma or "").strip() in CANONICAS


def forma_pago_canonica(texto: Optional[str]) -> Optional[str]:
    """Forma de pago canónica leída de un texto libre, o None si no se reconoce.

    Sirve para los DOS orígenes con la misma regla, que es justo lo que evita que el campo
    acabe con 119 valores distintos para 6 formas reales:
      · el concepto del extracto bancario ("Transferencia Inmediata A Favor De…")
      · lo que el OCR sacó de la factura del proveedor ("EFECTIVO", "METÁLICO", "Efectivo"…)

    Devolver None es deliberado: los PLAZOS ("Vencimiento 30 días", "A la vista", "Contado")
    y los números de cuenta sueltos no dicen cómo se pagó. Antes que inventar un dato que la
    gestoría dará por bueno, el campo se queda vacío."""
    c = _norm(texto or "")
    if not c:
        return None
    for patron, forma in _PATRONES:
        if re.search(patron, c):
            return forma
    return None


# Nombre histórico del caso "leer el extracto". Misma regla, se conserva por legibilidad
# en el motor de conciliación, donde el origen SIEMPRE es el banco.
forma_pago_desde_apunte = forma_pago_canonica
