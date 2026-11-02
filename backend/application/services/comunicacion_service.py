"""Comunicación / WhatsApp (capa de aplicación).

Port del módulo communication de SmileStudioPro .37 a la BBDD nueva. Orquesta:
  · credenciales Evolution por centro (integraciones, tipo='whatsapp') — multi-tenant
  · persistencia de conversaciones/mensajes con dedup ATÓMICO (ON CONFLICT)
  · match de paciente por teléfono (igualdad por últimos 9 dígitos, no subcadena)
  · envío vía Evolution y procesamiento del webhook entrante
  · confirmar/cancelar cita por WhatsApp (sobre citas + estados_cita, sin números mágicos)

Correcciones estructurales frente a la .37:
  · dedup real por message_id (índice UNIQUE) en vez de check-then-act
  · "próxima cita" filtra fecha >= hoy (la .37 cogía citas pasadas)
  · estado de cita por estados_cita.codigo legible (no IdSitC 7/999)
"""
import base64
import hashlib
import logging
import os
import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlmodel import Session, select

from domain.models.agenda import EstadoCita
from domain.models.clinico import AlertaPaciente
from domain.models.comunicacion import (
    Conversacion,
    Mensaje,
    PlantillaMensaje,
    PollContexto,
)
from domain.models.config import Integracion
from domain.models.core import Cita, CitaTratamiento, Paciente, Tratamiento
from domain.models.economico import Pago, Presupuesto, TratamientoRealizado
from domain.services import telefono as tel
from domain.services import whatsapp_flujos as wf
from infrastructure.debounce import debouncer
from infrastructure.external_apis.evolution_api import EvolutionClient, EvolutionError
from infrastructure.realtime import bus

logger = logging.getLogger(__name__)


def _iso_utc(dt: datetime | None) -> str | None:
    """.isoformat() de un datetime NAIVE que en realidad es UTC (columnas `timestamp without
    time zone`, sesión de Postgres en Etc/UTC) — sin esto, el string sale sin 'Z'/offset y el
    navegador lo interpreta como hora LOCAL ya puesta, mostrando la hora del mensaje desplazada
    por el huso horario (p.ej. 2h de menos en verano en Madrid)."""
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


# Estados de cita que cuentan como "cerrada/cancelada" → no son la próxima cita activa.
ESTADOS_INACTIVOS = ("anulada", "cancelada", "finalizada", "fallada")
# Palabras clave (mismas familias que la .37). Cancelar tiene precedencia sobre confirmar.
KW_CONFIRMAR = ("si", "sí", "claro", "confirmo", "confirmado", "de acuerdo", "ok", "perfecto", "estaré")
KW_CANCELAR = ("cancelar", "cancela", "anular", "anula", "no puedo ir", "no voy a ir", "no puedo acudir")
KW_URGENCIA = ("urgencia", "dolor", "emergencia", "sangrado", "hinchazón", "flemón", "no puedo más")


