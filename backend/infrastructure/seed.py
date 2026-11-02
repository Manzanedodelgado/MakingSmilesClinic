"""Seed de desarrollo — da vida mínima al organismo para poder probar F0.

Idempotente: si ya hay un centro, no hace nada. Crea:
  - 1 operador de plataforma (superadmin)   → nivel 1
  - 1 centro                                 → nodo-dios
  - catálogo de permisos finos + rol Administrador con todos
  - 1 usuario de centro con ese rol (acceso vía user_center_roles)
  - config de ejemplo (global + centro + sistema agenda)

Credenciales dev: admin@makingsmiles.local / admin1234
"""
from datetime import date
from sqlmodel import Session, select

from domain.models.agenda import EstadoCita, TipoCita
from domain.models.config import Configuracion
from domain.models.economico import FormaPago
from domain.models.core import Centro, Especialidad, RazonSocial
from domain.models.identidad import (
    Area, Permiso, PlatformUser, Rol, RolePermiso, Sistema, Usuario, UserCenterPermiso, UserCenterRole,
    UsuarioPeriodo,
)
from infrastructure.security import hash_password

# Sistemas del organismo (grupos): codigo, nombre, orden
SISTEMAS = [
    ("cuidarte", "CUIDARTE", 1),
    ("escucharte", "ESCÚCHARTE", 2),
    ("gestionalo", "GESTIÓNALO", 3),
    ("ia", "IA", 4),
    ("configuracion", "Configuración", 5),
    ("superuser", "SuperUser", 6),
]

# Áreas (pantallas) por sistema: sistema_codigo, codigo, nombre
AREAS = [
    ("cuidarte", "inicio", "Inicio"),
    ("cuidarte", "agenda", "Agenda"),
    ("cuidarte", "pacientes", "Pacientes"),
    ("escucharte", "whatsapp", "WhatsApp"),
    ("escucharte", "motion", "Automatizaciones"),
    ("gestionalo", "crm", "CRM"),
    ("gestionalo", "gestoria", "Gestoría"),
    ("gestionalo", "informes", "Informes"),
    ("ia", "ia", "IAs"),
    ("configuracion", "config", "Configuración"),
    ("superuser", "superuser", "SuperUser"),
]

# Estados de cita (catálogo). codigo, nombre, color, orden. (de TVarias)
ESTADOS_CITA = [
    ("solicitada", "Solicitada por paciente", "#2DD9C3", 0),
    ("planificada", "Planificada", "#3498db", 1),
    ("sala_espera", "Sala de Espera", "#9b59b6", 2),
    ("consulta", "Consulta", "#1abc9c", 3),
    ("confirmada", "Confirmada", "#f39c12", 4),
    ("aceptada", "Aceptada", "#16a085", 5),
    ("pte_firma", "Pte. Firma", "#e67e22", 6),
    ("finalizada", "Finalizada", "#2ecc71", 7),
    ("anulada", "Anulada", "#e74c3c", 8),
    ("cancelada", "Cancelada", "#95a5a6", 9),
]

# Especialidades (de TVarias)
ESPECIALIDADES = [
    "Recepcion", "Auxiliar", "Higienista", "General", "Endodoncista",
    "Ortodoncista", "Cirugia", "Implantologia", "Periodoncia",
    "Prostodoncista", "Mantenimiento", "Direccion",
]

# Tipos de cita en agenda (de TVarias). nombre.
TIPOS_CITA = [
    "Control", "Urgencia", "Protesis Fija", "Cirugia/Injerto", "Retirar Ortodoncia",
    "Protesis Removible", "Colocacion Ortodoncia", "Periodoncia", "Cirugia de Implante",
    "Mensualidad Ortodoncia", "Ajuste Prot/tto", "Primera Visita", "Higiene Dental",
    "Endodoncia", "Reconstruccion", "Exodoncia", "Estudio Ortodoncia", "Rx/escaner",
]

