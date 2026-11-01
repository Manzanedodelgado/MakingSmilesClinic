"""🧿 MEMBRANA PACIENTE — autenticación por código OTP (WhatsApp, con fallback a email).

Puerta separada de AuthService (personal de centro): identidad distinta (Paciente, no
Usuario), JWT distinto (tipo="paciente"). Mismo rigor que el reset de contraseña de staff
(auth_service.py): código de un solo uso, hash en reposo, caducidad corta, anti-enumeración,
freno al fuerza bruta reutilizando la tabla auditoria igual que el login de personal.
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select, text

from domain.config.settings import settings
from domain.models.auditoria import Auditoria
from domain.models.core import Centro, Paciente, PacienteOtp
from domain.services import telefono as tel
from infrastructure.mailer import send_email
from infrastructure.security import create_access_token

logger = logging.getLogger("centinela.paciente_auth")


class PacienteAuthError(Exception):
    """Identificador no encontrado, código inválido/caducado, o límite de intentos."""


class PacienteAuthNombreRequerido(PacienteAuthError):
    """El código es correcto pero varios pacientes comparten este teléfono: hace
    falta nombre y apellidos para saber a cuál pertenece la sesión."""
    def __init__(self) -> None:
        super().__init__("Varias fichas comparten este teléfono. Escribe tu nombre y apellidos.")


class PacienteAuthService:
    def __init__(self, session: Session):
        self.session = session

    # ───────────────────── auditoría (mismo patrón que AuthService) ─────────────────────
    def audit(self, accion: str, *, paciente_id: Optional[int] = None, centro_id: Optional[int] = None,
              recurso: Optional[str] = None, ip: Optional[str] = None, exito: bool = True) -> None:
        self.session.add(Auditoria(
            accion=accion, centro_id=centro_id, recurso=recurso, ip=ip, exito=exito,
            detalle={"paciente_id": paciente_id} if paciente_id else None,
        ))
        self.session.commit()

    # ───────────────────── localizar paciente por teléfono o email ─────────────────────
    def _buscar_paciente(self, identificador: str) -> Optional[Paciente]:
        identificador = (identificador or "").strip()
        if not identificador:
            return None
        u9 = tel.ultimos9(identificador)
        if len(u9) == 9:
            # Igualdad por últimos-9 dígitos (nunca subcadena — bug ya corregido en telefono.py),
            # calculada en SQL para no cargar todos los pacientes en memoria.
            #
            # OJO — puede haber MÁS DE UN paciente activo con el mismo teléfono.
            # Sin ORDER BY, Postgres puede devolver cualquiera de forma no determinista.
            # Se prioriza: 1) el que tiene canal de contacto (whatsapp o email), 2) el más
            # reciente. La desambiguación real (quién es quién) se hace con nombre y
            # apellidos en solicitar/verificar_codigo, no aquí.
            p = self.session.exec(
                select(Paciente).where(
                    Paciente.activo == True,  # noqa: E712
                    text("right(regexp_replace(coalesce(telefono_movil,''), '\\D', '', 'g'), 9) = :u9"),
                ).params(u9=u9)
                .order_by(
                    text("(acepta_whatsapp AND telefono_movil IS NOT NULL) DESC"),
                    text("(email IS NOT NULL AND email <> '') DESC"),
                    Paciente.id.desc(),
                )
            ).first()
            if p:
                return p
        return self.session.exec(
            select(Paciente).where(Paciente.email == identificador, Paciente.activo == True)  # noqa: E712
            .order_by(Paciente.id.desc())
        ).first()

    def _buscar_pacientes_por_telefono(self, identificador: str) -> list[Paciente]:
        """TODOS los pacientes activos que comparten este telefono (no solo el "mejor").
        Usado para poder desambiguar por nombre cuando hay mas de uno — ver verificar_codigo."""
        u9 = tel.ultimos9((identificador or "").strip())
        if len(u9) != 9:
            return []
        return list(self.session.exec(
            select(Paciente).where(
                Paciente.activo == True,  # noqa: E712
                text("right(regexp_replace(coalesce(telefono_movil,''), '\\D', '', 'g'), 9) = :u9"),
            ).params(u9=u9)
            .order_by(
                text("(acepta_whatsapp AND telefono_movil IS NOT NULL) DESC"),
                text("(email IS NOT NULL AND email <> '') DESC"),
                Paciente.id.desc(),
            )
        ).all())

    @staticmethod
    def _normaliza_nombre(s: str) -> str:
        """minusculas, sin acentos, sin espacios repetidos — para comparar nombre+apellidos
        tolerando como los escriba el paciente."""
        import unicodedata
        s = unicodedata.normalize("NFKD", (s or "")).encode("ascii", "ignore").decode()
        return " ".join(s.lower().split())

    # ───────────────────── freno al fuerza bruta (misma tabla que staff) ─────────────────────
    def _intentos_recientes(self, identificador: str, ip: Optional[str], accion: str) -> int:
        desde = datetime.utcnow() - timedelta(minutes=settings.otp_ventana_min)
        cond = Auditoria.recurso == identificador
        if ip:
            cond = cond | (Auditoria.ip == ip)
        return len(self.session.exec(
            select(Auditoria).where(
                Auditoria.accion == accion,
                Auditoria.exito == False,  # noqa: E712
                Auditoria.created_at >= desde,
                cond,
            )
        ).all())

    # ───────────────────── solicitar código ─────────────────────
    def solicitar_codigo(self, identificador: str, *, nombre_apellidos: Optional[str] = None,
                         ip: Optional[str] = None) -> None:
        """Genera y envía un código de 6 dígitos por WhatsApp (si acepta_whatsapp) o email.
        Silencioso: nunca revela si el identificador existe ni si el envío falló
        (anti-enumeración, mismo principio que solicitar_reset de staff).

        Si el teléfono lo comparten varios pacientes, el nombre y apellidos son
        obligatorios ANTES de enviar nada: el código se emite solo para el
        paciente identificado, nunca uno común para todos."""
        if settings.otp_max_intentos and \
           self._intentos_recientes(identificador, ip, "paciente.otp.solicitar") >= settings.otp_max_intentos:
            self.audit("paciente.otp.solicitar.bloqueado", recurso=identificador, ip=ip, exito=False)
            return

        candidatos = self._buscar_pacientes_por_telefono(identificador)
        if len(candidatos) > 1:
            objetivo = self._normaliza_nombre(nombre_apellidos or "")
            elegidos = [
                c for c in candidatos
                if objetivo and objetivo in self._normaliza_nombre(f"{c.nombre or ''} {c.apellidos or ''}")
            ]
            if len(elegidos) != 1:
                self.audit("paciente.otp.solicitar.requiere_nombre", recurso=identificador, ip=ip, exito=False)
                raise PacienteAuthNombreRequerido()
            paciente = elegidos[0]
        else:
            paciente = candidatos[0] if candidatos else self._buscar_paciente(identificador)
        if not paciente:
            self.audit("paciente.otp.solicitar", recurso=identificador, ip=ip, exito=False)
            return

        codigo = f"{secrets.randbelow(1_000_000):06d}"
        codigo_hash = hashlib.sha256(codigo.encode()).hexdigest()

        # invalida OTPs previos sin usar de ESTE paciente (evita acumulación/confusión)
        previos = self.session.exec(
            select(PacienteOtp).where(
                PacienteOtp.paciente_id == paciente.id, PacienteOtp.usado_at.is_(None),
            )
        ).all()
        for o in previos:
            o.usado_at = datetime.utcnow()
            self.session.add(o)

        canal: Optional[str] = None
        if paciente.acepta_whatsapp and paciente.telefono_movil:
            try:
                # import diferido: evita ciclo de imports entre servicios de aplicación
                from application.services.comunicacion_service import ComunicacionService
                centro = self.session.get(Centro, paciente.centro_id)
                nombre_centro = centro.nombre if centro else "la clínica"
                texto = (
                    f"Tu código de acceso a {nombre_centro} es {codigo}. "
                    f"Caduca en {settings.otp_expira_min} minutos."
                )
                ComunicacionService(self.session).enviar_texto(paciente.centro_id, paciente.telefono_movil, texto)
                canal = "whatsapp"
            except Exception:
                logger.warning("OTP: fallo envío WhatsApp para paciente %s, probando email", paciente.id)

        if canal is None and paciente.email:
            html = (
                f"<p>Tu código de acceso es <b>{codigo}</b>. "
                f"Caduca en {settings.otp_expira_min} minutos.</p>"
            )
            if send_email(self.session, paciente.email, "Tu código de acceso", html):
                canal = "email"

        if canal is None:
            logger.warning("OTP: paciente %s sin canal de contacto disponible (whatsapp/email)", paciente.id)
            self.audit("paciente.otp.solicitar", paciente_id=paciente.id, centro_id=paciente.centro_id,
                       recurso=identificador, ip=ip, exito=False)
            return

        expira = datetime.utcnow() + timedelta(minutes=settings.otp_expira_min)
        self.session.add(PacienteOtp(
            paciente_id=paciente.id, centro_id=paciente.centro_id, codigo_hash=codigo_hash,
            canal=canal, expira_at=expira,
        ))
        self.session.commit()
        self.audit("paciente.otp.solicitar", paciente_id=paciente.id, centro_id=paciente.centro_id,
                   recurso=identificador, ip=ip, exito=True)

    # ───────────────────── verificar código → JWT de paciente ─────────────────────
    def verificar_codigo(self, identificador: str, codigo: str, *,
                         nombre_apellidos: Optional[str] = None, ip: Optional[str] = None) -> dict:
        if settings.otp_max_intentos and \
           self._intentos_recientes(identificador, ip, "paciente.login") >= settings.otp_max_intentos:
            self.audit("paciente.login.bloqueado", recurso=identificador, ip=ip, exito=False)
            raise PacienteAuthError("Demasiados intentos. Inténtalo más tarde.")

        candidatos = self._buscar_pacientes_por_telefono(identificador)
        if not candidatos:
            paciente_email = self._buscar_paciente(identificador)  # fallback: login por email
            candidatos = [paciente_email] if paciente_email else []
        if not candidatos:
            self.audit("paciente.login", recurso=identificador, ip=ip, exito=False)
            raise PacienteAuthError("Código inválido o caducado")

        codigo_hash = hashlib.sha256((codigo or "").encode()).hexdigest()
        ahora = datetime.utcnow()
        # Un OTP valido por candidato (el mismo código se emitió para todos a la vez).
        validos: list[tuple[Paciente, PacienteOtp]] = []
        for c in candidatos:
            otp = self.session.exec(
                select(PacienteOtp).where(
                    PacienteOtp.paciente_id == c.id,
                    PacienteOtp.codigo_hash == codigo_hash,
                    PacienteOtp.usado_at.is_(None),
                ).order_by(PacienteOtp.id.desc())
            ).first()
            if otp and otp.expira_at >= ahora:
                validos.append((c, otp))

        if not validos:
            self.audit("paciente.login", recurso=identificador, ip=ip, exito=False)
            raise PacienteAuthError("Código inválido o caducado")

        if len(validos) == 1:
            paciente, otp = validos[0]
        else:
            # Varios pacientes activos comparten este teléfono (duplicado de datos, no
            # tutor+menores): el código por sí solo no basta para saber quién es. Se pide
            # nombre y apellidos para desambiguar entre los candidatos de ESTE teléfono.
            if not nombre_apellidos or not nombre_apellidos.strip():
                self.audit("paciente.login.requiere_nombre", recurso=identificador, ip=ip, exito=False)
                raise PacienteAuthNombreRequerido()
            objetivo = self._normaliza_nombre(nombre_apellidos)
            coincidencias = [
                (c, o) for c, o in validos
                if objetivo and objetivo in self._normaliza_nombre(f"{c.nombre or ''} {c.apellidos or ''}")
            ]
            if len(coincidencias) != 1:
                self.audit("paciente.login.nombre_no_coincide", recurso=identificador, ip=ip, exito=False)
                raise PacienteAuthError("No hemos podido verificar el nombre. Revisa cómo aparece en tu ficha.")
            paciente, otp = coincidencias[0]

        # Este código ya no sirve para NINGÚN candidato del teléfono (un solo uso real).
        otros = self.session.exec(
            select(PacienteOtp).where(
                PacienteOtp.paciente_id.in_([c.id for c in candidatos]),
                PacienteOtp.codigo_hash == codigo_hash,
                PacienteOtp.usado_at.is_(None),
            )
        ).all()
        for o in otros:
            o.usado_at = ahora
            self.session.add(o)
        self.session.commit()

        token = create_access_token(
            {"sub": str(paciente.id), "tipo": "paciente", "paciente_id": paciente.id, "centro_id": paciente.centro_id},
            expires_minutes=settings.paciente_token_expire_minutes,
        )
        self.audit("paciente.login", paciente_id=paciente.id, centro_id=paciente.centro_id,
                   recurso=identificador, ip=ip, exito=True)
        return {
            "access_token": token,
            "token_type": "bearer",
            "paciente": {"id": paciente.id, "nombre": paciente.nombre, "centro_id": paciente.centro_id},
        }
