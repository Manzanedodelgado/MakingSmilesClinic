"""Las facturas REALES ya verificadas contra el papel, una a una.

Este fichero es la red de seguridad del motor. Cada entrada se contrastó leyendo el
documento original y anotando lo que dice, no lo que el motor devuelve. A partir de ahí,
ninguna corrección puede romperlas sin que salte aquí.

Nace de un problema medido: al encadenar reglas de lectura, cada arreglo rompía una
factura anterior. Con esta prueba delante, una regla nueva que estropee lo ya conseguido
se detecta en el momento y no dos horas después.

Cómo se ejecuta (necesita Drive y OCR, así que va contra el entorno real):
    docker exec -w /app makingsmiles-backend python -m tests.test_gestor_facturas_reales
"""
from __future__ import annotations

from decimal import Decimal

from sqlmodel import Session, select

from domain.models.config import Integracion
from domain.services import gestor_archivo as archivo
from domain.services import gestor_documento as documento
from domain.services import gestor_lectura_fiscal as fiscal
from infrastructure.config.db import engine

CARPETA = "1Gs6cmcldxS1GcUoMMgFpDgzHKR0TXDOu"
PROPIAS = ["B88393764"]          # Tridental Odontólogos SLP: jamás es el emisor

# posición en el archivo (0 = la más antigua) -> lo que DICE EL PAPEL.
# Verificado documento a documento. `None` = el dato no aparece en la factura.
VERIFICADAS: dict[int, dict] = {
    0: {"nombre": "FNMT-RCM 9190455333",
        "emisor": "Q2826004J", "base": "14.00", "iva": "2.94", "total": "16.94",
        "por": "totales en línea; NIF con prefijo ES; CIF de organismo (control letra)"},
    1: {"nombre": "GLOBAL UNIFORMS FMAD19-1631",
        "emisor": "B85724607", "base": "27.74", "iva": "5.83", "total": "33.57",
        "por": "totales solo en tabla, cabecera de dos pisos; CIF con la B leída como 8"},
    2: {"nombre": "SERGIO SEDANO 012/2019",
        "emisor": "71268784H", "base": "1050.00", "iva": "220.50", "irpf": "157.50",
        "total": "1113.00",
        "por": "profesional con retención; la base no está rotulada, se deduce"},
    3: {"nombre": "SERVICOPY 4093",
        "emisor": "B79333738", "base": "10.00", "iva": "2.10", "total": "12.10",
        "por": "rótulos en bloque y valores después, sin emparejar"},
    4: {"nombre": "SERVICOPY 75581",
        "emisor": "B79333738", "base": "10.00", "iva": "2.10", "total": "12.10",
        "por": "varios rótulos con su importe en la MISMA línea"},
    5: {"nombre": "SISTEMA TRATAMIENTO 6.3",
        "emisor": "B83143602", "base": "774.05", "iva": "77.41", "total": "851.46",
        "por": "8 rótulos y 5 valores; solo la aritmética resuelve el emparejado"},
    7: {"nombre": "IMPLANT PROTESIS 54620",
        "emisor": "B63568513", "base": "285.00", "iva": "28.50", "total": "313.50",
        "por": "el total no está rotulado: va suelto junto a la fecha de vencimiento"},
    # El documento NO imprime el CIF del emisor en ninguna parte legible: solo aparece
    # el de la clínica. No se anota emisor esperado — inventarlo sería falsear la prueba.
    11: {"nombre": "PROCLINIC 0000216626",
         "base": "139.64", "iva": "26.22", "total": "165.86",
         "por": "DOS tipos de IVA (10% y 21%) desglosados EN COLUMNA, uno por línea"},
    18: {"nombre": "DENTALES 219327",
         "emisor": "B85937787", "base": "1068.87", "iva": "170.73", "total": "1239.60",
         "por": "DOS tipos de IVA repartidos en dos líneas; hay que sumar ambos tramos"},
    32: {"nombre": "DENTALES (2 tipos, sin símbolo %)",
         "base": "1211.92", "iva": "176.57", "total": "1388.49",
         "por": "desglose en columna con el tipo suelto (`10,0`), sin el símbolo %"},
    33: {"nombre": "MONTEIRO (IRPF sin IVA)",
         "base": "1078.92", "iva": "0.00", "irpf": "161.84", "total": "917.08",
         "por": "profesional con retención del 15% y SIN IVA: la resta es la que cierra"},
    38: {"nombre": "BNP PARIBAS FLGFBA94036",
         "base": "27.31", "iva": "5.73", "total": "33.04",
         "por": "el desglose va escrito EN PROSA: 'IVA 21,00 % 5,73 sobre la base de…'"},
    # El OCR de este ejemplar solo captura el CIF de la clínica; el del emisor queda
    # ilegible. No se anota emisor esperado: exigir un dato que el documento no da
    # legible sería falsear la prueba.
    41: {"nombre": "IMPLANT PROTESIS 9426",
         "base": "743.50", "iva": "111.89", "total": "855.39",
         "por": "dos tipos con el porcentaje escrito con céntimos (`21,00`)"},
    50: {"nombre": "IRENE GARCIA IGS2020",
         "emisor": "47541434C", "base": "612.95", "iva": "0.00", "irpf": "91.94",
         "total": "521.01",
         "por": "profesional con IRPF y sin IVA; el documento nombra a 'Dental Rubio "
                "García' sin que se confunda con el emisor"},
    60: {"nombre": "ORLANDO ZAPATA 00242",
         "base": "630.00", "iva": "0.00", "irpf": "94.50", "total": "535.50",
         "por": "exenta de IVA con retención; diez subtotales 'Total' antes del real"},
    70: {"nombre": "ISIDRO PESCADOR 200.269",
         "base": "250.00", "iva": "0.00", "total": "250.00",
         "por": "laboratorio protésico: el documento no menciona el IVA en ningún sitio"},
}

