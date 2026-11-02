"""Generación de consentimientos COEM (reutilizable por el endpoint manual y la
automatización de WhatsApp al confirmar cita). Estampa el PDF COEM y crea la fila
`consentimientos`. NO envía por WhatsApp (eso lo hace ComunicacionService para evitar
dependencias circulares)."""
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from application.services.consentimiento_pdf import (
    fecha_partes, firma_desde_datauri, incrustar_firma, rellenar_consentimiento,
)
from domain.models.agenda import TipoCita
from domain.models.core import Centro, Cita, Colaborador, Paciente, RazonSocial, Tratamiento
from domain.models.documentos import Consentimiento
from domain.models.identidad import Usuario, UsuarioPeriodo

_BASE = Path(__file__).resolve().parents[2]                       # backend/ (=/app en el contenedor)
PLANTILLAS_DIR = _BASE / "assets" / "consentimientos"
OUT_DIR = _BASE / "media" / "consentimientos"

# Catálogo COEM: key → (etiqueta, fichero PDF).
PLANTILLAS: dict[str, tuple[str, str]] = {
    "implante":           ("Implante dental",    "COEMconsentimientoImplante.pdf"),
    "extraccion":         ("Extracción",         "COEMconsentimientoExtraccion.pdf"),
    "obturacion":         ("Obturación",         "COEMconsentimientoObturacion.pdf"),
    "ortodoncia":         ("Ortodoncia",         "COEMconsentimientoOrtod.pdf"),
    "periodoncia":        ("Periodoncia",        "COEMconsentimientoPeriod.pdf"),
    "protesis_fija":      ("Prótesis fija",      "COEMconsentimientoProtesisFija.pdf"),
    "protesis_removible": ("Prótesis removible", "COEMconsentimientoProtesisRemovible.pdf"),
    "blanqueamiento":     ("Blanqueamiento",     "COEMconsentimientoBlanqueamiento.pdf"),
    "odontopediatria":    ("Odontopediatría",    "COEMconsentimientoOdontoped.pdf"),
}


def _leer_firma_colaborador(url: Optional[str]) -> Optional[bytes]:
    """Bytes de la firma del colaborador (subida en Config → Colaboradores, /media/*).
    Solo raster (png/jpg/jpeg/webp): un SVG no se puede estampar como imagen en el PDF."""
    if not url:
        return None
    nombre = url.rsplit("/", 1)[-1]
    if nombre.lower().rsplit(".", 1)[-1] not in {"png", "jpg", "jpeg", "webp"}:
        return None
    f = _BASE / "media" / nombre
    return f.read_bytes() if f.exists() else None

# Mapa tipo de cita (nombre normalizado, minúsculas) → consentimiento a enviar al confirmar.
# Portado de la .37 (automation.engine consentFromIdIcono). Solo actos que requieren consentimiento;
# el resto (control, urgencia, mensualidad orto, ajuste, primera visita, higiene, rx…) no dispara.
TIPO_CITA_CONSENT: dict[str, str] = {
    "cirugia de implante": "implante",
    "exodoncia": "extraccion",
    "protesis fija": "protesis_fija",
    "protesis removible": "protesis_removible",
    "colocacion ortodoncia": "ortodoncia",
    "estudio ortodoncia": "ortodoncia",
    "retirar ortodoncia": "ortodoncia",
    "periodoncia": "periodoncia",
    "cirugia/injerto": "periodoncia",
    "reconstruccion": "obturacion",
    "endodoncia": "obturacion",
}


def consent_key_para_cita(session: Session, cita: Cita) -> Optional[str]:
    """Devuelve la key de consentimiento para el tipo de esa cita, o None si no aplica."""
    if not cita or not cita.tipo_cita_id:
        return None
    tc = session.get(TipoCita, cita.tipo_cita_id)
    if not tc or not tc.nombre:
        return None
    return TIPO_CITA_CONSENT.get(tc.nombre.strip().lower())


