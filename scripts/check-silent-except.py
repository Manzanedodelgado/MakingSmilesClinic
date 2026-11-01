#!/usr/bin/env python3
"""Detecta parches sin trazar en diffs unificados o en ficheros de todo el repo.

Dos modos:
  --diff      Lee un diff unificado de stdin. Revisa solo líneas añadidas (+):
              marcadores (ver regex MARCADOR) en cualquier extensión,
              except+pass en .py y catch vacío en .ts/.tsx/.js/.swift.
  --files     Lee rutas de ficheros de stdin y escanea su contenido completo
              con las reglas según extensión.

Salida: una línea por hallazgo "origen :: detalle". Exit 0 siempre;
el que llama decide con `if [ -n "$OUT" ]`. Nunca aprueba por silencio:
ante error de lectura, escribe a stderr y sale 2 (el gate lo trata como bloqueo).
"""
import hashlib
import re
import builtins
import sys

# TODO es palabra corriente en español ("todo"); solo cuenta como marcador con
# dos puntos (convención TODO:). XXX en "6XX XXX XXX" o "tel=XXX" es placeholder
# de teléfono/URL, no marcador: exige `:`/`-`/fin tras él. FIXME/HACK/chapuza
# sí son inequívocos.
MARCADOR = re.compile(r"\b(FIXME|HACK|chapuza)\b|TODO:|XXX(?=\s*[:\-]|$)")
EXCEPT = re.compile(r"^[ \t]*except[:( ]")
PASS = re.compile(r"^[ \t]*pass[ \t]*$")
VACIA_O_COMENT = re.compile(r"^[ \t]*(#.*)?$")
# catch vacío en TS/JS/Swift: `catch {}` en una línea, o `catch...{` seguido de `}`.
CATCH_ABRE = re.compile(r"^[ \t]*(catch|except)[ \t]*(\([^)]*\))?[ \t]*\{[ \t]*(//.*)?$")
CATCH_CIERRA = re.compile(r"^[ \t]*\}[ \t]*(//.*)?$")
VACIA_O_COMENT_C = re.compile(r"^[ \t]*(//.*)?$")


def revisar(origen: str, lineas: list[str], ext: str) -> list[str]:
    """Reglas por extensión: .py → except+pass; .ts/.tsx/.js/.swift → catch vacío.
    Excepción: `# raiz:` declara propiedad de la raíz con motivo — trazado,
    no silencioso. Sin motivo no hay perdón."""
    hallazgos = []
    prev_except = None
    prev_catch = None
    for l in lineas:
        m = MARCADOR.search(l)
        if m:
            hallazgos.append(f"{origen} :: marcador sin trazar: {m.group(1)} en: {l.strip()[:100]}")
        if ext == "py":
            if prev_except is not None and PASS.match(l):
                if "# raiz:" not in prev_except:
                    hallazgos.append(f"{origen} :: except silencioso: {prev_except.strip()[:80]} -> pass")
            if EXCEPT.match(l):
                prev_except = l
            elif not VACIA_O_COMENT.match(l):
                prev_except = None
        else:
            if "raiz:" in l:
                prev_catch = None  # propiedad de la raíz con motivo: trazado
            elif re.search(r"catch[ \t]*(\([^)]*\))?[ \t]*\{[ \t]*\}", l):
                hallazgos.append(f"{origen} :: catch vacío: {l.strip()[:100]}")
            elif CATCH_ABRE.match(l):
                prev_catch = l
            elif prev_catch is not None:
                if CATCH_CIERRA.match(l):
                    hallazgos.append(f"{origen} :: catch vacío: {prev_catch.strip()[:80]} -> }}")
                    prev_catch = None
                elif not VACIA_O_COMENT_C.match(l):
                    prev_catch = None
    return hallazgos


# ── Sospechosos (heurística; se LISTAN, no bloquean: requieren ojo humano) ──
# except/catch genérico aunque tenga cuerpo: puede tapar la causa real.
BROAD_PY = re.compile(r"^[ \t]*except[ \t]+(Exception|BaseException)[ \t]*:")
BROAD_TS = re.compile(r"^[ \t]*catch[ \t]*(\([^)]*\))?[ \t]*\{")
# Valores de entorno/ red duros en código nuevo.
IP_DURA = re.compile(r"\b(?!0\.0\.0\.0|127\.|255\.)\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b")
# Atajos que ocultan errores reales.
ANY_TS = re.compile(r"\bas\s+any\b|@ts-ignore|@ts-nocheck|eslint-disable")
TRY_SWIFT = re.compile(r"\btry\?[ \t]")
# Esperas mágicas que tapan carreras.
SLEEP_MAGICO = re.compile(r"(setTimeout\s*\(.{0,60}?,\s*\d+|time\.sleep\s*\(\s*\d|await\s+asyncio\.sleep\s*\(\s*\d|Thread\.sleep\s*\(\s*\d)")
LOG_LLAMADA = re.compile(r"log(ger)?\.(debug|info|warning|error|exception)|console\.(debug|log|warn|error)|print\s*\(|raise |throw |Sentry|reportar")


