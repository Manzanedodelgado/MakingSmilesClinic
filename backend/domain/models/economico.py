"""Dominio económico — tarifas, presupuestos, pagos. FK a nodos-dios.

El precio vive en la tarifa, no en el tratamiento. El tratamiento es el catálogo;
la tarifa pone el precio; el presupuesto aplica tarifa a un paciente; el pago
salda el presupuesto.

    centro ──< tarifa ──< tarifa_precio >── tratamiento
    paciente ──< presupuesto ──< presupuesto_linea >── tratamiento (+ tarifa_precio)
    presupuesto ──< pago
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from domain.models._base import TimestampMixin


# ───────────────────────── CLIENTE (identidad económica) ─────────────────────────
class Cliente(TimestampMixin, table=True):
    """Identidad económica / titular de facturación (IdCli).

    Se crea de forma diferida con el primer movimiento económico. Es superconjunto
    del paciente: puede existir sin paciente (lead/titular externo). Un paciente
    apunta a su Cliente vía pacientes.cliente_id; otro cliente puede ser titular
    de la facturación de varios pacientes.
    """
    __tablename__ = "clientes"
    id: Optional[int] = Field(default=None, primary_key=True)   # IdCli
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    nombre: Optional[str] = Field(default=None, max_length=120, index=True)
    apellidos: Optional[str] = Field(default=None, max_length=200, index=True)
    razon_social: Optional[str] = Field(default=None, max_length=200)   # si es empresa
    es_empresa: bool = Field(default=False)
    nif: Optional[str] = Field(default=None, index=True, max_length=20)
    direccion: Optional[str] = Field(default=None, max_length=300)
    cp: Optional[str] = Field(default=None, max_length=10)
    poblacion_id: Optional[int] = Field(default=None, index=True)
    telefono: Optional[str] = Field(default=None, max_length=50)
    email: Optional[str] = Field(default=None, max_length=255)
    iban: Optional[str] = Field(default=None, max_length=34)
    titular_cuenta: Optional[str] = Field(default=None, max_length=200)
    forma_pago: Optional[str] = Field(default=None, max_length=60)
    fecha_alta: Optional[date] = Field(default=None)
    activo: bool = Field(default=True, index=True)


class PacienteTarifa(TimestampMixin, table=True):
    """Tarifa/póliza asignada a un paciente (puede tener varias). Origen: Pacientes_Tarifas."""
    __tablename__ = "paciente_tarifas"
    id: Optional[int] = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    tarifa_id: int = Field(foreign_key="tarifas.id", nullable=False, index=True)
    poliza: Optional[str] = Field(default=None, max_length=60)
    tarjeta: Optional[str] = Field(default=None, max_length=60)
    certificado: Optional[str] = Field(default=None, max_length=60)
    cobertura: Optional[str] = Field(default=None, max_length=120)
    fecha_alta: Optional[date] = Field(default=None)
    activo: bool = Field(default=True, index=True)


# ───────────────────────── TARIFA (el precio vive aquí) ─────────────────────────
class Tarifa(TimestampMixin, table=True):
    __tablename__ = "tarifas"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    nombre: str = Field(max_length=200)
    vigente_desde: Optional[date] = Field(default=None)
    vigente_hasta: Optional[date] = Field(default=None)
    activo: bool = Field(default=True, index=True)
    precios: list["TarifaPrecio"] = Relationship(back_populates="tarifa")


class TarifaPrecio(TimestampMixin, table=True):
    """Precio de un tratamiento dentro de una tarifa (tarifa × tratamiento)."""
    __tablename__ = "tarifa_precios"
    id: Optional[int] = Field(default=None, primary_key=True)
    tarifa_id: int = Field(foreign_key="tarifas.id", nullable=False, index=True)
    tratamiento_id: int = Field(foreign_key="tratamientos.id", nullable=False, index=True)
    precio: Decimal = Field(max_digits=10, decimal_places=2)
    # Coste de laboratorio = Σ cantidad × coste de sus trabajos (tarifa_precio_trabajos, migración 076).
    tarifa: Tarifa = Relationship(back_populates="precios")


class LaboratorioTrabajo(TimestampMixin, table=True):
    """Lista de precios de un laboratorio (proveedores.es_laboratorio): un trabajo y su coste."""
    __tablename__ = "laboratorio_trabajos"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    proveedor_id: int = Field(foreign_key="proveedores.id", nullable=False, index=True)
    codigo: Optional[str] = Field(default=None, max_length=40)
    nombre: str = Field(max_length=200)
    coste: Decimal = Field(max_digits=10, decimal_places=2)
    activo: bool = Field(default=True)


class TarifaPrecioTrabajo(TimestampMixin, table=True):
    """Trabajo de laboratorio de un precio de tarifa (p. ej. corona + interfase + tornillo)."""
    __tablename__ = "tarifa_precio_trabajos"
    __table_args__ = (UniqueConstraint("tarifa_precio_id", "laboratorio_trabajo_id"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    tarifa_precio_id: int = Field(foreign_key="tarifa_precios.id", nullable=False)
    laboratorio_trabajo_id: int = Field(foreign_key="laboratorio_trabajos.id", nullable=False, index=True)
    cantidad: Decimal = Field(default=Decimal("1"), max_digits=6, decimal_places=2)


# presupuesto_lineas.estado = id de estados_tratamiento (migración 082).
LINEA_PENDIENTE = 1        # Presupuestado
LINEA_ACEPTADA = 3         # Previsto
LINEA_REALIZADA = 5        # Realizado (todas sus fases hechas)
LINEA_CADUCADA, LINEA_CANCELADA, LINEA_ANULADA = 6, 7, 8
LINEA_ACEPTADAS = (LINEA_ACEPTADA, LINEA_REALIZADA)
LINEA_MUERTAS = (LINEA_CADUCADA, LINEA_CANCELADA, LINEA_ANULADA)
# Texto que sigue devolviendo la API a la pantalla de presupuestos.
LINEA_CODIGO = {LINEA_PENDIENTE: "PENDIENTE", LINEA_ACEPTADA: "ACEPTADA", LINEA_REALIZADA: "ACEPTADA",
                LINEA_CADUCADA: "ANULADA", LINEA_CANCELADA: "ANULADA", LINEA_ANULADA: "ANULADA"}


class EstadoPresupuesto(TimestampMixin, table=True):
    """Catálogo de estados de presupuesto (Nuevo, Entregado, Aceptado, En curso, Finalizado)."""
    __tablename__ = "estados_presupuesto"
    id: Optional[int] = Field(default=None, primary_key=True)
    codigo: str = Field(max_length=40, index=True)
    nombre: str = Field(max_length=80)
    orden: Optional[int] = Field(default=None)
    activo: bool = Field(default=True, index=True)


# ───────────────────────── PRESUPUESTO ───────────────────────── (Presu)
class Presupuesto(TimestampMixin, table=True):
    __tablename__ = "presupuestos"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    razon_social_id: Optional[int] = Field(default=None, foreign_key="razones_sociales.id", index=True)
    colaborador_id: Optional[int] = Field(default=None, foreign_key="colaboradores.id", index=True)
    num_serie: Optional[str] = Field(default=None, max_length=20, index=True)
    num_pre: Optional[int] = Field(default=None, index=True)
    titulo: Optional[str] = Field(default=None, max_length=200)
    notas: Optional[str] = Field(default=None, max_length=2000)
    fecha: date = Field(index=True)
    fecha_aceptacion: Optional[date] = Field(default=None)
    estado_id: Optional[int] = Field(default=None, foreign_key="estados_presupuesto.id", index=True)
    tipo_presupuesto: Optional[str] = Field(default=None, max_length=40)
    financiacion: bool = Field(default=False)
    es_alternativa: bool = Field(default=False)
    alternativa_de_id: Optional[int] = Field(default=None, foreign_key="presupuestos.id", index=True)
    total: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)
    aprobado: bool = Field(default=False, index=True)
    # fiscal / factura electrónica
    serie: Optional[str] = Field(default=None, max_length=20)
    num_serie_presu: Optional[int] = Field(default=None)
    hash_factura: Optional[str] = Field(default=None, max_length=120)
    codigo_atcud: Optional[str] = Field(default=None, max_length=40)
    codigo_qr: Optional[str] = Field(default=None, max_length=500)
    # firma digital
    fecha_aceptado_digital: Optional[datetime] = Field(default=None)
    fecha_entrega_digital: Optional[datetime] = Field(default=None)
    fecha_recibido_cliente: Optional[datetime] = Field(default=None)
    lineas: list["PresupuestoLinea"] = Relationship(back_populates="presupuesto")
    pagos: list["Pago"] = Relationship(back_populates="presupuesto")


class PresupuestoLinea(TimestampMixin, table=True):  # PresuTto
    __tablename__ = "presupuesto_lineas"
    id: Optional[int] = Field(default=None, primary_key=True)
    presupuesto_id: int = Field(foreign_key="presupuestos.id", nullable=False, index=True)
    num_linea: Optional[int] = Field(default=None)
    tratamiento_id: int = Field(foreign_key="tratamientos.id", nullable=False, index=True)
    tarifa_precio_id: Optional[int] = Field(default=None, foreign_key="tarifa_precios.id", index=True)
    colaborador_id: Optional[int] = Field(default=None, foreign_key="colaboradores.id", index=True)
    pieza: Optional[str] = Field(default=None, max_length=100)   # FDI; varias separadas por '.' (14.15.16)
    zona_boca: Optional[str] = Field(default=None, max_length=120)  # admite varias zonas separadas por coma
    # id de estados_tratamiento (el nombre de la columna es histórico; migración 082).
    estado: int = Field(default=1, foreign_key="estados_tratamiento.id", nullable=False)
    cantidad: int = Field(default=1)
    unidades: Optional[int] = Field(default=None)
    precio_unitario: Decimal = Field(max_digits=10, decimal_places=2)
    descuento: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    descuento_pct: bool = Field(default=False)   # True → `descuento` es % sobre el bruto; False → importe en €
    base_imponible: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    tipo_iva: Optional[float] = Field(default=None)
    importe_iva: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    presupuesto: Presupuesto = Relationship(back_populates="lineas")


# ───────── PRESUPUESTOS PREDISEÑADOS (plantillas) ───────── (GELITE: PresuTipo / PresuTipoTto)
class PresupuestoPredisenado(TimestampMixin, table=True):  # PresuTipo
    """Plantilla de presupuesto: un título + un conjunto de tratamientos (líneas).
    Se 'carga' en un presupuesto nuevo para volcar sus líneas. Origen: GELITE PresuTipo."""
    __tablename__ = "presupuestos_predisenados"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    titulo: str = Field(max_length=200, index=True)
    notas: Optional[str] = Field(default=None, max_length=2000)
    categoria_id: Optional[int] = Field(default=None, index=True)   # GELITE IdTipoPresupuesto (2-6)
    categoria: Optional[str] = Field(default=None, max_length=60)   # etiqueta legible de la categoría
    colaborador_id: Optional[int] = Field(default=None, foreign_key="colaboradores.id", index=True)
    orden: int = Field(default=0, index=True)
    activo: bool = Field(default=True, index=True)
    gelite_id: Optional[int] = Field(default=None, index=True)      # IdPresuTipo de origen (trazabilidad)
    lineas: list["PresupuestoPredisenadoLinea"] = Relationship(back_populates="predisenado")


class PresupuestoPredisenadoLinea(TimestampMixin, table=True):  # PresuTipoTto
    __tablename__ = "presupuestos_predisenados_lineas"
    id: Optional[int] = Field(default=None, primary_key=True)
    predisenado_id: int = Field(foreign_key="presupuestos_predisenados.id", nullable=False, index=True)
    tratamiento_id: int = Field(foreign_key="tratamientos.id", nullable=False, index=True)
    nombre: Optional[str] = Field(default=None, max_length=200)     # nombre tal cual en GELITE (referencia)
    # Ámbito por defecto de la línea (como en el presupuesto): se vuelca al cargar la plantilla.
    pieza: Optional[str] = Field(default=None, max_length=100)      # FDI; varias separadas por '.'
    zona_boca: Optional[str] = Field(default=None, max_length=120)  # arcada/cuadrante/sextante… (varias por coma)
    # Económico por defecto (se vuelca al cargar la plantilla). precio=None → usar tarifa del paciente.
    # cantidad: en tratamientos de mensualidad = nº de mensualidades/fases (p.ej. 18).
    precio: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    cantidad: int = Field(default=1)
    descuento: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    descuento_pct: bool = Field(default=False)   # True → `descuento` es % sobre el bruto
    orden: int = Field(default=0)
    predisenado: PresupuestoPredisenado = Relationship(back_populates="lineas")


# ───────────────────────── FORMA DE PAGO ───────────────────────── (TForPago)
class FormaPago(TimestampMixin, table=True):
    """Catálogo ÚNICO de formas de pago de pacientes (migración 040). ids 1-15 = TForPago de Gesden."""
    __tablename__ = "formas_pago"
    id: Optional[int] = Field(default=None, primary_key=True)
    codigo: Optional[str] = Field(default=None, max_length=2)
    nombre: str = Field(max_length=60)
    grupo: str = Field(max_length=30)          # agrupa variantes (p.ej. "Tarjeta pronto pago" → Tarjeta)
    en_caja: bool = Field(default=False)       # se ofrece al cobrar desde la app
    activo: bool = Field(default=True)
    orden: int = Field(default=100)


# ───────────────────────── FINANCIERAS ─────────────────────────
class Financiera(TimestampMixin, table=True):
    """Entidad financiera (Cetelem, Pepper, Sabadell Consumer…)."""
    __tablename__ = "financieras"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    nombre: str = Field(max_length=120)
    comision_pct: Decimal = Field(default=Decimal(0), max_digits=5, decimal_places=2)
    activo: bool = Field(default=True, index=True)


# ───────────────────────── PAGO ───────────────────────── (PagoCli)
class Pago(TimestampMixin, table=True):
    __tablename__ = "pagos"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    cliente_id: Optional[int] = Field(default=None, foreign_key="clientes.id", index=True)   # IdCli
    paciente_id: Optional[int] = Field(default=None, foreign_key="pacientes.id", index=True)
    presupuesto_id: Optional[int] = Field(default=None, foreign_key="presupuestos.id", index=True)
    fecha: date = Field(index=True)
    importe: Decimal = Field(max_digits=12, decimal_places=2)   # BRUTO (100% que paga/factura el paciente)
    neto: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)  # lo que recibe la clínica (financiación); coste = importe - neto
    # Campos de financiación
    financiera_id: Optional[int] = Field(default=None, foreign_key="financieras.id", index=True)
    entrada: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)
    num_cuotas: Optional[int] = Field(default=None)
    interes_pct: Optional[Decimal] = Field(default=None, max_digits=5, decimal_places=2)
    cuota_mensual: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)
    forma_pago_id: Optional[int] = Field(default=None, foreign_key="formas_pago.id", index=True)
    banco_id: Optional[int] = Field(default=None)
    iban: Optional[str] = Field(default=None, max_length=34)
    num_recibo: Optional[str] = Field(default=None, max_length=40)
    motivo: Optional[str] = Field(default=None, max_length=250)  # Motivo de devolución de saldo
    num_factura: Optional[str] = Field(default=None, max_length=40)
    num_transaccion: Optional[str] = Field(default=None, max_length=80)
    automatico: bool = Field(default=False)
    anulado: bool = Field(default=False, index=True)
    liquidado: bool = Field(default=False, index=True)
    # Liquidación de TPV (apunte "Liquidación efectuada el…") que abonó este cobro con tarjeta.
    liquidacion_mov_id: Optional[int] = Field(default=None, foreign_key="movimientos_bancarios.id", index=True)
    # Procedencia (migraciones 058/063). NULL = cobrado en la app. 'GELITE:…' = migrado.
    origen: Optional[str] = Field(default=None)
    origen_id_gelite: Optional[str] = Field(default=None)
    origen_fecha: Optional[date] = Field(default=None)
    presupuesto: Optional[Presupuesto] = Relationship(back_populates="pagos")


class EstadoTratamiento(TimestampMixin, table=True):
    """Catálogo de estados de tratamiento realizado (Planificado, En curso, Finalizado)."""
    __tablename__ = "estados_tratamiento"
    id: Optional[int] = Field(default=None, primary_key=True)
    codigo: str = Field(max_length=40, index=True)
    nombre: str = Field(max_length=80)
    orden: Optional[int] = Field(default=None)
    activo: bool = Field(default=True, index=True)


# ───────────────────────── TRATAMIENTO REALIZADO ───────────────────────── (TtosMed)
class TratamientoRealizado(TimestampMixin, table=True):
    """Acto clínico realizado (producción). Origen GELITE: TtosMed."""
    __tablename__ = "tratamientos_realizados"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    cliente_id: Optional[int] = Field(default=None, foreign_key="clientes.id", index=True)
    num_tto: Optional[int] = Field(default=None, index=True)
    # Procedencia (migración 052): NULL = creado en la app; GELITE:* = histórico importado.
    origen: Optional[str] = Field(default=None)
    origen_id_gelite: Optional[str] = Field(default=None)
    origen_fecha: Optional[date] = Field(default=None)
    # IdTto en GELITE = línea Tratamientos_Tarifas → da catálogo (tratamiento_id) Y precio (tarifa_precio_id)
    tratamiento_id: Optional[int] = Field(default=None, foreign_key="tratamientos.id", index=True)  # catálogo (fases/info)
    tarifa_precio_id: Optional[int] = Field(default=None, foreign_key="tarifa_precios.id", index=True)  # tarifa/precio
    presupuesto_linea_id: Optional[int] = Field(default=None, foreign_key="presupuesto_lineas.id", index=True)
    colaborador_id: Optional[int] = Field(default=None, foreign_key="colaboradores.id", index=True)
    colaborador_aux_id: Optional[int] = Field(default=None, foreign_key="colaboradores.id", index=True)
    piezas: Optional[str] = Field(default=None, max_length=60)     # FDI
    zona_boca: Optional[str] = Field(default=None, max_length=120)  # admite varias zonas separadas por coma
    estado_id: Optional[int] = Field(default=None, foreign_key="estados_tratamiento.id", index=True)  # StaTto
    fecha_inicio: Optional[date] = Field(default=None, index=True)
    fecha_fin: Optional[date] = Field(default=None)
    actos: Optional[int] = Field(default=None)
    tiempo_min: Optional[int] = Field(default=None)
    importe: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    descuento: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    # Dto. realizado que aplica (resta) en la liquidación del doctor. False → lo absorbe la clínica.
    descuento_aplica_doctor: bool = Field(default=False, nullable=False)
    # Coste de laboratorio de ESTE acto (migración 030). NULL = sin informar, ≠ 0 € informado.
    coste_laboratorio: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    importe_descuento: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    importe_privado: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    importe_mutua: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    pendiente: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    num_factura_e: Optional[str] = Field(default=None, max_length=40)
    factura_documento_id: Optional[int] = Field(default=None, foreign_key="documentos_admin.id", index=True)
    num_transaccion: Optional[str] = Field(default=None, max_length=80)
    notas: Optional[str] = Field(default=None, max_length=2000)
    campo_libre_1: Optional[str] = Field(default=None, max_length=200)
    fases: list["TratamientoRealizadoFase"] = Relationship(back_populates="tratamiento_realizado")


class TratamientoRealizadoFase(TimestampMixin, table=True):  # TtosMedFases
    __tablename__ = "tratamientos_realizados_fases"
    id: Optional[int] = Field(default=None, primary_key=True)
    tratamiento_realizado_id: int = Field(foreign_key="tratamientos_realizados.id", nullable=False, index=True)
    num_fase: Optional[int] = Field(default=None)
    estado: Optional[str] = Field(default=None, max_length=20)
    fecha: Optional[date] = Field(default=None)
    pct_facturar: Optional[float] = Field(default=None)
    colaborador_id: Optional[int] = Field(default=None, foreign_key="colaboradores.id", index=True)
    notas: Optional[str] = Field(default=None, max_length=1000)
    tratamiento_realizado: TratamientoRealizado = Relationship(back_populates="fases")


class TratamientoPrevisto(TimestampMixin, table=True):
    """Tratamiento pendiente de realizar (plan tras aceptar presupuesto)."""
    __tablename__ = "tratamientos_previstos"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    cliente_id: Optional[int] = Field(default=None, foreign_key="clientes.id", index=True)
    num_tto: Optional[int] = Field(default=None, index=True)
    tratamiento_id: Optional[int] = Field(default=None, foreign_key="tratamientos.id", index=True)
    presupuesto_linea_id: Optional[int] = Field(default=None, foreign_key="presupuesto_lineas.id", index=True)
    tarifa_precio_id: Optional[int] = Field(default=None, foreign_key="tarifa_precios.id", index=True)
    colaborador_id: Optional[int] = Field(default=None, foreign_key="colaboradores.id", index=True)
    colaborador_aux_id: Optional[int] = Field(default=None, foreign_key="colaboradores.id", index=True)
    piezas: Optional[str] = Field(default=None, max_length=60)
    zona_boca: Optional[str] = Field(default=None, max_length=120)
    fecha_inicio: Optional[date] = Field(default=None, index=True)
    fecha_fin: Optional[date] = Field(default=None)
    actos: Optional[int] = Field(default=None)
    tiempo_min: Optional[int] = Field(default=None)
    importe: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    descuento: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    importe_descuento: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    importe_privado: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    importe_mutua: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    pendiente: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    num_factura_e: Optional[str] = Field(default=None, max_length=40)
    num_transaccion: Optional[str] = Field(default=None, max_length=80)
    notas: Optional[str] = Field(default=None, max_length=2000)
    campo_libre_1: Optional[str] = Field(default=None, max_length=200)
    estado_id: Optional[int] = Field(default=None, foreign_key="estados_tratamiento.id", index=True)


# ───────── ARCHIVO HISTÓRICO DE FACTURAS RECIBIDAS (libros 2019-2024) ─────────
class FacturaHistorico(TimestampMixin, table=True):
    """Archivo DOCUMENTAL de consulta: filas de los LIBROFACTURAS.xls históricos + sus PDFs.

    AISLADO A PROPÓSITO: ni FK ni join con `gastos`/`proveedores`, y NINGÚN informe ni total
    de Gestoría lo lee — los números contables de años cerrados no cambian. Solo sirve para
    ENCONTRAR una factura vieja (buscador Gestoría › Facturación › Histórico)."""
    __tablename__ = "facturas_historico"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    anio: int = Field(index=True)
    mes: Optional[int] = Field(default=None, index=True)
    num_factura: Optional[str] = Field(default=None, max_length=80, index=True)
    fecha: Optional[date] = Field(default=None, index=True)
    abonada: Optional[str] = Field(default=None, max_length=10)          # SI | NO | vacío (del libro)
    area_gasto: Optional[str] = Field(default=None, max_length=120)
    proveedor: Optional[str] = Field(default=None, max_length=200, index=True)
    nif: Optional[str] = Field(default=None, max_length=20, index=True)
    detalle: Optional[str] = Field(default=None, max_length=500)
    base: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)
    iva: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)
    retencion: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)
    total: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)
    forma_pago: Optional[str] = Field(default=None, max_length=60)
    pdf_ruta: Optional[str] = Field(default=None, max_length=400)        # relativa a backend/media
    origen: str = Field(default="libro", max_length=10)                  # libro | pdf (huérfano sin fila)