# Facturas verificadas que ya NO están en la carpeta de origen sino en descartes o
# procesadas — se localizan por su nombre. Su valor está en probar casos que el barrido
# masivo destapó, no en su posición.
VERIFICADAS_POR_NOMBRE: dict[str, dict] = {
    "AURELIANO_MELERO_0260": {
        "nombre": "ALQUILER Aureliano Melero 02/60",
        "emisor": "00289369Y", "base": "3033.00", "iva": "636.93", "irpf": "576.27",
        "total": "3093.66",
        "por": "factura de alquiler: IVA 21% e IRPF 19% sobre la misma base, con los "
               "valores repetidos y desordenados por el OCR. El tipo desambigua: cada "
               "cuota es la única cifra que cuadra con su porcentaje. DNI sin ceros "
               "(289.369-Y -> 00289369Y)"},
}


# El NOMBRE original de cada documento verificado. Es lo que permite reencontrarlo
# cuando el motor ya lo ha archivado y renombrado: se busca por su nombre nuevo, que
# conserva el número de factura.
FICHEROS: dict[int, str] = {
    0: "2019-07-17_237_FNMT_RCM_9190455333.pdf",
    1: "2019-07-26_235_GLOBAL_UNIFORMS_FMAD19-1631.pdf",
    2: "2019-08-01_236_SERGIO_SEDANO_012_2019.pdf",
    3: "2019-08-12_238_SERVICOPY_4093.pdf",
    4: "2019-08-12_239_SERVICOPY_75581.pdf",
    5: "2019-08-31_234_SISTEMA_TRATAMIENTO_6.342.pdf",
    7: "2019-09-06_232_IMPLANT_PROPESIS_54620.pdf",
    11: "2019-10-02_222_PROCLINIC_0000216626.pdf",
    18: "2019-10-31_227_DENTALES_219327.pdf",
    32: "2019-12-27_205_DENTALES_2194043.pdf",
    33: "2019-12-30_204_MONTEIRO_CONSULTING.pdf",
    38: "2020-02-01_194_BNP_PARIBAS_FLGFBA94036.pdf",
    41: "2020-02-10_190_IMPLANT_PROTESIS_9426.pdf",
    50: "2020-03-31_184_IRENE_GARCIA_IGS20200331.pdf",
    60: "2020-05-29_164_ORLANDO_ZAPATA_00242.pdf",
    70: "2020-06-30_178_ISIDRO_PESCADOR_200.269.pdf",
}


