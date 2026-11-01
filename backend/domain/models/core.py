"""Los 5 nodos-dios del sistema y su interconexión total.

Estos 5 son las anclas: toda otra entidad referencia a uno o varios de ellos
con FK explícita. Aquí se definen ellos y las relaciones de primer nivel entre sí.

    centro ──< colaborador        (un colaborador trabaja en >=1 centro)
    centro ──< paciente           (un paciente pertenece a un centro)
    centro ──< razon_social       (centro factura por >=1 razón social)
    paciente ──< cita >── colaborador ── centro
    cita ──< cita_tratamiento >── tratamiento   (qué se hace en la cita)
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship, SQLModel

from domain.models._base import TimestampMixin, utcnow


# ───────────────────────── NODO-DIOS 1: CENTRO ─────────────────────────
class CentroBase(SQLModel):
    # El CIF y la licencia sanitaria NO son del centro: viven en la razón social.
    nombre: str = Field(index=True, min_length=1, max_length=200)
    codigo: Optional[str] = Field(default=None, max_length=20, index=True)
    direccion: Optional[str] = Field(default=None, max_length=300)
    cp: Optional[str] = Field(default=None, max_length=10)
    poblacion: Optional[str] = Field(default=None, max_length=120)
    provincia: Optional[str] = Field(default=None, max_length=120)
    telefono: Optional[str] = Field(default=None, max_length=50)
    telefono_movil: Optional[str] = Field(default=None, max_length=50)
    email: Optional[str] = Field(default=None, max_length=255)
    web: Optional[str] = Field(default=None, max_length=255)
    instagram: Optional[str] = Field(default=None, max_length=120)
    icono_url: Optional[str] = Field(default=None, max_length=500)   # FICHERO (icono app)
    logo_url: Optional[str] = Field(default=None, max_length=500)   # FICHERO (logo membrete)
    num_gabinetes: Optional[int] = Field(default=None)
    fecha_alta: Optional[date] = Field(default=None)
    fecha_baja: Optional[date] = Field(default=None)   # cierre del centro
    activo: bool = Field(default=True, index=True)


class Centro(CentroBase, TimestampMixin, table=True):
    __tablename__ = "centros"
    id: Optional[int] = Field(default=None, primary_key=True)
    # Módulos contratados/activos del centro (JSON en BD). Lo consume /auth/me.
    modulos_activos: Any = Field(default=None, sa_column=Column(JSON))
    # Si está informado, este centro NO tiene razón social propia: factura con la de otro
    # centro (asociación con comparte_razon_social=True — ver CentroAsociacion).
    razon_social_compartida_id: Optional[int] = Field(default=None, foreign_key="razones_sociales.id", index=True)

    # hijos directos (todo cuelga del centro)
    # foreign_keys explícito: razon_social_compartida_id abre un 2º camino de FK entre
    # Centro↔RazonSocial (centro que LEE una razón social ajena, no la suya propia) —
    # sin esto SQLAlchemy no puede decidir solo cuál usar para esta relación.
    razones_sociales: list["RazonSocial"] = Relationship(
        back_populates="centro", sa_relationship_kwargs={"foreign_keys": "RazonSocial.centro_id"})
    pacientes: list["Paciente"] = Relationship(back_populates="centro")
    citas: list["Cita"] = Relationship(back_populates="centro")
    colaboradores: list["ColaboradorCentro"] = Relationship(back_populates="centro")


# ───────────────────────── ASOCIACIÓN ENTRE CENTROS ─────────────────────────
class CentroAsociacion(TimestampMixin, table=True):
    """Un centro asociado a otro, con lo que comparte elegido independientemente (ninguno,
    alguno o todos): personal (identidad ya global, solo se le da acceso también aquí),
    razón social (factura con la del asociado) y pacientes (guardado, aún SIN aplicar —
    dato clínico/RGPD, pendiente de un acceso cruzado dedicado)."""
    __tablename__ = "centro_asociaciones"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    asociado_a_centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    comparte_personal: bool = Field(default=False)
    comparte_razon_social: bool = Field(default=False)
    comparte_pacientes: bool = Field(default=False)


# ───────────── RAZÓN SOCIAL (entidad facturadora; sello vive aquí) ─────────────
class RazonSocialBase(SQLModel):
    nombre: str = Field(max_length=200)              # denominación social
    cif: Optional[str] = Field(default=None, max_length=20)
    licencia_sanitaria: Optional[str] = Field(default=None, max_length=120)
    # Domicilio fiscal — puede diferir del domicilio del centro (sede social).
    direccion: Optional[str] = Field(default=None, max_length=300)
    cp: Optional[str] = Field(default=None, max_length=10)
    poblacion: Optional[str] = Field(default=None, max_length=120)
    provincia: Optional[str] = Field(default=None, max_length=120)
    serie: Optional[str] = Field(default=None, max_length=20)   # serie facturación
    iban: Optional[str] = Field(default=None, max_length=34)
    sello_url: Optional[str] = Field(default=None, max_length=500)  # FICHERO
    fecha_alta: Optional[date] = Field(default=None)   # alta (traspaso)
    fecha_baja: Optional[date] = Field(default=None)   # baja (traspaso) → histórico, no se borra
    activa: bool = Field(default=True, index=True)


class RazonSocial(RazonSocialBase, TimestampMixin, table=True):
    __tablename__ = "razones_sociales"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    centro: Centro = Relationship(back_populates="razones_sociales",
                                  sa_relationship_kwargs={"foreign_keys": "RazonSocial.centro_id"})


# ───────────────────────── NODO-DIOS 2: PACIENTE ─────────────────────────
class PacienteBase(SQLModel):
    num_historia: Optional[str] = Field(default=None, max_length=30)  # NumPac (público)
    nombre: Optional[str] = Field(default=None, index=True, max_length=120)
    apellidos: Optional[str] = Field(default=None, index=True, max_length=200)
    nif: Optional[str] = Field(default=None, index=True, max_length=20)
    fecha_nacimiento: Optional[date] = Field(default=None)
    direccion: Optional[str] = Field(default=None, max_length=300)
    poblacion_id: Optional[int] = Field(default=None, index=True)
    cp: Optional[str] = Field(default=None, max_length=10)
    telefono_fijo: Optional[str] = Field(default=None, max_length=50)
    telefono_fijo2: Optional[str] = Field(default=None, max_length=50)
    telefono_movil: Optional[str] = Field(default=None, max_length=50)   # WhatsApp / SMS
    email: Optional[str] = Field(default=None, max_length=255)
    foto_url: Optional[str] = Field(default=None, max_length=500)        # FICHERO, no base64
    descuento: Optional[float] = Field(default=None)                     # % global
    campo_libre_1: Optional[str] = Field(default=None, max_length=200)
    campo_libre_2: Optional[str] = Field(default=None, max_length=200)
    campo_libre_3: Optional[str] = Field(default=None, max_length=200)
    notas: Optional[str] = Field(default=None, max_length=4000)
    fecha_alta: Optional[date] = Field(default=None)
    # consentimientos (valor actual; histórico en consentimientos_paciente)
    acepta_lopd: bool = Field(default=False)
    acepta_info: bool = Field(default=False)
    acepta_whatsapp: bool = Field(default=False)
    acepta_bots: bool = Field(default=False)
    # acceso a la app del paciente
    app_usuario: Optional[str] = Field(default=None, max_length=120, index=True)
    app_password_hash: Optional[str] = Field(default=None, max_length=255)   # SIEMPRE hash
    app_email_registro: Optional[str] = Field(default=None, max_length=255)
    app_fecha_registro: Optional[datetime] = Field(default=None)
    app_fecha_modificacion: Optional[datetime] = Field(default=None)
    app_version: Optional[str] = Field(default=None, max_length=20)
    app_fecha_instalacion: Optional[date] = Field(default=None)
    # estado
    activo: bool = Field(default=True, index=True)
    fecha_baja: Optional[date] = Field(default=None)
    motivo_inactivo: Optional[str] = Field(default=None, max_length=300)
    updated_by: Optional[int] = Field(default=None)   # usuario de última modificación
    # Responsable legal (menores / tutela): datos del responsable. El vínculo a otro
    # paciente, si lo hubiera, va por tutor_id; estos son los datos del responsable.
    responsable_nombre: Optional[str] = Field(default=None, max_length=200)
    responsable_nif: Optional[str] = Field(default=None, max_length=20)
    responsable_parentesco: Optional[str] = Field(default=None, max_length=60)
    # Datos médicos básicos (1:1 con el paciente).
    grupo_sanguineo: Optional[str] = Field(default=None, max_length=8)
    peso: Optional[float] = Field(default=None)
    altura: Optional[float] = Field(default=None)
    medico_cabecera: Optional[str] = Field(default=None, max_length=200)
    tel_medico: Optional[str] = Field(default=None, max_length=50)
    especialista: Optional[str] = Field(default=None, max_length=200)
    # Anamnesis = lista de ítems marcados (el catálogo vive en CONFIG: clave clinica.anamnesis).
    anamnesis: Any = Field(default=None, sa_column=Column(JSON))
    # datos_extra: DEPRECADO — cada bloque vive ya en su tabla (facturación→clientes,
    # seguro→paciente_seguros, responsable/datos médicos→columnas). Se conserva por compat.
    datos_extra: Any = Field(default=None, sa_column=Column(JSON))


class Paciente(PacienteBase, TimestampMixin, table=True):
    __tablename__ = "pacientes"
    id: Optional[int] = Field(default=None, primary_key=True)   # IdPac (interno)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    # Constraint único compuesto: num_historia debe ser único por centro
    # Nota: SQLModel no soporta UniqueConstraint directamente en Field, usar migración DB
    # Para implementación, ver script de migración en backend/scripts/
    cliente_id: Optional[int] = Field(default=None, foreign_key="clientes.id", index=True)  # IdCliPac (facturación, diferido)
    agenda_id: Optional[int] = Field(default=None, foreign_key="agendas.id", index=True)
    tutor_id: Optional[int] = Field(default=None, foreign_key="pacientes.id", index=True)   # IdPac_tutor (menores)

    centro: Centro = Relationship(back_populates="pacientes")
    citas: list["Cita"] = Relationship(
        back_populates="paciente",
        sa_relationship_kwargs={"foreign_keys": "[Cita.paciente_id]"},
    )
    alertas: list["AlertaPaciente"] = Relationship(back_populates="paciente")
    alergias: list["Alergia"] = Relationship(back_populates="paciente")
    medicaciones: list["MedicPreescrita"] = Relationship(back_populates="paciente")
    consentimientos: list["ConsentimientoPaciente"] = Relationship(back_populates="paciente")


class PacienteSeguro(TimestampMixin, table=True):
    """Seguro / mutua del paciente (un paciente puede tener varios)."""
    __tablename__ = "paciente_seguros"
    id: Optional[int] = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    aseguradora: Optional[str] = Field(default=None, max_length=160)
    num_poliza: Optional[str] = Field(default=None, max_length=80)
    num_ss: Optional[str] = Field(default=None, max_length=40)   # nº seguridad social
    activo: bool = Field(default=True, index=True)


class PacienteOtp(TimestampMixin, table=True):
    """Código OTP de acceso a la app del paciente (un solo uso, con caducidad).
    Mismo rigor que PasswordReset (identidad.py): hash en reposo, TTL, un solo uso."""
    __tablename__ = "paciente_otps"
    id: Optional[int] = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    codigo_hash: str = Field(index=True, max_length=64)   # sha256 hex del código de 6 dígitos
    canal: str = Field(max_length=20)                      # "whatsapp" | "email"
    expira_at: datetime = Field(index=True)
    usado_at: Optional[datetime] = Field(default=None)


class ConsentimientoPaciente(TimestampMixin, table=True):
    """Histórico de consentimientos RGPD del paciente: qué se aceptó, cuándo y qué versión."""
    __tablename__ = "consentimientos_paciente"
    id: Optional[int] = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    tipo: str = Field(max_length=40, index=True)   # lopd | info | whatsapp | bots | email | sms | postal
    aceptado: bool = Field(default=False)
    fecha: datetime = Field(default_factory=utcnow, index=True)
    version_texto: Optional[str] = Field(default=None, max_length=40)
    paciente: Paciente = Relationship(back_populates="consentimientos")


# ───────────────────────── NODO-DIOS 3: COLABORADOR ─────────────────────────
class ColaboradorBase(SQLModel):
    # El económico de UNA etapa. La identidad (nombre, apellidos, color, nif) es de la
    # persona (usuarios); el tipo de contrato es del periodo. Aquí, solo lo profesional/
    # económico de esa etapa, colgando de `periodo_id` (1:1 con usuario_periodos).
    num_colegiado: Optional[str] = Field(default=None, max_length=30)
    firma_url: Optional[str] = Field(default=None, max_length=500)  # FICHERO
    # económico / liquidación
    contrato_inicio: Optional[date] = Field(default=None)
    contrato_fin: Optional[date] = Field(default=None)
    factura_produccion: bool = Field(default=False)   # autónomo=sí, régimen general=no
    pct_produccion: Optional[float] = Field(default=None)           # % de producción (comisión)
    aplica_laboratorio: bool = Field(default=False)                 # descuenta coste de laboratorio
    tpc_gastos: Optional[float] = Field(default=None)               # % de gastos (lab) imputado
    aplica_irpf: bool = Field(default=False)                        # retención IRPF
    irpf_pct: Optional[float] = Field(default=None)                 # % de retención IRPF
    # ausencia
    ausencia_inicio: Optional[date] = Field(default=None)
    ausencia_fin: Optional[date] = Field(default=None)
    activo: bool = Field(default=True, index=True)


class Colaborador(ColaboradorBase, TimestampMixin, table=True):
    __tablename__ = "colaboradores"
    id: Optional[int] = Field(default=None, primary_key=True)   # IdCol (incremental al marcar colaborador)
    # 1:1 con la etapa: este económico pertenece a un periodo concreto de la persona
    periodo_id: Optional[int] = Field(default=None, foreign_key="usuario_periodos.id", index=True, unique=True)
    # exención de comisión: varios tratamientos (tabla colaborador_tratamiento_exento) con un precio único
    precio_tratamiento_exento: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    # talonario oficial de recetas asignado
    talonario_id: Optional[int] = Field(default=None, foreign_key="talonarios.id", index=True)

    citas: list["Cita"] = Relationship(back_populates="colaborador")
    centros: list["ColaboradorCentro"] = Relationship(back_populates="colaborador")
    especialidades: list["ColaboradorEspecialidad"] = Relationship(back_populates="colaborador")


class Especialidad(TimestampMixin, table=True):
    """Catálogo de especialidades (un colaborador puede tener varias)."""
    __tablename__ = "especialidades"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: Optional[int] = Field(default=None, foreign_key="centros.id", index=True)
    codigo: Optional[str] = Field(default=None, max_length=20, index=True)
    nombre: str = Field(max_length=120, index=True)
    activo: bool = Field(default=True, index=True)


class ColaboradorEspecialidad(TimestampMixin, table=True):
    """N:M colaborador↔especialidad (idEspecia múltiple)."""
    __tablename__ = "colaborador_especialidad"
    colaborador_id: int = Field(foreign_key="colaboradores.id", primary_key=True, index=True)
    especialidad_id: int = Field(foreign_key="especialidades.id", primary_key=True, index=True)
    colaborador: Colaborador = Relationship(back_populates="especialidades")


class ColaboradorTratamientoExento(TimestampMixin, table=True):
    """N:M colaborador↔tratamiento exento de comisión.
    El precio único de la exención vive en colaboradores.precio_tratamiento_exento."""
    __tablename__ = "colaborador_tratamiento_exento"
    colaborador_id: int = Field(foreign_key="colaboradores.id", primary_key=True, index=True)
    tratamiento_id: int = Field(foreign_key="tratamientos.id", primary_key=True, index=True)


class ColaboradorTipoCita(TimestampMixin, table=True):
    """Duración (min) de un tipo de cita para un colaborador concreto. Sin default global."""
    __tablename__ = "colaborador_tipo_cita"
    colaborador_id: int = Field(foreign_key="colaboradores.id", primary_key=True, index=True)
    tipo_cita_id: int = Field(foreign_key="tipos_cita.id", primary_key=True, index=True)
    duracion_min: int = Field(nullable=False)


class ColaboradorCentro(TimestampMixin, table=True):
    """N:M colaborador↔centro (un doctor trabaja en varios centros)."""
    __tablename__ = "colaborador_centro"
    colaborador_id: int = Field(foreign_key="colaboradores.id", primary_key=True, index=True)
    centro_id: int = Field(foreign_key="centros.id", primary_key=True, index=True)
    colaborador: Colaborador = Relationship(back_populates="centros")
    centro: Centro = Relationship(back_populates="colaboradores")


# ───────────────────────── NODO-DIOS 4: CITA ─────────────────────────
class CitaBase(SQLModel):
    id_cita: Optional[int] = Field(default=None, index=True)   # hilo lógico (incremental por cita)
    fecha_alta: Optional[datetime] = Field(default=None)       # creación (inmutable)
    fecha: date = Field(index=True)                            # hueco: día
    hora: Optional[str] = Field(default=None, max_length=5)    # hueco: HH:MM
    duracion_min: Optional[int] = Field(default=None)
    fecha_hora_estado: Optional[datetime] = Field(default=None)  # cuándo se fijó el estado
    # Sellos de vida de la cita (columnas de la migración 088). cita_reglas los rellena al
    # insertar y renueva el de modificación en cada UPDATE; sin declararlos aquí, crear o
    # editar una cita reventaba con AttributeError (23-oct-2026).
    fecha_hora_creacion: Optional[datetime] = Field(default=None)
    fecha_hora_modificacion: Optional[datetime] = Field(default=None)
    # identidad inline (cuando no hay ficha): nombre y apellidos SIEMPRE separados
    num_historia: Optional[str] = Field(default=None, max_length=30, index=True)
    nombre: Optional[str] = Field(default=None, max_length=120)
    apellidos: Optional[str] = Field(default=None, max_length=200)
    telefono_movil: Optional[str] = Field(default=None, max_length=50)
    nif: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=255)
    fecha_nacimiento: Optional[date] = Field(default=None)
    id_externo: Optional[str] = Field(default=None, max_length=80)   # IdPacExt
    # económico / tipo
    gratuita: bool = Field(default=False)
    # operativa de sala
    hora_llegada: Optional[str] = Field(default=None, max_length=5)
    retraso_min: Optional[int] = Field(default=None)
    hora_ini_real: Optional[str] = Field(default=None, max_length=5)
    hora_fin_real: Optional[str] = Field(default=None, max_length=5)
    recordada: bool = Field(default=False)
    confirmada: bool = Field(default=False, index=True)
    envio_doc: bool = Field(default=False)
    firmado: bool = Field(default=False)
    aceptada: bool = Field(default=False)
    anulacion_gestionada: bool = Field(default=False)
    campo_libre_1: Optional[str] = Field(default=None, max_length=200)
    notas: Optional[str] = Field(default=None, max_length=2000)


class Cita(CitaBase, TimestampMixin, table=True):
    __tablename__ = "citas"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    agenda_id: Optional[int] = Field(default=None, foreign_key="agendas.id", index=True)
    estado_id: Optional[int] = Field(default=None, foreign_key="estados_cita.id", index=True)
    paciente_id: Optional[int] = Field(default=None, foreign_key="pacientes.id", index=True)  # opcional (lead/contacto inline)
    tutor_id: Optional[int] = Field(default=None, foreign_key="pacientes.id", index=True)     # menores
    colaborador_id: Optional[int] = Field(default=None, foreign_key="colaboradores.id", index=True)  # IdCol = doctor
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuarios.id", index=True)    # IdUsu = usuario logado
    gabinete_id: Optional[int] = Field(default=None, foreign_key="gabinetes.id", index=True)  # Box
    tipo_cita_id: Optional[int] = Field(default=None, foreign_key="tipos_cita.id", index=True)  # IdTto_Agenda
    tarifa_id: Optional[int] = Field(default=None, foreign_key="tarifas.id", index=True)

    centro: Centro = Relationship(back_populates="citas")
    paciente: Optional[Paciente] = Relationship(
        back_populates="citas",
        sa_relationship_kwargs={"foreign_keys": "[Cita.paciente_id]"},
    )
    colaborador: Optional[Colaborador] = Relationship(back_populates="citas")
    tratamientos: list["CitaTratamiento"] = Relationship(back_populates="cita")


# ───────────────────────── NODO-DIOS 5: TRATAMIENTO ─────────────────────────
class TratamientoBase(SQLModel):
    codigo: str = Field(index=True, max_length=30)
    nombre: str = Field(index=True, max_length=200)          # descripción médica
    descripcion_paciente: Optional[str] = Field(default=None, max_length=300)
    descripcion_agenda: Optional[str] = Field(default=None, max_length=300)
    duracion_base_min: Optional[int] = Field(default=None)
    num_actos: Optional[int] = Field(default=None)
    num_fases: Optional[int] = Field(default=None)
    online: bool = Field(default=False)                      # reservable online
    solo_presupuestos: bool = Field(default=False)
    no_planificable: bool = Field(default=False)
    con_garantia: bool = Field(default=False)
    fuera_produccion: bool = Field(default=False)            # no computa comisión
    # Mensualidad: al ACEPTAR el presupuesto, la línea (cantidad = nº de mensualidades) se despliega
    # en N fases en tratamientos_previstos, cada una al precio unitario (ver _volcar_a_previstos).
    es_mensualidad: bool = Field(default=False)
    consentimiento_tipo: Optional[str] = Field(default=None, max_length=40, index=True)
    fecha_alta: Optional[date] = Field(default=None)
    fecha_baja: Optional[date] = Field(default=None)
    activo: bool = Field(default=True, index=True)


class Tratamiento(TratamientoBase, TimestampMixin, table=True):
    __tablename__ = "tratamientos"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    especialidad_id: Optional[int] = Field(default=None, foreign_key="especialidades.id", index=True)
    tipo_cita_id: Optional[int] = Field(default=None, foreign_key="tipos_cita.id", index=True)  # familia del tratamiento (tipos_cita = catálogo de familias)
    # Ámbito del acto (GELITE): diente | arcada | cuadrante | sextante | tratamiento (general).
    # Es la FUENTE DE VERDAD para el selector de pieza/zona en Nuevo acto y Presupuestos.
    tipo_actuacion: Optional[str] = Field(default=None, max_length=20)
    citas: list["CitaTratamiento"] = Relationship(back_populates="tratamiento")


class CitaTratamiento(TimestampMixin, table=True):
    """N:M cita↔tratamiento (qué se hace/realiza en cada cita)."""
    __tablename__ = "cita_tratamiento"
    id: Optional[int] = Field(default=None, primary_key=True)
    cita_id: int = Field(foreign_key="citas.id", nullable=False, index=True)
    tratamiento_id: int = Field(foreign_key="tratamientos.id", nullable=False, index=True)
    pieza: Optional[str] = Field(default=None, max_length=10)   # nº diente FDI
    realizado: bool = Field(default=False, index=True)

    cita: Cita = Relationship(back_populates="tratamientos")
    tratamiento: Tratamiento = Relationship(back_populates="citas")


# ───────────────────────── CATÁLOGOS: FASES Y GEOGRAFÍA ─────────────────────────
class TratamientoFase(TimestampMixin, table=True):
    """Fase del catálogo de un tratamiento (orden, duración, % a facturar)."""
    __tablename__ = "tratamiento_fases"
    id: Optional[int] = Field(default=None, primary_key=True)
    tratamiento_id: int = Field(foreign_key="tratamientos.id", nullable=False, index=True)
    descripcion: str = Field(max_length=200)
    notas: Optional[str] = Field(default=None, max_length=500)
    orden_ejecucion: Optional[int] = Field(default=None)
    duracion_min: Optional[int] = Field(default=None)
    pct_facturar: Optional[float] = Field(default=None)
    min_dias: Optional[int] = Field(default=None)
    max_dias: Optional[int] = Field(default=None)


class Poblacion(TimestampMixin, table=True):
    """Catálogo LEGADO de poblaciones (datos sucios heredados de la migración GELITE,
    con duplicados/erratas — ver auditoría 27-sep-2026). NO usar para nada nuevo:
    usar Pais/Provincia/Municipio/CodigoPostalGeo, que son datos oficiales del INE."""
    __tablename__ = "poblaciones"
    id: Optional[int] = Field(default=None, primary_key=True)
    nombre: str = Field(index=True, max_length=120)
    provincia: Optional[str] = Field(default=None, max_length=120)
    pais: Optional[str] = Field(default=None, max_length=80)


class CodigoPostal(TimestampMixin, table=True):
    """CP ↔ población LEGADO — ver aviso en Poblacion. No usar para nada nuevo."""
    __tablename__ = "codigos_postales"
    id: Optional[int] = Field(default=None, primary_key=True)
    cp: str = Field(index=True, max_length=10)
    poblacion_id: int = Field(foreign_key="poblaciones.id", nullable=False, index=True)


class Pais(TimestampMixin, table=True):
    """Catálogo oficial de países (ISO 3166-1 alpha-2)."""
    __tablename__ = "paises"
    id: Optional[int] = Field(default=None, primary_key=True)
    iso2: str = Field(index=True, unique=True, max_length=2)
    nombre: str = Field(index=True, max_length=120)


class Provincia(TimestampMixin, table=True):
    """Catálogo oficial de provincias españolas (INE)."""
    __tablename__ = "provincias"
    id: Optional[int] = Field(default=None, primary_key=True)
    pais_id: int = Field(foreign_key="paises.id", nullable=False, index=True)
    ine_id: str = Field(index=True, max_length=5)
    nombre: str = Field(index=True, max_length=120)


class Municipio(TimestampMixin, table=True):
    """Catálogo oficial de municipios españoles (INE, Callejero del Censo Electoral)."""
    __tablename__ = "municipios"
    id: Optional[int] = Field(default=None, primary_key=True)
    provincia_id: int = Field(foreign_key="provincias.id", nullable=False, index=True)
    ine_id: str = Field(index=True, max_length=5)
    nombre: str = Field(index=True, max_length=150)


class CodigoPostalGeo(TimestampMixin, table=True):
    """CP ↔ municipio oficial (INE). Un municipio puede tener varios CP y,
    raramente, un CP puede repartirse entre municipios colindantes."""
    __tablename__ = "codigos_postales_geo"
    id: Optional[int] = Field(default=None, primary_key=True)
    cp: str = Field(index=True, max_length=5)
    municipio_id: int = Field(foreign_key="municipios.id", nullable=False, index=True)


class DispositivoPaciente(TimestampMixin, table=True):
    """Dispositivo del paciente (app/push/firma). Origen: DispositivoPac."""
    __tablename__ = "dispositivos_paciente"
    id: Optional[int] = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    tipo: Optional[str] = Field(default=None, max_length=40)
    id_tipo: Optional[str] = Field(default=None, max_length=120)   # token/identificador
    a_firmar: bool = Field(default=False)
