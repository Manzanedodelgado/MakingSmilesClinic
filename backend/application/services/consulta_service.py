"""Cerebro de La Consulta Viva — enruta una evidencia hablada al mapa de incógnitas.

Recibe UNA frase (lo que se dice/observa en consulta) + las incógnitas abiertas, y decide
cómo las mueve: a cuál ancla la evidencia, cuánto sube su confianza, si propone un tratamiento
o si abre una incógnita nueva. Normaliza coloquial→clínico (diccionario del gabinete).
Usa el LLM del centro (integración tipo='llm', OpenAI-compatible). Si no hay LLM, lanza LLMError
y el frontend cae al enrutador heurístico local.
"""
import json
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from sqlmodel import Session, select

from application.services.llm_config import CONSULTA_VIVA, resolver_llm
from application.services.caja_service import CajaService
from application.services.receta_pdf import generar_receta_pdf
from domain.models.clinico import Soap
from domain.models.core import Centro, Cita, Colaborador, Paciente, Tratamiento
from domain.models.documentos import Receta, RecetaLinea, TalonarioReceta

_MEDIA_RECETAS = Path(__file__).resolve().parents[2] / "media" / "recetas"
from domain.models.economico import PacienteTarifa, TarifaPrecio, TratamientoRealizado
from domain.models.identidad import UsuarioPeriodo
from infrastructure.external_apis.llm_client import LLMClient, LLMError

SYSTEM = (
    "Eres el copiloto clínico de una consulta dental en España. Trabajas con un MAPA DE "
    "INCÓGNITAS: preguntas clínicas abiertas sobre el paciente, cada una con su confianza (0-100).\n"
    "Recibes UNA frase de lo que se dice u observa en la consulta y la lista de incógnitas abiertas.\n"
    "Decide cómo esa frase mueve el mapa. Normaliza el coloquial al término clínico "
    "(empaste→obturación, funda→corona, matar el nervio→endodoncia, limpieza→tartrectomía, "
    "flemón→absceso, piorrea→periodontitis, etc.). Las piezas en notación FDI (p.ej. 46).\n\n"
    "Responde SOLO con un JSON con esta forma exacta:\n"
    "{\n"
    '  "pieza": "46" | null,              // pieza FDI mencionada\n'
    '  "targetId": "<id de una incógnita existente>" | null,  // a cuál ancla la evidencia\n'
    '  "deltaConf": 0-40,                  // cuánto sube su confianza\n'
    '  "propuesta": {"texto":"ENDODONCIA","precio":null} | null,  // tratamiento que propone\n'
    '  "nueva": {"pregunta":"¿Causa del dolor en 46?","pieza":"46","hipotesis":"...",'
    '"confianza":0-100,"propuesta":null,"origen":"escucha"} | null,  // incógnita que nace\n'
    '  "explica": "2-4 palabras"           // por qué, breve\n'
    "}\n\n"
    "Reglas:\n"
    "- Si la frase aporta a una incógnita existente → targetId + deltaConf (síntoma claro o decisión: alto; dato vago: bajo).\n"
    "- Si nombra un tratamiento que NO casa con ninguna incógnita → nueva con esa propuesta y confianza ~55.\n"
    "- Si es un síntoma con pieza y no hay incógnita de esa pieza → nueva '¿Causa del dolor en <pieza>?' confianza ~30, y targetId al motivo con deltaConf ~15.\n"
    "- Si es una ALERGIA o medicación de riesgo (Sintrom, anticoagulante…) → nueva con origen 'alerta' y confianza 90.\n"
    "- No inventes piezas ni precios. precio siempre null (lo pone el catálogo).\n"
    "- targetId debe ser uno de los ids que te paso, o null."
)


def _config_llm(session: Session, centro_id: int) -> dict:
    cfg = resolver_llm(session, centro_id, CONSULTA_VIVA)
    if not cfg:
        raise LLMError("LLM no configurado para este centro")
    return cfg


def _solo_json(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    # quédate con el primer objeto {...} por si el modelo añade texto
    m = re.search(r"\{.*\}", s, re.DOTALL)
    return m.group(0) if m else s


def _int(v: Any, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(float(v))))
    except (TypeError, ValueError):
        return default


