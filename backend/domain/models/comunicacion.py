"""Comunicación — conversaciones y mensajes con el paciente. FK a nodos-dios.

    centro ──< conversacion >── paciente
    conversacion ──< mensaje
Una conversación agrupa el hilo (WhatsApp/email/tel) de un paciente; cada
mensaje cuelga de ella. Todo apunta al paciente y al centro.
"""
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship, SQLModel

from domain.models._base import TimestampMixin, utcnow


class Recall(TimestampMixin, table=True):
    """Recordatorio / revisión programada del paciente. Origen: Recalls."""
    __tablename__ = "recalls"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    num_rec: Optional[int] = Field(default=None)
    fecha: Optional[date] = Field(default=None, index=True)
    hora: Optional[str] = Field(default=None, max_length=5)
    motivo: Optional[str] = Field(default=None, max_length=120)
    comentario: Optional[str] = Field(default=None, max_length=500)
    telefono: Optional[str] = Field(default=None, max_length=50)
    por_carta: bool = Field(default=False)
    por_email: bool = Field(default=False)
    por_sms: bool = Field(default=False)
    asistido: bool = Field(default=False)
    citado: bool = Field(default=False)
    colaborador_id: Optional[int] = Field(default=None, foreign_key="colaboradores.id", index=True)
    fecha_contacto: Optional[date] = Field(default=None)
    estado: Optional[str] = Field(default=None, max_length=40, index=True)
    resultado: Optional[str] = Field(default=None, max_length=120)
    notas: Optional[str] = Field(default=None, max_length=1000)


class MensajeInterno(TimestampMixin, table=True):
    """Mensaje/nota interna sobre un paciente (entre staff). Origen: PacMensajes."""
    __tablename__ = "mensajes_paciente"
    id: Optional[int] = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="pacientes.id", nullable=False, index=True)
    usuario_de_id: Optional[int] = Field(default=None, foreign_key="usuarios.id", index=True)
    fecha_hora: datetime = Field(default_factory=utcnow, index=True)
    mensaje: str = Field(max_length=2000)
    leido: bool = Field(default=False, index=True)


class EnvioEmail(TimestampMixin, table=True):
    """Tirada de envío masivo de email (Motion). Origen: EdMail."""
    __tablename__ = "envios_email"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    usuario_id: Optional[int] = Field(default=None, foreign_key="usuarios.id", index=True)
    fecha: Optional[datetime] = Field(default=None, index=True)
    filtro: Optional[str] = Field(default=None, max_length=500)
    destinatarios: list["EnvioEmailDestinatario"] = Relationship(back_populates="envio")


class EnvioEmailDestinatario(TimestampMixin, table=True):
    """Destinatario de una tirada de email. Origen: EdMailL."""
    __tablename__ = "envio_email_destinatarios"
    id: Optional[int] = Field(default=None, primary_key=True)
    envio_id: int = Field(foreign_key="envios_email.id", nullable=False, index=True)
    paciente_id: Optional[int] = Field(default=None, foreign_key="pacientes.id", index=True)
    cliente_id: Optional[int] = Field(default=None, foreign_key="clientes.id", index=True)
    envio: EnvioEmail = Relationship(back_populates="destinatarios")


