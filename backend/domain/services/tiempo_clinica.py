"""Hora local de la clínica.

El contenedor corre en UTC (y así deben quedarse las marcas que se guardan en la base de
datos). Pero hay decisiones y textos que se rigen por la hora que ve la clínica: la ventana
horaria de los envíos automáticos, el sello de los documentos que lee el paciente, los
horarios de las citas. Compararlos contra `datetime.now()` los desplaza 2 horas en verano
y 1 en invierno.

Regla: si el dato se GUARDA, va en UTC. Si lo LEE una persona o se compara con un horario
de la clínica (`citas.hora`, ventanas 8-21), se usa `ahora_clinica()`.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

TZ_CLINICA = ZoneInfo("Europe/Madrid")


def ahora_clinica() -> datetime:
    """Hora local de la clínica, naive (comparable con las cadenas 'HH:MM' de las citas)."""
    return datetime.now(TZ_CLINICA).replace(tzinfo=None)