def analizar(session: Session, centro_id: int, evidencia: str, incognitas: list[dict]) -> dict:
    cliente = LLMClient(_config_llm(session, centro_id))
    user = json.dumps({"evidencia": evidencia, "incognitas": incognitas}, ensure_ascii=False)
    msg = cliente.chat(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        temperature=0.2, max_tokens=400,
    )
    # Todo el parseo es defensivo: cualquier forma rara del modelo → LLMError (el front cae al heurístico).
    try:
        data: dict[str, Any] = json.loads(_solo_json(msg.get("content") or ""))
        if not isinstance(data, dict):
            raise ValueError("no es objeto")

        ids = {i.get("id") for i in incognitas}
        target = data.get("targetId")
        if target not in ids:
            target = None

        nueva = data.get("nueva")
        if isinstance(nueva, dict) and nueva.get("pregunta"):
            prop = nueva.get("propuesta")
            nueva = {
                "pregunta": str(nueva.get("pregunta"))[:200],
                "pieza": (str(nueva["pieza"])[:6] if nueva.get("pieza") else None),
                "hipotesis": str(nueva.get("hipotesis") or "Detectado en la consulta")[:200],
                "confianza": _int(nueva.get("confianza"), 30, 0, 100),
                "propuesta": {"texto": str(prop.get("texto"))[:120], "precio": None} if isinstance(prop, dict) and prop.get("texto") else None,
                "origen": nueva.get("origen") if nueva.get("origen") in ("escucha", "alerta") else "escucha",
            }
        else:
            nueva = None

        prop = data.get("propuesta")
        propuesta = {"texto": str(prop.get("texto"))[:120], "precio": None} if isinstance(prop, dict) and prop.get("texto") else None

        return {
            "pieza": (str(data["pieza"])[:6] if data.get("pieza") else None),
            "targetId": target,
            "deltaConf": _int(data.get("deltaConf"), 0, 0, 40),
            "propuesta": propuesta,
            "nueva": nueva,
            "explica": str(data.get("explica") or "ia")[:40],
        }
    except Exception as e:  # raiz: parseo robusto: nunca 500, siempre fallback limpio
        raise LLMError(f"Respuesta LLM no parseable: {e}") from e


# ───────────────────────── CIERRE: registrar lo decidido ─────────────────────────

def _colaborador(session: Session, usuario_id: int):
    return session.exec(
        select(Colaborador.id)
        .join(UsuarioPeriodo, UsuarioPeriodo.id == Colaborador.periodo_id)
        .where(UsuarioPeriodo.usuario_id == usuario_id)
        .order_by(UsuarioPeriodo.id.desc())
    ).first()


_STOP_TRAT = {"de", "del", "la", "el", "los", "las", "sobre", "con", "por", "y",
              "en", "a", "para", "un", "una", "o", "u"}

# Sinónimos coloquiales → término del catálogo (ya normalizado: sin acentos, z→c).
_SINONIMOS_TRAT = {
    "extraccion": "exodoncia", "extracciones": "exodoncia", "sacar": "exodoncia",
    "empaste": "obturacion", "empastes": "obturacion",
    "funda": "corona", "fundas": "corona",
    "reco": "reconstruccion", "endo": "endodoncia", "exo": "exodoncia",
    "limpieza": "tartrectomia", "tarta": "tartrectomia",
}


def _norm_trat(s: str) -> str:
    """Normaliza para comparar: minúsculas, sin acentos, z↔c unificadas (zirconio=circonio),
    solo alfanumérico. Así 'corona de circonio' ≈ 'CORONA ZIRCONIO'."""
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("z", "c")  # zirconio→circonio, unifica el sonido
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _tokens_trat(s: str) -> set[str]:
    return {_SINONIMOS_TRAT.get(t, t) for t in _norm_trat(s).split()
            if t and t not in _STOP_TRAT}


def _resolver_tratamiento(session: Session, centro_id: int, nombre: str):
    """Nombre coloquial/propuesto → id de catálogo. Exacto (ILIKE) → contiene →
    fallback por tokens normalizados (acentos/z-c/relleno) → None."""
    nombre = (nombre or "").strip()
    if len(nombre) < 2:
        return None
    base = select(Tratamiento.id).where(
        Tratamiento.centro_id == centro_id, Tratamiento.activo == True)  # noqa: E712
    tid = session.exec(base.where(Tratamiento.nombre.ilike(nombre))).first()
    if tid:
        return tid
    tid = session.exec(base.where(Tratamiento.nombre.ilike(f"%{nombre}%"))
                       .order_by(Tratamiento.nombre)).first()
    if tid:
        return tid
    # Fallback por tokens: exige que TODOS los tokens de la consulta estén en el candidato;
    # entre los que cumplen, elige el más ajustado (menos tokens sobrantes). Solo suma matches
    # donde antes había None, así que no altera lo que ya casaba.
    q = _tokens_trat(nombre)
    if not q:
        return None
    filas = session.exec(select(Tratamiento.id, Tratamiento.nombre).where(
        Tratamiento.centro_id == centro_id, Tratamiento.activo == True)).all()  # noqa: E712
    mejor, mejor_extra = None, 10**9
    for fid, fnombre in filas:
        cand = _tokens_trat(fnombre)
        if q <= cand:
            extra = len(cand - q)
            if extra < mejor_extra:
                mejor, mejor_extra = fid, extra
    return mejor


