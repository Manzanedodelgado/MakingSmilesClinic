# Integración API Vercel ↔ Oracle (task-4)

Capa nueva del backend para que el frontend desplegado en **Vercel** consuma la API en
**Oracle** sin depender del rewrite `/api/*` para dos flujos que no lo toleran:

1. **Media clínica pesada**: el navegador carga el fichero directamente contra Oracle con
   una **URL firmada de corta vida** (sin cookie), no a través de la función de Vercel.
2. **SSE** (`/comunicacion/stream`): `EventSource` no puede enviar cabeceras cross-origin,
   así que el frontend obtiene un **ticket de corta vida** y lo pasa en la URL.

Código (todo en `backend/`), sin modificar contratos existentes:

| Pieza | Fichero |
|---|---|
| Firma HMAC de URLs y ticket SSE | `backend/infrastructure/firma_media.py`, `backend/infrastructure/sse_ticket.py` |
| Política compartida de rutas de /media (anti-traversal + solo-proxy) | `backend/api/media_paths.py` (extraída de `api/media_router.py`, que ahora la reutiliza) |
| Endpoints media firmada | `backend/api/media_firma_router.py` |
| Endpoint ticket SSE | `backend/api/events_router.py` |
| Auth opcional cookie-o-ticket | `backend/api/auth_deps.py` (`get_current_user_opcional`, `resolver_centro`) |
| Stream con ticket | `backend/api/comunicacion_router.py` (`GET /comunicacion/stream`) |
| CORS de `/media/firmado/*` + CORP | `backend/main.py` (middleware `_cors_media_firmada`) |
| Configuración | `backend/domain/config/settings.py` |
| Tests | `backend/tests/test_integracion_firmada.py` |

> Nota de ruta: el encargo decía `backend/infrastructure/config/settings.py`; en el repo la
> configuración vive en `backend/domain/config/settings.py` (settings.py único). Se ha
> modificado esa, sin crear un módulo duplicado.

## Configuración (sin valores reales)

| Variable | Defecto | Uso |
|---|---|---|
| `PUBLIC_API_URL` | `http://localhost:8000` | URL pública del backend (tras Caddy) para construir las URLs firmadas. Fuera de development debe ser `https://`. |
| `MEDIA_SIGNING_SECRET` | `""` | Clave HMAC de las URLs de media (independiente del `SECRET_KEY` del JWT). **Obligatoria (≥32 chars) fuera de development**; el arranque falla si falta. En development, vacía → se usa `SECRET_KEY` local. |
| `MEDIA_SIGN_URL_TTL` | `300` | Vida de la URL firmada (segundos). |
| `SSE_TICKET_TTL` | `600` | Vida del ticket SSE (segundos). |

Pendiente para infra (task-2): añadir `PUBLIC_API_URL` y `MEDIA_SIGNING_SECRET` a
`deploy/oracle/env.example` y al entorno real de Oracle (sin ellos el backend no arranca
fuera de development, por diseño).

## Endpoints

### 1. `GET /media/firma?ruta=<relpath>` — auth cookie

Emite una URL firmada para un fichero de `/media`. La ruta es relativa a `backend/media`
(la misma que sirve `GET /media/{ruta:path}`). `media/pacientes/**` y las rutas que salen
de `/media` responden **404** (para esas imágenes va el punto 2).

```http
GET /media/firma?ruta=informes/informe.pdf
Authorization: Bearer <JWT>   (o cookie httpOnly access_token)
```
```json
200 {"url": "https://api.staging.example.com/media/firmado/informes/informe.pdf?exp=1793518907&uid=1&sig=0cbf69a5…ba6a920", "exp": 1793518907}
```
Errores: `401` sin sesión, `404` si no es servible por esta vía.

### 2. `GET /media/firmado/{ruta:path}?exp=&uid=&sig=` — **sin cookie**

Sirve el fichero solo si la firma HMAC-SHA256 y la caducidad son válidas. Cabeceras:
`Cache-Control: private, max-age=300` y `Cross-Origin-Resource-Policy: cross-origin`
(necesaria para incrustar la imagen con COEP/SharedArrayBuffer en el visor). CORS para los
orígenes permitidos (`ALLOWED_ORIGINS`), sin credenciales.

Mensaje firmado: `media|{ruta}|{exp}|{uid}` con `MEDIA_SIGNING_SECRET` (hex).
Errores: `403` firma inválida/caducada, `404` no encontrado/traversal/solo-proxy.

### 3. `POST /pacientes/{paciente_id}/multimedia/{file_id}/firma?thumb=0|1` — auth cookie

Firma una imagen de la ficha del paciente reutilizando el **mismo guard anti-IDOR** que el
proxy existente: `_get_paciente(session, centro_id, paciente_id)` (paciente∈centro) y
`MultimediaService.media(...)` (el fichero debe colgar de la carpeta del paciente en
local/Drive/Orthanc). `file_id` es el `id` que devuelve `GET /pacientes/{id}/multimedia`
(URL-encoded como segmento de path). `thumb=1` firma la **miniatura** (la UI la usa en
miniaturas de 76 px); ausente → imagen completa.

```http
POST /pacientes/42/multimedia/local%3AQUJDREVGRw%3D%3D/firma?thumb=1
```
```json
200 {"url": "https://api.staging.example.com/media/firmado/pacientes/42/local%3AQUJD…?exp=…&uid=1&thumb=1&sig=…", "exp": 1793518907}
```
Errores: `401` sin sesión, `403` sin permiso `pacientes.ver`, `404` paciente de otro centro /
fichero que no cuelga de él.

