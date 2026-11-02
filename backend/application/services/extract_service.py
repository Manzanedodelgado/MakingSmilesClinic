"""Pipeline de extracción de factura en 2 etapas (capa de aplicación).

    Etapa 1 · OCR de documento  → modelo de visión (nvidia/nemoretriever-parse):
              imagen → bloques {text, bbox} → se ordenan (y, x) → `ocr_text`.
    Etapa 2 · Estructuración     → modelo de texto (meta/llama-3.3-70b-instruct):
              `ocr_text` + PROMPT_EXTRACCION_V2 → JSON {proveedor, cif_emisor, …, suplido, total}.

REUTILIZA, no duplica:
  · `LLMClient` (infra) — se instancia DOS veces, una por etapa, con su config.
  · `_pdf_a_imagenes` (gmail_ingest_service) — render PDF→JPEG base64 ya existente.
  · `invoice_extractor` — to_date / to_number / normalizar_cif para normalizar la salida.

CONFIG (R2 · fuente única): la estructura llega desde `integraciones.tipo='llm'`:
    { base_url, model, api_key,            # etapa 2 (texto)
      ocr: { base_url, model, api_key } }  # etapa 1 (OCR)
Las CLAVES nunca se escriben en código: se leen de .env (OCR_API_KEY / TXT_API_KEY) y, si no
están, se cae a las del JSON de la integración. Nada de secretos en logs ni en excepciones.
"""
import base64
import json
import os
import re
from typing import Optional

from infrastructure.external_apis.llm_client import LLMClient, LLMError

# Render PDF→JPEG base64: se reutiliza el del servicio de ingesta (NO se reimplementa).
from application.services.gmail_ingest_service import _pdf_a_imagenes
from domain.services import invoice_extractor as ext

# Prompt de la etapa 2 (versionado, literal). La línea del C.I.F. del emisor es CRÍTICA:
# sin ella el modelo coge el CIF del cliente/destinatario (el de la clínica), no el del proveedor.
# Prompt del script V7 (Colab, probado por la clínica con buenos resultados), con las claves de
# salida que espera _normalizar. Sustituye al de 15 líneas: en la prueba de 106 facturas reales
# del 27-oct-2026 este camino solo leía bien el 29 % porque no conocía estas peculiaridades.
PROMPT_EXTRACCION_V2 = """Eres un CONTABLE SENIOR de una clínica dental en España. Extrae los datos del GASTO del documento SIN DEJAR NADA SIN RELLENAR.

LA CLÍNICA (cliente, quien paga): TRIDENTAL ODONTÓLOGOS S.L.P. / Rubio García Dental, CIF B88393764, C/ Mayor 19, Alcorcón. NUNCA es el proveedor. Sus administradores (Juan Antonio Manzanedo, Mario Rubio, Virginia Tresgallo) tampoco son proveedores salvo que la factura la emitan ellos.

GASTO = todo lo que RESTA DINERO: facturas, recibos, cargos de tarjeta, suscripciones, cuotas, nóminas, impuestos, recargos, intereses, cartas de pago, apremios, sanciones, multas, comisiones, seguros, alquileres, renting...

Responde SOLO con un objeto JSON con estas claves:
accion: "gasto" si sale dinero; "descartado" si NO sale dinero (publicidad, propuestas, consultas o dudas a la gestoría, certificados, avisos o notificaciones sin importe, contratos, facturas EMITIDAS por la clínica, cobros, listados internos)
motivo_descarte: si accion = "descartado", el motivo concreto; si es gasto: ""
proveedor: razón social del EMISOR que cobra (para impuestos: "Agencia Tributaria")
cif_emisor: identificador fiscal del EMISOR tal como aparece (español con dígito de control, o extranjero: VAT, Tax ID, EIN, GST, UEN...). Usa la lista IDENTIFICADORES FISCALES DEL EMISOR DETECTADOS si viene. Nunca B88393764. null si de verdad no aparece.
numero_factura: número de factura / recibo / justificante / referencia de la carta de pago
fecha: fecha de emisión, YYYY-MM-DD
tipo_documento: factura | abono | rectificativa | nomina | impuesto | recibo | otro
base_imponible: suma de TODAS las bases (varios tipos de IVA: súmalas). Si el documento no lleva IVA (impuestos, tasas, sanciones, recibos exentos, prótesis dental exenta art. 20 LIVA, recibos extranjeros): base_imponible = total
iva_pct: tipo principal (0 si no lleva IVA)
cuota_iva: importe total de IVA (0 si no lleva)
irpf: importe retenido de IRPF en € (0 si no hay; OBLIGATORIO en alquileres y facturas de doctores/colaboradores). "Placa de retención" es un aparato de ortodoncia, no IRPF.
suplido: portes, suplidos exentos o recargos que SUMAN al total fuera de la base (0 si no hay)
seguridad_social: cuota de S.S. en € (solo en nóminas)
total: lo que sale de la cuenta, el importe FINAL a pagar (en facturas de varias páginas NUNCA un "suma y sigue"; en sanciones con reducción, el íntegro)
divisa: "EUR", "USD"...
concepto: descripción breve de lo que se paga
categoria: cuenta PGC: 600 Compras | 621 Arrendamientos | 622 Reparaciones | 623 Servicios profesionales | 625 Seguros | 626 Servicios bancarios | 627 Publicidad | 628 Suministros | 629 Otros servicios | 631 Otros tributos | 640 Sueldos | 642 Seguridad Social | 662 Intereses | 678 Sanciones
direccion, telefono, email: del PROVEEDOR

Reglas: importes como números con punto decimal; un abono lleva los importes en negativo. Comprueba que base_imponible + cuota_iva - irpf + suplido = total. Lee el documento ENTERO (pie de página incluido: ahí suele estar el CIF del emisor)."""


