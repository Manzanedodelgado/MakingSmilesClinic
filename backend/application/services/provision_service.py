"""👁️‍🗨️ SUPERCREADOR — provisioning de un centro nuevo.

`POST /superuser/centros` solo insertaba la fila en `centros` (nombre/plan/módulos):
sin razón social, sin rol, sin usuario, sin catálogos de agenda, el centro quedaba
creado pero inservible — nadie tenía acceso y no había con qué trabajar.

Este servicio da de alta un centro OPERATIVO de un tirón:
  1. centro (fila real, mismas columnas que ya usa superuser_router)
  2. razón social mínima (se completa después en Config → Centro)
  3. agenda por defecto + catálogo de estados/tipos de cita (para que Agenda funcione)
  4. rol "Administrador" del centro (satisface el FK de user_center_roles; los permisos
     efectivos NO salen de aquí — ver AuthService.permisos_de)
  5. usuario administrador + acceso (user_center_roles) + TODOS los permisos existentes
     concedidos directos (user_center_permisos, la fuente real de autorización)
  6. config mínima de agenda para ese centro

Reutiliza el catálogo GLOBAL ya sembrado (Permiso, Sistema/Area) — nunca lo duplica;
Permiso.codigo y Sistema.codigo son UNIQUE a nivel de toda la plataforma.
"""
import json
import secrets
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlmodel import Session, select

from application.services.auth_service import AuthService, PERMISO_NO_GESTIONABLE
from application.services.config_service import ConfigService
from domain.models.agenda import Agenda, EstadoCita, TipoCita
from domain.models.core import Centro, CentroAsociacion, RazonSocial
from domain.models.identidad import (
    Permiso, Rol, RolePermiso, Usuario, UserCenterPermiso, UserCenterRole, UsuarioPeriodo,
)
from infrastructure.security import hash_password

# Catálogo operativo real de una clínica dental — MISMO contenido que infrastructure/seed.py
# (ESTADOS_CITA/TIPOS_CITA), verbatim. Esta plataforma es específicamente para clínicas
# dentales (odontograma, tratamientos…), no un SaaS genérico: no tiene sentido dar de alta
# un centro nuevo con un catálogo recortado cuando ya existe el real y probado.
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
TIPOS_CITA = [
    "Control", "Urgencia", "Protesis Fija", "Cirugia/Injerto", "Retirar Ortodoncia",
    "Protesis Removible", "Colocacion Ortodoncia", "Periodoncia", "Cirugia de Implante",
    "Mensualidad Ortodoncia", "Ajuste Prot/tto", "Primera Visita", "Higiene Dental",
    "Endodoncia", "Reconstruccion", "Exodoncia", "Estudio Ortodoncia", "Rx/escaner",
]


class ProvisionError(RuntimeError):
    """Datos insuficientes o en conflicto para dar de alta el centro."""


def compartir_personal_existente(
    session: Session, *, centro_id: int, centro_asociado_id: int, nombre_asociado: str,
    excluir_usuario_id: Optional[int] = None,
) -> int:
    """El personal YA existente (identidad global en `usuarios`) del centro asociado recibe
    acceso también en `centro_id`, con SUS MISMOS permisos exactos (nunca "Administrador"):
    no se duplica identidad, no se sobre-concede. Reutilizado por ProvisionService (al crear)
    y por el endpoint de editar asociación (al activarla después de creado el centro)."""
    rol_compartido = session.exec(select(Rol).where(
        Rol.centro_id == centro_id, Rol.nombre == "Personal (compartido)")).first()
    if not rol_compartido:
        rol_compartido = Rol(centro_id=centro_id, nombre="Personal (compartido)",
                             descripcion=f"Acceso heredado de {nombre_asociado}")
        session.add(rol_compartido)
        session.commit()
        session.refresh(rol_compartido)
    accesos_origen = session.exec(select(UserCenterRole).where(
        UserCenterRole.centro_id == centro_asociado_id)).all()
    compartidos = 0
    for acceso in accesos_origen:
        if acceso.usuario_id == excluir_usuario_id:
            continue
        ya_tiene = session.exec(select(UserCenterRole).where(
            UserCenterRole.usuario_id == acceso.usuario_id, UserCenterRole.centro_id == centro_id)).first()
        if ya_tiene:
            continue
        session.add(UserCenterRole(usuario_id=acceso.usuario_id, centro_id=centro_id, rol_id=rol_compartido.id))
        permisos_origen = session.exec(select(UserCenterPermiso.permiso_id).where(
            UserCenterPermiso.usuario_id == acceso.usuario_id,
            UserCenterPermiso.centro_id == centro_asociado_id)).all()
        session.add_all([
            UserCenterPermiso(usuario_id=acceso.usuario_id, centro_id=centro_id, permiso_id=pid)
            for pid in permisos_origen
        ])
        compartidos += 1
    session.commit()
    return compartidos


