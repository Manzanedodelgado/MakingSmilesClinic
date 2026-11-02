"""Interruptor manual del motor local de Alex/Víctor/Aura (Ollama en PC-ESCANER).

Por qué existe: el PC que tiene GPU dedicada (RTX 3080) es también el equipo del escáner
intraoral Medit i500, que satura la tarjeta gráfica durante el escaneo real de un paciente.
No puede dejarse el modelo corriendo 24/7 sin arriesgar que compita por la GPU justo cuando
el doctor está escaneando — así que el encendido/apagado es manual, bajo control humano,
nunca automático.

Cómo funciona: SSH directo al PC-ESCANER (Windows con OpenSSH Server) usando las
credenciales guardadas en `Integracion` (tipo='ollama_switch'). Encender = disparar la
tarea programada `AlexOllamaServer` (ya configurada para arrancar `ollama serve` con
OLLAMA_HOST=0.0.0.0:11434 en la sesión interactiva del usuario, necesaria para que Ollama
vea la GPU). Apagar = matar el proceso `ollama.exe`, liberando la GPU al instante.

Interruptor GENERAL + 3 ESPECÍFICOS: el general (encender/apagar de arriba) es el motor
físico — si está apagado, ninguno de los tres responde, sin excepción, porque no hay
proceso al que preguntar. Los 3 específicos (`agentes_activos`) son un cierre lógico
independiente por encima: permiten apagar solo Alex (o solo Víctor, o solo Aura) sin tocar
el motor, para los tres compartiendo el mismo servidor. El general SIEMPRE manda: un
específico en "activo" no sirve de nada si el general está apagado (`resolver_llm` en
`llm_config.py` es quien aplica este cierre antes de devolver la config a cada agente).
"""
from __future__ import annotations

from typing import Optional

import paramiko
from sqlmodel import Session, select

from domain.models.config import Integracion

TIMEOUT = 15
AGENTES = ("alex", "victor", "aura")


def _config(session: Session, centro_id: int) -> Optional[dict]:
    row = session.exec(
        select(Integracion).where(
            Integracion.tipo == "ollama_switch", Integracion.centro_id == centro_id,
        )
    ).first()
    return row.config if row else None


def _conectar(cfg: dict) -> paramiko.SSHClient:
    cliente = paramiko.SSHClient()
    cliente.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cliente.connect(
        hostname=cfg["host"], port=cfg.get("ssh_port", 22),
        username=cfg["ssh_user"], password=cfg["ssh_password"],
        timeout=TIMEOUT,
    )
    return cliente


def _ejecutar(cfg: dict, comando: str) -> str:
    cliente = _conectar(cfg)
    try:
        _, stdout, stderr = cliente.exec_command(comando, timeout=TIMEOUT)
        salida = stdout.read().decode(errors="replace")
        error = stderr.read().decode(errors="replace")
        return salida or error
    finally:
        cliente.close()


def estado(session: Session, centro_id: int) -> dict:
    """{disponible, encendido, motivo}. `disponible=False` si no hay switch configurado."""
    cfg = _config(session, centro_id)
    if not cfg:
        return {"disponible": False, "encendido": False, "motivo": "Interruptor no configurado"}
    try:
        salida = _ejecutar(cfg, 'powershell -Command "Get-Process ollama -ErrorAction SilentlyContinue | Measure-Object | Select-Object -ExpandProperty Count"')
        encendido = salida.strip() not in ("", "0")
        return {"disponible": True, "encendido": encendido, "motivo": None}
    except (paramiko.SSHException, OSError) as e:
        return {"disponible": True, "encendido": False, "motivo": f"Sin respuesta del PC ({type(e).__name__})"}


def encender(session: Session, centro_id: int) -> dict:
    cfg = _config(session, centro_id)
    if not cfg:
        raise ValueError("Interruptor no configurado para este centro")
    tarea = cfg.get("tarea_programada", "AlexOllamaServer")
    _ejecutar(cfg, f"schtasks /Run /TN {tarea}")
    return estado(session, centro_id)


def apagar(session: Session, centro_id: int) -> dict:
    cfg = _config(session, centro_id)
    if not cfg:
        raise ValueError("Interruptor no configurado para este centro")
    _ejecutar(cfg, 'powershell -Command "Get-Process ollama -ErrorAction SilentlyContinue | Stop-Process -Force"')
    return estado(session, centro_id)


def _fila(session: Session, centro_id: int) -> Optional[Integracion]:
    return session.exec(
        select(Integracion).where(Integracion.tipo == "ollama_switch", Integracion.centro_id == centro_id)
    ).first()


def agente_activo(session: Session, centro_id: int, agente: str) -> bool:
    """¿Está activo el interruptor ESPECÍFICO de `agente`? No mira el general — eso lo
    decide `resolver_llm` combinando esto con el estado real del motor."""
    row = _fila(session, centro_id)
    if not row:
        return True  # sin switch configurado: no bloquear (retrocompatible)
    return bool(row.config.get("agentes_activos", {}).get(agente, True))


def estado_agentes(session: Session, centro_id: int) -> dict:
    row = _fila(session, centro_id)
    activos = (row.config.get("agentes_activos") if row else None) or {}
    return {a: activos.get(a, True) for a in AGENTES}


def toggle_agente(session: Session, centro_id: int, agente: str, activo: bool) -> dict:
    if agente not in AGENTES:
        raise ValueError(f"Agente desconocido: {agente}")
    row = _fila(session, centro_id)
    if not row:
        raise ValueError("Interruptor no configurado para este centro")
    cfg = dict(row.config)
    agentes_activos = dict(cfg.get("agentes_activos") or {})
    agentes_activos[agente] = activo
    cfg["agentes_activos"] = agentes_activos
    row.config = cfg
    session.add(row); session.commit()
    return estado_agentes(session, centro_id)
