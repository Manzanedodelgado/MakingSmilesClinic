"""Motion — catálogo de disparadores y búsqueda de candidatos (port completo de la .37).

Cada disparador tiene una función que devuelve los CANDIDATOS a recibir el mensaje:
    [{clave, telefono, paciente_id, vars:{nombre, fecha, hora, clinica}}]
La decisión de enviar (regla activa, dedupe, maestro) vive en AutomatizacionService;
aquí solo se buscan candidatos sobre el esquema nuevo (citas/pacientes/recalls/presupuestos).

Consentimiento RGPD: los disparadores de recaptación/marketing (`solo_consentidos`)
filtran por `pacientes.acepta_whatsapp`; los operativos (recordatorios de SU cita,
no-show, anulación) no lo requieren, igual que en la .37.
"""
from datetime import date, datetime, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlmodel import Session, select

from domain.models.agenda import EstadoCita, TipoCita
from domain.models.comunicacion import Recall
from domain.models.core import Centro, Cita, Paciente
from domain.models.economico import EstadoPresupuesto, Presupuesto

# Estados de cita que NO cuentan como cita activa/pendiente.
ESTADOS_INACTIVOS = ("anulada", "cancelada", "finalizada", "fallada")
ESTADOS_ANULADOS = ("anulada", "cancelada")

# Cuerpos por defecto (siembra / regla recién activada sin plantilla propia).
DEFAULTS: dict[str, str] = {
    "recordatorio_48h": "👋 Hola {{nombre}}, te recordamos tu cita del *{{fecha}} a las {{hora}}h* en {{clinica}}. 🦷",
    "recordatorio_24h": "👋 Hola {{nombre}}, recordamos tu cita *mañana {{fecha}} a las {{hora}}h* en {{clinica}}. 🦷",
    "recordatorio_hoy": "Hola {{nombre}}, te esperamos hoy a las {{hora}}h en {{clinica}}.",
    "recordatorio_2h": "⏰ Tu cita es HOY a las {{hora}}h en {{clinica}}. ¡Te esperamos! 😊",
    "recordatorio_1h": "🦷 Hola {{nombre}}, tu cita en {{clinica}} es en *1 hora ({{hora}}h)*. ¡Nos vemos pronto!",
    "cita_creada": "✅ *Cita confirmada* en {{clinica}}\n\n📅 {{fecha}} a las *{{hora}}h*\n\n¿Necesitas cambiarla? Escríbenos aquí. 😊",
    "cita_confirmada": "✅ *Cita confirmada* en {{clinica}}\n\n📅 {{fecha}} a las *{{hora}}h*\n\n¿Necesitas cambiarla? Escríbenos aquí. 😊",
    "post_visita": "💙 Hola {{nombre}}, ¿cómo te encuentras tras tu visita?\n\nSi tienes alguna molestia o pregunta, escríbenos aquí y te atendemos enseguida. 😊",
    "post_quirurgico": "💙 Hola {{nombre}}, ¿cómo te encuentras tras la intervención de hoy?\n\nRecuerda seguir las indicaciones. Ante cualquier molestia fuerte, escríbenos o llámanos. 🦷",
    "no_show": "😊 Hola {{nombre}}, vemos que hoy no has podido venir a tu cita. ¡No pasa nada!\n\n¿Buscamos otro hueco que te venga mejor? Escríbenos aquí o llámanos. 🦷",
    "anulacion_reprogramar": "Hola {{nombre}}, tu cita del {{fecha}} quedó cancelada. ¿Buscamos un nuevo hueco que te venga bien? Escríbenos aquí y te lo damos al momento. 😊",
    "lista_espera": "📅 Hola {{nombre}}, se nos ha quedado un hueco libre próximamente en {{clinica}}. ¿Quieres que te lo reservemos? Responde *CITA* y es tuyo.",
    "pediatrico_tutor": "👋 Hola, te recordamos la cita de *{{nombre}}* el *{{fecha}} a las {{hora}}h* en {{clinica}}. 🦷",
    "bienvenida": "¡Bienvenido/a a {{clinica}}, {{nombre}}! 😊 Desde este número te enviaremos recordatorios de tus citas. Guárdanos en contactos y escríbenos para lo que necesites.",
    "revision_periodica": "Hola {{nombre}}, hace 6 meses de tu última visita a {{clinica}}. Te recomendamos una revisión 🦷 ¿Te buscamos cita?",
    "recall_pendiente": "Hola {{nombre}}, tienes pendiente una revisión en {{clinica}}. ¿Quieres que te demos cita?",
    "recall_higiene": "✨ Hola {{nombre}}, han pasado más de 6 meses desde tu última limpieza dental.\n\nTus dientes te lo agradecerán 😊 ¿Te buscamos un hueco esta semana?",
    "recall_anual": "👋 Hola {{nombre}}, hace tiempo que no sabemos nada de ti en {{clinica}}.\n\n¿Qué tal si aprovechamos para tu *revisión anual*? 🦷\n\nResponde *CITA* y te buscamos un hueco.",
    "ortho_2m": "😊 Hola {{nombre}}, ¿cómo vas con la retención?\n\nTe preparamos una *revisión rápida* 🦷 ¿Cuándo te viene bien?",
    "ortho_6m": "🦷 Hola {{nombre}}, han pasado 6 meses desde que terminaste tu ortodoncia.\n\n¡Revisemos que tu sonrisa sigue perfecta! ¿Te buscamos cita?",
    "implante_75dias": "🦷 Hola {{nombre}}, toca la revisión de tu implante (osteointegración). Es rápida e importante. ¿Te buscamos cita esta semana?",
    "presupuesto_pendiente": "Hola {{nombre}}, hace unos días te preparamos un presupuesto en {{clinica}}. ¿Tienes alguna duda? Escríbenos y te la resolvemos sin compromiso. 😊",
    "tratamiento_pendiente": "Hola {{nombre}}, tienes un tratamiento aceptado pendiente de empezar en {{clinica}}. ¿Buscamos fecha para la primera cita? 🦷",
    "resena_google": "⭐ Hola {{nombre}}, esperamos que tu visita haya sido perfecta.\n\nSi quedaste satisfecho/a, nos ayudarías *muchísimo* con una reseña en Google (solo 1 minuto) 🙏\n\n¡Gracias de corazón! 😊",
    "encuesta_satisfaccion": "Hola {{nombre}}, ayer nos visitaste en {{clinica}} y nos encantaría saber tu opinión. ¿Cómo valorarías la atención del 1 al 5? 😊",
    "consentimiento_whatsapp": "(Envía automáticamente el consentimiento COEM + enlace de firma al confirmarse una cita que lo requiera. El texto lo compone el sistema con el PDF y el enlace.)",
}