PERMISOS = [
    ("config.ver", "Ver configuración"),
    ("config.editar", "Editar configuración"),
    ("pacientes.ver", "Ver pacientes"),
    ("pacientes.editar", "Crear/editar pacientes"),
    ("citas.ver", "Ver agenda"),
    ("citas.editar", "Crear/editar citas"),
    ("gestoria.ver", "Ver gestoría / contabilidad"),
    ("gestoria.editar", "Crear/editar gestoría"),
    ("gestoria.facturacion.ver", "Asesoría — Facturación (Facturas + Debe/Haber), solo lectura"),
    ("informes.ver", "Ver / ejecutar informes"),
    ("informes.editar", "Crear / guardar / borrar informes"),
    ("comunicacion.ver", "Ver comunicación / WhatsApp"),
    ("comunicacion.editar", "Enviar mensajes y configurar WhatsApp"),
    # Pestañas por área (solo cuentan junto al permiso del área; ver migración 097)
    ("pacientes.tab.ficha", "Pacientes · Ficha"),
    ("pacientes.tab.filiacion", "Pacientes · Filiación"),
    ("pacientes.tab.presupuestos", "Pacientes · Presupuestos"),
    ("pacientes.tab.documentos", "Pacientes · Documentos"),
    ("pacientes.tab.plan-econ", "Pacientes · Plan económico"),
    ("gestoria.tab.facturacion", "Gestoría · Facturación"),
    ("gestoria.tab.produccion", "Gestoría · Producción"),
    ("config.tab.clinica", "Configuración · Clínica"),
    ("config.tab.admin", "Configuración · Admin"),
    ("config.tab.conectores", "Configuración · Conectores"),
    ("config.tab.automatizaciones", "Configuración · Automatizaciones"),
    ("config.tab.flujos", "Configuración · Flujos"),
    ("config.tab.agentes", "Configuración · Agentes IA"),
    ("gestoria.tab.facturacion.debehaber", "Gestoría · Facturación · Debe / Haber"),
    ("gestoria.tab.facturacion.facturas", "Gestoría · Facturación · Facturas"),
    ("gestoria.tab.facturacion.pagos", "Gestoría · Facturación · Pagos"),
    ("gestoria.tab.facturacion.impuestos", "Gestoría · Facturación · Impuestos"),
    ("gestoria.tab.facturacion.envio", "Gestoría · Facturación · Envío"),
    ("gestoria.tab.facturacion.historico", "Gestoría · Facturación · Histórico"),
    ("gestoria.tab.facturacion.gestor", "Gestoría · Facturación · Gestor IA"),
    ("gestoria.tab.produccion.tratamientos", "Gestoría · Producción · Tratamientos"),
    ("gestoria.tab.produccion.doctores", "Gestoría · Producción · Doctores"),
    ("gestoria.tab.produccion.pacientes", "Gestoría · Producción · Pacientes"),
    ("config.tab.clinica.centro", "Configuración · Clínica · Centro"),
    ("config.tab.clinica.agenda", "Configuración · Clínica · Agenda"),
    ("config.tab.clinica.personal", "Configuración · Clínica · Personal"),
    ("config.tab.clinica.colaboradores", "Configuración · Clínica · Colaboradores"),
    ("config.tab.admin.diseno", "Configuración · Admin · Diseño"),
    ("config.tab.admin.documentos", "Configuración · Admin · Documentos"),
    ("config.tab.admin.tablas", "Configuración · Admin · Tablas"),
    ("config.tab.conectores.whatsapp", "Configuración · Conectores · WhatsApp"),
    ("config.tab.conectores.voicebot", "Configuración · Conectores · Voicebot"),
    ("config.tab.conectores.mail", "Configuración · Conectores · Mail"),
    ("config.tab.conectores.drive", "Configuración · Conectores · Drive"),
    ("config.tab.conectores.radiografias", "Configuración · Conectores · Radiografías"),
    ("config.tab.conectores.servidor", "Configuración · Conectores · Servidor"),
    ("config.tab.automatizaciones.reglas", "Configuración · Automatizaciones · Reglas"),
    ("config.tab.automatizaciones.editor", "Configuración · Automatizaciones · Editor"),
    ("config.tab.automatizaciones.plantillas", "Configuración · Automatizaciones · Plantillas"),
    ("config.tab.flujos.flujos", "Configuración · Flujos · Flujos"),
    ("config.tab.flujos.editor", "Configuración · Flujos · Editor"),
]


FORMAS_PAGO = [
    (1, "D", "Domiciliación", "Domiciliación", True, 50), (2, "E", "Efectivo", "Efectivo", True, 10),
    (3, "L", "Letras", "Otros", False, 200), (4, "M", "Mutua", "Mutua", True, 70),
    (5, "T", "Talón", "Talón", True, 80), (6, "C", "Tarjeta de crédito", "Tarjeta", True, 20),
    (7, "F", "Transferencia", "Transferencia", True, 40), (8, "N", "Financiación", "Financiación", True, 60),
    (9, "P", "Efectivo pronto pago", "Efectivo", False, 110), (10, "J", "Tarjeta pronto pago", "Tarjeta", False, 120),
    (11, "M", "Mutua con tarjeta", "Tarjeta", False, 130), (12, "M", "Mutua con talón", "Mutua", False, 140),
    (13, None, "Descuento en nómina", "Otros", False, 210), (14, None, "Pago Eurodent", "Eurodent", False, 150),
    (15, None, "Redondeo", "Otros", False, 220), (16, None, "Bizum", "Bizum", True, 30),
]


