"""ComunicacionService comprueba que el directorio de media WhatsApp admite escritura al
crearse. Con varios workers y peticiones simultáneas, la comprobación no debe fallar."""
from concurrent.futures import ThreadPoolExecutor

from application.services.comunicacion_service import ComunicacionService


def test_inicializacion_concurrente_no_falla():
    with ThreadPoolExecutor(max_workers=16) as ex:
        resultados = list(ex.map(lambda _: ComunicacionService(None), range(400)))
    assert len(resultados) == 400
    restos = list(resultados[0]._MEDIA_DIR.glob(".test*"))
    assert restos == []