def candidatos_tratamiento(session: Session, centro_id: int, nombre: str,
                           tarifa_id=None, limit: int = 6) -> list[dict]:
    """Opciones de catálogo para un término coloquial, ordenadas por ajuste, con precio de
    tarifa. Sirve para DESAMBIGUAR: si un genérico ('implante', 'exodoncia') tiene varios
    específicos, el agente ofrece la lista en vez de elegir a ciegas."""
    nombre = (nombre or "").strip()
    if len(nombre) < 2:
        return []
    qn = _norm_trat(nombre)
    q = _tokens_trat(nombre)
    filas = session.exec(select(Tratamiento.id, Tratamiento.nombre).where(
        Tratamiento.centro_id == centro_id, Tratamiento.activo == True)).all()  # noqa: E712
    scored = []
    for fid, fnombre in filas:
        cn = _norm_trat(fnombre)
        ct = _tokens_trat(fnombre)
        if not cn or not ct:          # nombres vacíos/puntuación: no son candidatos
            continue
        if qn == cn:
            score = (0, 0)
        elif qn and (qn in cn or cn in qn):
            score = (1, abs(len(ct) - len(q)))
        elif q and q <= ct:
            score = (2, len(ct - q))
        else:
            continue
        scored.append((score, fid, fnombre))
    scored.sort(key=lambda x: x[0])
    return [{"tratamiento_id": fid, "nombre": fnombre,
             "precio": (_precio(session, tarifa_id, fid) if tarifa_id else None)}
            for _, fid, fnombre in scored[:limit]]


def cerrar(session: Session, centro_id: int, usuario_id: int, paciente_id: int,
           tratamientos: list[dict], nota: str | None) -> dict:
    """Registra el cierre de la consulta: crea un acto (tratamientos_realizados, estado=Realizado)
    por cada tratamiento decidido, resolviendo su nombre contra el catálogo. La nota SOAP de la
    visita se guarda en `notas`. La IA propone, el doctor dispone: esto solo corre al aprobar."""
    pac = session.get(Paciente, paciente_id)
    if not pac or pac.centro_id != centro_id:
        raise ValueError("Paciente no encontrado")
    col = _colaborador(session, usuario_id)
    if col is None:
        raise ValueError("El usuario no tiene colaborador asociado (no se puede registrar un acto)")

    creados = []
    for t in tratamientos:
        trid = _resolver_tratamiento(session, centro_id, t.get("texto"))
        precio = t.get("precio")
        acto = TratamientoRealizado(
            centro_id=centro_id, paciente_id=paciente_id, tratamiento_id=trid,
            piezas=(t.get("pieza") or None), fecha_inicio=date.today(),
            importe=(float(precio) if precio is not None else 0.0),
            notas=(nota or None), colaborador_id=col, estado_id=5,  # 5 = Realizado
        )
        session.add(acto)
        session.flush()
        creados.append({"id": acto.id, "tratamiento": t.get("texto"),
                        "tratamiento_id": trid, "pieza": t.get("pieza")})
    # Crear los cargos y aplicar pagos a cuenta dentro de la misma transacción que los actos.
    CajaService(session, centro_id).aplicar_saldo(paciente_id, commit=False)
    session.commit()
    return {"registrados": creados, "n": len(creados)}


