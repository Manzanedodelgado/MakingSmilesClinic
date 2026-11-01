"""Normalización de teléfonos (dominio).

Port del phone.ts de la .37 a Python. Regla ES: 9 dígitos → prefijo 34.
`ultimos9` se usa para casar contra los teléfonos del paciente sin depender del
prefijo guardado (+34, 0034 o sin prefijo) — comparación por igualdad, NUNCA por
subcadena (el bug de la .37 que casaba '648085696' dentro de '999648085696').
"""
import re


def normalizar(telefono: str) -> str:
    """A E.164 sin '+': dígitos, quita 00 inicial, antepone 34 si son 9 dígitos."""
    d = re.sub(r"\D", "", telefono or "")
    if d.startswith("00"):
        d = d[2:]
    if len(d) == 9:
        d = "34" + d
    return d


def ultimos9(telefono: str) -> str:
    """Últimos 9 dígitos (el número nacional), para casar contra fichas."""
    return re.sub(r"\D", "", telefono or "")[-9:]


def en_lista(telefono_digits: str, allowlist: list[str]) -> bool:
    """¿El teléfono está en la allowlist? Compara con/sin prefijo 34."""
    if not allowlist:
        return False
    return any(
        telefono_digits == a or telefono_digits == "34" + a or "34" + telefono_digits == a
        for a in (re.sub(r"\D", "", x) for x in allowlist if x)
    )
