# INFRA — Staging nuevo: Vercel (frontend) + Oracle Always Free (API)

| Campo | Valor |
|---|---|
| Frente | S1 — infraestructura nueva escrita de cero (`task-2`) |
| Autor | `infra-oracle` (equipo MakingSmiles_Studio) |
| Fecha | 2026-11-01 |
| Rama | `rebuild/vercel-oracle` (base `master` @ `a76ee81`) |
| Alcance | STAGING. No toca producción ni el árbol principal. |
| Entregables | `deploy/oracle/` (compose, Caddyfile, bootstrap, backup, restore, deploy, README), `vercel.json`, `.github/workflows/deploy-oracle.yml`, este documento |

**Leyenda de validación** (se usa en todo el documento):

- **VERIFICADO (ejecutado)** — lo he ejecutado en este entorno y el resultado está abajo (§12).
- **VERIFICADO (doc)** — lo he contrastado contra la documentación oficial citada, pero no lo he ejecutado.
- **NO VALIDADO** — no se pudo ejecutar aquí; queda listado en §13. No se presenta como hecho.

> **Advertencia de alcance legal**: este documento es técnico. El bloqueo del plan
> Hobby de Vercel (§6) tiene consecuencias contractuales y de protección de datos;
> no es asesoramiento jurídico. Antes de cortar a producción hace falta revisión
> jurídica/DPO, no solo técnica.

---

## 1. Resumen ejecutivo

- **Frontend** en Vercel (plan Hobby, decisión del propietario): `staging.<dominio>`.
- **API** en una instancia Oracle Always Free (A1.Flex, arm64) detrás de Caddy con
  TLS automático: `api.staging.<dominio>`. Solo 80/443 publicados.
- El navegador **nunca** llama a `api.<dominio>` para la API normal: pide `/api/*`
  al frontend y Vercel lo reescribe a `https://api.staging.<dominio>`. La cookie de
  sesión queda **first-party** (`staging.<dominio>`) y no hace falta CORS de
  credenciales.
- **`/media` y SSE no pasan por Vercel**: media con URL firmada de corta vida
  contra `api.<dominio>` (Caddy añade `Cross-Origin-Resource-Policy: cross-origin`
  para que funcione con `COEP: require-corp`); SSE con un **token firmado de corta
  vida y reutilizable durante su ventana** en la query porque `EventSource` no
  puede mandar cabeceras y reconecta solo (un ticket de un solo uso lo dejaría en
  401 al reconectar; ver §5.3).
- El análisis de IA (~30 s) es **asíncrono**: `POST` devuelve `job_id` y el cliente
  hace polling. Nunca una petición síncrona a través de proxies (§5.4).
- **Riesgo aceptado y registrado**: el plan Hobby prohíbe el uso comercial y no
  tiene DPA. Está en §6 como **bloqueo de revisión obligatoria** antes del corte a
  producción, con las consecuencias y las mitigaciones. El ADR del propietario es
  [ADR-001](../decisiones/ADR-001-riesgo-vercel-hobby.md) (§6.2).
- **Bloqueo vigente D-2**: la API todavía no implementa la firma de `/media` ni el
  token SSE; mientras no exista, media y SSE no funcionan (es S2). No es un fallo
  de esta capa: es una dependencia bloqueante del corte (§11).
- Todo se despliega desde Git: Vercel por integración Git (frontend), GitHub
  Actions por SSH (API). Rollback en §8 y backups/restauración en §9.

## 2. Arquitectura

```
                 ┌──────────────────────────────┐
  navegador ────►│  Vercel (Hobby, región fra1) │  staging.<dominio>
                 │  Next.js + CDN + rewrite     │  TLS gestionado por Vercel
                 └──────────────┬───────────────┘
                                │ /api/*  ── rewrite externo (proxy CDN)
                                ▼
                 ┌──────────────────────────────┐
                 │  Oracle Always Free (A1 ARM) │  api.staging.<dominio>
                 │  Caddy :80/:443 (TLS LE)     │  único puerto publicado
                 │    └─ api:8000 (FastAPI)     │  backend (interna) + edge (EGRESO:
                 │    ├─ postgres:16            │  LLM/SMTP); ningún puerto publicado
                 │    ├─ redis:7                │  sin puertos publicados
                 │    └─ evolution:v2.3.7       │  + edge (EGRESO: WSS WhatsApp)
                 └──────────────────────────────┘

  /media/*  y  /events/*  (SSE): el navegador va DIRECTO a api.staging.<dominio>,
  no pasan por Vercel (URL firmada y token firmado de corta vida, respectivamente).
```

### 2.1 Componentes y responsabilidades

| Componente | Imagen (fijada) | Red | Puertos | Salud |
|---|---|---|---|---|
| Caddy | `caddy:2.11.7-alpine` | `edge` + `backend` | **80, 443/tcp, 443/udp** (únicos publicados) | admin `:2019/config/` |
| API FastAPI | `ghcr.io/<owner>/<repo>-api:<sha>` | `backend` + `edge` (solo egress) | ninguno | `/health/db` |
| Postgres | `postgres:16` | `backend` | ninguno | `pg_isready` |
| Redis | `redis:7-alpine` | `backend` | ninguno | `redis-cli ping` |
| Evolution API | `evoapicloud/evolution-api:v2.3.7` | `backend` + `edge` | ninguno | `fetchInstances` autenticado |

`edge` = bridge con salida a internet (Caddy para ACME; API para LLM/SMTP; **Evolution
para el WSS con WhatsApp**). `backend` = bridge `internal: true`, sin ruta a internet.
Justificación: Postgres y Redis no necesitan salir; la API y Evolution sí. Se les da
egress por `edge`, que no publica ningún puerto (solo Caddy publica 80/443).
Un `POSTGRES_PASSWORD`/`SECRET_KEY` real vive solo en `/opt/makingsmiles/.env` (600).

Recursos por servicio (Compose `mem_limit`/`cpus`/`pids_limit`, pensados para 2 OCPU/12 GB):
Caddy 256 MB/0.5/200 · API 4 GB/1.5/512 · Postgres 2 GB/0.5/256 · Redis 256 MB/0.2/128 ·
Evolution 2 GB/0.3/256. Los workers de uvicorn son `${API_WORKERS:-2}` (no 4: 4
sobre-suscribe 2 vCPU; el CMD legacy pedía 4 y aquí se fija el `command:` explícito).
El operador del centro de salud puede detectar WSS caído con `check-evolution.sh` (§7.4).

### 2.2 Dominios y TLS