# ───────────────────────── ESCUCHA ACTIVA (borradores de la visita) ─────────────────────────
SYSTEM_ESCUCHA = (
    "Eres Alex, copiloto de una consulta dental en España. Escuchas la conversación entre el "
    "DOCTOR y el PACIENTE durante la visita y extraes un BORRADOR para que el doctor lo revise "
    "(nunca es definitivo, nada se guarda solo).\n"
    "CRÍTICO: El ANÁLISIS (diagnóstico) DEBE REFLEJAR LO QUE EL DOCTOR REALMENTE DIJO, no solo el tipo de tratamiento. "
    "Si el doctor dice 'dolor en molar 37', el diagnóstico es 'Dolor en molar 37', NO 'ENDODONCIA MULTIRRADICULAR'. "
    "Normaliza el coloquial (empaste→OBTURACIÓN, endo→ENDODONCIA, etc.) pero PRESERVA el diagnóstico clínico del doctor.\n"
    "Piezas en notación FDI (p.ej. 46).\n"
    "REGLAS CLÍNICAS AL ELEGIR EL TÉRMINO (según la pieza FDI, 2º dígito):\n"
    "- ENDODONCIA/REENDODONCIA por nº de raíces según el diente: MOLAR (6,7,8) → 'ENDODONCIA "
    "MULTIRRADICULAR'; premolar (4,5) → 'ENDODONCIA BIRRADICULAR'; incisivo/canino (1,2,3) → "
    "'ENDODONCIA UNIRRADICULAR'. REGLA DURA por el 2º dígito FDI: molares (6,7,8) SIEMPRE "
    "multirradiculares; premolares (posición 4 o 5) SIEMPRE BIRRADICULARES; incisivos/caninos "
    "(1,2,3) SIEMPRE unirradiculares. No deduzcas las raíces por otra vía: manda la posición.\n"
    "- 'perno y reco', 'perno + reconstrucción', 'perno de fibra' → UNA sola línea "
    "'RECONSTRUCCION CON PERNO DE FIBRA DE VIDRIO' (no separes perno y reconstrucción, salvo que "
    "digan explícitamente 'perno colado/muñón colado').\n"
    "- CORONA de circonio/zirconio: 'SOBRE DIENTE' si la pieza es un diente natural (lleva endo, "
    "reconstrucción, perno…); 'SOBRE IMPLANTE' solo si hay implante en esa pieza.\n\n"
    "Responde SOLO con un JSON con esta forma exacta:\n"
    "{\n"
    '  "soap": {\n'
    '    "subjetivo": "motivo de consulta + lo que cuenta el paciente + síntomas",\n'
    '    "objetivo": "exploración y hallazgos objetivos",\n'
    '    "analisis": "diagnóstico",\n'
    '    "plan": "plan de tratamiento, en texto"\n'
    "  },\n"
    '  "tratamientos": [ {"texto":"ENDODONCIA","pieza":"46"} ],   // para las líneas del presupuesto\n'
    '  "receta": [ {"medicamento":"Ibuprofeno 600 mg","posologia":"1 comprimido/8 h, 3 días","pauta":"cada 8 horas","duracion":"3 días","envases":1,"unidades":30} ],\n'
    '  "mensaje": "Mensaje breve (2-3 líneas) y cercano de WhatsApp al paciente que resuma el diagnóstico y próximos pasos. Tono cercano, SIN tecnicismos alarmantes. Ej: Hemos visto que [diagnóstico breve]. Lo mejor es [plan]. Te llamamos para [próxima acción]."\n'
    "}\n\n"
    "Reglas:\n"
    "- Rellena cada caja del SOAP con lo que se deduzca; si algo no se menciona, string vacío.\n"
    "- 'tratamientos' = lo que el doctor decide hacer, con su pieza si la hay; usa nombres de catálogo.\n"
    "- 'receta' solo si el doctor prescribe medicación; si no, lista vacía.\n"
    "- 'mensaje': tono cercano y claro, SIN tecnicismos ni diagnósticos alarmantes; incluye cuidados/"
    "recomendaciones y, si se menciona, la próxima cita.\n"
    "- No inventes datos que no estén en la conversación. No pongas precios (los pone el catálogo)."
)


def _tarifa_paciente(session: Session, paciente_id: int):
    return session.exec(select(PacienteTarifa.tarifa_id).where(
        PacienteTarifa.paciente_id == paciente_id, PacienteTarifa.activo == True)).first()  # noqa: E712


def _precio(session: Session, tarifa_id, trid) -> float:
    if not tarifa_id or not trid:
        return 0.0
    p = session.exec(select(TarifaPrecio.precio).where(
        TarifaPrecio.tarifa_id == tarifa_id, TarifaPrecio.tratamiento_id == trid)).first()
    return float(p or 0)


# Nº de raíces por posición FDI (2º dígito): 1-3 uni, 4-5 bi, 6-8 multi. Manda la posición, no el LLM.
_RADICULAR = {"1": "UNIRRADICULAR", "2": "UNIRRADICULAR", "3": "UNIRRADICULAR",
              "4": "BIRRADICULAR", "5": "BIRRADICULAR",
              "6": "MULTIRRADICULAR", "7": "MULTIRRADICULAR", "8": "MULTIRRADICULAR"}


