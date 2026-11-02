"""Cefalometría — motor de geometría del análisis de Steiner.

Calcula las medidas cefalométricas A PARTIR DE LOS LANDMARKS (puntos que el doctor coloca sobre
la telerradiografía lateral), no de valores tecleados. Los ÁNGULOS son invariantes de escala (no
necesitan calibración); las medidas LINEALES (mm) solo se calculan si hay calibración (2 puntos de
distancia conocida). Todo determinista y unit-verificable — el LLM no interviene aquí.

Sistema de coordenadas: píxeles de imagen (x derecha, y ABAJO, como en pantalla/SVG).
"""
from __future__ import annotations

import math
from typing import Optional

Punto = tuple[float, float]

# ── Definición del análisis de Steiner: landmarks a colocar (orden guiado) + normas ──
LANDMARKS_STEINER: list[dict] = [
    {"code": "S", "label": "Silla (Sella)", "hint": "Centro de la silla turca"},
    {"code": "N", "label": "Nasion", "hint": "Punto más anterior de la sutura frontonasal"},
    {"code": "A", "label": "Punto A (Subespinal)", "hint": "Concavidad máxima del maxilar superior"},
    {"code": "B", "label": "Punto B (Supramental)", "hint": "Concavidad máxima de la sínfisis mandibular"},
    {"code": "Go", "label": "Gonion", "hint": "Punto más posteroinferior del ángulo mandibular"},
    {"code": "Gn", "label": "Gnation", "hint": "Punto más anteroinferior de la sínfisis"},
    {"code": "U1T", "label": "Borde incisivo superior", "hint": "Punta del incisivo central superior"},
    {"code": "U1A", "label": "Ápice incisivo superior", "hint": "Ápice radicular del incisivo superior"},
    {"code": "L1T", "label": "Borde incisivo inferior", "hint": "Punta del incisivo central inferior"},
    {"code": "L1A", "label": "Ápice incisivo inferior", "hint": "Ápice radicular del incisivo inferior"},
]

# Normas (media, desviación) del análisis de Steiner. Unidad ° salvo las mm.
NORMAS_STEINER: dict[str, dict] = {
    "SNA": {"media": 82.0, "sd": 2.0, "unidad": "°", "label": "SNA"},
    "SNB": {"media": 80.0, "sd": 2.0, "unidad": "°", "label": "SNB"},
    "ANB": {"media": 2.0, "sd": 2.0, "unidad": "°", "label": "ANB"},
    "SN_GoGn": {"media": 32.0, "sd": 5.0, "unidad": "°", "label": "SN-GoGn (plano mandibular)"},
    "U1_NA_ang": {"media": 22.0, "sd": 4.0, "unidad": "°", "label": "Incisivo sup. / NA"},
    "U1_NA_mm": {"media": 4.0, "sd": 2.0, "unidad": "mm", "label": "Incisivo sup. a NA"},
    "L1_NB_ang": {"media": 25.0, "sd": 4.0, "unidad": "°", "label": "Incisivo inf. / NB"},
    "L1_NB_mm": {"media": 4.0, "sd": 2.0, "unidad": "mm", "label": "Incisivo inf. a NB"},
    "interincisal": {"media": 131.0, "sd": 6.0, "unidad": "°", "label": "Ángulo interincisal"},
}


# ── Análisis de Ricketts (subconjunto clínico bien definido) ──
LANDMARKS_RICKETTS: list[dict] = [
    {"code": "Po", "label": "Porion", "hint": "Punto más superior del conducto auditivo externo"},
    {"code": "Or", "label": "Orbitale", "hint": "Punto más inferior del reborde orbitario"},
    {"code": "N", "label": "Nasion", "hint": "Sutura frontonasal"},
    {"code": "A", "label": "Punto A (Subespinal)", "hint": "Concavidad máxima del maxilar"},
    {"code": "Pog", "label": "Pogonion", "hint": "Punto más anterior de la sínfisis"},
    {"code": "Go", "label": "Gonion", "hint": "Punto posteroinferior del ángulo mandibular"},
    {"code": "Me", "label": "Mentoniano (Menton)", "hint": "Punto más inferior de la sínfisis"},
    {"code": "Ba", "label": "Basion", "hint": "Punto más anteroinferior del foramen magno"},
    {"code": "Pt", "label": "Punto Pt (Pterigoideo)", "hint": "Techo posterosuperior de la fisura pterigomaxilar"},
    {"code": "Gn", "label": "Gnation", "hint": "Punto anteroinferior de la sínfisis"},
    {"code": "L1T", "label": "Borde incisivo inferior", "hint": "Punta del incisivo central inferior"},
    {"code": "L1A", "label": "Ápice incisivo inferior", "hint": "Ápice radicular del incisivo inferior"},
]