def sospechosos(origen: str, lineas: list[str], ext: str) -> list[str]:
    """Heurística sobre líneas (añadidas o de fichero). Lista, no bloquea."""
    out = []
    for l in lineas:
        s = l.strip()
        if not s or s.startswith(("#", "//")):
            continue
        if ext == "py" and BROAD_PY.match(l):
            out.append(f"{origen} ?? except genérico (revisar causa): {s[:100]}")
        if ext in ("ts", "tsx", "js") and BROAD_TS.match(l):
            out.append(f"{origen} ?? catch genérico (revisar causa): {s[:100]}")
        if ext in ("py", "ts", "tsx", "js", "swift"):
            m = IP_DURA.search(l)
            if m and "test" not in l.lower() and "example" not in l.lower():
                out.append(f"{origen} ?? IP dura en código: {m.group(0)} en: {s[:100]}")
        if ext in ("ts", "tsx") and ANY_TS.search(l):
            out.append(f"{origen} ?? ocultación de tipos/lint: {s[:100]}")
        if ext == "swift" and TRY_SWIFT.search(l):
            out.append(f"{origen} ?? try? traga error: {s[:100]}")
        if ext in ("py", "ts", "tsx", "js", "swift", "kt") and SLEEP_MAGICO.search(l):
            out.append(f"{origen} ?? espera mágica (posible carrera tapada): {s[:100]}")
    return out


def duplicados(rutas: list[str]) -> list[str]:
    """Bloques normalizados (≥8 líneas) repetidos en ≥2 ficheros: copiar-pegar
    que suele esconder causa sin corregir. Solo modo --files con rutas reales."""
    bloques: dict[str, list[str]] = {}
    for ruta in rutas:
        try:
            with open(ruta, encoding="utf-8", errors="replace") as f:
                contenido = f.read().splitlines()
        except OSError:
            continue
        norm = [re.sub(r"\s+", "", l) for l in contenido]
        norm = [l for l in norm if l and not l.startswith(("#", "//", "import", "from", "export"))]
        for i in range(len(norm) - 7):
            ventana = "\n".join(norm[i:i + 8])
            h = hashlib.md5(ventana.encode()).hexdigest()
            bloques.setdefault(h, []).append(f"{ruta}:{i + 1}")
    out = []
    for h, locs in bloques.items():
        ficheros = {l.rsplit(":", 1)[0] for l in locs}
        if len(ficheros) >= 2:
            out.append(f"?? bloque duplicado en {len(ficheros)} ficheros: {', '.join(sorted(ficheros)[:4])}")
    return sorted(set(out))


def _definiciones_del_repo() -> dict:
    """nombre → ficheros que lo definen (def / function / const x = / func x(), una sola pasada de git grep)."""
    import subprocess
    patron = r"def [A-Za-z_][A-Za-z_0-9]*\b|function [A-Za-z_][A-Za-z_0-9]*\b|const [A-Za-z_][A-Za-z_0-9]* ?=|func [A-Za-z_][A-Za-z_0-9]*\("
    try:
        r = subprocess.run(["git", "grep", "-o", "-I", "-E", patron, "--", "."],
                           capture_output=True, text=True, timeout=120)
    except Exception:
        return {}
    defs: dict = {}
    for linea in r.stdout.splitlines():
        ruta, _, m = linea.rpartition(":")
        n = re.match(r"(?:def|function|const|func) ([A-Za-z_][A-Za-z_0-9]*)", m)
        if n and ruta:
            defs.setdefault(n.group(1), set()).add(ruta)
    return defs


