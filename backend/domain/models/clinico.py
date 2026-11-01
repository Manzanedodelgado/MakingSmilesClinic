"""Entidades clínicas del paciente — todas FK a nodos-dios.

Interconexión brutal: cada dato clínico apunta SIEMPRE al paciente, y cuando
procede también a la cita y/o al tratamiento que lo originó. Así una imagen Rx
sabe de qué cita, qué paciente y (vía hallazgo) qué acto clínico es; un SOAP
sabe de qué cita y paciente; una alerta cuelga del paciente.

    paciente ──< alerta / alergia / medic_preescrita
    medic_preescrita ──> vademecum (catálogo de fármacos)
    paciente ──< imagen_rx ──> cita (opcional)
    paciente ──< soap ──> cita
    cita_tratamiento ──< hallazgo_imagen >── imagen_rx   (cruce imagen↔acto)
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from domain.models._base import TimestampMixin, utcnow


SEVERIDAD = "leve | moderada | grave | critica"


# ───────────────────────── ALERTAS / ANTECEDENTES ─────────────────────────
class AlertaPaciente(TimestampMixin, table=True):
    __tablename__ = "alertas_paciente"
    id: Optional[int] = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    texto: str = Field(max_length=500)
    severidad: Optional[str] = Field(default=None, max_length=20)
    activo: bool = Field(default=True, index=True)
    paciente: "Paciente" = Relationship(back_populates="alertas")


class Alergia(TimestampMixin, table=True):
    __tablename__ = "alergias"
    id: Optional[int] = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    nombre: str = Field(max_length=200)
    severidad: Optional[str] = Field(default=None, max_length=20)
    paciente: "Paciente" = Relationship(back_populates="alergias")


class TipoAntecedente(TimestampMixin, table=True):
    """Tipo de antecedente médico (catálogo)."""
    __tablename__ = "tipos_antecedente"
    id: Optional[int] = Field(default=None, primary_key=True)
    descripcion: str = Field(max_length=200)
    activo: bool = Field(default=True, index=True)


class SubtipoAntecedente(TimestampMixin, table=True):
    """Subtipo de antecedente médico. Origen: TSubTipoAntecedentes."""
    __tablename__ = "subtipos_antecedente"
    id: Optional[int] = Field(default=None, primary_key=True)
    tipo_antecedente_id: Optional[int] = Field(default=None, foreign_key="tipos_antecedente.id", index=True)
    descripcion: str = Field(max_length=200)
    agrupado: Optional[str] = Field(default=None, max_length=120)
    activo: bool = Field(default=True, index=True)


class Diagnostico(TimestampMixin, table=True):
    """Catálogo de diagnósticos (CIE / ICD-9)."""
    __tablename__ = "diagnosticos"
    id: Optional[int] = Field(default=None, primary_key=True)
    codigo: str = Field(index=True, max_length=20)
    descripcion: str = Field(max_length=300)
    visible: bool = Field(default=True, index=True)


class Vademecum(TimestampMixin, table=True):
    """Catálogo de fármacos: descripción, presentación, clasificación ATC y precio."""
    __tablename__ = "vademecum"
    id: Optional[int] = Field(default=None, primary_key=True)
    cod_nacional: Optional[str] = Field(default=None, max_length=20, index=True)
    descripcion: str = Field(index=True, max_length=300)
    presentacion: Optional[str] = Field(default=None, max_length=300)
    cod_atc: Optional[str] = Field(default=None, max_length=20, index=True)
    nombre_atc: Optional[str] = Field(default=None, max_length=200)
    laboratorio: Optional[str] = Field(default=None, max_length=200)
    composicion: Optional[str] = Field(default=None, max_length=1000)
    indicacion: Optional[str] = Field(default=None, max_length=1000)
    posologia: Optional[str] = Field(default=None, max_length=500)
    precio: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    activo: bool = Field(default=True, index=True)


class MedicPreescrita(TimestampMixin, table=True):
    """Medicación prescrita a un paciente: fármaco, dosis, vía y pauta."""
    __tablename__ = "medic_preescrita"
    id: Optional[int] = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    vademecum_id: Optional[int] = Field(default=None, foreign_key="vademecum.id", index=True)
    farmaco: str = Field(max_length=300)
    dosis: Optional[str] = Field(default=None, max_length=100)
    via_administracion: Optional[str] = Field(default=None, max_length=60)
    frecuencia: Optional[str] = Field(default=None, max_length=120)
    pauta: Optional[str] = Field(default=None, max_length=500)
    fecha_inicio: Optional[date] = Field(default=None)
    fecha_fin: Optional[date] = Field(default=None)
    notas: Optional[str] = Field(default=None, max_length=1000)
    activo: bool = Field(default=True, index=True)
    paciente: "Paciente" = Relationship(back_populates="medicaciones")


# ───────────────────────── IMAGEN / Rx ─────────────────────────
class ImagenRx(TimestampMixin, table=True):
    __tablename__ = "imagenes_rx"
    id: Optional[int] = Field(default=None, primary_key=True)
    # FK paciente (siempre) + cita (cuando se tomó en una cita)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    cita_id: Optional[int] = Field(default=None, foreign_key="citas.id", index=True)
    modalidad: str = Field(max_length=40)                 # PANO, CBCT, periapical…
    archivo_url: str = Field(max_length=500)              # FICHERO/Orthanc
    orthanc_study_id: Optional[str] = Field(default=None, max_length=120, index=True)
    hallazgos: list["HallazgoImagen"] = Relationship(back_populates="imagen")


class HallazgoImagen(TimestampMixin, table=True):
    """Hallazgo detectado en una imagen, cruzado con el acto clínico (pieza)."""
    __tablename__ = "hallazgos_imagen"
    id: Optional[int] = Field(default=None, primary_key=True)
    imagen_id: int = Field(foreign_key="imagenes_rx.id", nullable=False, index=True)
    # cruce imagen ↔ acto/tratamiento realizado (opcional)
    cita_tratamiento_id: Optional[int] = Field(
        default=None, foreign_key="cita_tratamiento.id", index=True)
    descripcion: str = Field(max_length=500)
    pieza: Optional[str] = Field(default=None, max_length=10)
    confianza: Optional[float] = Field(default=None)      # 0..1 si lo marca la IA
    imagen: ImagenRx = Relationship(back_populates="hallazgos")


class RomexisSync(TimestampMixin, table=True):
    """Cola/máquina de estados del puente de pacientes web → Romexis (PMBridge).

    Flujo: al crear un paciente en la web se encola en `pendiente`. El agente del PC de Romexis
    consulta la cola, mira si el ID existe en Romexis y reporta el resultado:
      · no existe                       → agente crea (DxStart) → `creado`
      · existe con MISMO id+nombre+apel. → agente abre (DxStart) → `abierto`
      · existe con MISMO id, DISTINTO nombre → `conflicto_id` (guarda el nombre de Romexis);
        la web pregunta si modificar. Si SÍ → `modificar` (agente lo cambia) → `resuelto`;
        si NO → `nuevo_circuito` (ese id pudo usarse para otro paciente por error → revisión).
    """
    __tablename__ = "romexis_sync"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(nullable=False, index=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    num_historia: str = Field(max_length=30, index=True)
    apellidos: str = Field(max_length=200)
    nombre: str = Field(max_length=120)
    fecha_nacimiento: Optional[date] = Field(default=None)
    estado: str = Field(default="pendiente", index=True, max_length=20)
    # Lo que el agente encontró en Romexis para ese ID (para resolver el conflicto).
    romexis_apellidos: Optional[str] = Field(default=None, max_length=200)
    romexis_nombre: Optional[str] = Field(default=None, max_length=120)
    intentos: int = Field(default=0)
    detalle: Optional[str] = Field(default=None, max_length=400)


class AnalisisCefalo(TimestampMixin, table=True):
    """Análisis cefalométrico definido por el centro (a medida). `landmarks_json` = puntos a colocar
    [{code,label,hint}]; `medidas_json` = fórmulas [{code,label,tipo,puntos,norma,sd,unidad}]. El motor
    de geometría las calcula igual que Steiner/Ricketts. Scope por centro."""
    __tablename__ = "analisis_cefalo"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(nullable=False, index=True)
    slug: str = Field(max_length=60, index=True)          # identificador estable (p. ej. custom_3)
    nombre: str = Field(max_length=120)
    landmarks_json: list = Field(default_factory=list, sa_column=Column(JSON))
    medidas_json: list = Field(default_factory=list, sa_column=Column(JSON))


class AnotacionImagen(TimestampMixin, table=True):
    """Anotaciones gráficas sobre una imagen radiológica (flechas, líneas/medidas, ángulos, texto).
    Una fila por imagen: `items_json` es la lista completa de anotaciones (upsert por imagen)."""
    __tablename__ = "anotaciones_imagen"
    id: Optional[int] = Field(default=None, primary_key=True)
    imagen_id: int = Field(foreign_key="imagenes_rx.id", nullable=False, index=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    items_json: list = Field(default_factory=list, sa_column=Column(JSON))


class AnalisisDentia(TimestampMixin, table=True):
    """Análisis DentIA de UNA imagen de Multimedia (identificada por su `file_id`, no por ImagenRx):
    paso del flujo (1 Procesar · 2 Patrones · 3 Plan · 4 Informe), patrones marcados (IA o doctor) y
    plan de tratamiento por hallazgo. Una fila por (paciente, imagen)."""
    __tablename__ = "analisis_dentia"
    __table_args__ = (UniqueConstraint("paciente_id", "file_id", name="uq_analisis_dentia_pac_file"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    file_id: str = Field(max_length=500, index=True)
    paso: int = Field(default=1)
    patrones_json: list = Field(default_factory=list, sa_column=Column(JSON))
    plan_json: list = Field(default_factory=list, sa_column=Column(JSON))


class Cefalometria(TimestampMixin, table=True):
    """Trazado cefalométrico sobre una telerradiografía lateral: landmarks colocados por el doctor +
    calibración + medidas calculadas por el motor de geometría. Una por (imagen, análisis)."""
    __tablename__ = "cefalometrias"
    id: Optional[int] = Field(default=None, primary_key=True)
    imagen_id: int = Field(foreign_key="imagenes_rx.id", nullable=False, index=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    analisis: str = Field(default="steiner", max_length=40)
    landmarks_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    calibracion_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    mediciones_json: dict = Field(default_factory=dict, sa_column=Column(JSON))


# ───────────────────────── SOAP (nota de consulta) ─────────────────────────
class Soap(TimestampMixin, table=True):
    __tablename__ = "soap"
    id: Optional[int] = Field(default=None, primary_key=True)
    # un SOAP pertenece a una cita (y por ella, a paciente+colaborador+centro)
    cita_id: int = Field(foreign_key="citas.id", nullable=False, index=True, unique=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    subjetivo: Optional[str] = Field(default=None, max_length=4000)
    objetivo: Optional[str] = Field(default=None, max_length=4000)
    analisis: Optional[str] = Field(default=None, max_length=4000)
    plan: Optional[str] = Field(default=None, max_length=4000)
    aprobado: bool = Field(default=False, index=True)


# ──────────────────── PLAN PRÓXIMA CITA (doctor → recepción) ────────────────────
class PlanProximaCita(TimestampMixin, table=True):
    """Lo que el doctor deja planificado para la PRÓXIMA cita del paciente: tratamientos
    a realizar y minutos estimados. Recepción lo consulta antes de agendar y enviarlo.
    items = lista de {linea_id?, tratamiento, pieza?, minutos}. Uno pendiente por paciente."""
    __tablename__ = "plan_proxima_cita"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    colaborador_id: Optional[int] = Field(default=None, foreign_key="colaboradores.id", index=True)
    presupuesto_id: Optional[int] = Field(default=None, foreign_key="presupuestos.id", index=True)
    minutos: int = Field(default=0)
    nota: Optional[str] = Field(default=None, max_length=500)
    items: Any = Field(default=None, sa_column=Column(JSON))
    estado: str = Field(default="pendiente", max_length=20, index=True)  # pendiente | agendada | cancelada


class RxExportada(TimestampMixin, table=True):
    """Registro de cada instancia DICOM de Orthanc ya procesada por el detector de RX nuevas.

    Sirve de DEDUP (no reexportar la misma instancia) y de AUDITORÍA del export a Drive/Multimedia.
    Se casa el paciente por PatientID == num_historia (convención del centro). Si no hay paciente,
    se registra igual con estado 'sin_paciente' para no reprocesarla en cada vuelta."""
    __tablename__ = "rx_exportada"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    instance_id: str = Field(max_length=80, index=True)   # ID de recurso Orthanc
    sop_uid: Optional[str] = Field(default=None, max_length=120)   # SOPInstanceUID (idempotencia real)
    patient_id_dicom: Optional[str] = Field(default=None, max_length=80)   # PatientID del DICOM
    paciente_id: Optional[int] = Field(default=None, foreign_key="pacientes.id", index=True)
    num_historia: Optional[str] = Field(default=None, max_length=40)
    modalidad: Optional[str] = Field(default=None, max_length=20)
    estado: str = Field(default="pendiente", max_length=20, index=True)  # exportada | sin_paciente | error
    drive_file_id: Optional[str] = Field(default=None, max_length=120)
    detalle: Optional[str] = Field(default=None, max_length=400)