### 4. `GET /media/firmado/pacientes/{paciente_id}/{file_id}?exp=&uid=&thumb=&sig=` — **sin cookie**

Descarga la imagen del paciente con la URL firmada. Mensaje firmado:
`paciente|{pid}|{file_id}|{exp}|{uid}|thumb={0|1}`. Vuelve a aplicar el guard anti-IDOR de
`MultimediaService` al servir. Errores: `403` firma inválida/caducada o variante distinta,
`404` no encontrado.

### 5. `GET /events/ticket` — auth cookie

```http
GET /events/ticket
Authorization: Bearer <JWT>
```
```json
200 {"token": "<jwt HS256>", "exp": 1793520000}
```
Claims: `sub` (usuario), `scope="sse"`, `centro_id`, `exp`. Firmado con `SECRET_KEY`
(HS256) y TTL `SSE_TICKET_TTL`. **No es de un solo uso** (EventSource reconecta solo) y
**no vale como token de sesión**: `get_current_user` exige `tipo="centro"` y el stream
exige `scope="sse"`.

### 6. `GET /comunicacion/stream?ticket=<jwt>` — cookie **o** ticket

Si llega `ticket` válido, autentica con él (el `centro_id` viaja en el ticket); si no,
comportamiento idéntico al actual (cookie/Bearer + `X-Centro-Id`). Se exige el permiso
`comunicacion.ver` en ambos casos. `?ticket=` **solo** se acepta en esta ruta.

## Decisiones de seguridad

- **Separación de claves**: las URLs de media usan `MEDIA_SIGNING_SECRET`, no el
  `SECRET_KEY` del JWT (que el ticket SSE sí usa). En development se permite el fallback
  a `SECRET_KEY`; en producción el arranque aborta si falta el secreto dedicado (≥32).
- **Ámbito de la firma (no reutilizable)**:
  - Genérica: `media|ruta|exp|uid` → no se puede cambiar la ruta, alargar `exp` ni
    atribuir la URL a otro usuario (el `uid` va en la query y forma parte del HMAC; si se
    cambia o se omite, la firma deja de cuadrar).
  - De paciente: `paciente|pid|file_id|exp|uid|thumb=N` → una URL de un paciente no sirve
    para otro `pid`, ni para otro `file_id`, ni para la otra variante (miniatura/completa).
  - Namespace explícito (`media|` vs `paciente|`) → una firma genérica no vale en la ruta
    de paciente ni al revés.
- **Anti-IDOR**: el POST de firma y el GET firmado de paciente reutilizan los guards ya
  existentes (`_get_paciente` + `MultimediaService.media`), sin duplicar reglas. La ruta
  genérica mantiene la regla de `media_router`: `pacientes/**` no se sirve crudo, ni
  siquiera con una firma genérica válida (404).
- **Anti-traversal**: la política vive en una sola función (`media_paths.resolver_media`),
  compartida por la ruta autenticada y la firmada; el fichero resuelto debe quedar dentro
  de `backend/media`.
- **Caducidad**: `exp` se comprueba contra el reloj del servidor en cada descarga; el
  ticket SSE usa además la validación `exp` estándar del JWT.
- **Sin trazas sensibles**: no se registran tokens, firmas ni URLs firmadas (son bearers
  de corta vida). Los errores son 401/403/404 explícitos, sin filtrar rutas internas.
- **Ticket no reutilizable como sesión**: `scope="sse"`, sin claim `tipo`, y solo el
  stream lo consume. Un JWT de sesión tampoco vale como ticket (no tiene `scope="sse"`).

## CORS y CORP

`/media/firmado/*` se carga desde el navegador con otro origen y **sin credenciales**: el
middleware `_cors_media_firmada` devuelve `Access-Control-Allow-Origin` para cualquier
origen de `ALLOWED_ORIGINS` (sin `Access-Control-Allow-Credentials`) y añade
`Cross-Origin-Resource-Policy: cross-origin` para el visor CBCT bajo COEP. El
preflight `OPTIONS` lo cubre el `CORSMiddleware` global.

## Verificación

- `backend/tests/test_integracion_firmada.py` — 6 tests con `TestClient` + SQLite en
  memoria (sin Postgres real): firma genérica y descarga sin cookie, manipulación
  (firma/uid/exp/traversal/solo-proxy), firma de multimedia de paciente (thumb, cross-paciente,
  cross-fichero), ticket SSE (claims, no válido como sesión), stream con ticket y con cookie,
  y validadores de settings de producción.
- `python -c "from main import app; print(len(app.openapi()['paths']))"` → `437` rutas
  (antes `432`; +5: `GET /media/firma`, `GET /media/firmado/{ruta:path}`,
  `GET /media/firmado/pacientes/{paciente_id}/{file_id}`,
  `POST /pacientes/{paciente_id}/multimedia/{file_id}/firma`, `GET /events/ticket`;
  `/comunicacion/stream` ya existía y suma `ticket` como query, sin perder rutas).
- Gate `scripts/deploy-gate.sh` en verde (ver informe de la tarea).

**No verificado aquí**: descarga real contra Oracle/Caddy (sin Docker ni dominio), CORS
preflight real en navegador (sin Playwright en este frente), y comportamiento de Redis
pub/sub del bus SSE (en tests el bus es en memoria). El handshake SSE completo se prueba
hasta la apertura del stream (cabeceras 200 `text/event-stream`), no se consumen eventos.
