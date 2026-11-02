"""Cliente ia-dental: error controlado si no hay servicio (la ficha nunca se rompe) y paso correcto de la imagen."""
import httpx
import pytest

from infrastructure import ia_dental_client as c


def test_sin_url_configurada(monkeypatch):
    monkeypatch.setattr(c, "IA_DENTAL_URL", "")
    with pytest.raises(c.IaDentalNoDisponible):
        c.analizar_ortopantomografia(b"x")


def test_servicio_caido(monkeypatch):
    monkeypatch.setattr(c, "IA_DENTAL_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(c, "TIMEOUT", 2)
    with pytest.raises(c.IaDentalNoDisponible):
        c.analizar_ortopantomografia(b"x")


def test_respuesta_ok(monkeypatch):
    monkeypatch.setattr(c, "IA_DENTAL_URL", "http://ia")
    visto = {}
    def falso(url, files, timeout):
        visto["url"], visto["bytes"] = url, files["file"][1]
        return httpx.Response(200, json={"dientes": [], "estructuras": []}, request=httpx.Request("POST", url))
    monkeypatch.setattr(c.httpx, "post", falso)
    assert c.analizar_ortopantomografia(b"img") == {"dientes": [], "estructuras": []}
    assert visto == {"url": "http://ia/analizar", "bytes": b"img"}


# ───────────── depuración de la numeración FDI ─────────────
def _d(fdi, x, y, w=60, h=200, conf=0.8):
    return {"fdi": fdi, "conf": conf, "bbox": [x, y, x + w, y + h]}


def test_depurar_no_toca_una_numeracion_coherente():
    from infrastructure.ia_dental_client import depurar_numeracion
    dientes = [_d("11", 1265, 300), _d("12", 1200, 300), _d("13", 1130, 300),
               _d("21", 1330, 300), _d("22", 1395, 300),
               _d("41", 1300, 600), _d("42", 1235, 600), _d("31", 1365, 600)]
    limpios, quitados = depurar_numeracion(dientes)
    assert quitados == [] and len(limpios) == len(dientes)


def test_depurar_quita_el_duplicado_de_menor_confianza():
    from infrastructure.ia_dental_client import depurar_numeracion
    limpios, quitados = depurar_numeracion([_d("31", 1312, 600, conf=0.41), _d("41", 1306, 600, conf=0.76)])
    assert [d["fdi"] for d in limpios] == ["41"] and quitados[0][0] == "31"


def test_depurar_quita_orden_imposible_en_el_cuadrante():
    from infrastructure.ia_dental_client import depurar_numeracion
    # cuadrante 1 (izquierda de la imagen): el 13 está MÁS cerca de la línea media que el 12 → imposible
    limpios, quitados = depurar_numeracion([_d("11", 1265, 300), _d("12", 1150, 300, conf=0.9),
                                            _d("13", 1215, 300, conf=0.4)])
    assert "13" not in [d["fdi"] for d in limpios] and any("orden imposible" in m for _, m in quitados)


def test_depurar_quita_arcada_contraria_y_no_permanentes():
    from infrastructure.ia_dental_client import depurar_numeracion
    dientes = [_d("11", 1265, 300), _d("12", 1200, 300), _d("41", 1300, 650), _d("42", 1235, 650),
               _d("33", 1000, 250, conf=0.3), _d("51", 1100, 300)]   # 33 «inferior» pero arriba; 51 es temporal
    limpios, quitados = depurar_numeracion(dientes)
    assert {d["fdi"] for d in limpios} == {"11", "12", "41", "42"}
    assert {f for f, _ in quitados} == {"33", "51"}


def test_depurar_respuesta_deja_constancia_para_el_doctor():
    from infrastructure.ia_dental_client import depurar_respuesta
    r = depurar_respuesta({"dientes": [_d("31", 1312, 600, conf=0.4), _d("41", 1306, 600, conf=0.8)],
                           "estructuras": [], "errores": []})
    assert len(r["dientes"]) == 1 and "descartados" in r["errores"][0]
    assert depurar_respuesta({"sin": "dientes"}) == {"sin": "dientes"}