class ProvisionService:
    def __init__(self, session: Session):
        self.session = session

    def provisionar_centro(
        self, *, nombre: str, admin_nombre: str, admin_email: str,
        plan: Optional[str] = None, modulos_activos: Optional[list[str]] = None,
        actor_usuario_id: Optional[int] = None,
        asociado_a_centro_id: Optional[int] = None, comparte_personal: bool = False,
        comparte_razon_social: bool = False, comparte_pacientes: bool = False,
    ) -> dict:
        nombre = (nombre or "").strip()
        admin_nombre = (admin_nombre or "").strip()
        admin_email = (admin_email or "").strip().lower()
        if not nombre:
            raise ProvisionError("El nombre del centro es obligatorio")
        if not admin_nombre or not admin_email:
            raise ProvisionError("El nombre y el email del administrador son obligatorios")
        if self.session.exec(select(Usuario).where(Usuario.email == admin_email)).first():
            raise ProvisionError(f"Ya existe un usuario con el email {admin_email}")

        comparte_algo = comparte_personal or comparte_razon_social or comparte_pacientes
        centro_asociado: Optional[Centro] = None
        if asociado_a_centro_id is not None:
            centro_asociado = self.session.get(Centro, asociado_a_centro_id)
            if not centro_asociado:
                raise ProvisionError("El centro al que se asocia no existe")
        elif comparte_algo:
            raise ProvisionError("Para compartir algo hay que elegir a qué centro se asocia")

        # 1) Centro — mismo INSERT crudo que centros_create (el ORM Centro no modela
        #    estado/plan/modulos_activos; ver nota en superuser_router.py).
        centro_id = self.session.execute(text(
            "INSERT INTO centros (created_at, updated_at, nombre, estado, plan, modulos_activos, activo) "
            "VALUES (now(), now(), :n, 'activo', :p, :m, true) RETURNING id"
        ), {"n": nombre, "p": plan, "m": json.dumps(modulos_activos or [])}).scalar_one()

        if centro_asociado is not None:
            self.session.add(CentroAsociacion(
                centro_id=centro_id, asociado_a_centro_id=centro_asociado.id,
                comparte_personal=comparte_personal, comparte_razon_social=comparte_razon_social,
                comparte_pacientes=comparte_pacientes,
            ))

        # 2) Razón social — propia (mínima, se completa en Config → Centro) O, si
        #    comparte_razon_social, ninguna propia: factura con la del centro asociado.
        razon_social_compartida_id = None
        if comparte_razon_social:
            rs_asociada = self.session.exec(select(RazonSocial).where(
                RazonSocial.centro_id == centro_asociado.id, RazonSocial.activa == True  # noqa: E712
            )).first()
            if not rs_asociada:
                raise ProvisionError(f"El centro asociado ({centro_asociado.nombre}) no tiene razón social activa que compartir")
            razon_social_compartida_id = rs_asociada.id
            self.session.execute(text("UPDATE centros SET razon_social_compartida_id = :rid WHERE id = :cid"),
                                 {"rid": razon_social_compartida_id, "cid": centro_id})
        else:
            self.session.add(RazonSocial(centro_id=centro_id, nombre=nombre))

        # 3) Agenda por defecto + catálogos (con agenda_id: si se dejan sin asignar,
        #    Config → Agenda no los muestra — ese fue justo el bug de seed_dev()).
        # Nombre: "Agenda 1", igual que el patrón real del centro 1 — no hay forma de
        # renombrar una agenda desde la UI (Config → Agenda solo edita intervalo/vista),
        # así que inventar un nombre distinto aquí dejaría al cliente atascado con él.
        agenda = Agenda(centro_id=centro_id, nombre="Agenda 1", color="#065AED",
                        intervalo_min=15, vista_defecto="Semana", orden=0)
        self.session.add(agenda)
        self.session.commit()
        self.session.refresh(agenda)
        self.session.add_all([
            EstadoCita(centro_id=centro_id, agenda_id=agenda.id, codigo=c, nombre=n, color=col, orden=o)
            for c, n, col, o in ESTADOS_CITA
        ])
        self.session.add_all([
            TipoCita(centro_id=centro_id, agenda_id=agenda.id, nombre=n)
            for n in TIPOS_CITA
        ])

        # 4) Rol "Administrador" del centro — satisface el FK de user_center_roles.
        #    Los permisos EFECTIVOS no salen de aquí (AuthService.permisos_de lee
        #    user_center_permisos directo), pero el acceso/membresía sí exige un rol.
        rol_admin = Rol(centro_id=centro_id, nombre="Administrador", descripcion="Acceso total al centro")
        self.session.add(rol_admin)
        self.session.commit()
        self.session.refresh(rol_admin)
        # El admin de un centro recibe TODOS los permisos DE CENTRO — nunca los de
        # PERMISO_NO_GESTIONABLE (plataforma; hoy solo "superuser"), que son concesión
        # manual aparte. Misma regla que usa Config → Personal (configuracion_staff_router).
        permisos = self.session.exec(select(Permiso).where(Permiso.codigo.notin_(PERMISO_NO_GESTIONABLE))).all()
        if not permisos:
            raise ProvisionError("No hay catálogo de permisos en la plataforma — provisionar sin permisos dejaría al admin sin acceso")
        self.session.add_all([RolePermiso(rol_id=rol_admin.id, permiso_id=p.id) for p in permisos])

        # 5) Usuario administrador — password temporal generada, se devuelve UNA vez.
        password_temporal = secrets.token_urlsafe(9)
        usuario = Usuario(nombre=admin_nombre, email=admin_email,
                          password_hash=hash_password(password_temporal))
        self.session.add(usuario)
        self.session.commit()
        self.session.refresh(usuario)
        self.session.add(UserCenterRole(usuario_id=usuario.id, centro_id=centro_id, rol_id=rol_admin.id))
        self.session.add_all([
            UserCenterPermiso(usuario_id=usuario.id, centro_id=centro_id, permiso_id=p.id)
            for p in permisos
        ])
        self.session.add(UsuarioPeriodo(
            usuario_id=usuario.id, centro_id=centro_id, orden=0, staff_tipo="ADMINISTRADOR",
            fecha_alta=date.today(),
        ))
        self.session.commit()

        # 5b) Personal compartido — el personal YA existente del centro asociado recibe
        # acceso también aquí (helper compartido con el endpoint de editar asociación).
        personal_compartido = 0
        if comparte_personal:
            personal_compartido = compartir_personal_existente(
                self.session, centro_id=centro_id, centro_asociado_id=centro_asociado.id,
                nombre_asociado=centro_asociado.nombre, excluir_usuario_id=usuario.id,
            )

        # 6) Config mínima de agenda para este centro.
        cfg = ConfigService(self.session)
        cfg.set("agenda.intervalo_min", 15, centro_id=centro_id, sistema="cuidarte")
        cfg.set("agenda.vista_defecto", "semana", centro_id=centro_id, sistema="cuidarte")

        AuthService(self.session).audit(
            "superuser.centro.provisionar", usuario_id=actor_usuario_id, centro_id=centro_id,
            recurso=f"centro:{centro_id}",
            detalle={"nombre": nombre, "admin_email": admin_email, "permisos": len(permisos),
                     "asociado_a_centro_id": asociado_a_centro_id, "comparte_personal": comparte_personal,
                     "comparte_razon_social": comparte_razon_social, "comparte_pacientes": comparte_pacientes,
                     "personal_compartido": personal_compartido},
        )

        return {
            "centro_id": centro_id,
            "usuario_id": usuario.id,
            "admin_email": admin_email,
            "password_temporal": password_temporal,
            "agenda_id": agenda.id,
            "razon_social_compartida_id": razon_social_compartida_id,
            "personal_compartido": personal_compartido,
        }