def envoltorios(diff_texto: str) -> list[str]:
    """Parche por definición: código NUEVO que envuelve funciones YA EXISTENTES
    sin modificar su raíz (try/except/catch añadido alrededor de llamadas a
    código que el diff no toca). Solo modo --diff."""
    import subprocess
    # Ficheros tocados por el diff (su raíz SÍ se modifica: no cuentan).
    tocados = set(re.findall(r"^diff --git a/(.*) b/.*$", diff_texto, re.M))
    # Llamadas dentro de bloques try añadidos.
    llamadas: dict[str, list[str]] = {}
    archivo = "<diff>"
    def _codigo(l: str) -> str:
        """Quita cadenas y comentarios: el heurístico no debe leer prosa como llamadas."""
        l = re.sub(r'`(?:[^`\\]|\\.)*`', '`x`', l)
        l = re.sub(r'"(?:[^"\\]|\\.)*"', '""', l)
        l = re.sub(r"'(?:[^'\\]|\\.)*'", "''", l)
        l = re.sub(r'//.*$', '', l)
        l = re.sub(r'#.*$', '', l)
        return l

    en_try = 0
    for raw in diff_texto.splitlines():
        if raw.startswith("diff --git"):
            m = re.match(r"diff --git a/(.*) b/.*", raw)
            archivo = m.group(1) if m else archivo
            en_try = 0
        elif raw.startswith("+++"):
            continue
        elif raw.startswith("+"):
            l = raw[1:]
            if re.match(r"^[ \t]*try\b", l):
                en_try += 1
            elif en_try and re.match(r"^[ \t]*\}", l):
                en_try = max(0, en_try - 1)
            if en_try:
                for c in re.findall(r"\b([a-zA-Z_]\w*)\s*\(", _codigo(l)):
                    if c not in ("if", "for", "while", "switch", "catch", "try"):
                        llamadas.setdefault(c, []).append(archivo)
    out = []
    # Verbos de interfaz ubicuos (logout, close, delete…): pertenecen a docenas
    # de raíces distintas; envolverlos no señala una raíz concreta. Sin perdón
    # para el resto.
    # Idem los verbos del cliente HTTP (api.del/post/put/patch) y errMsg (formateo del error,
    # fuente única en shared/lib/errores.ts): llamarlos dentro de un try es MANEJAR el error
    # (mostrarlo), no envolver una raíz ajena. No perdona nada más.
    GENERICOS = {"logout", "close", "delete", "save", "load", "get", "set", "find",
                 "run", "start", "stop", "open", "read", "write", "create",
                 "update", "send", "fetch", "del", "post", "put", "patch", "errMsg"}
    # UNA sola búsqueda en el repo (antes: un `git grep` por cada nombre llamado = cientos de procesos, ~3 min por
    # publicación). Mismo criterio que antes: `def N` · `function N` · `const N =` · `func N(`.
    definiciones = _definiciones_del_repo() if llamadas else {}
    # Builtins (int, sorted, print…): envolverlos no es envolver una raíz del repo; el
    # heurístico los confundía con funciones homónimas de otros ficheros.
    _BUILTINS = frozenset(dir(builtins))
    for nombre, archivos in llamadas.items():
        if nombre in GENERICOS or nombre in _BUILTINS:
            continue
        definidos = [f for f in sorted(definiciones.get(nombre, ())) if f not in tocados
                     and ".venv" not in f and "node_modules" not in f]
        if definidos:
            donde = sorted(set(archivos))[:2]
            out.append(f"{', '.join(donde)} ?? envoltorio nuevo sobre {nombre}() "
                       f"(raíz intacta en {definidos[0]}): modificar la raíz, no envolverla")
    return sorted(set(out))


def modo_diff() -> tuple[list[str], list[str]]:
    """Devuelve (duros, sospechosos)."""
    hallazgos = []
    susp = []
    archivo = "<diff>"
    anadidas: list[str] = []
    crudo: list[str] = []

    def ext_de(nombre: str) -> str:
        return nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""

    def volcar():
        if anadidas:
            hallazgos.extend(revisar(archivo, anadidas, ext_de(archivo)))
            susp.extend(sospechosos(archivo, anadidas, ext_de(archivo)))

    for raw in sys.stdin:
        crudo.append(raw.rstrip("\n"))
        linea = raw.rstrip("\n")
        if linea.startswith("diff --git"):
            volcar()
            anadidas = []
            m = re.match(r"diff --git a/(.*) b/.*", linea)
            archivo = m.group(1) if m else "<diff>"
        elif linea.startswith("+++"):
            continue
        elif linea.startswith("+"):
            anadidas.append(linea[1:])
        elif linea.startswith("@@"):
            volcar()
            anadidas = []
    volcar()
    return hallazgos, susp


def modo_files() -> tuple[list[str], list[str], list[str]]:
    hallazgos = []
    susp = []
    rutas = []
    for ruta in sys.stdin:
        ruta = ruta.strip()
        if not ruta:
            continue
        rutas.append(ruta)
        try:
            with open(ruta, encoding="utf-8", errors="replace") as f:
                contenido = f.read().splitlines()
        except OSError as e:
            print(f"ERROR leyendo {ruta}: {e}", file=sys.stderr)
            sys.exit(2)
        ext = ruta.rsplit(".", 1)[-1].lower() if "." in ruta else ""
        hallazgos.extend(revisar(ruta, contenido, ext))
        susp.extend(sospechosos(ruta, contenido, ext))
    return hallazgos, susp, rutas


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "--diff"
    solo_susp = "--sospechosos" in sys.argv
    if "--envoltorios" in sys.argv:
        # Lee el diff completo de stdin y lista envoltorios sobre raíz intacta.
        for h in envoltorios(sys.stdin.read()):
            print(h)
        sys.exit(0)
    if modo == "--files":
        duros, susp, rutas = modo_files()
    else:
        duros, susp = modo_diff()
        rutas = []
    if "--duplicados" in sys.argv and rutas:
        for h in duplicados(rutas):
            print(h)
    if solo_susp:
        for h in susp:
            print(h)
    else:
        for h in duros:
            print(h)
