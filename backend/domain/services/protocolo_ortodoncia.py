"""Protocolo fotográfico de ortodoncia — FUENTE DE VERDAD única.

Serie clínica estándar (American Association of Orthodontists): 8 fotografías
obligatorias + 3 opcionales, en dos grupos (extraoral / intraoral). El backend la
sirve a las apps (doctor iOS/Android) para que la guía de toma, el orden rutinario
y los criterios de calidad NO estén duplicados ni hardcodeados en cada cliente.

Cada ranura lleva:
  - overlay: silueta que la app dibuja encima del visor para encuadrar (no es una
    imagen, es un TIPO que el cliente renderiza vectorialmente).
  - instrucciones: cómo colocar al paciente / la cámara (protocolo rutinario).
  - checklist: criterios objetivos de calidad que el doctor confirma antes de guardar.

Referencias del protocolo (jul-2026):
  - Orthodontic photography protocol: ortodontmark.com/blogs/consultation
  - Clinical photography A-Z: apospublications.com/clinical-photography-a-to-z
  - Shofu — Digital Photography for Orthodontic Treatment Planning (2016)
"""
from typing import Optional

# overlay: guía vectorial que dibuja la app sobre el visor de cámara.
#   cara_frontal · cara_perfil · cara_tres_cuartos  → siluetas faciales
#   arcada_frontal · arcada_lateral · arcada_oclusal → marcos intraorales
GRUPO_EXTRAORAL = "extraoral"
GRUPO_INTRAORAL = "intraoral"