def seed_dev(session: Session) -> None:
    if session.exec(select(Centro)).first():
        return  # ya sembrado

    # Nivel 1 — operador de plataforma
    session.add(PlatformUser(
        email="root@makingsmiles.local", nombre="Root Plataforma",
        password_hash=hash_password("root1234"), rol="superadmin",
    ))

    # Nodo-dios centro
    centro = Centro(
        nombre="Rubio García Dental", codigo="RGD", cif="B88393764",
        direccion="C/ Mayor 19", cp="28921", poblacion="Alcorcón", provincia="Madrid",
        telefono="916410841", telefono_movil="664218253",
        email="info@rubiogarciadental.com", web="www.rubiogarciadental.com",
        instagram="@rubiogarciadental", num_gabinetes=2,
    )
    session.add(centro)
    session.commit()
    session.refresh(centro)

    # Razón social facturadora del centro
    session.add(RazonSocial(
        centro_id=centro.id, nombre="Tridental Odontologos SLP", cif="B88393764",
    ))

    # Permisos + rol Administrador (todos)
    permisos = [Permiso(codigo=c, descripcion=d) for c, d in PERMISOS]
    session.add_all(permisos)
    session.commit()
    for p in permisos:
        session.refresh(p)

    rol_admin = Rol(centro_id=centro.id, nombre="Administrador", descripcion="Acceso total al centro")
    session.add(rol_admin)
    session.commit()
    session.refresh(rol_admin)
    session.add_all([RolePermiso(rol_id=rol_admin.id, permiso_id=p.id) for p in permisos])

    # Usuario de centro + acceso + periodo laboral (para estar activo)
    usuario = Usuario(
        email="admin@makingsmiles.local", nombre="Admin Demo",
        password_hash=hash_password("admin1234"),
    )
    session.add(usuario)
    session.commit()
    session.refresh(usuario)
    session.add(UserCenterRole(usuario_id=usuario.id, centro_id=centro.id, rol_id=rol_admin.id))
    # Permisos EFECTIVOS = concesiones directas (permisos_de lee user_center_permisos, no el rol).
    session.add_all([UserCenterPermiso(usuario_id=usuario.id, centro_id=centro.id, permiso_id=p.id)
                     for p in permisos])
    session.add(UsuarioPeriodo(usuario_id=usuario.id, centro_id=centro.id, orden=0, staff_tipo="ADMINISTRADOR", fecha_alta=date(2026, 1, 1)))
    session.commit()

    # Catálogos de TVarias: estados de cita, especialidades, tipos de cita
    session.add_all([
        EstadoCita(centro_id=centro.id, codigo=c, nombre=n, color=col, orden=o)
        for c, n, col, o in ESTADOS_CITA
    ])
    session.add_all([
        Especialidad(centro_id=centro.id, nombre=n, activo=True)
        for n in ESPECIALIDADES
    ])
    session.add_all([
        TipoCita(centro_id=centro.id, nombre=n, activo=True)
        for n in TIPOS_CITA
    ])

    # Formas de pago de pacientes: el mismo catálogo que migrations/040_formas_pago.sql
    session.add_all([FormaPago(id=i, codigo=c, nombre=n, grupo=g, en_caja=caja, orden=o)
                     for i, c, n, g, caja, o in FORMAS_PAGO])

    # Sistemas (grupos) + áreas (pantallas)
    sistemas = {c: Sistema(codigo=c, nombre=n, orden=o) for c, n, o in SISTEMAS}
    session.add_all(sistemas.values())
    session.commit()
    for s in sistemas.values():
        session.refresh(s)
    session.add_all([
        Area(sistema_id=sistemas[sc].id, codigo=c, nombre=n, orden=i + 1)
        for i, (sc, c, n) in enumerate(AREAS)
    ])

    # Config de ejemplo en los tres niveles
    session.add_all([
        Configuracion(clave="marca.nombre", valor="MakingSmiles"),                 # global
        Configuracion(clave="marca.nombre", valor="Clínica Demo", centro_id=centro.id),  # centro gana
        Configuracion(clave="agenda.intervalo_min", valor=15, centro_id=centro.id, sistema="cuidarte"),
        Configuracion(clave="agenda.vista_defecto", valor="semana", centro_id=centro.id, sistema="cuidarte"),
    ])
    session.commit()
