"""Reglas de cita (application/services/cita_reglas.py): obligatorios, campos desconocidos,
datos de la ficha, disponibilidad del centro y gabinete↔doctor del horario del día."""
from datetime import date

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from application.services.cita_reglas import gabinete_y_doctor, no_disponible, validar_y_completar
from application.services.config_service import ConfigService
from domain.models.agenda import ColaboradorHorario, Gabinete, TipoCita
from domain.models.core import Cita, Paciente

LUNES = date(2026, 10, 12)
DOMINGO = date(2026, 10, 18)
H = {"Authorization": ""}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "X-Centro-Id": "1"}


def _base(session: Session) -> tuple[int, int]:
    tipo = TipoCita(centro_id=1, nombre="Control")
    session.add(Gabinete(centro_id=1, nombre="Box reglas"))
    pac = Paciente(centro_id=1, nombre="Ana", apellidos="Prueba Reglas", telefono_movil="600111222",
                   num_historia="H-1")
    session.add(tipo); session.add(pac); session.commit()
    return tipo.id, pac.id


def test_sin_tipo_ni_telefono_no_se_crea(client: TestClient, token: str, session: Session):
    n = len(session.exec(select(Cita)).all())
    r = client.post("/agenda/citas", headers=_auth(token),
                    json={"fecha": "2026-10-12", "hora": "10:00", "duracion_min": 30, "nombre": "X", "apellidos": "Y"})
    assert r.status_code == 422
    assert "tipo de cita" in r.text and "teléfono" in r.text
    session.rollback()   # la sesión de test es la misma que usó la API y quedó abortada por el 422
    assert len(session.exec(select(Cita)).all()) == n


def test_campo_desconocido_da_422(client: TestClient, token: str, session: Session):
    tipo_id, pac_id = _base(session)
    r = client.post("/agenda/citas", headers=_auth(token),
                    json={"fecha": "2026-10-12", "hora": "10:00", "paciente_id": pac_id, "tipo_cita": "Control"})
    assert r.status_code == 422


def test_con_ficha_nombre_y_telefono_salen_de_la_ficha(client: TestClient, token: str, session: Session):
    tipo_id, pac_id = _base(session)
    gab = session.exec(select(Gabinete).where(Gabinete.nombre == "Box reglas")).first()
    r = client.post("/agenda/citas", headers=_auth(token),
                    json={"fecha": "2026-10-12", "hora": "10:00", "duracion_min": 30,
                          "paciente_id": pac_id, "tipo_cita_id": tipo_id, "gabinete_id": gab.id})
    assert r.status_code == 201, r.text
    c = session.get(Cita, r.json()["id"])
    assert (c.nombre, c.apellidos, c.telefono_movil, c.num_historia) == ("Ana", "Prueba Reglas", "600111222", "H-1")


def test_hora_mal_formada_da_422(session: Session):
    tipo_id, pac_id = _base(session)
    with pytest.raises(HTTPException):
        validar_y_completar(session, 1, {"fecha": LUNES, "hora": "25:00", "duracion_min": 30,
                                         "paciente_id": pac_id, "tipo_cita_id": tipo_id})


def test_festivo_y_dia_cerrado_y_fuera_de_turno(session: Session):
    cfg = ConfigService(session)
    cfg.set("centro.festivos", ["2026-10-12"], centro_id=1)
    cfg.set("centro.horario", {"dias": [{"abierto": True, "t1a": "10:00", "t1b": "14:00", "t2a": "", "t2b": ""}] * 6
                               + [{"abierto": False}]}, centro_id=1)
    session.commit()
    assert "festivo" in no_disponible(session, 1, LUNES, "10:00", None)
    assert "cerrada" in no_disponible(session, 1, DOMINGO, "10:00", None)
    assert "Fuera del horario" in no_disponible(session, 1, date(2026, 10, 13), "15:00", None)
    assert no_disponible(session, 1, date(2026, 10, 13), "10:30", None) is None


def test_gabinete_lleva_el_doctor_del_horario(session: Session):
    gab = Gabinete(centro_id=1, nombre="Box prueba")
    session.add(gab); session.commit()
    session.add(ColaboradorHorario(centro_id=1, colaborador_id=7001, gabinete_id=gab.id, dia_semana=0,
                                   hora_inicio="10:00", hora_fin="14:00"))
    session.commit()
    assert gabinete_y_doctor(session, 1, LUNES, "11:00", gab.id, None) == (gab.id, 7001)
    assert gabinete_y_doctor(session, 1, LUNES, "11:00", None, 7001) == (gab.id, 7001)
    with pytest.raises(HTTPException):
        gabinete_y_doctor(session, 1, LUNES, "11:00", gab.id, 7002)
    # fuera de su franja el gabinete no tiene doctor asignado: no se impone nadie
    assert gabinete_y_doctor(session, 1, LUNES, "16:00", gab.id, None) == (gab.id, None)


def test_sin_gabinete_no_se_crea(client: TestClient, token: str, session: Session):
    """Sin gabinete la agenda pinta la cita en una columna "Sin gabinete" inventada (cita 49005)."""
    tipo_id, pac_id = _base(session)
    r = client.post("/agenda/citas", headers=_auth(token),
                    json={"fecha": "2026-10-12", "hora": "10:00", "duracion_min": 30,
                          "paciente_id": pac_id, "tipo_cita_id": tipo_id})
    assert r.status_code == 422 and "gabinete" in r.text



def test_infranqueable_aunque_se_guarde_sin_pasar_por_la_api(session: Session):
    """Cualquier código que guarde una cita pasa por las reglas: sin tipo ni gabinete no se guarda."""
    _tipo_id, pac_id = _base(session)
    session.add(Cita(centro_id=1, fecha=LUNES, hora="11:00", duracion_min=30, paciente_id=pac_id))
    with pytest.raises(HTTPException):
        session.commit()
    session.rollback()
    assert session.exec(select(Cita).where(Cita.paciente_id == pac_id)).all() == []


def test_anular_una_cita_antigua_incompleta_sigue_permitido(session: Session):
    """Cambiar solo el estado (anular) no exige completar la cita."""
    from domain.models.agenda import EstadoCita
    _tipo_id, pac_id = _base(session)
    from sqlalchemy import text
    session.exec(text("INSERT INTO citas (centro_id, fecha, hora, duracion_min, paciente_id, gratuita, recordada, "
                      "confirmada, envio_doc, firmado, aceptada, anulacion_gestionada, created_at, updated_at) "
                      f"VALUES (1, '2026-10-13', '11:00', 30, {pac_id}, 0,0,0,0,0,0,0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
    session.commit()
    vieja = session.exec(select(Cita).where(Cita.paciente_id == pac_id)).first()
    est = EstadoCita(centro_id=1, nombre="Anulada", codigo="anulada"); session.add(est); session.commit()
    vieja.estado_id = est.id
    session.add(vieja); session.commit()