def _forzar_radicular(nombre: str, pieza: str | None) -> str:
    """Fija el término de (re)endodoncia según la posición FDI de la pieza. Devuelve el nombre igual
    si no es una endodoncia o la pieza no es válida."""
    base = nombre.upper()
    if "ENDODONCIA" not in base:
        return nombre
    digitos = "".join(c for c in (pieza or "") if c.isdigit())
    if len(digitos) < 2 or digitos[1] not in _RADICULAR:
        return nombre
    raiz = "REENDODONCIA" if "REENDODONCIA" in base else "ENDODONCIA"
    return f"{raiz} {_RADICULAR[digitos[1]]}"


_CUADRANTE = {"1": "superior derecho", "2": "superior izquierdo", "3": "inferior izquierdo",
              "4": "inferior derecho", "5": "superior derecho", "6": "superior izquierdo",
              "7": "inferior izquierdo", "8": "inferior derecho"}
_POSICION = {"1": "incisivo central", "2": "incisivo lateral", "3": "canino", "4": "primer premolar",
             "5": "segundo premolar", "6": "primer molar", "7": "segundo molar", "8": "tercer molar"}
_POSICION_TEMPORAL = {"1": "incisivo central temporal", "2": "incisivo lateral temporal",
                      "3": "canino temporal", "4": "primer molar temporal", "5": "segundo molar temporal"}
_ANATOMIA = re.compile(r"incisiv|canin|premolar|molar|muela|colmillo|cordal|diente", re.I)


def _nombre_pieza(fdi: str) -> Optional[str]:
    """Nombre anatómico de una pieza FDI ('36' → 'primer molar inferior izquierdo'); None si
    el número no es una pieza (10, 19, 59…)."""
    if len(fdi) != 2 or fdi[0] not in _CUADRANTE:
        return None
    nombres = _POSICION_TEMPORAL if fdi[0] in "5678" else _POSICION
    pos = nombres.get(fdi[1])
    return f"{pos} {_CUADRANTE[fdi[0]]}" if pos else None


def nombrar_piezas(texto: str) -> str:
    """La anatomía de cada pieza la pone la numeración FDI, no el LLM (que llamaba al 36
    "molar superior derecho" en el WhatsApp al paciente). Dos casos:
      · marcador `[36]` → "primer molar inferior izquierdo (36)";
      · `36 (descripción anatómica)` → la descripción se sustituye por la correcta.
    Lo que no es una pieza válida o no describe un diente se deja como está."""
    def _marcador(m: re.Match) -> str:
        nombre = _nombre_pieza(m.group(1))
        return f"{nombre} ({m.group(1)})" if nombre else m.group(0)

    def _parentesis(m: re.Match) -> str:
        nombre = _nombre_pieza(m.group(1))
        if not nombre or not _ANATOMIA.search(m.group(2)):
            return m.group(0)
        return f"{m.group(1)} ({nombre})"

    texto = re.sub(r"\[(\d{2})\]", _marcador, texto or "")
    return re.sub(r"\b(\d{2}) \(([^()]{1,60})\)", _parentesis, texto)


def _alinear_radicular(texto: str, termino: Optional[str]) -> str:
    """Pone en el texto libre (plan, mensaje) el nº de raíces que fija la posición FDI,
    respetando mayúsculas/minúsculas. Sin término calculado no toca nada."""
    if not termino:
        return texto

    def _caso(m: re.Match) -> str:
        return termino.upper() if m.group(0).isupper() else termino.lower()

    return re.sub(r"(?i)\b(uni|bi|multi)rradicular\b", _caso, texto or "")