PROTOCOLO: list[dict] = [
    # ─────────────────────────── EXTRAORAL (facial) ───────────────────────────
    {
        "codigo": "frontal_reposo",
        "referencia": "guias/frontal_reposo.png",
        "nombre": "Frontal en reposo",
        "grupo": GRUPO_EXTRAORAL,
        "orden": 1,
        "obligatoria": True,
        "overlay": "cara_frontal",
        "orientacion": "vertical",
        "instrucciones": [
            "Paciente de frente, mirada al horizonte (plano de Frankfort paralelo al suelo).",
            "Labios en reposo, sin forzar la sonrisa ni apretar los dientes.",
            "Fondo neutro y liso; retira gafas, mascarilla y pelo de la cara.",
            "Centra la línea media facial en la vertical de la guía.",
        ],
        "checklist": [
            "Pupilas a la misma altura (cabeza sin inclinar)",
            "Orejas simétricas y visibles",
            "Sin sombras duras en la cara",
            "Cara nítida y bien iluminada",
        ],
    },
    {
        "codigo": "frontal_sonrisa",
        "referencia": "guias/frontal_sonrisa.png",
        "nombre": "Frontal sonriendo",
        "grupo": GRUPO_EXTRAORAL,
        "orden": 2,
        "obligatoria": True,
        "overlay": "cara_frontal",
        "orientacion": "vertical",
        "instrucciones": [
            "Misma posición frontal, ahora con sonrisa amplia y natural.",
            "Deben verse los dientes; no cierres los labios.",
            "Mantén la mirada al horizonte y la cabeza recta.",
        ],
        "checklist": [
            "Se ven los dientes anteriores al sonreír",
            "Línea media facial centrada",
            "Cabeza sin inclinar",
            "Enfoque nítido",
        ],
    },
    {
        "codigo": "perfil_derecho",
        "referencia": "guias/perfil_derecho.png",
        "nombre": "Perfil derecho en reposo",
        "grupo": GRUPO_EXTRAORAL,
        "orden": 3,
        "obligatoria": True,
        "overlay": "cara_perfil",
        "orientacion": "vertical",
        "instrucciones": [
            "Paciente girado 90° mostrando el lado DERECHO completo.",
            "Labios en reposo, mirada al horizonte.",
            "Despeja la oreja y la línea de la mandíbula (recoge el pelo).",
        ],
        "checklist": [
            "Perfil a 90° exactos (no se ve la otra ceja/ojo)",
            "Oreja visible como referencia",
            "Plano de Frankfort horizontal",
            "Contorno facial nítido",
        ],
    },
    {
        "codigo": "tres_cuartos_sonrisa",
        "referencia": "guias/tres_cuartos_sonrisa.png",
        "nombre": "Tres cuartos (45°) sonriendo",
        "grupo": GRUPO_EXTRAORAL,
        "orden": 4,
        "obligatoria": False,
        "overlay": "cara_tres_cuartos",
        "orientacion": "vertical",
        "instrucciones": [
            "Paciente girado 45° hacia su derecha, sonriendo.",
            "Útil para valorar la estética de la sonrisa en volumen.",
        ],
        "checklist": [
            "Giro de ~45° (se intuye la otra mejilla)",
            "Sonrisa natural con dientes visibles",
            "Enfoque nítido",
        ],
    },
    # ─────────────────────────── INTRAORAL ───────────────────────────
    {
        "codigo": "intraoral_frontal",
        "referencia": "guias/intraoral_frontal.png",
        "nombre": "Intraoral frontal en oclusión",
        "grupo": GRUPO_INTRAORAL,
        "orden": 5,
        "obligatoria": True,
        "overlay": "arcada_frontal",
        "orientacion": "horizontal",
        "instrucciones": [
            "Usa separadores labiales; tira de ellos hacia fuera y ligeramente atrás.",
            "Dientes en oclusión (mordida cerrada, máxima intercuspidación).",
            "Plano oclusal paralelo al borde horizontal de la guía.",
            "Cámara a la altura de la boca, nunca desde arriba ni desde abajo.",
        ],
        "checklist": [
            "Línea media dental centrada en la guía",
            "Plano oclusal horizontal (sin inclinar)",
            "Se ven caninos de ambos lados",
            "Sin saliva/reflejos que tapen los dientes",
            "Enfoque nítido en los incisivos",
        ],
    },
    {
        "codigo": "intraoral_lateral_derecha",
        "referencia": "guias/intraoral_lateral_derecha.png",
        "nombre": "Intraoral lateral derecha (en oclusión)",
        "grupo": GRUPO_INTRAORAL,
        "orden": 6,
        "obligatoria": True,
        "overlay": "arcada_lateral",
        "orientacion": "horizontal",
        "instrucciones": [
            "Separador del lado derecho traccionado; el izquierdo relaja para no tapar.",
            "Dientes en oclusión; encuadra desde el canino hasta el último molar visible.",
            "Fotografía la vista del lado DERECHO del paciente.",
        ],
        "checklist": [
            "Se ve la relación molar (llave de Angle)",
            "Plano oclusal horizontal",
            "Desde canino a molares visible",
            "Enfoque nítido",
        ],
    },
    {
        "codigo": "intraoral_lateral_izquierda",
        "referencia": "guias/intraoral_lateral_izquierda.png",
        "nombre": "Intraoral lateral izquierda (en oclusión)",
        "grupo": GRUPO_INTRAORAL,
        "orden": 7,
        "obligatoria": True,
        "overlay": "arcada_lateral",
        "orientacion": "horizontal",
        "instrucciones": [
            "Separador del lado izquierdo traccionado; el derecho relaja.",
            "Dientes en oclusión; del canino al último molar visible.",
            "Fotografía la vista del lado IZQUIERDO del paciente.",
        ],
        "checklist": [
            "Se ve la relación molar (llave de Angle)",
            "Plano oclusal horizontal",
            "Desde canino a molares visible",
            "Enfoque nítido",
        ],
    },
    {
        "codigo": "oclusal_superior",
        "referencia": "guias/oclusal_superior.png",
        "nombre": "Oclusal superior (con espejo)",
        "grupo": GRUPO_INTRAORAL,
        "orden": 8,
        "obligatoria": True,
        "overlay": "arcada_oclusal",
        "orientacion": "horizontal",
        "instrucciones": [
            "Espejo oclusal dentro de la boca; paciente con la boca bien abierta.",
            "Fotografía el reflejo del espejo, no los dientes directamente.",
            "Centra el rafe medio; deben verse los dos últimos molares.",
            "Calienta o seca el espejo para que no se empañe.",
        ],
        "checklist": [
            "Arcada en forma de 'U' simétrica",
            "Se ven incisivos y los molares del fondo",
            "Sin empañado ni dedos/separador en la imagen",
            "Enfoque nítido en toda la arcada",
        ],
    },
    {
        "codigo": "oclusal_inferior",
        "referencia": "guias/oclusal_inferior.png",
        "nombre": "Oclusal inferior (con espejo)",
        "grupo": GRUPO_INTRAORAL,
        "orden": 9,
        "obligatoria": True,
        "overlay": "arcada_oclusal",
        "orientacion": "horizontal",
        "instrucciones": [
            "Espejo oclusal inferior; boca bien abierta y lengua retraída hacia atrás.",
            "Fotografía el reflejo; centra el rafe/lengua y muestra los molares del fondo.",
            "Seca la saliva y evita que la lengua tape los dientes.",
        ],
        "checklist": [
            "Arcada en 'U' simétrica",
            "Lengua fuera de la vista de los dientes",
            "Se ven los molares del fondo",
            "Enfoque nítido",
        ],
    },
    {
        "codigo": "overjet_lateral",
        "referencia": "guias/overjet_lateral.png",
        "nombre": "Overjet lateral (resalte)",
        "grupo": GRUPO_INTRAORAL,
        "orden": 10,
        "obligatoria": False,
        "overlay": "arcada_lateral",
        "orientacion": "horizontal",
        "instrucciones": [
            "Vista lateral con los dientes en oclusión, centrada en los incisivos.",
            "Sirve para medir el resalte (overjet) y la sobremordida (overbite).",
            "Una regla milimetrada apoyada ayuda a cuantificar el resalte.",
        ],
        "checklist": [
            "Incisivos superiores e inferiores nítidos de perfil",
            "Se aprecia el resalte anteroposterior",
            "Plano oclusal horizontal",
        ],
    },
]

# Índice por código para validación O(1) en el gateway.
_POR_CODIGO = {s["codigo"]: s for s in PROTOCOLO}
CODIGOS_VALIDOS = set(_POR_CODIGO)
CODIGOS_OBLIGATORIOS = [s["codigo"] for s in PROTOCOLO if s["obligatoria"]]


def slot(codigo: str) -> Optional[dict]:
    """Devuelve la ranura del protocolo por su código, o None si no existe."""
    return _POR_CODIGO.get(codigo)


def es_codigo_valido(codigo: str) -> bool:
    return codigo in CODIGOS_VALIDOS
