"""Archivado de facturas en CLINICA/FACTURAS/<año> (oct-2026: las carpetas fijas estaban borradas)."""
from datetime import date

from application.services import factura_archivo as fa
from domain.models.gestoria import Gasto


def test_destino_es_la_carpeta_del_anio_de_la_factura(monkeypatch):
    llamadas = []
    monkeypatch.setattr(fa.drive_client, "buscar_o_crear_carpeta",
                        lambda cfg, nombre, parent: llamadas.append((nombre, parent)) or "id-2026")
    g = Gasto(centro_id=1, fecha=date(2026, 10, 1))
    assert fa._carpeta_destino({"carpeta_facturas_raiz": "RAIZ", "carpeta_facturas": "VIEJA"}, g) == "id-2026"
    assert llamadas == [("2026", "RAIZ")]


def test_si_no_se_puede_crear_el_anio_usa_la_raiz(monkeypatch):
    monkeypatch.setattr(fa.drive_client, "buscar_o_crear_carpeta", lambda cfg, nombre, parent: None)
    g = Gasto(centro_id=1, fecha=date(2026, 10, 1))
    assert fa._carpeta_destino({"carpeta_facturas_raiz": "RAIZ"}, g) == "RAIZ"


def test_sin_raiz_se_mantiene_la_carpeta_de_siempre():
    g = Gasto(centro_id=1, fecha=date(2026, 10, 1))
    assert fa._carpeta_destino({"carpeta_facturas": "VIEJA"}, g) == "VIEJA"


def test_fallo_de_drive_cae_a_local_y_queda_en_el_log(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(fa, "MEDIA", tmp_path)
    monkeypatch.setattr(fa, "_integ", lambda s, c, t: {"sa_b64": "x", "carpeta_facturas": "VIEJA"})
    monkeypatch.setattr(fa.drive_client, "configurado", lambda cfg: True)

    def _404(*a, **k):
        raise RuntimeError("File not found: VIEJA")
    monkeypatch.setattr(fa.drive_client, "subir", _404)

    class _S:
        def add(self, x):
            pass
    g = Gasto(id=7, centro_id=1, fecha=date(2026, 10, 1), proveedor_extraido="Acme", numero_factura="1")
    fuente = type("F", (), {"bytes": b"%PDF-1.4 x"})()
    url = fa.guardar_pdf(_S(), 1, g, {}, fuente)
    assert url.startswith("/media/facturas/")
    assert "Drive falló para el gasto 7" in caplog.text


def test_nombre_con_el_formato_de_la_carpeta_reorganizada():
    g = Gasto(centro_id=1, fecha=date(2026, 7, 21), proveedor_extraido="IMPLANT PROTESIS DENTAL 2004, S.L.",
              numero_factura="A-146574")
    assert fa._nombre(g) == "21-07-2026_IMPLANT-PROTESIS-DENTAL-2004-S-L_A-146574.pdf"
    g2 = Gasto(centro_id=1, fecha=date(2025, 5, 27), proveedor_extraido="Suministros Dentales Alcalá SL",
               numero_factura="1393/25")
    assert fa._nombre(g2) == "27-05-2025_SUMINISTROS-DENTALES-ALCALA-SL_1393-25.pdf"
