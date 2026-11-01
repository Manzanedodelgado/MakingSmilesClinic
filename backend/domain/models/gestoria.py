"""Gestoría / contabilidad — proveedores, gastos, comisiones, deuda. FK a nodos-dios.

    centro ──< proveedor ──< gasto
    centro ──< liquidacion >── colaborador   (la paga del doctor, por periodo)
    liquidacion ──< liquidacion_linea >── presupuesto_linea  (qué actos se le liquidan)
    paciente ──< deuda >── presupuesto       (lo que debe el paciente)
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlmodel import Field, Relationship

from domain.models._base import TimestampMixin


# ───────────────────────── PROVEEDORES / GASTOS ─────────────────────────
class Proveedor(TimestampMixin, table=True):
    __tablename__ = "proveedores"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    nombre: str = Field(max_length=200)
    cif: Optional[str] = Field(default=None, max_length=20)
    email_contacto: Optional[str] = Field(default=None, max_length=255)
    telefono: Optional[str] = Field(default=None, max_length=40)
    direccion: Optional[str] = Field(default=None, max_length=300)
    iban: Optional[str] = Field(default=None, max_length=34)
    categoria_defecto: Optional[str] = Field(default=None, max_length=80)
    forma_pago_defecto: Optional[str] = Field(default=None, max_length=40)
    es_laboratorio: bool = Field(default=False, index=True)
    gastos: list["Gasto"] = Relationship(back_populates="proveedor")


class Gasto(TimestampMixin, table=True):
    """Factura recibida / gasto."""
    __tablename__ = "gastos"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    proveedor_id: Optional[int] = Field(default=None, foreign_key="proveedores.id", index=True)
    fecha: date = Field(index=True)
    concepto: Optional[str] = Field(default=None, max_length=300)
    numero_factura: Optional[str] = Field(default=None, max_length=60)
    proveedor_extraido: Optional[str] = Field(default=None, max_length=200)  # nombre literal de la factura
    cif_emisor: Optional[str] = Field(default=None, max_length=20, index=True)  # identidad fiscal extraída
    emisor_datos: Optional[str] = Field(default=None)  # JSON snapshot del emisor {nombre,direccion,email,telefono,fuente}
    base_imponible: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)
    iva_pct: Decimal = Field(default=Decimal("0"), max_digits=5, decimal_places=2)
    retencion: Decimal = Field(default=Decimal("0"), max_digits=10, decimal_places=2)  # IRPF: total = base + IVA − retención
    suplido: Decimal = Field(default=Decimal("0"), max_digits=10, decimal_places=2)    # exento de IVA: total = base + IVA − retención + suplido
    total: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)
    divisa: Optional[str] = Field(default="EUR", max_length=3)             # EUR/USD… tal como aparece
    tipo_documento: Optional[str] = Field(default=None, max_length=20)     # factura|abono|rectificativa
    forma_pago: Optional[str] = Field(default=None, max_length=40)         # SOLO las 6 canónicas (ver domain/services/forma_pago.py)
    condiciones_pago: Optional[str] = Field(default=None, max_length=300)  # plazo/cuenta que traía la factura (migración 028)
    es_gasto_lab: bool = Field(default=False, index=True)
    estado: str = Field(default="pendiente", max_length=40, index=True)   # pendiente|revisar|pagada
    fiable: bool = Field(default=True, index=True)                        # False si la validación detectó algo dudoso
    categoria: Optional[str] = Field(default=None, max_length=40)
    incidencia: Optional[str] = Field(default=None, max_length=200)       # motivo legible si estado=revisar
    incidencias: Optional[str] = Field(default=None)                      # JSON lista de códigos de validación
    archivo_pdf_url: Optional[str] = Field(default=None, max_length=500)
    gmail_message_id: Optional[str] = Field(default=None, max_length=120, index=True)
    # Apunte bancario que pagó esta factura. VARIAS facturas pueden compartir apunte
    # (pago unificado: una transferencia que liquida varios meses de producción), por eso
    # el vínculo vive aquí y NO lleva único. Ver migración 025.
    movimiento_id: Optional[int] = Field(default=None, foreign_key="movimientos_bancarios.id", index=True)
    proveedor: Optional[Proveedor] = Relationship(back_populates="gastos")


class GastoIncidencia(TimestampMixin, table=True):
    """Correo del buzón que NO se convirtió en gasto (ruido, sin datos legibles…)."""
    __tablename__ = "gasto_incidencias"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    gmail_message_id: Optional[str] = Field(default=None, max_length=120, index=True)
    fecha: Optional[date] = Field(default=None)
    remitente: Optional[str] = Field(default=None, max_length=300)
    asunto: Optional[str] = Field(default=None, max_length=400)
    motivo: str = Field(max_length=200)


# ───────────────── COMISIONES / LIQUIDACIÓN DEL DOCTOR ─────────────────
class Liquidacion(TimestampMixin, table=True):
    """Paga de un colaborador en un periodo."""
    __tablename__ = "liquidaciones"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    colaborador_id: int = Field(foreign_key="colaboradores.id", nullable=False, index=True)
    periodo_desde: date = Field(index=True)
    periodo_hasta: date = Field(index=True)
    base: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)
    irpf_pct: Decimal = Field(default=Decimal("15"), max_digits=5, decimal_places=2)
    liquido: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)
    cerrada: bool = Field(default=False, index=True)
    lineas: list["LiquidacionLinea"] = Relationship(back_populates="liquidacion")


class LiquidacionLinea(TimestampMixin, table=True):
    """Acto facturado que se liquida al doctor (enlaza con la línea de presupuesto)."""
    __tablename__ = "liquidacion_lineas"
    id: Optional[int] = Field(default=None, primary_key=True)
    liquidacion_id: int = Field(foreign_key="liquidaciones.id", nullable=False, index=True)
    presupuesto_linea_id: Optional[int] = Field(
        default=None, foreign_key="presupuesto_lineas.id", index=True)
    importe: Decimal = Field(max_digits=10, decimal_places=2)
    porcentaje_colab: Decimal = Field(default=Decimal("0"), max_digits=5, decimal_places=2)
    liquidacion: Liquidacion = Relationship(back_populates="lineas")


# ───────────────────────── DEUDA DEL PACIENTE ───────────────────────── (DeudaCli)
class Deuda(TimestampMixin, table=True):
    __tablename__ = "deudas"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    cliente_id: Optional[int] = Field(default=None, foreign_key="clientes.id", index=True)   # IdCli
    presupuesto_id: Optional[int] = Field(default=None, foreign_key="presupuestos.id", index=True)
    tratamiento_realizado_id: Optional[int] = Field(default=None, foreign_key="tratamientos_realizados.id", index=True)
    num_fase: Optional[int] = Field(default=None)
    fecha_plazo: Optional[date] = Field(default=None, index=True)
    adeudo: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)
    importe_pendiente: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)
    num_factura: Optional[str] = Field(default=None, max_length=40)
    modalidad: Optional[str] = Field(default=None, max_length=40)
    incobrable: bool = Field(default=False, index=True)
    motivo_incobrable: Optional[str] = Field(default=None, max_length=300)
    liquidada: bool = Field(default=False, index=True)


class DeudaPago(TimestampMixin, table=True):
    """Aplicación de un pago a una deuda (N:M deuda↔pago). Origen: DeudaPago."""
    __tablename__ = "deuda_pago"
    id: Optional[int] = Field(default=None, primary_key=True)
    deuda_id: int = Field(foreign_key="deudas.id", nullable=False, index=True)
    pago_id: int = Field(foreign_key="pagos.id", nullable=False, index=True)
    pagado: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)
    fecha_pago: Optional[date] = Field(default=None, index=True)
    subtipo_pago: Optional[str] = Field(default=None, max_length=40)


class ExtractoSubido(TimestampMixin, table=True):
    """Fichero de extracto bancario TAL CUAL se subió (PDF/XLSX/CSV), archivado.

    La app extrae los apuntes y hasta ahora descartaba el fichero. Se guarda el original
    para que la asesoría pueda descargar exactamente lo que entregó el banco (soporte
    documental de los apuntes). El `hash_sha256` identifica el contenido: permite ver de
    un vistazo si dos subidas son el mismo fichero.
    """
    __tablename__ = "extractos_subidos"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    nombre_original: str = Field(max_length=255)
    archivo_url: str = Field(max_length=500)          # /media/extractos/<uuid>.<ext>
    mime: Optional[str] = Field(default=None, max_length=120)
    tamano_bytes: int = Field(default=0)
    hash_sha256: str = Field(index=True, max_length=64)
    subido_por: Optional[int] = Field(default=None, foreign_key="usuarios.id", index=True)
    # Resultado de la importación, para saber qué aportó cada fichero.
    apuntes_importados: int = Field(default=0)
    apuntes_omitidos: int = Field(default=0)


class MovimientoBancario(TimestampMixin, table=True):
    """Apunte del extracto bancario; se concilia con gasto o factura emitida."""
    __tablename__ = "movimientos_bancarios"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    iban_cuenta: str = Field(max_length=34)
    fecha_operacion: date = Field(index=True)
    concepto_banco: str = Field(max_length=300)   # texto LITERAL del extracto: nunca se altera
    # Lectura contable corregida cuando el rótulo del banco está mal (ver migración 027).
    # No sustituye al original: la identidad anti-duplicados sigue usando `concepto_banco`.
    concepto_corregido: Optional[str] = Field(default=None, max_length=300)

    @property
    def concepto_util(self) -> str:
        """El que vale para leer e interpretar el apunte: la corrección si la hay."""
        return self.concepto_corregido or self.concepto_banco
    importe: Decimal = Field(max_digits=12, decimal_places=2)
    saldo_posterior: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)
    categoria: Optional[str] = Field(default=None, max_length=40)
    estado_concil: str = Field(default="abierto", max_length=20, index=True)
    # El vínculo con la factura vive en Gasto.movimiento_id (N facturas → 1 apunte). Ver migración 025.
    documento_admin_id: Optional[int] = Field(default=None, foreign_key="documentos_admin.id", index=True)
    pago_id: Optional[int] = Field(default=None, foreign_key="pagos.id", index=True)


def movimiento_sin_factura():
    """Predicado SQL: el apunte no tiene NINGUNA factura asociada.

    Sustituye al viejo `MovimientoBancario.gasto_id IS NULL`, que desapareció al mover el
    vínculo a `Gasto.movimiento_id` (N facturas → 1 apunte). Ver migración 025."""
    from sqlalchemy import exists
    return ~exists().where(Gasto.movimiento_id == MovimientoBancario.id)


class ModeloFiscal(TimestampMixin, table=True):
    """Presentación de modelo fiscal (303/130/111/390…)."""
    __tablename__ = "modelos_fiscales"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    modelo: str = Field(max_length=10)
    ejercicio: int = Field(index=True)
    periodo: str = Field(max_length=4)
    estado: str = Field(default="borrador", max_length=20, index=True)
    fecha_limite: Optional[date] = Field(default=None)
    cuota_resultante: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)
    archivo_justif: Optional[str] = Field(default=None, max_length=500)
