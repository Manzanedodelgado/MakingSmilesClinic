"""Export a Excel de gastos — vista de apoyo para la asesoría.

NO es fuente de verdad: lee `Gasto` tal cual está en BD y genera un `.xlsx` en memoria, con una
pestaña por `estado` (pendiente/revisar/pagada…), para que la asesoría pueda trabajar offline con
un fichero. La BD sigue siendo la fuente de verdad; esto es solo una copia de lectura.
"""
from __future__ import annotations

import io
from datetime import date
from typing import Optional

import openpyxl
from sqlmodel import Session, select

from domain.models.gestoria import Gasto

_CABECERA = [
    "fecha", "proveedor", "CIF", "numero_factura",
    "base_imponible", "iva_pct", "total", "categoria",
    "cuota_iva", "retencion", "suplido", "divisa", "concepto", "incidencia",
]

_HOJA_VACIA = "sin_datos"

# I6 (revisión final de rama): caracteres que Excel/openpyxl interpretan como inicio de
# fórmula si son el primer caracter de una celda de texto.
_CARACTERES_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _neutralizar_celda(valor):
    """Antepone un apóstrofe si `valor` (string) empezaría una fórmula en Excel.

    Los campos que vienen de correos/IA no confiables (proveedor, nº factura, categoría,
    CIF) se escriben tal cual en la celda; si alguno empieza por '=', '+', '-', '@', tab o
    retorno de carro, Excel/openpyxl lo interpreta como fórmula real (inyección de
    fórmulas). Antepone un apóstrofe, que Excel trata como "forzar texto plano" y que
    openpyxl escribe literalmente (no lo interpreta como fórmula propia)."""
    if isinstance(valor, str) and valor.startswith(_CARACTERES_FORMULA):
        return "'" + valor
    return valor


def _cuota_iva(g: Gasto) -> float:
    """Despejada de total = base + IVA − retención + suplido: cuadra la fila exacta
    aunque la factura mezcle tipos de IVA."""
    return round(float((g.total or 0) - (g.base_imponible or 0) + (g.retencion or 0) - (g.suplido or 0)), 2)


def generar_excel_gastos(session: Session, centro_id: int,
                         desde: Optional[date] = None, hasta: Optional[date] = None) -> bytes:
    """Genera el .xlsx de gastos del centro, con una pestaña por `estado`. Devuelve los bytes."""
    query = select(Gasto).where(Gasto.centro_id == centro_id)
    if desde is not None:
        query = query.where(Gasto.fecha >= desde)
    if hasta is not None:
        query = query.where(Gasto.fecha <= hasta)
    gastos = session.exec(query.order_by(Gasto.fecha)).all()

    por_estado: dict[str, list[Gasto]] = {}
    for g in gastos:
        por_estado.setdefault(g.estado, []).append(g)

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # la hoja por defecto no nos sirve: creamos una por estado

    if not por_estado:
        wb.create_sheet(_HOJA_VACIA).append(_CABECERA)
    else:
        for estado, lista in por_estado.items():
            hoja = wb.create_sheet(estado[:31])  # openpyxl limita el nombre de hoja a 31 chars
            hoja.append(_CABECERA)
            for g in lista:
                hoja.append([
                    g.fecha,
                    _neutralizar_celda(g.proveedor_extraido),
                    _neutralizar_celda(g.cif_emisor),
                    _neutralizar_celda(g.numero_factura),
                    float(g.base_imponible) if g.base_imponible is not None else None,
                    float(g.iva_pct) if g.iva_pct is not None else None,
                    float(g.total) if g.total is not None else None,
                    _neutralizar_celda(g.categoria),
                    _cuota_iva(g),
                    float(g.retencion or 0),
                    float(g.suplido or 0),
                    g.divisa,
                    _neutralizar_celda(g.concepto),
                    _neutralizar_celda(g.incidencia),
                ])

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