# Disparadores que piden confirmar/cancelar una cita: en vez de pedir escribir SÍ/NO
# (frágil y ambiguo), se mandan como encuesta de WhatsApp — el paciente toca la opción,
# sin depender de botones nativos (deprecados/inestables en conexiones Baileys/QR como
# esta). Reutiliza el mismo pipeline de _ejecutar_accion_poll ya probado con encuestas
# manuales: confirmar_cita/cancelar_cita.
OPCIONES_DEFAULT: dict[str, list[dict]] = {
    disparador: [
        {"etiqueta": "Confirmar", "accion": "confirmar_cita"},
        {"etiqueta": "Cancelar", "accion": "cancelar_cita"},
    ]
    for disparador in (
        "recordatorio_48h", "recordatorio_24h", "recordatorio_hoy",
        "recordatorio_2h", "pediatrico_tutor",
    )
}

# ── Catálogo (fuente única: la API y el frontend lo leen de aquí) ──────────────
# ventana_dias = días que el dedupe considera "ya enviado" (1 = solo el mismo día).
CATALOGO: list[dict] = [
    {"disparador": "recordatorio_48h",     "nombre": "Recordatorio 48h antes de cita",       "grupo": "citas",       "ventana_dias": 3,   "descripcion": "Citas de pasado mañana con móvil."},
    {"disparador": "recordatorio_24h",     "nombre": "Recordatorio 24h antes de cita",       "grupo": "citas",       "ventana_dias": 2,   "descripcion": "Citas de mañana con móvil."},
    {"disparador": "recordatorio_hoy",     "nombre": "Recordatorio el mismo día",            "grupo": "citas",       "ventana_dias": 1,   "descripcion": "Citas de hoy con móvil."},
    {"disparador": "recordatorio_2h",      "nombre": "Recordatorio 2h (no confirmados)",     "grupo": "citas",       "ventana_dias": 1,   "descripcion": "Citas de hoy SIN confirmar que empiezan en ~2 horas."},
    {"disparador": "recordatorio_1h",      "nombre": "Recordatorio 1h antes de cita",        "grupo": "citas",       "ventana_dias": 1,   "descripcion": "Citas de hoy que empiezan en ~1 hora."},
    {"disparador": "cita_creada",          "nombre": "Confirmación al crear cita",           "grupo": "citas",       "ventana_dias": 1,   "descripcion": "Citas dadas de alta en la última hora."},
    {"disparador": "cita_confirmada",      "nombre": "Confirmación de cita",                 "grupo": "citas",       "ventana_dias": 1,   "descripcion": "Citas de hoy confirmadas (acuse al paciente)."},
    {"disparador": "post_visita",          "nombre": "Seguimiento post-visita",              "grupo": "citas",       "ventana_dias": 1,   "descripcion": "Citas de hoy terminadas hace ~2 horas."},
    {"disparador": "post_quirurgico",      "nombre": "Seguimiento post-quirúrgico",          "grupo": "citas",       "ventana_dias": 1,   "descripcion": "Cirugías (implante/injerto/exodoncia) terminadas hace ~4 horas."},
    {"disparador": "no_show",              "nombre": "Gestión no presentado",                "grupo": "citas",       "ventana_dias": 1,   "descripcion": "Citas de hoy confirmadas sin llegada 30 min después de la hora."},
    {"disparador": "anulacion_reprogramar", "nombre": "Cita cancelada — reprogramar",        "grupo": "citas",       "ventana_dias": 7,   "descripcion": "Citas futuras anuladas/canceladas sin gestionar: ofrece nuevo hueco."},
    {"disparador": "lista_espera",         "nombre": "Lista de espera — hueco disponible",   "grupo": "citas",       "ventana_dias": 7,   "descripcion": "Al cancelarse una cita de hoy/mañana avisa a pacientes con recall pendiente."},
    {"disparador": "pediatrico_tutor",     "nombre": "Recordatorio pediátrico al tutor (48h)", "grupo": "citas",     "ventana_dias": 3,   "descripcion": "Citas de menores de 14 años: el aviso va al tutor."},
    {"disparador": "consentimiento_whatsapp", "nombre": "Consentimiento digital al confirmar", "grupo": "citas",    "ventana_dias": 1,   "descripcion": "Cita confirmada cuyo tipo requiere consentimiento COEM: envía PDF + enlace de firma."},
    {"disparador": "bienvenida",           "nombre": "Bienvenida a paciente nuevo",          "grupo": "pacientes",   "ventana_dias": 30,  "descripcion": "Pacientes dados de alta en la última hora."},
    {"disparador": "revision_periodica",   "nombre": "Revisión periódica (6 meses)",         "grupo": "recaptacion", "ventana_dias": 60,  "descripcion": "Última visita hace 6-7 meses y sin cita futura. Solo con consentimiento.", "solo_consentidos": True},
    {"disparador": "recall_pendiente",     "nombre": "Recall — revisión programada",         "grupo": "recaptacion", "ventana_dias": 7,   "descripcion": "Recalls programados vencidos sin citar."},
    {"disparador": "recall_higiene",       "nombre": "Recall higiene dental (6 meses)",      "grupo": "recaptacion", "ventana_dias": 60,  "descripcion": "Higiene hace 6-7 meses sin visita posterior. Solo con consentimiento.", "solo_consentidos": True},
    {"disparador": "recall_anual",         "nombre": "Recaptación inactivos (+12 meses)",    "grupo": "recaptacion", "ventana_dias": 365, "descripcion": "Pacientes sin visita en más de un año. Solo con consentimiento.", "solo_consentidos": True},
    {"disparador": "ortho_2m",             "nombre": "Revisión ortodoncia (2 meses)",        "grupo": "clinico",     "ventana_dias": 30,  "descripcion": "Ortodoncia retirada hace ~60 días sin visita posterior. Solo con consentimiento.", "solo_consentidos": True},
    {"disparador": "ortho_6m",             "nombre": "Revisión ortodoncia (6 meses)",        "grupo": "clinico",     "ventana_dias": 30,  "descripcion": "Ortodoncia retirada hace ~180 días sin visita posterior. Solo con consentimiento.", "solo_consentidos": True},
    {"disparador": "implante_75dias",      "nombre": "Revisión implante (75 días)",          "grupo": "clinico",     "ventana_dias": 30,  "descripcion": "Cirugía de implante hace ~75 días sin revisión posterior. Solo con consentimiento.", "solo_consentidos": True},
    {"disparador": "presupuesto_pendiente", "nombre": "Presupuesto pendiente (3 días)",      "grupo": "economico",   "ventana_dias": 7,   "descripcion": "Presupuestos entregados hace 3 días sin aceptar."},
    {"disparador": "tratamiento_pendiente", "nombre": "Tratamiento sin iniciar (7 días)",    "grupo": "economico",   "ventana_dias": 14,  "descripcion": "Tratamientos aceptados hace 7 días sin fecha de inicio."},
    {"disparador": "resena_google",        "nombre": "Solicitud de reseña Google",           "grupo": "pacientes",   "ventana_dias": 180, "descripcion": "Visita finalizada ayer: pide reseña. Solo con consentimiento.", "solo_consentidos": True},
    {"disparador": "encuesta_satisfaccion", "nombre": "Encuesta de satisfacción",            "grupo": "pacientes",   "ventana_dias": 90,  "descripcion": "Visita de ayer con llegada registrada: encuesta 1-5."},
]