def _buscar_en_el_archivo(cfg_drive: dict, nombre_original: str):
    """Encuentra un documento aunque el motor ya lo haya archivado y renombrado.

    Se identifica por la FECHA más el número, no solo por el número: hay proveedores que
    reutilizan la numeración —Servicopy tiene cuatro facturas distintas con el nº 4093 y
    Ortolusi cinco con el 000118—, así que buscar solo el número devuelve otra factura.

    El nombre original `2019-08-12_238_SERVICOPY_4093.pdf` y el archivado
    `2019-08-09_2_COMERCIAL-SERVICOPY_4093.pdf` NO comparten fecha (la del archivo es la
    de recepción; la del nombre nuevo, la de emisión), así que se prueban ambas.
    """
    from infrastructure.external_apis import drive_client

    # El número puede llevar barra (`012/2019`), que al archivar se convierte en guion,
    # y en el nombre original venía partido por guiones bajos (`..._012_2019.pdf`). Se
    # compara la COLA de dígitos y separadores, unificando `_`, `-` y `/`.
    import re as _re

    def cifras_finales(nombre: str) -> str:
        """Las cifras del final del nombre, sin separadores.

        Es lo único que sobrevive intacto al renombrado, venga el número partido
        (`SEDANO_012_2019.pdf`), con barra (`012/2019`) o con guion (`012-2019`):
        los tres dan `0122019`.
        """
        sin_extension = _re.sub(r"\.(pdf|png|jpe?g)$", "", nombre, flags=_re.I)
        final = _re.search(r"[0-9][0-9A-Za-z._/-]*$", sin_extension)
        return _re.sub(r"[^0-9A-Za-z]", "", final.group() if final else "").upper()

    numero = cifras_finales(nombre_original)
    carpetas = [CARPETA]
    procesadas = (cfg_drive.get("carpetas") or {}).get("gestor_ia")
    if procesadas:
        carpetas.append(procesadas)
        carpetas += [c["id"] for c in drive_client.listar_subcarpetas(cfg_drive, procesadas)]

    coincidencias = []
    for carpeta in carpetas:
        for fichero in archivo.inventario(cfg_drive, carpeta):
            nombre = str(fichero.get("name", ""))
            if nombre == nombre_original:
                return fichero                     # el original, sin tocar
            if numero and cifras_finales(nombre) == numero:
                coincidencias.append(fichero)
    # Con varias del mismo número gana la más antigua: las verificadas son las primeras
    # del archivo.
    coincidencias.sort(key=lambda f: str(f.get("name", "")))
    return coincidencias[0] if coincidencias else None

def leer(indice: int) -> dict:
    """Procesa una factura del archivo tal como lo haría el motor."""
    with Session(engine) as sesion:
        drive = sesion.exec(select(Integracion).where(
            Integracion.tipo == "google_drive", Integracion.centro_id == 1)).first()
        llm = sesion.exec(select(Integracion).where(
            Integracion.tipo == "llm", Integracion.centro_id == 1)).first()
        cfg_drive = (drive.config if drive else {}) or {}
        cfg_ocr = dict(((llm.config if llm else {}) or {}).get("ocr") or {})

        # Se busca en TODO el archivo, no solo en la carpeta de origen: en cuanto el
        # motor archiva una factura, esta se mueve a `FACTURAS PROCESADAS/<año>` y su
        # posición en la carpeta original deja de existir. Localizarla por nombre hace
        # que la prueba siga valiendo antes y después del barrido.
        documentos = archivo.inventario(cfg_drive, CARPETA)
        if indice < len(documentos):
            fichero = documentos[indice]
        else:
            fichero = None
        esperado = FICHEROS.get(indice)
        if esperado and (fichero is None or fichero.get("name") != esperado):
            fichero = _buscar_en_el_archivo(cfg_drive, esperado)
        if fichero is None:
            raise RuntimeError(f"no se encuentra el documento {indice + 1}")
        binario = archivo.descargar(cfg_drive, fichero["id"])

    texto, via = documento.leer(cfg_ocr, binario, fichero.get("mimeType"))
    importes = fiscal.importes(texto)
    return {
        "fichero": fichero["name"], "via": via,
        "emisor": fiscal.emisor(texto, PROPIAS),
        **importes,
        "cuadre": fiscal.cuadre(importes["base"], importes["iva"],
                                importes["total"], importes.get("irpf")),
    }


def comprobar() -> int:
    """Contrasta cada factura verificada. Devuelve el número de fallos."""
    fallos = 0
    for indice, papel in sorted(VERIFICADAS.items()):
        obtenido = leer(indice)
        problemas = []

        for campo in ("emisor", "base", "iva", "irpf", "total"):
            if campo not in papel:
                continue
            esperado = papel[campo]
            valor = obtenido.get(campo)
            actual = str(valor) if valor is not None else None
            if campo != "emisor" and actual is not None:
                actual = str(Decimal(actual).quantize(Decimal("0.01")))
                esperado = str(Decimal(esperado).quantize(Decimal("0.01")))
            if actual != esperado:
                problemas.append(f"{campo}: {actual} (papel: {esperado})")

        if not obtenido["cuadre"]["cuadra"]:
            problemas.append(f"no cuadra (desvío {obtenido['cuadre']['desvio']})")

        marca = "OK   " if not problemas else "FALLO"
        print(f"  {marca} {indice + 1:3}. {papel['nombre']:32} {papel['por']}")
        for problema in problemas:
            print(f"           -> {problema}")
        fallos += bool(problemas)

    total = len(VERIFICADAS)
    print(f"\n  {total - fallos}/{total} facturas verificadas correctas")
    return fallos


if __name__ == "__main__":
    raise SystemExit(1 if comprobar() else 0)
