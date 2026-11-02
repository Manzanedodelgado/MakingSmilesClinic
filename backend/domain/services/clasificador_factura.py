"""Clasifica un correo recibido decidiendo PRIMERO por el sobre (asunto + remitente),
como hace un humano de un vistazo — NO por si el OCR pudo leer el documento.

Regla de oro: una factura cuyo PDF está cifrado, vive tras un portal o no se pudo leer
SIGUE SIENDO UNA FACTURA. Un fallo de extracción jamás la convierte en 'no_factura'.
Función pura: no toca BBDD, no descarga nada. Devuelve (clase, motivo).
"""
import re

from domain.services.invoice_extractor import normalizar_cif

# El sobre habla de una factura/recibo de compra.
FACTURA = re.compile(r"\b(factura|fatura|invoice|recibo|e-?factura)\b", re.I)

# El sobre es correspondencia/listado/ruido contable, NO una factura de compra concreta.
# OJO: "impuestos" y "retenciones" NO van aquí — un aviso de pago o recibo de un impuesto
# real (IRPF, IBI, tasas...) ES UN GASTO como cualquier otro, no solo lo que literalmente
# se llama "factura" (decisión del usuario, 2026-08-09). Lo que se excluye es el LISTADO o
# RESUMEN administrativo sobre impuestos ("resumen trimestral", "modelo 303 presentado"),
# no el cargo/recibo individual — de ahí que 'modelo\s*\d' sí se mantenga: presentar un
# modelo no es un gasto, es un trámite; el cargo real llega por el banco o por su propio recibo.
NO_COMPRA = re.compile(
    r"(libro|listado|lista\s+de|tabla|tablas|documentaci[oó]n|datos\b|"
    r"recibidas?\s+y\s+emitidas?|emitidas?|[1-4]\s*t(rimestre)?\b|trimestral|resumen|"
    r"extracto|contabilidad|modelo\s*\d|"
    r"pedido|presupuesto|inventario|dudas?|ahorr|promoci|newsletter)", re.I)

# ─────────────────────── BASURA CONFIABLE (no factura Y no correspondencia real) ───────────────────────
# Deliberadamente ESTRECHO: solo ruido automático inconfundible (alertas de seguridad, avisos
# de activación, bienvenidas de alta, newsletters). Ante cualquier duda NO entra aquí — se deja
# el correo tal cual en el INBOX sin tocar. Nunca se usa para decidir "es factura"; solo decide
# si algo que YA se clasificó como no_factura se puede borrar solo o hay que dejarlo en su sitio
# por si acaso (decisión del usuario, 2026-08-09: "si tengo duda si es basura lo dejo en inbox").
BASURA_REMITENTE = re.compile(
    r"no-?reply@|noreply@|notifications?@|alert(a|s)?@|security@|do-?not-?reply@|"
    r"mailer-daemon@|postmaster@|welcome@|hello@|newsletter@|marketing@|news@|"
    r"@mkt\.|\.mkt@", re.I)
BASURA_ASUNTO = re.compile(
    r"alerta de seguridad|security alert|nuevo inicio de sesi[oó]n|new sign-?in|"
    r"actividad inusual|unusual activity|"
    r"thanks for signing up|welcome to\b|bienvenido[a]? a\b|confirma tu (correo|email|cuenta)|"
    r"verify your (email|account)|c[oó]digo de verificaci[oó]n|verification code|"
    r"one-?time password|c[oó]digo de un solo uso|c[oó]digo de acceso|"
    r"newsletter|unsubscribe|darse de baja|date de baja|"
    # marketing/promociones genéricas (auditado contra datos reales, 2026-08-10: OpenRouter,
    # Ollama, Alibaba Cloud, DonWeb, Neon, proveedores dentales en oferta...)
    r"promoci[oó]n|oferta[s]?\s+exclusiv|\d+\s*%\s*(de\s*)?(dto\.?|descuento|off)\b|"
    r"env[ií]o\s+r[aá]pido|no dejes que|no pierdas la oportunidad|"
    r"taller\s+gratuito|curso\s+gratis|gratis\b.{0,20}\b(taller|curso|webinar)|"
    r"you'?re in\b|quick guide|get started with|free trial|welcome gift|unlock\b|"
    r"qu[eé] dicen tus clientes|desde cero \(|aprend[eé] .{0,25}gratis", re.I)
