"""Cobertura de gastos_export_service: export a Excel de gastos (vista de apoyo para la asesoría).

No es fuente de verdad: solo lee `Gasto` y produce un .xlsx en memoria, una pestaña por `estado`.
"""
import io
from datetime import date
from decimal import Decimal

import openpyxl

from application.services.gastos_export_service import generar_excel_gastos
from domain.models.gestoria import Gasto


def _gasto(session, **kw) -> Gasto:
    datos = {"centro_id": 1, "fecha": date(2020, 2, 10), "estado": "revisar", **kw}
    g = Gasto(**datos)
    session.add(g)
    session.commit()
    session.refresh(g)
    return g


def test_generar_excel_separa_por_estado(session):
    _gasto(session, estado="ok", cif_emisor="B86208824", numero_factura="F1", total=Decimal("100"))
    _gasto(session, estado="revisar", cif_emisor="B86208824", numero_factura="F2", total=Decimal("200"))
    contenido = generar_excel_gastos(session, centro_id=1)
    wb = openpyxl.load_workbook(io.BytesIO(contenido))
    assert set(wb.sheetnames) >= {"ok", "revisar"}
    hoja_ok = wb["ok"]
    assert hoja_ok.cell(row=2, column=1).value is not None   # hay cabecera + al menos 1 fila


def test_generar_excel_filtra_por_centro_y_fechas(session):
    _gasto(session, centro_id=1, estado="ok", fecha=date(2021, 1, 15), total=Decimal("10"))
    _gasto(session, centro_id=2, estado="ok", fecha=date(2021, 1, 15), total=Decimal("20"))
    _gasto(session, centro_id=1, estado="ok", fecha=date(2022, 6, 1), total=Decimal("30"))

    contenido = generar_excel_gastos(session, centro_id=1, desde=date(2021, 1, 1), hasta=date(2021, 12, 31))
    wb = openpyxl.load_workbook(io.BytesIO(contenido))
    hoja = wb["ok"]
    # cabecera en fila 1 + exactamente 1 fila de datos (el otro centro y la otra fecha quedan fuera)
    assert hoja.cell(row=2, column=1).value is not None
    assert hoja.cell(row=3, column=1).value is None


def test_generar_excel_sin_gastos_no_rompe(session):
    contenido = generar_excel_gastos(session, centro_id=999)
    wb = openpyxl.load_workbook(io.BytesIO(contenido))
    assert isinstance(contenido, bytes)
    assert len(wb.sheetnames) >= 1


def test_generar_excel_neutraliza_inyeccion_de_formulas(session):
    """I6 (revisión final de rama): campos que vienen de correos/IA no confiables
    (proveedor, nº factura, categoría, CIF) se escriben tal cual; si alguno empieza por
    '=', '+', '-', '@', tab o retorno de carro, Excel/openpyxl lo interpretaría como una
    fórmula real. Deben quedar neutralizados con un apóstrofe delante."""
    _gasto(session, estado="ok", proveedor_extraido='=cmd|"/c calc"!A1',
          cif_emisor="+SUM(A1:A9)", numero_factura="-1+1", categoria="@HYPERLINK(\"x\")",
          total=Decimal("10"))
    contenido = generar_excel_gastos(session, centro_id=1)
    wb = openpyxl.load_workbook(io.BytesIO(contenido))
    hoja = wb["ok"]
    fila = [hoja.cell(row=2, column=c).value for c in range(1, 9)]
    proveedor, cif, numero_factura, categoria = fila[1], fila[2], fila[3], fila[7]
    for valor in (proveedor, cif, numero_factura, categoria):
        assert isinstance(valor, str) and valor.startswith("'"), valor


def test_generar_excel_no_toca_valores_normales(session):
    """El fix de I6 no debe alterar valores que NO empiezan por un caracter de fórmula."""
    _gasto(session, estado="ok", proveedor_extraido="Proveedor Normal S.L.",
          cif_emisor="B86208824", numero_factura="F-2024-001", categoria="suministros",
          total=Decimal("50"))
    contenido = generar_excel_gastos(session, centro_id=1)
    wb = openpyxl.load_workbook(io.BytesIO(contenido))
    hoja = wb["ok"]
    assert hoja.cell(row=2, column=2).value == "Proveedor Normal S.L."
    assert hoja.cell(row=2, column=3).value == "B86208824"
    assert hoja.cell(row=2, column=4).value == "F-2024-001"


def test_generar_excel_incluye_columnas_para_cuadrar_totales(session):
    """La asesoría debe poder cuadrar total = base + IVA − retención + suplido."""
    _gasto(session, numero_factura="R1", base_imponible=Decimal("100"), iva_pct=Decimal("21"),
           retencion=Decimal("15"), suplido=Decimal("6"), total=Decimal("112"))
    wb = openpyxl.load_workbook(io.BytesIO(generar_excel_gastos(session, centro_id=1)))
    hoja = wb["revisar"]
    cab = [c.value for c in hoja[1]]
    fila = dict(zip(cab, [c.value for c in hoja[2]]))
    assert fila["cuota_iva"] == 21.0
    assert fila["retencion"] == 15.0 and fila["suplido"] == 6.0
    assert fila["base_imponible"] + fila["cuota_iva"] - fila["retencion"] + fila["suplido"] == fila["total"]
