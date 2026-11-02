"""Clasificación a nivel de correo (buckets B/C del backlog).

La lógica vive en `clasificador_factura.clasificar_email` (se EXTENDIÓ el clasificador existente
en vez de duplicarlo en un módulo nuevo — R2). Casos verificados sobre el backlog real del centro 1.
"""
from domain.services.clasificador_factura import clasificar_email


def test_correo_propio_clinica():
    out = clasificar_email({"from": "info@rubiogarciadental.com", "subject": "saludos",
                            "body": "", "attachments": []})
    assert out == ("NO_FACTURA", "correo_propio_clinica")


def test_correo_enviado_clinica_etiqueta_sent():
    out = clasificar_email({"from": "x@proveedor.com", "subject": "re: factura",
                            "labels": ["\\Sent"], "attachments": []})
    assert out == ("NO_FACTURA", "correo_enviado_clinica")


def test_asunto_nomina():
    out = clasificar_email({"from": "rrhh@tridental.com",
                            "subject": "NÓMINA RECTIFICADA SETIEMBRE 2024", "attachments": []})
    assert out == ("NO_FACTURA", "nomina")


def test_asunto_contrato_transmision():
    out = clasificar_email({"from": "x@formacd.com",
                            "subject": "CONTRATO DE TRANSMISIÓN DE UNIDAD DE NEGOCIO",
                            "attachments": []})
    assert out == ("NO_FACTURA", "contrato")


def test_cuerpo_asesoria_pide_facturas():
    out = clasificar_email({"from": "gestoria@turset.com", "subject": "documentación",
                            "body": "Les ruego nos remitan escaneadas las facturas del trimestre.",
                            "attachments": []})
    assert out == ("NO_FACTURA", "asesoria_pide_facturas")


def test_portal_fineasy_sin_adjunto():
    out = clasificar_email({"from": "no.reply_sp_leasingsolutions@fineasy.com",
                            "subject": "Nueva factura disponible", "attachments": []})
    assert out == ("PORTAL", "portal:fineasy")


def test_acudent_con_pdf_es_factura():
    clase, _motivo = clasificar_email({"from": "labo@acudent.com", "subject": "Su pedido",
                                       "attachments": [{"filename": "factura.pdf"}]})
    assert clase == "FACTURA"