IDS_CLINICA = {"B88393764"}
IDS_ADMINISTRADORES = {"52982664W", "14304784A", "45573140C"}   # administradores: nunca proveedores


class ExtractionError(RuntimeError):
    """Fallo de una de las dos etapas del pipeline (OCR o estructuración)."""


def _client_ocr(integ: dict) -> Optional[LLMClient]:
    """Cliente de la etapa OCR. None si la integración no trae bloque 'ocr' utilizable."""
    ocr = dict(integ.get("ocr") or {})
    if not ocr.get("base_url") or not ocr.get("model"):
        return None
    ocr["api_key"] = os.environ.get("OCR_API_KEY") or ocr.get("api_key") or ""
    return LLMClient(ocr)


def _client_texto(integ: dict) -> LLMClient:
    """Cliente de la etapa de estructuración (texto)."""
    # Se pasa la configuración ENTERA salvo el bloque OCR: antes solo base_url/model/api_key, y se
    # perdían `reasoning_effort` (qwen3.5 es un modelo que razona: sin "none" gasta la respuesta
    # pensando y devuelve content vacío → "etapa2_estructura: respuesta sin JSON") y los `relevos`
    # (plan B). Desde el cambio a qwen3.5 ninguna factura de correo se pudo leer (21-sep→22-oct-2026).
    cfg = {k: v for k, v in integ.items() if k != "ocr"}
    cfg["api_key"] = os.environ.get("TXT_API_KEY") or integ.get("api_key") or ""
    return LLMClient(cfg)


