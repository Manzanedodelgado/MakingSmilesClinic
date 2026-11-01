"""Stock / almacén — inventario de material por centro. FK a nodos-dios.

Material consumible por centro, con movimientos de entrada/salida. Una salida puede ligarse al acto clínico que
lo consumió (trazabilidad de implantes/material).

    centro ──< articulo ──< stock_movimiento >── proveedor / cita_tratamiento
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel

from domain.models._base import TimestampMixin


class Articulo(TimestampMixin, table=True):
    __tablename__ = "articulos"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    codigo: Optional[str] = Field(default=None, max_length=40, index=True)
    nombre: str = Field(max_length=200)
    stock_actual: int = Field(default=0)
    stock_minimo: int = Field(default=0)
    es_implante: bool = Field(default=False, index=True)
    activo: bool = Field(default=True, index=True)
    movimientos: list["StockMovimiento"] = Relationship(back_populates="articulo")


class StockMovimiento(TimestampMixin, table=True):
    """Entrada (compra) o salida (consumo) de un artículo."""
    __tablename__ = "stock_movimientos"
    id: Optional[int] = Field(default=None, primary_key=True)
    articulo_id: int = Field(foreign_key="articulos.id", nullable=False, index=True)
    tipo: str = Field(index=True)                  # entrada | salida
    cantidad: int = Field()
    fecha: date = Field(index=True)
    # entrada → de qué proveedor; salida → en qué acto clínico se consumió
    proveedor_id: Optional[int] = Field(default=None, foreign_key="proveedores.id", index=True)
    cita_tratamiento_id: Optional[int] = Field(
        default=None, foreign_key="cita_tratamiento.id", index=True)
    coste_unitario: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    articulo: Articulo = Relationship(back_populates="movimientos")
