from sqlmodel import Session, select

from domain.models.agentes import Agente, CapacidadCatalogo, AgenteCapacidad
from domain.models.core import Centro


def test_crear_agente_con_capacidad(session: Session):
    centro = session.exec(select(Centro)).first()
    assert centro is not None

    agente = Agente(
        centro_id=centro.id,
        nombre="Alex",
        audiencia="paciente",
        activo=True,
        modo_activacion="manual",
        modelo_llm="qwen2.5-coder:7b",
        config_key="agente.alex",
        es_agente_base=True,
    )
    session.add(agente)
    session.commit()
    session.refresh(agente)
    assert agente.id is not None
    assert agente.rol_sub is None
    assert agente.nombre_presentacion is None

    capacidad = CapacidadCatalogo(
        clave="crear_cita",
        descripcion="Crea una cita real en un hueco libre.",
        ejecutor="AgenteService.ejecutar_tool:crear_cita",
        parametros={"type": "object", "properties": {
            "fecha": {"type": "string"}, "hora": {"type": "string"},
        }, "required": ["fecha", "hora"]},
    )
    session.add(capacidad)
    session.commit()
    session.refresh(capacidad)

    puente = AgenteCapacidad(agente_id=agente.id, capacidad_id=capacidad.id, activa=True)
    session.add(puente)
    session.commit()

    fila = session.exec(
        select(AgenteCapacidad).where(AgenteCapacidad.agente_id == agente.id)
    ).first()
    assert fila is not None
    assert fila.activa is True
    assert fila.capacidad_id == capacidad.id


def test_clave_capacidad_es_unica(session: Session):
    c1 = CapacidadCatalogo(clave="escalar_a_humano", descripcion="a", ejecutor="x.y", parametros={})
    session.add(c1)
    session.commit()

    c2 = CapacidadCatalogo(clave="escalar_a_humano", descripcion="b", ejecutor="x.z", parametros={})
    session.add(c2)
    import pytest
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        session.commit()