def escuchar_visita(session: Session, centro_id: int, paciente_id: int, texto: str) -> dict:
    """Escucha activa: de la conversación de la visita saca 4 BORRADORES (SOAP, líneas de
    presupuesto con su precio de tarifa, receta y mensaje de WhatsApp). NO guarda nada: el
    doctor revisa, corrige y decide qué se graba/envía."""
    cliente = LLMClient(_config_llm(session, centro_id))
    msg = cliente.chat(
        [{"role": "system", "content": SYSTEM_ESCUCHA},
         {"role": "user", "content": (texto or "").strip()[:12000]}],
        temperature=0.2, max_tokens=1200,
    )
    try:
        data: dict[str, Any] = json.loads(_solo_json(msg.get("content") or ""))
        if not isinstance(data, dict):
            raise ValueError("no es objeto")
    except Exception as e:  # raiz: parseo robusto: nunca 500, siempre fallback limpio
        raise LLMError(f"Respuesta LLM no parseable: {e}") from e

    soap_in = data.get("soap") if isinstance(data.get("soap"), dict) else {}
    soap = {k: str(soap_in.get(k) or "")[:3000] for k in ("subjetivo", "objetivo", "analisis", "plan")}

    tarifa_id = _tarifa_paciente(session, paciente_id)
    lineas = []
    for t in (data.get("tratamientos") or [])[:25]:
        if not isinstance(t, dict):
            continue
        nombre = str(t.get("texto") or "").strip()
        if len(nombre) < 2:
            continue
        pieza = str(t.get("pieza"))[:20] if t.get("pieza") else None
        nombre = _forzar_radicular(nombre, pieza)   # el nº de raíces lo manda la posición FDI, no el LLM
        trid = _resolver_tratamiento(session, centro_id, nombre)
        precio = _precio(session, tarifa_id, trid)
        lineas.append({
            "tratamiento": nombre, "tratamiento_id": trid,
            "pieza": pieza,
            # sin_precio: la tarifa del paciente no lo tiene → el doctor debe ponerlo, no 0 €
            "cantidad": 1, "precio": precio, "sin_precio": precio <= 0,
        })

    # Nº de raíces del texto libre (plan, mensaje) alineado con la posición FDI, solo si todas
    # las endodoncias del dictado apuntan al mismo (con varias distintas no se adivina cuál es cuál).
    terminos = {_RADICULAR[d[1]] for l in lineas if "ENDODONCIA" in l["tratamiento"].upper()
                for d in ["".join(c for c in (l["pieza"] or "") if c.isdigit())]
                if len(d) >= 2 and d[1] in _RADICULAR}
    termino = terminos.pop() if len(terminos) == 1 else None
    soap = {k: _alinear_radicular(nombrar_piezas(v), termino) for k, v in soap.items()}

    receta = []
    for r in (data.get("receta") or [])[:15]:
        if isinstance(r, dict) and str(r.get("medicamento") or "").strip():
            receta.append({
                "medicamento": str(r.get("medicamento"))[:200],
                "posologia": str(r.get("posologia") or "")[:300],
                "pauta": str(r.get("pauta") or "")[:300] if r.get("pauta") else None,
                "duracion": str(r.get("duracion") or "")[:60] if r.get("duracion") else None,
                "envases": int(r.get("envases")) if r.get("envases") else None,
                "unidades": int(r.get("unidades")) if r.get("unidades") else None,
            })

    pac = session.get(Paciente, paciente_id)
    return {"soap": soap, "presupuesto": lineas, "receta": receta,
            "mensaje": _alinear_radicular(nombrar_piezas(str(data.get("mensaje") or "")), termino)[:1500],
            "telefono": (pac.telefono_movil if pac else None)}


# ───────────────────────── GUARDAR (al confirmar los borradores) ─────────────────────────

# Estados que NO cuentan como "el paciente tiene cita hoy" (la cita no se hizo).
_ESTADOS_CAIDOS = ("anulada", "cancelada", "fallada")
_URGENCIA_MIN = 15


def _a_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _hhmm(minutos: int) -> str:
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def _hueco_urgencia(session: Session, centro_id: int, ahora: datetime) -> tuple[date, str]:
    """Dónde va la urgencia: «ahora» si cae dentro de un tramo del horario del centro (y cabe
    entera); si no, al final del último tramo ya pasado (hoy o días atrás) menos 15 min, para
    que quepa dentro del tramo. Sin horario configurado, «ahora»."""
    from datetime import timedelta
    from application.services.config_service import ConfigService
    dias = (ConfigService(session).resolve("centro.horario", centro_id=centro_id, default={}) or {}).get("dias") or []
    if not dias:
        return ahora.date(), ahora.strftime("%H:%M")

    def tramos(d: date) -> list[tuple[int, int]]:
        dia = dias[d.weekday()] if d.weekday() < len(dias) else None
        if not dia or not dia.get("abierto"):
            return []
        return [(_a_min(dia[a]), _a_min(dia[b])) for a, b in (("t1a", "t1b"), ("t2a", "t2b"))
                if dia.get(a) and dia.get(b)]

    m = ahora.hour * 60 + ahora.minute
    for t_ini, t_fin in tramos(ahora.date()):
        if t_ini <= m < t_fin:
            return ahora.date(), _hhmm(min(m, t_fin - _URGENCIA_MIN))
    for atras in range(0, 15):
        d = ahora.date() - timedelta(days=atras)
        pasados = [t_fin for _t_ini, t_fin in tramos(d) if atras > 0 or t_fin <= m]
        if pasados:
            return d, _hhmm(max(pasados) - _URGENCIA_MIN)
    return ahora.date(), ahora.strftime("%H:%M")