NORMAS_RICKETTS: dict[str, dict] = {
    "profundidad_facial": {"media": 87.0, "sd": 3.0, "unidad": "°", "label": "Profundidad facial (FH·N-Pog)"},
    "eje_facial": {"media": 90.0, "sd": 3.0, "unidad": "°", "label": "Eje facial (Ba-N·Pt-Gn)"},
    "plano_mandibular_FMA": {"media": 26.0, "sd": 4.0, "unidad": "°", "label": "Plano mandibular (FH·Go-Me)"},
    "convexidad_A_mm": {"media": 2.0, "sd": 2.0, "unidad": "mm", "label": "Convexidad (A a N-Pog)"},
    "L1_APog_mm": {"media": 1.0, "sd": 2.0, "unidad": "mm", "label": "Incisivo inf. a A-Pog"},
    "L1_APog_ang": {"media": 22.0, "sd": 4.0, "unidad": "°", "label": "Incisivo inf. / A-Pog"},
}

# Registro de análisis disponibles → (landmarks, normas, función analizadora)
ANALISIS: dict[str, dict] = {}


# ── primitivas geométricas ──
def _v(a: Punto, b: Punto) -> Punto:
    return (b[0] - a[0], b[1] - a[1])


def _ang_vectores(u: Punto, v: Punto) -> float:
    """Ángulo (grados, 0..180) entre dos vectores."""
    du = math.hypot(*u); dv = math.hypot(*v)
    if du == 0 or dv == 0:
        return float("nan")
    cos = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (du * dv)))
    return math.degrees(math.acos(cos))


def _ang_en(vertice: Punto, p1: Punto, p2: Punto) -> float:
    """Ángulo en `vertice` del triángulo vertice-p1-p2."""
    return _ang_vectores(_v(vertice, p1), _v(vertice, p2))


def _ang_lineas(a: Punto, b: Punto, c: Punto, d: Punto) -> float:
    """Ángulo agudo/obtuso (0..180) entre la recta a-b y la recta c-d."""
    return _ang_vectores(_v(a, b), _v(c, d))


def _agudo(x: float) -> float:
    """Ángulo entre RECTAS (sin dirección): la inclinación se reporta como el agudo (≤90)."""
    if math.isnan(x):
        return x
    return min(x, 180.0 - x)


def _dist_punto_recta(p: Punto, a: Punto, b: Punto) -> float:
    """Distancia perpendicular (px, con signo por el lado) del punto p a la recta a-b."""
    ab = _v(a, b); ap = _v(a, p)
    d = math.hypot(*ab)
    if d == 0:
        return 0.0
    cross = ab[0] * ap[1] - ab[1] * ap[0]
    return cross / d


def _px_por_mm(calibracion: Optional[dict]) -> Optional[float]:
    """De {p1:[x,y], p2:[x,y], mm} → px/mm. None si falta o es inválida."""
    if not calibracion:
        return None
    try:
        p1 = tuple(calibracion["p1"]); p2 = tuple(calibracion["p2"]); mm = float(calibracion["mm"])
        d = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        return d / mm if mm > 0 and d > 0 else None
    except (KeyError, TypeError, ValueError):
        return None


def _round(x: Optional[float], n: int = 1) -> Optional[float]:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(x, n)


def analizar_steiner(landmarks: dict, calibracion: Optional[dict] = None) -> dict:
    """Devuelve {mediciones:{code:{valor,norma,unidad,label,desviacion}}, interpretacion:{...}}.

    Cada medida se calcula solo si están sus landmarks; si no, se omite (no se inventa).
    """
    P: dict[str, Punto] = {}
    for k, v in (landmarks or {}).items():
        try:
            P[k] = (float(v[0]), float(v[1]))
        except (TypeError, ValueError, IndexError):
            continue

    ppm = _px_por_mm(calibracion)
    m: dict[str, Optional[float]] = {}

    if {"S", "N", "A"} <= P.keys():
        m["SNA"] = _ang_en(P["N"], P["S"], P["A"])
    if {"S", "N", "B"} <= P.keys():
        m["SNB"] = _ang_en(P["N"], P["S"], P["B"])
    if m.get("SNA") is not None and m.get("SNB") is not None:
        m["ANB"] = m["SNA"] - m["SNB"]
    if {"S", "N", "Go", "Gn"} <= P.keys():
        m["SN_GoGn"] = _ang_lineas(P["S"], P["N"], P["Go"], P["Gn"])
    if {"U1T", "U1A", "N", "A"} <= P.keys():
        m["U1_NA_ang"] = _agudo(_ang_lineas(P["U1A"], P["U1T"], P["N"], P["A"]))
        if ppm:
            m["U1_NA_mm"] = abs(_dist_punto_recta(P["U1T"], P["N"], P["A"])) / ppm
    if {"L1T", "L1A", "N", "B"} <= P.keys():
        m["L1_NB_ang"] = _agudo(_ang_lineas(P["L1A"], P["L1T"], P["N"], P["B"]))
        if ppm:
            m["L1_NB_mm"] = abs(_dist_punto_recta(P["L1T"], P["N"], P["B"])) / ppm
    if {"U1T", "U1A", "L1T", "L1A"} <= P.keys():
        m["interincisal"] = _ang_vectores(_v(P["U1T"], P["U1A"]), _v(P["L1T"], P["L1A"]))

    return {"mediciones": _mediciones_dto(m, NORMAS_STEINER),
            "interpretacion": _interpretar(m), "calibrada": ppm is not None}


