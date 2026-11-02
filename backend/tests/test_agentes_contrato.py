"""Contrato del área de IAs: los invariantes que NO pueden desaparecer sin avisar.

Por qué existe este fichero: el 24-jul-2026 un commit amplio de otra área congeló una
versión anterior de cuatro ficheros del área de agentes y se llevó por delante la jerarquía
Victor→Aura. No hubo error de sintaxis, ni excepción, ni test rojo: el código compilaba,
importaba y respondía. Sólo faltaba algo, y sólo se vio mirándolo a mano.

Un invariante que no está en un test no está protegido. Estos tests son baratos (no tocan
BD ni red) y fallan en el momento en que alguien revierte, renombra o "limpia" una de las
piezas que sostienen el área.
"""
from domain.config.agentes import CATALOGO, POR_ID


# ─────────────────────── el roster acordado ───────────────────────
def test_el_roster_es_exactamente_el_acordado():
    """Alex · Victor · Aura · Gestor. Ni uno más, ni uno menos.

    El área arrastraba DOS rosters incompatibles (el de las tablas vacías
    AURA/VISTA/ESCUCHA/PLUMA/FORENSE y el real). Si vuelve a aparecer un agente
    fantasma o desaparece uno de los cuatro, esto salta.

    "Gestor IA" y "Gestor IA Multimodal" fusionados en uno solo (`gestor`) el
    2026-09-19: eran la misma función de negocio (procesar facturas) descrita dos veces
    — la ingesta por lotes del primero llevaba tiempo borrada del código, y el interruptor
    del segundo no apagaba el pipeline real (la suscripción push de Gmail, aparte)."""
    assert {a.id for a in CATALOGO} == {"alex", "victor", "aura", "gestor"}


def test_centinela_no_es_un_agente_del_catalogo():
    """Centinela vigila la salud del sistema; no es conversacional y no tiene parcela de
    IA. Meterlo aquí reabriría la confusión de nombres que costó revertir."""
    assert "centinela" not in POR_ID


# ─────────────────────── la jerarquía ───────────────────────
# La jerarquía Victor→Aura de la primera versión se descartó a propósito (confirmado con
# el usuario): Victor habla con el personal de la clínica, Aura SOLO con SuperUser — son
# ámbitos independientes, no una especialización uno del otro. `depende_de` se conserva en
# el modelo como mecanismo genérico por si algún agente futuro sí necesita depender de otro.
def test_ningun_agente_depende_de_otro_hoy():
    for a in CATALOGO:
        assert a.depende_de is None, f"{a.id} no debería depender de nadie en el diseño actual"


def test_la_jerarquia_viaja_en_el_dto():
    """La pantalla pinta la anidación con `dependeDe`. Si el DTO deja de exponerlo, el
    frontend no podría avisar de un futuro agente bloqueado por su responsable."""
    assert "dependeDe" in POR_ID["aura"].to_dict()
    assert "dependeDe" in POR_ID["alex"].to_dict()


# ─────────────────────── parcelas y fronteras ───────────────────────
def test_cada_agente_declara_su_frontera():
    """Un agente se entiende por lo que NO puede hacer. Sin límites explícitos, mañana
    alguien le da a Alex una herramienta de contabilidad sin que chirríe."""
    for a in CATALOGO:
        assert a.limites, f"{a.id} no declara límites"
        assert a.capacidades, f"{a.id} no declara capacidades"
        assert a.permisos, f"{a.id} no declara qué permisos usa"
        assert a.titular, f"{a.id} no dice con quién habla"


def test_las_claves_de_config_son_unicas():
    """Dos agentes compartiendo clave de CONFIG se pisarían el interruptor."""
    claves = [a.config_key for a in CATALOGO]
    assert len(claves) == len(set(claves))


def test_ningun_agente_toca_la_parcela_de_otro():
    """Alex habla con el paciente; Victor con el equipo; el Gestor con la contabilidad.
    Que Alex tuviera permisos de gestoría sería un salto de parcela. Aura es la EXCEPCIÓN
    a propósito: administración total del sistema para SuperUser, así que sus permisos
    cruzan todas las parcelas por diseño (confirmado con el usuario)."""
    assert not [p for p in POR_ID["alex"].permisos if p.startswith("gestoria")]
    assert not [p for p in POR_ID["victor"].permisos if p.startswith("gestoria")]
    assert not [p for p in POR_ID["gestor"].permisos if p.startswith(("citas", "comunicacion"))]
    assert "superuser" in POR_ID["aura"].permisos, "Aura debe tener el permiso superuser"


