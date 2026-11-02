"""Ollama solo carga JPEG/PNG: el resto de imágenes del correo se convierte o se omite."""
import base64
import io

from PIL import Image

from application.services.gmail_ai_processor import GmailAIProcessor as P


def _b64(fmt: str) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode()


def test_png_y_jpeg_pasan_sin_tocar():
    for fmt in ("PNG", "JPEG"):
        b = _b64(fmt)
        assert P._imagen_para_ollama(b) == b


def test_gif_se_convierte_a_jpeg():
    out = base64.b64decode(P._imagen_para_ollama(_b64("GIF")))
    assert out[:3] == b"\xff\xd8\xff"


def test_svg_o_basura_se_omite():
    svg = base64.b64encode(b"<svg xmlns='http://www.w3.org/2000/svg'/>").decode()
    assert P._imagen_para_ollama(svg) is None
    assert P._imagen_para_ollama("no-es-base64!!") is None
