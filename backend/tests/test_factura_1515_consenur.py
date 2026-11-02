"""Regresión de la factura real más difícil del backlog: id=1515, SRCL Consenur, con SUPLIDO.

Ground truth del bake-off (8/8 campos correctos, incluido el CIF del emisor del pie B86208824).
NOTA: el validador real devuelve un DICT {coherente, iva_calculado, incidencias, suplido_sugerido}
(no una tupla). Estos tests usan la firma REAL del repo (adaptación acordada, no la del prompt).
"""
from domain.services.invoice_validator import validar_importes

FACTURA_1515_GT = {
    "proveedor": "SRCL Consenur S.L.U",
    "cif_emisor": "B86208824",
    "numero_factura": "LGFA2005203",
    "fecha": "2020-02-10",
    "base_imponible": 102.55,
    "iva_pct": 21.00,
    "suplido": 21.33,
    "total": 145.42,
}


def test_consenur_1515_ecuacion_suplido():
    """Con el suplido (21,33) registrado, la ecuación base+IVA−ret+suplido cuadra → coherente."""
    r = validar_importes(base=102.55, iva_pct=21, total=145.42, suplido=21.33, retencion=0)
    assert r["coherente"] is True
    assert r["iva_calculado"] == 21.0
    assert r["incidencias"] == []


def test_consenur_1515_sin_suplido_falla():
    """Sin el suplido, el residual (21,33) descuadra el IVA → incoherente + se sugiere el suplido."""
    r = validar_importes(base=102.55, iva_pct=21, total=145.42, suplido=0, retencion=0)
    assert r["coherente"] is False
    assert any("suplido" in i or "iva" in i.lower() for i in r["incidencias"])
    assert r["suplido_sugerido"] is not None
    assert abs(r["suplido_sugerido"] - FACTURA_1515_GT["suplido"]) < 0.01


def test_fila_1516_outlier_base_cero_no_inventa_suplido():
    """Guard: con base=0 el 'residual' no es un suplido (es la factura mal leída) → no se sugiere."""
    r = validar_importes(base=0, iva_pct=0, total=164.23, suplido=0)
    assert r["suplido_sugerido"] is None
