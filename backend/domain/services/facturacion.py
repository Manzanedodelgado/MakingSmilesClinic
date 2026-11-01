"""Reglas de facturación de actos clínicos (dominio).

`facturado_al_doctor` vivía en api/clinico_router.py (M07) y lo importaba
api/pacientes_router.py (M03): dependencia cruzada M03→M07. Extraída aquí para que
ambos consuman la misma regla sin arrastrar el router de clínica.
"""
from datetime import date
from typing import Optional


def facturado_al_doctor(f: Optional[date]) -> bool:
    """Regla del centro: el día 10 de cada mes se facturan al doctor los actos del mes
    ANTERIOR. Un acto del mes M queda facturado al llegar el día 10 del mes M+1."""
    if not f:
        return False
    ny, nm = (f.year + 1, 1) if f.month == 12 else (f.year, f.month + 1)
    return date.today() >= date(ny, nm, 10)