def _crear_urgencia(session: Session, centro_id: int, pac: Paciente) -> int:
    """Cita URGENCIA de 15 min, ya Finalizada, para colgar el SOAP de un paciente atendido sin
    cita. Pasa por las mismas reglas que cualquier cita (cita_reglas): el gabinete y el doctor
    salen del horario de colaboradores para ese hueco."""
    from domain.models.agenda import EstadoCita, TipoCita
    from application.services.cita_reglas import gabinete_y_doctor
    fecha, hora = _hueco_urgencia(session, centro_id, datetime.now())
    tipo = session.exec(select(TipoCita.id).where(TipoCita.centro_id == centro_id,
                                                   TipoCita.nombre == "Urgencia")).first()
    estado = session.exec(select(EstadoCita.id).where(EstadoCita.centro_id == centro_id,
                                                       EstadoCita.codigo == "finalizada")).first()
    gabinete_id, colaborador_id = gabinete_y_doctor(session, centro_id, fecha, hora, None, None)
    cita = Cita(centro_id=centro_id, paciente_id=pac.id, fecha=fecha, hora=hora,
                duracion_min=_URGENCIA_MIN, tipo_cita_id=tipo, estado_id=estado,
                gabinete_id=gabinete_id, colaborador_id=colaborador_id, confirmada=True,
                notas="Urgencia creada al guardar el SOAP (paciente atendido sin cita)")
    session.add(cita)
    session.flush()
    return cita.id


def guardar_soap(session: Session, centro_id: int, paciente_id: int, soap: dict) -> dict:
    """Graba el SOAP en la cita VIVA de hoy del paciente (1 SOAP por cita, se actualiza si ya
    existe). Si no la tiene (las anuladas/canceladas/falladas no cuentan), se crea una cita de
    URGENCIA de 15 min Finalizada y el SOAP se cuelga de ella (regla de jmd, 12-oct-2026)."""
    from domain.models.agenda import EstadoCita

    pac = session.get(Paciente, paciente_id)
    if not pac or pac.centro_id != centro_id:
        raise ValueError("Paciente no encontrado")

    caidos = select(EstadoCita.id).where(EstadoCita.centro_id == centro_id,
                                         EstadoCita.codigo.in_(_ESTADOS_CAIDOS))
    cita_id = session.exec(select(Cita.id).where(
        Cita.centro_id == centro_id, Cita.paciente_id == paciente_id, Cita.fecha == date.today(),
        (Cita.estado_id.is_(None)) | (Cita.estado_id.not_in(caidos))).order_by(Cita.id.desc())).first()
    if not cita_id:
        cita_id = _crear_urgencia(session, centro_id, pac)

    row = session.exec(select(Soap).where(Soap.cita_id == cita_id)).first()
    campos = {k: (str(soap.get(k) or "")[:4000] or None) for k in ("subjetivo", "objetivo", "analisis", "plan")}
    if row:
        for k, v in campos.items():
            setattr(row, k, v)
    else:
        row = Soap(cita_id=cita_id, paciente_id=paciente_id, **campos)
        session.add(row)
    session.commit(); session.refresh(row)
    return {"ok": True, "soap_id": row.id, "cita_id": cita_id}


