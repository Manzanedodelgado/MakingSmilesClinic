"""Lectura fiscal determinista de una factura.

Aquí no hay IA: son las reglas que se cumplen SIEMPRE en una factura española y que por
tanto se comprueban con aritmética y con el dígito de control. Lo que no se puede
comprobar, no se afirma.

CÓMO SE BUSCA UN DATO (lección de los tres intentos anteriores)
--------------------------------------------------------------
Reconstruir la geometría de las columnas del OCR es frágil: las cabeceras vienen en
varios pisos, con celdas fundidas y huecos, y cualquier desalineación mete el descuento
donde va la base imponible. Así que NO se reconstruye la tabla. Un dato se busca por su
RÓTULO, en dos formas y por este orden:

  1. En línea:  `TOTAL FACTURA 16,94 EUR`   (factura 001)
  2. En tabla, emparejando DESDE LA DERECHA: la última columna de una fila de totales es
     siempre el importe final, y contando hacia atrás no hay ambigüedad. (factura 002,
     cuya cabecera de dos pisos es imposible de alinear de izquierda a derecha)

Facturas que han moldeado este código:
  · 001 · FNMT-RCM 9190455333 (17/07/2019). NIF con prefijo intracomunitario
    (`ESQ2826004J`), CIF de organismo con control de LETRA (Q), marcas `<br>` y
    `**negritas**`, totales en línea (`TOTAL FACTURA 16,94 EUR`).
  · 002 · GLOBAL UNIFORMS FMAD19-1631 (26/07/2019). CIF del emisor mal leído por el OCR
    (`8-85724607` por `B-85724607`), rótulos con `:` y `{llaves}`, y totales SOLO dentro
    de una tabla con cabecera de dos pisos y descuento por medio.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any


# ─────────────────────────── texto ───────────────────────────

def normalizar(texto: str) -> str:
    """Mayúsculas, sin tildes y con los espacios colapsados.

    'Fecha de emisión' y 'FECHA DE EMISION' son el mismo rótulo, y el OCR alterna entre
    ambas formas dentro del MISMO documento (factura 001). También escribe `I. V. A.`
    con espacios sueltos (factura 002).
    """
    sin_tildes = unicodedata.normalize("NFKD", texto or "")
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_tildes).strip().upper()


def limpiar(texto: str) -> str:
    """El texto del OCR sin sus marcas de formato, listo para buscar por líneas.

    Verificado en ambas facturas: el OCR devuelve saltos como `<br>`, rótulos en
    `**negritas**`, tablas en LaTeX con `&` de separador y `\\\\` de fin de fila. Nada de
    eso está en el papel, y todo estorba para localizar un rótulo.
    """
    limpio = re.sub(r"<br\s*/?>", "\n", texto or "", flags=re.I)
    limpio = re.sub(r"\*\*(.*?)\*\*", r"\1", limpio)
    limpio = re.sub(r"\\(begin|end)\{tabular\}(\{[^}]*\})?", "\n", limpio)
    limpio = re.sub(r"\\multicolumn\{\d+\}\{[^}]*\}", " ", limpio)
    limpio = re.sub(r"\\multirow\{\d+\}\{[^}]*\}", " ", limpio)
    limpio = limpio.replace("\\\\", "\n").replace("&", " ")
    limpio = limpio.replace("{", " ").replace("}", " ")
    # El OCR mete espacios sueltos junto al separador de una fecha (`01- 09-2.019`),
    # lo que la parte en dos y produce lecturas falsas. Se pega el separador a sus
    # cifras cuando queda entre dígitos.
    limpio = re.sub(r"(?<=\d)\s*([/.-])\s*(?=\d)", r"\1", limpio)
    return "\n".join(re.sub(r"[ \t]+", " ", l).strip()
                     for l in limpio.split("\n") if l.strip())


# ─────────────────────────── identificación fiscal ───────────────────────────

_LETRAS_NIF = "TRWAGMYFPDXBNJZSQVHLCKE"      # tabla oficial del dígito de control
_CIF_CONTROL_LETRA = "PQRSNW"                 # organismos: el control es SIEMPRE letra
_CIF_CONTROL_NUMERO = "ABEH"                  # sociedades: el control es SIEMPRE cifra
_MAPA_CONTROL = "JABCDEFGHI"


# Prefijos de país del IVA intracomunitario. `ES` se recorta porque el CIF español vive
# sin él en la base; el resto se CONSERVA, porque en un identificador extranjero el país
# forma parte del dato (DE315480539 no es lo mismo que 315480539).
_PREFIJOS_PAIS = (
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "FI", "FR", "GB", "HR", "HU",
    "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK", "XI",
    "EU",   # las plataformas digitales (DigitalOcean, Paddle) usan el régimen MOSS
)


def normalizar_identificacion(valor: str | None) -> str | None:
    """Forma canónica: sin espacios, guiones ni puntos.

    La FNMT escribe `NIF ESQ2826004J` (el `ES` es el prefijo de IVA intracomunitario, no
    parte del CIF) y Global Uniforms escribe `B-88.393.764`. El `ES` se quita; los demás
    prefijos de país se mantienen porque sí identifican al emisor extranjero.
    """
    if not valor:
        return None
    limpio = re.sub(r"[^0-9A-Za-z]", "", str(valor)).upper()
    if len(limpio) == 11 and limpio.startswith("ES"):
        limpio = limpio[2:]
    return limpio or None


def _valida_espanol(ident: str) -> bool:
    """NIF, NIE o CIF español: 9 caracteres con dígito de control propio."""
    if len(ident) != 9:
        return False

    if ident[:8].isdigit() and ident[8].isalpha():                          # NIF
        return ident[8] == _LETRAS_NIF[int(ident[:8]) % 23]

    if ident[0] in "XYZ" and ident[1:8].isdigit() and ident[8].isalpha():   # NIE
        return ident[8] == _LETRAS_NIF[int(str("XYZ".index(ident[0])) + ident[1:8]) % 23]

    if ident[0].isalpha() and ident[1:8].isdigit():                         # CIF
        pares = sum(int(d) for d in ident[2:8:2])
        impares = sum(sum(divmod(int(d) * 2, 10)) for d in ident[1:8:2])
        digito = (10 - (pares + impares) % 10) % 10
        # La FNMT es Q2826004J: sin este reparto, un CIF de organismo público se
        # rechazaría por no terminar en cifra.
        if ident[0] in _CIF_CONTROL_LETRA:
            return ident[8] == _MAPA_CONTROL[digito]
        if ident[0] in _CIF_CONTROL_NUMERO:
            return ident[8] == str(digito)
        return ident[8] in (str(digito), _MAPA_CONTROL[digito])

    return False


def _valida_nif_portugues(n: str) -> bool:
    """NIF portugués: 9 dígitos, control módulo 11 con pesos 9..2.

    Hace falta porque LUSOBIONIC, LDA (Vizela) factura con NIF 513990623 y sin esto sus
    facturas se quedaban sin identificador fiscal.
    """
    if len(n) != 9 or not n.isdigit():
        return False
    resto = sum(int(d) * (9 - i) for i, d in enumerate(n[:8])) % 11
    control = 0 if resto < 2 else 11 - resto
    return str(control) == n[8]


def _valida_ein(n: str) -> bool:
    """EIN de EE.UU.: 9 dígitos y un prefijo de campus del IRS válido.

    No lleva dígito de control, así que esto es lo único comprobable. Se exige el prefijo
    para no aceptar como identificador fiscal cualquier número de 9 cifras que aparezca en
    una factura (un nº de pedido, un teléfono, un código de cliente).
    """
    if len(n) != 9 or not n.isdigit():
        return False
    # Un NIF portugués también son 9 dígitos, así que los rangos se solapan. Se le da
    # prioridad SOLO en los prefijos donde Portugal es inequívoco: 50-51 y 98 (personas
    # colectivas y no residentes). Ahí, si no supera su dígito de control, no se acepta
    # como EIN — que es lo que hace que `513990624`, el NIF de LUSOBIONIC con el control
    # cambiado, siga rechazándose sin tumbar EIN reales como 93-3636348 o 61-1797223.
    if n[:2] in ("50", "51", "98") and not _valida_nif_portugues(n):
        return False
    p = int(n[:2])
    return (1 <= p <= 6 or 10 <= p <= 16 or 20 <= p <= 27 or 30 <= p <= 35
            or 37 <= p <= 39 or 41 <= p <= 48 or 50 <= p <= 68 or 71 <= p <= 77
            or 80 <= p <= 88 or 90 <= p <= 95 or p in (98, 99))


def _valida_iva_intracomunitario(ident: str) -> bool:
    """Formato del IVA intracomunitario por país (sin dígito de control salvo PT).

    Solo se comprueba la ESTRUCTURA: número de caracteres y qué posiciones son cifra o
    letra según cada país. No todos los estados publican un dígito de control verificable,
    así que aquí la validación es más débil que la española a propósito — y eso es
    preferible a rechazar un identificador real, que es lo que pasaba antes.
    """
    pais, resto = ident[:2], ident[2:]
    if pais not in _PREFIJOS_PAIS or not resto:
        return False

    if pais == "PT":                                    # Portugal sí tiene control
        return _valida_nif_portugues(resto)
    if pais == "DE":                                    # 9 cifras
        return len(resto) == 9 and resto.isdigit()
    if pais == "AT":                                    # U + 8 cifras
        return len(resto) == 9 and resto[0] == "U" and resto[1:].isdigit()
    if pais == "IE":                                    # 8 o 9, mezcla de cifra y letra
        return 8 <= len(resto) <= 9 and resto[0].isdigit() and resto.isalnum()
    if pais == "NL":                                    # 9 cifras + B + 2 cifras
        return len(resto) == 12 and resto[9] == "B" and resto[:9].isdigit()
    if pais == "FR":                                    # 2 alfanuméricos + 9 cifras
        return len(resto) == 11 and resto[2:].isdigit()
    if pais == "IT":                                    # 11 cifras
        return len(resto) == 11 and resto.isdigit()
    if pais == "EU":                                    # régimen MOSS: 9 cifras
        return len(resto) == 9 and resto.isdigit()
    # Resto de la UE: entre 8 y 12 alfanuméricos
    return 8 <= len(resto) <= 12 and resto.isalnum()


def validar_identificacion(valor: str | None) -> bool:
    """True si el identificador supera su propio dígito de control.

    Es la única forma de saber que un CIF leído por OCR es real y no una confusión de
    caracteres, y de distinguirlo de lo que solo se le parece: en la factura 001, el nº
    de pedido 7172527465 y el de cliente 71539489.

    Acepta también identificadores EXTRANJEROS. Rechazarlos era un fallo: el archivo
    tiene 21 facturas de LUSOBIONIC, LDA (Portugal, 21.720 €) que se quedaron sin
    identificador fiscal, más facturas irlandesas (Google, Anthropic, Facebook),
    alemanas (fino data services, AgentFlow AI), austriaca (Dentsply Sirona), holandesa
    (Align Technology) y una brasileña (APPOLLO PUBLICIDADE).
    """
    ident = normalizar_identificacion(valor)
    if not ident:
        return False

    if _valida_espanol(ident):
        return True

    # NIF portugués suelto, sin el prefijo PT: así viene impreso en las facturas de
    # LUSOBIONIC, bajo la dirección de Vizela.
    if len(ident) == 9 and ident.isdigit() and _valida_nif_portugues(ident):
        return True

    # EIN de EE.UU.: 9 dígitos, se escribe NN-NNNNNNN. NO tiene dígito de control, así
    # que solo se puede comprobar la forma. Hace falta para Alphalux Consulting LLC
    # (93-3636348) y para las facturas de Celonis/Make (US EIN 61-1797223).
    # Los dos primeros dígitos son el prefijo de campus del IRS: 01-06, 10-16, 20-27,
    # 30-35, 37-39, 41-48, 50-68, 71-77, 80-88, 90-95, 98-99.
    if len(ident) == 9 and ident.isdigit() and _valida_ein(ident):
        return True

    return _valida_iva_intracomunitario(ident)


# Caracteres que el OCR confunde por tener la misma forma. Se usan SOLO para rescatar un
# identificador que ya viene rotulado como tal pero no valida.
# Cada carácter puede confundirse con VARIOS. El archivo real lo demuestra: `B-03568513`
# por `B63568513` (0 leído como 6) y `8-85724607` por `B85724607` (8 por B).
_CONFUSIONES: dict[str, tuple[str, ...]] = {
    "0": ("O", "6", "8", "9", "D", "Q"),
    "1": ("I", "7", "L"),
    "2": ("Z", "7"),
    "3": ("8",),
    "5": ("S", "6", "8"),
    "6": ("G", "0", "5", "8"),
    "7": ("1", "2"),
    "8": ("B", "0", "3", "5", "6", "9"),
    "9": ("0", "8", "4"),
    "B": ("8", "R", "P"),
    "D": ("0", "O"),
    "G": ("6", "C"),
    "I": ("1", "L"),
    "L": ("1", "I"),
    "O": ("0", "Q", "D"),
    "Q": ("0", "O"),
    "S": ("5",),
    "Z": ("2",),
}


def rescatar_identificacion(bruto: str) -> str | None:
    """Corrige la confusión de UN carácter del OCR, si con ello el identificador valida.

    La factura 002 trae `CIF: 8-85724607` donde el papel dice `B-85724607`; sin este
    rescate el proveedor se pierde entero.

    Solo se acepta el arreglo cuando el resultado supera el dígito de control: eso hace
    imposible inventarse un CIF. Si ninguna variante valida se devuelve None y el
    documento irá a revisión — jamás se registra un identificador dudoso.
    """
    ident = normalizar_identificacion(bruto)
    if not ident:
        return None
    if len(ident) == 9 and validar_identificacion(ident):
        return ident

    # DNI escrito SIN los ceros de relleno: `289.369-Y` es en realidad `00289369Y`. Es
    # habitual en facturas de particulares (el alquiler de Aureliano Melero). Se rellena
    # con ceros a la izquierda hasta 8 cifras + letra, y solo se acepta si valida.
    solo = re.match(r"^(\d{1,8})([A-Z])$", ident)
    if solo:
        candidato = solo.group(1).zfill(8) + solo.group(2)
        if validar_identificacion(candidato):
            return candidato

    # El OCR también DUPLICA caracteres al leer: la factura 019 trae `B-8598377887` y
    # `B-859837787` donde el papel dice `B85937787`. Se prueba quitando los sobrantes,
    # y como siempre solo se acepta si el resultado supera el dígito de control.
    if 9 < len(ident) <= 12:
        validos = {ident[:i] + ident[i + 1:] for i in range(len(ident))}
        while validos and len(next(iter(validos))) > 9:
            validos = {c[:i] + c[i + 1:] for c in validos for i in range(len(c))}
        encontrados = sorted(c for c in validos if validar_identificacion(c))
        # Si más de un recorte valida, el identificador es ambiguo y no se decide.
        return encontrados[0] if len(encontrados) == 1 else None

    if len(ident) != 9:
        return None
    # Solo se corrigen las confusiones LETRA↔CIFRA, no cifra↔cifra.
    #
    # Cambiar una cifra por otra es peligroso: el dígito de control acierta por azar 1 de
    # cada 10 veces, y con 8 posiciones eso significa que casi cualquier número inventado
    # encuentra una "corrección válida". Se comprobó: `12345678X` —que no es un NIF real—
    # salía rescatado como `12345628X`. Eso es fabricar un identificador fiscal.
    #
    # Las confusiones de FORMA (8↔B, 0↔O) sí son seguras: cambian el tipo de carácter, y
    # que además cuadre el dígito de control es prácticamente imposible por casualidad.
    validos: set[str] = set()
    for i, caracter in enumerate(ident):
        for alternativa in _CONFUSIONES.get(caracter, ()):
            if caracter.isdigit() == alternativa.isdigit():
                continue                       # cifra por cifra: no se toca
            candidato = ident[:i] + alternativa + ident[i + 1:]
            if validar_identificacion(candidato):
                validos.add(candidato)
    return validos.pop() if len(validos) == 1 else None


_PATRON_ID = re.compile(
    r"(?<![0-9A-Za-z])"
    r"((?:ES)?[A-HJ-NP-SUVW][-.\s]?(?:\d[-.\s]?){7}[0-9A-J]"        # CIF
    r"|(?:ES)?(?:\d[-.\s]?){8}[A-HJ-NP-TV-Z]"                        # NIF
    r"|(?:ES)?[XYZ][-.\s]?(?:\d[-.\s]?){7}[A-HJ-NP-TV-Z])"           # NIE
    r"(?![0-9A-Za-z])")

# El identificador que sigue al rótulo: exactamente 9 caracteres útiles, admitiendo los
# separadores que mete el emisor (`B-85724607`, `B-88.393.764`). Sin acotarlo así se
# capturaba `B-85724607 El ` con la palabra siguiente pegada y no validaba nada.
# Se capturan hasta 12 caracteres útiles, no exactamente 9: el OCR duplica dígitos
# (factura 019: `B-859837787` por `B85937787`) y `rescatar_identificacion` sabe quitar
# los sobrantes, pero solo si el patrón se los entrega enteros.
_PATRON_ROTULADO = re.compile(
    r"(?:C\.?\s?I\.?\s?F\.?|N\.?\s?I\.?\s?F\.?)\s*(?:/\s*[A-Za-z.]+)?\s*[:\s&]\s*"
    r"((?:ES)?[0-9A-Za-z](?:[-.\s]?[0-9A-Za-z]){8,11})(?![0-9A-Za-z])", re.I)


def identificadores(texto: str) -> list[str]:
    """Los NIF/CIF/NIE válidos del documento, en orden de aparición."""
    vistos: list[str] = []

    def anotar(ident: str | None) -> None:
        if ident and ident not in vistos:
            vistos.append(ident)

    # Las pasadas por RÓTULO se hacen sobre el texto limpio: en las tablas LaTeX el
    # rótulo y su número quedan en celdas distintas (`\multicolumn{2}{c}{DNI:} &
    # 289.369 -Y`, factura 4) y el rótulo no alcanza al número en el texto bruto.
    limpio = limpiar(texto or "")

    # Un NÚMERO DE FACTURA puede tener forma de NIF válido (`Nr: M-20902912`, Acquajet):
    # letra + 8 cifras. Si se cuela como identificador, `emisor()` lo toma por el CIF del
    # proveedor. Se recogen los que van tras un rótulo de número para NO anotarlos.
    numeros_factura = set()
    for m in re.finditer(r"\bNR\s*:\s*([A-Z]?-?\d[A-Z0-9/._-]{2,29})", normalizar(limpio)):
        n = normalizar_identificacion(m.group(1))
        if n:
            numeros_factura.add(n)

    for bruto in _PATRON_ID.findall(texto or ""):
        ident = normalizar_identificacion(bruto)
        if ident and validar_identificacion(ident) and ident not in numeros_factura:
            anotar(ident)

    # DNI de particular escrito sin ceros tras su rótulo (`DNI: 289.369-Y`, alquiler de
    # Aureliano Melero). Se rescata rellenando ceros; el patrón general no lo capta
    # porque tiene menos de 8 cifras.
    for bruto in re.findall(r"\bD\.?\s?N\.?\s?I\.?\s*[:\s]\s*([\d][\d.\s-]{4,10}[A-Za-z])",
                            limpio, re.I):
        anotar(rescatar_identificacion(bruto))

    # Segunda pasada: lo que el emisor ROTULA como CIF/NIF pero no valida, casi siempre
    # por un carácter que el OCR confundió (factura 002). Sobre el texto limpio para que
    # el rótulo alcance su número aunque el LaTeX los separe en celdas distintas.
    for bruto in _PATRON_ROTULADO.findall(limpio):
        norm = normalizar_identificacion(bruto) or ""
        # Se prueba primero con los 9 primeros caracteres —lo normal— y solo si eso no
        # da nada se recurre al recorte de sobrantes. Al revés, un CIF correcto con
        # texto pegado detrás se descartaba por ambiguo (factura 002).
        anotar(rescatar_identificacion(norm[:9]) or rescatar_identificacion(norm))

    # Tercera pasada: candidatos SUELTOS con forma de CIF que no validan. Algunos
    # emisores no rotulan su identificador —lo ponen en el pie, junto al registro
    # mercantil— y el OCR lo corrompe (`B-03568513` por `B63568513`, factura 022).
    if not vistos:
        for bruto in re.findall(r"(?<![0-9A-Za-z])([A-Z][-.\s]?(?:\d[-.\s]?){7}[0-9A-J])"
                                r"(?![0-9A-Za-z])", (texto or "").upper()):
            anotar(rescatar_identificacion(bruto))

    return vistos


def emisor(texto: str, propias: list[str]) -> str | None:
    """El identificador de QUIEN EMITE la factura: el primero que no sea de la clínica.

    Toda factura recibida trae al menos dos (factura 001: Q2826004J de la FNMT y
    B88393764 de Tridental). Tomar el que no toca daría de alta a la propia clínica como
    proveedor de sí misma.

    Devuelve None si todos son propios, y eso NO descarta el documento: hay que buscar al
    emisor por otra vía, porque una factura sin CIF legible sigue siendo una factura.
    """
    propios = {normalizar_identificacion(p) for p in propias if p}
    for ident in identificadores(texto):
        if ident not in propios:
            return ident
    return None


# ─────────────────────────── la clínica nunca es proveedor ───────────────────────────

# La clínica se nombra de varias formas en los documentos que recibe: su razón social
# fiscal (Tridental Odontólogos SLP) y su nombre comercial (Rubio García Dental), que
# además aparece invertido por error en algunos documentos (Dental Rubio García).
# Ninguna de ellas puede darse de alta como proveedor, y una factura suya NO se descarta:
# hay que buscar la siguiente figura fiscal del documento.
DENOMINACIONES_PROPIAS = (
    "TRIDENTAL ODONTOLOGOS",
    "TRIDENTAL",
    "RUBIO GARCIA DENTAL",
    "DENTAL RUBIO GARCIA",
    "CLINICA RUBIO GARCIA",
)

# Formas jurídicas: lo que convierte un nombre en una razón social identificable.
_FORMA_JURIDICA = re.compile(
    r"\b(S\.?\s?L\.?\s?P|S\.?\s?L\.?\s?U|S\.?\s?L|S\.?\s?A\.?\s?U|S\.?\s?A|"
    r"S\.?\s?C\.?\s?P|S\.?\s?COOP|C\.?\s?B)\b\.?")

# Poblaciones que aparecen sueltas en las cabeceras de las facturas del archivo. No son
# nombres de empresa aunque estén escritas en mayúsculas y solas en su línea.
# El OCR las deforma, así que la comparación es tolerante (ver `_parecido`).
_POBLACIONES = {
    "MADRID", "BARCELONA", "VALENCIA", "SEVILLA", "ZARAGOZA", "MALAGA", "MURCIA",
    "ALCORCON", "GETAFE", "MOSTOLES", "LEGANES", "FUENLABRADA", "ALCALA", "HENARES",
    "ARGANDA", "MATARO", "NAVALAFUENTE", "ALCOBENDAS", "POZUELO", "MAJADAHONDA",
    "TORREJON", "PARLA", "COSLADA", "ESPANA", "ESPAÑA", "BILBAO", "GRANADA",
}


def _distancia(uno: str, otro: str) -> int:
    """Cuántas ediciones separan dos palabras (sustituir, insertar o borrar un carácter).

    El OCR comete los tres tipos de error, y el archivo real lo demuestra sobre el mismo
    nombre: ODONTOLOGOS se lee como ODONGOLOGOS (sustitución), ONDONTOLOGOS (inserción)
    y TRIDENTAL como TRIDENTRAL (inserción). Contar solo sustituciones dejaba escapar la
    mitad de las variantes.
    """
    if uno == otro:
        return 0
    previa = list(range(len(otro) + 1))
    for i, letra_uno in enumerate(uno, 1):
        actual = [i]
        for j, letra_otro in enumerate(otro, 1):
            actual.append(min(previa[j] + 1,               # borrar
                              actual[j - 1] + 1,           # insertar
                              previa[j - 1] + (letra_uno != letra_otro)))  # sustituir
        previa = actual
    return previa[-1]


def _parecido(uno: str, otro: str) -> bool:
    """True si dos palabras son la misma con algún carácter mal leído por el OCR.

    Formas REALES del archivo que tienen que reconocerse como la misma clínica:
        TRIDENTAL   -> TRIDENTRAL          (una R de más)
        ODONTOLOGOS -> ODONGOLOGOS         (T por G)
                    -> ONDONTOLOGOS        (una N de más)
                    -> ODONTUULOGOS        (dos letras cambiadas)

    Se tolera hasta un 25% de la longitud en ediciones, con un mínimo de 6 caracteres
    para no emparejar palabras cortas que solo se parecen por casualidad.
    """
    if uno == otro:
        return True
    if min(len(uno), len(otro)) < 6 or abs(len(uno) - len(otro)) > 2:
        return False
    return _distancia(uno, otro) <= max(1, len(otro) // 4)


def es_denominacion_propia(nombre: str | None) -> bool:
    """True si ese nombre es la clínica, en cualquiera de sus formas.

    Se compara sin tildes, sin la forma jurídica y palabra a palabra tolerando las
    confusiones del OCR, porque los emisores y el escáner la escriben de maneras muy
    distintas: 'Tridental Odontólogos S.L.P.', 'TRIDENTAL ODONTOLOGOS SLP',
    'TRIDENTAL ODONGOLOGOS S.L.P', 'TRIDENTAL ODONTOLOGOS LLP'.
    """
    if not nombre:
        return False
    limpio = _FORMA_JURIDICA.sub(" ", normalizar(nombre))
    limpio = re.sub(r"\([^)]*\)", " ", limpio)          # 'S.L.P. (RUBUAL...)'
    limpio = re.sub(r"[^A-Z0-9 ]", " ", limpio)
    palabras = limpio.split()
    if not palabras:
        return False

    for propia in DENOMINACIONES_PROPIAS:
        objetivo = propia.split()
        # Se busca la secuencia de palabras de la denominación propia dentro del nombre,
        # permitiendo que cada una venga con algún carácter corrompido.
        for inicio in range(len(palabras) - len(objetivo) + 1):
            if all(_parecido(palabras[inicio + i], objetivo[i])
                   for i in range(len(objetivo))):
                return True
    return False


# Rótulos del propio formulario de la factura. Ninguno es el nombre de una empresa,
# aunque aparezcan junto a una forma jurídica o en la cabecera.
_NO_SON_NOMBRES = {
    "ORIGINAL", "COPIA", "DUPLICADO", "CLIENTE", "PROVEEDOR", "EMISOR", "DESTINATARIO",
    "ORIGINAL Y COPIA", "CODIGO CLIENTE", "NUMERO CLIENTE", "N CLIENTE", "DATOS FISCALES",
    "DATOS GENERALES", "DATOS DEL CLIENTE", "FACTURAR A", "ENVIAR A", "DIRECCION DE ENVIO",
    "FORMA DE PAGO", "METODO DE PAGO", "VENCIMIENTO", "OBSERVACIONES", "DESCRIPCION",
    "CONCEPTO", "REFERENCIA", "ALBARAN", "PEDIDO", "PRESUPUESTO", "SUBTOTAL",
    "BASE IMPONIBLE", "TOTAL FACTURA", "IMPORTE TOTAL", "SUMA NETO", "TOTAL UNIDADES",
}

# Palabras sueltas que aparecen pegadas a una forma jurídica o en la cabecera y que por
# sí solas no nombran a nadie.
_PALABRAS_SUELTAS = {
    "EUROS", "EURO", "EUR", "TOTAL", "IVA", "IRPF", "BASE", "IMPORTE", "PRECIO",
    "CANTIDAD", "UNIDADES", "FECHA", "PAGINA", "TELEFONO", "MOVIL", "EMAIL", "WEB",
    "BANCO", "CUENTA", "IBAN", "TRANSFERENCIA", "RECIBO", "DOMICILIACION", "CONTADO",
    "CLINICAS", "CLINICA", "LABORATORIO", "DENTAL", "MEDICO", "MEDICA",
}


def _nombre_plausible(candidato: str) -> bool:
    """True si eso puede ser el nombre de una empresa.

    Sin esta criba se registraban como proveedor trozos de dirección y restos del OCR:
    `/ OQ SL`, `CL/Mayor,19`, `Cami del Mig, 71, 1o-2a`, `Original`. Un nombre de empresa
    no lleva números de portal, ni empieza por una vía, ni es una sola palabra genérica.
    """
    limpio = candidato.strip(" ,.:-/|")
    if len(limpio) < 5:
        return False
    normalizado = normalizar(limpio)
    # Direcciones: la vía delante o un número de portal detrás.
    if re.match(r"^(C/|CL/|CL\b|CALLE|AVDA|AVENIDA|PLAZA|PZA|CTRA|CAMI|CAMINO|"
                r"POLIGONO|PASEO|RONDA|TRAVESIA|URB)", normalizado):
        return False
    # Cifras: se rechazan las que delatan una dirección (`nº 41`, `2, 2ºC`, `71, 1o-2a`)
    # pero NO las que forman parte del nombre comercial: 'Dental 360 S.L.',
    # 'Implant Prótesis Dental 2004 S.L.'
    if re.search(r"N[ºO°]\s*\d|\d\s*[ºªO]\b|\d+\s*[-,]\s*\d|,\s*\d", normalizado):
        return False
    if len(re.findall(r"\d", normalizado)) > 4:
        return False
    # Palabras y rótulos que no identifican a nadie: son parte del formulario de la
    # factura, no el nombre de quien la emite.
    if normalizado in _NO_SON_NOMBRES:
        return False
    # Una sola palabra corta y genérica tampoco: 'EUROS' salía como proveedor porque
    # precede a una forma jurídica en la línea de totales.
    if len(limpio.split()) == 1 and normalizado in _PALABRAS_SUELTAS:
        return False
    # Ni una población: las facturas la ponen sola en la cabecera o junto a la provincia
    # ('Navalafuente (Madrid)'). Se compara con tolerancia porque el OCR la deforma
    # ('ALCOROCN' por 'ALCORCON'). Se descarta si TODAS las palabras son poblaciones:
    # así 'Madrid' cae pero 'Dental Madrid Norte' no.
    # Se quitan los paréntesis antes de juzgar: 'Navalafuente (Madrid)' es la población
    # con su provincia, no una empresa.
    sin_parentesis = re.sub(r"\([^)]*\)", " ", normalizado)
    palabras = [p for p in re.split(r"[^A-ZÁÉÍÓÚÑ0-9]+", sin_parentesis) if p]
    if palabras and all(any(_parecido(p, pob) for pob in _POBLACIONES) or len(p) <= 2
                        or p.isdigit() for p in palabras):
        return False
    # Un nombre que acaba en número y solo tiene una palabra antes es una dirección:
    # 'MAYOR 19' es la calle del cliente, no el emisor.
    if len(palabras) <= 2 and palabras and palabras[-1].isdigit():
        return False
    # Palabras que delatan un trozo de dirección aunque no lleve la vía delante:
    # 'MAYOR 19', '(oficinas n.o 1 y 2)', 'Casimiro Escudero local'.
    if re.search(r"\b(LOCAL|OFICINA|OFICINAS|PORTAL|PISO|PLANTA|BAJO|ESCALERA|ESC|"
                 r"PUERTA|PTA|NAVE|EDIFICIO|BLOQUE|APARTADO|APDO|POLIGONO|PARCELA|"
                 r"KM|SN|S/N)\b", normalizado):
        return False
    # Al menos dos letras seguidas y algo que parezca una palabra de verdad.
    return bool(re.search(r"[A-ZÁÉÍÓÚÑ]{3,}", normalizado))


def _emisor_en_clausula_lopd(texto: str) -> str | None:
    """El emisor nombrado en la cláusula de protección de datos.

    Cuando el OCR solo lee al cliente en la cabecera (facturas de Implant Prótesis, donde
    arriba solo sale TRIDENTAL), el emisor aparece igualmente en el texto legal: es el
    'Responsable del Tratamiento'. La ley obliga a nombrarlo con su razón social completa,
    así que es una fuente fiable — `IMPLANT PROTESIS DENTAL 2004, S.L.`
    """
    for patron in (
        r"TRATADOS?\s+POR\s+([A-ZÑÁÉÍÓÚ0-9][A-Za-zÑñÁÉÍÓÚáéíóú0-9 .,&'-]{4,60}?"
        r"\s+S\.?\s?[LA]\.?(?:\s?[PU])?\.?)",
        r"RESPONSABLE\s+DEL\s+TRATAMIENTO[:\s]+([A-ZÑÁÉÍÓÚ][A-Za-zÑñÁÉÍÓÚáéíóú0-9 .,&'-]"
        r"{4,60}?\s+S\.?\s?[LA]\.?(?:\s?[PU])?\.?)",
    ):
        m = re.search(patron, texto, re.I)
        if m:
            candidato = re.sub(r"\s+", " ", m.group(1)).strip(" .,;:")
            if not es_denominacion_propia(candidato):
                return candidato
    return None


def denominacion_emisor(texto: str) -> str | None:
    """El nombre de la empresa que emite, descartando el de la clínica.

    Se buscan las razones sociales del documento —un nombre seguido de su forma
    jurídica— y se devuelve la primera que NO sea la clínica. Si solo aparece la
    clínica, se devuelve None y el documento va a revisión con su CIF: la factura
    existe, lo que falta es ponerle nombre al emisor.
    """
    # En un ARRENDAMIENTO el emisor es el propietario, una persona física sin forma
    # jurídica: se nombra tras "Propietario:" (factura 1, Aureliano Melero Ponce de León).
    # Sin esto, `denominacion_emisor` cogía el primer rótulo con forma jurídica, que es el
    # cliente ("TRIDENTAL ODONTÓLOGOS S.L.P.") o un rótulo del formulario.
    for linea in limpiar(texto).split("\n"):
        m = re.search(r"PROPIETARI[OA]\s*[:\-]?\s*(.+)", normalizar(linea))
        if m:
            # El nombre son las palabras alfabéticas tras el rótulo, hasta que aparezca
            # otra cosa (un rótulo en mayúsculas largo, una cifra o "TOTAL").
            resto = m.group(1)
            nombre = re.match(r"([A-ZÑÁÉÍÓÚ][A-Za-zÑñÁÉÍÓÚáéíóú ]{5,50}?)"
                              r"(?=\s+(?:TOTAL|N\.?I\.?F|C\.?I\.?F|D\.?N\.?I|DOMICILIO|\d)|$)",
                              linea[linea.upper().find("PROPIETARI"):].split(":", 1)[-1].strip())
            if nombre:
                cand = " ".join(nombre.group(1).split())
                if len(cand) >= 6 and not es_denominacion_propia(cand):
                    return cand

    # Preferente: el responsable del tratamiento de la cláusula LOPD. Es donde aparece la
    # razón social completa cuando el OCR no lee el membrete (IPD / Implant Prótesis, cuya
    # cabecera con el logo el OCR se salta).
    por_lopd = _emisor_en_clausula_lopd(texto)
    if por_lopd:
        return por_lopd

    for linea in limpiar(texto).split("\n"):
        for encontrado in _FORMA_JURIDICA.finditer(linea):
            antes = linea[:encontrado.start()].strip(" ,.-:")
            palabras = antes.split()
            # Se toman las palabras de derecha a izquierda mientras parezcan parte del
            # nombre. Se corta en:
            #   · una palabra con cifras -> es una referencia de producto, no un nombre
            #     ('D.3,9 / Alt.10 / OQ SL' en la factura 006);
            #   · una palabra en minúscula -> viene del párrafo anterior, no del rótulo
            #     ('y oposición IMPLANT PROTESIS...' en la factura 008).
            nombre: list[str] = []
            for palabra in reversed(palabras[-6:]):
                limpia = palabra.strip(" ,.:-")
                if not limpia or any(c.isdigit() for c in limpia):
                    break
                # Preposiciones y conjunciones sueltas: vienen del texto anterior, no
                # del nombre ('prestado a través de Fadente S.A.U.' -> 'Fadente S.A.U.').
                if normalizar(limpia) in ("DE", "DEL", "A", "POR", "EN", "Y", "CON",
                                          "PARA", "TRAVES", "LA", "EL", "LOS", "LAS"):
                    break
                # Se admiten cifras solo si forman parte del nombre comercial, como el
                # año en 'IMPLANT PROTESIS DENTAL 2004 S.L.'
                if limpia.islower() and len(limpia) > 2:
                    break
                nombre.insert(0, limpia)
            if not nombre:
                continue
            candidato = " ".join(nombre)
            completo = f"{candidato} {encontrado.group().strip()}".strip()
            if len(candidato) < 4 or es_denominacion_propia(completo):
                continue
            if not _nombre_plausible(candidato):
                continue
            return completo

    # Un PROFESIONAL factura a su nombre, sin forma jurídica: el emisor es una persona.
    # Su nombre aparece junto a su NIF, que es la marca inequívoca (`Fdo.: Dª. IRENE
    # GARCIA SANZ`, `Sergio Sedano Campo ... 71268784H`). Sin esto quedaban registrados
    # con el CIF por nombre, que no identifica a nadie en el directorio.
    lineas = limpiar(texto).split("\n")
    for indice, linea in enumerate(lineas):
        if not re.search(r"\b(?:\d[-.\s]?){8}[A-HJ-NP-TV-Z]\b|"
                         r"\b[XYZ][-.\s]?(?:\d[-.\s]?){7}[A-HJ-NP-TV-Z]\b", linea):
            continue
        # El nombre está en esa línea o ENCIMA, y entre ambos suele ir la dirección
        # completa. La factura 003 lo pone tres líneas más arriba:
        #     Sergio Sedano Campo  /  Travesía del Moral, 4  /  Navalafuente (Madrid)
        #     71.268.784-H
        # Se sube hasta cuatro líneas y se queda con la primera que sea un nombre; las
        # direcciones y poblaciones las rechaza `_nombre_plausible`.
        arriba = [lineas[j] for j in range(indice - 1, max(-1, indice - 5), -1)]
        for texto_nombre in [linea, *arriba]:
            # Una línea de contacto no lleva el nombre: al limpiarle los símbolos, un
            # correo se convierte en palabras y pasaba por nombre de persona
            # ('E mail hvsistemassanitarios gmail com', factura 017).
            if re.search(r"@|WWW\.|HTTP|\.(COM|ES|NET|ORG)\b|\bE-?MAIL\b|\bTEL\b|"
                         r"\bFAX\b|\bMOVIL\b", normalizar(texto_nombre)):
                continue
            limpio = re.sub(r"(?:\d[-.\s]?){8}[A-HJ-NP-TV-Z]|[XYZ][-.\s]?(?:\d[-.\s]?){7}[A-HJ-NP-TV-Z]",
                            " ", texto_nombre)
            limpio = re.sub(r"\b(?:N\.?I\.?F|D\.?N\.?I|FDO|DON|DOÑA|D|Dª|SR|SRA)\b\.?",
                            " ", limpio, flags=re.I)
            limpio = re.sub(r"[^A-Za-zÁÉÍÓÚÑáéíóúñ ]", " ", limpio)
            candidato = " ".join(limpio.split())
            # Un nombre de persona: al menos dos palabras, ninguna genérica.
            if (len(candidato.split()) >= 2 and 8 <= len(candidato) <= 60
                    and _nombre_plausible(candidato)
                    and not es_denominacion_propia(candidato)):
                return candidato

    # Sin forma jurídica a la vista, el emisor es el ENCABEZADO: la primera línea con
    # aspecto de nombre de empresa. Muchas facturas no repiten su razón social completa
    # en la cabecera (`FNMT-RCM`, `Dental 360`), y dejar el proveedor sin nombre obliga
    # después a identificarlo solo por su CIF.
    for linea in limpiar(texto).split("\n")[:8]:
        candidato = linea.strip(" .,:-|")
        normalizado = normalizar(candidato)
        if not (4 <= len(candidato) <= 60):
            continue
        # Se descarta lo que claramente no es un nombre: direcciones, contactos, rótulos
        # del propio documento y cualquier línea con pinta de importe o identificador.
        if re.search(r"\bC/|\bCALLE|\bAVDA|\bTEL|\bFAX|@|WWW|HTTP|"
                     r"\bCIF\b|\bNIF\b|\bFACTURA\b|\bFECHA\b|\bPAGINA\b|\bPRECIO\b|"
                     r"\bPRODUCTO\b|\bCANTIDAD\b|\bTOTAL\b|\bIMPORTE\b|\bPORTES\b|"
                     r"\d{4}", normalizado):
            continue
        # Una sola palabra que es una población no es el nombre del emisor: las facturas
        # ponen la localidad suelta en la cabecera. Se compara con tolerancia porque el
        # OCR la deforma ('ALCOROCN' por 'ALCORCON').
        if len(candidato.split()) == 1 and any(_parecido(normalizado, p)
                                               for p in _POBLACIONES):
            continue
        if es_denominacion_propia(candidato) or not _nombre_plausible(candidato):
            continue
        return candidato
    return None


# ─────────────────────────── importes ───────────────────────────

def cifra(valor: Any) -> Decimal | None:
    """Un importe escrito como lo escriben las facturas españolas.

    El riesgo real es confundir el separador de millar con el decimal: leer `1.234,56`
    como 1,234 divide el importe por mil y falsea la contabilidad. Se decide por la
    POSICIÓN del último separador, no por el carácter, así que valen tanto el formato
    español (`1.234,56`) como el anglosajón (`1,234.56`).
    """
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, (int, float)):
        return Decimal(str(valor))

    texto = str(valor).strip()
    negativo = texto.startswith("-")
    texto = re.sub(r"[^0-9.,]", "", texto)          # fuera €, EUR, %, espacios
    if not any(c.isdigit() for c in texto):
        return None

    ultima_coma, ultimo_punto = texto.rfind(","), texto.rfind(".")
    if ultima_coma >= 0 and ultimo_punto >= 0:
        # Están los dos: el ÚLTIMO en aparecer es el decimal; el otro, el millar.
        if ultima_coma > ultimo_punto:
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    else:
        # Con un solo separador el carácter no dice si es millar o decimal: `1.234` son
        # mil doscientos treinta y cuatro y `1,5` es uno y medio. Manda cuántas cifras
        # le siguen: exactamente 3 = millar. Sin esto, 1.234 € se registraría como 1,23 €.
        texto = texto.replace(",", ".")
        entero, _, decimales = texto.rpartition(".")
        if entero and len(decimales) == 3 and entero.isdigit():
            texto = entero + decimales

    try:
        numero = Decimal(texto)
    except InvalidOperation:
        return None
    return -numero if negativo and numero > 0 else numero


# Un importe: cifras con separador decimal de dos dígitos, o un entero suelto.
_IMPORTE = re.compile(r"-?\d{1,3}(?:[.\s]\d{3})*,\d{2}|-?\d+[.,]\d{2}|-?\d+")


def importes_de(linea: str) -> list[Decimal]:
    """Los importes de una línea, en el orden en que aparecen.

    Se excluyen los porcentajes: `21%` es un tipo impositivo, no una cantidad de dinero,
    y colarlo entre los importes desplaza todo lo demás (factura 002).
    """
    sin_pct = re.sub(r"-?[\d.,]+\s*%", " ", linea or "")
    return [c for c in (cifra(t) for t in _IMPORTE.findall(sin_pct)) if c is not None]


# ─────────────────────────── búsqueda por rótulo ───────────────────────────

def valor_tras_rotulo(texto: str, *rotulos: str) -> Decimal | None:
    """El importe que sigue a un rótulo en su misma línea.

    Es la vía directa cuando el emisor imprime los totales en línea:
    `TOTAL FACTURA 16,94 EUR` (factura 001). Se prueban los rótulos en el orden dado y
    gana el primero que aparezca, así que el llamante los pasa del más específico al más
    genérico ('TOTAL FACTURA' antes que 'TOTAL').

    El rótulo debe estar al PRINCIPIO de la línea: 'TOTAL' dentro de un párrafo legal no
    es un total (factura 002 tiene el pie de registro mercantil lleno de cifras).
    """
    lineas = limpiar(texto).split("\n")

    # a0) Varios rótulos en la MISMA línea, cada uno con su importe detrás:
    #     `BASE IMPONIBLE 10,00 TIPO 21 CUOTA IVA 2,10 PORTES 12,10` (factura 005).
    #     Se corta en el rótulo y se toma el importe que le sigue — no el primero de la
    #     línea, que pertenecería al rótulo anterior.
    for rotulo in rotulos:
        clave = normalizar(rotulo)
        for linea in lineas:
            normalizada = normalizar(linea)
            posicion = normalizada.find(clave)
            if posicion < 0 or normalizada.count(clave) != 1:
                continue
            # El rótulo tiene que empezar palabra: 'TOTAL DCTO.' no es 'TOTAL', e
            # 'IMPORTE TOTAL' seguido del importe del descuento no es el total de la
            # factura (factura 005). Y detrás debe venir la cifra, no otra palabra.
            anterior = normalizada[posicion - 1] if posicion else " "
            if anterior.isalnum() or anterior == ".":
                continue
            # El rótulo también tiene que TERMINAR palabra: 'IVA' no puede casar dentro
            # de 'I.V.A.' partido ni pegado a otra letra. En el alquiler de Aureliano
            # Melero, 'IVA' casaba en la línea del I.R.P.F. y se llevaba su importe.
            fin = posicion + len(clave)
            siguiente_car = normalizada[fin] if fin < len(normalizada) else " "
            if siguiente_car.isalpha():
                continue
            resto = normalizada[posicion + len(clave):]
            # Si tras el rótulo hay un IMPORTE con céntimos, ese es el valor, aunque
            # antes venga el tipo: `I.V.A. 21% 636,93 €` -> 636,93, no 21 (alquiler de
            # Aureliano Melero). El porcentaje no lleva céntimos y se ignora.
            con_centimos = re.search(r"(-?\d{1,3}(?:[.\s]\d{3})*,\d{2}|-?\d+\.\d{2})\b",
                                     resto)
            if con_centimos and re.match(r"[\s:.]*-?\d{1,2}\s*%", resto):
                valor = cifra(con_centimos.group(1))
                if valor is not None:
                    return valor
            siguiente = re.match(r"[\s:.]*(-?\d[\d.,]*)(?![A-Z])", resto)
            if siguiente:
                valor = cifra(siguiente.group(1))
                # Un porcentaje no es un importe: `10,00 %` es el descuento aplicado.
                if valor is not None and not re.match(r"[\s:.]*-?\d[\d.,]*\s*%", resto):
                    return valor

    for rotulo in rotulos:
        clave = normalizar(rotulo)
        for i, linea in enumerate(lineas):
            normalizada = normalizar(linea)
            if not normalizada.startswith(clave):
                continue

            # a) El importe en la MISMA línea: `TOTAL FACTURA 16,94 EUR` (factura 001).
            #    El importe de un total SIEMPRE lleva céntimos; un número redondo pegado
            #    al rótulo suele ser otra cosa —en la factura 091, la línea `total` va
            #    seguida de `Dental 360 S.L.` y el 360 se tomaba por el total—.
            resto = normalizada[len(clave):].strip(" :.")
            # Se admite lo que el emisor intercala entre el rótulo y la cifra: el tipo
            # entre paréntesis (`I.V.A. (21 por 100)`, factura 003) o la palabra 'EUR'.
            if not resto or resto[0].isdigit() or resto[0] == "-" or resto[0] == "(":
                importes = importes_de(_sin_parentesis(linea))
                if importes:
                    return importes[0]

            # b) El importe en la línea SIGUIENTE, cuando el emisor lo alinea a la
            #    derecha y el OCR lo separa (factura 003):
            #        I.V.A. (21 por 100)
            #        220,50 Euros
            if i + 1 < len(lineas):
                siguiente = lineas[i + 1]

                # b1) La línea es una CABECERA de columnas (`... I.R.P.F. I.V.A.`) y la
                #     siguiente son los valores en el mismo orden (`3.033 576,27 636,93`,
                #     alquiler de Aureliano Melero). Se empareja por POSICIÓN: el rótulo
                #     que ocupa el lugar k se lleva la cifra k, no la primera.
                rotulos_linea = re.findall(
                    r"I\.?\s?V\.?\s?A\.?|I\.?\s?R\.?\s?P\.?\s?F\.?|BASE\s+IMPONIBLE|"
                    r"SUBTOTAL|RETENCION|TOTAL", normalizada)
                valores_sig = importes_de(siguiente)
                if len(rotulos_linea) >= 2 and len(valores_sig) >= len(rotulos_linea):
                    # posición de ESTE rótulo entre los de su línea
                    orden = [normalizar(r).replace(" ", "") for r in rotulos_linea]
                    k = next((j for j, r in enumerate(orden)
                              if clave.replace(" ", "") in r or r in clave.replace(" ", "")),
                             None)
                    if k is not None:
                        # los valores suelen venir tras las bases; se toman los últimos
                        base = len(valores_sig) - len(rotulos_linea)
                        idx = base + k if base >= 0 else k
                        if 0 <= idx < len(valores_sig):
                            return abs(valores_sig[idx])

                # b2) Un importe suelto CON CÉNTIMOS, no otro concepto con su cifra: bajo
                #     el rótulo `total` de la factura 091 viene `Dental 360 S.L.` y el 360
                #     se tomaba por el importe.
                if len(normalizar(siguiente)) <= 24 and re.search(r"\d[.,]\d{2}\b",
                                                                  siguiente):
                    importes = importes_de(siguiente)
                    if importes:
                        return importes[0]
    return None


def bloque_rotulos_valores(texto: str, *rotulos: str) -> Decimal | None:
    """El valor de un rótulo cuando la factura imprime TODOS los rótulos seguidos y
    DESPUÉS todos los valores, sin nada que los empareje visualmente.

    Es como salen las facturas cuyo PDF coloca cada celda por coordenadas: al extraer el
    texto se pierde la rejilla y queda (factura 004, Servicopy):

        BASE IMPONIBLE          <- rótulos, uno por línea
        TIPO
        CUOTA IVA
        ...
        TOTAL FACTURA
        12,10 €                 <- y aquí empiezan los valores, en el mismo orden
        10,00
        21
        2,10

    El emparejado se hace por POSICIÓN: el rótulo que ocupa el lugar n de la lista de
    rótulos se corresponde con el valor que ocupa el lugar n de la lista de valores.
    Solo se aplica si las dos listas tienen la misma longitud; si no encajan, se devuelve
    None y el dato se busca por otra vía o queda a revisión. Adivinar aquí sería inventar.
    """
    lineas = [l for l in limpiar(texto).split("\n") if l.strip()]

    # Un rótulo del bloque es una línea SIN cifras; un valor, una línea que es solo cifra.
    solo_rotulo, solo_valor = [], []
    for i, linea in enumerate(lineas):
        n = normalizar(linea)
        if not n:
            continue
        if re.fullmatch(r"-?[\d.,]+\s*(?:€|EUR|EUROS|%)?", n):
            solo_valor.append((i, linea))
        elif len(n) <= 30 and not any(c.isdigit() for c in n):
            solo_rotulo.append((i, n))

    if not solo_rotulo or not solo_valor:
        return None

    # Un documento tiene VARIOS bloques de estos (la cabecera con NUMERO/FECHA/ALBARÁN y,
    # más abajo, el de totales). Se agrupan todos y luego se elige el que contiene el
    # rótulo buscado: quedarse con el primero devolvía el número de albarán como base
    # imponible (factura 004).
    bloques: list[tuple[list[tuple[int, str]], list[tuple[int, str]]]] = []
    rotulos_actual: list[tuple[int, str]] = []
    valores_actual: list[tuple[int, str]] = []
    indices_valor = {i for i, _ in solo_valor}
    indices_rotulo = {i: n for i, n in solo_rotulo}

    for i in range(max(indices_valor | set(indices_rotulo)) + 1):
        if i in indices_rotulo:
            if valores_actual:                      # empieza un bloque nuevo
                bloques.append((rotulos_actual, valores_actual))
                rotulos_actual, valores_actual = [], []
            rotulos_actual.append((i, indices_rotulo[i]))
        elif i in indices_valor:
            valores_actual.append((i, next(l for j, l in solo_valor if j == i)))
    if rotulos_actual and valores_actual:
        bloques.append((rotulos_actual, valores_actual))

    for rotulo in rotulos:
        clave = normalizar(rotulo)
        for nombres, valores in bloques:
            # El emparejado por posición solo vale si hay tantos valores como rótulos.
            if len(nombres) != len(valores) or len(nombres) < 3:
                continue
            for posicion, (_, nombre) in enumerate(nombres):
                if nombre == clave or nombre.startswith(clave):
                    importes = importes_de(valores[posicion][1])
                    if importes:
                        return importes[0]
    return None


def _sin_parentesis(linea: str) -> str:
    """La línea sin lo que va entre paréntesis.

    `I.V.A. (21 por 100) 220,50 Euros` lleva dentro del paréntesis un 21 y un 100 que no
    son importes; sin quitarlos, el primer número de la línea sería 21 en vez de 220,50.
    """
    return re.sub(r"\([^)]*\)", " ", linea or "")


def fila_de_totales(texto: str) -> list[Decimal]:
    """Los importes de la fila de totales de una tabla, LEÍDOS DESDE LA DERECHA.

    Cuando el emisor no imprime los totales en línea, viven en una tabla cuya cabecera
    puede tener varios pisos, celdas fundidas y huecos — imposible de alinear de
    izquierda a derecha sin equivocarse (factura 002):

        TOTAL UNIDADES | SUMA NETO | DTO. GENERAL | BASE IMPON. | I.V.A.    | TOTAL €
                       |           |  %  IMPORTE  |             | % IMPORTE |
        2              | 35,56     |     | 7,82   | 27,74       | 21% | 5,83| 33,57

    Por la derecha, en cambio, el orden es fijo en toda factura española: el último
    importe es el TOTAL, el anterior la cuota de IVA y el anterior la base imponible.
    Devuelve la lista completa, para que el llamante tome los que necesite desde el final.

    Se elige la fila con MÁS importes de entre las que contienen el total del documento,
    que es la fila de cierre y no una línea de detalle.
    """
    candidatas: list[list[Decimal]] = []
    for linea in limpiar(texto).split("\n"):
        # SOLO cuentan las cifras con decimales: un importe de dinero se escribe `27,74`.
        # Sin esta exigencia se colaban el número de serie de la factura 001
        # (296F55A9…, que el OCR parte en cifras) y el teléfono y código postal del pie
        # de la 002 — ninguno es dinero.
        con_decimales = re.findall(r"-?\d{1,3}(?:[.\s]\d{3})*,\d{2}\b|-?\d+\.\d{2}\b", linea)
        if len(con_decimales) < 3:
            continue
        # Un párrafo de texto no es una fila de totales, por muchas cifras que lleve.
        if len(re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{4,}", linea)) > 3:
            continue
        importes = [c for c in (cifra(t) for t in con_decimales) if c is not None]
        if importes:
            candidatas.append(importes)
    if not candidatas:
        return []
    # La fila de cierre es la que más importes reúne; a igualdad, la última del documento.
    return max(candidatas, key=len)


# ─────────────────────────── importes de la factura ───────────────────────────

# 'LÍQUIDO' es como IPD (Implant Prótesis) rotula el total: `Líquido(EUR) 192,50`.
_ROTULOS_TOTAL = ("TOTAL A PAGAR", "TOTAL FACTURA", "IMPORTE TOTAL HONORARIOS",
                  "IMPORTE TOTAL", "LIQUIDO", "TOTAL EUR", "TOTAL")
# 'BASE IVA' y 'B. IMPONIBLE' son variantes reales del rótulo de la base (IPD escribe
# la cabecera 'Base IVA | %IVA | Cuota IVA'). 'IMPORTE NETO' es la base antes de impuestos.
_ROTULOS_BASE = ("TOTAL BASE IMPONIBLE", "BASE IMPONIBLE", "BASE I.V.A.", "BASE IVA",
                 "B. IMPONIBLE", "TOTAL BASE", "SUBTOTAL", "SUMA NETO", "IMPORTE NETO")
# Del más específico al más genérico: 'I.V.A.' (con puntos) antes que 'IVA' a secas,
# porque el genérico casa dentro de otras líneas. En el alquiler de Aureliano Melero,
# buscar 'IVA' cogía el importe de la línea del I.R.P.F.; con 'I.V.A.' delante gana la
# línea correcta.
_ROTULOS_IVA = ("TOTAL IMPUESTOS", "CUOTA I.V.A.", "CUOTA IVA", "TOTAL I.V.A.",
                "TOTAL IVA", "I.V.A.", "IVA")
# El IRPF RESTA del total. Solo lo llevan las facturas de profesionales y las de
# alquiler de inmuebles (factura 003: un abogado, retención del 15%).
_ROTULOS_IRPF = ("RETENCION I.R.P.F.", "RETENCION IRPF", "RETENCION", "I.R.P.F.", "IRPF")


def importes(texto: str) -> dict[str, Decimal | None]:
    """Base, IVA y total de la factura, por las dos vías y en este orden de confianza.

      1. Por RÓTULO en línea. Es la lectura más segura: el emisor ha escrito al lado del
         importe qué es (`TOTAL FACTURA 16,94 EUR`, factura 001).
      2. Por la FILA DE TOTALES leída desde la derecha, cuando el emisor solo los imprime
         dentro de una tabla (factura 002). El orden por la derecha —total, cuota, base—
         es fijo en toda factura española, y por ahí no hay ambigüedad que la cabecera de
         varios pisos sí introduce por la izquierda.

    Lo que no se encuentra se devuelve como None: no se deduce ni se rellena. Un importe
    inventado es peor que un hueco, porque el hueco se ve y el invento no.
    """
    # Cuando el documento dice el TIPO (IVA 21%, IRPF 19%), la cuota es la cifra impresa
    # que cumple base × tipo — no la que está en tal posición. Es la regla más robusta:
    # el OCR desordena las columnas, pero la aritmética no miente. En el alquiler de
    # Aureliano Melero, IVA 21% solo cuadra con 636,93 e IRPF 19% solo con 576,27.
    base_previa = valor_tras_rotulo(texto, *_ROTULOS_BASE)
    iva_por_tipo = cuota_por_tipo(texto, base_previa, ("I.V.A", "IVA"))
    irpf_por_tipo = cuota_por_tipo(texto, base_previa, ("I.R.P.F", "IRPF", "RETENCION"))

    irpf = irpf_por_tipo if irpf_por_tipo is not None else retencion_irpf(texto)
    leidos: dict[str, Decimal | None] = {
        "base": base_previa,
        "iva": iva_por_tipo if iva_por_tipo is not None
        else valor_tras_rotulo(texto, *_ROTULOS_IVA),
        "total": total_por_rotulo(texto),
        # La retención se imprime en negativo (`-157,50`, factura 003) porque resta. Se
        # guarda en positivo: quien cuadra ya sabe que va restando, y con el signo puesto
        # se restaría dos veces.
        "irpf": abs(irpf) if irpf is not None else None,
    }

    # Vía 3: rótulos en bloque y valores después (factura 004).
    if leidos["base"] is None:
        leidos["base"] = bloque_rotulos_valores(texto, *_ROTULOS_BASE)
    if leidos["iva"] is None:
        leidos["iva"] = bloque_rotulos_valores(texto, *_ROTULOS_IVA)
    if leidos["total"] is None:
        leidos["total"] = bloque_rotulos_valores(texto, *_ROTULOS_TOTAL)

    if leidos["base"] is None or leidos["total"] is None:
        fila = fila_de_totales(texto)
        if len(fila) >= 3:
            if leidos["total"] is None:
                leidos["total"] = fila[-1]
            if leidos["iva"] is None:
                leidos["iva"] = fila[-2]
            if leidos["base"] is None:
                leidos["base"] = fila[-3]

    # La base no siempre se rotula: la factura 003 lista los honorarios por conceptos y
    # nunca escribe 'base imponible'. Se deduce de la identidad que SIEMPRE se cumple,
    # nunca inventando: base = total − IVA + IRPF.
    if leidos["base"] is None and leidos["total"] is not None and leidos["iva"] is not None:
        leidos["base"] = (leidos["total"] - leidos["iva"]
                          + (leidos["irpf"] or Decimal("0"))).quantize(Decimal("0.01"))

    # Vía 4: se buscan entre los importes del documento los dos que cuadran con el total
    # a un tipo de IVA legal. Se aplica cuando falta alguno de los dos, y TAMBIÉN cuando
    # lo leído no cuadra: una base que no cuadra es una base mal leída, y la aritmética
    # es mejor testigo que un rótulo mal emparejado.
    #
    # La factura 006 lo demuestra: su cabecera `TOTAL IMP. | DESCUENTO | Base I.V.A. % |
    # IVA | ...` deja el "10,00" del tipo justo debajo de 'Base', y por rótulo se leía
    # base=10,00 con un total de 851,46. Por cuadre salen los 774,05 reales.
    falta = leidos["base"] is None or leidos["iva"] is None
    no_cuadra = (not falta and leidos["total"] is not None
                 and not cuadre(leidos["base"], leidos["iva"], leidos["total"],
                                leidos["irpf"])["cuadra"])
    if leidos["total"] is not None and (falta or no_cuadra):
        pareja = base_e_iva_por_cuadre(texto, leidos["total"])
        if pareja:
            leidos["base"], leidos["iva"] = pareja

    # Vía 5: ni el total está rotulado. Hay facturas que lo imprimen suelto, junto a la
    # fecha de vencimiento (factura 008: `06/10/2019 313,50 313,50`). Se busca el trío
    # base/cuota/total que cierra la aritmética, y solo se acepta si es ÚNICO.
    if leidos["total"] is None or no_cuadra or leidos["base"] is None:
        trio = trio_por_cuadre(texto)
        if trio:
            leidos["base"], leidos["iva"], leidos["total"] = trio
            # Un trío con cuota 0 que no cuadra por suma es una factura con RETENCIÓN y
            # sin IVA (factura 034): la diferencia entre base y total ES la retención.
            if leidos["iva"] == 0 and leidos["irpf"] is None:
                diferencia = (leidos["base"] - leidos["total"]).quantize(Decimal("0.01"))
                if diferencia > 0:
                    leidos["irpf"] = diferencia

    # Base e IVA INTERCAMBIADOS: cuando el desglose viene en columna (`Base IVA | %IVA |
    # Cuota IVA` sobre `175,00 | 10,00 | 17,50`, IPD) el motor puede tomar la cuota por
    # base y al revés. Si hay un tipo impreso, la base es la cifra que multiplicada por
    # ese tipo da la otra: 175 × 10% = 17,50, no al revés. La aritmética los ordena.
    if (leidos["base"] is not None and leidos["iva"] is not None
            and leidos["base"] > 0 and leidos["iva"] > 0):
        b, i = leidos["base"], leidos["iva"]
        # No se exige que el tipo lleve el símbolo %: el OCR a menudo lo pierde ('10,00'
        # suelto bajo la cabecera '%IVA' en las facturas de IPD). Se prueban los tipos
        # legales y se acepta el intercambio solo si UNO ordena las cifras sin ambigüedad:
        # 175 × 10% = 17,50 encaja; 17,50 × 10% = 1,75 no. La cuota es la parte pequeña.
        if i > b:                                    # la 'cuota' es mayor que la 'base'
            for tipo in (Decimal("21"), Decimal("10"), Decimal("4")):
                if abs((i * tipo / 100).quantize(Decimal("0.01")) - b) <= Decimal("0.02"):
                    leidos["base"], leidos["iva"] = i, b   # estaban al revés
                    break

    # Vía 6: el desglose por TIPOS de IVA. Una factura puede llevar varios (21% en unos
    # artículos, 10% en otros) y entonces no hay una sola cuota, sino la suma:
    #
    #     28,26   10,0%    2,83    31,09     (factura 012, Proclinic)
    #    111,38   21,0%   23,39   134,77
    #    ------          ------  -------
    #    139,64           26,22   165,86
    #
    # Leído a un solo tipo, el 28,26 de la primera línea se toma por el total. Sumando
    # el desglose salen la base, la cuota y el total verdaderos.
    desglose = desglose_por_tipos(texto)
    if desglose:
        base_d, iva_d = desglose
        total_d = (base_d + iva_d).quantize(Decimal("0.01"))
        actual_cuadra = (leidos["total"] is not None and cuadre(
            leidos["base"], leidos["iva"], leidos["total"], leidos["irpf"])["cuadra"])
        # El desglose sustituye a lo leído salvo que sea un desglose INCOMPLETO de una
        # factura cuyo total sí conocemos. Dos casos reales que hay que distinguir:
        #
        #   · factura 019: total impreso 1.239,60 y un desglose que solo suma 702,19
        #     -> falta un tramo; sustituir registraría un total falso que cuadra solo.
        #   · factura 012: total mal leído (28,26, que es la base del primer tramo) y un
        #     desglose que suma 165,86 -> aquí manda el desglose, porque el "total"
        #     leído es en realidad una de sus propias líneas.
        #
        # Se distinguen porque en el primero el total impreso es MAYOR que el desglose
        # (falta sumar) y en el segundo es MENOR (se leyó un trozo por el todo).
        impreso = leidos["total"]
        desglose_incompleto = impreso is not None and impreso > total_d + TOLERANCIA
        if not actual_cuadra and not desglose_incompleto:
            leidos["base"], leidos["iva"], leidos["total"] = base_d, iva_d, total_d

    # Factura SIN IVA: no le falta la base, es que no lleva impuesto. Base = total.
    # Se acepta en dos supuestos, y en ninguno se supone nada que el papel no diga:
    #
    #   · el documento DECLARA la exención (factura 025, Ortosol: "exenta de IVA,
    #     Directiva 2006/112/CE"), lo habitual en laboratorios de prótesis dental;
    #   · o no hay NI RASTRO de IVA en todo el texto (factura 071: `Total Factura :
    #     250,00` y ninguna mención al impuesto). Una factura que no nombra el IVA en
    #     ninguna parte no lo lleva; inventarle una base distinta del total sí sería
    #     suponer.
    # Retención deducida del propio cuadre: hay facturas que imprimen el rótulo
    # `Retención IRPF 15%` en un pie muy alejado de su importe, y el emparejado por
    # cercanía no lo alcanza (factura 118: el rótulo está 17 líneas por debajo). Si base
    # y total están leídos y la diferencia entre ambos es un porcentaje legal de la base,
    # esa diferencia ES la retención — y el documento menciona el IRPF, así que no se
    # está suponiendo nada.
    if (leidos["irpf"] is None and leidos["base"] is not None
            and leidos["total"] is not None and (leidos["iva"] or 0) == 0
            and re.search(r"\bI\.?\s?R\.?\s?P\.?\s?F\b|RETENCION", normalizar(texto))):
        diferencia = (leidos["base"] - leidos["total"]).quantize(Decimal("0.01"))
        if diferencia > 0:
            porcentaje = (diferencia * 100 / leidos["base"]).quantize(Decimal("0.1"))
            if porcentaje in (Decimal("15.0"), Decimal("7.0"), Decimal("19.0"),
                              Decimal("21.0"), Decimal("2.0"), Decimal("1.0")):
                leidos["irpf"] = diferencia

    sin_iva = exenta_de_iva(texto) or not re.search(r"\bI\.?\s?V\.?\s?A\b|IMPUESTO",
                                                    normalizar(texto))
    if leidos["base"] is None and leidos["total"] is not None and sin_iva:
        leidos["base"] = leidos["total"]

    # Una factura exenta tiene el IVA a CERO, que no es lo mismo que no haberlo leído:
    # cero es un dato (el impuesto no se aplica) y None es un hueco. La factura 061 es
    # exenta y con retención, así que su base sí se lee y aun así el IVA vale 0,00.
    if leidos["iva"] is None and sin_iva:
        leidos["iva"] = Decimal("0.00")

    # Total NO impreso, pero base/IVA/IRPF sí y por vía fiable (cuota por su tipo). En un
    # recibo de alquiler con retención el total no se rotula (factura 4): su valor es la
    # identidad fiscal base + IVA − IRPF, que no se inventa, se calcula. Se aplica solo
    # cuando lo leído como total es None o NO cuadra, y el IVA se obtuvo por su tipo.
    total_ausente = (leidos["total"] is None
                     or not cuadre(leidos["base"], leidos["iva"],
                                   leidos["total"], leidos["irpf"])["cuadra"])
    if (total_ausente and iva_por_tipo is not None
            and leidos["base"] is not None and leidos["iva"] is not None):
        calc = (leidos["base"] + leidos["iva"]
                - (leidos["irpf"] or Decimal("0"))).quantize(Decimal("0.01"))
        # Solo si NO había un total impreso que cuadre por su cuenta: nunca se pisa un
        # total real leído; solo se rellena el hueco o se corrige un total imposible.
        if leidos["total"] is None or leidos["total"] != calc:
            leidos["total"] = calc

    return leidos


# Una línea de desglose: base, tipo y cuota. El símbolo % es opcional porque muchos
# emisores lo ponen solo en la cabecera de la columna (factura 019: `488,55 10,0 48,86`).
# El tipo se distingue de un importe por no llevar céntimos: `10,0` y no `10,00`.
_LINEA_TIPO = re.compile(
    r"^\s*(-?[\d.]+,\d{2})\s+(\d{1,2}(?:[.,]\d)?)\s*%\s+(-?[\d.]+,\d{2})"
    r"|^\s*(-?[\d.]+,\d{2})\s+(\d{1,2}[.,]\d)\s+(-?[\d.]+,\d{2})")


def desglose_por_tipos(texto: str) -> tuple[Decimal, Decimal] | None:
    """Base y cuota TOTALES de una factura con varios tipos de IVA.

    Devuelve la suma de las bases y la suma de las cuotas, aceptándolas solo si cada
    línea es coherente consigo misma (cuota = base × tipo). Esa comprobación es la que
    impide confundir una línea de artículo con una de desglose: en un artículo, el
    número que sigue al precio no es un porcentaje de él.

    None si no hay al menos una línea válida: sin desglose no se inventa nada.
    """
    lineas = limpiar(texto).split("\n")
    bases: list[Decimal] = []
    cuotas: list[Decimal] = []

    # a0) El desglose escrito EN PROSA, que es como lo redactan bancos y aseguradoras:
    #        `Importe IVA 21,00 % 5,73 sobre la base de 27,31`   (factura 039, BNP)
    #     Leída por posición, esa línea da base 21,00 (que es el tipo) y total 27,31
    #     (que es la base). La frase, en cambio, dice exactamente qué es cada cifra.
    for linea in lineas:
        prosa = re.search(
            r"IVA\s+(\d{1,2}(?:[.,]\d{1,2})?)\s*%\s+(-?[\d.]+,\d{2})"
            r"\s+SOBRE\s+LA\s+BASE\s+(?:DE\s+)?(-?[\d.]+,\d{2})",
            normalizar(linea))
        if not prosa:
            continue
        tipo = cifra(prosa.group(1).replace(",", "."))
        cuota = cifra(prosa.group(2))
        base = cifra(prosa.group(3))
        if None in (tipo, cuota, base) or tipo not in TIPOS_IVA:
            continue
        if abs((base * tipo / 100).quantize(Decimal("0.01")) - cuota) <= Decimal("0.02"):
            bases.append(base)
            cuotas.append(cuota)
    if bases:
        return sum(bases), sum(cuotas)

    # a) El desglose en una sola línea: `28,26  10,0%  2,83  31,09`
    for linea in lineas:
        encontrado = _LINEA_TIPO.match(linea.strip())
        if not encontrado:
            continue
        # El patrón tiene dos alternativas (con y sin el símbolo %); se toma la que casó.
        grupos = encontrado.groups()
        crudos = grupos[:3] if grupos[0] is not None else grupos[3:]
        base = cifra(crudos[0])
        tipo = cifra(str(crudos[1]).replace(",", "."))
        cuota = cifra(crudos[2])
        if None in (base, tipo, cuota) or tipo not in TIPOS_IVA:
            continue
        if abs((base * tipo / 100).quantize(Decimal("0.01")) - cuota) <= Decimal("0.02"):
            bases.append(base)
            cuotas.append(cuota)

    # a2) El desglose repartido en VARIAS líneas, con el total en la primera y los tramos
    #     siguientes debajo (factura 019, Dentales):
    #         0,00   488,55   10,0   48,86   1.239,60
    #                580,32   21,0  121,87
    #     La primera línea casa el patrón por su segundo importe, pero el tramo de abajo
    #     hay que sumarlo o la base queda a la mitad. Se recogen TODOS los tramos que
    #     cumplan cuota = base × tipo, vengan donde vengan.
    if True:
        for linea in lineas:
            # El tipo puede venir con céntimos (`21,00` en vez de `21,0`), y entonces es
            # indistinguible de un importe por su forma (factura 042, Implant Prótesis:
            # `743,50  341,25  21,00  71,66`). Lo desempata la aritmética: solo se
            # acepta el trío si la cuota es de verdad ese porcentaje de esa base.
            for encontrado in re.finditer(
                    r"(-?[\d.]+,\d{2})\s+(\d{1,2}[.,]\d{1,2})\s*%?\s+(-?[\d.]+,\d{2})",
                    linea):
                base = cifra(encontrado.group(1))
                tipo = cifra(encontrado.group(2).replace(",", "."))
                cuota = cifra(encontrado.group(3))
                if None in (base, tipo, cuota) or tipo not in TIPOS_IVA or base == 0:
                    continue
                if base in bases:                       # ya contabilizado
                    continue
                if abs((base * tipo / 100).quantize(Decimal("0.01")) - cuota) <= Decimal("0.02"):
                    bases.append(base)
                    cuotas.append(cuota)

    # b) El desglose EN COLUMNA, una cifra por línea (factura 012, Proclinic):
    #        28,26 / 10,0% / 2,83 / 31,09
    #       111,38 / 21,0% / 23,39 / 134,77
    #    Se detecta por el porcentaje: la cifra ANTERIOR es su base y la POSTERIOR su
    #    cuota. Se acepta cada trío solo si la cuota es realmente ese % de esa base, lo
    #    que descarta cualquier coincidencia casual.
    #
    #    Se prueba SIEMPRE, no solo cuando las otras formas fallan: una factura con dos
    #    tipos puede tener el desglose en columna (012) o en líneas sueltas (019), y
    #    quedarse con la primera forma que casa dejaba la otra a medias. Al final gana
    #    la lectura más completa.
    en_columna_bases: list[Decimal] = []
    en_columna_cuotas: list[Decimal] = []
    if True:
        for i, linea in enumerate(lineas):
            # El símbolo % es opcional: hay emisores que lo ponen solo en la cabecera de
            # la columna y dejan el tipo suelto (factura 033: la línea es `10,0`). Se
            # distingue de un importe porque no lleva céntimos: `10,0` y no `10,00`.
            porcentaje = re.fullmatch(r"\s*(\d{1,2}(?:[.,]\d)?)\s*%\s*", linea) or \
                re.fullmatch(r"\s*(\d{1,2}[.,]\d)\s*", linea)
            if not porcentaje or i == 0 or i + 1 >= len(lineas):
                continue
            tipo = cifra(porcentaje.group(1).replace(",", "."))
            base = cifra(lineas[i - 1])
            cuota = cifra(lineas[i + 1])
            # base != 0: en un abono la base es negativa y sigue siendo válida.
            if None in (base, tipo, cuota) or tipo not in TIPOS_IVA or base == 0:
                continue
            if abs((base * tipo / 100).quantize(Decimal("0.01")) - cuota) <= Decimal("0.02"):
                en_columna_bases.append(base)
                en_columna_cuotas.append(cuota)

    # Gana la forma que MÁS tramos ha reunido: es la lectura completa del desglose.
    if len(en_columna_bases) > len(bases):
        bases, cuotas = en_columna_bases, en_columna_cuotas

    # NO se intenta reconstruir desgloses desordenados probando combinaciones de cifras.
    # Se probó con la factura 010 (`172,50  27,50  21,00  5,78` en una línea y
    # `145,00  10,00  14,50` en otra) y el resultado fue peor que el problema: salían
    # tríos que cumplen la aritmética por casualidad y producen un total FALSO que
    # además cuadra — un dato inventado que ya nadie vuelve a mirar. Esas facturas van
    # a revisión, que es un fallo visible y no un error silencioso en la contabilidad.

    if not bases:
        return None
    return sum(bases), sum(cuotas)


_EXENCION = re.compile(
    r"EXENT[AO]S?\s+DE\s+I\.?\s?V\.?\s?A|"
    r"EXENCION\s+DE\s+I\.?\s?V\.?\s?A|"
    r"NO\s+SUJET[AO]\s+A\s+I\.?\s?V\.?\s?A|"
    r"DIRECTIVA\s+2006/112|"
    r"ART[IÍ]CULO\s+20\b.{0,40}EXENC")


# Documentos que llegan al archivo y NO son facturas: tarifarios, comunicaciones de la
# Seguridad Social, contratos, presupuestos. Tienen cifras y hasta membrete de empresa,
# pero no documentan una operación cobrada.
_NO_ES_FACTURA = (
    "TARIFAS PARA", "LISTA DE PRECIOS", "LISTADO DE PRECIOS", "CATALOGO DE PRECIOS",
    "COMUNICACION SOBRE", "TESORERIA GENERAL DE LA SEGURIDAD SOCIAL",
    "CONTRATO DE TRABAJO", "PRESUPUESTO N", "OFERTA COMERCIAL", "ALBARAN DE ENTREGA N",
)


# TODAS las palabras que declaran un documento de cobro, en los idiomas y variantes que
# llegan al archivo. La palabra NO tiene por qué ser 'factura': un ticket, una nómina, un
# recibo o un 'invoice' son igual de contables. Se contemplan singular y plural, con y sin
# tilde, y las formas de otros idiomas (portugués, inglés, italiano, francés).
_ES_DOCUMENTO_DE_COBRO = re.compile(
    r"\bFACTURAS?\b|\bFACT\b|\bFRA\b|\bFRAS\b|\bF[ºO]\b|"
    r"\bFATURAS?\b|\bINVOICES?\b|\bRECEIPTS?\b|\bBILLS?\b|"
    r"\bFATTURAS?\b|\bRECHNUNGS?\b|\bTICKETS?\b|\bTIQUES?\b|\bTIQUETS?\b|"
    r"\bABONOS?\b|\bRECTIFICATIVAS?\b|\bNOTA\s+DE\s+CR[EÉ]DITO\b|\bCREDIT\s+NOTE\b|"
    r"\bNOMINAS?\b|\bN[OÓ]MINAS?\b|\bRECIBOS?\b|\bMINUTA\b|\bHONORARIOS\b|"
    r"\bN\.?[ºO]\s*FACTURA\b|\bNUM(ERO)?\s+DE\s+FACTURA\b")

# Documentos contables que NO son factura pero SÍ son un gasto imputable: impuestos,
# Seguridad Social, nóminas, recibos. La contabilidad no son solo facturas.
_ES_GASTO = re.compile(
    r"\bMODELO\s*\d{2,3}\b|\bIMPUESTO\b|\bI\.?\s?R\.?\s?P\.?\s?F\b|"
    r"\bSEGURIDAD\s+SOCIAL\b|\bTGSS\b|\bAEAT\b|\bCOTIZACION\b|"
    # `N\s?MINA` tolera que el nombre haya perdido la vocal ('N_MINA' -> 'N MINA').
    r"\bN\s?[OÓ]?MINA\b|\bNOMINAS?\b|\bRECIBO\b|\bLIQUIDACION\b|\bAUTOLIQUIDACION\b|"
    r"\bCUOTA\s+DE\s+AUT[OÓ]NOMOS\b|\bALQUILER\b|\bARRENDAMIENTO\b|"
    r"\bTASA\b|\bRESIDUOS\b|\bSUMINISTRO\b|\bP[OÓ]LIZA\b|\bSEGURO\b|\bPRIMA\b")

# Lo que de verdad NO se contabiliza: correos reenviados, avisos, dudas, notificaciones,
# presupuestos y comunicaciones. Aquí no hay un gasto que imputar.
_NO_CONTABLE = re.compile(
    r"^RE\b|^RV\b|^FWD\b|\bDUDAS\b|\bAVISO\b|\bNOTIFICACION(ES)?\s+PENDIENTES\b|"
    r"\bSOLICITUD\b|\bPRESUPUESTO\b|\bLISTA\s+DE\s+PRECIOS\b|\bTARIFAS\b|"
    r"\bCOMUNICACION\b|\bCERTIFICADO\b|\bPENDIENTES?\s+DE\s+RECIBIR\b")


def es_documento_contable(texto: str, nombre: str = "",
                          propias: list[str] | None = None) -> bool:
    """True si el documento debe entrar en la contabilidad.

    La contabilidad NO son solo facturas: son gastos. Una nómina, un modelo de Hacienda,
    un recibo de la Seguridad Social o del alquiler son gastos imputables aunque no
    lleven la palabra 'factura'. Descartarlos por no ser factura era el error de fondo.

    Entra si:
      · se declara factura/fatura/invoice/abono, o
      · es un documento de gasto reconocible (impuesto, nómina, recibo, alquiler), o
      · tiene ESTRUCTURA de factura: CIF de un tercero + importes con céntimos + total.

    Queda fuera lo que no imputa nada: correos reenviados, avisos, dudas, presupuestos,
    notificaciones y comunicaciones — salvo que además se identifiquen como factura.
    """
    normalizado = normalizar(texto)
    # El nombre del fichero es una PISTA, no prueba: solo se usa para reconocer el tipo
    # de gasto, nunca para afirmar el contenido. Los guiones bajos y otros separadores del
    # nombre se pasan a espacio para que 'MODELO_111' case con el patrón 'MODELO 111'.
    nombre_norm = re.sub(r"[_.\-/]+", " ", normalizar(nombre))
    contexto = normalizado + " " + nombre_norm

    dice_factura = bool(_ES_DOCUMENTO_DE_COBRO.search(contexto))

    # Un correo reenviado (Fwd/Re/RV) o una consulta (dudas) NO es un documento contable,
    # aunque su cuerpo cite un CIF y cifras: es un mensaje que HABLA de facturas, no una.
    # El prefijo del asunto lo delata y veta el documento entero.
    if re.search(r"\b(FWD|RE|RV)\b|\bDUDAS?\b|\bCONSULTA\b", nombre_norm) \
            and not _ES_DOCUMENTO_DE_COBRO.search(nombre_norm):
        return False

    # Aviso/presupuesto/certificado/notificación/tarifa sin declararse factura: fuera,
    # aunque mencione impuestos o la AEAT ('NOTIFICACIONES PENDIENTES AEAT' es un aviso).
    if _NO_CONTABLE.search(nombre_norm) and not dice_factura:
        return False
    if any(m in normalizado for m in _NO_ES_FACTURA) and not dice_factura \
            and not _ES_GASTO.search(contexto):
        return False

    # Un aviso o notificación NUNCA es un gasto, aunque nombre a la AEAT o un impuesto.
    if re.search(r"\bNOTIFICACION(ES)?\b|\bAVISO\b|\bRECORDATORIO\b|\bPENDIENTES?\b",
                 nombre_norm) and not dice_factura:
        return False

    # Es un gasto reconocible (impuesto, nómina, recibo…): entra.
    if _ES_GASTO.search(contexto):
        return True

    ids = identificadores(texto)
    # Se declara documento de cobro (en el texto O en el nombre del fichero): es
    # contable. No se exige además el CIF aquí — se leerá del contenido al procesarlo;
    # que el emisor no sea legible es motivo de REVISIÓN, no de descarte.
    if dice_factura:
        return True

    # Sin la palabra pero con estructura de factura (Media Markt): CIF de tercero +
    # varios importes con céntimos + un total.
    terceros = [i for i in ids if normalizar_identificacion(i) not in
                {normalizar_identificacion(p) for p in (propias or []) if p}]
    if terceros:
        importes = len(re.findall(r"\d+[,.]\d{2}\b", texto or ""))
        tiene_total = bool(re.search(r"\bTOTAL\b|\bIMPORTE\b|\bBASE\s+IMPONIBLE\b|"
                                     r"\bI\.?\s?V\.?\s?A\b|\bAMOUNT\b", normalizado))
        if importes >= 3 and tiene_total:
            return True

    return False


_ROTULOS_NUMERO = ("FACTURA NUMERO", "NUMERO FACTURA", "NUM FACTURA", "N FACTURA",
                   "No FACTURA", "Nº FACTURA", "NR FACTURA", "FACTURA N", "FACTURA NO",
                   "FACTURA NUM", "FACTURA SIMPLIFICADA N", "FRA N", "FACTURA")


def numero_factura(texto: str) -> str | None:
    """El número de la factura.

    Se busca tras el rótulo y se exige que contenga alguna cifra: `FACTURA 0000216626`,
    `nr. factura: 20123`, `Factura número 012/2019`. Se admiten letras y separadores
    porque muchas series los llevan (`FMAD19-1631`, `MCA202010`, `A-2.020_613`).
    """
    lineas = limpiar(texto).split("\n")

    def valido(candidato: str) -> str | None:
        candidato = candidato.strip(" .:-_")
        # Un número de factura lleva cifras; si no, se ha capturado otra palabra.
        if not candidato or not any(c.isdigit() for c in candidato):
            return None
        # Ni una fecha ni un importe son un número de factura.
        if re.fullmatch(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", candidato):
            return None
        if re.fullmatch(r"[\d.]+,\d{2}", candidato):
            return None
        return candidato

    # Rótulo `Nr:` a secas (facturas con software internacional, Acquajet: `Nr:
    # M-20902912`). Se exige el DOS PUNTOS pegado para no capturar `Nr Contrato`, `Nr
    # NIF` ni `Nº Web`, que llevan otra palabra entre medias. Va antes del bucle general
    # porque `Nr` no está entre los rótulos largos y su valor es fiable.
    for linea in lineas:
        m = re.search(r"\bNR\s*:\s*([A-Z]?-?\d[A-Z0-9/._-]{2,29})", normalizar(linea))
        if m:
            candidato = valido(m.group(1))
            if candidato:
                return candidato

    for rotulo in _ROTULOS_NUMERO:
        clave = normalizar(rotulo)
        for indice, linea in enumerate(lineas):
            normalizada = normalizar(linea)
            posicion = normalizada.find(clave)
            if posicion < 0:
                continue

            # a) El número en la misma línea que el rótulo.
            resto = normalizada[posicion + len(clave):]
            encontrado = re.match(r"[\s:.ºNO°-]*([A-Z0-9][A-Z0-9/._-]{2,29})", resto)
            if encontrado:
                candidato = valido(encontrado.group(1))
                if candidato:
                    return candidato

            # b) El rótulo SOLO en su línea y el número debajo. Es lo más frecuente en
            #    las facturas escaneadas, donde la cabecera se parte por columnas
            #    (facturas 005, 008, 010: una línea con `FACTURA` y nada más).
            if not re.search(r"\d", normalizada) and indice + 1 < len(lineas):
                siguiente = normalizar(lineas[indice + 1]).strip()
                encontrado = re.fullmatch(r"[\s:.ºNO°-]*([A-Z0-9][A-Z0-9/._-]{2,29})",
                                          siguiente)
                if encontrado:
                    candidato = valido(encontrado.group(1))
                    if candidato:
                        return candidato

    # Cabecera en COLUMNAS: una fila de rótulos `Serie Número Fecha [Cliente]` y debajo
    # la de valores `A 69584 30/10/2019 [408740]` (factura de IPD/Implant Prótesis). El
    # número es el valor que cae bajo la columna 'Número'. Se localiza por su POSICIÓN de
    # palabra en la fila de rótulos y se toma esa misma posición en la de valores.
    for indice, linea in enumerate(lineas):
        rotulos = normalizar(linea).split()
        if "NUMERO" not in rotulos or indice + 1 >= len(lineas):
            continue
        col = rotulos.index("NUMERO")
        valores = lineas[indice + 1].split()
        if col < len(valores):
            candidato = valido(valores[col])
            # Ha de ser plausible como número y la fila de valores traer también una fecha,
            # lo que confirma que es la fila de datos de la cabecera y no otra cualquiera.
            if candidato and re.search(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", lineas[indice + 1]):
                return candidato

    # Recibo de alquiler: no lleva "Factura Nº", su identificador es el número de
    # recibo NN/NN de la cabecera (recibo 02 de 60 mensualidades → 02/60). Lo delata
    # que aparece dos veces (una por cada copia de la tabla) y que hay "Propietario:"
    # o "Renta"/"Aumentos legales", exclusivos de un recibo de arrendamiento.
    if re.search(r"PROPIETARI[OA]|AUMENTOS LEGALES", normalizar(texto)):
        for m in re.finditer(r"(?<!\d)(\d{1,3}/\d{1,3})(?!\d)", limpiar(texto)):
            recibo = m.group(1)
            n, total = (int(x) for x in recibo.split("/"))
            # Un recibo real es "n de total" con 1<=n<=total y total plausible (<=600).
            if 1 <= n <= total <= 600:
                return recibo

    return None


def numero_del_nombre(nombre: str | None) -> str | None:
    """El número de factura que viene en el NOMBRE del fichero.

    El archivo tiene los documentos nombrados `fecha_interno_PROVEEDOR_numero.pdf`
    (`2019-08-12_239_SERVICOPY_75581.pdf`). Cuando el OCR no logra leer la cabecera, ese
    nombre es el único sitio donde queda el número — y lo escribió una persona al
    archivar, así que es fiable.

    Es un metadato, no el documento: solo se usa como último recurso y así se anota.
    """
    if not nombre:
        return None
    # Las extensiones pueden venir DUPLICADAS (`...20190930.pdf.pdf`): se quitan todas.
    base = re.sub(r"(\.(pdf|png|jpe?g|tiff?))+$", "", nombre.strip(), flags=re.I)
    partes = [p for p in base.split("_") if p]
    if len(partes) < 3:
        return None
    ultimo = partes[-1].strip()
    if not any(c.isdigit() for c in ultimo) or len(ultimo) > 30:
        return None
    # La primera parte es la fecha del archivo, no un número de factura.
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", ultimo):
        return None
    # Tampoco es número una FECHA pegada como AAAAMMDD (`20190930`): muchos ficheros del
    # archivo llevan la fecha al final en vez del número real, y tomarla registraría un
    # "número" que en realidad es una fecha. Se descarta si esos 8 dígitos son una fecha.
    solo_digitos = re.sub(r"\D", "", ultimo)
    if re.fullmatch(r"20\d{6}", solo_digitos):
        a, m, d = int(solo_digitos[:4]), int(solo_digitos[4:6]), int(solo_digitos[6:8])
        if 2000 <= a <= 2100 and 1 <= m <= 12 and 1 <= d <= 31:
            return None
    return ultimo


_MESES = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
          "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11,
          "DICIEMBRE": 12}


def fecha_emision(texto: str) -> str | None:
    """La fecha de emisión, en formato ISO (`2019-07-17`).

    Se prueban las tres formas en que las escriben las facturas españolas:
    `17/07/2019`, `31.08.2020` y `1 de agosto de 2.019` (factura 003).
    Se prefiere la que sigue a un rótulo de fecha; si no hay rótulo, la primera del
    documento, que es la de cabecera.
    """
    lineas = limpiar(texto).split("\n")

    def a_iso(dia: str, mes: str, anio: str) -> str | None:
        try:
            d, m = int(dia), int(mes)
            a = int(re.sub(r"[^\d]", "", anio))
        except ValueError:
            return None
        if a < 100:
            a += 2000
        if not (1 <= d <= 31 and 1 <= m <= 12 and 2000 <= a <= 2100):
            return None
        return f"{a:04d}-{m:02d}-{d:02d}"

    # Prioridad del rótulo: 2 = fecha de la factura, 1 = un 'fecha' cualquiera,
    # 0 = sin rótulo. Un documento trae varias fechas (envío, pedido, vencimiento) y la
    # que vale es la de emisión: la factura 012 lleva `FECHA FACTURA`, `FECHA ENVIO` y
    # `FECHA PEDIDO` seguidas, y sin prioridad se tomaba la que tocara.
    candidatas: list[tuple[int, str]] = []
    for indice, linea in enumerate(lineas):
        normalizada = normalizar(linea)
        if re.search(r"FECHA\s+(?:DE\s+)?(?:EMISION|FACTURA|EXPEDICION)|FECHA\s+FRA",
                     normalizada):
            prioridad = 2
        elif re.search(r"VENCIMIENTO|ENVIO|PEDIDO|ALBARAN|ENTREGA", normalizada):
            prioridad = -1                       # esas fechas NO son la de emisión
        elif "FECHA" in normalizada:
            prioridad = 1
        else:
            prioridad = 0

        # El rótulo puede ir solo en su línea y la fecha en la siguiente. Se mira la
        # línea de abajo cuando en la propia no hay una FECHA completa (dd?dd?aaaa) —no
        # basta con "no hay dígitos": en un recibo el rótulo comparte renglón con los
        # importes (`FECHA DE EXPEDICION I.R.P.F. 19% 576,27`) y la fecha va debajo.
        textos = [normalizada]
        hay_fecha_aqui = re.search(r"\d{1,2}[/.-]\d{1,2}[/.-]\d", normalizada)
        if prioridad >= 1 and not hay_fecha_aqui and indice + 1 < len(lineas):
            textos.append(normalizar(lineas[indice + 1]))

        for texto_fecha in textos:
            # El separador puede ser /.- y el año llevar punto de millar (`2.019`,
            # factura 1 de alquiler). El año-millar se reconoce aparte (\d\.\d{3}) para
            # no confundir su punto con un separador; a_iso limpia el punto después.
            for dia, mes, anio in re.findall(
                    r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d\.\d{3}|\d{2,4})\b", texto_fecha):
                iso = a_iso(dia, mes, anio)
                if iso:
                    candidatas.append((prioridad, iso))
            for dia, mes, anio in re.findall(
                    r"\b(\d{1,2})\s+DE\s+([A-Z]+)\s+DE\s+([\d.]+)", texto_fecha):
                if mes in _MESES:
                    iso = a_iso(dia, str(_MESES[mes]), anio)
                    if iso:
                        candidatas.append((prioridad, iso))

    validas = [(p, f) for p, f in candidatas if p >= 0]
    if not validas:
        return None
    mejor = max(p for p, _ in validas)
    return next(f for p, f in validas if p == mejor)


def exenta_de_iva(texto: str) -> bool:
    """True si la factura declara estar exenta de IVA.

    La exención se ESCRIBE en la factura, no se deduce: el emisor está obligado a citar
    el precepto que la ampara. Se busca esa mención literal, nunca se supone porque
    falte el desglose — un IVA que no se encuentra no es un IVA que no exista.
    """
    return bool(_EXENCION.search(normalizar(texto)))


def trio_por_cuadre(texto: str) -> tuple[Decimal, Decimal, Decimal] | None:
    """Base, cuota y total deducidos SOLO de la aritmética del documento.

    Último recurso, cuando el emisor no rotula el total. Se prueban los importes
    impresos y se acepta un trío únicamente si cumple las dos condiciones a la vez:

        base + cuota = total     y     cuota = base × tipo legal

    Si hay más de un trío posible el documento es ambiguo y se devuelve None: irá a
    revisión. Se prefiere el total MAYOR entre los que cuadran con la misma base, porque
    un mismo desglose puede aparecer repetido (original y copia) pero nunca dos totales
    distintos para la misma base.
    """
    # SOLO las cifras escritas con céntimos. Un importe de factura siempre los lleva;
    # un código de artículo, un teléfono o un número de albarán, no. Sin este filtro la
    # factura 016 aportaba 56 candidatos (19, 28921, 618, 999, 1744401…), aparecían
    # varias combinaciones que cuadraban por casualidad y la lectura se descartaba por
    # ambigua siendo perfectamente legible.
    candidatos: list[Decimal] = []
    for linea in limpiar(texto).split("\n"):
        for bruto in re.findall(r"-?\d{1,3}(?:[.\s]\d{3})*,\d{2}\b|-?\d+\.\d{2}\b", linea):
            importe = cifra(bruto)
            # Se admiten los NEGATIVOS: un abono (factura rectificativa) tiene todos sus
            # importes en negativo y es tan factura como cualquier otra —factura 016,
            # Implant Prótesis: −85,00 de base, −8,50 de IVA al 10%, −93,50 de total—.
            if importe is not None and importe != 0 and importe not in candidatos:
                candidatos.append(importe)
    if len(candidatos) > 60:            # documento con demasiadas cifras: no se adivina
        return None

    soluciones: set[tuple[Decimal, Decimal, Decimal]] = set()
    for base in candidatos:
        for tipo in TIPOS_IVA:
            if tipo == 0:
                continue
            calculada = (base * tipo / 100).quantize(Decimal("0.01"))
            # Manda la cuota IMPRESA, no la calculada: el emisor redondea a su criterio
            # y 774,05 al 10% da 77,405, que él escribe 77,41 y el cálculo deja en 77,40
            # (factura 006). Registrar la calculada desviaría el total un céntimo
            # respecto al documento, y una factura debe copiar lo que dice el papel.
            cuota = next((c for c in candidatos if abs(c - calculada) <= Decimal("0.01")),
                         calculada)
            total = (base + cuota).quantize(Decimal("0.01"))
            # Las TRES cifras tienen que estar impresas: no se inventa ninguna.
            if any(abs(c - cuota) <= Decimal("0.01") for c in candidatos) and \
               any(abs(c - total) <= Decimal("0.01") for c in candidatos):
                soluciones.add((base, cuota, total))

    # Facturas con RETENCIÓN y sin IVA: las de profesionales exentos (factura 034,
    # 1.078,92 − 161,84 = 917,08). Aquí la resta es la que cierra, no la suma, y sin
    # contemplarla la factura queda sin total por buscar un IVA que no existe.
    # Solo si el documento DICE que hay retención. Sin esta condición, cualquier factura
    # con dos cifras en proporción 85/100 producía una lectura falsa: la 019 devolvía
    # base 15,75 y total 12,76 cuando sus importes reales son 1.068,87 y 1.239,60.
    if not soluciones and re.search(r"\bI\.?\s?R\.?\s?P\.?\s?F\b|RETENCION",
                                    normalizar(texto)):
        # No se acota la base por su tamaño: la factura 051 tiene un bruto mayor (688,80)
        # del que se descuentan gastos antes de retener, así que la base imponible NO es
        # la cifra más grande. Lo que valida el trío es que las TRES cifras estén
        # impresas y que la retención sea un porcentaje legal exacto de la base.
        for base in candidatos:
            if base <= 0:
                continue
            for tipo in (Decimal("15"), Decimal("7"), Decimal("19"), Decimal("21"),
                         Decimal("2"), Decimal("1")):
                retencion = (base * tipo / 100).quantize(Decimal("0.01"))
                total = (base - retencion).quantize(Decimal("0.01"))
                if any(abs(c - retencion) <= Decimal("0.01") for c in candidatos) and \
                   any(abs(c - total) <= Decimal("0.01") for c in candidatos):
                    # La cuota se devuelve como 0: no hay IVA, y la retención se deduce
                    # de la diferencia entre base y total.
                    soluciones.add((base, Decimal("0.00"), total))

    if not soluciones:
        return None
    # Varias soluciones con la MISMA base son el mismo desglose leído dos veces; distinta
    # base significa ambigüedad real y entonces no se decide.
    #
    # Caso típico y deliberadamente NO resuelto: un documento que contiene la factura
    # original y su abono (factura 016: 175,00 + 17,50 = 192,50 junto a
    # −85,00 − 8,50 = −93,50). Son dos operaciones distintas y cuál registrar no lo
    # decide un algoritmo: va a revisión para que lo mire una persona.
    bases = {s[0] for s in soluciones}
    if len(bases) != 1:
        return None
    return max(soluciones, key=lambda s: s[2])


# Tipos de IVA vigentes en España. Se usan SOLO para confirmar una pareja base/cuota que
# ya cuadra con el total leído — nunca para calcular un importe que no esté impreso.
TIPOS_IVA = (Decimal("21"), Decimal("10"), Decimal("4"), Decimal("0"))


def retencion_irpf(texto: str) -> Decimal | None:
    """La retención de IRPF de la factura, o None si no la lleva.

    Cuidado con la palabra 'retención': en una clínica dental aparece constantemente como
    NOMBRE DE PRODUCTO — 'PLACA DE RETENCIÓN HAWLEY' es un aparato de ortodoncia, y su
    precio (48,00 €) tomado por retención falsearía la factura entera.

    Solo se acepta como impuesto cuando el rótulo va acompañado de una marca inequívoca:
    las siglas IRPF, la mención a la renta, o un porcentaje de retención junto al importe.
    Y solo lo llevan las facturas de profesionales y las de alquiler de inmuebles.
    """
    lineas = limpiar(texto).split("\n")
    for i, linea in enumerate(lineas):
        normalizada = normalizar(linea)
        # 'RETENCION' a secas no basta: hace falta la marca fiscal.
        if not re.search(r"\bI\.?\s?R\.?\s?P\.?\s?F\b|RETENCION\s*(?:I\.?R\.?P\.?F|"
                         r"DE\s+I\.?R\.?P\.?F|[\d.,]+\s*%|\()", normalizada):
            continue
        # Descarta el nombre de producto: 'PLACA DE RETENCION HAWLEY' no lleva IRPF.
        if "PLACA" in normalizada or "APARATO" in normalizada:
            continue

        # El importe puede ir en la misma línea o en las siguientes, según cómo alinee el
        # emisor (factura 003: `RETENCIÓN I.R.P.F. (15 por 100)` y debajo `-157,50 Euros`;
        # factura 061: `Retención (15%)`, luego `Base imponible 630,00 €` y después
        # `-94,50 €`). Cuando el rótulo trae el PORCENTAJE, la retención se identifica
        # sin ambigüedad: es la cifra que resulta de aplicarlo a la base.
        importes = importes_de(_sin_parentesis(linea))

        # Si la línea del IRPF ya trae un importe CON CÉNTIMOS, ese es la retención, sin
        # recalcular nada: `I.R.P.F. 19% 576,27 €` (alquiler de Aureliano Melero). El
        # porcentaje suelto (19) no lleva céntimos y queda descartado.
        con_centimos = [cifra(x) for x in
                        re.findall(r"-?\d{1,3}(?:[.\s]\d{3})*,\d{2}|-?\d+\.\d{2}\b", linea)]
        con_centimos = [c for c in con_centimos if c is not None and abs(c) > 0]
        if con_centimos:
            return abs(con_centimos[0])

        pct = re.search(r"\(?\s*(\d{1,2}(?:[.,]\d)?)\s*(?:%|POR\s*100)", normalizar(linea))
        if pct:
            tipo = cifra(pct.group(1).replace(",", "."))
            cercanas: list[Decimal] = []
            for j in range(i, min(i + 4, len(lineas))):
                cercanas += importes_de(lineas[j])
            # Se descarta el propio porcentaje de la lista: en `Retención (15%)` el 15 es
            # el tipo, no un importe, y tomarlo por base daba una retención de 2,25 €.
            cercanas = [c for c in cercanas if abs(c) != tipo]
            for base_posible in cercanas:
                esperada = (abs(base_posible) * tipo / 100).quantize(Decimal("0.01"))
                if esperada <= 0:
                    continue
                # La retención calculada tiene que estar IMPRESA en el documento, y ser
                # distinta de la base: si no, no se ha encontrado, se ha inventado.
                for candidata in cercanas:
                    if (abs(abs(candidata) - esperada) <= Decimal("0.02")
                            and abs(candidata) != abs(base_posible)):
                        return esperada
        if not importes and i + 1 < len(lineas):
            siguiente = lineas[i + 1]
            if len(normalizar(siguiente)) <= 24:
                importes = importes_de(siguiente)
        # Un identificador fiscal no es un importe: `NIF DESTINATARIO: B88393764` daba
        # una retención de 88.393.764 € (factura 109). Una retención lleva céntimos y no
        # alcanza el millón; el filtro se aplica al VALOR, no a la línea, porque el
        # importe puede estar en la de al lado (factura 003).
        importes = [x for x in importes if abs(x) < Decimal("1000000")]
        if importes and importes[0] != 0:
            # Un 0 no es una retención leída: es la casilla vacía del formulario. Darlo
            # por bueno impedía después deducir la retención real (factura 034).
            # El emisor la imprime en negativo porque resta; se devuelve en positivo y
            # el cuadre ya sabe que va restando.
            return abs(importes[0])
    return None


def cuota_por_tipo(texto: str, base: Decimal | None,
                   siglas: tuple[str, ...]) -> Decimal | None:
    """La cuota de un impuesto, elegida porque CUADRA con su porcentaje.

    Regla del usuario, verificada en el alquiler de Aureliano Melero: las facturas traen
    los valores en un sitio y, más abajo, repetidos y CAMBIADOS de orden. No sirve
    fiarse de la posición. Lo que no cambia es la aritmética: si el documento dice
    'I.V.A. 21%', la cuota es la ÚNICA cifra impresa que es el 21% de la base (636,93);
    'I.R.P.F. 19%' solo cuadra con 576,27. Así el orden del OCR deja de importar.

    Necesita la base para poder comprobar el cuadre. Si no hay base, o el tipo no aparece
    junto a esas siglas, devuelve None y se usa la lectura por rótulo como antes.
    """
    if base is None or base <= 0:
        return None

    patron_tipo = re.compile(
        r"(?:" + "|".join(s.replace(".", r"\.?\s?") for s in siglas) +
        r")\D{0,4}(\d{1,2}(?:[.,]\d)?)\s*(?:%|POR\s*100)", re.I)
    tipos = {cifra(m.replace(",", ".")) for m in patron_tipo.findall(normalizar(texto))}
    tipos.discard(None)
    if not tipos:
        return None

    # Todas las cifras con céntimos del documento son candidatas a ser la cuota.
    candidatos: list[Decimal] = []
    for linea in limpiar(texto).split("\n"):
        for bruto in re.findall(r"-?\d{1,3}(?:[.\s]\d{3})*,\d{2}|-?\d+\.\d{2}\b", linea):
            c = cifra(bruto)
            if c is not None and c != 0 and c not in candidatos:
                candidatos.append(c)

    for tipo in tipos:
        esperada = (base * tipo / 100).quantize(Decimal("0.01"))
        # Se acepta la cifra IMPRESA que coincide con el cálculo (±2 céntimos de
        # redondeo). No se registra la calculada: manda lo que dice el papel.
        for candidata in candidatos:
            if abs(abs(candidata) - esperada) <= Decimal("0.02"):
                return abs(candidata)
    return None


def total_por_rotulo(texto: str) -> Decimal | None:
    """El total de la factura, eligiendo entre TODOS los candidatos rotulados.

    Tomar el primer rótulo que casa es lo que fallaba: una factura escribe 'IMPORTE
    TOTAL' encima del descuento y 'TOTAL FACTURA' encima del importe real (factura 005),
    y otra rotula 'TOTAL IMP.' sobre el bruto antes de descuento (factura 006, donde el
    1.674,00 no es el total sino la suma de líneas).

    Se recogen todos los candidatos y gana el que CUADRA con algún par base/cuota
    impreso en el documento. El total de una factura es, por definición, el que cierra
    la aritmética; si ninguno cuadra, se devuelve el del rótulo más específico.
    """
    # Los candidatos han de llevar CÉNTIMOS: el total de una factura se escribe con
    # ellos. Sin esta condición, la línea `total` seguida de `Dental 360 S.L.` daba un
    # total de 360 € (factura 091).
    con_centimos = {c for l in limpiar(texto).split("\n")
                    for c in (cifra(b) for b in re.findall(
                        r"-?\d{1,3}(?:[.\s]\d{3})*,\d{2}\b|-?\d+\.\d{2}\b", l))
                    if c is not None}

    candidatos: list[Decimal] = []
    for rotulo in _ROTULOS_TOTAL:
        valor = valor_tras_rotulo(texto, rotulo)
        if (valor is not None and valor > 0 and valor not in candidatos
                and (valor in con_centimos or not con_centimos)):
            candidatos.append(valor)

    # Una factura puede repetir el rótulo 'Total' en cada trabajo o partida y dejar el
    # de la factura al final (factura 061: diez subtotales antes del total real). Se
    # recogen TODOS los importes que sigan a un rótulo de total, no solo el primero.
    lineas = limpiar(texto).split("\n")
    for i, linea in enumerate(lineas):
        if normalizar(linea).strip(" :.") not in ("TOTAL", "TOTAL FACTURA", "TOTAL A PAGAR"):
            continue
        if i + 1 < len(lineas):
            for valor in importes_de(lineas[i + 1])[:1]:
                if valor > 0 and valor not in candidatos:
                    candidatos.append(valor)

    # También cuentan los totales que aparecen SIN rótulo pero cierran la aritmética:
    # el OCR no lee igual en cada pasada y un rótulo puede perderse (factura 006).
    trio = trio_por_cuadre(texto)
    if trio and trio[2] not in candidatos:
        candidatos.append(trio[2])

    if not candidatos:
        return None

    # Gana el candidato que cuadra con un par base/cuota impreso. Entre varios, el MAYOR:
    # los rótulos parciales ('TOTAL IMP.', 'IMPORTE TOTAL' del descuento) siempre nombran
    # cantidades menores que el total de la factura.
    cuadran = [c for c in candidatos if base_e_iva_por_cuadre(texto, c)]
    if cuadran:
        return max(cuadran)

    # Sin IVA que cuadrar, el total puede ser el que cierra con la base y la retención:
    # `Base imponible 630,00 − Retención (15%) 94,50 = Total 535,50` (factura 061, un
    # protésico exento de IVA). Sin esto se tomaba el primer subtotal de la lista.
    base = valor_tras_rotulo(texto, *_ROTULOS_BASE)
    retencion = retencion_irpf(texto)
    if base is not None and retencion:
        esperado = (base - retencion).quantize(Decimal("0.01"))
        for candidato in candidatos:
            if abs(candidato - esperado) <= TOLERANCIA:
                return candidato

    return candidatos[0] if candidatos else None


def base_e_iva_por_cuadre(texto: str, total: Decimal) -> tuple[Decimal, Decimal] | None:
    """Base y cuota deducidas de los importes del documento, confirmadas por el cuadre.

    Hay facturas cuyo PDF coloca cada celda por coordenadas y, al extraer el texto, los
    rótulos y sus valores quedan desordenados e imposibles de emparejar por posición
    (factura 004: 7 rótulos y 5 valores, con publicidad intercalada).

    Los importes SÍ están impresos, así que en vez de adivinar se prueban las parejas y
    se acepta una solo si cumple LAS DOS condiciones:

        base + cuota = total   (exacto, ±1 céntimo de redondeo)
        cuota = base × tipo    para un tipo de IVA legal

    Y únicamente si la solución es ÚNICA: si dos parejas distintas cuadran, el documento
    es ambiguo y se devuelve None para que vaya a revisión. Nunca se elige "la más
    probable" — eso sería inventar un dato contable.
    """
    candidatos: list[Decimal] = []
    for linea in limpiar(texto).split("\n"):
        for importe in importes_de(linea):
            if importe > 0 and importe not in candidatos:
                candidatos.append(importe)

    soluciones: set[tuple[Decimal, Decimal]] = set()
    for base in candidatos:
        # La base ha de ser la parte GRANDE del total: con IVA del 21% nunca baja del
        # 82% de él. Sin esta cota salían parejas absurdas como base 4,00 con cuota
        # 61.500,00 sumando "casi" el total (factura 006). Se compara en valor absoluto
        # para que valga igual en un abono, donde todo va en negativo (factura 016).
        if abs(base) >= abs(total) or abs(base) < abs(total) * Decimal("0.75"):
            continue
        for cuota in candidatos:
            if cuota <= 0 or abs(base + cuota - total) > Decimal("0.01"):
                continue
            for tipo in TIPOS_IVA:
                esperada = (base * tipo / 100).quantize(Decimal("0.01"))
                if abs(esperada - cuota) <= Decimal("0.02"):
                    soluciones.add((base, cuota))
                    break

    return soluciones.pop() if len(soluciones) == 1 else None


# ─────────────────────────── cuadre ───────────────────────────

# Dos céntimos: el emisor redondea cada cuota por su cuenta y la suma puede quedar a un
# par de céntimos del total impreso. Más margen taparía lecturas malas, que es justo lo
# que hay que detectar.
TOLERANCIA = Decimal("0.02")


def cuadre(base: Decimal | None, iva: Decimal | None, total: Decimal | None,
           irpf: Decimal | None = None, suplido: Decimal | None = None) -> dict[str, Any]:
    """Comprueba que las cifras leídas son coherentes entre sí:

        total = base + IVA − IRPF + suplido

    El IVA suma y el IRPF resta: son las dos únicas reglas y valen para toda factura
    española. El suplido —gasto que el proveedor adelanta por cuenta del cliente— va
    fuera de la base imponible pero SÍ dentro del total.

    NUNCA se ajusta una cifra para forzar el cuadre. Si no encaja, el documento se leyó
    mal y eso es lo que se informa: un cuadre forzado mete un dato falso en la
    contabilidad y nadie vuelve a mirarlo.
    """
    if total is None:
        return {"cuadra": False, "motivo": "sin_total", "esperado": None, "desvio": None}
    if base is None:
        return {"cuadra": False, "motivo": "sin_base", "esperado": None, "desvio": None}

    esperado = (base + (iva or 0) - (irpf or 0) + (suplido or 0)).quantize(Decimal("0.01"))
    desvio = abs(esperado - total.quantize(Decimal("0.01")))
    return {"cuadra": desvio <= TOLERANCIA,
            "motivo": None if desvio <= TOLERANCIA else "descuadre",
            "esperado": str(esperado), "desvio": str(desvio)}