# Marketing casi siempre lleva emoji decorativo en el asunto; correspondencia real de
# facturación/impuestos/pagos, prácticamente nunca (auditado 2026-08-10).
EMOJI_ASUNTO = re.compile(
    r"[\U0001F300-\U0001FAFF\u2600-\u27BF\u2190-\u21FF\u2B00-\u2BFF]")

# EXCEPCIÓN — auditando datos reales (2026-08-09) aparecieron avisos automáticos que SÍ importan:
# "Google Workspace: se ha rechazado el pago de rubiogarciadental.com", Cloudflare pidiendo
# actualizar los nameservers del propio dominio, Zadarma avisando de que la centralita se
# queda sin saldo. Todos vienen de remitentes 'noreply@' de confianza (matchean BASURA_REMITENTE)
# y Gmail tampoco los marca \Important — un remitente automático NO es sinónimo de "sin
# importancia" cuando el asunto habla de dinero, plazos o infraestructura propia. Esto GANA
# siempre a BASURA_REMITENTE/BASURA_ASUNTO, se comprueba primero.
NO_ES_BASURA_AUNQUE_PAREZCA = re.compile(
    r"pago|payment|factura|cobro|cargo|rechazad|fallid|impagad|"
    r"acci[oó]n (requerida|necesaria)|action required|urgent|"
    r"dominio|domain|nameserver|dns|centralita|suspend|cancelad|"
    r"vence|caduca|expir", re.I)


def es_basura_confiable(asunto: str | None, remitente: str | None) -> bool:
    """True SOLO si el remitente o el asunto son ruido automático/marketing inconfundible Y el
    asunto no trae ninguna señal de que en realidad importa (dinero, plazo, infraestructura
    propia). No decide nunca si algo ES factura — solo si un no_factura ya decidido se puede
    tirar solo."""
    if NO_ES_BASURA_AUNQUE_PAREZCA.search(asunto or ""):
        return False
    return bool(BASURA_REMITENTE.search(remitente or "") or BASURA_ASUNTO.search(asunto or "")
                or EMOJI_ASUNTO.search(asunto or ""))


def clasificar(asunto: str, remitente: str, datos: dict | None = None,
               *, receptores=()) -> tuple[str, str | None]:
    """clase ∈ {factura, factura_pendiente, no_factura}.
    - 'factura'           : extrajimos CIF de emisor fiable → lista para dar de alta el gasto.
    - 'factura_pendiente' : el sobre dice factura pero no pudimos leer el importe (cifrada/portal/
                            OCR/CIF dudoso) → se queda en 'revisar' CON motivo. Nunca se descarta.
    - 'no_factura'        : ni sobre, ni remitente, ni contenido apuntan a factura de compra.
    """
    datos = datos or {}
    asunto = (asunto or "").strip()
    remitente = (remitente or "").strip()
    sobre = f"{asunto} {remitente}"
    cif = normalizar_cif(datos.get("cif_emisor"))

    es_correspondencia = bool(NO_COMPRA.search(asunto)) and not _factura_singular(asunto)
    sobre_dice_factura = bool(FACTURA.search(sobre)) and not es_correspondencia

    # Nuestro propio CIF leído como emisor → o es venta nuestra o se leyó mal: a revisar, no se tira.
    if cif and cif in receptores:
        return "factura_pendiente", "revisar_cif_receptor"
    # Datos fiables (CIF de un tercero) → factura lista.
    if cif:
        return "factura", None
    # El sobre dice factura pero no hay datos → factura pendiente de leer (cifrada/portal/OCR).
    if sobre_dice_factura:
        return "factura_pendiente", "pendiente_de_leer"
    # Ni sobre ni datos → no es factura de compra.
    return "no_factura", "no_parece_factura"


def _factura_singular(asunto: str) -> bool:
    """'Factura nº 123' / 'Su factura de X' es una factura concreta aunque caiga cerca de palabras
    de listado; 'Facturas recibidas y emitidas 1T' es correspondencia. Distingue uno de otro."""
    return bool(re.search(r"\bfactura\s+(n[ºo.]|de\b|del\b|mes\b|mayo|junio|\d)", asunto, re.I))