def guardar_receta(session: Session, centro_id: int, usuario_id: int, paciente_id: int,
                   medicamentos: list[dict], diagnostico: str | None = None,
                   instrucciones: str | None = None, urgencia: bool = False,
                   desabastecimiento: bool = False, motivo_sustitucion: str | None = None) -> dict:
    """Crea una receta con sus líneas (farmaco, posologia, pauta, duracion, envases, unidades)."""
    pac = session.get(Paciente, paciente_id)
    if not pac or pac.centro_id != centro_id:
        raise ValueError("Paciente no encontrado")
    meds = [m for m in medicamentos if isinstance(m, dict) and str(m.get("medicamento") or "").strip()]
    if not meds:
        raise ValueError("La receta no tiene medicamentos")
    col = _colaborador(session, usuario_id)
    if col is None:
        raise ValueError("El usuario no tiene colaborador asociado (no se puede emitir una receta)")
    colaborador = session.get(Colaborador, col)
    if not colaborador or not colaborador.talonario_id:
        raise ValueError("El doctor no tiene un talonario de recetas subido en su perfil")
    numero = session.exec(select(TalonarioReceta).where(
        TalonarioReceta.talonario_id == colaborador.talonario_id,
        TalonarioReceta.usada == False,  # noqa: E712
    ).order_by(TalonarioReceta.id).limit(1)).first()
    if not numero:
        raise ValueError("El talonario del doctor no tiene números libres; sube uno nuevo")
    numero.usada = True
    numero.usada_at = datetime.now()
    session.add(numero)

    rec = Receta(centro_id=centro_id, paciente_id=paciente_id, colaborador_id=col,
                 fecha=date.today(), diagnostico=(diagnostico or None),
                 notas=(instrucciones or None), notas_farmaceutico=(motivo_sustitucion or None),
                 urgencia=bool(urgencia), desabastecimiento=bool(desabastecimiento),
                 talonario_receta_id=numero.id, cve=numero.cve)
    session.add(rec); session.flush()
    for i, m in enumerate(meds, start=1):
        session.add(RecetaLinea(
            receta_id=rec.id,
            farmaco=str(m.get("medicamento"))[:200],
            posologia=(str(m.get("posologia"))[:300] if m.get("posologia") else None),
            pauta=(str(m.get("pauta"))[:300] if m.get("pauta") else None),
            duracion=(str(m.get("duracion"))[:60] if m.get("duracion") else None),
            envases=(int(m.get("envases")) if m.get("envases") else None),
            unidades=(int(m.get("unidades")) if m.get("unidades") else None),
            orden_dispensacion=i
        ))
    session.commit()

    # Archivar el PDF de verdad (igual que consentimientos/documentos): se guarda en
    # media/recetas/ y se enlaza en Receta.archivo_url — nunca solo "generado al vuelo".
    try:
        centro = session.get(Centro, centro_id)
        usu_col = session.get(Colaborador, col)
        from domain.models.identidad import Usuario, UsuarioPeriodo
        periodo = session.get(UsuarioPeriodo, usu_col.periodo_id) if usu_col else None
        usuario = session.get(Usuario, periodo.usuario_id) if periodo else None
        prescriptor_nombre = f"{usuario.nombre or ''} {usuario.apellidos or ''}".strip() if usuario else "—"
        lineas_rec = session.exec(select(RecetaLinea).where(RecetaLinea.receta_id == rec.id)
                                  .order_by(RecetaLinea.orden_dispensacion)).all()
        pdf = generar_receta_pdf(
            numero_receta=numero.numero, cve=numero.cve,
            paciente_nombre=f"{pac.nombre or ''} {pac.apellidos or ''}".strip(),
            paciente_fecha_nac=pac.fecha_nacimiento.strftime("%d/%m/%Y") if pac.fecha_nacimiento else "",
            paciente_nif=pac.nif or "",
            prescriptor_nombre=prescriptor_nombre,
            num_colegiado=(usu_col.num_colegiado if usu_col else None) or "—",
            centro_direccion=(centro.direccion if centro else "") or "",
            centro_poblacion=(f"{centro.cp or ''} {centro.poblacion or ''}".strip() if centro else ""),
            fecha_prescripcion=rec.fecha, diagnostico=rec.diagnostico or "",
            instrucciones=rec.notas or "", urgencia=rec.urgencia, desabastecimiento=rec.desabastecimiento,
            motivo_sustitucion=rec.notas_farmaceutico or "",
            lineas=[{
                "medicamento": ln.farmaco, "envases": ln.envases, "duracion": ln.duracion,
                "unidades": ln.unidades, "pauta": ln.pauta, "orden": ln.orden_dispensacion,
            } for ln in lineas_rec],
        )
        _MEDIA_RECETAS.mkdir(parents=True, exist_ok=True)
        (_MEDIA_RECETAS / f"receta_{rec.id}.pdf").write_bytes(pdf)
        rec.archivo_url = f"/media/recetas/receta_{rec.id}.pdf"
        session.add(rec); session.commit()
    except Exception:  # raiz: la receta ya es válida en BD aunque el PDF falle
        pass

    return {"ok": True, "receta_id": rec.id, "n": len(meds)}
