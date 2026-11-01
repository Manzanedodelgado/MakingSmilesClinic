"""Cliente del servicio ia-dental (numeracion FDI + impactados, canal dentario inferior y seno maxilar).
Solo sugerencias: el doctor valida. Si el servicio no responde, devuelve error controlado (nunca rompe la ficha)."""
import os

import httpx

IA_DENTAL_URL = os.environ.get("IA_DENTAL_URL", "")
TIMEOUT = float(os.environ.get("IA_DENTAL_TIMEOUT", "120"))


class IaDentalNoDisponible(Exception):
    pass


def analizar_ortopantomografia(contenido: bytes, nombre: str = "rx.jpg") -> dict:
    if not IA_DENTAL_URL:
        raise IaDentalNoDisponible("Servicio de IA no configurado")
    try:
        r = httpx.post(f"{IA_DENTAL_URL}/analizar", files={"file": (nombre, contenido)}, timeout=TIMEOUT)
        r.raise_for_status()
        return depurar_respuesta(r.json())
    except httpx.HTTPError as e:
        raise IaDentalNoDisponible(f"Servicio de IA no disponible ({type(e).__name__})") from e


# ───────────── Depuración de la numeración FDI ─────────────
# El detector da a veces un mismo diente con dos números, números fuera de orden dentro de su cuadrante o de la
# arcada contraria. Se descartan SOLO esas contradicciones (con reglas objetivas): no se «corrige» ningún número,
# no se inventan piezas. El doctor sigue validando todo.
IOU_MAX = 0.5


def _iou(a: list, b: list) -> float:
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _cx(d: dict) -> float:
    return (d["bbox"][0] + d["bbox"][2]) / 2


def _cy(d: dict) -> float:
    return (d["bbox"][1] + d["bbox"][3]) / 2


def _permanente(d: dict) -> bool:
    f = str(d.get("fdi", ""))
    return len(f) == 2 and f[0] in "1234" and f[1] in "12345678"


def depurar_numeracion(dientes: list) -> tuple[list, list]:
    """→ (dientes depurados, [(fdi, motivo)]). Cada paso quita lo de menor confianza de cada contradicción."""
    out = [d for d in dientes if _permanente(d)]
    quitados: list = [(d.get("fdi"), "no es una pieza permanente") for d in dientes if not _permanente(d)]

    def quitar(d: dict, motivo: str) -> None:
        if d in out:
            out.remove(d)
            quitados.append((d["fdi"], motivo))

    # 1) mismo diente con dos números: cajas casi iguales → se queda la de mayor confianza
    for a in sorted(list(out), key=lambda d: d.get("conf", 0), reverse=True):
        if a not in out:
            continue
        for b in list(out):
            if b is not a and _iou(a["bbox"], b["bbox"]) > IOU_MAX:
                perdedor, ganador = (b, a) if b.get("conf", 0) <= a.get("conf", 0) else (a, b)
                quitar(perdedor, f"se solapa con la {ganador['fdi']}")
    # 2) arcada: las piezas 1x/2x deben quedar por encima de las 3x/4x
    sup = [d for d in out if d["fdi"][0] in "12"]
    inf = [d for d in out if d["fdi"][0] in "34"]
    if sup and inf:
        corte = (sum(_cy(d) for d in sup) / len(sup) + sum(_cy(d) for d in inf) / len(inf)) / 2
        for d in list(out):
            if (d["fdi"][0] in "12" and _cy(d) > corte) or (d["fdi"][0] in "34" and _cy(d) < corte):
                quitar(d, "arcada contraria a su posición")
    # 3) orden dentro del cuadrante: el número crece alejándose de la línea media.
    #    Cuadrantes 1 y 4 están a la izquierda de la imagen (x decrece al crecer el número); 2 y 3, a la derecha.
    for q in "1234":
        sentido = -1 if q in "14" else 1
        while True:
            qs = sorted([d for d in out if d["fdi"][0] == q], key=lambda d: int(d["fdi"][1]))
            malos = [(a, b) for a, b in zip(qs, qs[1:]) if sentido * (_cx(b) - _cx(a)) <= 0]
            if not malos:
                break
            a, b = malos[0]
            quitar(a if a.get("conf", 0) < b.get("conf", 0) else b, f"orden imposible en el cuadrante {q}")
    return out, quitados


def depurar_respuesta(r: dict) -> dict:
    """Aplica depurar_numeracion a la respuesta del servicio y deja constancia en `errores` (se muestra al doctor)."""
    if not isinstance(r, dict) or not isinstance(r.get("dientes"), list):
        return r
    limpios, quitados = depurar_numeracion(r["dientes"])
    if quitados:
        r = dict(r)
        r["dientes"] = limpios
        r["errores"] = list(r.get("errores") or []) + [
            "Números descartados por incoherentes: " + ", ".join(f"{f} ({m})" for f, m in quitados)]
    return r