def analizar_ricketts(landmarks: dict, calibracion: Optional[dict] = None) -> dict:
    """Subconjunto clínico de Ricketts. Ángulos sin calibración; distancias (mm) solo con ella."""
    P: dict[str, Punto] = {}
    for k, v in (landmarks or {}).items():
        try:
            P[k] = (float(v[0]), float(v[1]))
        except (TypeError, ValueError, IndexError):
            continue
    ppm = _px_por_mm(calibracion)
    m: dict[str, Optional[float]] = {}

    if {"Po", "Or", "N", "Pog"} <= P.keys():
        m["profundidad_facial"] = _agudo(_ang_lineas(P["Po"], P["Or"], P["N"], P["Pog"]))
    if {"Ba", "N", "Pt", "Gn"} <= P.keys():
        m["eje_facial"] = _ang_lineas(P["Ba"], P["N"], P["Pt"], P["Gn"])
    if {"Po", "Or", "Go", "Me"} <= P.keys():
        m["plano_mandibular_FMA"] = _agudo(_ang_lineas(P["Po"], P["Or"], P["Go"], P["Me"]))
    if {"A", "N", "Pog"} <= P.keys() and ppm:
        m["convexidad_A_mm"] = _dist_punto_recta(P["A"], P["N"], P["Pog"]) / ppm
    if {"L1T", "A", "Pog"} <= P.keys() and ppm:
        m["L1_APog_mm"] = _dist_punto_recta(P["L1T"], P["A"], P["Pog"]) / ppm
    if {"L1T", "L1A", "A", "Pog"} <= P.keys():
        m["L1_APog_ang"] = _agudo(_ang_lineas(P["L1A"], P["L1T"], P["A"], P["Pog"]))

    return {"mediciones": _mediciones_dto(m, NORMAS_RICKETTS),
            "interpretacion": _interpretar_ricketts(m), "calibrada": ppm is not None}


def _mediciones_dto(m: dict, normas: dict) -> dict:
    """Empaqueta {code: valor} + normas en {code: {valor, label, norma, sd, unidad, desviacion}}."""
    out = {}
    for code, valor in m.items():
        norma = normas.get(code, {})
        media = norma.get("media")
        val = _round(valor)
        # La norma es opcional (una medida a medida puede no tenerla) → sin norma no hay desviación.
        desv = _round(val - media) if (val is not None and media is not None) else None
        out[code] = {
            "valor": val, "label": norma.get("label", code),
            "norma": media, "sd": norma.get("sd"),
            "unidad": norma.get("unidad", "°"), "desviacion": desv,
        }
    return out


def _interpretar_ricketts(m: dict) -> dict:
    """Patrón por eje facial y plano mandibular; clase por convexidad de A."""
    out: dict[str, Optional[str]] = {"clase": None, "patron": None}
    conv = m.get("convexidad_A_mm")
    if conv is not None and not math.isnan(conv):
        if conv > 4:
            out["clase"] = "II (perfil convexo)"
        elif conv < 0:
            out["clase"] = "III (perfil cóncavo)"
        else:
            out["clase"] = "I (perfil recto)"
    eje = m.get("eje_facial")
    fma = m.get("plano_mandibular_FMA")
    if fma is not None and not math.isnan(fma):
        if fma > 30:
            out["patron"] = "dolicofacial (crecimiento vertical)"
        elif fma < 22:
            out["patron"] = "braquifacial (crecimiento horizontal)"
        else:
            out["patron"] = "mesofacial"
    elif eje is not None and not math.isnan(eje):
        out["patron"] = "dolicofacial" if eje < 87 else ("braquifacial" if eje > 93 else "mesofacial")
    return out


