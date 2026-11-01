#!/usr/bin/env python3
"""Utilidad de paridad de la superficie HTTP del backend — MakingSmiles_Studio (S1b).

Genera y compara el snapshot versionado `backend/tests/contract/openapi_paridad.json`
a partir de la app REAL (`backend/main.py:app` + `app.openapi()`), no de la spec
estática de docs/rebuild/. Es la utilidad que los tests de contrato usan como
biblioteca (se cargan este fichero por ruta) y que un humano ejecuta a mano.

Uso (desde cualquier cwd; resuelve la raíz del repo por `__file__`):

    python3 scripts/paridad_api.py                    # compara con el snapshot; exit 1 si deriva
    python3 scripts/paridad_api.py --resumen          # solo cifras actuales (paths/operaciones)
    python3 scripts/paridad_api.py --snapshot /tmp/x.json   # compara contra otro snapshot
    python3 scripts/paridad_api.py --escribir-snapshot --motivo "texto obligatorio"

Códigos de salida:
    0 → sin deriva (o snapshot escrito)
    1 → deriva de contrato detectada
    2 → error de entorno / snapshot ilegible / actualización sin motivo

Qué compara (por operación, método+path):
    auth          → esquemas de seguridad declarados (None = sin seguridad declarada;
                    [""] = seguridad OPCIONAL, es decir se permite anónimo)
    parametros    → "in:nombre:requerido" de path/query/header/cookie
    request_body  → content-types admitidos
    respuestas    → códigos de estado declarados
Además detecta rutas añadidas/eliminadas y métodos añadidos/eliminados.

Contrato del snapshot (version 1):
    {
      "version": 1,
      "generado_por": "scripts/paridad_api.py",
      "app": "backend/main.py:app",
      "openapi": "3.x.y",
      "entorno": "development",
      "fecha_utc": "...",
      "motivo": "por qué se aceptó este estado (obligatorio)",
      "conteos": {"paths": 432, "operaciones": 498},
      "rutas": {"/ruta": {"GET": {firma}, ...}, ...}
    }

Actualización consciente del snapshot (NUNCA automática):
    1. `python3 scripts/paridad_api.py` → leer CADA diferencia y decidir si es intencionada.
    2. Si lo es: `python3 scripts/paridad_api.py --escribir-snapshot --motivo "<porqué>"`
       (el script imprime el diff que acepta y lo sella en el JSON).
    3. Revisar `git diff backend/tests/contract/openapi_paridad.json` y pegarlo en el PR.
    4. `cd backend && python -m pytest tests/contract -q` y el deploy-gate.
Los tests NUNCA escriben el snapshot: solo lo leen y fallan si hay deriva.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
BACKEND = RAIZ / "backend"
SNAPSHOT_POR_DEFECTO = BACKEND / "tests" / "contract" / "openapi_paridad.json"
VERSION_SNAPSHOT = 1
METODOS_HTTP = ("get", "post", "put", "patch", "delete", "head", "options", "trace")
CAMPOS_FIRMA = ("auth", "parametros", "request_body", "respuestas")

# Variables mínimas para poder importar backend/main.py sin servicios reales.
# Son las MISMAS que usa backend/tests/conftest.py: importar la app no ejecuta su
# lifespan, así que no se abre ninguna conexión a BD/servicios. `setdefault`: si el
# entorno ya las define (CI, .env real), se respetan.
ENTORNO_MINIMO = {
    "ENVIRONMENT": "development",
    "DATABASE_URL": "sqlite://",
    "SECRET_KEY": "paridad-api-local-secret-key-32-chars-min",
    "INTERNAL_API_KEY": "paridad-api-local-internal-key-32-chars-min",
}


def preparar_entorno() -> None:
    """Deja `backend/` importable y el entorno mínimo para importar la app."""
    for clave, valor in ENTORNO_MINIMO.items():
        os.environ.setdefault(clave, valor)
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))


def app_actual():
    """Importa y devuelve la app real. Solo para uso CLI (los tests la importan vía conftest)."""
    preparar_entorno()
    from main import app

    return app


def firma_operacion(operacion: dict) -> dict:
    """Firma estable y legible de una operación OpenAPI (lo que el contrato observable expone)."""
    seguridad = operacion.get("security") or []
    auth: list[str] | None
    if seguridad:
        # Cada requisito es una lista de esquemas que deben cumplirse a la vez (AND).
        # Varios requisitos = alternativas (OR). Un requisito vacío ("") = se permite anónimo.
        auth = sorted("+".join(sorted(requisito)) for requisito in seguridad)
    else:
        auth = None
    parametros = sorted(
        f'{p.get("in")}:{p.get("name")}{"!" if p.get("required") else "?"}'
        for p in operacion.get("parameters") or []
    )
    cuerpo = sorted((operacion.get("requestBody") or {}).get("content") or {}) or None
    respuestas = sorted((operacion.get("responses") or {}).keys())
    return {
        "auth": auth,
        "parametros": parametros,
        "request_body": cuerpo,
        "respuestas": respuestas,
    }


def capturar_esquema(app) -> dict:
    """Captura la superficie observable: {rutas: {path: {METODO_Y_FIRMA: firma}}}."""
    especificacion = app.openapi()
    rutas: dict[str, dict[str, dict]] = {}
    for ruta, operaciones in (especificacion.get("paths") or {}).items():
        por_metodo = {
            metodo.upper(): firma_operacion(operacion)
            for metodo, operacion in operaciones.items()
            if metodo.lower() in METODOS_HTTP
        }
        if por_metodo:
            rutas[ruta] = por_metodo
    return {"rutas": rutas}


def contar(esquema: dict) -> dict:
    rutas = esquema.get("rutas") or {}
    return {
        "paths": len(rutas),
        "operaciones": sum(len(operaciones) for operaciones in rutas.values()),
    }


def construir_snapshot(esquema: dict, motivo: str, version_openapi: str = "") -> dict:
    return {
        "version": VERSION_SNAPSHOT,
        "generado_por": "scripts/paridad_api.py",
        "app": "backend/main.py:app",
        "openapi": version_openapi,
        "entorno": "development",
        "fecha_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "motivo": motivo,
        "conteos": contar(esquema),
        "rutas": esquema["rutas"],
    }


def cargar_snapshot(ruta) -> dict:
    """Lee y valida el snapshot. Lanza OSError/ValueError con mensaje accionable."""
    destino = Path(ruta)
    try:
        datos = json.loads(destino.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(
            f"No existe el snapshot '{destino}'. Créalo de forma consciente con "
            "--escribir-snapshot --motivo \"...\" (no se autogenera solo)."
        ) from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"Snapshot '{destino}' no es JSON válido: {exc}") from exc
    if not isinstance(datos, dict):
        raise ValueError(f"Snapshot '{destino}' debe ser un objeto JSON.")
    if datos.get("version") != VERSION_SNAPSHOT:
        raise ValueError(
            f"Snapshot '{destino}' con version={datos.get('version')!r}; "
            f"esta utilidad espera version={VERSION_SNAPSHOT}."
        )
    if not isinstance(datos.get("rutas"), dict):
        raise ValueError(f"Snapshot '{destino}' sin el objeto 'rutas'.")
    return datos


def comparar(snapshot: dict, actual: dict) -> list[str]:
    """Devuelve la lista de diferencias legibles (vacía = paridad)."""
    previas = snapshot.get("rutas") or {}
    ahora = actual.get("rutas") or {}
    diferencias: list[str] = []

    for ruta in sorted(set(ahora) - set(previas)):
        diferencias.append(f"RUTA AÑADIDA: {ruta} ({', '.join(sorted(ahora[ruta]))})")
    for ruta in sorted(set(previas) - set(ahora)):
        diferencias.append(f"RUTA ELIMINADA: {ruta} ({', '.join(sorted(previas[ruta]))})")

    for ruta in sorted(set(previas) & set(ahora)):
        antes, despues = previas[ruta], ahora[ruta]
        for metodo in sorted(set(despues) - set(antes)):
            diferencias.append(f"METODO AÑADIDO: {metodo} {ruta}")
        for metodo in sorted(set(antes) - set(despues)):
            diferencias.append(f"METODO ELIMINADO: {metodo} {ruta}")
        for metodo in sorted(set(antes) & set(despues)):
            firma_antes, firma_despues = antes[metodo], despues[metodo]
            if not isinstance(firma_antes, dict):
                diferencias.append(
                    f"FIRMA ILEGIBLE EN SNAPSHOT: {metodo} {ruta} ({firma_antes!r})"
                )
                continue
            for campo in CAMPOS_FIRMA:
                if firma_antes.get(campo) != firma_despues.get(campo):
                    diferencias.append(
                        f"OPERACIÓN CAMBIADA: {metodo} {ruta} · {campo}: "
                        f"{firma_antes.get(campo)!r} -> {firma_despues.get(campo)!r}"
                    )
    return diferencias


def _imprimir_resumen(resumen: str, snapshot: dict | None, ruta_snapshot: Path) -> None:
    if snapshot is not None:
        print(f"snapshot: {ruta_snapshot} (motivo: {snapshot.get('motivo', '?')})")
    print(f"actual:   {resumen}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Paridad de la superficie HTTP real del backend contra un snapshot versionado."
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=SNAPSHOT_POR_DEFECTO,
        help=f"snapshot a leer/escribir (por defecto {SNAPSHOT_POR_DEFECTO})",
    )
    parser.add_argument(
        "--escribir-snapshot",
        action="store_true",
        help="actualiza el snapshot con el estado actual (exige --motivo; acto consciente)",
    )
    parser.add_argument(
        "--motivo",
        default=None,
        help="porqué se acepta el nuevo estado; obligatorio con --escribir-snapshot",
    )
    parser.add_argument(
        "--resumen",
        action="store_true",
        help="solo imprime las cifras actuales (paths/operaciones)",
    )
    args = parser.parse_args(argv)

    try:
        app = app_actual()
    except (ImportError, OSError, ValueError) as exc:
        print(f"ERROR: no se pudo importar backend/main.py: {exc}", file=sys.stderr)
        return 2

    esquema = capturar_esquema(app)
    conteos = contar(esquema)
    resumen = f"{conteos['paths']} paths / {conteos['operaciones']} operaciones"

    if args.resumen:
        print(resumen)
        return 0

    ruta_snapshot = Path(args.snapshot)
    if args.escribir_snapshot:
        motivo = (args.motivo or "").strip()
        if not motivo:
            print(
                "BLOQUEO: --escribir-snapshot exige --motivo no vacío. El snapshot no se "
                "auto-acepta: describe qué cambia y por qué es intencionado.",
                file=sys.stderr,
            )
            return 2
        previo: dict | None = None
        if ruta_snapshot.exists():
            try:
                previo = cargar_snapshot(ruta_snapshot)
            except (OSError, ValueError) as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 2
        diferencias = comparar(previo, esquema) if previo is not None else []
        if diferencias:
            print(f"CAMBIOS QUE SE ACEPTAN ({len(diferencias)}):")
            for diferencia in diferencias:
                print(f"  - {diferencia}")
        else:
            print("Sin cambios respecto al snapshot actual.")
        nuevo = construir_snapshot(esquema, motivo, app.openapi().get("openapi", ""))
        ruta_snapshot.parent.mkdir(parents=True, exist_ok=True)
        ruta_snapshot.write_text(
            json.dumps(nuevo, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"SNAPSHOT ESCRITO: {ruta_snapshot} — {resumen} — motivo: {motivo}")
        return 0

    try:
        snapshot = cargar_snapshot(ruta_snapshot)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    diferencias = comparar(snapshot, esquema)
    _imprimir_resumen(resumen, snapshot, ruta_snapshot)
    if not diferencias:
        print("OK: sin deriva de contrato.")
        return 0
    print(f"DERIVA DETECTADA: {len(diferencias)} diferencia(s)")
    for diferencia in diferencias:
        print(f"  - {diferencia}")
    print(
        "Si el cambio es INTENCIONADO, revisa cada diferencia y actualiza el snapshot con "
        "--escribir-snapshot --motivo \"...\"; si no lo es, corrige el código."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
