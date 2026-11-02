"""Hora real de los mensajes de WhatsApp entrantes (29-oct-2026)."""


def test_epoch_valido_acepta_formatos_y_descarta_absurdos():
    import time
    from application.services.comunicacion_service import ComunicacionService as C

    ahora = int(time.time())
    assert C._epoch_valido(ahora - 3600) == ahora - 3600
    assert C._epoch_valido(str(ahora - 3600)) == ahora - 3600
    assert C._epoch_valido({"low": ahora - 60, "high": 0}) == ahora - 60
    assert C._epoch_valido(None) is None
    assert C._epoch_valido("abc") is None
    assert C._epoch_valido(0) is None                  # antes de 2015
    assert C._epoch_valido(ahora + 86400) is None      # futuro: reloj roto → now()
