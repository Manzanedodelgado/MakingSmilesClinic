"""¿Está VIVO el modelo de IA? (no: ¿hay una clave escrita?)

Por qué existe: el 23-jul-2026 NVIDIA retiró el modelo que usaba el centro
(`mistral-large-3-675b`, HTTP 410 Gone) y toda la IA de texto dejó de funcionar —Alex, el
Gestor, la Consulta— mientras el panel seguía diciendo "Operativa". El indicador se
calculaba como `iaOk = bool(config_llm)`: comprobaba que ALGUIEN hubiera escrito una clave,
no que el modelo contestara. Un modelo puede desaparecer del proveedor sin que la config
cambie ni una letra, y eso es exactamente lo que pasó.

Cómo se comprueba: se pide al proveedor su catálogo (`GET /models`, una sola llamada
barata) y se mira si el modelo configurado sigue en la lista. Es fiable y no gasta tokens.
El resultado se cachea unos minutos porque esto se pinta en cada carga del panel.
"""
from __future__ import annotations

import time
from typing import Optional

import httpx

TIMEOUT = 12.0
CACHE_SEG = 300          # 5 min: un modelo no se retira cada minuto
_cache: dict[str, tuple[float, dict]] = {}


def estado_llm(config: Optional[dict]) -> dict:
    """{ok, modelo, motivo}. `ok=False` con motivo legible si no se puede usar.

    Ante un fallo de red se devuelve `ok=None` (desconocido), NUNCA True: no se da por
    bueno lo que no se ha podido comprobar."""
    if not config:
        return {"ok": False, "modelo": None, "motivo": "Sin configurar"}
    modelo = config.get("model")
    base = (config.get("base_url") or "").rstrip("/")
    clave = config.get("api_key") or ""
    if not modelo or not base:
        return {"ok": False, "modelo": modelo, "motivo": "Falta modelo o servidor"}

    # La clave entra en el índice de caché: sin ella, cambiar a una credencial inválida
    # devolvía el resultado cacheado de la buena y el estado seguía diciendo "Operativa".
    import hashlib
    ck = f"{base}|{modelo}|{hashlib.sha256(clave.encode()).hexdigest()[:12]}"
    ahora = time.time()
    if (hit := _cache.get(ck)) and ahora - hit[0] < CACHE_SEG:
        return hit[1]

    try:
        r = httpx.get(f"{base}/models", headers={"Authorization": f"Bearer {clave}"}, timeout=TIMEOUT)
        if r.status_code in (401, 403):
            res = {"ok": False, "modelo": modelo, "motivo": "La clave de API no es válida"}
        elif r.status_code != 200:
            res = {"ok": None, "modelo": modelo, "motivo": f"El proveedor respondió {r.status_code}"}
        else:
            disponibles = {m.get("id") for m in r.json().get("data", [])}
            if modelo not in disponibles:
                res = {"ok": False, "modelo": modelo,
                       "motivo": f"El modelo «{modelo}» ya no existe en el proveedor"}
            else:
                # El catálogo de NVIDIA es PÚBLICO (responde 200 sin credencial), así que
                # por sí solo no prueba que la clave valga. Se remata con una generación
                # mínima (1 token), que es lo único que valida credencial + acceso real.
                res = _probar_generacion(base, clave, modelo)
    except (httpx.HTTPError, ValueError, KeyError) as e:
        # Sin respuesta ≠ funcionando. Se dice que no se sabe.
        res = {"ok": None, "modelo": modelo, "motivo": f"Sin respuesta del proveedor ({type(e).__name__})"}

    _cache[ck] = (ahora, res)
    return res


def _probar_generacion(base: str, clave: str, modelo: str) -> dict:
    """Una generación de 1 token: barata y concluyente. Sólo se llega aquí tras confirmar
    que el modelo está en el catálogo, y el resultado se cachea 5 min."""
    try:
        r = httpx.post(f"{base}/chat/completions",
                       headers={"Authorization": f"Bearer {clave}", "Content-Type": "application/json"},
                       json={"model": modelo, "messages": [{"role": "user", "content": "ok"}],
                             "max_tokens": 1},
                       timeout=TIMEOUT)
        if r.status_code in (401, 403):
            return {"ok": False, "modelo": modelo, "motivo": "La clave de API no es válida"}
        if r.status_code == 410:
            return {"ok": False, "modelo": modelo, "motivo": f"El modelo «{modelo}» fue retirado"}
        if r.status_code == 429:
            return {"ok": None, "modelo": modelo, "motivo": "Límite de uso alcanzado ahora mismo"}
        if r.status_code >= 400:
            return {"ok": False, "modelo": modelo, "motivo": f"El proveedor rechazó la petición ({r.status_code})"}
        return {"ok": True, "modelo": modelo, "motivo": "Operativa"}
    except httpx.HTTPError as e:
        return {"ok": None, "modelo": modelo, "motivo": f"Sin respuesta del proveedor ({type(e).__name__})"}
