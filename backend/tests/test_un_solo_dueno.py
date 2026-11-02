"""Una entidad se escribe desde un solo sitio. Si no, este test falla.

El comprobador vive en scripts/check-un-solo-dueno.py y lo ejecuta también el gate del
despliegue. Aquí se repite para que salte en la suite, sin depender de desplegar.
"""
import pathlib
import subprocess
import sys


def test_un_solo_dueno_por_entidad():
    script = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check-un-solo-dueno.py"
    assert script.exists(), f"falta el comprobador: {script}"
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    assert r.returncode == 0, (
        "Una entidad se escribe desde dos sitios. Deja un único dueño "
        "(el resto lee o llama al dueño):\n" + r.stdout + r.stderr
    )
