"""Gestor IA — archivo de facturación construido desde el correo.

Tablas propias del motor. El archivo anterior (`gastos`, `proveedores`) no se lee, no se
completa y no se corrige: no existe para este motor.

    centro ──< factura_gestor >── proveedor_gestor
    centro ──< revision_gestor        (lo que el motor no pudo resolver)
    centro ──< descarte_gestor        (lo que el motor determinó que NO es facturable)
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import JSON, Column, Index, Text
from sqlmodel import Field

from domain.models._base import TimestampMixin


class FacturaGestor(TimestampMixin, table=True):
    """Factura válida leída de un correo (§1).

    `id_fiscal` es NOT NULL a propósito: sin identificación fiscal del emisor no hay
    factura, así que la regla queda garantizada por el esquema y no solo por el código.
    """
    __tablename__ = "facturas_gestor"
    __table_args__ = (
        # Control de duplicados triple exacto: FECHA + NÚMERO + TOTAL (§6).
        Index("ix_fgestor_triple", "fecha_emision", "numero_factura", "total"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)

    # ── Campos A–D (§4) ────────────────────────────────────────────────────
    numero_factura: str = Field(max_length=60)
    fecha_emision: date = Field(index=True)
    proveedor_nombre: str = Field(max_length=200)
    id_fiscal: str = Field(max_length=20, index=True)

    # ── Campo E: IRPF — porcentaje y cuota, explícitos aunque sean cero ────
    irpf_pct: Decimal = Field(default=Decimal("0"), max_digits=5, decimal_places=2)
    irpf_cuota: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)

    # ── Campo F: IVA — [{base, pct, cuota}, ...]; una factura puede llevar
    #    21% y 10% a la vez y una columna plana perdería el desglose.
    iva_desglose: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False, server_default="[]"))
    base_total: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)

    # ── Campo G ────────────────────────────────────────────────────────────
    total: Decimal = Field(max_digits=12, decimal_places=2)
    divisa: str = Field(default="EUR", max_length=3)

    # ── Campos H–I: en blanco si no constan en el documento ────────────────
    direccion: Optional[str] = Field(default=None, max_length=300)
    telefono: Optional[str] = Field(default=None, max_length=40)

    concepto: Optional[str] = Field(default=None, max_length=300)
    categoria: Optional[str] = Field(default=None, max_length=80)

    # ── Drive (§7) ─────────────────────────────────────────────────────────
    drive_url: Optional[str] = Field(default=None, max_length=500)
    drive_file_id: Optional[str] = Field(default=None, max_length=120)
    reconstruida: bool = Field(default=False)

    # ── Trazabilidad (§0): de dónde salió cada dato ────────────────────────
    origen_dato: str = Field(max_length=20)  # xml|adjunto|enlace|ocr|cuerpo
    gmail_message_id: str = Field(max_length=120, unique=True)  # idempotencia
    remitente: Optional[str] = Field(default=None, max_length=255)
    proveedor_id: Optional[int] = Field(default=None, foreign_key="proveedores_gestor.id",
                                        index=True)
    estado: str = Field(default="registrada", max_length=20)


class ProveedorGestor(TimestampMixin, table=True):
    """Directorio propio (§8). Identidad = ID fiscal; jamás se fusiona por nombre.
    Se construye solo con lo que el motor lee de los correos."""
    __tablename__ = "proveedores_gestor"

    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    id_fiscal: str = Field(max_length=20, unique=True)
    nombre: str = Field(max_length=200)
    direccion: Optional[str] = Field(default=None, max_length=300)
    telefono: Optional[str] = Field(default=None, max_length=40)
    # Remitentes detectados; se SUMAN, nunca se reemplazan.
    remitentes: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False, server_default="[]"))
    # En blanco si la categoría es ambigua → alimenta el badge (§8).
    categoria: Optional[str] = Field(default=None, max_length=80, index=True)
    num_facturas: int = Field(default=0)


class ExcepcionGestor(TimestampMixin, table=True):
    """Reglas manuales del usuario que corrigen al motor en casos concretos.

    El motor acierta en el caso general, pero siempre hay emisores que se resisten: un
    nombre que se normaliza mal, un remitente cuyo CIF nunca figura en el documento, un
    proveedor que hay que descartar siempre. En vez de tocar el código para cada uno,
    aquí se declaran como datos.

    `tipo` indica qué corrige y `patron` con qué casa (remitente, CIF o denominación):

        marca_proveedor  → fija el nombre corto que se usa en el fichero de Drive
        id_fiscal        → asigna el CIF del emisor cuando el documento no lo trae
        denominacion     → fija la razón social del emisor
        categoria        → fija la categoría contable
        siempre_descartar→ el motor nunca registra lo que case con este patrón
    """
    __tablename__ = "excepciones_gestor"

    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    tipo: str = Field(max_length=24, index=True)
    # Con qué se compara: dirección de correo, dominio, ID fiscal o denominación.
    campo: str = Field(default="id_fiscal", max_length=20)
    patron: str = Field(max_length=200, index=True)
    valor: Optional[str] = Field(default=None, max_length=200)
    nota: Optional[str] = Field(default=None, max_length=300)
    activa: bool = Field(default=True, index=True)
    veces_aplicada: int = Field(default=0)


class RevisionGestor(TimestampMixin, table=True):
    """Correo que SÍ parece facturable pero que el motor no pudo resolver (§9).

    Distinto de `DescarteGestor`: aquí hay trabajo pendiente. Guarda el texto que el motor
    llegó a leer para que la revisión se haga en bloque desde la web, sin reabrir el correo
    ni depender de que alguien inspeccione el PDF a mano.
    """
    __tablename__ = "revisiones_gestor"

    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    gmail_message_id: str = Field(max_length=120, unique=True)
    remitente: Optional[str] = Field(default=None, max_length=255)
    asunto: Optional[str] = Field(default=None, max_length=300)
    fecha_correo: Optional[date] = Field(default=None)

    motivo: str = Field(max_length=40, index=True)
    detalle: Optional[str] = Field(default=None, sa_column=Column(Text))
    origen_dato: Optional[str] = Field(default=None, max_length=20)
    # Lo que sí se pudo leer: permite juzgar sin volver al documento.
    campos: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False, server_default="{}"))
    texto_leido: Optional[str] = Field(default=None, sa_column=Column(Text))
    intentos: int = Field(default=1)
    resuelta: bool = Field(default=False, index=True)


class DescarteGestor(TimestampMixin, table=True):
    """Correo que el motor determinó que NO es un documento facturable (§2).

    Tiene tabla propia para que no ensucie la cola de revisión: mezclar 'no es factura'
    con 'es factura y no sé leerla' obliga a mirar uno a uno lo que no lo necesita.
    Se registra igualmente — un descarte silencioso es indistinguible de una pérdida.
    """
    __tablename__ = "descartes_gestor"

    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    gmail_message_id: str = Field(max_length=120, unique=True)
    remitente: Optional[str] = Field(default=None, max_length=255)
    asunto: Optional[str] = Field(default=None, max_length=300)
    fecha_correo: Optional[date] = Field(default=None)
    motivo: str = Field(max_length=40, index=True)
    # Señales objetivas halladas pese al descarte (adjunto, importe, CIF…): si aparecen,
    # el criterio de cribado está mal y hay que corregirlo.
    senales: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False, server_default="[]"))


class PasadaGestor(TimestampMixin, table=True):
    """Registro de cada barrido: qué se procesó, cuánto costó y en qué acabó.
    Sin esto, 'el motor va bien' es una opinión."""
    __tablename__ = "pasadas_gestor"

    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    carpeta: str = Field(max_length=80)
    inicio: datetime = Field()
    fin: Optional[datetime] = Field(default=None)
    recuento: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False, server_default="{}"))
    llamadas_ia: int = Field(default=0)
    cortada: bool = Field(default=False)