def analizar(analisis: str, landmarks: dict, calibracion: Optional[dict] = None) -> Optional[dict]:
    """Dispatcher por nombre de análisis. None si no existe."""
    fn = ANALISIS.get(analisis, {}).get("fn")
    return fn(landmarks, calibracion) if fn else None


# ── Análisis DEFINIDO por el usuario (constructor a medida) ──
# Tipos de medida soportados (fórmula geométrica sobre los códigos de landmark en `puntos`):
#   angulo3     [v, a, b]        → ángulo en el vértice v entre v→a y v→b
#   lineas      [a, b, c, d]     → ángulo AGUDO entre la recta a-b y la recta c-d (inclinación)
#   distancia   [a, b]           → distancia a-b en mm (requiere calibración)
#   perpendicular [p, a, b]      → distancia con signo de p a la recta a-b en mm (requiere calibración)
TIPOS_MEDIDA = {"angulo3", "lineas", "distancia", "perpendicular"}


def analizar_definido(medidas_def: list[dict], landmarks: dict,
                      calibracion: Optional[dict] = None) -> dict:
    """Calcula un análisis a medida a partir de sus fórmulas. Una medida se omite si le faltan
    landmarks o calibración (mm). Nunca lanza."""
    P: dict[str, Punto] = {}
    for k, v in (landmarks or {}).items():
        try:
            P[k] = (float(v[0]), float(v[1]))
        except (TypeError, ValueError, IndexError):
            continue
    ppm = _px_por_mm(calibracion)
    normas: dict[str, dict] = {}
    m: dict[str, Optional[float]] = {}

    for d in medidas_def or []:
        code = str(d.get("code") or "").strip()
        tipo = d.get("tipo")
        pts = d.get("puntos") or []
        if not code or tipo not in TIPOS_MEDIDA:
            continue
        unidad = "mm" if tipo in ("distancia", "perpendicular") else "°"
        normas[code] = {"media": d.get("norma"), "sd": d.get("sd"),
                        "unidad": unidad, "label": d.get("label") or code}
        if not all(c in P for c in pts):
            continue
        try:
            if tipo == "angulo3" and len(pts) == 3:
                m[code] = _ang_en(P[pts[0]], P[pts[1]], P[pts[2]])
            elif tipo == "lineas" and len(pts) == 4:
                m[code] = _agudo(_ang_lineas(P[pts[0]], P[pts[1]], P[pts[2]], P[pts[3]]))
            elif tipo == "distancia" and len(pts) == 2 and ppm:
                m[code] = _dist(P[pts[0]], P[pts[1]]) / ppm
            elif tipo == "perpendicular" and len(pts) == 3 and ppm:
                m[code] = _dist_punto_recta(P[pts[0]], P[pts[1]], P[pts[2]]) / ppm
        except (KeyError, ZeroDivisionError):
            continue

    return {"mediciones": _mediciones_dto(m, normas), "interpretacion": {"clase": None, "patron": None},
            "calibrada": ppm is not None}


def _dist(a: Punto, b: Punto) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


# Registro de análisis disponibles (nombre → landmarks guiados, normas, analizador).
ANALISIS.update({
    "steiner": {"label": "Steiner", "landmarks": LANDMARKS_STEINER, "normas": NORMAS_STEINER, "fn": analizar_steiner},
    "ricketts": {"label": "Ricketts", "landmarks": LANDMARKS_RICKETTS, "normas": NORMAS_RICKETTS, "fn": analizar_ricketts},
})


def _interpretar(m: dict) -> dict:
    """Clase esquelética (ANB) y patrón de crecimiento (SN-GoGn), en lenguaje clínico."""
    out: dict[str, Optional[str]] = {"clase": None, "patron": None}
    anb = m.get("ANB")
    if anb is not None and not math.isnan(anb):
        if anb > 4:
            out["clase"] = "II (retrognatismo mandibular relativo)"
        elif anb < 0:
            out["clase"] = "III (prognatismo mandibular relativo)"
        else:
            out["clase"] = "I (relación esquelética normal)"
    mp = m.get("SN_GoGn")
    if mp is not None and not math.isnan(mp):
        if mp > 37:
            out["patron"] = "hiperdivergente (dolicofacial)"
        elif mp < 27:
            out["patron"] = "hipodivergente (braquifacial)"
        else:
            out["patron"] = "normodivergente (mesofacial)"
    return out
