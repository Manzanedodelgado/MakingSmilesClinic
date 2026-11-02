"""Alcanzar la MÁQUINA ANFITRIONA desde dentro del contenedor (infraestructura).

Hace falta porque no todo vive en Docker: la web que ve la clínica es un proceso
del host (Next.js bajo systemd, ver ~/.config/systemd/user/makingsmiles-web.service),
así que para vigilarla el backend tiene que salir del contenedor.

Se resuelve leyendo la puerta de enlace por defecto de /proc/net/route en vez de
fijar una IP a mano: la subred del bridge de Docker cambia sola al recrear el
stack, y un `172.20.0.1` hardcodeado dejaría la vigilancia ciega en silencio el
día que cambie. Tampoco se usa `host.docker.internal`: exige `extra_hosts` en el
compose, es decir recrear el contenedor del backend — y esto tiene que poder
añadirse sin cortarle el servicio a una clínica en marcha.
"""
_CACHE: str | None = None
_POR_DEFECTO = "172.17.0.1"   # bridge por defecto de Docker, último recurso


def host_gateway() -> str:
    """IP de la máquina anfitriona vista desde este contenedor."""
    global _CACHE
    if _CACHE:
        return _CACHE
    try:
        with open("/proc/net/route") as f:
            for linea in f.readlines()[1:]:
                campos = linea.split()
                # campos[1] = destino; 00000000 = ruta por defecto. campos[2] = gateway,
                # hex little-endian (p.ej. "010014AC" → 172.20.0.1).
                if len(campos) > 2 and campos[1] == "00000000":
                    g = int(campos[2], 16)
                    _CACHE = ".".join(str((g >> (8 * i)) & 0xFF) for i in range(4))
                    return _CACHE
    except Exception:  # raiz: fuera de Linux no hay /proc; vale el puente por defecto
        pass
    _CACHE = _POR_DEFECTO
    return _CACHE
