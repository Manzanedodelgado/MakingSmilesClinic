# Hallazgos de seguridad verificados (2026-11-01)

Verificados por el Lead leyendo el código de `master` @ `a76ee81` en el worktree del
rebuild. **No se ha modificado código**: los cambios que afectan a autenticación
requieren revisión obligatoria (skill `patches-to-core`) y decisión del propietario.

## S1 · CRÍTICO — `GET /pacientes/{paciente_id}/ficha` sin autenticación

**Qué:** endpoint que devuelve datos clínicos de un paciente **sin exigir sesión**.

- Ruta: `backend/api/pacientes_router.py:1433` (`@router.get("/{paciente_id}/ficha")`).
- Firma (líneas 1434-1437): solo `paciente_id` y `session: Session = Depends(get_session)`.
  No hay `Depends(get_current_user)` ni `require_permission(...)`.
- El router se monta sin dependencias globales: `backend/main.py:169`
  (`app.include_router(pacientes_router)`), y no hay middleware de autenticación
  (`main.py:111` es CORS y `main.py:140` es el registrador de errores).
- Respuesta (líneas 1455-1466): `id`, `num_historia`, `nombre`, `apellidos`, `email`,
  `alergias`, `anamnesis`, `nombreCompleto` → **PII + datos de categoría especial (salud)**.

**Alcance real:** el navegador entra por `https://<app>/api/*` y Next reescribe a la API sin
autenticar. Cualquiera con la URL puede recorrer `paciente_id` y obtener la ficha, sin cookie.
No requiere acceso al servidor.

**Comprobación reproducible:**
```bash
grep -n "ficha" -A6 backend/api/pacientes_router.py   # 1433-1437: sin auth
grep -n "@app.middleware" backend/main.py              # solo el registrador de errores
```
(No se puede hacer la petición real aquí: no hay backend/BD levantados en este entorno.)

**Causa raíz:** bloque «ENDPOINTS PARA APPS MÓVILES» (`pacientes_router.py:1432`) escrito
antes de que existiera `app_paciente_router` (rutas de app con su propia
autenticación de paciente). Quedó como código legacy alcanzable: es exactamente el patrón
que las 376 eliminables / 542 parches describen.

**Corrección propuesta (mínima, para revisión):** retirar las dos rutas del bloque
(`/ficha` y `/citas`) en lugar de añadirles autenticación, porque la app móvil usa su propio
router autenticado; añadirlas con `Depends(get_current_user)` sería mantener API duplicada.
Requiere PR a `master` con prueba que demuestre que la app móvil sigue funcionando.

## S2 · ALTO — `GET /pacientes/{paciente_id}/citas` sin autenticación

- Ruta: `backend/api/pacientes_router.py:1468`. Sin auth (solo `get_session`).
- Hoy devuelve un stub (`{"proximas": [], "total": 0}`, línea 1475), por lo que no filtra
  datos; pero está publicado como API de app y cualquier implementación futura repetiría
  el fallo de S1. Misma corrección: retirar el bloque.

## S3 · MEDIO — Rutas sin autenticación declarada: 23

Inventariadas en `PARIDAD-API.md` §4.5. 15 son públicas legítimas (login, webhooks firmados,
relé, salud) y 8 usan un mecanismo de auth que no es `Depends` (`X-Internal-Key`,
`signing_code`, token de webhook, WS). Las 8 deben verificarse una a una antes del corte;
no se han auditado en profundidad todavía.

## S4 · INFORMATIVO — Colisión de rutas

`GET /pacientes/{id}/previstos` está declarada dos veces: sirve
`pacientes_router.py:855` y `clinico_router.py:417` es código muerto (no alcanzable).
Documentado en `PARIDAD-API.md` §2.3.