def generar(session: Session, centro_id: int, paciente_id: int, plantilla_key: str,
            colaborador_id: Optional[int] = None) -> Consentimiento:
    """Rellena el PDF COEM, lo guarda en media y crea la fila consentimientos (pendiente)."""
    if plantilla_key not in PLANTILLAS:
        raise ValueError(f"Plantilla desconocida: {plantilla_key}")
    label, fichero = PLANTILLAS[plantilla_key]
    tpl = PLANTILLAS_DIR / fichero
    if not tpl.exists():
        raise FileNotFoundError(f"Plantilla PDF no encontrada: {fichero}")
    pac = session.get(Paciente, paciente_id)
    centro = session.get(Centro, centro_id)
    doctor, colegiado, firma_prof = "", "", None
    if colaborador_id:
        # El nombre del profesional sale de SU usuario (colaborador → periodo → usuario).
        # Antes se hacía session.get(Usuario, colaborador_id) suponiendo ids iguales, y el
        # consentimiento salía a nombre de OTRA persona (colaborador 15 → usuario 15 ≠ el doctor).
        col = session.get(Colaborador, colaborador_id)
        per = session.get(UsuarioPeriodo, col.periodo_id) if col and col.periodo_id else None
        usu = session.get(Usuario, per.usuario_id) if per else None
        if usu:
            doctor = f"{usu.nombre or ''} {usu.apellidos or ''}".strip()
        if col:
            colegiado = col.num_colegiado or ""
            firma_prof = _leer_firma_colaborador(col.firma_url)   # firma subida en Config → Colaboradores
    # Sin firma del colaborador → sello del centro (de momento).
    if firma_prof is None:
        razon = session.exec(select(RazonSocial).where(RazonSocial.centro_id == centro_id)).first()
        if razon and razon.sello_url:
            firma_prof = _leer_firma_colaborador(razon.sello_url)
    dia, mes, anio = fecha_partes(date.today())
    pdf = rellenar_consentimiento(
        str(tpl),
        clinica=(centro.nombre if centro else "") or "",
        doctor=doctor, colegiado=colegiado,
        paciente=f"{pac.nombre or ''} {pac.apellidos or ''}".strip() if pac else "",
        dni=(pac.nif if pac else "") or "",
        ciudad=(centro.poblacion if centro else "") or "",
        dia=dia, mes=mes, anio=anio,
        firma_profesional_png=firma_prof,
    )
    c = Consentimiento(centro_id=centro_id, paciente_id=paciente_id, tipo=label, estado="pendiente")
    session.add(c)
    session.commit()
    session.refresh(c)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"consent_{c.id}.pdf").write_bytes(pdf)
    c.archivo_url = f"/media/consentimientos/consent_{c.id}.pdf"
    c.signing_code = secrets.token_urlsafe(16)     # enlace público de firma (WhatsApp), 128 bits
    c.signing_code_expira = datetime.utcnow() + timedelta(days=30)
    session.add(c)
    session.commit()
    return c


def firma_profesional(session: Session, centro_id: int, colaborador_id: Optional[int]) -> Optional[str]:
    """Qué firma profesional lleva el consentimiento: 'doctor' (la de su perfil), 'sello' (de la
    clínica, cuando el doctor no tiene firma) o None (ninguna). Misma regla que generar()."""
    col = session.get(Colaborador, colaborador_id) if colaborador_id else None
    if col and _leer_firma_colaborador(col.firma_url) is not None:
        return "doctor"
    razon = session.exec(select(RazonSocial).where(RazonSocial.centro_id == centro_id)).first()
    if razon and _leer_firma_colaborador(razon.sello_url) is not None:
        return "sello"
    return None


