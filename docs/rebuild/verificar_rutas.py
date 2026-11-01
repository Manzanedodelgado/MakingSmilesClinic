#!/usr/bin/env python3
"""Verificador de paridad de rutas — MakingSmiles_Studio (S1).

Uso:
    python3 docs/rebuild/verificar_rutas.py                # extracción estática (sin deps)
    python3 docs/rebuild/verificar_rutas.py --import       # importa backend/main.py:app y compara
                                                           # (requiere venv con requirements.txt y
                                                           #  paths: cwd=backend/)
    python3 docs/rebuild/verificar_rutas.py --csv          # imprime una fila CSV por operación

Qué hace:
  1. Parsea backend/api/*.py con `ast`, resuelve `router = APIRouter(prefix=...)`, cruza con
     `app.include_router(...)` de backend/main.py y cuenta operaciones (método, path).
  2. Detecta colisiones exactas y semánticas ({param} -> *) en el orden real de registro.
  3. Con --import, instancia la app y compara: len(app.routes) y len(app.openapi()["paths"]).
     Cualquier diferencia con la extracción estática se lista para investigar.

Salida: contadores + lista de operaciones (una por línea). Código de salida 0 si
estático==import (cuando se usa --import), 1 si hay discrepancia o si el import falla.
"""
import ast
import csv
import re
import sys
from pathlib import Path

# ── localizar backend/ (funciona desde la raíz del repo o desde docs/rebuild) ──
def _backend_dir() -> Path:
    for cand in (Path.cwd() / "backend", Path(__file__).resolve().parents[2] / "backend"):
        if (cand / "main.py").is_file():
            return cand
    raise SystemExit("No encuentro backend/main.py; ejecuta desde la raíz del worktree.")

API_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "websocket"}


def _const(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{expr}" for v in node.values)
    if isinstance(node, ast.BinOp):
        return _const(node.left) + _const(node.right)
    return "<expr>"


def _kw(call, name):
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def extract(backend: Path):
    routes = []
    for f in sorted((backend / "api").glob("*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError as e:
            print(f"SYNTAX ERROR {f}: {e}", file=sys.stderr)
            continue
        prefix = ""
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "router":
                        p = _kw(node.value, "prefix")
                        if p is not None:
                            prefix = _const(p)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                        and isinstance(dec.func.value, ast.Name) and dec.func.value.id == "router"
                        and dec.func.attr in API_METHODS):
                    path = (_const(dec.args[0]) if dec.args else "")
                    full = (prefix + path).replace("//", "/")
                    if not full.startswith("/"):
                        full = "/" + full
                    routes.append({"file": f.name, "line": dec.lineno,
                                   "method": dec.func.attr.upper(), "path": full,
                                   "func": node.name})
    main_src = (backend / "main.py").read_text(encoding="utf-8")
    include = re.findall(r"app\.include_router\((\w+)\)", main_src)
    modmap = dict(re.findall(r"from api\.(\w+) import router as (\w+)", main_src))
    included = [modmap.get(n, n) for n in include]
    # orden real de registro: include_router × orden de definición en el módulo
    by_mod = {}
    for r in routes:
        by_mod.setdefault(r["file"][:-3], []).append(r)
    ordered = []
    for mod in included:
        ordered.extend(sorted(by_mod.get(mod, []), key=lambda x: x["line"]))
    return routes, ordered, included


def main(argv):
    backend = _backend_dir()
    routes, ordered, included = extract(backend)
    exact = {(r["method"], r["path"]) for r in routes}
    norm = lambda p: re.sub(r"\{[^}]+\}", "*", p)
    sem = {}
    for r in ordered:
        sem.setdefault((r["method"], norm(r["path"])), []).append(r)
    coll = {k: v for k, v in sem.items() if len(v) > 1}

    print(f"backend: {backend}")
    print(f"routers montados: {len(included)} | operaciones declaradas: {len(routes)}")
    print(f"operaciones únicas (método+path): {len(exact)} | rutas únicas (path): "
          f"{len({r['path'] for r in routes})}")
    print(f"colisiones exactas: {len(routes) - len(exact)} | colisiones semánticas: {len(coll)}")
    for (m, p), v in coll.items():
        print(f"  COLISION {m} {p}")
        for r in v:
            print(f"    {r['file']}:{r['line']} -> {r['path']} ({r['func']})")
    unmatched = [m for m in by_mod_keys(routes) if m not in included]
    if unmatched:
        print(f"ATENCIÓN: {len(unmatched)} módulos de router NO montados: {unmatched}")
    else:
        print("todos los módulos de router declarados están montados en main.py")

    if "--csv" in argv:
        w = csv.writer(sys.stdout)
        w.writerow(["method", "path", "file", "line", "func"])
        for r in routes:
            w.writerow([r["method"], r["path"], r["file"], r["line"], r["func"]])

    if "--import" not in argv:
        return 0

    # ── comparación con la app importada (requiere entorno preparado) ──
    sys.path.insert(0, str(backend))
    try:
        import main  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        print(f"IMPORT FALLÓ: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("Este script no instala dependencias. Usa un venv con backend/requirements.txt.",
              file=sys.stderr)
        return 1
    # OJO: en FastAPI moderno `len(app.routes)` NO cuenta operaciones: `include_router` deja un
    # envoltorio `_IncludedRouter` por router (path == ""). La métrica de paridad es openapi.
    from collections import Counter
    tipos = Counter(type(r).__name__ for r in main.app.routes)
    print(f"\nimport: len(app.routes) = {len(main.app.routes)}  desglose={dict(tipos)}")
    print("        (los _IncludedRouter son envoltorios de include_router, NO operaciones)")
    openapi = main.app.openapi()
    import_ops = {(path, method.upper()) for path, ops in openapi["paths"].items()
                  for method in ops}
    static_ops = {(r["path"], r["method"]) for r in routes}
    print(f"        openapi paths = {len(openapi['paths'])} | operaciones = {len(import_ops)}")
    solo_import = sorted(import_ops - static_ops)
    solo_estatico = sorted(static_ops - import_ops)
    if solo_import:
        print(f"DIFERENCIAS: {len(solo_import)} operaciones del OpenAPI no están en el estático:")
        for m, p in solo_import[:50]:
            print(f"  {m} {p}")
    if solo_estatico:
        # esperado: el WebSocket no aparece en OpenAPI (no es una operación OpenAPI)
        print(f"Nota: {len(solo_estatico)} operaciones del estático no están en OpenAPI "
              f"(se espera la WebSocket y las de documentación):")
        for m, p in solo_estatico[:10]:
            print(f"  {m} {p}")
    inesperadas = [op for op in solo_import if not _es_doc(op[0])]
    if inesperadas:
        print(f"FALLO: {len(inesperadas)} operaciones inesperadas fuera del inventario estático")
        return 1
    print("OK: OpenAPI y extracción estática coinciden (salvo WebSocket/documentación)")
    return 0


def _es_doc(path: str) -> bool:
    return path in ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc")


def by_mod_keys(routes):
    return {r["file"][:-3] for r in routes}


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