# ─────────────────────── modelos ───────────────────────
def test_todos_los_agentes_tienen_modelo():
    for a in CATALOGO:
        assert a.modelo, f"{a.id} sin modelo válido: {a.modelo!r}"
    # NOTA: Alex y Victor/Aura/Gestor compartían modelos DISTINTOS por proveedor externo
    # (gpt-oss-120b vs llama-3.3-70b) hasta que este catálogo pasó a un único motor local
    # (Ollama/RTX 3080, PC-ESCANER) por coste — hoy comparten `qwen2.5-coder:7b` a propósito.
    # El catálogo real es la fuente de la verdad, no un valor fijo esperado aquí.


def test_no_queda_el_modelo_retirado_por_nvidia():
    """NVIDIA retiró mistral-large-3 el 23-jul-2026 (HTTP 410) y dejó toda la IA muerta.
    Que nadie lo reintroduzca por copiar-pegar de un fichero viejo."""
    muerto = "mistralai/mistral-large-3-675b-instruct-2512"
    assert all(a.modelo != muerto for a in CATALOGO)


# ─────────────────────── Victor no ejecuta desde el LLM ───────────────────────
def test_victor_no_expone_confirmar_al_llm():
    """El agente conversacional de Victor NO debe dar al LLM la capacidad de ejecutar un
    cambio. En la primera versión el modelo se auto-confirmó y bloqueó una agenda sin
    permiso; la herramienta 'bloquear_agenda' que ve el LLM sólo PREVISUALIZA."""
    from application.services.victor_agente import TOOLS
    bloq = next(t for t in TOOLS if t["function"]["name"] == "bloquear_agenda")
    props = bloq["function"]["parameters"]["properties"]
    assert "confirmar" not in props, "el LLM no debe poder confirmar/ejecutar un bloqueo"
    # Y no debe existir ninguna herramienta de escritura directa (liberar ejecuta al vuelo).
    nombres = {t["function"]["name"] for t in TOOLS}
    assert "liberar_agenda" not in nombres, "liberar ejecuta sin previsualizar: fuera del LLM"


def test_victor_fuerza_previsualizacion():
    """Aunque alguien colara confirmar en los args, el despacho lo ignora: bloquear_agenda
    se llama SIEMPRE con confirmar=False desde el agente."""
    import inspect
    from application.services import victor_agente
    src = inspect.getsource(victor_agente.VictorAgente.ejecutar)
    assert "confirmar=False" in src, "el despacho debe forzar confirmar=False"
    assert "confirmar=True" not in src and "confirmar=bool" not in src,         "el agente NUNCA debe ejecutar un bloqueo"


# ─────────────────────── modo prueba: la IA no habla con pacientes reales ───────────────────────
def test_modo_prueba_blinda_el_entrante():
    """Con lista de números de prueba, la IA entrante SOLO responde a esos números. Sin
    este gate, encender el canal de Alex lo soltaría a responder a pacientes REALES. La
    barrera del modo prueba estaba solo en el saliente; debe estar también en el entrante."""
    import inspect
    from application.services import comunicacion_service as cs
    fuente = inspect.getsource(cs.ComunicacionService)
    assert "_telefono_en_modo_prueba" in fuente, "falta el gate de modo prueba en el entrante"
    # y debe consultarse ANTES de decidir la respuesta automática
    cuerpo = inspect.getsource(cs.ComunicacionService._telefono_en_modo_prueba)
    assert "numeros_prueba" in cuerpo, "el gate debe leer la lista blanca motion.numeros_prueba"


# ─────────────────────── Alex recuerda la conversación ───────────────────────
def test_alex_carga_historial_de_conversacion():
    """Sin historial, Alex ve cada mensaje aislado: saluda en cada turno y olvida lo dicho
    ('quería una cita' → '¿qué necesitas?'). El agente DEBE cargar los turnos previos."""
    import inspect
    from application.services import agente_service
    src = inspect.getsource(agente_service.AgenteService.responder)
    assert "_historial_conversacion" in src, "Alex debe inyectar el historial de la conversación"
    assert hasattr(agente_service.AgenteService, "_historial_conversacion")
