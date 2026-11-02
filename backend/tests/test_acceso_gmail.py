"""Plan Gestión de Facturas · Punto 1 — Comprobación de acceso a Gmail y buzones.

Test de INTEGRACIÓN (toca la BD real y el servidor IMAP real de Gmail), marcado
`integration` → no corre en la suite rápida. Ejecutar con:

    pytest tests/test_acceso_gmail.py -m integration

Verifica los 4 criterios acordados:
  1.1  existe la config IMAP en la BD para el centro
  1.2  login real correcto (no solo que haya credenciales)
  1.3  se listan los buzones, incluida la carpeta \\All (Todos) que usa el backlog
  1.4  se lee de verdad (se cuentan correos recientes)

Si no hay config IMAP (p.ej. en CI sin credenciales), el test se SALTA, no falla.
"""
import pytest
from sqlmodel import Session, select

from infrastructure.config.db import engine
from domain.models import Integracion
from infrastructure.external_apis import gmail_imap

pytestmark = pytest.mark.integration

CENTRO_ID = 1


@pytest.fixture(scope="module")
def acceso():
    """Carga la config real una vez, conecta una sola vez y reúne todas las señales."""
    with Session(engine) as s:
        ig = s.exec(select(Integracion).where(
            Integracion.centro_id == CENTRO_ID,
            Integracion.tipo == "email_imap")).first()

    if not ig or not (ig.config or {}).get("password"):
        pytest.skip("No hay config IMAP con password para el centro: nada que comprobar.")

    cfg = dict(ig.config)
    conn = gmail_imap.test_connection(cfg)          # 1.2
    folders, allbox = [], None
    if conn.get("ok"):
        cli = gmail_imap._connect(cfg)
        typ, boxes = cli.list()                     # 1.3
        folders = boxes or [] if typ == "OK" else []
        allbox = gmail_imap._carpeta_todos(cli)
        cli.logout()
    recientes = gmail_imap.fetch_recientes(cfg, max_msgs=5)  # 1.4
    return {"activo": ig.activo, "usuario": cfg.get("usuario"),
            "conn": conn, "folders": folders, "allbox": allbox, "recientes": recientes}


def test_1_1_config_imap_existe(acceso):
    # Si llega aquí (no se saltó), la config existe y tiene password.
    assert acceso["usuario"], "La integración email_imap no tiene usuario configurado."


def test_1_2_login_real(acceso):
    assert acceso["conn"].get("ok"), f"Login IMAP falló: {acceso['conn'].get('error')}"


def test_1_3_buzones_listados_y_carpeta_all(acceso):
    assert len(acceso["folders"]) > 0, "No se listó ningún buzón."
    assert acceso["allbox"], "No se encontró la carpeta \\All (Todos los mensajes) del backlog."


def test_1_4_lectura_real(acceso):
    assert isinstance(acceso["recientes"], list), "fetch_recientes no devolvió una lista."
    assert len(acceso["recientes"]) > 0, "No se pudo leer ningún correo reciente (lectura real falla)."
