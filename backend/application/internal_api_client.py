"""Cliente para API interna del servidor casa.

NUNCA conecta directamente a PostgreSQL.
Siempre pasa por API interna autorizada.
"""

import asyncio
import logging
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import aiohttp

logger = logging.getLogger(__name__)


class InternalAPIClient:
    """
    Cliente para API interna del servidor casa.
    
    Comunicación via Tailscale:
    - Host Cloud: 100.x.x.10
    - Linux Casa: 100.x.x.20
    - API interna: https://api-interna:8443
    """
    
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: int = 30
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def _ensure_session(self):
        """Crear sesión aiohttp si no existe."""
        if self._session is None or self._session.closed:
            headers = {}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
            
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=self.timeout
            )
    
    async def close(self):
        """Cerrar sesión."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def get_patient(
        self,
        patient_id: int,
        user_context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Obtener datos de paciente via API interna.
        
        La autorización se realiza en el servidor casa,
        NO en el LLM.
        """
        await self._ensure_session()
        
        url = urljoin(self.base_url, f"/api/internal/patients/{patient_id}")
        
        # Añadir contexto de autorización en headers
        headers = {
            "X-User-ID": str(user_context.get("user_id")),
            "X-User-Type": user_context.get("user_type"),
            "X-Tenant-ID": str(user_context.get("centro_id")),
        }
        
        try:
            async with self._session.get(url, headers=headers) as response:
                if response.status == 403:
                    logger.warning(f"Acceso denegado a paciente {patient_id}")
                    return None
                
                if response.status != 200:
                    logger.error(f"Error obteniendo paciente: {response.status}")
                    return None
                
                data = await response.json()
                return data
                
        except Exception as e:  # raiz: fallo de red hacia la API interna → sin datos del paciente
            logger.error(f"Error en API interna: {e}")
            return None
    
    async def get_patient_summary(
        self,
        patient_id: int,
        user_context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Obtener resumen de paciente autorizado."""
        return await self.get_patient(patient_id, user_context)
    
    async def create_presupuesto(
        self,
        patient_id: int,
        items: list,
        user_context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Crear presupuesto via API interna."""
        await self._ensure_session()
        
        url = urljoin(self.base_url, "/api/internal/presupuestos")
        
        headers = {
            "X-User-ID": str(user_context.get("user_id")),
            "X-User-Type": user_context.get("user_type"),
            "X-Tenant-ID": str(user_context.get("centro_id")),
        }
        
        payload = {
            "patient_id": patient_id,
            "items": items,
            "user_id": user_context.get("user_id"),
        }
        
        try:
            async with self._session.post(url, json=payload, headers=headers) as response:
                if response.status == 403:
                    logger.warning(f"Acceso denegado para crear presupuesto")
                    return None
                
                if response.status != 201:
                    logger.error(f"Error creando presupuesto: {response.status}")
                    return None
                
                data = await response.json()
                return data
                
        except Exception as e:  # raiz: fallo de red hacia la API interna → presupuesto no creado
            logger.error(f"Error creando presupuesto: {e}")
            return None
    
    async def get_treatments(
        self,
        patient_id: int,
        user_context: Dict[str, Any]
    ) -> Optional[list]:
        """Obtener tratamientos de paciente autorizado."""
        await self._ensure_session()
        
        url = urljoin(
            self.base_url,
            f"/api/internal/patients/{patient_id}/treatments"
        )
        
        headers = {
            "X-User-ID": str(user_context.get("user_id")),
            "X-User-Type": user_context.get("user_type"),
            "X-Tenant-ID": str(user_context.get("centro_id")),
        }
        
        try:
            async with self._session.get(url, headers=headers) as response:
                if response.status == 403:
                    logger.warning(f"Acceso denegado a tratamientos")
                    return None
                
                if response.status != 200:
                    logger.error(f"Error obteniendo tratamientos: {response.status}")
                    return None
                
                data = await response.json()
                return data.get("treatments", [])
                
        except Exception as e:  # raiz: fallo de red hacia la API interna → sin tratamientos
            logger.error(f"Error obteniendo tratamientos: {e}")
            return None
