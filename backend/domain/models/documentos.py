"""Documentos — recetas, consentimientos, PDFs. FK a nodos-dios.

    paciente ──< receta ──< receta_linea
    paciente ──< consentimiento >── tratamiento (opcional)
    paciente ──< documento_generado   (factura/recibo/justificante PDF)

El membrete usa logo del centro (centros.logo_url) y el sello de la razón
social (razones_sociales.sello_url) — ambos como FICHERO/URL, nunca base64.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, Relationship, SQLModel

from domain.models._base import TimestampMixin


class Talonario(TimestampMixin, table=True):
    """Talonario oficial de recetas asignado a un colaborador (lote numerado)."""
    __tablename__ = "talonarios"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    colaborador_id: int = Field(foreign_key="colaboradores.id", nullable=False, index=True)
    numero_lote: Optional[str] = Field(default=None, max_length=40, index=True)
    total_numeros: Optional[int] = Field(default=None)
    importado_at: Optional[datetime] = Field(default=None)
    activo: bool = Field(default=True, index=True)
    numeros: list["TalonarioReceta"] = Relationship(back_populates="talonario")


class TalonarioReceta(TimestampMixin, table=True):
    """Número individual de un talonario (cve oficial, marcado al usarse)."""
    __tablename__ = "talonario_recetas"
    id: Optional[int] = Field(default=None, primary_key=True)
    talonario_id: int = Field(foreign_key="talonarios.id", nullable=False, index=True)
    numero: str = Field(max_length=40, index=True)
    cve: Optional[str] = Field(default=None, max_length=60)   # código de verificación
    usada: bool = Field(default=False, index=True)
    usada_at: Optional[datetime] = Field(default=None)
    talonario: Talonario = Relationship(back_populates="numeros")


class Receta(TimestampMixin, table=True):
    __tablename__ = "recetas"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    colaborador_id: Optional[int] = Field(default=None, foreign_key="colaboradores.id", index=True)
    cita_id: Optional[int] = Field(default=None, foreign_key="citas.id", index=True)
    talonario_receta_id: Optional[int] = Field(default=None, foreign_key="talonario_recetas.id", index=True)
    fecha: date = Field(index=True)
    tipo_receta: Optional[str] = Field(default=None, max_length=40)
    descripcion: Optional[str] = Field(default=None, max_length=300)
    diagnostico: Optional[str] = Field(default=None, max_length=300)
    notas: Optional[str] = Field(default=None, max_length=1000)               # instrucciones al paciente
    notas_farmaceutico: Optional[str] = Field(default=None, max_length=1000)  # motivo de la sustitución
    urgencia: bool = Field(default=False)
    desabastecimiento: bool = Field(default=False)
    cve: Optional[str] = Field(default=None, max_length=60)
    publico: bool = Field(default=False)
    dispensada: bool = Field(default=False, index=True)
    anulada: bool = Field(default=False, index=True)
    aprobada: bool = Field(default=False, index=True)   # requiere firma del doctor
    archivo_url: Optional[str] = Field(default=None, max_length=500)
    lineas: list["RecetaLinea"] = Relationship(back_populates="receta")


class RecetaLinea(TimestampMixin, table=True):
    __tablename__ = "receta_lineas"
    id: Optional[int] = Field(default=None, primary_key=True)
    receta_id: int = Field(foreign_key="recetas.id", nullable=False, index=True)
    tratamiento_id: Optional[int] = Field(default=None, foreign_key="tratamientos.id", index=True)
    farmaco: str = Field(max_length=200)
    posologia: Optional[str] = Field(default=None, max_length=300)
    pauta: Optional[str] = Field(default=None, max_length=300)
    duracion: Optional[str] = Field(default=None, max_length=60)
    envases: Optional[int] = Field(default=None)
    unidades: Optional[int] = Field(default=None)
    orden_dispensacion: Optional[int] = Field(default=None)
    receta: Receta = Relationship(back_populates="lineas")


class Consentimiento(TimestampMixin, table=True):
    __tablename__ = "consentimientos"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    tratamiento_id: Optional[int] = Field(default=None, foreign_key="tratamientos.id", index=True)
    tipo: str = Field(max_length=120)
    estado: str = Field(default="pendiente", index=True)   # pendiente|firmado|revocado
    firma_url: Optional[str] = Field(default=None, max_length=500)
    archivo_url: Optional[str] = Field(default=None, max_length=500)
    signing_code: Optional[str] = Field(default=None, max_length=24, index=True)   # firma pública por enlace (WhatsApp)
    signing_code_expira: Optional[datetime] = Field(default=None)   # caduca mientras esté 'pendiente'; ver expirado()


class RecomendacionPaciente(TimestampMixin, table=True):
    """Recomendaciones seleccionadas al final de la consulta (Caminos 1, 2, 3)."""
    __tablename__ = "recomendaciones_paciente"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    cita_id: Optional[int] = Field(default=None, foreign_key="citas.id", index=True)
    items: Optional[dict] = Field(default=None, sa_column=Column(JSON))  # claves del catálogo marcadas
    texto_generado: Optional[str] = Field(default=None, max_length=2000)  # texto final imprimible/enviable
    archivo_url: Optional[str] = Field(default=None, max_length=500)


class DocumentoGenerado(TimestampMixin, table=True):
    """PDF generado (factura/recibo/justificante) con membrete del centro + sello."""
    __tablename__ = "documentos_generados"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    paciente_id: Optional[int] = Field(default=None, foreign_key="pacientes.id", index=True)
    razon_social_id: Optional[int] = Field(default=None, foreign_key="razones_sociales.id", index=True)
    presupuesto_id: Optional[int] = Field(default=None, foreign_key="presupuestos.id", index=True)
    tipo: str = Field(max_length=60, index=True)   # factura|recibo|justificante|presupuesto
    archivo_url: str = Field(max_length=500)


class DocumentoAdmin(TimestampMixin, table=True):
    """Documento administrativo / factura (con datos fiscales). Origen: DocAdmin."""
    __tablename__ = "documentos_admin"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    cliente_id: Optional[int] = Field(default=None, foreign_key="clientes.id", index=True)
    razon_social_id: Optional[int] = Field(default=None, foreign_key="razones_sociales.id", index=True)
    tipo_documento: Optional[str] = Field(default=None, max_length=40, index=True)  # factura|abono|recibo…
    tipo_factura: Optional[str] = Field(default=None, max_length=40)
    serie: Optional[str] = Field(default=None, max_length=20, index=True)
    num_doc: Optional[int] = Field(default=None, index=True)
    anyo: Optional[int] = Field(default=None, index=True)
    fecha: date = Field(index=True)
    # datos fiscales del receptor
    nombre: Optional[str] = Field(default=None, max_length=120)
    apellidos: Optional[str] = Field(default=None, max_length=200)
    nif: Optional[str] = Field(default=None, max_length=20)
    nif_tutor: Optional[str] = Field(default=None, max_length=20)
    direccion: Optional[str] = Field(default=None, max_length=300)
    cp: Optional[str] = Field(default=None, max_length=10)
    concepto: Optional[str] = Field(default=None, max_length=500)
    abonado: bool = Field(default=False)
    importe_abono: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)
    # fiscal / factura electrónica
    serie_oficial: Optional[str] = Field(default=None, max_length=20)
    num_doc_oficial: Optional[str] = Field(default=None, max_length=40)
    hash_factura: Optional[str] = Field(default=None, max_length=120)
    codigo_qr: Optional[str] = Field(default=None, max_length=500)
    codigo_atcud: Optional[str] = Field(default=None, max_length=40)
    num_transaccion: Optional[str] = Field(default=None, max_length=80)
    anulada: bool = Field(default=False, index=True)


class DocumentoPaciente(TimestampMixin, table=True):
    """Documento/fichero adjunto a la ficha del paciente. Origen: TDocumentosPac."""
    __tablename__ = "documentos_paciente"
    id: Optional[int] = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    fecha: Optional[date] = Field(default=None, index=True)
    tipo_doc: Optional[str] = Field(default=None, max_length=60)
    descripcion: Optional[str] = Field(default=None, max_length=300)
    archivo_url: Optional[str] = Field(default=None, max_length=500)   # "Original"
    notas: Optional[str] = Field(default=None, max_length=1000)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuarios.id", index=True)
    # Rectificativa aportada desde la ficha del paciente; conserva el vínculo fiscal original.
    factura_origen_id: Optional[int] = Field(default=None, foreign_key="documentos_admin.id", index=True)
    motivo_rectificacion: Optional[str] = Field(default=None, max_length=500)


class DocumentoFirmado(TimestampMixin, table=True):
    """Documento firmado (digitalmente) por paciente o colaborador. Origen: DocsFirmados."""
    __tablename__ = "documentos_firmados"
    id: Optional[int] = Field(default=None, primary_key=True)
    paciente_id: Optional[int] = Field(default=None, foreign_key="pacientes.id", index=True)
    fecha: Optional[date] = Field(default=None, index=True)
    tipo_doc: Optional[str] = Field(default=None, max_length=60)
    tipo_firma: Optional[str] = Field(default=None, max_length=40)
    descripcion: Optional[str] = Field(default=None, max_length=300)
    archivo_url: Optional[str] = Field(default=None, max_length=500)   # "Original"
    firmado: bool = Field(default=False, index=True)
    firma_usuario_id: Optional[int] = Field(default=None, foreign_key="usuarios.id", index=True)
    colaborador_firma_id: Optional[int] = Field(default=None, foreign_key="colaboradores.id", index=True)
    firmado_colaborador: bool = Field(default=False)
    estado: Optional[str] = Field(default=None, max_length=40, index=True)
    fecha_publicado: Optional[datetime] = Field(default=None)


class RecetaFrecuente(TimestampMixin, table=True):
    """Receta frecuente del doctor (plantilla para reutilizar rápidamente)."""
    __tablename__ = "recetas_frecuentes"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    colaborador_id: int = Field(foreign_key="colaboradores.id", nullable=False, index=True)
    nombre: str = Field(max_length=100, index=True)  # ej: "Dolor post-exodoncia"
    medicamentos: Any = Field(default=None, sa_column=Column(JSON))  # array de {farmaco, posologia, pauta, duracion, envases, unidades}
    activo: bool = Field(default=True, index=True)


class PlantillaDocumento(TimestampMixin, table=True):
    """Plantilla de documento (carta, informe…). Origen: EdDocs."""
    __tablename__ = "plantillas_documento"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    grupo: Optional[str] = Field(default=None, max_length=80, index=True)
    subgrupo: Optional[str] = Field(default=None, max_length=80)
    titulo: str = Field(max_length=200)
    especialidad_id: Optional[int] = Field(default=None, foreign_key="especialidades.id", index=True)
    colaborador_id: Optional[int] = Field(default=None, foreign_key="colaboradores.id", index=True)
    idioma: Optional[str] = Field(default=None, max_length=10)
    publico: bool = Field(default=False)
    cuerpo: Optional[str] = Field(default=None, max_length=8000)
    activo: bool = Field(default=True, index=True)