class Conversacion(TimestampMixin, table=True):
    __tablename__ = "conversaciones"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    paciente_id: Optional[int] = Field(default=None, foreign_key="pacientes.id", index=True)
    canal: str = Field(default="whatsapp", index=True)   # whatsapp | email | telefono
    telefono: Optional[str] = Field(default=None, max_length=50)
    estado: str = Field(default="abierta", index=True)   # abierta | pendiente | resuelta
    tags: Optional[str] = Field(default=None, max_length=300)   # urgencia, recall…
    chatwoot_id: Optional[int] = Field(default=None, index=True)
    # bandeja: estado de lectura y último mensaje (para listar sin tocar `mensajes`)
    no_leidos: int = Field(default=0)
    ultimo_mensaje: Optional[str] = Field(default=None, max_length=200)
    ultimo_mensaje_at: Optional[datetime] = Field(default=None, index=True)
    archivada: bool = Field(default=False, index=True)
    fijada: bool = Field(default=False, index=True)   # conversación fijada arriba de la bandeja
    urgente: bool = Field(default=False, index=True)   # marcada a mano por el equipo (no automático)
    ultima_direccion: Optional[str] = Field(default=None, max_length=10)   # entrante | saliente (del último mensaje)
    ia_pausada_hasta: Optional[datetime] = Field(default=None)   # IA en pausa para ESTA conversación hasta esta hora
    mensaje_fijado_id: Optional[int] = Field(default=None)
    # estado del flujo conversacional en curso (máquina de estados WhatsApp); NULL = sin flujo
    estado_flujo: Any = Field(default=None, sa_column=Column(JSON))
    mensajes: list["Mensaje"] = Relationship(back_populates="conversacion")


class Mensaje(TimestampMixin, table=True):
    __tablename__ = "mensajes"
    id: Optional[int] = Field(default=None, primary_key=True)
    conversacion_id: int = Field(foreign_key="conversaciones.id", nullable=False, index=True)
    direccion: str = Field(default="entrante", index=True)     # entrante | saliente
    cuerpo: str = Field(max_length=4000)
    enviado_at: datetime = Field(default_factory=utcnow, index=True)
    # id del proveedor (Evolution) — dedup atómico vía índice UNIQUE parcial
    message_id: Optional[str] = Field(default=None, max_length=160)
    estado: str = Field(default="enviado", index=True)   # pendiente|enviado|entregado|leido|error
    media_url: Optional[str] = Field(default=None, max_length=500)
    media_tipo: Optional[str] = Field(default=None, max_length=40)   # image|video|audio|document
    media_nombre: Optional[str] = Field(default=None, max_length=255)
    responde_a_id: Optional[str] = Field(default=None, max_length=160)
    responde_a_texto: Optional[str] = Field(default=None, max_length=500)
    fijado: bool = Field(default=False)
    # si lo generó la IA y requiere aprobación del doctor
    generado_por_ia: bool = Field(default=False, index=True)
    aprobado: bool = Field(default=True, index=True)
    # editar/borrar (solo mensajes salientes, solo si estado != 'leido' — antes de que el
    # paciente lo vea). El borrado es "para ambos" de verdad vía Evolution, no solo local.
    eliminado: bool = Field(default=False, index=True)
    editado: bool = Field(default=False)
    conversacion: Conversacion = Relationship(back_populates="mensajes")


class PlantillaMensaje(TimestampMixin, table=True):
    """Plantilla editable de mensaje (CONFIG = fuente de la verdad; nada hardcodeado).
    Origen .37: whatsapp_message_templates. tipo: texto | encuesta | lista."""
    __tablename__ = "plantillas_mensaje"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    disparador: Optional[str] = Field(default=None, max_length=60, index=True)  # recordatorio_24h…
    nombre: str = Field(max_length=120)
    cuerpo: str = Field(max_length=4000)   # con variables {{nombre}} {{fecha}} {{hora}}…
    tipo: str = Field(default="texto", max_length=20)
    opciones: Any = Field(default=None, sa_column=Column(JSON))   # [{etiqueta, accion}]
    activo: bool = Field(default=True, index=True)
    updated_by: Optional[int] = Field(default=None, foreign_key="usuarios.id")


class PollContexto(TimestampMixin, table=True):
    """Contexto para resolver el voto de una encuesta de WhatsApp.
    Origen .37: whatsapp_poll_context. Guarda hashes de opción → acción."""
    __tablename__ = "poll_contexto"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    message_id: str = Field(max_length=160, index=True)
    plantilla_id: Optional[int] = Field(default=None, foreign_key="plantillas_mensaje.id", index=True)
    telefono: str = Field(max_length=50)
    opciones: Any = Field(default=None, sa_column=Column(JSON))
    opcion_hashes: Any = Field(default=None, sa_column=Column(JSON))
    opcion_resuelta: Optional[str] = Field(default=None, max_length=200)
    resuelto_at: Optional[datetime] = Field(default=None)