CATALOGO_IDX = {c["disparador"]: c for c in CATALOGO}

# Límite de mensajes por disparador y pasada (protección anti-tirada masiva, como la .37).
MAX_LOTE = {"revision_periodica": 20, "recall_pendiente": 30, "recall_higiene": 30,
            "recall_anual": 50, "ortho_2m": 50, "ortho_6m": 50, "implante_75dias": 20,
            "presupuesto_pendiente": 20, "tratamiento_pendiente": 20, "resena_google": 20,
            "encuesta_satisfaccion": 30, "lista_espera": 5}


# El contenedor corre en UTC pero `citas.hora` es hora LOCAL de la clínica y el cron
# del scheduler usa Europe/Madrid. Comparar contra datetime.now() (UTC) desplazaba las
# ventanas de recordatorio_1h/2h, post_visita, post_quirurgico y no_show 2 horas.
TZ_CLINICA = ZoneInfo("Europe/Madrid")


def ahora_clinica() -> datetime:
    """Hora local de la clínica, naive (comparable con las cadenas 'HH:MM' de las citas)."""
    return datetime.now(TZ_CLINICA).replace(tzinfo=None)


def fecha_es(d: Optional[date]) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def _hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


class Candidatos:
    """Consultas de candidatos por disparador. Estado compartido: sesión + centro + ahora."""

    def __init__(self, session: Session, centro_id: int, ahora: Optional[datetime] = None,
                 paciente_id: Optional[int] = None):
        self.session = session
        self.centro_id = centro_id
        # Solo Inicio lo usa (lo pendiente de UN paciente). El scheduler no lo pasa: sin él
        # las consultas recorren todo el centro, exactamente como antes.
        self.paciente_id = paciente_id
        self.ahora = ahora or ahora_clinica()
        c = session.get(Centro, centro_id)
        self.clinica = c.nombre if c else ""

    # ─────────────────────── helpers ───────────────────────
    def _estado_ids(self, codigos: tuple[str, ...]) -> list[int]:
        return list(self.session.exec(select(EstadoCita.id).where(
            EstadoCita.centro_id == self.centro_id,
            EstadoCita.codigo.in_(codigos))).all())  # type: ignore[union-attr]

    def _citas_de(self, dia: date, *extra) -> list[Cita]:
        excl = self._estado_ids(ESTADOS_INACTIVOS)
        q = select(Cita).where(Cita.centro_id == self.centro_id, Cita.fecha == dia, *extra)
        if excl:
            q = q.where((Cita.estado_id.is_(None)) | (Cita.estado_id.not_in(excl)))  # type: ignore[union-attr]
        return list(self.session.exec(q).all())

    def _telefono(self, cita: Cita) -> Optional[str]:
        pac = self.session.get(Paciente, cita.paciente_id) if cita.paciente_id else None
        return (pac.telefono_movil if pac else None) or cita.telefono_movil

    def _cand_cita(self, cita: Cita, telefono: Optional[str] = None,
                   nombre: Optional[str] = None) -> Optional[dict]:
        telf = telefono or self._telefono(cita)
        if not telf:
            return None
        pac = self.session.get(Paciente, cita.paciente_id) if cita.paciente_id else None
        return {"clave": f"cita:{cita.id}", "telefono": telf, "paciente_id": cita.paciente_id,
                "vars": {"nombre": nombre or (pac.nombre if pac else None) or cita.nombre or "",
                         "fecha": fecha_es(cita.fecha), "hora": cita.hora or "",
                         "clinica": self.clinica}}

    def _cand_paciente(self, pac: Paciente, clave: str, telefono: Optional[str] = None) -> Optional[dict]:
        telf = telefono or pac.telefono_movil
        if not telf:
            return None
        return {"clave": clave, "telefono": telf, "paciente_id": pac.id,
                "vars": {"nombre": pac.nombre or "", "fecha": "", "hora": "", "clinica": self.clinica}}

    def _pacientes_por_tipo_cita(self, patrones: list[str], dias: int, rango: int,
                                 sin_visita_desde: bool = True) -> list[dict]:
        """Pacientes con cita FINALIZADA de un tipo (ILIKE sobre tipos_cita.nombre) hace
        `dias`±`rango` días y sin visita posterior. Para ortho/higiene/implante."""
        desde = self.ahora.date() - timedelta(days=dias + rango)
        hasta = self.ahora.date() - timedelta(days=dias - rango)
        fin = self._estado_ids(("finalizada",))
        if not fin:
            return []
        tipos = [t.id for t in self.session.exec(select(TipoCita)).all()
                 if t.nombre and any(p in t.nombre.strip().lower() for p in patrones)]
        if not tipos:
            return []
        citas = self.session.exec(select(Cita).where(
            Cita.centro_id == self.centro_id,
            Cita.fecha >= desde, Cita.fecha <= hasta,
            Cita.estado_id.in_(fin),                    # type: ignore[union-attr]
            Cita.tipo_cita_id.in_(tipos),               # type: ignore[union-attr]
            Cita.paciente_id.isnot(None))).all()        # type: ignore[union-attr]
        out, vistos = [], set()
        excl = self._estado_ids(ESTADOS_ANULADOS)
        for c in citas:
            if c.paciente_id in vistos:
                continue
            vistos.add(c.paciente_id)
            if sin_visita_desde:
                q = select(Cita.id).where(
                    Cita.centro_id == self.centro_id, Cita.paciente_id == c.paciente_id,
                    Cita.fecha > hasta)
                if excl:
                    q = q.where((Cita.estado_id.is_(None)) | (Cita.estado_id.not_in(excl)))  # type: ignore[union-attr]
                if self.session.exec(q.limit(1)).first():
                    continue
            pac = self.session.get(Paciente, c.paciente_id)
            if not pac or not pac.activo or not pac.acepta_whatsapp:
                continue
            cand = self._cand_paciente(pac, f"paciente:{pac.id}")
            if cand:
                out.append(cand)
        return out

    # ─────────────────────── citas: recordatorios ───────────────────────
    def recordatorio_48h(self) -> list[dict]:
        dia = self.ahora.date() + timedelta(days=2)
        return [c for c in (self._cand_cita(x) for x in self._citas_de(dia)) if c]

    def recordatorio_24h(self) -> list[dict]:
        dia = self.ahora.date() + timedelta(days=1)
        return [c for c in (self._cand_cita(x) for x in self._citas_de(dia)) if c]

    def recordatorio_hoy(self) -> list[dict]:
        return [c for c in (self._cand_cita(x) for x in self._citas_de(self.ahora.date())) if c]

    def _citas_hoy_en_ventana(self, min_desde: int, min_hasta: int, *extra) -> list[Cita]:
        d, h = _hhmm(self.ahora + timedelta(minutes=min_desde)), _hhmm(self.ahora + timedelta(minutes=min_hasta))
        return [x for x in self._citas_de(self.ahora.date(), *extra) if x.hora and d <= x.hora <= h]

    def recordatorio_2h(self) -> list[dict]:
        citas = self._citas_hoy_en_ventana(115, 125, Cita.confirmada == False)  # noqa: E712
        return [c for c in (self._cand_cita(x) for x in citas) if c]

    def recordatorio_1h(self) -> list[dict]:
        citas = self._citas_hoy_en_ventana(55, 65)
        return [c for c in (self._cand_cita(x) for x in citas) if c]

    # ─────────────────────── citas: ciclo de vida ───────────────────────
    def cita_creada(self) -> list[dict]:
        hace_1h = datetime.utcnow() - timedelta(hours=1)   # created_at se guarda en UTC
        excl = self._estado_ids(ESTADOS_INACTIVOS)
        q = select(Cita).where(Cita.centro_id == self.centro_id,
                               Cita.created_at >= hace_1h,           # type: ignore[attr-defined]
                               Cita.fecha >= self.ahora.date())
        if excl:
            q = q.where((Cita.estado_id.is_(None)) | (Cita.estado_id.not_in(excl)))  # type: ignore[union-attr]
        return [c for c in (self._cand_cita(x) for x in self.session.exec(q).all()) if c]

    def cita_confirmada(self) -> list[dict]:
        citas = self._citas_de(self.ahora.date(), Cita.confirmada == True)  # noqa: E712
        return [c for c in (self._cand_cita(x) for x in citas) if c]

    def _citas_hoy_terminadas_hace(self, min_desde: int, min_hasta: int,
                                   tipos_patron: Optional[list[str]] = None) -> list[Cita]:
        """Citas de hoy cuyo fin (hora + duración, default 60 min) cayó hace [min_hasta, min_desde] min."""
        out = []
        tipos = None
        if tipos_patron is not None:
            tipos = {t.id for t in self.session.exec(select(TipoCita)).all()
                     if t.nombre and any(p in t.nombre.strip().lower() for p in tipos_patron)}
        for x in self._citas_de(self.ahora.date()):
            if not x.hora:
                continue
            if tipos is not None and x.tipo_cita_id not in tipos:
                continue
            try:
                hh, mm = map(int, x.hora.split(":"))
            except ValueError:
                continue
            fin = self.ahora.replace(hour=hh, minute=mm, second=0, microsecond=0) \
                + timedelta(minutes=x.duracion_min or 60)
            transcurrido = (self.ahora - fin).total_seconds() / 60
            if min_hasta <= transcurrido <= min_desde:
                out.append(x)
        return out

    def post_visita(self) -> list[dict]:
        citas = self._citas_hoy_terminadas_hace(125, 115)
        return [c for c in (self._cand_cita(x) for x in citas) if c]

    def post_quirurgico(self) -> list[dict]:
        citas = self._citas_hoy_terminadas_hace(245, 235, ["implante", "injerto", "cirugia", "exodoncia"])
        return [c for c in (self._cand_cita(x) for x in citas) if c]

    def no_show(self) -> list[dict]:
        limite = _hhmm(self.ahora - timedelta(minutes=30))
        activos = self._estado_ids(("planificada", "confirmada"))
        citas = [x for x in self._citas_de(self.ahora.date(),
                                           Cita.confirmada == True,               # noqa: E712
                                           Cita.hora_llegada.is_(None))           # type: ignore[union-attr]
                 if x.hora and x.hora <= limite and (x.estado_id is None or x.estado_id in activos)]
        return [c for c in (self._cand_cita(x) for x in citas) if c]

    def anulacion_reprogramar(self) -> list[dict]:
        anulados = self._estado_ids(ESTADOS_ANULADOS)
        if not anulados:
            return []
        citas = self.session.exec(select(Cita).where(
            Cita.centro_id == self.centro_id, Cita.fecha >= self.ahora.date(),
            Cita.estado_id.in_(anulados),                    # type: ignore[union-attr]
            Cita.anulacion_gestionada == False,              # noqa: E712
        ).limit(20)).all()
        out = []
        for x in citas:
            cand = self._cand_cita(x)
            if cand:
                cand["marcar_gestionada_cita_id"] = x.id   # tras enviar: anulacion_gestionada=True
                out.append(cand)
        return out

    def lista_espera(self) -> list[dict]:
        anulados = self._estado_ids(ESTADOS_ANULADOS)
        if not anulados:
            return []
        hace_1h = datetime.utcnow() - timedelta(hours=1)   # fecha_hora_estado se guarda en UTC
        hueco = self.session.exec(select(Cita.id).where(
            Cita.centro_id == self.centro_id,
            Cita.fecha >= self.ahora.date(),
            Cita.fecha <= self.ahora.date() + timedelta(days=1),
            Cita.estado_id.in_(anulados),                    # type: ignore[union-attr]
            Cita.fecha_hora_estado >= hace_1h).limit(1)).first()
        if not hueco:
            return []
        recalls = self.session.exec(select(Recall).where(
            Recall.centro_id == self.centro_id, Recall.citado == False,  # noqa: E712
            Recall.asistido == False).limit(5)).all()                    # noqa: E712
        out = []
        for r in recalls:
            pac = self.session.get(Paciente, r.paciente_id) if r.paciente_id else None
            if not pac:
                continue
            cand = self._cand_paciente(pac, f"paciente:{pac.id}", telefono=r.telefono or pac.telefono_movil)
            if cand:
                out.append(cand)
        return out

    def pediatrico_tutor(self) -> list[dict]:
        dia = self.ahora.date() + timedelta(days=2)
        limite_nacimiento = date(self.ahora.year - 14, self.ahora.month, self.ahora.day)
        out = []
        for x in self._citas_de(dia):
            pac = self.session.get(Paciente, x.paciente_id) if x.paciente_id else None
            fnac = (pac.fecha_nacimiento if pac else None) or x.fecha_nacimiento
            if not fnac or fnac <= limite_nacimiento:
                continue   # no es menor de 14
            # Teléfono del tutor: cita.tutor → paciente.tutor → el móvil de la ficha del menor.
            tutor = self.session.get(Paciente, x.tutor_id) if x.tutor_id else None
            if not tutor and pac and pac.tutor_id:
                tutor = self.session.get(Paciente, pac.tutor_id)
            telf = (tutor.telefono_movil if tutor else None) or (pac.telefono_movil if pac else None) or x.telefono_movil
            cand = self._cand_cita(x, telefono=telf, nombre=(pac.nombre if pac else None) or x.nombre or "")
            if cand:
                out.append(cand)
        return out

    def consentimiento_whatsapp(self) -> list[dict]:
        """Citas futuras confirmadas sin doc enviado cuyo tipo requiere consentimiento COEM.
        El envío real (PDF + enlace de firma) lo hace ComunicacionService; aquí solo candidatos."""
        from application.services import consentimiento_service as consvc
        excl = self._estado_ids(ESTADOS_INACTIVOS)
        q = select(Cita).where(
            Cita.centro_id == self.centro_id, Cita.fecha >= self.ahora.date(),
            Cita.confirmada == True,                          # noqa: E712
            Cita.envio_doc == False,                          # noqa: E712
            Cita.paciente_id.isnot(None))                     # type: ignore[union-attr]
        if excl:
            q = q.where((Cita.estado_id.is_(None)) | (Cita.estado_id.not_in(excl)))  # type: ignore[union-attr]
        out = []
        for x in self.session.exec(q.limit(20)).all():
            if not consvc.consent_key_para_cita(self.session, x):
                continue
            cand = self._cand_cita(x)
            if cand:
                cand["consentimiento_cita_id"] = x.id   # AutomatizacionService lo despacha aparte
                out.append(cand)
        return out

    # ─────────────────────── pacientes ───────────────────────
    def bienvenida(self) -> list[dict]:
        hace_1h = datetime.utcnow() - timedelta(hours=1)
        pacs = self.session.exec(select(Paciente).where(
            Paciente.centro_id == self.centro_id, Paciente.activo == True,   # noqa: E712
            Paciente.created_at >= hace_1h)).all()                           # type: ignore[attr-defined]
        return [c for c in (self._cand_paciente(p, f"paciente:{p.id}") for p in pacs) if c]

    # NOTA: el disparador `cumpleanos` está INHABILITADO por decisión del usuario
    # (10-jul-2026): felicitar es marketing y no filtraba por `acepta_whatsapp`.
    # Se retiró del catálogo, no solo se apagó: no se puede encender desde la UI.

    def resena_google(self) -> list[dict]:
        ayer = self.ahora.date() - timedelta(days=1)
        fin = self._estado_ids(("finalizada",))
        citas = self.session.exec(select(Cita).where(
            Cita.centro_id == self.centro_id, Cita.fecha == ayer,
            Cita.hora_llegada.isnot(None),                    # type: ignore[union-attr]
            Cita.estado_id.in_(fin) if fin else True,         # type: ignore[union-attr]
            Cita.paciente_id.isnot(None)).limit(20)).all()    # type: ignore[union-attr]
        out = []
        for x in citas:
            pac = self.session.get(Paciente, x.paciente_id)
            if not pac or not pac.acepta_whatsapp:
                continue
            cand = self._cand_cita(x)
            if cand:
                out.append(cand)
        return out

    def encuesta_satisfaccion(self) -> list[dict]:
        ayer = self.ahora.date() - timedelta(days=1)
        excl = self._estado_ids(ESTADOS_ANULADOS)
        q = select(Cita).where(Cita.centro_id == self.centro_id, Cita.fecha == ayer,
                               Cita.hora_llegada.isnot(None))                 # type: ignore[union-attr]
        if excl:
            q = q.where((Cita.estado_id.is_(None)) | (Cita.estado_id.not_in(excl)))  # type: ignore[union-attr]
        return [c for c in (self._cand_cita(x) for x in self.session.exec(q.limit(30)).all()) if c]

    # ─────────────────────── recaptación / clínico ───────────────────────
    def _sin_cita_futura(self, paciente_id: int) -> bool:
        excl = self._estado_ids(ESTADOS_ANULADOS)
        q = select(Cita.id).where(Cita.centro_id == self.centro_id,
                                  Cita.paciente_id == paciente_id,
                                  Cita.fecha >= self.ahora.date())
        if excl:
            q = q.where((Cita.estado_id.is_(None)) | (Cita.estado_id.not_in(excl)))  # type: ignore[union-attr]
        return self.session.exec(q.limit(1)).first() is None

    def _ultima_visita_entre(self, desde_dias: int, hasta_dias: int) -> list[dict]:
        """Pacientes cuya ÚLTIMA cita finalizada cayó hace [hasta_dias, desde_dias] días."""
        fin = self._estado_ids(("finalizada",))
        if not fin:
            return []
        rows = self.session.execute(text("""
            SELECT c.paciente_id, MAX(c.fecha) AS ult
            FROM citas c
            WHERE c.centro_id = :cid AND c.paciente_id IS NOT NULL
              AND c.estado_id = ANY(:fin)
              AND (CAST(:pid AS INTEGER) IS NULL OR c.paciente_id = :pid)
            GROUP BY c.paciente_id
            HAVING MAX(c.fecha) BETWEEN :desde AND :hasta
        """), {"cid": self.centro_id, "fin": fin, "pid": self.paciente_id,
               "desde": self.ahora.date() - timedelta(days=desde_dias),
               "hasta": self.ahora.date() - timedelta(days=hasta_dias)}).all()
        out = []
        for paciente_id, _ult in rows:
            pac = self.session.get(Paciente, paciente_id)
            if not pac or not pac.activo or not pac.acepta_whatsapp:
                continue
            if not self._sin_cita_futura(paciente_id):
                continue
            cand = self._cand_paciente(pac, f"paciente:{pac.id}")
            if cand:
                out.append(cand)
        return out

    def revision_periodica(self) -> list[dict]:
        return self._ultima_visita_entre(210, 180)

    def recall_anual(self) -> list[dict]:
        return self._ultima_visita_entre(3650, 365)

    def recall_pendiente(self) -> list[dict]:
        hoy = self.ahora.date()
        recalls = self.session.exec(select(Recall).where(
            Recall.centro_id == self.centro_id, Recall.citado == False,  # noqa: E712
            Recall.asistido == False,                                    # noqa: E712
            Recall.fecha.isnot(None), Recall.fecha <= hoy)).all()        # type: ignore[union-attr]
        out = []
        for r in recalls:
            pac = self.session.get(Paciente, r.paciente_id) if r.paciente_id else None
            telf = r.telefono or (pac.telefono_movil if pac else None)
            if not telf:
                continue
            out.append({"clave": f"recall:{r.id}", "telefono": telf, "paciente_id": r.paciente_id,
                        "vars": {"nombre": (pac.nombre if pac else None) or "", "fecha": "",
                                 "hora": "", "clinica": self.clinica}})
        return out

    def recall_higiene(self) -> list[dict]:
        return self._pacientes_por_tipo_cita(["higiene"], dias=195, rango=15)

    def ortho_2m(self) -> list[dict]:
        return self._pacientes_por_tipo_cita(["retirar ortodoncia"], dias=60, rango=3)

    def ortho_6m(self) -> list[dict]:
        return self._pacientes_por_tipo_cita(["retirar ortodoncia"], dias=180, rango=3)

    def implante_75dias(self) -> list[dict]:
        return self._pacientes_por_tipo_cita(["implante", "injerto"], dias=75, rango=2)

    # ─────────────────────── económico ───────────────────────
    def presupuesto_pendiente(self) -> list[dict]:
        pendientes = [e.id for e in self.session.exec(select(EstadoPresupuesto).where(
            EstadoPresupuesto.codigo.in_(("nuevo", "entregado")))).all()]    # type: ignore[union-attr]
        if not pendientes:
            return []
        presus = self.session.exec(select(Presupuesto).where(
            Presupuesto.centro_id == self.centro_id,
            Presupuesto.fecha >= self.ahora.date() - timedelta(days=4),
            Presupuesto.fecha < self.ahora.date() - timedelta(days=2),
            Presupuesto.estado_id.in_(pendientes)).limit(20)).all()          # type: ignore[union-attr]
        out, vistos = [], set()
        for p in presus:
            if p.paciente_id in vistos:
                continue
            vistos.add(p.paciente_id)
            pac = self.session.get(Paciente, p.paciente_id)
            if not pac or not pac.activo:
                continue
            cand = self._cand_paciente(pac, f"presupuesto:{p.id}")
            if cand:
                out.append(cand)
        return out

    def tratamiento_pendiente(self) -> list[dict]:
        # tratamientos_previstos no tiene modelo SQLModel (tabla operativa) → SQL directo.
        rows = self.session.execute(text("""
            SELECT DISTINCT ON (t.paciente_id) t.id, t.paciente_id
            FROM tratamientos_previstos t
            WHERE t.centro_id = :cid AND t.fecha_inicio IS NULL
              AND t.created_at >= :desde AND t.created_at < :hasta
            ORDER BY t.paciente_id, t.id
            LIMIT 20
        """), {"cid": self.centro_id,
               "desde": datetime.utcnow() - timedelta(days=8),
               "hasta": datetime.utcnow() - timedelta(days=7)}).all()
        out = []
        for _tid, paciente_id in rows:
            pac = self.session.get(Paciente, paciente_id)
            if not pac or not pac.activo:
                continue
            cand = self._cand_paciente(pac, f"paciente:{pac.id}")
            if cand:
                out.append(cand)
        return out


# Registro disparador → método de Candidatos (validado contra el catálogo al importar).
TRIGGERS: dict[str, Callable[[Candidatos], list[dict]]] = {
    c["disparador"]: getattr(Candidatos, c["disparador"]) for c in CATALOGO
}
