#!/usr/bin/env python3
"""¿Cuadra la app con GELITE? Población entera, nunca una muestra.

Existe porque dije "coincide" después de mirar UNA fila que casaba por casualidad, y por
poco se queda dentro el fallo de los doctores. Aquí no hay muestreo: se comparan todas las
filas de las dos bases y se dice cuántas difieren. Si no sale de aquí, no se dice "cuadra".

  python3 scripts/cuadra.py realizados
  python3 scripts/cuadra.py doctores
  python3 scripts/cuadra.py pagos
"""
import subprocess, sys, pathlib
sys.path.insert(0, "/tmp/migcitas")


def app(sql: str) -> str:
    r = subprocess.run(["docker", "exec", "makingsmiles-postgres", "psql", "-U", "makingsmiles",
                        "-d", "makingsmiles", "-At", "-c", sql], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"ERROR consultando la app: {r.stderr.strip()[:200]}")
    return r.stdout.strip()


def comprueba(nombre: str, gelite: float, aplicacion: float, poblacion: str) -> bool:
    ok = abs(gelite - aplicacion) < 0.01
    print(f"  {nombre:<34} GELITE {gelite:>15,.2f} | APP {aplicacion:>15,.2f}  "
          f"{'CUADRA' if ok else '*** DESCUADRA ***'}   ({poblacion})")
    return ok


def main() -> int:
    que = sys.argv[1] if len(sys.argv) > 1 else "todo"
    from g17 import q                                    # noqa: E402
    fallos = []

    if que in ("todo", "realizados"):
        print("== importe de los tratamientos realizados ==")
        g = float(q("select sum(Importe) i from TtosMed where StaTto=5 and Importe>0")[0]["i"])
        a = float(app("select sum(importe) from tratamientos_realizados where importe>0"))
        if not comprueba("total realizados", g, a, "todas las filas con importe>0"):
            fallos.append("realizados")

    if que in ("todo", "doctores"):
        print("== producción por doctor (TODOS, no una muestra) ==")
        ids = [r["IdCol"] for r in q("select distinct IdCol from TtosMed where StaTto=5 and IdCol is not null")]
        malos = 0
        for i in ids:
            g = float(q(f"select coalesce(sum(Importe),0) i from TtosMed where StaTto=5 and Importe>0 and IdCol={i}")[0]["i"])
            a = app(f"select coalesce(sum(r.importe),0) from tratamientos_realizados r "
                    f"join colaboradores c on c.id=r.colaborador_id where r.importe>0 and c.id_gelite={i}")
            a = float(a or 0)
            if abs(g - a) >= 0.01:
                malos += 1
                print(f"  IdCol {i:<4} GELITE {g:>14,.2f} | APP {a:>14,.2f}  *** DESCUADRA ***")
        print(f"  {len(ids) - malos} de {len(ids)} doctores cuadran  (población entera)")
        if malos:
            fallos.append(f"doctores ({malos})")

    if que in ("todo", "pagos"):
        print("== pagos ==")
        g = float(q("select sum(Importe) i from PagoCli")[0]["i"])
        a = float(app("select sum(importe) from pagos"))
        if not comprueba("total pagos", g, a, "todas las filas"):
            fallos.append("pagos")

    print()
    if fallos:
        print(f"NO CUADRA: {', '.join(fallos)}")
        return 1
    print("CUADRA todo lo comprobado, sobre la población entera.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