class ComunicacionService:
    def __init__(self, session: Session):
        self.session = session
        # FIX B5: inicializar directorio de media robustamente (por instancia)
        # Sin fallback a /tmp - debe fallar cerrado para evitar fugas de datos cross-tenant
        logger = logging.getLogger("comunicacion.media")

        try:
            self._MEDIA_DIR = Path(__file__).resolve().parents[2] / "media" / "whatsapp"
            self._MEDIA_DIR.mkdir(parents=True, exist_ok=True)
            # Nombre único: con varios workers/peticiones a la vez, un ".test" compartido lo
            # borraba otra petición y esta fallaba con 500 (FileNotFoundError).
            test_file = self._MEDIA_DIR / f".test-{os.getpid()}-{secrets.token_hex(6)}"
            test_file.write_text("ok")
            test_file.unlink(missing_ok=True)
            logger.debug(f"Directorio de media inicializado: {self._MEDIA_DIR}")
        except Exception as e:  # raiz: no se pudo crear/escribir media/whatsapp (ruta, permisos o disco); se aborta en vez de caer a /tmp para no filtrar datos entre centros
            logger.error(f"Inicialización de media_dir fallida: {e}. No se usa fallback para evitar fugas.")
            raise RuntimeError(f"No se pudo inicializar directorio de media WhatsApp: {e}")

    # ─────────────────────── CONFIG / INTEGRACIÓN (Evolution) ───────────────────────
    def _integracion(self, centro_id: int) -> Integracion | None:
        return self.session.exec(select(Integracion).where(
            Integracion.centro_id == centro_id, Integracion.tipo == "whatsapp")).first()

    # Las credenciales se editan en Configuración › IA's › Alex › Canales (CanalesIA),
    # que persiste en `integraciones` vía /configuracion/centro/integracion. Aquí solo
    # se LEEN para operar (estado, QR, envío). Una sola fuente de verdad.

    def _client(self, centro_id: int) -> EvolutionClient:
        ig = self._integracion(centro_id)
        if not ig or not ig.activo or not ig.config:
            raise EvolutionError("WhatsApp no configurado para este centro")
        return EvolutionClient(ig.config)

    def estado(self, centro_id: int) -> dict:
        try:
            cli = self._client(centro_id)
            st = cli.connection_state()
            estado = (st.get("instance") or {}).get("state") or st.get("state")
            numero = perfil = None
            if estado == "open":
                self.asegurar_webhook(centro_id)   # auto-cura; total por contrato
                try:
                    inst = cli.fetch_instance()        # número/propietario realmente conectado
                    numero = self._extraer_numero(inst)
                    perfil = inst.get("profileName") or inst.get("profilename")
                except Exception:  # raiz: el número es informativo; nunca rompe el estado
                    pass
            return {"evolution": True, "estado": estado, "conectado": estado == "open",
                    "numero": numero, "perfil": perfil}
        except EvolutionError as e:  # raiz: integración WhatsApp ausente/inactiva o Evolution caído; se devuelve estado no conectado con el motivo
            return {"evolution": False, "estado": None, "conectado": False, "error": str(e)}

    @staticmethod
    def _extraer_numero(inst: dict) -> str | None:
        """Número conectado a partir de la instancia (ownerJid '34648...@s.whatsapp.net' o number)."""
        raw = inst.get("ownerJid") or inst.get("owner") or inst.get("number") or ""
        n = "".join(c for c in str(raw).split("@")[0] if c.isdigit())
        return f"+{n}" if n else None

    def qr(self, centro_id: int) -> dict:
        data = self._client(centro_id).get_qr()
        return {"qrcode": data.get("base64") or data.get("code"), "raw": data}

    def desvincular(self, centro_id: int) -> dict:
        """Cierra la sesión de WhatsApp actual (logout) para poder enlazar OTRO teléfono.
        No borra la instancia ni la config: acto seguido /whatsapp/qr da el QR nuevo. Tras
        escanearlo, el webhook se reasegura solo en el próximo `estado()` con conexión 'open'."""
        try:
            self._client(centro_id).logout()
            return {"ok": True}
        except EvolutionError as e:  # raiz: Evolution caído o sesión ya cerrada al hacer logout; se informa ok=False sin propagar
            return {"ok": False, "error": str(e)}

    # ─────────────────────── WEBHOOK (recepción real de entrantes) ───────────────────────
    _WEBHOOK_EVENTS = ["MESSAGES_UPSERT", "MESSAGES_UPDATE", "SEND_MESSAGE", "CONNECTION_UPDATE"]

    def asegurar_webhook(self, centro_id: int) -> dict:
        """Garantiza que Evolution entregue los mensajes entrantes a NUESTRO webhook,
        autenticado por secreto en `?token=`. Idempotente: genera el secreto si falta y
        (re)registra el webhook en Evolution solo si difiere. Así el entrante funciona y
        sobrevive a reconexiones/re-escaneos sin tocar nada a mano (CONFIG = verdad)."""
        ig = self._integracion(centro_id)
        if not ig or not ig.config:
            return {"ok": False, "motivo": "sin integración"}
        cfg = dict(ig.config)
        secret = cfg.get("webhook_hmac") or cfg.get("webhook_secret")
        cambiado = False
        if not secret:
            secret = secrets.token_hex(16)
            cambiado = True
        # Canoniza a una sola clave `webhook_hmac` (la que muestra el form), conservando el
        # MISMO valor → el token del webhook en Evolution no cambia.
        if cfg.get("webhook_hmac") != secret or "webhook_secret" in cfg:
            cfg["webhook_hmac"] = secret
            cfg.pop("webhook_secret", None)
            cambiado = True
        base = os.getenv("WEBHOOK_BASE_URL", "http://backend:8000").rstrip("/")
        url = f"{base}/comunicacion/webhook/{centro_id}?token={secret}"
        try:
            cli = self._client(centro_id)
            try:
                actual = cli.find_webhook() or {}
            except EvolutionError:  # raiz: webhook aún no registrado o Evolution caído al leerlo; se trata como 'sin webhook' y se registra
                actual = {}
            difiere = (actual.get("url") != url or not actual.get("enabled")
                       or set(actual.get("events") or []) != set(self._WEBHOOK_EVENTS))
            if difiere:
                cli.set_webhook(url, self._WEBHOOK_EVENTS)
        except Exception:  # raiz: Evolution caído al leer o registrar el webhook; el secreto queda persistido y el llamador recibe ok=False  # noqa: BLE001
            logger.warning("comunicación: Evolution caído al asegurar webhook, secreto persistido", exc_info=True)
            return {"ok": False, "motivo": "evolution caído", "url": url}
        if cambiado:
            ig.config = cfg
            self.session.add(ig)
            self.session.commit()
        return {"ok": True, "url": url}

    # ─────────────────────── PACIENTE POR TELÉFONO ───────────────────────
    def match_paciente(self, centro_id: int, telefono: str) -> tuple[Paciente | None, int]:
        """Devuelve (paciente, nº de coincidencias). Igualdad por últimos 9 dígitos
        sobre los 3 teléfonos del paciente. Si hay >1, no se actúa automáticamente."""
        n9 = tel.ultimos9(telefono)
        if len(n9) < 9:
            return None, 0
        sql = text("""
            SELECT id FROM pacientes
            WHERE centro_id = :c AND activo = TRUE AND (
                  right(regexp_replace(coalesce(telefono_movil,''),  '\\D', '', 'g'), 9) = :n9
               OR right(regexp_replace(coalesce(telefono_fijo,''),   '\\D', '', 'g'), 9) = :n9
               OR right(regexp_replace(coalesce(telefono_fijo2,''),  '\\D', '', 'g'), 9) = :n9)
            ORDER BY id ASC
        """)
        ids = [row[0] for row in self.session.execute(sql, {"c": centro_id, "n9": n9}).all()]
        if not ids:
            return None, 0
        return self.session.get(Paciente, ids[0]), len(ids)

    # ─────────────────────── CONVERSACIONES / MENSAJES ───────────────────────
    def _get_or_create_conversacion(self, centro_id: int, telefono: str) -> int:
        canonical = tel.normalizar(telefono)
        pac, _ = self.match_paciente(centro_id, canonical)
        sql = text("""
            INSERT INTO conversaciones (centro_id, paciente_id, canal, telefono, estado, created_at, updated_at)
            VALUES (:c, :p, 'whatsapp', :tel, 'abierta', now(), now())
            ON CONFLICT (centro_id, canal, telefono) WHERE telefono IS NOT NULL
            DO UPDATE SET paciente_id = COALESCE(conversaciones.paciente_id, EXCLUDED.paciente_id),
                          updated_at = now()
            RETURNING id
        """)
        cid = self.session.execute(
            sql, {"c": centro_id, "p": pac.id if pac else None, "tel": canonical}).scalar_one()
        self.session.commit()
        return cid

    @staticmethod
    def _epoch_valido(valor) -> int | None:
        """`messageTimestamp` del webhook (int, str o {low,high} de protobuf) → epoch UTC, o
        None si falta o es absurdo (antes de 2015 o >5 min en el futuro): se usa now()."""
        if isinstance(valor, dict):
            valor = valor.get("low")
        try:
            ep = int(valor)
        except (TypeError, ValueError):  # raiz: messageTimestamp ausente, no numérico o con forma inesperada; se usa la hora de llegada
            return None
        return ep if 1420070400 <= ep <= int(datetime.now(timezone.utc).timestamp()) + 300 else None

    def guardar_entrante(self, centro_id: int, telefono: str, cuerpo: str,
                         message_id: str | None = None, epoch: int | None = None, **media) -> int:
        conv_id = self._get_or_create_conversacion(centro_id, telefono)
        self._reabrir_si_resuelta(conv_id)
        if self._insertar_mensaje(conv_id, "entrante", cuerpo, message_id, estado="leido",
                                  incrementa_no_leidos=True, epoch=epoch, **media):
            bus.publish(centro_id, {"tipo": "mensaje", "convId": conv_id, "direccion": "entrante"})
        return conv_id

    def _reabrir_si_resuelta(self, conv_id: int) -> None:
        """Un entrante nuevo en una conversación resuelta implica que el paciente retoma
        el tema: se reabre automáticamente (igual que Chatwoot/Front con nueva respuesta).
        Una conversación 'pendiente' (escalada a humano) no se toca aquí."""
        self.session.execute(text(
            "UPDATE conversaciones SET estado='abierta', updated_at=now() "
            "WHERE id=:id AND estado='resuelta'"), {"id": conv_id})
        self.session.commit()

    def guardar_saliente(self, centro_id: int, telefono: str, cuerpo: str,
                         message_id: str | None = None, generado_por_ia: bool = False,
                         epoch: int | None = None, **media) -> None:
        conv_id = self._get_or_create_conversacion(centro_id, telefono)
        # Un saliente (humano o el propio Alex) cierra cualquier turno acumulado pendiente:
        # nunca deben llegar dos respuestas (una humana y otra de Alex) a la misma ráfaga.
        debouncer.cancelar(conv_id)
        if self._insertar_mensaje(conv_id, "saliente", cuerpo, message_id, estado="enviado",
                                  generado_por_ia=generado_por_ia, epoch=epoch, **media):
            bus.publish(centro_id, {"tipo": "mensaje", "convId": conv_id, "direccion": "saliente"})

    def _insertar_mensaje(self, conv_id: int, direccion: str, cuerpo: str,
                          message_id: str | None, *, estado: str,
                          incrementa_no_leidos: bool = False, generado_por_ia: bool = False,
                          media_url: str | None = None, media_tipo: str | None = None,
                          media_nombre: str | None = None, responde_a_id: str | None = None,
                          responde_a_texto: str | None = None, epoch: int | None = None) -> bool:
        """Inserta el mensaje. Devuelve True si insertó, False si era duplicado (dedup).
        `epoch` = hora real del mensaje (messageTimestamp); sin él, la hora de llegada. Evolution
        entrega mensajes atrasados al reconectar y antes TODOS quedaban con la hora de entrega."""
        # FIX B6: dedup previa si no hay message_id (fallback para duplicados sin mid)
        if not message_id:
            ahora = datetime.now(timezone.utc)
            ventana_seg = 5  # dentro de 5 seg
            existe = self.session.exec(select(Mensaje).where(
                Mensaje.conversacion_id == conv_id,
                Mensaje.direccion == direccion,
                Mensaje.cuerpo == cuerpo,
                Mensaje.enviado_at >= ahora - timedelta(seconds=ventana_seg)
            )).first()
            if existe:
                return False  # es duplicado

        # Dedup ATÓMICO: si el message_id ya existe, ON CONFLICT no hace nada.
        ins = text("""
            INSERT INTO mensajes (conversacion_id, direccion, cuerpo, message_id, estado,
                media_url, media_tipo, media_nombre, responde_a_id, responde_a_texto,
                generado_por_ia, aprobado, fijado, enviado_at, created_at, updated_at)
            VALUES (:conv, :dir, :cuerpo, :mid, :estado, :murl, :mtipo, :mnom, :rid, :rtxt,
                :ia, TRUE, FALSE, COALESCE(to_timestamp(:epoch), now()),
                COALESCE(to_timestamp(:epoch), now()), now())
            ON CONFLICT (message_id) WHERE message_id IS NOT NULL DO NOTHING
            RETURNING id
        """)
        res = self.session.execute(ins, {
            "conv": conv_id, "dir": direccion, "cuerpo": cuerpo, "mid": message_id,
            "estado": estado, "murl": media_url, "mtipo": media_tipo, "mnom": media_nombre,
            "rid": responde_a_id, "rtxt": responde_a_texto, "ia": generado_por_ia,
            "epoch": epoch,
        }).first()
        if res is None:   # era duplicado → no tocar el resumen de la conversación
            self.session.commit()
            return False
        resumen = ("→ " + cuerpo if direccion == "saliente" else cuerpo)[:200]
        self.session.execute(text("""
            UPDATE conversaciones SET ultimo_mensaje = :m,
                ultimo_mensaje_at = GREATEST(COALESCE(ultimo_mensaje_at, '-infinity'::timestamp),
                                             COALESCE(to_timestamp(:epoch)::timestamp, now()::timestamp)),
                no_leidos = no_leidos + :inc, archivada = FALSE, updated_at = now()
            WHERE id = :id
        """), {"m": resumen, "inc": 1 if incrementa_no_leidos else 0, "id": conv_id,
                                                  "epoch": epoch})
        self.session.commit()
        return True

    # ─────────────────────── IMPORTAR HISTORIAL (sync desde Evolution) ───────────────────────
    _HIST_MEDIA = {"imageMessage": ("image", "[imagen]"), "videoMessage": ("video", "[vídeo]"),
                   "audioMessage": ("audio", "[audio]"), "documentMessage": ("document", "[documento]"),
                   "stickerMessage": ("image", "[sticker]")}

    def _texto_historial(self, message: dict) -> tuple[str, str | None]:
        """Extrae texto + tipo de media de un mensaje del historial (sin descargar ficheros)."""
        txt = message.get("conversation") or (message.get("extendedTextMessage") or {}).get("text")
        if txt:
            return txt, None
        for clave, (tipo, etiqueta) in self._HIST_MEDIA.items():
            node = message.get(clave)
            if isinstance(node, dict):
                return (node.get("caption") or etiqueta), tipo
        return "[mensaje]", None

    def importar_historial(self, centro_id: int, limite_chats: int | None = None) -> dict:
        """Recupera los chats/mensajes YA existentes en el número conectado (vía Evolution
        findChats/findMessages) y los vuelca a la bandeja. Solo chats individuales
        (@s.whatsapp.net): se ignoran grupos (@g.us) y estados. Idempotente: el dedup por
        message_id evita duplicar al re-ejecutar. Cada mensaje conserva su fecha original."""
        cli = self._client(centro_id)
        chats = cli.find_chats()
        procesados = saltados = convs_tocadas = msgs = 0
        for ch in chats:
            jid = (ch.get("remoteJid") or "").strip()
            telefono = jid.split("@")[0] if jid else ""
            if not jid.endswith("@s.whatsapp.net") or not telefono.isdigit():
                saltados += 1
                continue
            try:
                records = cli.find_messages(jid)
            except EvolutionError:  # raiz: Evolution falló al leer los mensajes de ese chat; se salta ese chat y sigue con el resto
                saltados += 1
                continue
            if not records:
                continue
            records.sort(key=lambda m: (m.get("messageTimestamp") or 0))
            conv_id = self._get_or_create_conversacion(centro_id, telefono)
            n_ins = 0
            for m in records:
                key = m.get("key") or {}
                mid = key.get("id")
                from_me = bool(key.get("fromMe"))
                cuerpo, mtipo = self._texto_historial(m.get("message") or {})
                epoch = int(m.get("messageTimestamp") or 0) or None
                res = self.session.execute(text("""
                    INSERT INTO mensajes (conversacion_id, direccion, cuerpo, message_id, estado,
                        media_tipo, generado_por_ia, aprobado, fijado, enviado_at, created_at, updated_at)
                    VALUES (:conv, :dir, :cuerpo, :mid, :estado, :mtipo, FALSE, TRUE, FALSE,
                        COALESCE(to_timestamp(:epoch), now()), COALESCE(to_timestamp(:epoch), now()), now())
                    ON CONFLICT (message_id) WHERE message_id IS NOT NULL DO NOTHING
                    RETURNING id
                """), {"conv": conv_id, "dir": "saliente" if from_me else "entrante",
                       "cuerpo": cuerpo, "mid": mid, "estado": "enviado" if from_me else "leido",
                       "mtipo": mtipo, "epoch": epoch}).first()
                if res is not None:
                    n_ins += 1
            # Resumen/fecha/no_leídas SIEMPRE desde la tabla (fuente de verdad): el preview es el
            # último mensaje real y no_leidos = entrantes posteriores al último saliente
            # (último mensaje saliente → 0). Evita incoherencias preview↔contador.
            self._recalcular_resumen(conv_id)
            self.session.commit()
            msgs += n_ins
            procesados += 1
            if n_ins:
                convs_tocadas += 1
            if limite_chats and procesados >= limite_chats:
                break
        return {"chats_total": len(chats), "chats_procesados": procesados, "chats_saltados": saltados,
                "conversaciones": convs_tocadas, "mensajes_importados": msgs}

    def _recalcular_resumen(self, conv_id: int) -> None:
        """Recalcula ultimo_mensaje/ultimo_mensaje_at/no_leidos de UNA conversación desde la
        tabla de mensajes (autoritativo). no_leidos = entrantes posteriores al último saliente."""
        self.session.execute(text("""
            UPDATE conversaciones c SET
                ultimo_mensaje = lm.resumen, ultimo_mensaje_at = lm.t,
                ultima_direccion = lm.direccion,
                no_leidos = COALESCE(nl.cnt, 0), updated_at = now()
            FROM (
                SELECT direccion,
                       (CASE WHEN direccion = 'saliente' THEN '→ ' ELSE '' END || left(cuerpo, 200)) AS resumen,
                       enviado_at AS t
                FROM mensajes WHERE conversacion_id = :id AND direccion IN ('entrante', 'saliente')
                ORDER BY enviado_at DESC, id DESC LIMIT 1
            ) lm
            LEFT JOIN LATERAL (
                SELECT count(*) AS cnt FROM mensajes m
                WHERE m.conversacion_id = :id AND m.direccion = 'entrante'
                  AND m.enviado_at > COALESCE((SELECT max(s.enviado_at) FROM mensajes s
                      WHERE s.conversacion_id = :id AND s.direccion = 'saliente'), '-infinity'::timestamptz)
            ) nl ON TRUE
            WHERE c.id = :id
        """), {"id": conv_id})

    def listar_conversaciones(self, centro_id: int, archivadas: bool = False) -> list[dict]:
        convs = self.session.exec(
            select(Conversacion).where(
                Conversacion.centro_id == centro_id, Conversacion.archivada == archivadas)
            .order_by(Conversacion.fijada.desc(), Conversacion.urgente.desc(), Conversacion.ultimo_mensaje_at.desc())).all()  # type: ignore[union-attr]
        return [self._conv_dict(c) for c in convs]

    def _conv_dict(self, c: Conversacion) -> dict:
        nombre = None
        if c.paciente_id:
            pac = self.session.get(Paciente, c.paciente_id)
            if pac:
                nombre = f"{pac.nombre or ''} {pac.apellidos or ''}".strip()
        return {
            "id": c.id, "telefono": c.telefono, "nombre": nombre or c.telefono,
            "pacienteId": c.paciente_id, "estado": c.estado, "tags": c.tags,
            "noLeidos": c.no_leidos, "ultimoMensaje": c.ultimo_mensaje,
            "ultimoMensajeAt": _iso_utc(c.ultimo_mensaje_at),
            "ultimaDireccion": c.ultima_direccion, "fijada": c.fijada, "urgente": c.urgente,
            "iaPausada": bool(c.ia_pausada_hasta and c.ia_pausada_hasta > datetime.now()),
            "iaPausadaHasta": _iso_utc(c.ia_pausada_hasta),
        }

    # ─────────────────────── PAUSA DE IA POR CONVERSACIÓN ───────────────────────
    def _ia_pausada(self, centro_id: int, telefono: str) -> bool:
        """True si la IA está pausada (ia_pausada_hasta en el futuro) para esa conversación."""
        row = self.session.execute(text(
            "SELECT ia_pausada_hasta > now() FROM conversaciones WHERE centro_id=:c AND telefono=:t"
        ), {"c": centro_id, "t": tel.normalizar(telefono)}).first()
        return bool(row and row[0])

    def pausar_ia(self, conv_id: int, minutos: int = 60) -> None:
        self.session.execute(text(
            "UPDATE conversaciones SET ia_pausada_hasta = now() + make_interval(mins => :m), updated_at=now() WHERE id=:id"
        ), {"m": max(1, minutos), "id": conv_id})
        self.session.commit()

    def reanudar_ia(self, conv_id: int) -> None:
        self.session.execute(text(
            "UPDATE conversaciones SET ia_pausada_hasta = NULL, updated_at=now() WHERE id=:id"
        ), {"id": conv_id})
        self.session.commit()

    # ─── PAUSA GLOBAL Y TEMPORAL DE LA IA (a nivel de centro) ───
    # Distinta del on/off PERSISTENTE de Config › IA's (canal del agente Alex): esto es una
    # pausa rápida desde la barra de WhatsApp que caduca sola (por defecto 20 min). Se guarda
    # como timestamp ISO en `configuraciones` (sistema='ia', clave abajo) → CONFIG = verdad.
    _PAUSA_GLOBAL_KEY = "ia.pausa_global_hasta"

    def _config(self):
        from application.services.config_service import ConfigService
        return ConfigService(self.session)

    def _pausa_global_hasta(self, centro_id: int) -> datetime | None:
        raw = self._config().resolve(self._PAUSA_GLOBAL_KEY, centro_id=centro_id, sistema="ia", default=None)
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):  # raiz: ia.pausa_global_hasta no es un ISO válido en configuración; se trata como 'sin pausa'
            return None

    def _ia_pausada_global(self, centro_id: int) -> bool:
        hasta = self._pausa_global_hasta(centro_id)
        return bool(hasta and hasta > datetime.now(timezone.utc))

    def _paciente_sin_bots(self, centro_id: int, telefono: str) -> bool:
        """Pausa PERSISTENTE e INDIVIDUAL por paciente: True si el paciente (match por
        teléfono) tiene desactivados los asistentes en su ficha (Filiación › 'Asistentes /
        Bots' = `acepta_bots` False). Es un consentimiento, no caduca."""
        pac, _ = self.match_paciente(centro_id, telefono)
        return bool(pac and not pac.acepta_bots)

    def estado_ia_global(self, centro_id: int) -> dict:
        hasta = self._pausa_global_hasta(centro_id)
        pausada = bool(hasta and hasta > datetime.now(timezone.utc))
        # iaActiva = master de Config › IA's. Si está off, las pausas de WhatsApp no aplican (UI en gris).
        return {"pausada": pausada, "hasta": hasta.isoformat() if (pausada and hasta) else None,
                "iaActiva": self._modo_ia(centro_id) is not None}

    def set_paciente_bots(self, centro_id: int, telefono: str, acepta: bool) -> dict:
        """Marca desde WhatsApp si el paciente acepta IA/bots (= Filiación › 'Asistentes / Bots')."""
        pac, _ = self.match_paciente(centro_id, telefono)
        if not pac:
            return {"ok": False, "error": "sin ficha"}
        pac.acepta_bots = acepta
        self.session.add(pac)
        self.session.commit()
        return {"ok": True, "aceptaBots": acepta}

    def pausar_ia_global(self, centro_id: int, minutos: int = 20) -> dict:
        hasta = datetime.now(timezone.utc) + timedelta(minutes=max(1, minutos))
        self._config().set(self._PAUSA_GLOBAL_KEY, hasta.isoformat(), centro_id=centro_id, sistema="ia")
        return {"pausada": True, "hasta": hasta.isoformat()}

    def reanudar_ia_global(self, centro_id: int) -> dict:
        self._config().set(self._PAUSA_GLOBAL_KEY, None, centro_id=centro_id, sistema="ia")
        return {"pausada": False, "hasta": None}

    # ─────────────────────── FIJAR (PIN) MENSAJE ───────────────────────
    def fijar_mensaje(self, conv_id: int, msg_id: int) -> None:
        """Fija UN mensaje por conversación (desfija el anterior si lo hubiera)."""
        self.session.execute(text("UPDATE mensajes SET fijado=false WHERE conversacion_id=:c AND fijado=true"), {"c": conv_id})
        self.session.execute(text("UPDATE mensajes SET fijado=true WHERE id=:m AND conversacion_id=:c"), {"m": msg_id, "c": conv_id})
        self.session.execute(text("UPDATE conversaciones SET mensaje_fijado_id=:m, updated_at=now() WHERE id=:c"), {"m": msg_id, "c": conv_id})
        self.session.commit()

    def desfijar_mensaje(self, conv_id: int) -> None:
        self.session.execute(text("UPDATE mensajes SET fijado=false WHERE conversacion_id=:c AND fijado=true"), {"c": conv_id})
        self.session.execute(text("UPDATE conversaciones SET mensaje_fijado_id=NULL, updated_at=now() WHERE id=:c"), {"c": conv_id})
        self.session.commit()

    # ─── Gestión de la conversación desde la ficha (Inicio) ───
    def _conv_del_centro(self, centro_id: int, conv_id: int) -> Conversacion | None:
        conv = self.session.get(Conversacion, conv_id)
        return conv if conv is not None and conv.centro_id == centro_id else None

    def cortar_flujo(self, centro_id: int, conv_id: int) -> bool:
        """Saca la conversación del flujo en curso: el próximo mensaje empieza de cero."""
        conv = self._conv_del_centro(centro_id, conv_id)
        if conv is None:
            return False
        conv.estado_flujo = None
        self.session.add(conv)
        self.session.commit()
        return True

    def pausar_ia_conversacion(self, centro_id: int, conv_id: int, minutos: int) -> bool:
        """La IA no contesta en ESTA conversación durante `minutos` (la atiende una persona).
        Usa pausar_ia (now() de la BD), el mismo reloj con el que _ia_pausada la comprueba."""
        if self._conv_del_centro(centro_id, conv_id) is None:
            return False
        self.pausar_ia(conv_id, minutos)
        return True

    def reanudar_ia_conversacion(self, centro_id: int, conv_id: int) -> bool:
        if self._conv_del_centro(centro_id, conv_id) is None:
            return False
        self.reanudar_ia(conv_id)
        return True

    def _validar_acceso_conversacion(self, centro_id: int, conv_id: int) -> bool:
        """Valida que la conversación pertenece al centro. Retorna True si acceso válido."""
        conv = self.session.get(Conversacion, conv_id)
        return conv is not None and conv.centro_id == centro_id

    @staticmethod
    def _msg_dict(m: Mensaje) -> dict:
        return {
            "id": m.id, "direccion": m.direccion, "cuerpo": m.cuerpo, "estado": m.estado,
            "mediaUrl": m.media_url, "mediaTipo": m.media_tipo, "mediaNombre": m.media_nombre, "fijado": m.fijado,
            "generadoPorIa": m.generado_por_ia, "eliminado": m.eliminado, "editado": m.editado,
            "enviadoAt": _iso_utc(m.enviado_at),
        }

    def listar_mensajes(self, centro_id: int, conv_id: int) -> list[dict]:
        if not self._validar_acceso_conversacion(centro_id, conv_id):
            return []
        msgs = self.session.exec(
            select(Mensaje).where(Mensaje.conversacion_id == conv_id)
            .order_by(Mensaje.enviado_at.asc(), Mensaje.id.asc())).all()  # FIX B1: add id para orden determinista
        return [self._msg_dict(m) for m in msgs]

    def agregar_nota(self, centro_id: int, conv_id: int, texto: str) -> dict | None:
        """Nota interna del equipo dentro del hilo: NUNCA se envía por WhatsApp (no toca
        Evolution) y no cuenta como último mensaje/no-leído de la conversación (ver el
        filtro `direccion IN ('entrante','saliente')` de `_recalcular_resumen`)."""
        if not self._validar_acceso_conversacion(centro_id, conv_id):
            return None
        texto = (texto or "").strip()[:4000]
        if not texto:
            return None
        m = Mensaje(conversacion_id=conv_id, direccion="nota", cuerpo=texto, estado="nota")
        self.session.add(m)
        self.session.commit()
        self.session.refresh(m)
        bus.publish(centro_id, {"tipo": "mensaje", "convId": conv_id, "direccion": "nota"})
        return self._msg_dict(m)

    # ─────────────────────── ENVÍO ───────────────────────
    def enviar_texto(self, centro_id: int, telefono: str, texto: str,
                     generado_por_ia: bool = False) -> dict:
        cli = self._client(centro_id)
        # `delay` es el "simulando que escribe" de Evolution: la petición NO vuelve hasta
        # que pasa. Tiene sentido cuando escribe el BOT a un paciente (llegar instantáneo
        # delata a la máquina), pero cuando una persona del equipo pulsa enviar solo añade
        # 1,2 s de espera mirando la pantalla sin que aparezca nada. Medido el 24-jul-2026:
        # Evolution responde en ~20 ms, así que ese retardo era casi todo el tiempo de espera.
        retardo = 1200 if generado_por_ia else 0
        try:
            resp = cli.send_text(tel.normalizar(telefono), texto, delay=retardo)
        except EvolutionError as e:  # raiz: Evolution no disponible al enviar el texto; se registra el fallo en whatsapp_monitor y se propaga
            from infrastructure import whatsapp_monitor
            whatsapp_monitor.registrar_fallo(self.session, centro_id, "sendText", str(e))
            raise
        mid = (resp.get("key") or {}).get("id") if isinstance(resp, dict) else None
        self.guardar_saliente(centro_id, telefono, texto, message_id=mid,
                              generado_por_ia=generado_por_ia)
        return {"enviado": True, "messageId": mid}

    def responder_conversacion(self, centro_id: int, conv_id: int, texto: str) -> dict:
        conv = self.session.get(Conversacion, conv_id)
        if not conv or conv.centro_id != centro_id or not conv.telefono:
            return {"enviado": False, "error": "conversación no encontrada"}
        return self.enviar_texto(centro_id, conv.telefono, texto)

    def enviar_documento(self, centro_id: int, telefono: str, base64_doc: str, filename: str,
                         caption: str | None = None, mimetype: str = "application/pdf") -> dict:
        """Envía un documento (PDF) por WhatsApp vía Evolution y lo registra en el hilo."""
        cli = self._client(centro_id)
        try:
            resp = cli.send_media(tel.normalizar(telefono), media=base64_doc, media_type="document",
                                  mimetype=mimetype, filename=filename, caption=caption)
        except EvolutionError as e:  # raiz: Evolution no disponible al enviar el documento; se registra el fallo en whatsapp_monitor y se propaga
            from infrastructure import whatsapp_monitor
            whatsapp_monitor.registrar_fallo(self.session, centro_id, "sendMedia", str(e))
            raise
        mid = (resp.get("key") or {}).get("id") if isinstance(resp, dict) else None
        self.guardar_saliente(centro_id, telefono, caption or f"📄 {filename}", message_id=mid,
                              media_tipo="document", media_nombre=filename)
        return {"enviado": True, "messageId": mid}

    # ─────────────────────── ENVÍO DE MEDIA (adjuntar) ───────────────────────
    _MEDIA_DESC = {"image": "[imagen]", "video": "[vídeo]", "audio": "[audio]", "document": "[documento]"}

    @staticmethod
    def _tipo_media(mimetype: str | None, filename: str | None) -> str:
        """image | video | audio | document a partir del MIME (fallback document)."""
        m = (mimetype or "").lower()
        if m.startswith("image/"):
            return "image"
        if m.startswith("video/"):
            return "video"
        if m.startswith("audio/"):
            return "audio"
        return "document"

    def _guardar_media_local(self, contenido: bytes, filename: str | None, mid: str | None) -> str | None:
        """Guarda el adjunto saliente en disco para poder renderizarlo en el hilo (igual que el entrante)."""
        logger = logging.getLogger("comunicacion.media")

        try:
            self._MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # raiz: no se pudo crear media/whatsapp al guardar el saliente (permisos o disco); se descarta la copia local
            logger.error(f"No se pudo crear directorio {self._MEDIA_DIR}: {e}", exc_info=True)
            return None

        try:
            ext = ""
            if filename and "." in filename:
                ext = "." + filename.rsplit(".", 1)[1].lower()[:8]
            base = (mid or hashlib.sha256(contenido).hexdigest()[:24])
            nombre = f"out-{base}{ext}".replace("/", "_").replace("\\", "_")
            (self._MEDIA_DIR / nombre).write_bytes(contenido)
            logger.debug(f"Media saliente guardada: {nombre} ({len(contenido)} bytes)")
            return f"/media/whatsapp/{nombre}"
        except Exception as e:  # raiz: fallo escribiendo el adjunto saliente en media/whatsapp (disco, permisos o nombre); se descarta la copia local
            logger.error(f"Fallo guardar media {filename or 'sin-nombre'}: {e}", exc_info=True)
            return None

    def enviar_media(self, centro_id: int, telefono: str, contenido: bytes, filename: str | None,
                     mimetype: str | None = None, caption: str | None = None) -> dict:
        """Envía un adjunto (imagen/vídeo/audio/documento) por WhatsApp y lo registra en el hilo."""
        import logging
        logger = logging.getLogger("comunicacion.media")

        tipo = self._tipo_media(mimetype, filename)
        b64 = base64.b64encode(contenido).decode()

        # Validar tamaño antes de enviar
        if len(b64) > 50_000_000:  # 50MB en base64 ≈ 37MB binario
            return {"enviado": False, "error": "archivo muy grande (máximo 20MB)", "mediaUrl": None}

        try:
            cli = self._client(centro_id)
            resp = cli.send_media(tel.normalizar(telefono), media=b64, media_type=tipo,
                                  mimetype=mimetype, filename=filename, caption=caption)
            mid = (resp.get("key") or {}).get("id") if isinstance(resp, dict) else None

            # Guardar copia local con error explícito (el envío ya salió; si esto falla solo avisa).
            url = None
            try:
                url = self._guardar_media_local(contenido, filename, mid)
                if not url:
                    logger.warning(f"_guardar_media_local devolvió None para {filename}")
            except Exception as e:  # raiz: fallo guardando la copia local del media ya enviado (solo afecta al preview); se registra y se sigue
                logger.error(f"Fallo guardar media local {filename}: {e}", exc_info=True)

            cuerpo = caption or self._MEDIA_DESC.get(tipo, "[archivo]")
            self.guardar_saliente(centro_id, telefono, cuerpo, message_id=mid,
                                  media_url=url, media_tipo=tipo, media_nombre=filename)
            return {"enviado": True, "messageId": mid, "mediaUrl": url, "almacenado_localmente": url is not None}

        except EvolutionError as e:  # raiz: Evolution caído al enviar el adjunto; se devuelve enviado=False con el motivo
            logger.error(f"Evolution no disponible para enviar media: {e}")
            return {"enviado": False, "error": f"Evolution caído: {e!s}", "mediaUrl": None}
        except Exception as e:  # raiz: fallo inesperado en el envío del adjunto (no es EvolutionError); se registra y se propaga
            logger.error(f"Error inesperado en enviar_media: {e}", exc_info=True)
            raise

    def enviar_media_conv(self, centro_id: int, conv_id: int, contenido: bytes, filename: str | None,
                          mimetype: str | None = None, caption: str | None = None) -> dict:
        conv = self.session.get(Conversacion, conv_id)
        if not conv or conv.centro_id != centro_id or not conv.telefono:
            return {"enviado": False, "error": "conversación no encontrada"}
        return self.enviar_media(centro_id, conv.telefono, contenido, filename, mimetype, caption)

    # ─────────────────────── PLANTILLAS (tabla plantillas_mensaje) ───────────────────────
    def listar_plantillas(self, centro_id: int) -> list[dict]:
        rows = self.session.exec(select(PlantillaMensaje).where(
            PlantillaMensaje.centro_id == centro_id).order_by(PlantillaMensaje.nombre)).all()  # type: ignore[union-attr]
        return [{"id": p.id, "nombre": p.nombre, "cuerpo": p.cuerpo, "disparador": p.disparador,
                 "tipo": p.tipo, "activo": p.activo} for p in rows]

    def guardar_plantilla(self, centro_id: int, data: dict, usuario_id: int | None = None) -> dict:
        pid = data.get("id")
        p = self.session.get(PlantillaMensaje, pid) if pid else None
        if not p or p.centro_id != centro_id:
            p = PlantillaMensaje(centro_id=centro_id, nombre="", cuerpo="")
        p.nombre = data.get("nombre") or p.nombre
        p.cuerpo = data.get("cuerpo") or p.cuerpo
        p.disparador = data.get("disparador") or None
        p.tipo = data.get("tipo") or "texto"
        if "activo" in data:
            p.activo = bool(data["activo"])
        p.updated_by = usuario_id
        self.session.add(p); self.session.commit(); self.session.refresh(p)
        return {"id": p.id}

    def borrar_plantilla(self, centro_id: int, pid: int) -> None:
        p = self.session.get(PlantillaMensaje, pid)
        if p and p.centro_id == centro_id:
            self.session.delete(p); self.session.commit()

    def marcar_leida(self, centro_id: int, conv_id: int) -> bool:
        if not self._validar_acceso_conversacion(centro_id, conv_id):
            return False
        self.session.execute(text(
            "UPDATE conversaciones SET no_leidos = 0, updated_at = now() WHERE id = :id"),
            {"id": conv_id})
        self.session.commit()
        # Sin esto, el badge de no-leídas (lista de conversaciones + icono del rail) no se
        # entera de que se marcó como leída hasta el sondeo de respaldo (30s) — la sensación
        # de "sigue apareciendo como no leída" tras leer y contestar era justo ese hueco.
        bus.publish(centro_id, {"tipo": "leida", "convId": conv_id})
        return True

    def marcar_no_leida(self, centro_id: int, conv_id: int) -> bool:
        """Fuerza la conversación a no-leída (como Gmail/WhatsApp), aunque no_leidos ya fuera 0."""
        if not self._validar_acceso_conversacion(centro_id, conv_id):
            return False
        self.session.execute(text(
            "UPDATE conversaciones SET no_leidos = GREATEST(no_leidos, 1), updated_at = now() WHERE id = :id"),
            {"id": conv_id})
        self.session.commit()
        bus.publish(centro_id, {"tipo": "no_leida", "convId": conv_id})
        return True

    def fijar_conversacion(self, centro_id: int, conv_id: int, fijada: bool) -> bool:
        if not self._validar_acceso_conversacion(centro_id, conv_id):
            return False
        self.session.execute(text(
            "UPDATE conversaciones SET fijada = :f, updated_at = now() WHERE id = :id"),
            {"f": fijada, "id": conv_id})
        self.session.commit()
        bus.publish(centro_id, {"tipo": "fijada", "convId": conv_id})
        return True

    def marcar_urgente(self, centro_id: int, conv_id: int, urgente: bool) -> bool:
        """Urgencia SIEMPRE manual (marcada por el equipo desde el menú de la conversación) —
        la detección automática por texto se retiró por falsos positivos con palabras comunes."""
        if not self._validar_acceso_conversacion(centro_id, conv_id):
            return False
        self.session.execute(text(
            "UPDATE conversaciones SET urgente = :u, updated_at = now() WHERE id = :id"),
            {"u": urgente, "id": conv_id})
        self.session.commit()
        bus.publish(centro_id, {"tipo": "urgente", "convId": conv_id})
        return True

    def _mensaje_editable(self, centro_id: int, conv_id: int, msg_id: int) -> tuple[Mensaje | None, Conversacion | None]:
        """Mensaje propio, de esa conversación de ese centro, aún sin leer y sin borrar ya —
        la única ventana en la que Evolution deja borrar/editar de verdad para ambos."""
        conv = self.session.get(Conversacion, conv_id)
        if not conv or conv.centro_id != centro_id:
            return None, None
        m = self.session.get(Mensaje, msg_id)
        if not m or m.conversacion_id != conv_id or m.direccion != "saliente" or m.eliminado:
            return None, None
        if m.estado == "leido":
            return None, None
        return m, conv

    def _refrescar_preview_si_es_el_ultimo(self, conv_id: int, msg_id: int) -> None:
        """Tras editar/borrar, si el mensaje tocado ERA el último de la conversación, refresca
        el preview de la lista (si no, el listado quedaría mostrando un texto ya obsoleto)."""
        ultimo = self.session.exec(
            select(Mensaje.id, Mensaje.cuerpo, Mensaje.eliminado, Mensaje.direccion)
            .where(Mensaje.conversacion_id == conv_id)
            .order_by(Mensaje.enviado_at.desc(), Mensaje.id.desc())).first()
        if not ultimo or ultimo[0] != msg_id:
            return
        cuerpo = "Mensaje eliminado" if ultimo[2] else ultimo[1]
        resumen = ("→ " + cuerpo if ultimo[3] == "saliente" else cuerpo)[:200]
        self.session.execute(text(
            "UPDATE conversaciones SET ultimo_mensaje = :m, updated_at = now() WHERE id = :id"),
            {"m": resumen, "id": conv_id})

    def borrar_mensaje(self, centro_id: int, conv_id: int, msg_id: int) -> None:
        """Borra un saliente para AMBOS (Evolution) — solo si el paciente aún no lo ha leído.
        Deja subir PermissionError (gate) / EvolutionError (falló Evolution) al router."""
        m, conv = self._mensaje_editable(centro_id, conv_id, msg_id)
        if not m:
            raise PermissionError("El mensaje no se puede borrar (ya leído, ya borrado o no es tuyo).")
        if m.message_id:
            cli = self._client(centro_id)
            remote_jid = f"{tel.normalizar(conv.telefono)}@s.whatsapp.net"
            cli.delete_message_for_everyone(remote_jid, m.message_id)
        m.eliminado = True
        self.session.add(m)
        self._refrescar_preview_si_es_el_ultimo(conv_id, msg_id)
        self.session.commit()
        bus.publish(centro_id, {"tipo": "mensaje_borrado", "convId": conv_id})

    def editar_mensaje(self, centro_id: int, conv_id: int, msg_id: int, texto: str) -> None:
        texto = (texto or "").strip()
        if not texto:
            raise PermissionError("El texto no puede quedar vacío.")
        m, conv = self._mensaje_editable(centro_id, conv_id, msg_id)
        if not m:
            raise PermissionError("El mensaje no se puede editar (ya leído, borrado o no es tuyo).")
        if m.message_id:
            cli = self._client(centro_id)
            remote_jid = f"{tel.normalizar(conv.telefono)}@s.whatsapp.net"
            cli.update_message(tel.normalizar(conv.telefono), remote_jid, m.message_id, texto)
        m.cuerpo = texto
        m.editado = True
        self.session.add(m)
        self._refrescar_preview_si_es_el_ultimo(conv_id, msg_id)
        self.session.commit()
        bus.publish(centro_id, {"tipo": "mensaje_editado", "convId": conv_id})

    def set_estado(self, centro_id: int, conv_id: int, estado: str) -> bool:
        if not self._validar_acceso_conversacion(centro_id, conv_id):
            return False
        self.session.execute(text(
            "UPDATE conversaciones SET estado = :e, updated_at = now() WHERE id = :id"),
            {"e": estado, "id": conv_id})
        self.session.commit()
        return True

    def archivar(self, centro_id: int, conv_id: int) -> bool:
        if not self._validar_acceso_conversacion(centro_id, conv_id):
            return False
        self.session.execute(text(
            "UPDATE conversaciones SET archivada = TRUE, updated_at = now() WHERE id = :id"),
            {"id": conv_id})
        self.session.commit()
        return True

    def desarchivar(self, centro_id: int, conv_id: int) -> bool:
        if not self._validar_acceso_conversacion(centro_id, conv_id):
            return False
        self.session.execute(text(
            "UPDATE conversaciones SET archivada = FALSE, updated_at = now() WHERE id = :id"),
            {"id": conv_id})
        self.session.commit()
        return True

    # ─────────────────────── WEBHOOK ENTRANTE ───────────────────────
    def procesar_webhook(self, centro_id: int, payload: dict) -> dict:
        """Procesa un evento de Evolution. Devuelve un resumen de lo actuado."""
        event = (payload.get("event") or "").lower()  # FIX B3: normalizar a lowercase
        data = payload.get("data") or {}

        if event == "messages.update":
            # BUG REAL encontrado verificando el payload real de Evolution v2: aquí NO viene
            # anidado como en messages.upsert (data.key.id) — viene plano en data.keyId. Con
            # (data.get("key") or {}).get("id") esto SIEMPRE daba None → el doble check nunca
            # se actualizó ni un solo mensaje desde que existe la función (301/301 en "enviado").
            mid = data.get("keyId") or (data.get("key") or {}).get("id")
            estado = self._map_estado(data.get("status"))
            if mid and estado:
                row = self.session.execute(text(
                    "UPDATE mensajes SET estado = :e WHERE message_id = :m RETURNING conversacion_id"),
                    {"e": estado, "m": mid}).first()
                self.session.commit()
                # Sin esto el doble check (✓/✓✓ azul) no se actualiza en pantalla hasta el
                # sondeo de 30s — mismo hueco que tenía marcar_leida, misma solución.
                if row:
                    bus.publish(centro_id, {"tipo": "estado_mensaje", "convId": row[0]})
            return {"actuado": "estado_actualizado"}

        if event not in ("messages.upsert", "send.message"):
            return {"actuado": "ignorado", "event": event}

        key = data.get("key") or {}
        from_me = bool(key.get("fromMe"))
        telefono = (key.get("remoteJid") or "").split("@")[0]
        mid = key.get("id")
        msg = data.get("message") or {}
        epoch = self._epoch_valido(data.get("messageTimestamp"))
        if not telefono:
            return {"actuado": "sin_telefono"}

        # Voto de encuesta entrante → resolver acción
        poll = msg.get("pollUpdateMessage")
        if poll and not from_me:
            return {"actuado": "poll", **self._resolver_poll(centro_id, telefono, poll)}

        # Texto o media
        media = self._extraer_media(centro_id, msg, data)
        texto = (msg.get("conversation")
                 or (msg.get("extendedTextMessage") or {}).get("text")
                 or media.get("descripcion") or "")

        if from_me:
            self.guardar_saliente(centro_id, telefono, texto or "[media]", message_id=mid,
                                  epoch=epoch, **media["campos"])
            return {"actuado": "saliente_guardado"}

        conv_id = self.guardar_entrante(centro_id, telefono, texto or "[media]", message_id=mid,
                                        epoch=epoch, **media["campos"])
        # Si un humano pausó la IA para esta conversación → no autorrespondemos (solo guardamos).
        if self._ia_pausada(centro_id, telefono):
            return {"actuado": "entrante", "ia": "pausada"}
        # Pausa global temporal (barra de WhatsApp): suprime la IA en todo el centro hasta que caduque.
        if self._ia_pausada_global(centro_id):
            return {"actuado": "entrante", "ia": "pausada_global"}
        # Pausa PERSISTENTE por paciente (Filiación › 'Asistentes / Bots'): si no acepta bots, la IA no le responde.
        if self._paciente_sin_bots(centro_id, telefono):
            return {"actuado": "entrante", "ia": "paciente_sin_bots"}
        # MODO PRUEBA (motion.numeros_prueba): si hay lista blanca, la IA SOLO responde a esos
        # números. Es la misma barrera que la automatización saliente, ahora también en el
        # entrante: encender el canal de Alex sin esto lo soltaría a responder a pacientes
        # REALES. Lista vacía = sin restricción (comportamiento de producción normal).
        if not self._telefono_en_modo_prueba(centro_id, telefono):
            return {"actuado": "entrante", "ia": "fuera_de_modo_prueba"}
        # Esperar a que el paciente termine de escribir (varios mensajes seguidos = 1 turno).
        # espera<=0 → responder al instante, igual que antes de este cambio.
        espera = self._espera_respuesta_seg(centro_id)
        if espera <= 0:
            return self._decidir_respuesta(centro_id, telefono, texto)
        debouncer.programar(conv_id, espera,
                            lambda: self._turno_acumulado(centro_id, telefono, conv_id))
        return {"actuado": "entrante", "debounced": True, "esperaSeg": espera}

    def _telefono_en_modo_prueba(self, centro_id: int, telefono: str) -> bool:
        """¿Puede la IA responder a este número?

        Reutiliza `motion.numeros_prueba` (la misma lista blanca del modo prueba saliente):
          · lista con números  → SOLO esos reciben respuesta de la IA (blindaje de pruebas);
          · lista vacía        → sin restricción (producción).
        Compara por los últimos 9 dígitos, como el resto del sistema (ignora prefijos)."""
        from application.services.automatizacion_service import AutomatizacionService
        allow = AutomatizacionService(self.session).numeros_prueba(centro_id)
        if not allow:
            return True
        n9 = "".join(c for c in (telefono or "") if c.isdigit())[-9:]
        return any("".join(c for c in a if c.isdigit())[-9:] == n9 for a in allow)

    def _decidir_respuesta(self, centro_id: int, telefono: str, texto: str) -> dict:
        """Decide y ejecuta la respuesta automática (o no) a un texto ya recibido —
        el mismo cuerpo de siempre, ahora invocado directamente (espera=0) o desde
        `_turno_acumulado` tras la espera configurada."""
        modo = self._modo_ia(centro_id)
        if modo == "agente":
            from application.services.agente_service import AgenteService
            from infrastructure.external_apis.llm_client import LLMError
            try:
                return {"actuado": "entrante",
                        **AgenteService(self.session).responder(centro_id, telefono, texto)}
            except LLMError:  # raiz: LLM no configurado o caído al responder como agente; se cae a la máquina de estados
                pass   # sin LLM operativo → cae a la máquina de estados
        if modo in ("agente", "flujos"):
            return {"actuado": "entrante", **self.procesar_conversacion(centro_id, telefono, texto)}
        return {"actuado": "entrante", **self._detectar_intents(centro_id, telefono, texto)}

    # ─────────────────────── ESPERA ANTES DE RESPONDER (debounce) ───────────────────────
    def _config_respuesta(self, centro_id: int) -> dict:
        from application.services.config_service import ConfigService
        alex = ConfigService(self.session).resolve(
            "agente.alex", centro_id=centro_id, sistema="ia", default=None) or {}
        return alex.get("respuesta") or {}

    def _espera_respuesta_seg(self, centro_id: int) -> float:
        try:
            return float(self._config_respuesta(centro_id).get("esperaSeg", 8))
        except (TypeError, ValueError):  # raiz: esperaSeg de configuración no numérica; se usa el valor por defecto de 8 s
            return 8.0

    def _mostrar_escribiendo(self, centro_id: int) -> bool:
        return bool(self._config_respuesta(centro_id).get("escribiendo", True))

    def _turno_acumulado(self, centro_id: int, telefono: str, conv_id: int) -> None:
        """Dispara el debounce (corre en el threadpool, fuera del event loop): la sesión
        del request original ya se cerró, así que abre una propia — mismo patrón que los
        jobs de `infrastructure/scheduler.py`."""
        from infrastructure.config.db import engine
        with Session(engine) as session:
            ComunicacionService(session)._ejecutar_turno_acumulado(centro_id, telefono, conv_id)

    def _ejecutar_turno_acumulado(self, centro_id: int, telefono: str, conv_id: int) -> dict:
        conv = self.session.get(Conversacion, conv_id)
        if not conv or conv.centro_id != centro_id:
            return {"actuado": "abortado", "motivo": "conversacion_invalida"}

        ultimo_saliente = self.session.execute(text(
            "SELECT max(enviado_at) FROM mensajes WHERE conversacion_id=:id AND direccion='saliente'"
        ), {"id": conv_id}).scalar()
        params: dict = {"id": conv_id}
        filtro = ""
        if ultimo_saliente:
            filtro = "AND enviado_at > :ult"
            params["ult"] = ultimo_saliente
        filas = self.session.execute(text(
            f"SELECT cuerpo FROM mensajes WHERE conversacion_id=:id AND direccion='entrante' "
            f"{filtro} ORDER BY enviado_at ASC, id ASC"), params).all()
        if not filas:
            # Ya no hay nada que contestar: un humano ya respondió mientras esperábamos
            # (protección extra; `guardar_saliente` ya cancela el timer, esto cubre la
            # carrera si el callback ya se había disparado al threadpool).
            return {"actuado": "abortado", "motivo": "ya_respondido"}
        texto = "\n".join(r[0] for r in filas if r[0])

        # Re-comprobar los gates EN CALIENTE: el estado pudo cambiar durante la espera.
        if self._ia_pausada(centro_id, telefono):
            return {"actuado": "entrante", "ia": "pausada"}
        if self._ia_pausada_global(centro_id):
            return {"actuado": "entrante", "ia": "pausada_global"}
        if self._paciente_sin_bots(centro_id, telefono):
            return {"actuado": "entrante", "ia": "paciente_sin_bots"}
        return self._decidir_respuesta(centro_id, telefono, texto)

    def _modo_ia(self, centro_id: int) -> str | None:
        """Modo de respuesta automática del centro (off por defecto). La controla el
        toggle del canal WhatsApp del agente Alex (Config › IA's › Alex), en
        `configuraciones` clave `agente.alex`. Con canal activo se intenta el agente
        LLM; si no hay LLM configurado, el webhook cae a la máquina de estados."""
        from application.services.config_service import ConfigService
        alex = ConfigService(self.session).for_scope(centro_id=centro_id, sistema="ia").get("agente.alex") or {}
        # Alex desactivado (interruptor de su ficha en Config › Agentes IA) no contesta,
        # aunque el canal WhatsApp esté encendido: los dos tienen que estar en verde.
        if alex.get("activa") is False:
            return None
        if (alex.get("canales") or {}).get("whatsapp"):
            return "agente"
        return None

    # ─────────────────────── MEDIA ENTRANTE ───────────────────────
    # _MEDIA_DIR inicializado en __init__ (FIX B5)
    _MEDIA_TIPOS = {"imageMessage": ("image", "[imagen]", "jpg"),
                    "videoMessage": ("video", "[vídeo]", "mp4"),
                    "audioMessage": ("audio", "[audio]", "ogg"),
                    "documentMessage": ("document", "[documento]", "bin")}

    def _extraer_media(self, centro_id: int, msg: dict, data: dict) -> dict:
        """Detecta media en el mensaje; descarga el fichero si se puede."""
        for clave, (tipo, desc, ext) in self._MEDIA_TIPOS.items():
            node = msg.get(clave)
            if not node:
                continue
            url = self._descargar_media(centro_id, data, msg, ext)
            return {"descripcion": node.get("caption") or desc,
                    "campos": {"media_tipo": tipo, "media_url": url,
                               "media_nombre": node.get("fileName")}}
        return {"descripcion": None, "campos": {}}

    def _descargar_media(self, centro_id: int, data: dict, msg: dict, ext: str) -> str | None:
        import logging
        logger = logging.getLogger("comunicacion.media")

        mid = (data.get("key") or {}).get("id") or "media"

        # FIX B4: crear directorio con manejo de error
        try:
            self._MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # raiz: no se pudo crear media/whatsapp al descargar el entrante (permisos o disco); el mensaje queda sin adjunto local
            logger.error(f"No se pudo crear directorio de media: {e}", exc_info=True)
            return None

        try:
            cli = self._client(centro_id)
            res = cli.get_base64_from_media({"key": data.get("key"), "message": msg})
            b64 = res.get("base64") or res.get("media")
            if not b64:
                logger.warning(f"get_base64_from_media devolvió vacío para {mid}")
                return None

            # FIX B4: decodificar con manejo de error
            try:
                contenido = base64.b64decode(b64)
            except Exception as e:  # raiz: base64 del adjunto entrante corrupto o truncado; el mensaje queda sin adjunto local
                logger.error(f"Base64 corrupto para {mid}: {e}")
                return None

            nombre = f"{mid}.{ext}"
            try:
                (self._MEDIA_DIR / nombre).write_bytes(contenido)
                url = f"/media/whatsapp/{nombre}"
                logger.debug(f"Media descargada: {nombre}")
                return url
            except Exception as e:  # raiz: fallo escribiendo el adjunto entrante en media/whatsapp (disco, permisos o nombre); queda sin copia local
                logger.error(f"No se pudo escribir {nombre}: {e}", exc_info=True)
                return None

        except EvolutionError as e:  # raiz: Evolution no disponible o sin acceso al media entrante; queda sin adjunto local
            logger.warning(f"Evolution no disponible para descargar media {mid}: {e}")
            return None
        except Exception as e:  # raiz: fallo inesperado descargando el media entrante (respuesta no esperada de Evolution); queda sin adjunto local
            logger.error(f"Error inesperado en _descargar_media: {e}", exc_info=True)
            return None

    # ─────────────────────── ENCUESTAS (POLLS) ───────────────────────
    @staticmethod
    def _hash_opcion(etiqueta: str) -> str:
        return hashlib.sha256(etiqueta.encode("utf-8")).hexdigest()

    def enviar_encuesta(self, centro_id: int, telefono: str, nombre: str,
                        opciones: list[dict]) -> dict:
        """Envía una encuesta WhatsApp. opciones = [{etiqueta, accion}]. Guarda el
        contexto (hashes de cada opción → acción) para resolver el voto entrante."""
        etiquetas = [o["etiqueta"] for o in opciones]
        cli = self._client(centro_id)
        resp = cli.send_poll(tel.normalizar(telefono), nombre, etiquetas)
        mid = (resp.get("key") or {}).get("id") if isinstance(resp, dict) else None
        if mid:
            self.session.add(PollContexto(
                centro_id=centro_id, message_id=mid, telefono=tel.normalizar(telefono),
                opciones=opciones,
                opcion_hashes={self._hash_opcion(o["etiqueta"]): i for i, o in enumerate(opciones)}))
            self.session.commit()
        return {"enviado": True, "messageId": mid}

    def _resolver_poll(self, centro_id: int, telefono: str, poll: dict) -> dict:
        ref = (poll.get("pollCreationMessageKey") or {}).get("id")
        if not ref:
            return {"resuelto": False, "motivo": "sin_referencia"}
        ctx = self.session.exec(select(PollContexto).where(
            PollContexto.message_id == ref)).first()
        if not ctx:
            return {"resuelto": False, "motivo": "sin_contexto"}
        # Claim atómico: solo el primer voto resuelve.
        claimed = self.session.execute(text(
            "UPDATE poll_contexto SET resuelto_at = now() WHERE id = :id AND resuelto_at IS NULL "
            "RETURNING id"), {"id": ctx.id}).first()
        if not claimed:
            return {"resuelto": False, "motivo": "ya_resuelto"}

        idx = self._opcion_votada(ctx, poll)
        opciones = ctx.opciones or []
        if idx is None or idx >= len(opciones):
            self.session.commit()
            return {"resuelto": False, "motivo": "voto_no_identificado"}
        accion = (opciones[idx] or {}).get("accion")
        self.session.execute(text(
            "UPDATE poll_contexto SET opcion_resuelta = :o WHERE id = :id"),
            {"o": opciones[idx].get("etiqueta"), "id": ctx.id})
        self.session.commit()
        return {"resuelto": True, "accion": accion,
                **self._ejecutar_accion_poll(centro_id, telefono, accion)}

    def _opcion_votada(self, ctx: PollContexto, poll: dict) -> int | None:
        vote = poll.get("vote") or {}
        seleccionados = vote.get("selectedOptions") or poll.get("selectedOptions") or []
        hashes = ctx.opcion_hashes or {}
        for sel in seleccionados:
            h = sel if isinstance(sel, str) else (sel.get("hash") or sel.get("name") or "")
            if h in hashes:
                return hashes[h]
        # fallback: por etiqueta literal
        for i, o in enumerate(ctx.opciones or []):
            if o.get("etiqueta") in seleccionados:
                return i
        return None

    def _ejecutar_accion_poll(self, centro_id: int, telefono: str, accion: str | None) -> dict:
        if accion in ("confirmar_cita", "cancelar_cita"):
            pac, n = self.match_paciente(centro_id, telefono)
            if n != 1 or not pac:
                return {"cita": f"omitida ({n} pacientes)"}
            r = (self.confirmar_cita if accion == "confirmar_cita" else self.cancelar_cita)(centro_id, pac.id)
            cc = getattr(self, "_consent_cita", None)   # en poll no hay acuse de texto: enviar ya
            if cc:
                self._consent_cita = None
                self._enviar_consentimiento_cita(centro_id, cc)
            return {"cita": r.get("accion")}
        if accion == "escalar_humano":
            self._escalar(centro_id, telefono, "encuesta")
            return {"escalado": True}
        return {}

    # ─────────────────────── CAPA A: MÁQUINA DE ESTADOS ───────────────────────
    def procesar_conversacion(self, centro_id: int, telefono: str, texto: str) -> dict:
        """Corre la máquina de estados sobre un mensaje entrante: decide respuesta,
        aplica la acción (con guards) y, si procede, envía la respuesta al paciente."""
        conv = self.session.exec(select(Conversacion).where(
            Conversacion.centro_id == centro_id, Conversacion.canal == "whatsapp",
            Conversacion.telefono == tel.normalizar(telefono))).first()
        pac, n = self.match_paciente(centro_id, telefono)
        ctx = {"tiene_paciente": pac is not None, "n_pacientes": n,
               "nombres": self._nombres_por_telefono(centro_id, telefono)}
        estado = conv.estado_flujo if conv else None

        res = wf.manejar(estado, texto, ctx)
        respuesta = res.get("respuesta") or ""
        accion = res.get("accion")

        # Aplicar acción (los guards viven aquí, no en el flujo puro)
        if accion:
            respuesta = self._aplicar_accion(centro_id, telefono, pac, n, accion, respuesta)

        # Persistir el nuevo estado del flujo
        if conv:
            conv.estado_flujo = res.get("nuevo_estado")
            self.session.add(conv); self.session.commit()

        # Enviar la respuesta (si hay y la instancia está operativa)
        enviado = False
        if respuesta:
            try:
                self.enviar_texto(centro_id, telefono, respuesta, generado_por_ia=True)
                enviado = True
            except EvolutionError:  # raiz: Evolution no operativa al enviar la respuesta del flujo; la respuesta queda calculada pero no enviada
                pass   # no operativa: la respuesta queda calculada pero no se envía
        # Tras el acuse de confirmación: enviar el consentimiento (enlace de firma) si quedó pendiente.
        cc = getattr(self, "_consent_cita", None)
        if cc:
            self._consent_cita = None
            self._enviar_consentimiento_cita(centro_id, cc)
        return {"flujo": accion.get("tipo") if accion else "conversacion",
                "respondido": enviado}

    def _aplicar_accion(self, centro_id: int, telefono: str, pac, n: int,
                        accion: dict, respuesta: str) -> str:
        tipo = accion.get("tipo")
        if tipo in ("confirmar", "cancelar"):
            if n != 1 or not pac:
                return ("Tengo varias fichas con este número; te paso con el equipo para "
                        "gestionar tu cita.")
            r = (self.confirmar_cita if tipo == "confirmar" else self.cancelar_cita)(centro_id, pac.id)
            if r.get("accion") == "sin_cita":
                return "No encuentro una cita próxima a tu nombre. ¿Quieres pedir una?"
            return respuesta
        if tipo == "citas" and pac:
            citas = self._proximas_citas(centro_id, pac.id, limit=3)
            if not citas:
                return "No tienes citas próximas registradas. ¿Quieres pedir una?"
            lineas = "\n".join(f"• {c.fecha.isoformat()} {c.hora or ''}".rstrip() for c in citas)
            return f"Estas son tus próximas citas:\n{lineas}"
        if tipo == "escalar":
            self._escalar(centro_id, telefono, accion.get("motivo", "escalado"))
            return respuesta
        return respuesta

    def _escalar(self, centro_id: int, telefono: str, motivo: str) -> None:
        canonical = tel.normalizar(telefono)
        self.session.execute(text("""
            UPDATE conversaciones SET estado = 'pendiente',
                tags = COALESCE(NULLIF(tags,''), :m), updated_at = now()
            WHERE centro_id = :c AND canal = 'whatsapp' AND telefono = :t
        """), {"m": motivo, "c": centro_id, "t": canonical})
        self.session.commit()

    def _nombres_por_telefono(self, centro_id: int, telefono: str) -> list[str]:
        """Nombres completos de TODOS los pacientes que casan con el teléfono (identidad)."""
        n9 = tel.ultimos9(telefono)
        if len(n9) < 9:
            return []
        rows = self.session.execute(text("""
            SELECT trim(coalesce(nombre,'') || ' ' || coalesce(apellidos,'')) AS n
            FROM pacientes WHERE centro_id = :c AND activo = TRUE AND (
                  right(regexp_replace(coalesce(telefono_movil,''), '\\D','','g'),9) = :n9
               OR right(regexp_replace(coalesce(telefono_fijo,''),  '\\D','','g'),9) = :n9
               OR right(regexp_replace(coalesce(telefono_fijo2,''), '\\D','','g'),9) = :n9)
        """), {"c": centro_id, "n9": n9}).all()
        return [r[0] for r in rows if r[0] and r[0].strip()]

    @staticmethod
    def _map_estado(status: Any) -> str | None:
        return {"READ": "leido", "PLAYED": "leido", "DELIVERY_ACK": "entregado",
                "SERVER_ACK": "enviado"}.get(str(status or "").upper())

    def _detectar_intents(self, centro_id: int, telefono: str, texto: str) -> dict:
        low = f" {(texto or '').lower()} "
        hit = lambda kws: any(f" {k} " in low or low.strip().startswith(k) for k in kws)
        out: dict[str, Any] = {}
        if hit(KW_URGENCIA):
            out["urgencia"] = True
        # Solo actuamos sobre la cita si el teléfono casa EXACTAMENTE con 1 paciente.
        if hit(KW_CANCELAR) or hit(KW_CONFIRMAR):
            pac, n = self.match_paciente(centro_id, telefono)
            if n != 1 or not pac:
                out["cita"] = f"omitida ({n} pacientes)"
            elif hit(KW_CANCELAR):
                out["cita"] = self.cancelar_cita(centro_id, pac.id).get("accion")
            else:
                out["cita"] = self.confirmar_cita(centro_id, pac.id).get("accion")
        return out

    # ─────────────────────── ACCIONES DE CITA ───────────────────────
    def _estado_id(self, centro_id: int, codigo: str) -> int | None:
        e = self.session.exec(select(EstadoCita).where(
            EstadoCita.centro_id == centro_id, EstadoCita.codigo == codigo)).first()
        return e.id if e else None

    def _proxima_cita(self, centro_id: int, paciente_id: int) -> Cita | None:
        excl = self.session.exec(select(EstadoCita.id).where(
            EstadoCita.centro_id == centro_id,
            EstadoCita.codigo.in_(ESTADOS_INACTIVOS))).all()  # type: ignore[union-attr]
        q = select(Cita).where(
            Cita.centro_id == centro_id, Cita.paciente_id == paciente_id,
            Cita.fecha >= date.today())            # FIX .37: solo citas futuras
        if excl:
            q = q.where(Cita.estado_id.not_in(excl))  # type: ignore[union-attr]
        return self.session.exec(q.order_by(Cita.fecha.asc(), Cita.hora.asc())).first()  # type: ignore[union-attr]

    def _ultima_cita(self, centro_id: int, paciente_id: int) -> Cita | None:
        """Última cita YA PASADA. A diferencia de `_proxima_cita`, 'finalizada' SÍ cuenta
        (es el estado normal de una visita pasada) — solo se excluyen anulada/cancelada/fallada."""
        excl = self.session.exec(select(EstadoCita.id).where(
            EstadoCita.centro_id == centro_id,
            EstadoCita.codigo.in_(("anulada", "cancelada", "fallada")))).all()  # type: ignore[union-attr]
        q = select(Cita).where(
            Cita.centro_id == centro_id, Cita.paciente_id == paciente_id,
            Cita.fecha <= date.today())
        if excl:
            q = q.where(Cita.estado_id.not_in(excl))  # type: ignore[union-attr]
        return self.session.exec(q.order_by(Cita.fecha.desc(), Cita.hora.desc())).first()  # type: ignore[union-attr]

    def _tratamientos_de_cita(self, cita_id: int) -> str:
        nombres = self.session.exec(
            select(Tratamiento.nombre).join(CitaTratamiento, CitaTratamiento.tratamiento_id == Tratamiento.id)
            .where(CitaTratamiento.cita_id == cita_id)).all()
        return ", ".join(nombres) if nombres else ""

    def _proximas_citas(self, centro_id: int, paciente_id: int, limit: int = 3) -> list[Cita]:
        excl = self.session.exec(select(EstadoCita.id).where(
            EstadoCita.centro_id == centro_id,
            EstadoCita.codigo.in_(ESTADOS_INACTIVOS))).all()  # type: ignore[union-attr]
        q = select(Cita).where(
            Cita.centro_id == centro_id, Cita.paciente_id == paciente_id,
            Cita.fecha >= date.today())
        if excl:
            q = q.where(Cita.estado_id.not_in(excl))  # type: ignore[union-attr]
        return self.session.exec(
            q.order_by(Cita.fecha.asc(), Cita.hora.asc()).limit(limit)).all()  # type: ignore[union-attr]

    def confirmar_cita(self, centro_id: int, paciente_id: int) -> dict:
        cita = self._proxima_cita(centro_id, paciente_id)
        if not cita:
            return {"accion": "sin_cita"}
        cita.confirmada = True
        eid = self._estado_id(centro_id, "confirmada")
        if eid:
            cita.estado_id = eid
        cita.fecha_hora_estado = datetime.utcnow()
        self.session.add(cita); self.session.commit()
        # PRIMERO se confirma la cita; el consentimiento se envía DESPUÉS del acuse → se deja pendiente.
        self._consent_cita = cita
        return {"accion": "confirmada", "citaId": cita.id}

    def enviar_consentimiento_cita(self, centro_id: int, cita) -> None:
        """Alias público: lo usa Motion (disparador consentimiento_whatsapp) además del
        flujo de confirmación por WhatsApp. Auto-guardado por `cita.envio_doc`."""
        self._enviar_consentimiento_cita(centro_id, cita)

    def _enviar_consentimiento_cita(self, centro_id: int, cita) -> None:
        """Al confirmar la cita: si su tipo requiere consentimiento, genera uno y envía por WhatsApp
        el ENLACE de firma (el paciente lo lee y firma con el dedo en su móvil). Best-effort: nunca
        rompe la confirmación. Salta si el tipo no requiere consentimiento o ya hay uno firmado."""
        try:
            if getattr(cita, "envio_doc", False) or not cita.paciente_id:
                return
            from application.services import consentimiento_service as consvc
            key = consvc.consent_key_para_cita(self.session, cita)
            if not key:
                return
            label = consvc.PLANTILLAS[key][0]
            if consvc.ya_firmado(self.session, cita.paciente_id, label):
                cita.envio_doc = True
                self.session.add(cita); self.session.commit()
                return
            c = consvc.generar(self.session, centro_id, cita.paciente_id, key, cita.colaborador_id)
            cita.envio_doc = True
            self.session.add(cita); self.session.commit()   # el consentimiento ya existe aunque WhatsApp falle
        except Exception:  # raiz: fallo generando el consentimiento (PDF, plantilla o configuración); se revierte y no rompe la confirmación
            self.session.rollback()
            return
        # Enviar por WhatsApp: PDF adjunto + enlace de firma (best-effort).
        try:
            from domain.config.settings import settings
            from domain.models.core import Paciente
            pac = self.session.get(Paciente, cita.paciente_id)
            telefono = getattr(cita, "telefono_movil", None) or (pac.telefono_movil or pac.telefono_fijo if pac else None)
            if not telefono:
                return
            nombre = (pac.nombre.split(" ")[0] if pac and pac.nombre else "")
            # 1) PDF del consentimiento como documento (se abre dentro del propio WhatsApp)
            try:
                b64 = base64.b64encode((consvc.OUT_DIR / f"consent_{c.id}.pdf").read_bytes()).decode()
                self.enviar_documento(centro_id, telefono, b64, f"Consentimiento {c.tipo}.pdf",
                                      f"Hola {nombre}, este es tu consentimiento informado de {c.tipo} para tu próxima cita.")
            except Exception:  # raiz: el PDF es accesorio; el enlace de firma de abajo es lo crítico
                pass
            # 2) Enlace de firma (para firmarlo con el dedo a distancia)
            if c.signing_code:
                enlace = f"{settings.public_frontend_url.rstrip('/')}/firmar/{c.signing_code}"
                self.enviar_texto(centro_id, telefono, f"Y aquí puedes firmarlo con el dedo:\n\n{enlace}")
        except Exception:  # raiz: fallo enviando el consentimiento por WhatsApp (Evolution o datos del paciente); es best-effort y no rompe la confirmación
            return

    def cancelar_cita(self, centro_id: int, paciente_id: int) -> dict:
        cita = self._proxima_cita(centro_id, paciente_id)
        if not cita:
            return {"accion": "sin_cita"}
        eid = self._estado_id(centro_id, "cancelada")
        if eid:
            cita.estado_id = eid
        cita.fecha_hora_estado = datetime.utcnow()
        self.session.add(cita); self.session.commit()
        return {"accion": "cancelada", "citaId": cita.id}

    # ─────────────────────── CONTEXTO DEL PACIENTE (sidebar) ───────────────────────
    def contexto_paciente(self, centro_id: int, telefono: str) -> dict:
        pac, n = self.match_paciente(centro_id, telefono)
        if not pac:
            return {"encontrado": False, "coincidencias": n}
        alertas = self.session.exec(select(AlertaPaciente).where(
            AlertaPaciente.paciente_id == pac.id, AlertaPaciente.activo == True)).all()
        prox = self._proxima_cita(centro_id, pac.id)
        ult = self._ultima_cita(centro_id, pac.id)
        presus = self.session.exec(select(Presupuesto).where(
            Presupuesto.paciente_id == pac.id).order_by(Presupuesto.id.desc()).limit(5)).all()  # type: ignore[union-attr]
        tratamientos = self.session.exec(
            select(TratamientoRealizado, Tratamiento.nombre)
            .join(Tratamiento, Tratamiento.id == TratamientoRealizado.tratamiento_id, isouter=True)
            .where(TratamientoRealizado.centro_id == centro_id, TratamientoRealizado.paciente_id == pac.id)
            .order_by(TratamientoRealizado.fecha_inicio.desc(), TratamientoRealizado.id.desc())  # type: ignore[union-attr]
            .limit(5)).all()
        from application.services.formas_pago_service import mapa_formas, nombre_forma
        formas_cat = mapa_formas(self.session)
        pagos = self.session.exec(select(Pago).where(
            Pago.centro_id == centro_id, Pago.paciente_id == pac.id, Pago.anulado == False)
            .order_by(Pago.fecha.desc(), Pago.id.desc()).limit(5)).all()  # type: ignore[union-attr]
        return {
            "encontrado": True, "coincidencias": n,
            "paciente": {"id": pac.id, "numHistoria": pac.num_historia,
                         "nombre": pac.nombre, "apellidos": pac.apellidos,
                         "telefonoMovil": pac.telefono_movil, "aceptaBots": pac.acepta_bots},
            "alertas": [{"texto": a.texto, "severidad": a.severidad} for a in alertas],
            "proximaCita": ({"id": prox.id, "fecha": prox.fecha.isoformat(), "hora": prox.hora,
                             "confirmada": prox.confirmada,
                             "tratamiento": self._tratamientos_de_cita(prox.id)} if prox else None),
            "ultimaCita": ({"id": ult.id, "fecha": ult.fecha.isoformat(), "hora": ult.hora,
                            "tratamiento": self._tratamientos_de_cita(ult.id)} if ult else None),
            "tratamientosRealizados": [{
                "id": t.id, "fecha": t.fecha_inicio.isoformat() if t.fecha_inicio else None,
                "tratamiento": nombre or "", "piezas": t.piezas,
            } for t, nombre in tratamientos],
            "pagos": [{
                "id": p.id, "fecha": p.fecha.isoformat(), "importe": float(p.importe),
                "formaPago": nombre_forma(formas_cat, p.forma_pago_id),
            } for p in pagos],
            "presupuestos": [{"id": p.id, "estadoId": p.estado_id} for p in presus],
        }