def _bloques_a_texto(arguments: str) -> str:
    """tool_calls[0].function.arguments (JSON) → bloques {text, bbox} ordenados por (y, x)."""
    try:
        data = json.loads(arguments) if isinstance(arguments, str) else arguments
    except (json.JSONDecodeError, TypeError):
        return ""
    bloques = data
    if isinstance(data, dict):  # admite {"blocks": [...]} / {"elements": [...]} / {"bloques": [...]}
        for k in ("blocks", "elements", "bloques", "items"):
            if isinstance(data.get(k), list):
                bloques = data[k]
                break
        else:
            bloques = []
    if not isinstance(bloques, list):
        return ""
    # nemoretriever-parse devuelve [[{block},...]] (una lista de bloques por página) → aplanar.
    flat: list = []
    for item in bloques:
        if isinstance(item, list):
            flat.extend(x for x in item if isinstance(x, dict))
        elif isinstance(item, dict):
            flat.append(item)
    bloques = flat

    def clave(b: dict):
        bbox = b.get("bbox") or {}
        return (round(float(bbox.get("ymin", 0) or 0), 3), float(bbox.get("xmin", 0) or 0))

    ordenados = sorted((b for b in bloques if isinstance(b, dict)), key=clave)
    return "\n".join(str(b.get("text", "")).strip() for b in ordenados if b.get("text"))


def _ocr_text(pdf_bytes: bytes, mime: str, integ: dict) -> str:
    """Devuelve el texto del documento. Atajo: si el PDF trae texto NATIVO (≥50 chars) se usa
    directo y se ahorra la etapa OCR (y la clave OCR). Si no, render página 1 → OCR de visión."""
    nativo = _texto_nativo_pdf(pdf_bytes) if mime == "application/pdf" else ""
    if len(nativo) >= 50:
        return nativo
    # Sin texto nativo → necesitamos la imagen y el OCR de visión. La imagen ya es JPG/PNG (se manda
    # con su tipo real); un PDF se renderiza a JPEG.
    if mime.startswith("image/"):
        b64, img_mime = base64.b64encode(pdf_bytes).decode(), mime
    else:
        imgs = _pdf_a_imagenes(pdf_bytes, max_paginas=1, dpi=130)
        b64, img_mime = (imgs[0] if imgs else ""), "image/jpeg"
    if not b64:
        return nativo  # ni texto ni imagen: devolvemos lo poco que haya (la etapa 2 lo gestiona)
    cli = _client_ocr(integ)
    if cli is None:
        raise ExtractionError("OCR no configurado: falta integraciones.llm.ocr {base_url, model} o OCR_API_KEY")
    # nemoretriever-parse: SOLO la imagen en el content (NO acepta texto plano) + tool 'markdown_bbox';
    # max_tokens ≤ 3584 (límite real del modelo; 4000 da HTTP 400).
    messages = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": _data_uri(img_mime, b64)}},
    ]}]
    try:
        msg = cli.chat(messages, max_tokens=3000,
                       tools=[{"type": "function", "function": {"name": "markdown_bbox"}}])
    except LLMError as e:
        raise ExtractionError(f"etapa1_ocr: {e}") from e
    # Bloques OCR: _bloques_a_texto ya tolera string/lista/dict y aplana el [[…]] de nemoretriever.
    tool_calls = msg.get("tool_calls") or []
    if tool_calls:
        texto = _bloques_a_texto(tool_calls[0].get("function", {}).get("arguments", ""))
        if texto:
            return texto
    return (msg.get("content") or "").strip() or nativo


def _data_uri(mime: str, b64: str) -> str:
    """data-URI de la imagen para la PETICIÓN saliente al OCR (es el payload de la request, NO base64
    servido al cliente → fuera de la intención de R4). El tipo (image/png|jpeg) va según el fichero."""
    return "data:" + mime + ";base64," + b64


def _texto_nativo_pdf(pdf_bytes: bytes) -> str:
    try:
        import fitz  # pymupdf
    except ImportError:
        return ""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        txt = "\n".join((pg.get_text() or "") for pg in list(doc)[:3])
        doc.close()
        return txt.strip()
    except Exception:  # raiz: PDF ilegible/cifrado -> sin texto nativo; el flujo seguira a OCR  # noqa: BLE001
        return ""