def requerido_para_cita(session: Session, cita: Cita) -> Optional[dict]:
    """Consentimiento que pide el tipo de la cita y si el paciente ya tiene uno FIRMADO vigente
    (3 meses, misma regla que vigente_para_tratamiento). None si el tipo no lo requiere."""
    key = consent_key_para_cita(session, cita)
    if not key or not cita.paciente_id:
        return None
    label = PLANTILLAS[key][0]
    limite = datetime.utcnow() - timedelta(days=90)
    vigente = session.exec(select(Consentimiento).where(
        Consentimiento.paciente_id == cita.paciente_id, Consentimiento.tipo == label,
        Consentimiento.estado == "firmado", Consentimiento.updated_at >= limite)).first()
    return {"key": key, "label": label, "vigente": vigente is not None}


def info_por_codigo(session: Session, code: str) -> Optional[Consentimiento]:
    if not code:
        return None
    return session.exec(select(Consentimiento).where(Consentimiento.signing_code == code)).first()


def expirado(c: Consentimiento) -> bool:
    """Caducidad del enlace público: solo aplica mientras el consentimiento esté
    'pendiente' de firmar. Uno ya 'firmado' sigue sirviendo en modo lectura (el paciente
    puede reabrir su enlace y ver la confirmación) sin límite de tiempo."""
    return (c.estado != "firmado" and c.signing_code_expira is not None
            and datetime.utcnow() > c.signing_code_expira)


def ya_firmado(session: Session, paciente_id: int, tipo_label: str) -> bool:
    """True si el paciente ya tiene un consentimiento FIRMADO de ese tipo (evita reenviar)."""
    return session.exec(select(Consentimiento).where(
        Consentimiento.paciente_id == paciente_id,
        Consentimiento.tipo == tipo_label,
        Consentimiento.estado == "firmado",
    )).first() is not None


def vigente_para_tratamiento(session: Session, paciente_id: int, tratamiento_id: int) -> bool:
    """True si el tratamiento no requiere consentimiento, o si existe uno FIRMADO
    hace <= 3 meses del tipo que requiere. Camino 1 (realizar-en-cita) lo usa para validar."""
    tto = session.get(Tratamiento, tratamiento_id)
    if not tto or not tto.consentimiento_tipo:
        return True  # No requiere consentimiento

    # Resolver label: consentimiento_tipo es la key (implante, endodoncia, etc.)
    # pero Consentimiento.tipo almacena el label (Implante dental, Endodoncia, etc.)
    if tto.consentimiento_tipo not in PLANTILLAS:
        return True  # Key desconocida, permiso por seguridad

    label = PLANTILLAS[tto.consentimiento_tipo][0]  # Etiqueta (ej: "Implante dental")

    # Buscar consentimiento vigente: firmado hace <= 3 meses
    limite = date.today() - timedelta(days=90)
    consent = session.exec(select(Consentimiento).where(
        Consentimiento.paciente_id == paciente_id,
        Consentimiento.tipo == label,
        Consentimiento.estado == "firmado",
        Consentimiento.updated_at >= limite,  # TimestampMixin: updated_at se actualiza al firmar
    )).first()

    return consent is not None


def firmar_por_codigo(session: Session, code: str, firma_datauri: str) -> Optional[Consentimiento]:
    """Firma pública por enlace: incrusta la firma en el PDF y pasa a 'firmado'."""
    c = info_por_codigo(session, code)
    if not c:
        return None
    if c.estado == "firmado":
        return c                                   # idempotente
    if expirado(c):
        return None                                # enlace caducado, aún sin firmar
    firma = firma_desde_datauri(firma_datauri)
    if not firma:
        raise ValueError("Firma vacía")
    path = OUT_DIR / f"consent_{c.id}.pdf"
    if path.exists():
        path.write_bytes(incrustar_firma(str(path), firma))
        (OUT_DIR / f"firma_{c.id}.png").write_bytes(firma)
        c.firma_url = f"/media/consentimientos/firma_{c.id}.png"
    c.estado = "firmado"
    session.add(c)
    session.commit()
    session.refresh(c)
    return c