# ─────────────────────── CLASIFICACIÓN A NIVEL DE CORREO ───────────────────────
# Amplía la clasificación del "sobre" con las señales del BUZÓN (dominio propio, etiquetas,
# patrones de no-factura, portales conocidos). Lo usa el re-proceso del backlog (buckets B/C)
# y la ingesta. Devuelve clases en MAYÚSCULAS {FACTURA, NO_FACTURA, PORTAL} con su subtipo.
# Verificadas experimentalmente sobre el backlog real del centro 1.
DOMINIOS_CLINICA_POR_DEFECTO = ("rubiogarciadental.com",)
ETIQUETAS_NO_FACTURA = (r"\Sent",)
PATRONES_NO_FACTURA = [
    ("asunto", r"\bn[oó]mina\b", "nomina"),
    ("asunto", r"\bcontrato\b", "contrato"),
    ("asunto", r"\btransmisi[oó]n\b", "contrato"),
    ("asunto", r"^inventario$", "inventario"),
    ("cuerpo", r"ruego.*remit.*facturas?", "asesoria_pide_facturas"),
    ("cuerpo", r"podr[ií]an enviar.*facturas?", "clinica_pide_facturas"),
    ("asunto", r"confirmaci[oó]n de pedido", "confirmacion_pedido"),
]
# Orden = prioridad del subtipo cuando el remitente cae en varios (fineasy antes que leasingsolutions).
PORTALES_CONOCIDOS = ("endesa", "fineasy", "leasingsolutions", "quicksmile", "vevidental", "bnpparibas")


def _dominio(remitente: str) -> str:
    m = re.search(r"@([\w.\-]+)", remitente or "")
    return (m.group(1).lower().rstrip(">").strip() if m else "")


def _es_etiqueta_no_factura(label) -> bool:
    norm = str(label).lstrip("\\").strip().lower()
    return norm in {e.lstrip("\\").strip().lower() for e in ETIQUETAS_NO_FACTURA}


def _portal_de(remitente_l: str) -> str:
    return next((p for p in PORTALES_CONOCIDOS if p in remitente_l), "")


def clasificar_email(email: dict, *, dominio_clinica: str = DOMINIOS_CLINICA_POR_DEFECTO[0]) -> tuple[str, str]:
    """Devuelve (clase, motivo). clase ∈ {FACTURA, NO_FACTURA, PORTAL}.

    Lee de `email`: from/remitente, subject/asunto, body/cuerpo, labels, attachments/adjuntos
    (acepta tanto las claves del prompt como las del parser IMAP `_parse_message`).

    Regla de oro heredada: un correo CON adjunto o cuyo sobre dice factura nunca se degrada a
    no_factura por un fallo de lectura. PORTAL = aviso de un portal conocido SIN documento adjunto
    (intervención humana: bajar la factura del portal), nunca una factura real ya adjunta.
    """
    remitente = email.get("from") or email.get("remitente") or ""
    asunto = (email.get("subject") or email.get("asunto") or "").strip()
    cuerpo = email.get("body") or email.get("cuerpo") or ""
    labels = email.get("labels") or []
    adjuntos = email.get("attachments") or email.get("adjuntos") or []
    tiene_adjunto = bool(adjuntos)

    # 1 · Correo del propio dominio de la clínica → no es factura de compra.
    dom = _dominio(remitente)
    if dom and dominio_clinica and dom.endswith(dominio_clinica.lower()):
        return "NO_FACTURA", "correo_propio_clinica"
    # 2 · Etiqueta de Gmail \Sent → correo enviado por la clínica.
    if any(_es_etiqueta_no_factura(lb) for lb in labels):
        return "NO_FACTURA", "correo_enviado_clinica"
    # 3 · Patrones de asunto/cuerpo (nómina, contrato, asesoría pide facturas…).
    for campo, patron, subtipo in PATRONES_NO_FACTURA:
        texto = asunto if campo == "asunto" else cuerpo
        if re.search(patron, texto, re.I):
            return "NO_FACTURA", subtipo
    # 4 · Portal conocido SIN adjunto → falta el documento, lo baja un humano.
    portal = _portal_de(remitente.lower())
    if portal and not tiene_adjunto:
        return "PORTAL", f"portal:{portal}"
    # 5 · Resto: la clasificación del sobre. Con adjunto o sobre-factura → FACTURA (no se descarta).
    clase, _motivo = clasificar(asunto, remitente, {"cif_emisor": email.get("cif_emisor")})
    if clase == "no_factura" and not tiene_adjunto:
        return "NO_FACTURA", "no_parece_factura"
    return "FACTURA", ""
