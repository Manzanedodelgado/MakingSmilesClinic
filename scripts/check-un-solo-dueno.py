#!/usr/bin/env python3
"""Un solo dueño por entidad.

Cada entidad de la base la escribe UN router y solo uno. El resto lee, o llama al dueño.
Este comprobador recorre los routers, apunta qué modelo escribe cada endpoint POST/PUT/
PATCH/DELETE y bloquea si una entidad se escribe desde más de un fichero.

La deuda que ya existía el 17-oct-2026 está congelada abajo, en DEUDA. Esa lista solo
puede MENGUAR: si una entidad deja de estar duplicada hay que quitarla de aquí, y si
aparece una duplicación nueva el gate bloquea el despliegue. No se añaden entradas
nuevas sin que el usuario lo autorice expresamente.
"""
import re, sys, glob, collections, pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent / "backend"

# entidad -> ficheros que HOY la escriben (deuda del 17-oct-2026). Solo puede menguar.
DEUDA: dict[str, set[str]] = {
    "EstadoCita":          {"configuracion_agenda_router.py", "configuracion_centro_router.py"},
    "Gabinete":            {"configuracion_agenda_router.py", "configuracion_centro_router.py"},
    "CasoOrtodoncia":      {"casos_ortodoncia_router.py", "llm_router.py"},
    "TratamientoRealizado":{"clinico_router.py", "presupuestos_router.py"},
    "Usuario":             {"configuracion_staff_router.py", "internal_tenant_router.py"},
    "Cita":                {"agenda_router.py", "app_paciente_router.py"},
}

ESCRIBEN = ("post", "put", "patch", "delete")


def escrituras() -> dict[str, set[str]]:
    """{modelo: {fichero, ...}} mirando solo los endpoints que escriben."""
    out: dict[str, set[str]] = collections.defaultdict(set)
    for ruta in glob.glob(str(RAIZ / "api" / "*.py")):
        fichero = pathlib.Path(ruta).name
        src = pathlib.Path(ruta).read_text(errors="replace")
        trozos = re.split(r'@router\.(?:get|post|put|patch|delete)\(\s*"[^"]*"', src)
        metodos = re.findall(r'@router\.(get|post|put|patch|delete)\(\s*"[^"]*"', src)
        for n, metodo in enumerate(metodos):
            cuerpo = trozos[n + 1] if n + 1 < len(trozos) else ""
            if metodo in ESCRIBEN:
                # alta: session.add(Modelo(...)) o  x = Modelo(centro_id=...)
                modelos = set(re.findall(r'session\.add\(\s*([A-Z]\w+)\(', cuerpo))
                modelos |= set(re.findall(r'=\s*([A-Z]\w+)\(\s*(?:centro_id|nombre|codigo)', cuerpo))
                # baja: var = session.get(Modelo, ...) ... session.delete(var)
                leidos = dict(re.findall(r'(\w+)\s*=\s*session\.get\(\s*([A-Z]\w+)\s*,', cuerpo))
                for var in re.findall(r'session\.delete\(\s*(\w+)\s*\)', cuerpo):
                    if var in leidos:
                        modelos.add(leidos[var])
                # modificación: var = session.get(Modelo,...) ; var.campo = ... ; session.add(var)
                for var, modelo in leidos.items():
                    if re.search(rf'{var}\.\w+\s*(,\s*{var}\.\w+\s*)*=\s*', cuerpo) and re.search(rf'session\.add\(\s*{var}\s*\)|_persist\(\s*session\s*,\s*{var}', cuerpo):
                        modelos.add(modelo)
                for m in modelos:
                    out[m].add(fichero)
    return out


def main() -> int:
    actual = escrituras()
    nuevas, crecidas = [], []
    for modelo, ficheros in sorted(actual.items()):
        if len(ficheros) < 2:
            continue
        if modelo not in DEUDA:
            nuevas.append((modelo, ficheros))
        elif not ficheros <= DEUDA[modelo]:
            crecidas.append((modelo, ficheros - DEUDA[modelo]))

    saldadas = [m for m, f in DEUDA.items() if len(actual.get(m, set())) < 2]

    if nuevas or crecidas:
        print("BLOQUEO: una entidad no puede escribirse desde dos sitios.")
        for m, f in nuevas:
            print(f"  NUEVA duplicación · {m}: {', '.join(sorted(f))}")
        for m, f in crecidas:
            print(f"  {m} gana un escritor más: {', '.join(sorted(f))}")
        print("\n  Deja un único dueño: el resto lee o llama al dueño.")
        return 1

    print(f"OK: un solo dueño por entidad. Deuda pendiente: {len(DEUDA)} entidades.")
    if saldadas:
        print(f"  Ya no están duplicadas, QUITA de DEUDA: {', '.join(sorted(saldadas))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