class AgenteRevision(TimestampMixin, table=True):
    """Correcciones/entrenamiento por agente. Dos orígenes posibles (`conversacion_id`
    distingue cuál):
      · Bandeja IA: cola de aprobación de una respuesta real de WhatsApp antes de enviarla
        (con `agente.alex.revision_humana` activo) — conversacion_id/telefono reales.
      · Chat IA: corrección hecha a mano en el chat de entrenamiento de un agente
        (sin conversación real) — conversacion_id NULL.
    En ambos casos, si estado='editada', la corrección alimenta el few-shot futuro DE ESE
    `agente` en concreto (nunca se mezcla entre agentes).
    estado: pendiente | aprobada | editada | descartada."""
    __tablename__ = "agente_revisiones"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    agente: str = Field(default="alex", max_length=40, index=True)
    agente_id: Optional[int] = Field(default=None, foreign_key="agentes.id", index=True)
    conversacion_id: Optional[int] = Field(default=None, foreign_key="conversaciones.id", index=True)
    telefono: Optional[str] = Field(default=None, max_length=50)
    entrada: str = Field(max_length=2000)
    propuesta: str = Field(max_length=2000)
    estado: str = Field(default="pendiente", max_length=20, index=True)
    respuesta_final: Optional[str] = Field(default=None, max_length=2000)
    revisado_por: Optional[int] = Field(default=None, foreign_key="usuarios.id")
    revisado_at: Optional[datetime] = Field(default=None)


class EnvioAutomatico(TimestampMixin, table=True):
    """Log de envíos de automatización (idempotencia). Origen .37: automation_sent_log.
    Un disparador no envía dos veces al mismo objetivo el mismo día."""
    __tablename__ = "envios_automaticos"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    disparador: str = Field(max_length=60)
    clave_objetivo: str = Field(max_length=80)
    canal: str = Field(default="whatsapp", max_length=20)
    fecha_envio: date = Field(index=True)
    paciente_id: Optional[int] = Field(default=None, foreign_key="pacientes.id")


class AccionBoton(TimestampMixin, table=True):
    """Catálogo de acciones de botón/encuesta (qué hace cada opción).
    Origen .37: whatsapp_button_actions."""
    __tablename__ = "acciones_boton"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: Optional[int] = Field(default=None, foreign_key="centros.id", index=True)
    codigo: str = Field(max_length=60)   # confirmar_cita | cancelar_cita | escalar_humano…
    etiqueta: str = Field(max_length=120)
    descripcion: Optional[str] = Field(default=None, max_length=300)
    handler: Optional[str] = Field(default=None, max_length=120)
    activo: bool = Field(default=True, index=True)


class LlamadaVoz(TimestampMixin, table=True):
    """Registro de una llamada/turno de voz atendido por el agente. Origen .37: voicebotCall.
    El canal de voz reutiliza el agente Alex; la config SIP vive en integraciones."""
    __tablename__ = "llamadas_voz"
    id: Optional[int] = Field(default=None, primary_key=True)
    centro_id: int = Field(foreign_key="centros.id", nullable=False, index=True)
    paciente_id: Optional[int] = Field(default=None, foreign_key="pacientes.id", index=True)
    telefono: Optional[str] = Field(default=None, max_length=50)
    entrada: Optional[str] = Field(default=None, max_length=2000)
    respuesta: Optional[str] = Field(default=None, max_length=2000)
    duracion_seg: Optional[int] = Field(default=None)
    estado: str = Field(default="finalizada", max_length=20)   # en_curso | finalizada | fallida
