"""Tests de `check-silent-except.py --envoltorios` (regla «resolver en la raíz, no envolverla»).

El gate bloquea el despliegue cuando un `try` NUEVO envuelve una función que ya existe sin tocar.
Estos tests fijan dos cosas: (1) lo que NO es un envoltorio (falsos positivos reales vistos el
02-nov-2026 en `generar_guias_protocolo.py` y `APIClient.swift`) y (2) lo que SÍ lo es, que debe seguir
marcándose. Ejecutar: python3 -m pytest scripts/test_check_silent_except.py -q
"""
import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location("check_silent_except", pathlib.Path(__file__).with_name("check-silent-except.py"))
cse = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cse)


def diff_nuevo(ruta: str, cuerpo: str) -> str:
    lineas = cuerpo.strip("\n").splitlines()
    return (f"diff --git a/{ruta} b/{ruta}\nnew file mode 100644\n--- /dev/null\n+++ b/{ruta}\n@@ -0,0 +1,{len(lineas)} @@\n"
            + "\n".join("+" + l for l in lineas) + "\n")


def hallazgos(monkeypatch, defs: dict, ruta: str, cuerpo: str) -> list[str]:
    monkeypatch.setattr(cse, "_definiciones_del_repo", lambda: {k: set(v) for k, v in defs.items()})
    return cse.envoltorios(diff_nuevo(ruta, cuerpo))


# ── Lo que NO es un envoltorio ────────────────────────────────────────────────

def test_python_llamada_fuera_del_try_no_es_envoltorio(monkeypatch):
    cuerpo = """
def f(d):
    try:
        x = 1
    except ValueError:
        x = 2
    ayudante(x)
"""
    assert hallazgos(monkeypatch, {"ayudante": ["backend/otro.py"]}, "backend/nuevo.py", cuerpo) == []


def test_nombre_definido_solo_en_otro_lenguaje_no_es_raiz(monkeypatch):
    cuerpo = """
def f(d):
    try:
        d.line((0, 0, 5, 5), fill=1)
    except ValueError:
        pass
"""
    assert hallazgos(monkeypatch, {"line": ["frontend/public/editor.html"]}, "backend/tools/guias.py", cuerpo) == []


def test_activo_generado_o_minificado_no_es_raiz(monkeypatch):
    cuerpo = """
async function f() {
  try {
    await calcular(1);
  } catch (e) {
    mostrar(e);
  }
}
"""
    defs = {"calcular": ["frontend/public/assets/decode-abc.js.map", "frontend/public/vendor.js"]}
    assert hallazgos(monkeypatch, defs, "frontend/src/nuevo.ts", cuerpo) == []


def test_typescript_no_compara_con_funciones_de_python(monkeypatch):
    cuerpo = """
async function f() {
  try {
    await calcular(1);
  } catch (e) {
    mostrar(e);
  }
}
"""
    assert hallazgos(monkeypatch, {"calcular": ["backend/x.py"]}, "frontend/src/nuevo.ts", cuerpo) == []


def test_swift_try_de_propagacion_no_es_bloque_try_catch(monkeypatch):
    cuerpo = """
func protocolo() async throws -> [Slot] {
    try decode(Respuesta.self, await request("/app/protocolo")).protocolo
}
"""
    assert hallazgos(monkeypatch, {"request": ["frontend/src/shared/lib/api.ts"]}, "mobile/APIClient.swift", cuerpo) == []


def test_palabra_clave_in_no_es_llamada(monkeypatch):
    cuerpo = """
def f():
    try:
        for k in(1, 2):
            pass
    except ValueError:
        pass
"""
    assert hallazgos(monkeypatch, {"in": ["backend/x.py"]}, "backend/nuevo.py", cuerpo) == []


# ── Lo que SÍ es un envoltorio: debe seguir marcándose ────────────────────────

def test_python_llamada_dentro_del_try_sigue_marcando(monkeypatch):
    cuerpo = """
def f(d):
    try:
        ayudante(d)
    except ValueError:
        pass
"""
    r = hallazgos(monkeypatch, {"ayudante": ["backend/otro.py"]}, "backend/nuevo.py", cuerpo)
    assert len(r) == 1 and "ayudante()" in r[0] and "backend/otro.py" in r[0]


def test_typescript_try_catch_sigue_marcando(monkeypatch):
    cuerpo = """
async function f() {
  try {
    await cargar(1);
  } catch (e) {
    mostrar(e);
  }
}
"""
    r = hallazgos(monkeypatch, {"cargar": ["frontend/src/otra.tsx"]}, "frontend/src/nuevo.ts", cuerpo)
    assert len(r) == 1 and "cargar()" in r[0]


def test_swift_do_catch_sigue_marcando(monkeypatch):
    cuerpo = """
func cargar() async {
    do {
        try await peticion("/a")
    } catch {
        print(error)
    }
}
"""
    r = hallazgos(monkeypatch, {"peticion": ["mobile/Otro.swift"]}, "mobile/APIClient.swift", cuerpo)
    assert len(r) == 1 and "peticion()" in r[0]


# ── Segunda tanda (comparación con 40 commits reales de master) ───────────────

def test_bundle_minificado_no_se_analiza(monkeypatch):
    cuerpo = "try{await L(1)}catch(e){}"
    assert hallazgos(monkeypatch, {"L": ["frontend/src/app/agenda/page.tsx"]}, "frontend/public/assets/decode-x.js", cuerpo) == []


def test_funcion_definida_en_el_propio_fichero_nuevo_no_es_envoltorio(monkeypatch):
    cuerpo = """
final class APIClient {
    private func request(_ path: String) async throws -> Data { Data() }
    func protocolo() async {
        do {
            try await request("/a")
        } catch {
            print(error)
        }
    }
}
"""
    assert hallazgos(monkeypatch, {"request": ["mobile/Otra/APIClient.swift"]}, "mobile/Doctor/APIClient.swift", cuerpo) == []


def test_funcion_que_el_propio_fichero_ya_define_en_el_arbol_no_es_envoltorio(monkeypatch):
    cuerpo = """
func protocolo() async {
    do {
        try await request("/a")
    } catch {
        print(error)
    }
}
"""
    defs = {"request": ["mobile/Doctor/APIClient.swift", "mobile/Otra/APIClient.swift"]}
    assert hallazgos(monkeypatch, defs, "mobile/Doctor/APIClient.swift", cuerpo) == []


def test_declaracion_def_dentro_de_try_no_es_llamada(monkeypatch):
    cuerpo = """
try:
    def interno(x):
        return x
except ValueError:
    pass
"""
    assert hallazgos(monkeypatch, {"interno": ["backend/otro.py"]}, "backend/nuevo.py", cuerpo) == []


def test_texto_de_una_cadena_no_es_llamada(monkeypatch):
    cuerpo = """
def f():
    try:
        mensaje = "Servicio de IA no disponible (timeout)"  # disponible (aviso)
    except ValueError:
        pass
"""
    assert hallazgos(monkeypatch, {"disponible": ["backend/otro.py"]}, "backend/nuevo.py", cuerpo) == []


def test_llamada_dentro_de_fstring_en_el_try_sigue_marcando(monkeypatch):
    cuerpo = """
def f(d):
    try:
        x = f"valor {ayudante(d)}"
    except ValueError:
        pass
"""
    r = hallazgos(monkeypatch, {"ayudante": ["backend/otro.py"]}, "backend/nuevo.py", cuerpo)
    assert len(r) == 1 and "ayudante()" in r[0]
