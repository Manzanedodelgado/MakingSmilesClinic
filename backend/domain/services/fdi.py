"""Nomenclatura FDI → nombre del diente en lenguaje claro. Determinista: la anatomía no la decide el LLM."""
from typing import Optional

_LADO = {1: ("superior", "derecho"), 2: ("superior", "izquierdo"), 3: ("inferior", "izquierdo"), 4: ("inferior", "derecho")}
_PERMANENTE = {1: "incisivo central", 2: "incisivo lateral", 3: "canino", 4: "primer premolar",
               5: "segundo premolar", 6: "primer molar", 7: "segundo molar", 8: "tercer molar (muela del juicio)"}
_TEMPORAL = {1: "incisivo central de leche", 2: "incisivo lateral de leche", 3: "canino de leche",
             4: "primer molar de leche", 5: "segundo molar de leche"}


def nombre_pieza(pieza: object) -> Optional[str]:
    """'36' → 'primer molar inferior izquierdo'. None si no es una pieza FDI válida."""
    s = str(pieza or "").strip()
    if len(s) != 2 or not s.isdigit():
        return None
    c, n = int(s[0]), int(s[1])
    if 1 <= c <= 4 and n in _PERMANENTE:
        tipo, (arcada, lado) = _PERMANENTE[n], _LADO[c]
    elif 5 <= c <= 8 and n in _TEMPORAL:
        tipo, (arcada, lado) = _TEMPORAL[n], _LADO[c - 4]
    else:
        return None
    if tipo.endswith(")"):
        base, extra = tipo.split(" (", 1)
        return f"{base} {arcada} {lado} ({extra}"
    return f"{tipo} {arcada} {lado}"