def _json_de_contenido(content: str) -> dict:
    """Extrae el objeto JSON del `content` del modelo (tolera fences ```json … ``` y prosa)."""
    s = (content or "").strip()
    ini, fin = s.find("{"), s.rfind("}")
    if ini == -1 or fin <= ini:
        raise ExtractionError(f"etapa2_estructura: respuesta sin JSON ({s[:120]!r})")
    bruto = s[ini:fin + 1]
    try:
        return json.loads(bruto)
    except json.JSONDecodeError as e:
        # qwen3.5 escribe los importes a la española ("total": 6,34 / 1.234,56): JSON inválido.
        # Se reparan SOLO valores numéricos sin comillas tras ':' (los textos no se tocan).
        def _decimal_es(m: re.Match) -> str:
            return f"{m.group(1)}{m.group(2).replace('.', '')}.{m.group(3)}"
        reparado = re.sub(r'(:\s*)(-?\d{1,3}(?:\.\d{3})+|-?\d+),(\d+)(?=\s*[,}\n])', _decimal_es, bruto)
        try:
            return json.loads(reparado)
        except json.JSONDecodeError:
            raise ExtractionError(f"etapa2_estructura: JSON inválido ({e})") from e


def _num(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return ext.to_number(str(v))


def _fecha_iso(v) -> Optional[str]:
    d = ext.to_date(str(v).strip()) if v else None
    return d.isoformat() if d else None


def _cif_raw(v) -> Optional[str]:
    """Limpia el CIF crudo del modelo. Descarta frases ('NO DISPONIBLE EN EL TEXTO…') que el LLM
    a veces devuelve en vez de null: un CIF no lleva espacios y no pasa de ~18 chars."""
    if not v:
        return None
    c = str(v).strip().upper()
    return c if (c and " " not in c and len(c) <= 18) else None


def _normalizar(raw: dict) -> dict:
    """Salida canónica del pipeline: claves fijas, fecha YYYY-MM-DD, importes float."""
    return {
        "proveedor": (str(raw.get("proveedor")).strip() if raw.get("proveedor") else None),
        "cif_emisor": _cif_raw(raw.get("cif_emisor")),
        "numero_factura": (str(raw.get("numero_factura")).strip() if raw.get("numero_factura") else None),
        "fecha": _fecha_iso(raw.get("fecha")),
        "base_imponible": _num(raw.get("base_imponible")),
        "iva_pct": _num(raw.get("iva_pct")),
        "suplido": _num(raw.get("suplido")) or 0.0,
        "total": _num(raw.get("total")),
        # ── Datos completos de gestoría (dirección/tel/mail → emisor_datos; IRPF/S.S./
        #    tipo/concepto/categoría para el registro completo que pide la asesoría).
        "direccion": (str(raw.get("direccion")).strip() if raw.get("direccion") else None),
        "telefono": (str(raw.get("telefono")).strip() if raw.get("telefono") else None),
        "email": (str(raw.get("email")).strip() if raw.get("email") else None),
        "tipo_documento": (str(raw.get("tipo_documento")).strip().lower() if raw.get("tipo_documento") else None),
        "concepto": (str(raw.get("concepto")).strip()[:300] if raw.get("concepto") else None),
        "irpf": _num(raw.get("irpf")),
        "seguridad_social": _num(raw.get("seguridad_social")),
        "categoria": (str(raw.get("categoria")).strip()[:40] if raw.get("categoria") else None),
        "divisa": (str(raw.get("divisa")).strip().upper()[:3] if raw.get("divisa") else None),
        "accion": (str(raw.get("accion")).strip().lower() if raw.get("accion") else None),
        "motivo_descarte": (str(raw.get("motivo_descarte")).strip()[:120] if raw.get("motivo_descarte") else None),
        "cuota_iva": _num(raw.get("cuota_iva")),
    }


# Identificadores fiscales extranjeros rotulados (VAT, EIN, GST...). Del script V7.
_RE_ID_EXTRANJERO = re.compile(
    r"\b(?i:VAT(?:\s*(?:No|Number|ID|Reg\w*))?|Tax\s*(?:ID|Number|Reg\w*)|TIN|EIN|GST(?:\s*Reg\w*)?|ABN|UID|"
    r"USt-?IdNr\.?|P\.?\s?IVA|Partita IVA|N[°º]?\s*TVA|SIRE[NT]|RFC|UEN|CNPJ|NIPC)\s*[:#.]?\s*(?i:No\.?|Number|n[°º])?"
    r"\s*[:#]?\s*([A-Z]{0,3}[\s-]?\d[\d\s.-]{4,16}\d[A-Z]?)(?![a-z0-9])")


def pista_identificadores(texto: str) -> str:
    """Bloque «IDENTIFICADORES FISCALES DEL EMISOR DETECTADOS» que el V7 añade al mensaje: los
    NIF/CIF válidos del documento (dígito de control) y los extranjeros rotulados, sin los de la
    clínica ni sus administradores. La IA deja de inventar o de coger el del cliente."""
    from domain.services import gestor_lectura_fiscal as fiscal
    excluidos = IDS_CLINICA | IDS_ADMINISTRADORES
    try:
        es = [i for i in fiscal.identificadores(texto or "") if ext.normalizar_cif(i) not in excluidos]
    except Exception:  # raiz: motor fiscal (identificadores) falla -> pista vacia; nunca bloquea la lectura  # noqa: BLE001
        es = []
    fuera = []
    for m in _RE_ID_EXTRANJERO.finditer(texto or ""):
        c = re.sub(r"\s+", "", m.group(1)).strip(".-")
        if c not in fuera and c not in es:
            fuera.append(c)
    if not es and not fuera:
        return ""
    return ("IDENTIFICADORES FISCALES DEL EMISOR DETECTADOS EN EL DOCUMENTO (validados, excluida la "
            f"clínica): españoles={es} extranjeros={fuera}")


def extraer_desde_texto(texto: str, integracion_llm: dict, aviso: Optional[str] = None) -> dict:
    """Etapa 2 a secas: estructura a JSON un texto YA legible (texto OCR, o el CUERPO de un correo
    cuando la factura viene en el propio email y no en un adjunto). Devuelve el dict normalizado.
    `aviso`: corrección del validador para un reintento (p.ej. «el CIF que diste es del cliente»)."""
    if not texto or not texto.strip():
        raise ExtractionError("etapa2_estructura: texto vacío")
    cli = _client_texto(integracion_llm)
    user = texto[:12000]
    pista = pista_identificadores(texto)
    if pista:
        user += "\n\n" + pista
    if aviso:
        user += f"\n\n⚠️ CORRECCIÓN OBLIGATORIA de tu lectura anterior: {aviso}"
    messages = [
        {"role": "system", "content": PROMPT_EXTRACCION_V2},
        {"role": "user", "content": user},
    ]
    try:
        # max_tokens alto a propósito: gpt-oss-120b "gasta" tokens en razonamiento interno
        # (reasoning) antes del contenido; con 600 devolvía '' o JSON truncado → incidencias.
        msg = cli.chat(messages, temperature=0.0, max_tokens=4000)
    except LLMError as e:
        raise ExtractionError(f"etapa2_estructura: {e}") from e
    return _normalizar(_json_de_contenido(msg.get("content") or ""))


def extraer_desde_pdf(pdf_bytes: bytes, mime: str, integracion_llm: dict,
                      aviso: Optional[str] = None) -> dict:
    """Extrae los campos de una factura desde sus bytes (PDF o imagen) con el pipeline 2-etapas.

    Devuelve un dict normalizado: proveedor, cif_emisor, numero_factura, fecha (YYYY-MM-DD),
    base_imponible, iva_pct, suplido, total. Lanza ExtractionError si una etapa falla.
    `aviso`: feedback del validador para el reintento (se aplica solo a la etapa 2; el OCR no
    se repite porque su resultado no cambia).
    """
    if not pdf_bytes:
        raise ExtractionError("sin contenido: pdf_bytes vacío")
    ocr_text = _ocr_text(pdf_bytes, mime or "application/pdf", integracion_llm)
    if not ocr_text.strip():
        raise ExtractionError("etapa1_ocr: documento sin texto legible")
    return extraer_desde_texto(ocr_text, integracion_llm, aviso=aviso)
