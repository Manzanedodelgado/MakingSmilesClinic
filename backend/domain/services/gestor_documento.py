"""De un fichero binario al texto de la factura.

Un documento del archivo llega como PDF o como imagen, y puede tener el texto incrustado
(generado por ordenador) o no tenerlo (escaneado o fotografiado). Aquí se resuelve esa
diferencia y se devuelve texto, sin interpretar todavía qué dice.

Facturas que han moldeado este código:
  · 001 · FNMT-RCM 9190455333 — PDF de 225 KB SIN texto incrustado: obliga a rasterizar
    la página y pasarla por OCR. El OCR de layout devuelve el texto en `tool_calls`,
    no en `content`, y con las tablas escritas en LaTeX.
"""
from __future__ import annotations

import base64
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# Un PDF con menos texto que esto es, en la práctica, un escaneado: lo poco que trae son
# metadatos del generador, no el contenido de la factura.
MINIMO_TEXTO_UTIL = 40
ESPERA = 180


class DocumentoIlegible(Exception):
    """El documento no se pudo convertir en texto por ninguna vía."""


# ─────────────────────────── texto incrustado ───────────────────────────

def texto_incrustado(pdf: bytes, nombre: str = "") -> str:
    """El texto que el PDF ya lleva dentro. Cadena vacía si es un escaneado.

    Es gratis e instantáneo frente al OCR, así que siempre se intenta primero. Si el PDF
    está cifrado, se abre con las claves probables antes de leerlo.
    """
    try:
        import fitz                                   # PyMuPDF
    except ImportError:
        return ""
    try:
        with fitz.open(stream=pdf, filetype="pdf") as doc:
            if doc.needs_pass and not any(doc.authenticate(c)
                                          for c in _claves_probables(nombre)):
                return ""
            return "\n".join(p.get_text() for p in doc).strip()
    except Exception:  # raiz: PDF roto → texto vacío
        logger.warning("gestor-documento: PDF roto en texto incrustado (%s)", nombre, exc_info=True)
        return ""


def texto_por_posicion(pdf: bytes, nombre: str = "") -> str:
    """El texto del PDF reordenado por POSICIÓN física, no por flujo de escritura.

    Muchas facturas colocan el valor de un campo a la derecha de su rótulo con una
    coordenada X mayor (`Nr:` .... `M-20902912`, factura de Acquajet). Al extraer el
    texto en orden de escritura ese valor cae lejos del rótulo y se pierde la relación.
    Reagrupando las palabras por su banda horizontal (misma Y) y ordenándolas por X, cada
    línea del papel se reconstruye tal como se ve, y el rótulo recupera su valor.

    Se devuelve como texto de líneas para que el resto del motor lo trate igual que
    cualquier otro; es un COMPLEMENTO del texto incrustado, no lo sustituye.
    """
    try:
        import fitz                                   # PyMuPDF
    except ImportError:
        return ""
    try:
        piezas: list[str] = []
        with fitz.open(stream=pdf, filetype="pdf") as doc:
            if doc.needs_pass and not any(doc.authenticate(c)
                                          for c in _claves_probables(nombre)):
                return ""
            for pagina in doc:
                palabras = pagina.get_text("words")   # x0,y0,x1,y1,texto,bloque,linea,nº
                if not palabras:
                    continue
                # Se agrupan por banda horizontal: dos palabras están en la misma línea
                # del papel si sus Y se solapan (tolerancia de 3 pt, que absorbe el
                # desnivel entre una mayúscula y una minúscula de la misma fila).
                filas: list[tuple[float, list]] = []
                for p in sorted(palabras, key=lambda w: (round(w[1]), w[0])):
                    for y, grupo in filas:
                        if abs(p[1] - y) <= 3:
                            grupo.append(p)
                            break
                    else:
                        filas.append((p[1], [p]))
                for _, grupo in filas:
                    grupo.sort(key=lambda w: w[0])
                    piezas.append(" ".join(w[4] for w in grupo))
        return "\n".join(piezas).strip()
    except Exception:  # raiz: PDF roto → texto vacío
        logger.warning("gestor-documento: PDF roto en extracción posicional", exc_info=True)
        return ""


def _claves_probables(nombre: str) -> list[str]:
    """Contraseñas a probar en un PDF protegido, deducidas del nombre del fichero.

    Un proveedor (Acudent, laboratorio de prótesis) manda sus facturas cifradas con
    `tridental` + el año, en minúsculas. Se generan todas las variantes razonables de
    ese esquema —mayúsculas, año de dos y cuatro cifras, con y sin separador— porque el
    formato exacto varía y probar de más no cuesta nada.
    """
    import re as _re

    anios = _re.findall(r"20\d\d", nombre or "")
    claves: list[str] = [""]                      # la vacía primero: muchos no cifran apertura
    for base in ("tridental", "Tridental", "TRIDENTAL"):
        claves.append(base)
        for a4 in anios:
            a2 = a4[2:]
            for sufijo in (a4, a2):
                for sep in ("", "-", "_", " "):
                    claves.append(f"{base}{sep}{sufijo}")
    for a4 in anios:                              # solo el año
        claves += [a4, a4[2:]]
    return list(dict.fromkeys(claves))            # sin duplicados, en orden


