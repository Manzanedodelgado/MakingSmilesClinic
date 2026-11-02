"""Tests de polls y media del webhook (sin BBDD ni Evolution reales)."""
from application.services.comunicacion_service import ComunicacionService
from domain.models.comunicacion import PollContexto


def _svc():
    s = ComunicacionService.__new__(ComunicacionService)
    s.session = None
    return s


def test_hash_opcion_determinista():
    h1 = ComunicacionService._hash_opcion("Confirmar")
    h2 = ComunicacionService._hash_opcion("Confirmar")
    assert h1 == h2 and len(h1) == 64


def test_opcion_votada_por_hash():
    svc = _svc()
    opciones = [{"etiqueta": "Confirmar", "accion": "confirmar_cita"},
                {"etiqueta": "Cancelar", "accion": "cancelar_cita"}]
    hashes = {ComunicacionService._hash_opcion(o["etiqueta"]): i for i, o in enumerate(opciones)}
    ctx = PollContexto(centro_id=1, message_id="m1", telefono="34648085696",
                       opciones=opciones, opcion_hashes=hashes)
    poll = {"vote": {"selectedOptions": [ComunicacionService._hash_opcion("Cancelar")]}}
    assert svc._opcion_votada(ctx, poll) == 1


def test_opcion_votada_por_etiqueta():
    svc = _svc()
    opciones = [{"etiqueta": "Sí", "accion": "confirmar_cita"}]
    ctx = PollContexto(centro_id=1, message_id="m1", telefono="x",
                       opciones=opciones, opcion_hashes={})
    assert svc._opcion_votada(ctx, {"selectedOptions": ["Sí"]}) == 0


def test_opcion_votada_no_identificada():
    svc = _svc()
    ctx = PollContexto(centro_id=1, message_id="m1", telefono="x",
                       opciones=[{"etiqueta": "A", "accion": "x"}], opcion_hashes={})
    assert svc._opcion_votada(ctx, {"vote": {"selectedOptions": ["zzz"]}}) is None


def test_extraer_media_detecta_imagen():
    svc = _svc()   # sin sesión → la descarga falla y url=None, pero detecta el tipo
    msg = {"imageMessage": {"caption": "mira", "fileName": None}}
    out = svc._extraer_media(1, msg, {"key": {"id": "x"}})
    assert out["campos"]["media_tipo"] == "image"
    assert out["descripcion"] == "mira"
    assert out["campos"]["media_url"] is None


def test_extraer_media_sin_media():
    svc = _svc()
    out = svc._extraer_media(1, {"conversation": "hola"}, {})
    assert out["campos"] == {}
    assert out["descripcion"] is None
