"""VERI*FACTU — la huella se comprueba contra los EJEMPLOS OFICIALES de la AEAT.

No son tests de "¿la función devuelve algo?": son los tres casos publicados por la AEAT en
«Detalle de las especificaciones técnicas para generación de la huella o hash de los
registros de facturación» v0.1.2 (§6.1, §6.2, §6.3), con su cadena de entrada y su hash
esperado. Si alguien cambia el orden de los campos, el separador, el formato de la fecha o
el de los importes, el hash deja de coincidir con el de Hacienda y esto se pone en rojo.
"""
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from domain.services import verifactu as vf

# ─────────── §6.1 · primer registro de alta del sistema (sin huella anterior) ───────────
ALTA_1 = dict(id_emisor="89890001K", num_serie="12345678/G33",
              fecha_expedicion=date(2024, 1, 1), tipo_factura="F1",
              cuota_total="12.35", importe_total="123.45", huella_anterior=None,
              fecha_hora_huso="2024-01-01T19:20:30+01:00")
CADENA_1 = ("IDEmisorFactura=89890001K&NumSerieFactura=12345678/G33&"
            "FechaExpedicionFactura=01-01-2024&TipoFactura=F1&CuotaTotal=12.35&"
            "ImporteTotal=123.45&Huella=&FechaHoraHusoGenRegistro=2024-01-01T19:20:30+01:00")
HUELLA_1 = "3C464DAF61ACB827C65FDA19F352A4E3BDC2C640E9E9FC4CC058073F38F12F60"

# ─────────── §6.2 · alta encadenada al registro anterior ───────────
ALTA_2 = dict(id_emisor="89890001K", num_serie="12345679/G34",
              fecha_expedicion=date(2024, 1, 1), tipo_factura="F1",
              cuota_total="12.35", importe_total="123.45", huella_anterior=HUELLA_1,
              fecha_hora_huso="2024-01-01T19:20:35+01:00")
HUELLA_2 = "F7B94CFD8924EDFF273501B01EE5153E4CE8F259766F88CF6ACB8935802A2B97"

# ─────────── §6.3 · anulación encadenada ───────────
ANUL_3 = dict(id_emisor="89890001K", num_serie="12345679/G34",
              fecha_expedicion=date(2024, 1, 1), huella_anterior=HUELLA_2,
              fecha_hora_huso="2024-01-01T19:20:40+01:00")
HUELLA_3 = "177547C0D57AC74748561D054A9CEC14B4C4EA23D1BEFD6F2E69E3A388F90C68"


def test_cadena_de_entrada_del_alta_es_la_de_la_aeat():
    """La cadena, carácter a carácter: es donde se cuelan los errores (orden, '&', fechas)."""
    assert vf.cadena_alta(**ALTA_1) == CADENA_1


def test_huella_primer_registro():
    assert vf.huella_alta(**ALTA_1) == HUELLA_1


def test_huella_registro_encadenado():
    assert vf.huella_alta(**ALTA_2) == HUELLA_2


def test_huella_anulacion():
    assert vf.huella_anulacion(**ANUL_3) == HUELLA_3


def test_sin_huella_anterior_el_campo_va_vacio_pero_presente():
    """El primer registro NO omite el campo: pone «Huella=» sin valor (espec. §3)."""
    assert "&Huella=&" in vf.cadena_alta(**ALTA_1)


def test_los_importes_admiten_decimal_float_o_texto():
    """La huella no puede depender de con qué tipo llegue el importe desde la app."""
    base = {**ALTA_1}
    con_decimal = vf.huella_alta(**{**base, "cuota_total": Decimal("12.35"),
                                    "importe_total": Decimal("123.45")})
    con_float = vf.huella_alta(**{**base, "cuota_total": 12.35, "importe_total": 123.45})
    assert con_decimal == con_float == HUELLA_1


def test_los_ceros_a_la_derecha_no_cambian_la_huella():
    """«123.1» y «123.10» son el mismo importe para la AEAT: deben dar el mismo hash."""
    a = vf.huella_alta(**{**ALTA_1, "importe_total": "123.4", "cuota_total": "12.3"})
    b = vf.huella_alta(**{**ALTA_1, "importe_total": "123.40", "cuota_total": "12.30"})
    assert a == b


def test_la_huella_es_hex_mayusculas_de_64():
    h = vf.huella_alta(**ALTA_1)
    assert len(h) == 64 and h == h.upper() and all(c in "0123456789ABCDEF" for c in h)


def test_la_cadena_de_anulacion_usa_los_nombres_anulada():
    """Los nombres de campo del registro de anulación NO son los del alta."""
    c = vf.cadena_anulacion(**ANUL_3)
    assert c.startswith("IDEmisorFacturaAnulada=") and "NumSerieFacturaAnulada=" in c
    assert "FechaExpedicionFacturaAnulada=01-01-2024" in c


# ─────────── QR de cotejo (arts. 20-21) ───────────
def test_url_qr_produccion_verificable():
    u = vf.url_qr(nif="89890001K", num_serie="12345678/G33",
                  fecha_expedicion=date(2024, 1, 1), importe_total="241.40")
    assert u.startswith("https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR?")
    assert "nif=89890001K" in u and "fecha=01-01-2024" in u and "importe=241.40" in u


def test_url_qr_codifica_los_caracteres_especiales_del_numero():
    """Un '&' en el nº de serie sin codificar parte la URL en dos parámetros (ejemplo de la AEAT)."""
    u = vf.url_qr(nif="89890001K", num_serie="12345678&G33",
                  fecha_expedicion=date(2024, 1, 1), importe_total="241.4", pruebas=True)
    assert "numserie=12345678%26G33" in u
    assert u.startswith("https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?")


def test_url_qr_no_verificable_usa_su_propio_servicio():
    u = vf.url_qr(nif="89890001K", num_serie="F1", fecha_expedicion=date(2024, 1, 1),
                  importe_total=10, verificable=False)
    assert "/ValidarQRNoVerifactu?" in u


def test_marca_temporal_lleva_huso_y_no_lleva_microsegundos():
    m = vf.marca_temporal(datetime(2024, 1, 1, 19, 20, 30, 123456,
                                   tzinfo=ZoneInfo("Europe/Madrid")))
    assert m == "2024-01-01T19:20:30+01:00"
