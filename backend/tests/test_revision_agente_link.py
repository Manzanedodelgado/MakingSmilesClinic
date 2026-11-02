from sqlmodel import Session, select

from domain.models.agentes import Agente
from domain.models.comunicacion import AgenteRevision
from domain.models.core import Centro


def test_revision_con_agente_id(session: Session):
    centro = session.exec(select(Centro)).first()
    ag = Agente(centro_id=centro.id, nombre="Alex", audiencia="paciente", config_key="agente.alex", es_agente_base=True)
    session.add(ag); session.commit(); session.refresh(ag)

    rev = AgenteRevision(centro_id=centro.id, agente="alex", agente_id=ag.id, entrada="hola", propuesta="hola!", estado="editada", respuesta_final="Hola!")
    session.add(rev); session.commit(); session.refresh(rev)
    assert rev.agente_id == ag.id

    # query por agente_id
    filas = session.exec(select(AgenteRevision).where(AgenteRevision.agente_id == ag.id)).all()
    assert len(filas) == 1
    # nullable: sin agente_id sigue funcionando
    rev2 = AgenteRevision(centro_id=centro.id, agente="alex", entrada="x", propuesta="y", estado="pendiente")
    session.add(rev2); session.commit()
    assert rev2.agente_id is None
