"""Blacklist de tablas/columnas sensibles — fuente única (compartida).

Antes vivía duplicada en informes_router y la importaba configuracion_admin_router
(dependencia cruzada M02→M16). Extraída aquí para que ambos consuman la misma regla
C6 (PII/credenciales nunca expuestas en informes ni en introspección de BD).
"""


# Tablas de respaldo/internas que NO se ofrecen para informes ni DB explorer.
def _es_oculta(nombre: str) -> bool:
    low = nombre.lower()
    return nombre.startswith("_") or any(s in low for s in ("bk", "backup", "bak", "dedup"))


# C6: Blacklist de columnas sensibles (PII/credenciales) que NO se exponen.
_COLUMNAS_OCULTAS_POR_TABLA = {
    "usuarios": {"password_hash", "email", "username", "nif", "telefono"},  # PII + credentials
    "integraciones": {"config"},  # secrets (webhook_hmac, api_keys, etc.)
}
