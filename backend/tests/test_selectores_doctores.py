"""Selectores de doctor de Agenda y Config › Agenda: solo personal ACTIVO y de ESTE centro.

Regresión (datos reales): "Test Admin" tenía Colaborador.activo=true pero periodo con
fecha_baja → salía en los selectores. Y /agenda/referencias no filtraba por centro.
"""
from datetime import date

from fastapi.testclient import TestClient
from sqlmodel import Session

from domain.models.core import Centro, Colaborador
from domain.models.identidad import Usuario, UsuarioPeriodo


def _doctor(session: Session, nombre: str, centro_id: int = 1, baja: date | None = None) -> int:
    u = Usuario(nombre=nombre, apellidos="Selector", email=f"{nombre.lower()}@sel.es")
    session.add(u); session.commit(); session.refresh(u)
    per = UsuarioPeriodo(usuario_id=u.id, centro_id=centro_id, fecha_alta=date(2020, 1, 1), fecha_baja=baja)
    session.add(per); session.commit(); session.refresh(per)
    col = Colaborador(periodo_id=per.id, activo=True)
    session.add(col); session.commit(); session.refresh(col)
    return col.id


def _ids(resp) -> set[int]:
    assert resp.status_code == 200, resp.text
    return {c["id"] for c in resp.json()["colaboradores"]}


def test_selectores_excluyen_bajas_y_otros_centros(client: TestClient, token: str, session: Session):
    otro = Centro(nombre="Otro centro", codigo="OTRO-SEL")
    session.add(otro); session.commit(); session.refresh(otro)
    activo = _doctor(session, "Activo")
    de_baja = _doctor(session, "DeBaja", baja=date(2026, 9, 26))
    ajeno = _doctor(session, "Ajeno", centro_id=otro.id)
    h = {"Authorization": f"Bearer {token}"}

    for url in ("/agenda/referencias", "/configuracion/agenda"):
        ids = _ids(client.get(url, headers=h))
        assert activo in ids, url
        assert de_baja not in ids, f"{url}: ex-personal de baja en el selector"
        assert ajeno not in ids, f"{url}: doctor de otro centro en el selector"