| Nombre | Apunta a | TLS | Quién lo emite |
|---|---|---|---|
| `staging.<dominio>` | Vercel | HTTPS automático | Vercel ([dominios](https://vercel.com/docs/domains)) |
| `api.staging.<dominio>` | IP pública Oracle | HTTPS automático | Caddy / Let's Encrypt ([automatic-https](https://caddyserver.com/docs/automatic-https)) |
| `staging.example.com` / `api.staging.example.com` | — | — | **placeholders de este repo**: hay que sustituirlos (§7.2.1) |

Notas:
- El certificado de `api.*` se emite cuando el DNS ya resuelve a la instancia y el
  puerto 80 es alcanzable desde internet (ACME HTTP-01). Antes de eso Caddy
  reintenta; no bloquea el arranque de la API.
- Para ensayar sin gastar cuota de Let's Encrypt, `ACME_CA` admite la CA de staging
  (`https://acme-staging-v02.api.letsencrypt.org/directory`).
- No se usa `preload` de HSTS en staging.

### 2.3 Por qué el rewrite va en `vercel.json` y no en `next.config`

`next.config.ts` (Next.js) también sabe reescribir, pero esas reglas se ejecutan en
el runtime de Next, es decir **dentro de una invocación de función** y sujetas a los
límites de funciones (cuerpo 4,5 MB; duración máxima 300 s en Hobby). Un rewrite
externo declarado en `vercel.json` lo aplica el CDN como proxy: el timeout aplicable
es el de *proxied request* (120 s) y no consume una función ([rewrites externos](https://vercel.com/docs/routing/rewrites#rewrites-to-external-origins),
[límites de funciones](https://vercel.com/docs/functions/limitations),
[proxied request timeout](https://vercel.com/docs/limits#proxied-request-timeout)).

Consecuencia práctica: el rewrite de `/api/*` **no** está pensado para cuerpos
grandes (límite de función 4,5 MB si en algún momento algo pasa por una función) ni
para respuestas > 120 s. Por eso `/media` y SSE van directos al origen.

> **Hay dos `vercel.json`, y el que manda es `frontend/vercel.json`.** El proyecto
> de Vercel usa *Root Directory* = `frontend/`, y Vercel busca el fichero de
> configuración en la raíz del proyecto ([vercel.json](https://vercel.com/docs/project-configuration/vercel-json)),
> es decir, en `frontend/`. El de la **raíz del repo** es la copia canónica de
> revisión de esta tarea (y la que valida el gate); el **operativo** es
> `frontend/vercel.json`. Ambos deben ser **idénticos**: el gate de CI comprueba la
> igualdad y falla si divergen. Si solo se actualiza uno, el rewrite/CSP de Vercel
> no cambia aunque el repo parezca correcto.

## 3. Mapa de rutas observables

| Ruta del navegador | Va a | Timeout relevante | Notas |
|---|---|---|---|
| `https://staging.<dominio>/*` | Vercel (Next/CDN) | — | estáticos por CDN global |
| `https://staging.<dominio>/api/*` | `https://api.staging.<dominio>/*` | **120 s** (proxy Vercel) | cookie first-party; respuestas `no-store` |
| `https://api.staging.<dominio>/media/*` | API | sin límite Vercel | URL firmada corta + CORP `cross-origin` |
| `https://api.staging.<dominio>/events/*` | API (SSE) | sin límite Vercel | token firmado de corta vida en `?token=` |
| `https://api.staging.<dominio>/health/db` | API | — | healthcheck de Compose y de despliegue |
| `https://api.staging.<dominio>/` (resto) | API | — | API directa (p. ej. apps móviles) |

## 4. Variables de entorno (sin secretos)

Plantilla completa: `deploy/oracle/env.example`. Se genera en el servidor con
`bootstrap-oracle.sh` y modo 600.

| Variable | Ejemplo | Secreto | Dónde |
|---|---|---|---|
| `DOMAIN` / `APP_DOMAIN` / `API_DOMAIN` | `example.com` / `staging.example.com` / `api.staging.example.com` | No | `.env` servidor, `vercel.json`, DNS |
| `ACME_EMAIL` / `ACME_CA` | `ops@example.com` / CA LE | No | `.env` servidor |
| `API_IMAGE` | `ghcr.io/owner/repo-api:<sha>` | No | `.env` servidor (lo actualiza el deploy) |
| `POSTGRES_USER` / `POSTGRES_DB` | `makingsmiles` | No | `.env` |
| `POSTGRES_PASSWORD` | `openssl rand -hex 24` | **Sí** | `.env` |
| `DATABASE_URL` | `postgresql+psycopg://...@postgres:5432/...` | **Sí** (lleva contraseña) | `.env` |
| `EVOLUTION_DATABASE_URI` | `postgresql://...@postgres:5432/evolution?schema=public` | **Sí** | `.env` |
| `SECRET_KEY` | `openssl rand -hex 48` | **Sí** | `.env` |
| `INTERNAL_API_KEY` | `openssl rand -hex 32` | **Sí** | `.env` |
| `EVOLUTION_API_KEY` | `openssl rand -hex 24` | **Sí** | `.env` |
| `ENVIRONMENT` | `staging` | No | `.env` |
| `COOKIE_SECURE` | `1` | No | `.env` |
| `PUBLIC_FRONTEND_URL` | `https://staging.<dominio>` | No | derivada de `APP_DOMAIN` en compose; CORS de la API |
| `PUBLIC_API_URL` | `https://api.staging.<dominio>` | No | derivada de `API_DOMAIN`; firma de `/media` y tokens SSE |
| `API_WORKERS` / `API_MEM_LIMIT` / `API_CPUS` | `2` / `4g` / `1.5` | No | `.env` (recursos de Compose) |
| `REDIS_URL` | `redis://redis:6379/0` | No | `.env` |
| `BACKUP_DIR` / `BACKUP_RETENTION_DAYS` | `/opt/makingsmiles/backups` / `14` | No | `.env` |
| `BACKUP_DEST` | `user@host:/srv/backups/makingsmiles-staging` (**directorio dedicado**) | **Sí** | `.env` |
| `BACKUP_SSH_KEY` / `BACKUP_KNOWN_HOSTS` | `/opt/makingsmiles/.ssh/backup_key` / `.../known_hosts` | **Sí** | ficheros root 600 en el servidor |
| `BACKUP_AGE_RECIPIENT` | `age1...` (clave pública) | No (pública) | `.env`; privada fuera del servidor |
| `BACKUP_OFFSITE_REQUIRED` | `1` | No | `.env` |
| `LLM_*`, `GROQ_*`, `OPENROUTER_*`, `GEMINI_*`, `NVIDIA_*`, `OCR_*`, `TXT_*` | opcionales | **Sí** | `.env` |
| Secretos de GitHub Actions | `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_PORT`, `DEPLOY_KNOWN_HOSTS`, `STAGING_API_URL` | **Sí** | GitHub → Settings → Environments → `staging` |

Ningún secreto se escribe aquí ni se commitea. `.env` está gitignored.

## 5. Flujos críticos

### 5.1 Login y cookie first-party

1. El navegador hace `POST https://staging.<dominio>/api/auth/login`.
2. Vercel aplica el rewrite externo y reenvía a `https://api.staging.<dominio>/auth/login`.
   El navegador **no** ve redirección: la URL sigue siendo la del frontend
   ([rewrites](https://vercel.com/docs/routing/rewrites#rewrites-to-external-origins)).
3. La API responde `Set-Cookie: access_token=...; HttpOnly; Secure; SameSite=Lax` **sin
   atributo `Domain`**. Como la respuesta llega al navegador con el origen
   `staging.<dominio>`, la cookie es host-only de ese dominio: **first-party**.
4. Peticiones siguientes: `/api/*` vuelve a pasar por el rewrite con la cookie; no
   hay CORS de credenciales desde el navegador.
5. La API tiene `PUBLIC_FRONTEND_URL=https://staging.<dominio>` para su CORS, que
   solo se usa en las rutas que el navegador llama **directamente** (`/media`,
   `/events`). Esas peticiones no usan cookies (URL firmada / token firmado).
   El nombre real de la cookie es **`access_token`** (verificado en
   `backend/api/auth_router.py:84-97`).

Cabeceras que Vercel añade al origen externo: `x-real-ip`, `x-forwarded-for`,
`x-forwarded-host`, `x-forwarded-proto` ([rewrites externos](https://vercel.com/docs/routing/rewrites#identifying-the-visitor-at-your-origin)).
Caddy, por defecto, **ignora** el `X-Forwarded-For` entrante y pone el suyo
([reverse_proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#defaults)),
así que la IP real del visitante llega en `X-Real-IP` (la reenvía Vercel) y Caddy la
propaga tal cual. **Riesgo abierto**: cualquiera que llame directo a `api.<dominio>`
puede falsificar `X-Real-IP`; para auditoría de login hay que decidir una política de
confianza (ver §10.5). En staging se acepta; no para producción.

### 5.2 `/media`: URL firmada de corta vida + CORP

- El navegador no pide media a Vercel. La API firma una URL absoluta contra
  `PUBLIC_API_URL` con caducidad corta (p. ej. 60-120 s) y la devuelve en el JSON.
- `<img>/<video>` carga `https://api.staging.<dominio>/media/...?exp&sig` sin cookie.
- El frontend tiene `Cross-Origin-Embedder-Policy: require-corp`; por eso Caddy
  añade `Cross-Origin-Resource-Policy: cross-origin` en `/media/*`. Sin CORP, el
  navegador bloquearía el recurso cross-origin.
- La CSP del frontend (`vercel.json`) incluye `img-src`/`media-src` con el origen
  `https://api.staging.<dominio>`.
- Motivo de no pasar por Vercel: los cuerpos/archivos superan el límite de 4,5 MB
  documentado para funciones ([request body size](https://vercel.com/docs/functions/limitations#request-body-size));
  en el baseline hay ficheros de hasta 8,6 MB y `backend/media` ~1,2 GB.
- Contrato de API necesario (lo implementa el frente de backend): firma HMAC,
  caducidad, binding a ruta y, si se puede, a usuario. El TTL lo decide la API.

### 5.3 SSE: token firmado de corta vida (NO de un solo uso)

`EventSource` no permite cabeceras personalizadas y **reconecta automáticamente**
(reintenta con backoff si el stream se corta). Un ticket de un solo uso dejaría la
reconexión en 401; por eso el diseño vigente es un **token firmado de corta vida y
reutilizable durante su ventana**:

1. `POST https://staging.<dominio>/api/events/token` (por el rewrite, con cookie)
   → `200 {"token": "...", "url": "https://api.staging.<dominio>/events/stream?token=..."}`.
2. El navegador abre `EventSource` contra esa URL **directa** (nunca por Vercel).
3. La API valida en cada conexión (y reconexión) el token firmado: HMAC, caducidad
   corta (p. ej. 5 min), ligado a usuario/sesión. Mientras no caduque, el mismo
   token sirve para reconectar; al expirar, el cliente pide otro por el endpoint 1.
4. Caddy no bufferiza ni comprime el stream (`flush_interval -1`,
   `stream_timeout 1h`), [documentado](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#streaming).
5. CORS: la API responde `Access-Control-Allow-Origin: https://staging.<dominio>`
   (su CORS normal). `EventSource` es una petición CORS; no hay preflight.

Por qué no por Vercel: un stream largo choca con el timeout de proxy externo de
120 s ([proxied request timeout](https://vercel.com/docs/limits#proxied-request-timeout))
y con el buffering del CDN. No se usa el límite de 300 s de función Hobby
([max duration](https://vercel.com/docs/functions/limitations#max-duration)) porque
el SSE va directo, no por una función.

> **Discrepancia documental conocida**: el ADR-001 (lo lleva el Lead) todavía dice
> «ticket de un solo uso»; el diseño vigente es token firmado reutilizable. Hay que
> corregir la frase del ADR, no este documento (aquí ya está el diseño nuevo).


### 5.4 Análisis de IA (~30 s): asíncrono

- `POST /api/analisis` responde rápido con `202 {"job_id": ...}`.
- El trabajo corre **fuera** de la petición HTTP (worker/cola con Redis).
- El cliente hace `GET /api/analisis/{job_id}` (polling) o recibe el resultado por
  SSE (§5.3).
- Por qué: aunque 30 s caben bajo el timeout de proxy de 120 s, un diseño síncrono
  acumula tres puntos de fallo (Vercel CDN → Caddy → uvicorn), no admite reintentos
  baratos y bloquea workers. Además, el límite de proxy (120 s) es el techo duro,
  no los 300 s de función Hobby.
- Estados del job y su limpieza en Redis son responsabilidad del backend; TTL
  propuesto ≥ 15 min y resultado recuperable tras reconexión.

---

## 6. Límites de plataforma y riesgos (cada dato con su URL oficial)

### 6.1 Matriz Vercel — plan Hobby (todo citado)

Consultado el 2026-11-01. Páginas con fecha de actualización oficial indicada por Vercel.

| Tema | Dato oficial | Fuente |
|---|---|---|
| Uso comercial | «Hobby teams are restricted to non-commercial personal use only. All commercial usage of the platform requires either a Pro or Enterprise plan.» | [Fair Use Guidelines → Commercial usage](https://vercel.com/docs/limits/fair-use-guidelines#commercial-usage) |
| DPA (encargado del tratamiento) | El DPA «applies to Vercel's Processing of Personal Data as a Processor under the Agreement for Customers who are on Enterprise and Pro plans.» → **Hobby no tiene DPA** | [Vercel DPA](https://vercel.com/legal/dpa) |
| Transferencia de datos (Fast Data Transfer) | primeros **100 GB/mes** incluidos | [Hobby Plan](https://vercel.com/docs/plans/hobby) |
| Fast Origin Transfer | primeros **10 GB/mes** | [Hobby Plan](https://vercel.com/docs/plans/hobby) |
| Despliegues | **100/día**, 1 build concurrente | [Plans → Hobby](https://vercel.com/docs/plans/hobby), [Limits → General](https://vercel.com/docs/limits#general-limits) |
| Duración máxima de función | **300 s** (por defecto y máximo en Hobby) | [Functions limits → Max duration](https://vercel.com/docs/functions/limitations#max-duration) |
| Memoria de función | **2 GB / 1 vCPU** máximo en Hobby | [Functions limits → Memory](https://vercel.com/docs/functions/limitations#memory-size-limits) |
| Cuerpo de petición/respuesta de función | **4,5 MB** (413 `FUNCTION_PAYLOAD_TOO_LARGE`) | [Functions limits → Request body size](https://vercel.com/docs/functions/limitations#request-body-size) |
| Timeout de proxy externo (rewrites) | **120 s**; si el origen no responde: `ROUTER_EXTERNAL_TARGET_ERROR` | [Limits → Proxied request timeout](https://vercel.com/docs/limits#proxied-request-timeout) |
| Regiones de función | Hobby: **una sola región**; Pro: 5; Enterprise: todas | [Configuring regions → Limits](https://vercel.com/docs/functions/configuring-functions/region#limits) |
| `fra1` (Frankfurt) disponible | sí | [Regions → Region list](https://vercel.com/docs/regions#region-list) |
| Logs de runtime | **1 hora** de retención en Hobby | [Limits → Logs](https://vercel.com/docs/limits#logs) |
| Si se exceden límites | «you will have to wait until 30 days have passed before you can use the feature again» | [Hobby Plan → billing cycle](https://vercel.com/docs/plans/hobby) |
| Rewrites externos: comportamiento | no cambian la URL del navegador; reenvían `x-real-ip`/`x-forwarded-*`; por defecto (proyectos nuevos) **respetan `cache-control` del origen** | [Rewrites → external origins](https://vercel.com/docs/routing/rewrites#rewrites-to-external-origins) |
| Rewrites externos: restringir origen a tráfico de Vercel | patrón oficial con `routes` + secreto `x-origin-secret` | [Rewrites → restricting your origin](https://vercel.com/docs/routing/rewrites#restricting-your-origin-to-vercel-traffic) |
| Rollback Vercel (Hobby) | Instant Rollback; en Hobby solo al **despliegue inmediatamente anterior** | [Instant Rollback](https://vercel.com/docs/instant-rollback) |

Cómo se aplica en este diseño:

- **`regions: ["fra1"]`** en `vercel.json` (Frankfurt): una región es lo máximo de
  Hobby; `fra1` está en la lista oficial. No hay multi-región ni failover.
- **120 s de proxy** es el techo de `/api/*`: por eso IA es asíncrona y SSE no pasa
  por Vercel. 300 s de función no ayudan al rewrite externo.
- **4,5 MB** es la razón de que media/subidas grandes vayan directas a
  `api.<dominio>` con URL firmada; no se puede subir una radiografía de 8 MB por
  `/api`.
- **Caché de rewrites externos**: `vercel.json` fuerza `x-vercel-enable-rewrite-caching: 0`
  y `Cache-Control: no-store` en `/api/*` para que respuestas autenticadas no
  queden cacheadas en el CDN (Vercel, por defecto en proyectos nuevos, respeta el
  `cache-control` del origen; aun así se explicita).
- **Logs de 1 h**: insuficientes como registro de auditoría/incidentes. Ver §10.4.

### 6.2 Registro de riesgo aceptado: Vercel Hobby (BLOQUEO DE REVISIÓN)

**Decisión del propietario (por escrito):** usar Vercel **plan Hobby** para el
staging. Este documento no reabre la decisión; registra el riesgo y sus
consecuencias, y la somete a **revisión obligatoria antes del corte a producción**.

**ADR de referencia (ya existe):** [ADR-001 — Riesgo aceptado: frontend en Vercel
con plan Hobby](../decisiones/ADR-001-riesgo-vercel-hobby.md). Este documento y el
ADR se complementan: el ADR registra la decisión y las condiciones de contención
del propietario; aquí están los detalles técnicos y las citas. Si hay conflicto,
**manda el ADR** y hay que corregir este documento. Las condiciones 1-3 del ADR
(media/SSE fuera de Vercel, nada cacheado, datos sintéticos) son exactamente lo que
implementa este diseño (§5.2, §5.3, `vercel.json` con `no-store` y §7.2.1); la 4
(IA asíncrona por el timeout de 120 s) está en §5.4.

> **Discrepancia conocida con el ADR (no editado aquí)**: el ADR-001 habla de «ticket
> de un solo uso» para SSE, pero el diseño vigente es un **token firmado de corta
> vida y reutilizable** (§5.3): `EventSource` reconecta solo y un ticket de un solo
> uso lo dejaría en 401. Queda apuntado para que el Lead corrija el ADR.

| # | Riesgo | Consecuencia concreta | Evidencia oficial |
|---|---|---|---|
| H-1 | El plan Hobby **prohíbe el uso comercial**; una clínica dental que cobra servicios lo es | Vercel puede pausar/cerrar el despliegue y la cuenta; pérdida de servicio del frontend sin SLA | [Fair Use → Commercial usage](https://vercel.com/docs/limits/fair-use-guidelines#commercial-usage) |
| H-2 | **No hay DPA** en Hobby | No existe contrato de encargado del tratamiento con Vercel; con datos de salud (categoría especial, art. 9 RGPD) y datos de pacientes esto es un problema legal, no solo de plataforma | [DPA](https://vercel.com/legal/dpa) · [RGPD](https://eur-lex.europa.eu/eli/reg/2016/679/oj) |
| H-3 | Sin soporte de plataforma en Hobby (solo Pro/Enterprise tienen email support) | incidencias del frontend se resuelven sin canal de soporte | [Hobby Plan](https://vercel.com/docs/plans/hobby) |
| H-4 | Timeout de proxy **120 s** | cualquier endpoint `/api/*` >120 s falla; IA ya es asíncrona | [Limits](https://vercel.com/docs/limits#proxied-request-timeout) |
| H-5 | Cuerpo de función **4,5 MB** | subidas grandes directas al origen (ya diseñado así) | [Functions limits](https://vercel.com/docs/functions/limitations#request-body-size) |
| H-6 | Región única, sin failover multi-región | una caída de `fra1` afecta al frontend (el CDN sirve estáticos; funciones no) | [Regions](https://vercel.com/docs/regions) · [Region limits](https://vercel.com/docs/functions/configuring-functions/region#limits) |
| H-7 | Límites de uso (100 GB transferencia, 10 GB origin, 100 deploys/día) y pausa de 30 días al exceder | durante una campaña o pico de uso la web puede quedar limitada | [Hobby Plan](https://vercel.com/docs/plans/hobby) |
| H-8 | Logs de runtime 1 h | sin trazabilidad de incidentes más allá de 1 h | [Limits → Logs](https://vercel.com/docs/limits#logs) |
| H-9 | Instant Rollback en Hobby solo al despliegue inmediatamente anterior | si se encadenan dos deploys malos, no se puede volver a uno anterior desde la UI; mitigación: `vercel promote` a un deployment concreto (requiere conservarlo) | [Instant Rollback](https://vercel.com/docs/instant-rollback) |

**Mitigaciones obligatorias mientras se use Hobby:**

1. **Staging y previews con datos sintéticos; nunca datos reales de pacientes**
   (condición 3 del ADR-001). Si se necesita un espejo con datos reales, no puede
   vivir en Hobby: exige Pro con DPA + base legal.
2. **No usar Hobby para producción.** El corte a producción queda condicionado a
   plan Pro (o Enterprise) **con DPA firmado**, o a mover el frontend a otro
   proveedor con DPA.
3. Aceptar por escrito que una pausa de cuenta por uso comercial puede tumbar el
   staging sin previo aviso; el propietario lo ha aceptado.
4. Revisión en el punto de corte: revalidar precios, condiciones y límites en la
   fecha (los documentos citados son de 2026 y pueden cambiar).
5. Vigilar el uso en el dashboard (transferencia/origin) y mantener el frontend
   estático lo más cacheable posible.

**Qué cambia al pasar a Pro** (según la documentación citada): el DPA pasa a
aplicar ([DPA](https://vercel.com/legal/dpa)); uso comercial permitido
([Fair Use](https://vercel.com/docs/limits/fair-use-guidelines#commercial-usage));
más regiones y despliegues; soporte por email; Instant Rollback a más despliegues.
El timeout de proxy de 120 s **sigue igual** ([Limits](https://vercel.com/docs/limits#proxied-request-timeout)),
así que el diseño asíncrono de IA y el SSE directo se mantienen con Pro.

### 6.3 Matriz Oracle Cloud — Always Free (todo citado)

| Tema | Dato oficial | Fuente |
|---|---|---|
| AMD micro | hasta **2** instancias `VM.Standard.E2.1.Micro` (1/8 OCPU, **1 GB** RAM, ~50 Mbps) | [Always Free Resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) |
| ARM Ampere A1 | **1.500 OCPU-hora + 9.000 GB-hora al mes**; «For Always Free tenancies, this is equivalent to **2 OCPUs and 12 GB of memory**» | [Always Free Resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) |
| A1 reparto | se puede usar en una instancia o repartir hasta 2 | [Always Free Resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) |
| Disco | **200 GB** de block volume combinados (boot 50 GB por defecto) | idem |
| Salida a internet | **10 TB/mes** de outbound | idem (`Additional Services → Outbound Data Transfer`) |
| Región | los recursos Always Free deben crearse en la **home region**; las tenencias free/trial están limitadas a **una región suscrita** | [Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) · [Regions → Subscribed Region Limits](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm) |
| Regiones UE disponibles | identificadores en la lista oficial: `eu-madrid-1`, `eu-madrid-3`, `eu-frankfurt-1`, `eu-amsterdam-1`, `eu-paris-1`, `eu-marseille-1`, `eu-milan-1`, `eu-turin-1`, `eu-stockholm-1`, `eu-zurich-1`, `uk-london-1`, `uk-cardiff-1` | [Regions and Availability Domains](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm) |
| Capacidad A1 | puede fallar con «out of host capacity»; el propio doc sugiere otro availability domain, esperar, o el upgrade a Pay As You Go | [Always Free Resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) |
| Reclamación de inactivas | Oracle puede reclamar instancias Always Free si **durante 7 días**: CPU 95th percentile < **20%**, red < **20%**, y memoria < **20%** (A1) | [Always Free Resources → Idle Compute Instances](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) |
| Upgrade a PAYG | «Oracle doesn't charge for Always Free resources after you upgrade»; solo se paga lo que exceda | idem |
| Firewall de red | Security List del VCN (capa de red) además del firewall del SO; por defecto solo SSH | [Security Lists](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securitylists.htm) |
| Imágenes arm64 | Ubuntu está entre las imágenes Always Free-eligible para A1 | [Always Free Resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) |

**Elección**: A1.Flex (ARM, 2 OCPU/12 GB) y no las micro AMD (1 GB es insuficiente
para Postgres+Redis+API+Evolution+Caddy). Con 12 GB hay margen para la pila y para
un `pg_dump`; el disco por defecto de 50 GB entra en los 200 GB.

**Riesgo de reclamación por inactividad** (importante para una clínica: la API
puede no tener carga 7 días):

- Los umbrales son **percentiles 95** durante 7 días; el tráfico normal de una
  clínica pequeña probablemente no los supera. **No se puede garantizar** que
  Oracle no reclame la instancia.
- Mitigaciones: (a) copias **fuera del host** (§9) para poder reconstruir; (b)
  `bootstrap-oracle.sh` reconstruye desde cero de forma idempotente; (c) valorar
  upgrade a Pay As You Go (los Always Free siguen gratis y evita la reclamación de
  inactivas como cuenta free) — decisión del propietario, no tomada aquí.
- **NO VALIDADO**: no se ha comprobado en una cuenta real si esta carga concreta
  supera o no los umbrales, ni si Oracle ha reclamado alguna vez esta instancia.

### 6.4 Imágenes arm64: comprobado contra el registry (no supuesto)

Consulta ejecutada el 2026-11-01 contra la API pública de Docker Hub
(`https://hub.docker.com/v2/repositories/<repo>/tags/<tag>`), campo `images[].architecture`:

| Imagen | Tag | amd64 | arm64/v8 | Fecha tag |
|---|---|---|---|---|
| `postgres` | `16.14` | sí | **sí** | 2026-08-05 |
| `redis` | `7.4-alpine` | sí | **sí** | 2026-10-29 |
| `caddy` | `2.11.7-alpine` | sí | **sí** | 2026-10-30 |
| `evoapicloud/evolution-api` | `v2.3.7` | sí | **sí** | 2025-12-05 |
| `evoapicloud/evolution-api` | `latest` | sí | sí | 2026-05-06 (apunta a `2.4.0-rc1`, RC → **no se usa**) |

Páginas humanas: [postgres](https://hub.docker.com/_/postgres), [redis](https://hub.docker.com/_/redis),
[caddy](https://hub.docker.com/_/caddy), [evolution-api tags](https://hub.docker.com/r/evoapicloud/evolution-api/tags).

**No validado**: que el manifest arm64 *funcione* en la instancia (arranque real,
sesión de WhatsApp de Evolution). Eso se comprueba en el primer despliegue (§7.5).
Se han **fijado las versiones menores**: `postgres:16.14` y `redis:7.4-alpine`
(antes eran `postgres:16`/`redis:7-alpine`, tags flotantes de minor). Caddy y
Evolution ya estaban fijados a versión completa. Para producción, fijar además el
digest (`image: postgres:16.14@sha256:...`).

---

## 7. Procedimiento de despliegue (un tercero, sin preguntar)

### 7.0 Prerrequisitos

- Cuenta Oracle Cloud con Always Free disponible y una instancia A1 Ubuntu 22.04/24.04
  **arm64** con IP pública.
- Dominio con capacidad de crear registros DNS (`staging` y `api.staging`).
- Cuenta Vercel (Hobby) con acceso al repo de Git.
- Repo en GitHub con permiso para publicar paquetes en GHCR.
- Par de claves SSH para el usuario de despliegue (la privada en GitHub Secrets).
- Un destino de backup fuera del servidor (SSH+rsync).

### 7.1 Orden correcto (no saltarse pasos)

1. Crear la instancia Oracle y abrir red (§7.3.1).
2. Ejecutar `bootstrap-oracle.sh` **con `--skip-pull`** (§7.3.2), pasándole
   `--ghcr-user`, `--admin-cidr` y `--ssh-pubkey` (clave pública de CI). Deja
   servidor, Docker, sudo acotado, SSH endurecido, dirs, secretos, claves de backup
   y timer listos sin necesitar imagen. (Sin `--skip-pull`, si la imagen aún no
   existe avisa y sigue; no es fatal, pero la pila no arranca todavía.)
3. Publicar la primera imagen en GHCR (push a `staging-*` con el workflow, o build
   manual §7.3.4).
4. Arrancar la pila: `cd /opt/makingsmiles && sudo docker compose pull && sudo docker compose up -d`
   (o re-ejecutar el bootstrap; es idempotente y no toca el `.env` existente).
5. Apuntar `api.staging.<dominio>` a la IP y reiniciar Caddy para el certificado.
6. Configurar Vercel + `vercel.json`/`frontend/vercel.json` + dominio
   `staging.<dominio>` (§7.2).
7. Smoke tests (§7.5).
8. **Activar el backup offsite** (clave pública SSH en el host de backups,
   `known_hosts` verificado, `BACKUP_DEST`, `BACKUP_OFFSITE_REQUIRED=1`) y probar
   copia + restauración en seco (§9). Hasta entonces el timer falla a propósito.

### 7.2 Vercel (frontend)

1. **Crear proyecto**: Vercel → Add New → Project → importar el repo.
   - *Root Directory*: `frontend/`
   - *Framework Preset*: Next.js (autodetectado)
   - *Build Command* / *Output*: los de Next por defecto.
2. **Sustituir el placeholder de dominio en los DOS `vercel.json`** (raíz y
   `frontend/`), manteniéndolos idénticos. Ya están creados ambos; no hay que
   copiar nada, solo sustituir el placeholder (§7.2.1). El operativo para Vercel es
   `frontend/vercel.json` (Root Directory = `frontend/`); el de la raíz es la
   referencia canónica y lo que valida el gate. Las **5 apariciones** del
   placeholder en cada fichero son: `rewrites[0].destination` y las 4 de la CSP
   (`img-src`, `media-src`, y `connect-src` que lleva `https://` **y** `wss://`).
   Si se olvida, el rewrite apunta a `api.staging.example.com` y **todo `/api/*`
   falla**.

#### 7.2.1 Placeholders → valores a sustituir

No hay dominio definitivo en el repo: estos son los placeholders y dónde se
sustituyen. En la prosa de este documento, `<dominio>` equivale a `example.com`.

| Placeholder literal | Dónde aparece | Sustituir por |
|---|---|---|
| `api.staging.example.com` | `frontend/vercel.json` (5), `vercel.json` (5), `deploy/oracle/env.example` (`API_DOMAIN`, `PUBLIC_API_URL`), `deploy/oracle/bootstrap-oracle.sh` (ejemplo de uso) | host real de la API: `api.staging.<dominio-real>` |
| `staging.example.com` | `deploy/oracle/env.example` (`APP_DOMAIN`) y **dominio del proyecto en Vercel** (se añade en el dashboard, no en un fichero) | host real del frontend: `staging.<dominio-real>` |
| `example.com` | `deploy/oracle/env.example` (`DOMAIN`) | dominio raíz real |
| `ops@example.com` | `deploy/oracle/env.example` (`ACME_EMAIL`) | email real para Let's Encrypt |
| `OWNER` | `deploy/oracle/env.example` (`API_IMAGE`: `ghcr.io/OWNER/...`) | owner/organización de GitHub del repo |
| `makingsmiles` | usuario/BD en `env.example` y compose | opcional: se puede mantener |

Comandos (desde la raíz del repo; sustituye `<API_HOST>`, `<APP_HOST>` y `<DOMAIN>`
por los valores reales). Se hace en los dos ficheros y se comprueba con el gate:

```bash
API_HOST=api.staging.<DOMINIO_REAL>
sed -i "s/api\.staging\.example\.com/${API_HOST}/g" vercel.json frontend/vercel.json
grep -o "${API_HOST}" frontend/vercel.json | wc -l    # debe dar 5
python3 -c "import json; a=json.load(open('vercel.json')); b=json.load(open('frontend/vercel.json')); assert a==b; print('idénticos')"
```

El dominio de la app (`<APP_HOST>`) **no** está en `vercel.json`: se añade en
Vercel → Settings → Domains (§7.2 paso 4) y, para el `.env` de Oracle, como
`APP_DOMAIN`/`--app-domain`. El gate de CI comprueba también que ambos
`vercel.json` son idénticos, para que no se sustituya uno y el otro no.
3. **Variables de entorno del proyecto Vercel**: el frontend usa rutas relativas
   `/api`; no necesita la URL de la API en build. Si el frente de frontend define
   `NEXT_PUBLIC_API_BASE`, debe ser `/api` (nunca la URL absoluta de Oracle, o se
   rompe la cookie first-party). *No hay secretos de backend en Vercel.*
4. **Dominio**: Project → Settings → Domains → añadir `staging.<dominio>` y seguir
   las instrucciones de DNS de Vercel (registro que indique el dashboard)
   ([dominios](https://vercel.com/docs/domains)). El TLS del frontend lo gestiona
   Vercel.
5. **Rama de producción**: Settings → Git → Production Branch = rama de staging
   (p. ej. `rebuild/vercel-oracle` o una `staging`). Cada push a esa rama despliega.
   Los *preview deployments* también usarán el rewrite literal al **mismo** API de
   staging: aceptable en staging; si molestara, activar Deployment Protection.
6. **Verificar** (sustituye el dominio):

   ```bash
   curl -sS -o /dev/null -w '%{http_code}\n' https://staging.<dominio>/
   curl -sS https://staging.<dominio>/api/health/db          # JSON de la API vía rewrite
   curl -sSI https://staging.<dominio>/ | grep -Ei 'cross-origin-(opener|embedder)|content-security'
   ```

   Si `/api/health/db` devuelve 404 de Next en vez de JSON de la API, el
   `vercel.json` no está en la raíz del proyecto o el dominio no está bien sustituido.
7. **Rollback Vercel**: Deployments → Instant Rollback (Hobby: solo el anterior) o
   promover un deployment concreto ([Instant Rollback](https://vercel.com/docs/instant-rollback)).
   No requiere tocar Oracle.

**Por qué `vercel.json` y no `next.config`**: ver §2.3. Además, el frente de
frontend no debe duplicar estas cabeceras en `next.config.ts`: dos fuentes de
verdad para CSP/COOP/COEP acaban divergiendo. Este `vercel.json` es la única.

### 7.3 Oracle (API)

#### 7.3.1 Crear instancia y red

1. OCI Console → Compute → Instances → Create. Shape `VM.Standard.A1.Flex`
   (2 OCPU / 12 GB si hay capacidad; si da «out of host capacity», probar otro AD o
   esperar). Imagen **Ubuntu 22.04/24.04 (arm64)**. Boot volume 50-100 GB. IP pública.
2. VCN → Security List → **añadir ingress**: TCP 80 `0.0.0.0/0`, TCP 443
   `0.0.0.0/0`, y SSH 22 solo desde la IP del administrador. La Security List es un
   firewall de red **independiente** de `ufw` ([Security Lists](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securitylists.htm)).
3. DNS: `api.staging.<dominio>` → IP pública (registro A). Comprobar `dig +short`.
4. SSH con clave (nunca contraseña) y `sudo`.

#### 7.3.2 Bootstrap

Desde un checkout del repo **en el servidor** (o copiando `deploy/oracle/` por scp),
como root. El token de GHCR va **por entorno o stdin, nunca por argumento** (argv es
visible en `ps`/historial):

```bash
export GHCR_TOKEN='...'   # PAT con read:packages; o haz docker login a mano
sudo -E bash deploy/oracle/bootstrap-oracle.sh \
  --domain <dominio> \
  --app-domain staging.<dominio> \
  --api-domain api.staging.<dominio> \
  --email ops@<dominio> \
  --ghcr-user <usuario-github> \
  --admin-cidr <IP-admin>/32 \
  --ssh-pubkey /root/clave-ci.pub \
  --skip-pull
```

Qué hace (idempotente; no cambia SSH si no le pasas clave pública, para no dejarte
fuera):

- instala Docker Engine + Compose plugin desde el repo oficial y paquetes base
  (incluye `age` para cifrar backups);
- crea el usuario de despliegue **SIN añadirlo al grupo `docker`** (el grupo docker
  equivale a root) y le permite **solo** `sudo /usr/local/sbin/makingsmiles-deploy`
  (wrapper root con acciones fijas deploy/rollback/reload-caddy/check-evolution/
  backup-dry-run; valida la referencia de imagen). El wrapper ejecuta **copias
  root-owned** de los scripts en `/usr/local/lib/makingsmiles`, no las de
  `/opt/makingsmiles` (escribibles por el usuario de deploy): si los scripts cambian
  en el repo, un admin debe reinstalarlos (re-ejecutar bootstrap);
- `ufw` (80/443; **22 solo desde `--admin-cidr`**, o la IP de la sesión SSH), fail2ban,
  unattended-upgrades;
- endurece SSH (`PermitRootLogin no`, `PasswordAuthentication no`) **solo** si
  instala una clave pública, con `sshd -t` previo y reversión si no valida;
- copia la pila a `/opt/makingsmiles` (media owner 1001; `.ssh` y `backups` root 0700);
- genera `/opt/makingsmiles/.env` **root 600** con secretos aleatorios y
  `umask 077`, sustituyendo placeholders; `validate-env.sh` debe **rechazar** la
  plantilla y **aceptar** el `.env` generado (autotest en el bootstrap);
- genera pares de claves de backup SSH ed25519 y `age`; imprime la clave pública SSH
  (para instalarla en el host de backups) y deja la privada `age` en el servidor
  (hay que custodiarla fuera);
- instala y activa `makingsmiles-backup.timer` (diario 03:15 + retardo) que corre
  como **root** (el `.env` es root 600);
- `docker compose pull` + `up -d` (si falta imagen, avisa y sigue), espera a
  `/health/db`, y ejecuta como root `backup-postgres.sh --dry-run` (prueba de
  lock/permisos con el mismo usuario que el timer) y `check-evolution.sh`.

Activar el offsite después (obligatorio antes de producción): instalar
`/opt/makingsmiles/.ssh/backup_key.pub` en el host de backups, fijar
`known_hosts` (`ssh-keyscan -H <host> > /opt/makingsmiles/.ssh/known_hosts` y
**verificar la huella**), rellenar `BACKUP_DEST` y `BACKUP_OFFSITE_REQUIRED=1` en
`.env` (el bootstrap lo deja a 0 para no fallar el timer el primer día), y hacer:

```bash
sudo /usr/local/sbin/makingsmiles-deploy backup-dry-run
sudo /opt/makingsmiles/backup-postgres.sh
sudo /opt/makingsmiles/backup-postgres.sh --verify
sudo /opt/makingsmiles/restore-postgres.sh --scratch --dump <último dump>
```

**Residual asumido:** el usuario de deploy puede escribir los ficheros de
`/opt/makingsmiles` (los rsyncea CI). No tiene docker ni shell root, pero podría
alterar el compose y disparar el wrapper. Para producción, valorar mover
`/opt/makingsmiles` a root y hacer el rsync por el wrapper (deuda D-10).


#### 7.3.3 Verificación de la instancia

```bash
cd /opt/makingsmiles
docker compose ps                                   # todos running/healthy
docker compose exec -T api curl -fsS http://127.0.0.1:8000/health/db
curl -fsS https://api.staging.<dominio>/health/db   # tras TLS
ss -ltnp | grep -E ':(80|443|5432|6379|8080)\b'     # solo 80/443 deben estar a la escucha
```

Si `ss` muestra 5432/6379/8080 escuchando en 0.0.0.0, **para**: hay un puerto
publicado y la pila no está como este compose.

#### 7.3.4 Primera imagen (antes de que exista CI o para probar)

```bash
# en un equipo con Docker (o en el servidor, si tiene el repo):
docker build -f deploy/backend.Dockerfile -t ghcr.io/<owner>/<repo>-api:local ./backend
docker tag ... && docker push ...   # si el paquete es privado, login previo
# en el servidor:
cd /opt/makingsmiles && ./deploy-staging.sh ghcr.io/<owner>/<repo>-api:local --reload-caddy
```

### 7.4 CI/CD de la API (`.github/workflows/deploy-oracle.yml`)

Disparadores: push de tags `staging-*` o `workflow_dispatch` (`action=deploy|rollback`).

| Job | Qué hace |
|---|---|
| `gate` | parsea YAML/JSON, comprueba placeholders, valida **`env.example` contra las variables que interpola compose**, ejecuta `validate-env.sh` dos veces (debe rechazar la plantilla y aceptar un env relleno), y corre `scripts/deploy-gate.sh`. Si falla, no hay build ni deploy. |
| `build` | imagen `linux/arm64` desde `./backend` con `deploy/backend.Dockerfile`; push a GHCR con `:<sha>` y `:staging`. |
| `deploy` | rsync de config/scripts (nunca `.env`); SSH; **`sudo /usr/local/sbin/makingsmiles-deploy deploy <imagen>`** (wrapper root acotado, que a su vez corre `deploy-staging.sh --reload-caddy`); smoke público opcional; comprobación **no bloqueante** de sesión WhatsApp (`check-evolution`). |
| `rollback` | **sin `needs: gate`** (emergencia): SSH + wrapper `rollback`, sin build ni gate. |

Secretos por **environment** `staging` (nunca en el repo): `DEPLOY_HOST`,
`DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_PORT`, `DEPLOY_KNOWN_HOSTS` (opcional;
mejor fijarlo), `STAGING_API_URL` (opcional).

Seguridad del workflow:
- **Ningún `${{ ... }}` dentro de un `run:`**: `image_tag` (input de usuario) entra
  por `env:` y se valida con `^[A-Za-z0-9._-]+$` antes de formar la referencia; la
  referencia final también se valida contra
  `^ghcr\.io/[a-z0-9][a-z0-9._/\-]*:[A-Za-z0-9._-]+$`. Así no hay inyección de shell.
- El usuario de deploy no tiene docker: solo puede ejecutar el wrapper por sudo.

El gate usa un `.env` **efímero** en el runner con 12 marcadores literales porque
`scripts/deploy-gate.sh` exige que existan (solo comprueba presencia); no son
secretos y el runner es efímero. Es una limitación del gate legacy: no valida
valores reales, por eso se añade `validate-env.sh` para el `.env` nuevo.

GHCR: `GITHUB_TOKEN` con `packages: write`
([GHCR](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)).
El servidor hace `pull` como root (el wrapper), así que el login del bootstrap
(`/root/.docker`) es el que se usa.


### 7.5 Smoke tests mínimos tras el primer despliegue

```bash
# frontend y rewrite
curl -fsS -o /dev/null -w '%{http_code}\n' https://staging.<dominio>/
curl -fsS https://staging.<dominio>/api/health/db
# API directa y TLS
curl -fsS https://api.staging.<dominio>/health/db
echo | openssl s_client -connect api.staging.<dominio>:443 -servername api.staging.<dominio> 2>/dev/null | openssl x509 -noout -dates
# media cross-origin (necesita una URL firmada real de la API)
#   curl -sSI 'https://api.staging.<dominio>/media/<ruta>?exp=...&sig=...' | grep -i cross-origin-resource-policy
# SSE (necesita token real): abrir en DevTools > Network > EventSource y comprobar que NO aparece staging.<dominio>/events
#   y que la conexión es a api.staging.<dominio> y permanece abierta > 120 s
#   (y que al reconectar el mismo token sigue valiendo hasta su caducidad)
# cookie first-party: DevTools > Application > Cookies > staging.<dominio> (HttpOnly, Secure, SameSite=Lax)
```

Comprobaciones de navegador que **solo se pueden hacer en un navegador real** y que
están en §13: COEP+media (CORP), SSE >120 s, cookies cross-origin (no usadas), y
`EventSource` bajo COEP.

---

## 8. Rollback

### 8.1 API (Oracle): automático y manual

El estado vive en `/opt/makingsmiles/.deploy/` con **dos slots + historial**:

- `current_image` — imagen que está sirviendo.
- `previous_image` — imagen anterior **sana** (destino de `--rollback`).
- `history.log` — una línea por operación (acción, from, to, resultado).

**El estado solo se escribe tras un healthcheck correcto.** Si la imagen nueva falla,
se vuelve sola a `current_image` y `previous_image` **no se toca**. En `--rollback`
tampoco se pisa `previous_image` antes de aplicar: si el rollback va bien, se
intercambian los slots (previous pasa a ser la que se acaba de dejar). Esto corrige
el bug de la versión anterior, que guardaba la imagen mala como «anterior» y hacía
que un segundo rollback volviera a desplegarla.

```bash
cd /opt/makingsmiles
sudo /usr/local/sbin/makingsmiles-deploy deploy ghcr.io/<owner>/<repo>-api:<sha>
# o a mano como root:
./deploy-staging.sh --dry-run                 # enseña current/previous/objetivo, sin cambios
./deploy-staging.sh --dry-run --rollback      # ídem para rollback (prueba en seco)
./deploy-staging.sh --rollback --reload-caddy # rollback real
docker compose ps && docker compose exec -T api curl -fsS http://127.0.0.1:8000/health/db
cat .deploy/current_image .deploy/previous_image
```

Estados esperados:
- `--dry-run --rollback` con `previous_image: <ninguna>` → no hay nada a lo que
  volver (solo ha habido un deploy). Informativo, no error.
- Rollback real correcto → `health OK tras Ns` y `OK: <imagen>`; los slots quedan
  intercambiados.
- Rollback real incorrecto (la anterior también está rota) → intenta restaurar la
  que estaba sirviendo; si tampoco, error y `history.log` lo registra. Entonces toca
  desplegar una imagen conocida buena o restaurar BD (§9).

Caddy: `--reload-caddy` valida el Caddyfile antes de aplicar; si es inválido, Caddy
mantiene la configuración anterior (no se cae el TLS). Es comportamiento de Caddy,
no se ha podido ejecutar aquí (§13).


### 8.2 Frontend (Vercel)

Dashboard → Project → Deployments → **Instant Rollback** al deployment anterior
(en Hobby solo el inmediatamente anterior; para otro, `vercel promote <deployment>`).
Efectos documentados: Vercel considera el deployment restaurado como versión del
anterior, no actualiza variables de entorno, y **desactiva la auto-asignación del
dominio de producción** hasta que se promueva otro deployment o se haga "Undo
Rollback" ([Instant Rollback](https://vercel.com/docs/instant-rollback)). Hay que
recordarlo tras un rollback de Vercel: los pushes nuevos no sustituyen al
rolled-back hasta deshacerlo.

### 8.3 Base de datos

No hay rollback automático de esquema. Dos caminos:

1. **Restaurar copia** (§9): es el único probado/documentado aquí; vuelve al estado
   del dump (se pierde lo escrito desde entonces).
2. **Migración inversa**: no existe en este rebuild; el arranque usa
   `init_db()` (crea lo que falta). **Deuda**: antes de tocar esquema en producción
   hace falta estrategia de migraciones (Alembic u equivalente) y probar
   forward/backward. Ver §11.

### 8.4 Qué significa "rollback probado en seco" aquí

En este entorno **no** se ha podido ejecutar un rollback ni una restauración reales
(no hay daemon Docker, §13). Lo que hay es:

- procedimiento escrito y scripts con `--dry-run`;
- `bash -n` de todos los scripts (sintaxis);
- el rollback automático **implementado** y conectado al healthcheck (revisado a
  mano, no ejecutado);
- un test de aceptación explícito para el **primer** despliegue de staging (§8.5).

### 8.5 Test de aceptación del rollback (hacer en el primer staging)

```bash
cd /opt/makingsmiles
./deploy-staging.sh --dry-run
./deploy-staging.sh --dry-run --rollback
./backup-postgres.sh --dry-run && ./backup-postgres.sh
./backup-postgres.sh --verify
./restore-postgres.sh --dump "$(ls -1t backups/makingsmiles-db-*.dump | head -1)" --scratch
# y un rollback real controlado: desplegar una imagen buena, luego:
./deploy-staging.sh --rollback
```
Anotar en el registro del deploy: hora, imagen, resultado de health y de restore
scratch. Sin esto, "rollback probado" es solo una intención.

## 9. Copias de seguridad y restauración

### 9.1 Qué se copia y cómo

| Dato | Cómo | Fichero |
|---|---|---|
| BD de la app | `pg_dump -Fc` (custom, comprimido) | `makingsmiles-db-<UTC>.dump` |
| BD de Evolution | `pg_dump -Fc` (si existe) | `makingsmiles-evolution-<UTC>.dump` |
| Roles/globals | `pg_dumpall --globals-only` | `makingsmiles-globals-<UTC>.sql` |
| Media (radiografías/documentos) | `tar -czf` de `/app/media` (bind mount `./media`); **si `BACKUP_MEDIA=1` y falla, la copia es FALLO** | `makingsmiles-media-<UTC>.tar.gz` |
| Integridad | `sha256sum` por fichero | `<fichero>.sha256` |
| Cifrado para offsite | `age -r <BACKUP_AGE_RECIPIENT>` de cada fichero | `offsite/<fichero>.age` |

`backup-postgres.sh` corre como **root** (servicio systemd `makingsmiles-backup`,
diario 03:15 + retardo; el `.env` es root 600), con `flock` en
`/opt/makingsmiles/.deploy/backup.lock` (antes estaba en `/run`, root:root, y el
timer no-root fallaba antes de `pg_dump`: corregido). Retención local
(`BACKUP_RETENTION_DAYS`, 14 por defecto) y copia **fuera del host** con `rsync`
sobre SSH:
- clave dedicada `/opt/makingsmiles/.ssh/backup_key` (root 600), **no** una ruta
  bajo `/etc/makingsmiles` 0700 root ilegible por el usuario del timer (bug corregido);
- `known_hosts` **fijado** y verificado (`StrictHostKeyChecking=yes`); no se usa
  `accept-new`;
- **cifrado en reposo con `age` ANTES de salir del host** (obligatorio si el
  offsite es obligatorio); la copia local puede quedar en claro para restaurar;
- `rsync --delete` sobre un **directorio remoto dedicado**
  (`BACKUP_DEST=/srv/backups/makingsmiles-staging`), para que la retención se
  espeje; no apuntar a un directorio compartido con otras cosas.

Cada copia se **verifica antes de salir 0**: checksum + `pg_restore --list` de la
BD principal y de Evolution, y `globals` no vacío. Si `BACKUP_OFFSITE_REQUIRED=1` y
falla el offsite (o el tar de media), sale **2/1** y systemd marca el servicio
`failed`: es intencionado.

El `.env` (secretos) **no** se copia con este script a propósito; el bootstrap
avisa. Sin `SECRET_KEY`, una restauración de BD deja tokens/credenciales inválidos.
La clave privada `age` (`/opt/makingsmiles/.ssh/age.key`) debe custodiarse **fuera
del servidor**: sin ella no se pueden descifrar las copias offsite.

### 9.2 RPO/RTO (honesto)

- **RPO**: hasta ~24 h (timer diario), con verificación y cifrado; si se necesita
  menos, bajar el intervalo o copiar antes de operaciones arriesgadas.
- **RTO**: **no medido**. Depende del tamaño de la BD/media y de la instancia.
  Medirlo en el primer restore completo y anotarlo aquí.

### 9.3 Restauración

**Prueba en seco REAL** — restaura app + evolution en bases temporales, con
`ANALYZE` y `count(*)` de tablas clave (no `n_live_tup`, que es 0 sin analizar),
valida globals y media en frío, y borra las bases temporales:

```bash
cd /opt/makingsmiles
./restore-postgres.sh --scratch --dump "$(ls -1t backups/makingsmiles-db-*.dump | head -1)"
```

Comprobaciones que hace (y que antes no hacía): exige el `.sha256` del dump;
restaura con `--exit-on-error`; `ANALYZE`; exige que existan y tengan filas las
tablas clave `usuarios pacientes citas consentimientos` (configurable con
`RESTORE_KEY_TABLES`); valida el dump de evolution (checksum, `pg_restore --list`,
restauración y tablas >0); valida `globals` (`CREATE/ALTER ROLE`); valida el tar de
media (checksum + listado + no vacío). Autodetecta los ficheros hermanos por
timestamp.

**Restauración real** (para la API; pide `--yes`):

```bash
cd /opt/makingsmiles
./restore-postgres.sh \
  --dump "$(ls -1t backups/makingsmiles-db-*.dump | head -1)" \
  --media "$(ls -1t backups/makingsmiles-media-*.tar.gz | head -1)" \
  --yes
```

Hace: verifica checksum y `pg_restore --list`, para la API, termina conexiones,
recrea la base, restaura con `--no-owner`, `ANALYZE`, arranca la API y espera
`/health/db`; después exige comprobar login real y un listado real. El dump de
globals se aplica a mano si hacen falta roles:
`compose exec -T postgres psql -U <user> -d postgres < makingsmiles-globals-*.sql`.

**Lo que NO se ha probado**: ni la prueba en seco ni la restauración real se han
ejecutado en este entorno (§13). El primer staging debe ejecutar §8.5 y dejar
constancia en `history.log`/registro del deploy.

### 9.4 Recomendaciones que faltan (no implementadas)

- Copia **offsite en dos destinos** distintos y prueba de restauración periódica
  (trimestral) con registro.
- Custodia de la clave privada `age` fuera del servidor (si se pierde, las copias
  cifradas no sirven) y rotación documentada.
- Alertar si el timer lleva >48 h sin ejecutarse correctamente (dead-man's switch).


## 10. Seguridad y operación

### 10.1 Defensa en capas

1. **Security List del VCN** (Oracle): ingress 22 solo desde la IP admin, 80 y 443.
2. **ufw** en el SO: `default deny incoming`, 80/443, **22 solo desde `--admin-cidr`**
   (o la IP de la sesión SSH; nunca 0.0.0.0/0 por defecto).
3. **Compose**: solo Caddy publica puertos; Postgres/Redis/Evolution/API no.
   API y Evolution tienen **egress** por `edge` (LLM/SMTP y WSS de WhatsApp).
4. **Usuario de deploy sin docker**: no está en el grupo `docker` (equivale a root
   en el host). Solo puede `sudo /usr/local/sbin/makingsmiles-deploy` (wrapper root
   con acciones fijas y referencia de imagen validada). La contraseña sudo no se
   pide solo para ese comando (`NOPASSWD` acotado).
5. **SSH**: solo clave pública; `PermitRootLogin no`, `PasswordAuthentication no`,
   `KbdInteractiveAuthentication no` (el bootstrap solo lo aplica si instala antes
   una clave y tras `sshd -t`, y revierte si no valida).
6. **TLS**: Caddy (API) y Vercel (frontend); HSTS en la API.
7. **fail2ban** sobre SSH. La jaula HTTP sobre logs de Caddy sigue pendiente (§11).

### 10.2 Secretos

- Nunca en git. `.env` en el servidor **root 600** y secretos de CI en el
  *environment* `staging` de GitHub.
- El token de GHCR **no se pasa por argumento**: el bootstrap lo lee de
  `GHCR_TOKEN` (env) y lo manda a `docker login --password-stdin`.
- Claves del servidor: `/opt/makingsmiles/.ssh/` root 0700; claves de backup 600.
  La clave privada `age` se custodia fuera del servidor.
- `validate-env.sh` rechaza `CAMBIAR`, `OWNER`, `example.com/org`, `CHANGEME`,
  secretos por defecto y longitudes insuficientes: evita arrancar Postgres con una
  contraseña conocida (el placeholder `CAMBIAR` no está vacío y Compose lo acepta).
- Rotación: `deploy/oracle/README.md` (la API recoge el valor nuevo al recrearse;
  `POSTGRES_PASSWORD` exige `ALTER ROLE` + recrear API/Evolution).

### 10.3 Cookies, CORS y CSRF

- Cookie de sesión **`access_token`** (verificado en `backend/api/auth_router.py:84-97`):
  `HttpOnly`, `Secure`, `SameSite=Lax`, sin `Domain` → host-only de `staging.<dominio>`.
- CORS de la API: solo `PUBLIC_FRONTEND_URL`; las rutas cross-origin directas
  (`/media`, `/events`) no usan cookies.
- CSRF: al ser same-origin a través del rewrite, el navegador no hace preflight; la
  API debe mantener las comprobaciones de `Origin`/doble cookie. El rewrite **no**
  sustituye esas defensas.

### 10.4 Logs y observabilidad

- **Caddy**: access log JSON en `/data/access.log` con rotación (50 MiB ×10).
  `/media/*` y `/events/*` **se omiten del log** (`log_skip`) para no registrar
  `?sig=`/`?token=`; [log_skip](https://caddyserver.com/docs/caddyfile/directives/log_skip).
- **Docker**: `json-file` con `max-size: 10m`, `max-file: 3` por servicio.
- **Vercel**: logs de runtime **1 h** en Hobby ([Limits](https://vercel.com/docs/limits#logs)).
  No son registro de auditoría. Para staging se acepta; para producción hace falta
  sumidero externo.
- **No implementado**: monitor externo de `/health/db` y del frontend, alerta al
  propietario y dead-man's switch del backup (deudas §11).
- `/health` (cadena LLM) no se usa como healthcheck: `/health/db`.

### 10.5 IP del cliente para auditoría de login (abierto)

Cadena: navegador → Vercel CDN → Caddy → API. Vercel reenvía `x-real-ip` y
`x-forwarded-for` ([rewrites](https://vercel.com/docs/routing/rewrites#identifying-the-visitor-at-your-origin)).
**Caddy ahora propaga `X-Real-IP = {remote_host}`** (el peer TCP que ve Caddy), no
copia el header del cliente: copiarlo era falsificable. Consecuencia: en tráfico
proxeado por Vercel, la API ve la **IP del edge de Vercel**, no la del paciente. La
IP real del visitante no está disponible de forma fiable sin una política de
confianza; **no usar cabeceras para decisiones de seguridad**, solo para auditoría.

Opciones (ninguna implementada; decisión pendiente):
- **A (recomendada)**: patrón oficial de **secreto de origen** (`routes` con
  `x-origin-secret` en `vercel.json` y validación en Caddy/API) y rechazar en el
  origen el tráfico que no venga de Vercel
  ([doc](https://vercel.com/docs/routing/rewrites#restricting-your-origin-to-vercel-traffic)).
- **B**: restringir por IP a rangos de Vercel (mantenimiento).
- **C**: aceptar que la auditoría solo tenga la IP del edge (staging).

### 10.6 Actualizaciones

- `unattended-upgrades` para parches de SO.
- Imágenes fijadas a versión completa salvo `postgres:16.14` y `redis:7.4-alpine`
  (minor fijado; §6.4). Antes de producción, fijar **digest** y política de parcheo.


## 11. Deudas, bloqueos y decisiones pendientes (explícitas)

**BLOQUEOS vigentes para el corte** (el staging actual no es funcional en esas partes):

| # | Bloqueo / deuda | Estado | Dueño propuesto |
|---|---|---|---|
| **D-2** | **La API no implementa la firma de `/media` (URL firmada) ni el token SSE firmado.** Mientras no exista, `/media` y `/events` **no funcionan**; la capa de infra ya los enruta fuera de Vercel. Es S2. | **BLOQUEO VIGENTE** | frente backend (S2) |
| **EXT-1** | `frontend/next.config.ts` tiene un bloque `headers()` que **pisa la CSP/COOP/COEP** del `vercel.json`. No es scope de esta tarea (lo registra el Lead y lo arregla el rebuild del frontend). Hasta entonces, la CSP efectiva no es la documentada. | **BLOQUEO externo** | frente frontend |
| **ADR-1** | El ADR-001 dice «ticket de un solo uso»; el diseño vigente es **token firmado de corta vida reutilizable** (§5.3). Corregir el ADR (lo lleva el Lead). | discrepancia doc | Lead |

Otras deudas:

| # | Deuda | Por qué importa | Dueño propuesto |
|---|---|---|---|
| D-1 | **Sustituir el placeholder** de dominio al crear el proyecto Vercel (§7.2.1) en **ambos** `vercel.json`; el gate ya verifica igualdad y recuento | si no se sustituye, `/api/*` apunta a `api.staging.example.com` | Lead/operador |
| D-3 | Patrón `x-origin-secret` para restringir el origen a Vercel (§10.5) | IP/auditoría fiables y rechazo de tráfico directo | Lead + backend |
| D-4 | Migraciones de esquema (forward/backward) | sin ellas no hay rollback de BD seguro | frente backend |
| D-5 | Rate limit en Caddy o fail2ban sobre logs HTTP | segunda capa contra fuerza bruta/abuso | infra |
| D-6 | Monitor externo + dead-man's switch de backups | detectar caídas y backups silenciosamente roto | infra/propietario |
| D-7 | ~~ADR-001~~ **creado**; queda corregir la frase del ticket (§5.3) | coherencia del riesgo aceptado | Lead |
| D-8 | Revisión jurídica/DPO antes del corte (DPA, categoría especial) | datos de salud; Hobby no tiene DPA | propietario |
| D-9 | Fijar digests y política de actualización para producción | reproducibilidad y parcheo | infra |
| D-10 | `/opt/makingsmiles` es escribible por el usuario de deploy (rsync): los **scripts** que ejecuta el wrapper ya son copias root-owned en `/usr/local/lib/makingsmiles`, pero **`docker-compose.yml`/`Caddyfile` de `/opt` siguen siendo deploy-owned**. Un deploy comprometido podría alterar el compose y disparar el wrapper root. Mitigación propuesta: dir root y rsync vía wrapper con validación | elevación de privilegios por cuenta de deploy comprometida | infra (producción) |


## 12. Validación ejecutada de verdad (con qué herramienta)

Fecha: 2026-11-01 (UTC). Todo lo de esta tabla se ejecutó en el worktree; lo que no
está aquí, no se hizo.

| Qué | Comando / herramienta | Resultado |
|---|---|---|
| Python del sistema | `python3 -V` | `Python 3.14.6` |
| PyYAML del sistema | `python3 -c "import yaml"` | **ausente** → venv temporal |
| Parser YAML real | `/tmp/ms-yaml-venv/bin/python` con **PyYAML 6.0.3** | `docker-compose.yml` y `deploy-oracle.yml`: **parse OK** |
| Parser JSON real | `json` de stdlib sobre `vercel.json` y `frontend/vercel.json` | **parse OK en ambos e idénticos** |
| Placeholders | recuento de `api.staging.example.com` | **5 en cada `vercel.json`** |
| Variables de entorno | contraste de las `${VAR}` de compose contra las claves de `env.example` | **28 variables de compose, 0 sin documentar** |
| Validador de env (negativo) | `bash deploy/oracle/validate-env.sh deploy/oracle/env.example` | **rechaza** (22 errores por placeholders/secretos) |
| Validador de env (positivo) | `validate-env.sh` sobre env relleno (`/tmp/ci-staging.env`, `age` simulado con stub en PATH) | **acepta** |
| Sintaxis de scripts | `bash -n` de **6** scripts (`backup`, `bootstrap`, `check-evolution`, `deploy-staging`, `restore`, `validate-env`) | **OK en los 6** |
| Compose YAML | PyYAML: servicios/redes/volúmenes/puertos/límites | 5 servicios, 2 redes, 3 volúmenes + bind; solo Caddy publica 80/443/443udp; API y Evolution en `edge` |
| Workflow | PyYAML + comprobación de `${{ }}` dentro de `run:` | parse OK; **0** interpolaciones de Actions dentro de `run:` |
| Rollback de emergencia | inspección de `needs:` | job `rollback` **sin** `needs` |
| Arquitecturas de imagen | API pública de Docker Hub (`/v2/repositories/.../tags/...`) | arm64 en `postgres:16.14`, `redis:7.4-alpine`, `caddy:2.11.7-alpine`, `evolution-api:v2.3.7` |
| Documentación de plataforma | `web_fetch` de las URLs de §14 | contenido contrastado (§6) |
| Docker (binario) | `docker --version` | 29.9.2 (binario), **daemon NO disponible** |
| Caddy / ShellCheck / actionlint / Vercel CLI | `command -v` | **no instalados** |

Nota sobre el parser YAML: PyYAML implementa YAML 1.1 y lee la clave `on:` de
GitHub Actions como booleano `True`; es una diferencia de versión del estándar, no
un error de sintaxis (GitHub usa YAML 1.2). No hay `actionlint` para validar
semántica de Actions; por eso el primer run real del workflow está en §13.

## 13. Lo NO validado (lista explícita)

No se ha ejecutado o no se puede garantizar en este entorno. **Nada de esto debe
presentarse como probado.** Cada punto indica cómo se valida.

**Plataforma Docker / configuración**
1. `docker compose config` (interpolación real, `mem_limit`/`cpus`/`pids_limit`,
   `command:` de workers, `depends_on`): **no ejecutado** (daemon no disponible).
2. `caddy validate --config Caddyfile`: **no ejecutado** (binario no instalado). Las
   directivas se revisaron contra documentación oficial; `request_body` es
   **experimental (v2.10+)** y `log_skip` se comprobó en su doc. Plan B si el
   Caddyfile no adapta: comentar `request_body` (y dejar el límite solo en la API).
3. `shellcheck` de los scripts: **no ejecutado** (no instalado). Solo `bash -n`.
4. `postgres-init/01-evolution-db.sql` con el `psql` de `postgres:16.14`:
   **no ejecutado**.
5. Healthchecks con herramientas de las imágenes: Caddy `wget`, Evolution `node`,
   API `curl`. **No ejecutados**; el de Evolution ahora exige 200 en
   `/instance/fetchInstances` con apikey (puede quedar `unhealthy` si la config de
   BD/API falla: es señal, no ruido).
6. `check-evolution.sh` (sesión real `connectionStatus=open`): **no ejecutado**; solo
   se verificó `bash -n`. La forma del JSON de `fetchInstances` en `v2.3.7` no se
   ha comprobado en vivo (el parser tolera varias claves).
7. Wrapper `sudo` (`/usr/local/sbin/makingsmiles-deploy`), fichero sudoers y
   `visudo`: **no ejecutados** (requiere servidor); revisados a mano.
8. Endurecimiento SSH (`sshd -t`, reload, claves): **no ejecutado**.
9. Límites de recursos (`mem_limit`/`cpus`/`pids_limit`) y workers=2: **no
   ejecutados**; Compose los soporta, pero no se ha medido consumo real en A1.

**Oracle**
10. Capacidad A1 en la región elegida: **no comprobado** («out of host capacity»
    documentado).
11. Umbrales de reclamación de inactivas: **no medidos**.
12. Egress real (10 TB/mes): **no medido**.
13. Que las imágenes arm64 arranquen en A1: **no ejecutado** (solo manifest).
14. TLS/ACME real para `api.<dominio>`: **no ejecutado** (sin DNS/instancia).

**Vercel**
15. Proyecto Vercel real, build, dominio y TLS: **no ejecutado**.
16. Rewrite externo de `/api/*` y CSP/COOP/COEP reales: **no ejecutados**; el JSON
    sí se validó y los dos ficheros son idénticos.
17. Caché de rewrites externos: **no medido** (mitigado con
    `x-vercel-enable-rewrite-caching: 0` + `no-store`).
18. **`next.config.ts` del frontend pisa la CSP** (bloqueo EXT-1, §11): no es scope
    de esta tarea; no se ha comprobado qué CSP gana en un deploy real.

**Navegador / extremo a extremo**
19. COOP/COEP + media cross-origin con CORP: **no probado en navegador**.
20. SSE >120 s a través de Caddy y **reutilización del token al reconectar**:
    **no probado**.
21. Cookie first-party `access_token` a través del rewrite: **no probada** en
    DevTools.
22. Login/CSRF completos: **no probados**.
23. IA asíncrona de punta a punta: **no implementada** (S2); aquí solo el diseño.
24. URL firmada de media y token SSE: **no implementados** (S2, bloqueo D-2).

**Backups / restore / operación**
25. Backup real local, verificación inline, cifrado `age` y offsite rsync:
    **no ejecutados**.
26. Restauración `--scratch` (ANALYZE, tablas clave, evolution, globals, media) y
    restauración real: **no ejecutadas**.
27. Rollback automático/manual real y estados `current_image`/`previous_image`:
    **no ejecutados** (lógica revisada; `bash -n`).
28. Timer systemd y validación de `.env` en el servidor: **no ejecutados**.
29. Rotación de secretos (`ALTER ROLE`): **no ejecutada**.

**CI/CD**
30. Ejecución real del workflow (gate, build arm64 con QEMU, push GHCR, SSH,
    wrapper sudo, deploy, rollback): **no ejecutada**.
31. Que `scripts/deploy-gate.sh` pase con este árbol: **no ejecutado aquí**.
32. `rsync`/SSH desde Actions al servidor: **no ejecutado**.
33. El gate positivo de `validate-env.sh` se probó localmente con `age` **simulado**
    (stub en PATH), porque `age` no está instalado en este entorno de escritura.

**Legal / protección de datos**
34. Suficiencia legal de Vercel Hobby para datos de salud: **no evaluada** (requiere
    DPO/abogado; aquí solo consta que **no hay DPA** en Hobby, citado).
35. Acuerdo de encargado del tratamiento de Oracle: **no revisado** aquí.
36. Que el staging no contenga datos reales: **no verificado** (depende de la carga;
    es condición del ADR).

## 14. Referencias oficiales usadas (todas consultadas 2026-11-01)

**Vercel**
- Hobby Plan — https://vercel.com/docs/plans/hobby
- Fair Use Guidelines (commercial usage) — https://vercel.com/docs/limits/fair-use-guidelines#commercial-usage
- Data Processing Addendum — https://vercel.com/legal/dpa
- Limits (general, proxied request timeout, logs) — https://vercel.com/docs/limits
- Vercel Functions limits (body 4,5 MB, max duration, memoria) — https://vercel.com/docs/functions/limitations
- Configuring regions for Vercel Functions (Hobby = una región) — https://vercel.com/docs/functions/configuring-functions/region
- Global network and regions (`fra1`) — https://vercel.com/docs/regions
- Rewrites on Vercel (rewrites externos, cabeceras, caché, secreto de origen) — https://vercel.com/docs/routing/rewrites
- `vercel.json` (rewrites, headers, regions) — https://vercel.com/docs/project-configuration/vercel-json
- Instant Rollback — https://vercel.com/docs/instant-rollback
- Domains — https://vercel.com/docs/domains
- KB: ¿se puede usar Vercel como reverse proxy? — https://vercel.com/kb/guide/vercel-reverse-proxy-rewrites-external
- KB: límite de cuerpo de 4,5 MB y alternativas — https://vercel.com/kb/guide/how-to-bypass-vercel-body-size-limit-serverless-functions

**Oracle Cloud Infrastructure**
- Always Free Resources (A1/micro, disco, egress, idle reclamation, home region, out of host capacity) — https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- Regions and Availability Domains (regiones UE, límite de una región suscrita) — https://docs.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm
- Security Lists (firewall de red del VCN) — https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securitylists.htm

**Caddy**
- Automatic HTTPS — https://caddyserver.com/docs/automatic-https
- `request_body` (límite de cuerpo; experimental v2.10+) — https://caddyserver.com/docs/caddyfile/directives/request_body
- `reverse_proxy` (flush_interval, stream_timeout, health checks, X-Forwarded) — https://caddyserver.com/docs/caddyfile/directives/reverse_proxy
- `log` — https://caddyserver.com/docs/caddyfile/directives/log
- `log_skip` (omitir peticiones con secretos en la query del access log) — https://caddyserver.com/docs/caddyfile/directives/log_skip
- Orden de directivas de Caddy (por qué `handle` va antes que `respond`) — https://caddyserver.com/docs/caddyfile/directives#directive-order

**Imágenes (Docker Hub)**
- postgres — https://hub.docker.com/_/postgres · API de tags (16.14): https://hub.docker.com/v2/repositories/library/postgres/tags/16.14
- redis — https://hub.docker.com/_/redis · API de tags (7.4-alpine): https://hub.docker.com/v2/repositories/library/redis/tags/7.4-alpine
- caddy — https://hub.docker.com/_/caddy · API de tags: https://hub.docker.com/v2/repositories/library/caddy/tags/2.11.7-alpine
- evolution-api — https://hub.docker.com/r/evoapicloud/evolution-api/tags · API de tags: https://hub.docker.com/v2/repositories/evoapicloud/evolution-api/tags/v2.3.7

**Docker / herramientas de backup**
- Docker Compose file (`mem_limit`, `cpus`, `pids_limit`, `command`) — https://docs.docker.com/reference/compose-file/services/
- `age` (cifrado en reposo de las copias) — https://age-encryption.org/

**GitHub / RGPD**
- GHCR (GitHub Container Registry) — https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
- Secrets en GitHub Actions — https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions
- RGPD (Reglamento UE 2016/679, arts. 9 y 28) — https://eur-lex.europa.eu/eli/reg/2016/679/oj