def rasterizar(pdf: bytes, paginas_max: int = 4, escala: float = 2.0,
               nombre: str = "") -> list[bytes]:
    """Convierte las páginas del PDF en imágenes PNG para poder pasarlas por OCR.

    `escala=2.0` dobla la resolución respecto a la nominal: por debajo de eso el OCR
    confunde caracteres en los CIF y en los importes pequeños.
    """
    try:
        import fitz
    except ImportError:
        return []
    imagenes: list[bytes] = []
    try:
        with fitz.open(stream=pdf, filetype="pdf") as doc:
            # Un PDF protegido con contraseña no se puede rasterizar hasta abrirlo. Se
            # prueban las claves probables (vacía, `tridental`+año…). Si ninguna cede, se
            # informa: necesita una clave que no tenemos, no es un fallo del OCR.
            if doc.needs_pass and not any(doc.authenticate(c)
                                          for c in _claves_probables(nombre)):
                raise DocumentoIlegible("PDF protegido con contraseña")
            for pagina in list(doc)[:paginas_max]:
                imagenes.append(pagina.get_pixmap(matrix=fitz.Matrix(escala, escala))
                                .tobytes("png"))
    except DocumentoIlegible:
        raise
    except Exception:  # raiz: PDF ilegible para rasterizar → sin imágenes
        logger.warning("gestor-documento: rasterizado falló", exc_info=True)
        return []
    return imagenes


# ─────────────────────────── OCR ───────────────────────────

def _texto_de_respuesta(datos: dict[str, Any]) -> str:
    """El texto de la respuesta del OCR, venga donde venga.

    Los OCR de layout (`nemoretriever-parse`) devuelven `content: null` y emiten una
    llamada a función cuyos argumentos son los bloques `{bbox, text}` de la página. Leer
    solo `content` daba "documento vacío" con el OCR funcionando perfectamente.
    """
    mensaje = ((datos.get("choices") or [{}])[0].get("message")) or {}

    contenido = mensaje.get("content")
    if isinstance(contenido, str) and contenido.strip():
        return contenido.strip()

    piezas: list[str] = []

    def recorrer(nodo: Any) -> None:
        if isinstance(nodo, dict):
            texto = nodo.get("text")
            if isinstance(texto, str) and texto.strip():
                piezas.append(texto.strip())
            else:
                for valor in nodo.values():
                    recorrer(valor)
        elif isinstance(nodo, list):
            for valor in nodo:
                recorrer(valor)

    for llamada in mensaje.get("tool_calls") or []:
        crudos = ((llamada.get("function") or {}).get("arguments")) or ""
        if not crudos:
            continue
        try:
            recorrer(json.loads(crudos))
        except ValueError:
            piezas.append(str(crudos))            # el argumento ya era el texto

    return "\n".join(piezas).strip()


def _ocr_imagen(base_url: str, api_key: str, modelo: str,
                imagen: bytes, mime: str) -> str:
    """Una llamada de OCR sobre una imagen.

    Los OCR puros rechazan que se les mande texto junto al documento: el mensaje lleva
    la imagen y nada más.
    """
    cuerpo = {
        "model": modelo,
        "messages": [{"role": "user", "content": [{
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{base64.b64encode(imagen).decode()}"},
        }]}],
    }
    respuesta = httpx.post(f"{base_url.rstrip('/')}/chat/completions", json=cuerpo,
                           headers={"Authorization": f"Bearer {api_key}",
                                    "Content-Type": "application/json"},
                           timeout=ESPERA)
    if respuesta.status_code != 200:
        raise DocumentoIlegible(f"ocr {respuesta.status_code}: {respuesta.text[:120]}")
    return _texto_de_respuesta(respuesta.json())


