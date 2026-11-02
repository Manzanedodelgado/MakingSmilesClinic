"""Puerto de TRANSCRIPCIÓN (voz → texto) para Aura.

Por qué es un puerto y no una llamada directa a un proveedor: el motor de voz es la pieza
más volátil de todo el área de IAs. Depende de la ley (el audio de una consulta es dato de
salud, art. 9 RGPD), del hardware (hoy no hay GPU) y del precio. Atar Aura a un proveedor
concreto sería repetir el error que acabamos de pagar: cuando NVIDIA retiró un modelo, toda
la IA de texto murió sin aviso porque el proveedor estaba incrustado en la config.

Aquí sólo se define QUÉ tiene que saber hacer un motor de voz. Los adaptadores concretos
(nube, local con GPU, el que venga) viven en `infrastructure/external_apis/` y se eligen por
configuración. Cambiar de motor no debe tocar ni una línea de Aura.

MEDICIÓN QUE JUSTIFICA ESTE DISEÑO (24-jul-2026, en esta máquina, 4 CPU sin GPU):
    faster-whisper `base`, voz real en español → 99 s de audio en 795 s  = x0,1 tiempo real
    → una consulta de 20 min tardaría 3,3 HORAS. El local aquí NO es viable.
    (Mediciones previas de x1,4 y x11,9 eran falsas: audio de tono sin voz, y el VAD lo
     descartaba entero. Se repitió con voz real y el resultado se desplomó.)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass
class Transcripcion:
    """Lo que devuelve un motor de voz."""
    texto: str
    idioma: str = "es"
    duracion_seg: float = 0.0
    motor: str = ""
    # Cada tramo con su marca de tiempo: permite volver al audio y comprobar qué se dijo.
    tramos: list[dict] = field(default_factory=list)


class MotorTranscripcion(Protocol):
    """Contrato mínimo de un motor de voz."""

    nombre: str
    #: ¿el audio sale de la clínica? Aura lo advierte en pantalla y queda en la auditoría.
    envia_fuera: bool

    def disponible(self) -> tuple[bool, str]:
        """(listo, motivo). `motivo` legible cuando no lo está."""
        ...

    def transcribir(self, audio: bytes, *, nombre_archivo: str = "consulta.wav",
                    idioma: str = "es", contexto: Optional[str] = None) -> Transcripcion:
        """Pasa el audio a texto.

        `contexto` es vocabulario para orientar al motor (nombres de tratamientos, piezas
        dentales, apellidos del paciente): sube mucho el acierto en jerga clínica."""
        ...
