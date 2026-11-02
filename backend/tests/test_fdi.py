from domain.services.fdi import nombre_pieza


def test_ejemplos_clinicos():
    assert nombre_pieza("36") == "primer molar inferior izquierdo"
    assert nombre_pieza("11") == "incisivo central superior derecho"
    assert nombre_pieza(25) == "segundo premolar superior izquierdo"
    assert nombre_pieza("48") == "tercer molar inferior derecho (muela del juicio)"
    assert nombre_pieza("85") == "segundo molar de leche inferior derecho"
    assert nombre_pieza("63") == "canino de leche superior izquierdo"


def test_cubre_las_52_piezas_y_rechaza_el_resto():
    validas = [f"{c}{n}" for c in range(1, 5) for n in range(1, 9)] + [f"{c}{n}" for c in range(5, 9) for n in range(1, 6)]
    assert len(validas) == 52 and all(nombre_pieza(p) for p in validas)
    for mala in ("19", "56", "90", "3", "136", "", None, "ab"):
        assert nombre_pieza(mala) is None