def transcribir(cfg_ocr: dict, binario: bytes, mime: str, nombre: str = "") -> str:
    """El texto de un documento escaneado, mediante OCR.

    Se admite una LISTA de modelos y se combinan sus lecturas: cada OCR falla en cosas
    distintas, y unir lo que leen da un texto más completo que cualquiera por separado.
    Solo se doblan modelos en la PRIMERA página, que es donde están la cabecera con el
    CIF y el bloque de totales; en el resto no aporta y multiplica el coste.
    """
    base_url = str(cfg_ocr.get("base_url") or "")
    api_key = str(cfg_ocr.get("api_key") or "")
    modelos = cfg_ocr.get("models") or ([cfg_ocr["model"]] if cfg_ocr.get("model") else [])
    if isinstance(modelos, str):
        modelos = [modelos]
    if not base_url or not api_key or not modelos:
        raise DocumentoIlegible("OCR sin configurar (base_url, api_key o modelo)")

    if str(mime).startswith("image/"):
        imagenes, tipo = [binario], mime
    else:
        imagenes, tipo = rasterizar(binario, nombre=nombre), "image/png"
    if not imagenes:
        raise DocumentoIlegible("no se pudo rasterizar el documento")

    tareas = [(p, img, m) for p, img in enumerate(imagenes)
              for m in (modelos if p == 0 else modelos[:1])]

    def una(tarea: tuple) -> tuple[int, str]:
        pagina, imagen, modelo = tarea
        try:
            return pagina, _ocr_imagen(base_url, api_key, str(modelo), imagen, tipo)
        except Exception:  # raiz: un modelo de OCR caído no invalida la lectura del otro
            return pagina, ""

    # En paralelo: el OCR es espera de red, no cálculo.
    if len(tareas) > 1:
        with ThreadPoolExecutor(max_workers=min(4, len(tareas))) as pool:
            resultados = list(pool.map(una, tareas))
    else:
        resultados = [una(t) for t in tareas]

    # Ordenado por página, para no romper el orden de lectura del documento.
    texto = "\n".join(t for _, t in sorted(resultados, key=lambda r: r[0]) if t).strip()
    if not texto:
        raise DocumentoIlegible("el OCR no devolvió texto")
    return texto


# ─────────────────────────── entrada única ───────────────────────────

def _trae_importes(texto: str) -> bool:
    """True si el texto contiene el bloque económico de la factura.

    No basta con que haya cifras con céntimos: la cabecera de la factura 012 (Proclinic)
    trae varias y ni un solo importe real, porque el detalle y los totales viven en una
    imagen. Se exige que aparezca algún rótulo económico Y cifras con decimales; si no,
    se rasteriza y se pasa por OCR igual que un escaneado.
    """
    import re as _re
    if len(_re.findall(r"\d+,\d{2}\b", texto)) < 3:
        return False
    return bool(_re.search(r"BASE\s+IMPONIBLE|TOTAL\s+FACTURA|TOTAL\s+A\s+PAGAR|"
                           r"CUOTA\s+IVA|IMPORTE\s+TOTAL|TOTAL\s+BASE|"
                           r"I\.?\s?V\.?\s?A\.?\s*[\d(]|TOTAL\s*[:\s]\s*\d",
                           texto, _re.I))


def _ruta_cache(binario: bytes) -> "Path":
    """Dónde se guarda el texto ya extraído de un documento.

    La clave es el contenido del fichero, no su nombre: el mismo PDF da siempre el mismo
    texto y un fichero distinto nunca colisiona.
    """
    from hashlib import sha256
    from pathlib import Path
    carpeta = Path("/tmp/gestor_ocr")
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta / f"{sha256(binario).hexdigest()[:32]}.txt"


def leer(cfg_ocr: dict, binario: bytes, mime: Optional[str] = None,
         nombre: str = "") -> tuple[str, str]:
    """El texto del documento y cómo se obtuvo ('incrustado' u 'ocr').

    Saber la vía importa: un texto de OCR puede traer caracteres confundidos y las tablas
    en LaTeX, mientras que el incrustado es literal. Quien interpreta después necesita
    saber con cuál de los dos está tratando.
    """
    if not binario:
        raise DocumentoIlegible("documento vacío")

    es_pdf = binario[:4] == b"%PDF"
    if es_pdf:
        texto = texto_incrustado(binario, nombre)
        # Tener texto no basta: hay PDF cuya capa de texto solo trae la cabecera y deja
        # el detalle y los totales en una imagen (factura 012, Proclinic: 2.557
        # caracteres sin un solo importe). Si no aparece el bloque de importes, se
        # rasteriza y se pasa por OCR igual que un escaneado.
        if len(texto) >= MINIMO_TEXTO_UTIL and _trae_importes(texto):
            # El texto en orden de escritura descoloca los valores que van a la derecha de
            # su rótulo (`Nr:` .... `M-20902912`, Acquajet). El posicional reconstruye cada
            # fila del papel y recupera esas relaciones; se prefiere cuando está disponible.
            posicional = texto_por_posicion(binario, nombre)
            if posicional and _trae_importes(posicional):
                return posicional, "incrustado"
            return texto, "incrustado"

    # El OCR NO es determinista: el mismo PDF devuelve textos distintos en cada pasada
    # (medido: 5.683, 5.857 y 5.872 caracteres para el mismo documento). Eso hacía que
    # una factura leída bien fallara al repetirla, y volvía imposible afinar el motor
    # porque el suelo se movía. Guardando la primera lectura, el resultado es
    # reproducible: dos ejecuciones sobre el mismo archivo dan lo mismo.
    cache = _ruta_cache(binario)
    if cache.exists():
        guardado = cache.read_text(encoding="utf-8")
        if guardado.strip():
            return guardado, "ocr"

    texto = transcribir(cfg_ocr, binario,
                        mime or ("application/pdf" if es_pdf else "image/png"), nombre)
    try:
        cache.write_text(texto, encoding="utf-8")
    except OSError:
        pass                            # sin caché se sigue trabajando, solo es más lento
    return texto, "ocr"
