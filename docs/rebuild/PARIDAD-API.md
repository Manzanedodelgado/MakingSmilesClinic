# PARIDAD-API — MakingSmiles_Studio

> **Qué es este documento.** La especificación de la superficie HTTP/WebSocket del backend
> legacy (`master` @ `a76ee81`, worktree `.worktrees/rebuild-vercel-oracle`) que el rebuild
> por módulos con corte progresivo debe preservar **exactamente** hasta que cada módulo se
> sustituya. Es un contrato observable, no una descripción de intenciones.
>
> **Cómo leerlo.** §1 método y límites; §2 cifras medidas y contraste con la auditoría previa;
> §3 topología de invocación; §4 autenticación/autorización; §5 modelo de errores; §6 formas de
> respuesta; §7 resumen por módulo; §8 **inventario completo de las 498 operaciones** (una fila
> por ruta, con evidencia `fichero:línea`); §9 contrato estable para apps móviles; §10 riesgos y
> lo no verificado. El mismo inventario está en `PARIDAD-API.csv` (formato máquina).
>
> **Reglas de este documento:** toda afirmación sobre el código lleva evidencia `ruta:línea`.
> Lo que no se pudo verificar se marca como **NO VERIFICADO**. No contiene PII de pacientes ni
> valores de secretos (las claves de configuración se citan por su *nombre*, nunca por su valor).

---

## 1. Método de extracción (reproducible) y límites

### 1.1 Qué se hizo

Extracción **estática** de la superficie de rutas a partir del árbol de código, sin ejecutar la
aplicación (el `.venv` del backend es de Linux y no arranca en este macOS; ver `docs/rebuild/BASELINE.md`).
El procedimiento exacto es:

1. **Decoradores de ruta.** Se parsean todos los módulos `backend/api/*.py` con `ast` y se
   recogen las funciones decoradas con `@router.<get|post|put|patch|delete|websocket>(...)`.
   Evidencia del patrón: p. ej. `backend/api/auth_router.py:65` (`@router.post("/login")`),
   `backend/api/ws_router.py:153` (`@router.websocket("/gestoria/{centro_id}")`).
2. **Prefijo del router.** Para cada módulo se lee la asignación `router = APIRouter(prefix=...)`
   (p. ej. `backend/api/agenda_router.py:34`, `backend/api/comunicacion_router.py:37`) y se
   concatena con el `path` del decorador. Los tres routers sin prefijo se tratan como prefijo
   vacío (`backend/api/health_router.py:9`, `backend/api/media_router.py:21`,
   `backend/api/radiologia_router.py:73`, `backend/api/romexis_router.py:30`,
   `backend/api/cefalometria_router.py:29`).
3. **Routers realmente montados.** Se cruzan los módulos con las llamadas
   `app.include_router(...)` de `backend/main.py:159-206` (43 llamadas, en ese orden). resultado:
   **los 43 módulos de router están montados; 0 módulos huérfanos**.
4. **Auth/authz.** Por cada operación se recogen las expresiones `Depends(...)` de la firma, los
   valores por defecto de los parámetros y el parámetro `dependencies=[...]` del decorador
   (p. ej. `backend/api/internal_tenant_router.py:48`). Se resuelven las constantes locales de
   permiso (`EDITAR`, `VER`, `_SU`, ...) contra su asignación en el mismo módulo
   (p. ej. `backend/api/comunicacion_router.py:39-40`, `backend/api/superuser_router.py:35`).
5. **Request/response/errores.** Se extraen los parámetros tipados con `Query/Form/Body/File/Path/Header`,
   el `response_model` del decorador, el `status_code` del decorador y los `raise HTTPException(...)`
   (status + `detail`) del cuerpo de cada función.
6. **Colisiones.** Se comprueba la colisión exacta `(método, path)` y la colisión semántica
   `(método, path con todo `{param}` normalizado a `*`)` en el orden real de registro
   (orden de `include_router` × orden de definición dentro del módulo).

Script reproducible: `docs/rebuild/verificar_rutas.py` (incluido en el worktree). Ejecuta la
extracción estática y, **si el entorno tiene dependencias**, opcionalmente importa `main:app`
y compara con `len(app.routes)`/`app.openapi()["paths"]`.

**Columnas de `PARIDAD-API.csv`** (498 filas, una por operación):

| Columna | Contenido |
|---|---|
| `metodo`, `ruta` | método HTTP y path final (prefijo resuelto) |
| `modulo`, `fichero`, `linea`, `funcion` | router, fichero, línea del decorador y nombre de la función |
| `autenticacion` | puerta(s) de auth (`JWT centro`+`X-Centro-Id`, `JWT paciente`, `X-Internal-Key`, token de webhook/firma/relé, o `SIN AUTENTICACIÓN`) |
| `autorizacion` | permiso(s) fino(s) exigidos (`permiso <código>`, `O` = OR) |
| `centro` | si aplica resolución multi-tenant por `X-Centro-Id` |
| `request` | parámetros relevantes (`Query`/`Form`/`Body`/`File`/`Path`/`Header`) |
| `response_model` | modelo Pydantic declarado (vacío = respuesta libre/binaria) |
| `status_code` | código de éxito declarado |
| `errores` | códigos de error detectados/deducidos (`401/403/400` implícitos de auth) |
| `resumen` | primer línea del docstring |
| `capas_implicadas` | capas que toca la operación según los `import` de su router: `api/` (siempre) → `application/…` → `domain/models(…)` → `infrastructure/(…)` |
| `sin_auth_declarada` | `sí`/`no` para filtrar las 23 operaciones del §4.5 |

### 1.2 Límites del método (honestidad sobre el alcance)

- **No se instanció la app.** El conteo por import (`app.routes`) no se pudo ejecutar aquí.
  Lo que se reporta es lo que el código **declara**; la app importada puede añadir rutas
  automáticas (docs/OpenAPI, ver §2.2) y `app.exception_handler` no añade rutas.
- Las rutas **generadas dinámicamente** dentro de bucles/factorías no se detectarían con el
  patrón de decorador. Barrido manual de `grep -n "@router\."` sobre `backend/api/`: los 498
  decoradores son literales de módulo; **no se ha encontrado ninguna factoría de rutas**.
  Búsqueda de respaldo: `grep -rn "add_api_route\|APIRouter()" backend/api` (solo los
  `APIRouter(prefix=...)` de §1.1). **NO VERIFICADO** en tiempo de ejecución, por la limitación
  del punto anterior.
- El `request`/`response` documentado es el **declarado** en la firma y los DTOs Pydantic. El
  cuerpo real que devuelven los `return {...}` se resume a partir del propio código cuando es
  relevante, no se ejecutó cada endpoint.
- Las **reglas de negocio** internas (qué calcula cada servicio) están resumidas a partir de
  docstrings y del código leído; el detalle por flujo vive en `PARIDAD-FLUJOS.md`.

---

## 2. Cifras medidas y contraste con la auditoría previa («48 rutas»)

### 2.1 Medición (2026-11-01, sobre `a76ee81`)

| Medición | Valor | Cómo se obtuvo |
|---|---:|---|
| Operaciones declaradas (método + path) | **498** | AST sobre `backend/api/*.py` |
| Rutas únicas de router (path, sin método) | **431** | `set(path)` sobre las 498; + `GET /` = **432** en OpenAPI (§2.2) |
| Operaciones únicas (método+path exactos) | **497** | 498 − 1 duplicada (ver §2.3) |
| Routers montados | **43** | `main.py:159-206` |
| Módulos de router existentes | **43** | `backend/api/*_router.py` |
| WebSockets | **1** | `backend/api/ws_router.py:153` |
| GET / POST / PUT / PATCH / DELETE | **221 / 175 / 53 / 14 / 34** | AST |
| Operaciones con `response_model` declarado | **15** | decoradores |
| Rutas sin ninguna dependencia de auth | **23** | ver §4.5 |
| Rutas con permiso fino exigido | **397** | `require_permission(...)` resuelto |

### 2.2 Verificación por import (ejecutada) y el artefacto `_IncludedRouter`

Una versión anterior de este apartado decía «esperado, NO ejecutado». **Ya está verificado**: el
lead ejecutó el import de la app en un venv macOS (el `.venv` del repo es de Linux, `BASELINE.md:28`).
Resultado el 2026-11-01 con **FastAPI 0.162.0**, `ENVIRONMENT=development`:

| Medición por import | Valor | Desglose |
|---|---:|---|
| `len(app.routes)` | **48** | **43 objetos `_IncludedRouter`** (los `include_router`, con `path == ""`) + **4 rutas de documentación** + **1 `GET /`** |
| `len(app.openapi()["paths"])` | **432** | 431 paths únicos extraídos de los routers + `GET /` de `main.py:209-211` |
| Operaciones OpenAPI | **≈498** | 498 estáticas − 1 WebSocket (OpenAPI no incluye WS) + 1 `GET /` = **498** |

Comando exacto que lo reproduce (desde `backend/`, con el venv que tenga las dependencias):

```bash
cd backend
ENVIRONMENT=development PYTHONPATH=. python3 - <<'PY'
import main
from collections import Counter
print("len(app.routes) =", len(main.app.routes))
print(Counter(type(r).__name__ for r in main.app.routes))
print("openapi paths  =", len(main.app.openapi()["paths"]))
PY
# Salida verificada (FastAPI 0.162.0):
# len(app.routes) = 48
# Counter({'_IncludedRouter': 43, 'APIRoute': 5})
# openapi paths  = 432
```

**Por qué `len(app.routes)` son 48 y no ~500:** en las versiones recientes de FastAPI,
`include_router` ya no aplana las rutas del sub-router dentro de `app.routes`: deja **un objeto
envoltorio `_IncludedRouter` por router montado** (43 aquí) más las rutas propias de la app
(`GET /` y las de documentación). Esos 43 envoltorios **no son operaciones**: es el artefacto que
produjo la cifra «48». La comprobación se cierra con el desglose por tipo de objeto, no con el
número bruto.

**Matiz de versión (NO VERIFICADO en producción):** `requirements.txt:1` pide `fastapi>=0.115.0`
y `constraints.txt:12` fija `fastapi==0.141.1`, pero los Dockerfile instalan solo
`requirements.txt` (`backend/Dockerfile:30-31`, `backend/Dockerfile.prod:13-14`), así que **la
versión efectiva del backend desplegado no está fijada por el repo**. En versiones antiguas de
FastAPI, `include_router` aplanaba las rutas y `len(app.routes)` habría dado ~500; el artefacto
«48» depende, por tanto, de la versión. Este dato refuerza la conclusión de §2.3: **no usar
`len(app.routes)` como métrica de paridad**.

Un import real también puede fallar si faltan dependencias o variables de entorno; `init_db()`
se ejecuta en el `lifespan` (`main.py:82`), no al importar, pero `create_engine` sí se evalúa al
importar `main.py` (`infrastructure/config/db.py:8`), de modo que un `DATABASE_URL` inválido
tumba el import.

### 2.3 Contraste con las «48 rutas» de la auditoría previa: era un artefacto, no un conteo

**Resuelto.** La auditoría previa concluyó «48 rutas idénticas antes/después» midiendo
`len(app.routes)`. Con el FastAPI verificado (§2.2), **ese número es un artefacto de
`_IncludedRouter` y no mide rutas**: si se borraran todas las operaciones de uno o varios routers
incluso dejando los `include_router`, el conteo podría seguir dando 48. Por tanto la conclusión de
la auditoría previa **no demuestra paridad de rutas**.

| Métrica | Valor | ¿Sirve para paridad de rutas? |
|---|---:|---|
| `len(app.routes)` | 48 | **NO** — cuenta 43 envoltorios + 5 rutas reales |
| `len(app.openapi()["paths"])` | 432 | **SÍ** — paths únicos servidos (432 = 431 de routers + `GET /`) |
| Operaciones OpenAPI | ~498 | **SÍ** — 498 estáticas − WS + `GET /` (coincide con el AST) |
| Operaciones estáticas (AST, §2.1) | 498 | **SÍ** — fuente principal de este documento |

**Criterio para el rebuild:** la paridad de rutas se verifica con
`app.openapi()["paths"]` y con el conjunto de operaciones `(método, path)` del OpenAPI, **nunca**
con `len(app.routes)`. Además hay que comparar contra el inventario estático de §8, porque el
OpenAPI **no incluye** el WebSocket (`/ws/gestoria/{centro_id}`, `ws_router.py:153`) y **sí
incluye** documentación (que en producción puede estar desactivada, `main.py:95-101`).

El script `docs/rebuild/verificar_rutas.py --import` implementa esta comparación (paths/operaciones
OpenAPI contra la extracción estática) y desglosa `app.routes` por tipo de objeto para exponer el
artefacto.

### 2.4 Duplicado real y ruta muerta

Hay una única colisión exacta en las 498 operaciones:

| Operación | Definición 1 (la que sirve) | Definición 2 (muerta) | Consecuencia |
|---|---|---|---|
| `GET /pacientes/{paciente_id}/previstos` | `backend/api/pacientes_router.py:855` (incluido en `main.py:171`) | `backend/api/clinico_router.py:417` (incluido después en `main.py:177`) | FastAPI resuelve por orden de registro: **la respuesta servida es la de `pacientes_router`**. La versión de `clinico_router` (SQL directo sobre `tratamientos_previstos`, docstring en :421) **nunca se ejecuta**. El rebuild debe preservar el contrato de `pacientes_router.py:855`; la otra es código muerto que no se debe portar a ciegas. |

No hay otras colisiones exactas ni semánticas (normalizando `{param}` → `*`).

---

## 3. Topología de invocación (cómo llega una petición)

| Hecho | Evidencia |
|---|---|
| En producción el navegador **no** llama al backend: Next reescribe `/api/:path*` → `BACKEND_ORIGIN` | `frontend/next.config.ts:5`, `frontend/next.config.ts:21-22` |
| El cliente web usa `API_BASE = "/api"` por defecto y `credentials: "include"` (cookie first-party) | `frontend/src/shared/lib/api.ts:10`, `:31` |
| Un `401` del backend redirige a `/login` en el cliente | `frontend/src/shared/lib/api.ts:44-47` |
| El proxy de Next corta a 30 s por defecto; se sube a **180 s** por el análisis de IA de radiografía (~30 s) | `frontend/next.config.ts:20` (comentario en :19) |
| CORS: en desarrollo permite `localhost/127.0.0.1/100.86.41.61/192.168.1.46` puertos 3000–3006; en producción **solo** `settings.public_frontend_url` | `backend/main.py:65-77`, `:111-117` |
| `allow_credentials=True` (imprescindible para la cookie httpOnly) | `backend/main.py:114` |
| Swagger/Redoc solo en desarrollo; en producción `openapi_url` únicamente si `ENABLE_AI_OPENAPI=true` | `backend/main.py:95-101` |
| Al arrancar: `init_db()` (create_all), seed de desarrollo, bus SSE, scheduler | `backend/main.py:80-92` |

**Implicación para el rebuild en Vercel + Oracle:** la cookie es first-party porque el navegador
habla solo con el dominio de Next y Next reenvía al backend. Si el frontend de Vercel llama
directo a la API de Oracle, la cookie pasa a ser third-party/cross-site y el login por
`/auth/login-cookie` deja de funcionar igual (SameSite=Lax, `auth_router.py:84-88`). Preservar el
rewrite (o mover la emisión de cookie al borde de Vercel) es parte del contrato, no un detalle.

---

## 4. Autenticación y autorización

Toda la authz del personal pasa por `backend/api/auth_deps.py` (CENTINELA). Hay **tres puertas**
distintas y una cuarta de servicio:

### 4.1 Personal del centro (web y app del doctor): JWT «centro»

- **Token**: JWT HS256 (`settings.jwt_algorithm`, `backend/domain/config/settings.py:77`) con
  caducidad **12 h** (`access_token_expire_minutes = 60 * 12`, `settings.py:78`; aplicada en
  `backend/infrastructure/security.py:28-33`). Payload: `sub`, `tipo="centro"`, `nombre`,
  `accesos=[{centro_id, rol_id}]` (`backend/application/services/auth_service.py:114-125`).
- **Transporte**: `Authorization: Bearer <jwt>` **o** cookie `access_token` httpOnly
  (`backend/api/auth_deps.py:33-35`). El login web (`POST /auth/login-cookie`,
  `backend/api/auth_router.py:71-74`) **no devuelve el token en el JSON**; el login bearer
  (`POST /auth/login`, `:65-68`, usado por la app móvil del doctor) sí lo devuelve.
- **Cookie**: `httponly=True`, `secure=settings.cookie_secure` (forzado a `True` fuera de
  development, `settings.py:145-150`), `samesite="lax"`, `max_age=60*60*12`, `path="/"`
  (`backend/api/auth_router.py:84-88`). `POST /auth/logout` la borra con los mismos atributos
  (`:94-98`).
- **Multi-tenant**: cabecera opcional `X-Centro-Id`. Si el usuario tiene un solo acceso se usa
  ese; si tiene varios y no manda cabecera → **400**; si no tiene acceso a ese centro → **403**
  (`backend/api/auth_deps.py:46-61`).
- **Permisos finos**: `require_permission(codigo)` consulta `AuthService.permisos_de(usuario, centro)`
  y devuelve **403** si falta (`auth_deps.py:64-79`). La resolución de permisos es
  `(rol − denegados_por_persona) ∪ concesiones_directas`, y `superuser` nunca sale de un rol
  (`backend/application/services/auth_service.py:174-197`).
- **Freno de fuerza bruta**: bloqueo por **email** (no por IP) si hay
  `login_max_intentos` fallos en `login_ventana_min` minutos durante `login_bloqueo_min`
  (`auth_service.py:68-84`, `:99-112`). **Valores por defecto: 5 intentos / 15 min / 15 min**
  (`backend/domain/config/settings.py:128-130`). El `0` desactiva el freno (`settings.py:127`).
  El enunciado de la tarea decía «máx 4 intentos»: **el default del código es 5**; si el
  despliegue real usa 4 será por variable de entorno (`LOGIN_MAX_INTENTOS`), lo cual **no se ha
  verificado** (prohibido leer valores de `.env`). El script de paridad debe tratar este umbral
  como **configurable**, no como constante.
- **Auditoría**: cada intento (éxito/fallo/bloqueo) se escribe en `auditoria`
  (`auth_service.py:41-53`, `:104`, `:111`, `:126`).

### 4.2 Paciente (apps nativas): JWT «paciente»

- Puerta separada: `backend/api/paciente_auth_deps.py:25-36` exige `Bearer` con `tipo="paciente"`
  y extrae `paciente_id`/`centro_id` del propio token (sin cookie, sin `X-Centro-Id`).
- Vida del token: **30 días** (`paciente_token_expire_minutes`, `settings.py:139, :142`).
- Login OTP público: `POST /app/auth/solicitar-codigo` y `POST /app/auth/verificar-codigo`
  (`backend/api/paciente_auth_router.py:33`, `:50`). Código de 6 dígitos, hash SHA-256, caduca en
  `otp_expira_min=10` (`settings.py:139`), intento limitado por `otp_max_intentos=5` /
  `otp_ventana_min=15` (`settings.py:137-138`). Teléfono compartido entre pacientes exige
  `nombre_apellidos` y responde **428** para que la app pida el nombre (`paciente_auth_router.py:40-45`,
  `:59-64`). La respuesta de solicitud es siempre `{"ok": true}` (anti-enumeración, `:47-49`).

### 4.3 Servicio/servidor: clave interna y sesión de plataforma

- Cabecera **`X-Internal-Key`** comparada con `hmac.compare_digest` contra
  `settings.internal_api_key` (variable `internal_api_key`, `settings.py:67`). Usada por
  `internal_tenant_router.py:29-35` (8 endpoints), `jarvis_operador_router.py:24` (2),
  `romexis_router.py:35` (2) y, verificada dentro de la función, por
  `radiologia_router.py:146-155` y `:459-470`.
- **SuperUser**: permiso de plataforma `superuser` (`superuser_router.py:35`) sobre la **BBDD de
  plataforma** separada (`infrastructure/config/platform_db.py:1-47`, `get_platform_session`
  `:47`). Los datos operativos de un centro se tocan por el router interno
  (`internal_tenant_router`), no por queries directas: `settings.py:63-66` (comentario de
  diseño) y `superuser_router.py:1-5`.
- **Webhook WhatsApp**: `POST /comunicacion/webhook/{centro_id}` es público pero exige
  `token == webhook_secret/HMAC` de la integración del centro (`comunicacion_router.py:620-630`).
- **Firma pública de consentimiento**: las 3 rutas `/consentimientos/firmar/{code}` se autorizan
  por `signing_code` (tabla `consentimientos.signing_code`, `domain/models/documentos.py:85-95`).
- **Relé Ollama**: `GET /ollama/{token}/api/tags` autoriza por token en el path
  (`ollama_relay_router.py:487-491`).
- **WebSocket Gestoría**: `?token=<JWT centro>` validado **dentro** del socket (no por
  `Depends`), comprobando firma, tipo `centro`, acceso al centro y permiso `gestoria.ver`;
  cierra con código **4001** (token inválido) o **4003** (sin centro/permiso)
  (`ws_router.py:153-195`).

### 4.4 Catálogo de permisos efectivamente exigidos por la API

| Código de permiso | Nº de operaciones que lo exigen | Dónde se usa (ejemplo de evidencia) |
|---|---:|---|
| `pacientes.editar` | 65 | `pacientes_router.py` (muchas), `clinico_router.py` |
| `config.editar` | 62 | `configuracion_*_router.py`, `uploads_router.py:26` |
| `pacientes.ver` | 55 | `pacientes_router.py`, `dentia_router.py:96` |
| `gestoria.editar` | 51 | `gestoria_router.py`, `gestor_ia_router.py` |
| `gestoria.ver` | 32 (+12 lectura con `gestoria.facturacion.ver`) | `gestoria_router.py:25` (`VER_FACT = require_any_permission(VER, FACT)`) |
| `comunicacion.editar` | 32 | `comunicacion_router.py:40`, `motion_router.py`, `voicebot_router.py` |
| `superuser` | 25 | `superuser_router.py:35` |
| `comunicacion.ver` | 22 | `comunicacion_router.py:39` |
| `config.ver` | 11 | `config_router.py`, `configuracion_centro_router.py` |
| `informes.ver` | 10 | `informes_router.py` |
| `citas.ver` / `citas.editar` | 7 / 7 | `agenda_router.py:43`, `:294` |
| `informes.editar` | 3 | `informes_router.py` |
| `chat.usar` | 2 | `chat_router.py:53`, `:83` |
| **Total** | **397 operaciones con permiso fino**; otras **95** exigen solo autenticación de transporte (JWT/centro, `_SU`...) sin permiso adicional, y **23** no tienen ninguna dependencia de auth declarada (ver §4.5). | |

`require_any_permission(*codigos)` existe para permisos de lectura compartidos
(`auth_deps.py:81-99`); hoy solo lo usa Gestoría para `gestoria.facturacion.ver`
(`gestoria_router.py:23-25`). **Los códigos concretos son contrato**: los consume el frontend
(`frontend/src/app/(app)/layout.tsx:23-31`, filtros `perm`) y las apps móviles. El catálogo
semilla está en las migraciones `096_permisos_denegados_por_rol.sql`, `097_permisos_por_pestana.sql`,
`098_permisos_por_seccion.sql` (ver `PARIDAD-DATOS.md`).

### 4.5 Las 23 operaciones sin dependencia de autenticación (clasificadas)

Todas las demás (475) exigen al menos JWT. Estas 23 se han revisado una a una:

| Operación | Auth real | Evidencia | Veredicto |
|---|---|---|---|
| `POST /auth/login` | pública (credenciales en el body) | `auth_router.py:65-68` | Correcto |
| `POST /auth/login-cookie` | pública (credenciales en el body) | `auth_router.py:71-74` | Correcto |
| `POST /auth/logout` | pública (solo borra cookie) | `auth_router.py:94-98` | Correcto |
| `POST /auth/forgot` / `POST /auth/reset` | públicas anti-enumeración / token de un uso | `auth_router.py:101-119` | Correcto |
| `GET /auth/apariencia` | pública (branding de login) | `auth_router.py:22-25` | Correcto |
| `GET /auth/apariencia/imagen/{campo}` | pública, limitada a 3 campos y a `/media` | `auth_router.py:28-48` | Correcto (excepción deliberada) |
| `GET /health`, `/health/db`, `/health/llm` | públicas | `health_router.py:12`, `:42`, `:48` | Correcto |
| `GET /radiologia/modalidades` | pública (catálogo estático) | `radiologia_router.py:174-178` | Correcto (sin datos de paciente) |
| `POST /app/auth/solicitar-codigo` / `verificar-codigo` | públicas (login OTP) | `paciente_auth_router.py:33`, `:50` | Correcto |
| `POST /comunicacion/webhook/{centro_id}` | token = secreto de integración | `comunicacion_router.py:620-630` | Correcto |
| `GET/POST /consentimientos/firmar/{code}`, `.../pdf` | `signing_code` del consentimiento | `consentimientos_router.py:57`, `:69`, `:84` | Correcto |
| `GET /ollama/{token}/api/tags` | token en path | `ollama_relay_router.py:487-491` | Correcto |
| `POST /radiologia/detectar-rx-interno`, `/radiologia/importar-romexis-interno` | cabecera `X-Internal-Key` | `radiologia_router.py:146-155`, `:459-470` | Correcto |
| `WEBSOCKET /ws/gestoria/{centro_id}` | JWT en query validado dentro | `ws_router.py:153-195` | Correcto |
| **`GET /pacientes/{paciente_id}/ficha`** | **NINGUNA** | `pacientes_router.py:1433-1470` | **DEFECTO DE SEGURIDAD** (ver §10.1) |
| **`GET /pacientes/{paciente_id}/citas`** | **NINGUNA** | `pacientes_router.py:1468-1475` | **DEFECTO DE SEGURIDAD** (ver §10.1) |

**Aviso para el rebuild:** las dos últimas devuelven datos de paciente (nombre, email, alergias,
anamnesis) sin token. El rebuild **no debe reproducir el defecto**: el contrato funcional es
«la app del paciente obtiene su ficha», y la corrección es exigir `get_current_paciente` y
comprobar `paciente_id == token.paciente_id` (como ya hace `/app/pacientes/me/*`,
`app_paciente_router.py:66`). Documentado, no arreglado: esta tarea es de solo lectura.

---

## 5. Modelo de errores (contrato observable)

| Situación | Respuesta | Evidencia |
|---|---|---|
| `HTTPException(status, "texto")` | JSON `{"detail": "texto"}` con ese status | patrón en todo `api/`; p. ej. `auth_deps.py:35` |
| Validación de request (Pydantic) | **422** con el esquema estándar de FastAPI | p. ej. `dentia_router.py:86-92` |
| Caja de negocio (`CajaError`, `CajaNoEncontrado`) | **422** / **404** con `{"detail": ...}` | handler global en `main.py:120-127` |
| WhatsApp/Evolution (`EvolutionError`) | **422** si el número no es válido; **502** si la pasarela no responde | handler global `main.py:130-137` + `evolution_api.py:15-34` |
| Sin token / token inválido | **401** `{"detail": "No autenticado"}` / `"Token inválido o expirado"` | `auth_deps.py:34-38` |
| Sin acceso al centro | **403** `"Sin acceso a ese centro"` | `auth_deps.py:59-61` |
| Varios accesos y sin `X-Centro-Id` | **400** `"Indica el centro en la cabecera X-Centro-Id"` | `auth_deps.py:52-58` |
| Permiso fino ausente | **403** `"Permiso requerido: <código>"` | `auth_deps.py:72-78` |
| LLM caído en Consulta | **503** controlado (el frontend cae a su heurístico) | `consulta_router.py:54-60`, `:120-123` |
| IA dental (ortopantomografía) caída | **503** `"Servicio de IA no configurado/no disponible"` | `ia_dental_client.py:11-22`, `pacientes_router.py:1088-1095` |
| Error no controlado | **500**; además el middleware de Centinela cuenta 5xx para avisar | `main.py:140-152` |

**No hay envelope global de respuesta.** Cada ruta decide su forma: `dict` libre, modelos
Pydantic (`response_model`, solo 15 operaciones), `list[DTO]`, `FileResponse`/`Response` binario,
`StreamingResponse` SSE. Algunas rutas envuelven en `{"data": ...}` (p. ej.
`comunicacion_router.py:166-172`) y otras devuelven la lista/objeto directo. **Preservar la forma
exacta por ruta** (columna «Resp.» del inventario) es tan obligatorio como preservar la URL.

Códigos de éxito no-200 usados: **201** en 48 operaciones (35 con literal `201` + 13 con
`status.HTTP_201_CREATED`) y **204** en 17. El resto 200.

---

## 6. Resumen de la superficie por capa (Clean Architecture)

- **Capa propietaria de todo el HTTP**: `backend/api/*_router.py` (43 routers). Los routers
  importan directamente servicios de `backend/application/services/`, modelos de
  `backend/domain/models/` y, en algunos casos, infraestructura
  (`backend/infrastructure/...`). Es una Clean Architecture **pragmática**: hay routers que
  implementan lógica de negocio *inline* (p. ej. `pacientes_router.py:1221-1290` odontograma,
  `radiologia_router.py:180-235` importación) y routers que delegan en servicios de aplicación.
  **Para reconstruir un módulo, la unidad a portar es el trío router+servicio(s)+modelo(s)**, con
  la tabla de servicios/modelos importados de §7 como inventario de dependencias.
- **Servicios de aplicación**: 64 ficheros `.py` en `backend/application/services/` (medido con
  `ls application/services/*.py | wc -l`). Los servicios con más **importaciones desde `api/`** son
  `auth_service` (23), `config_service` (16), `agente_service` (9), `caja_service` (9) y
  `conciliacion_service` (9). `backend/domain/services/` tiene 17 ficheros de reglas puras.
- **Dominio puro**: `backend/domain/models/` (20 módulos, **142 tablas** — ver `PARIDAD-DATOS.md`)
  y `backend/domain/services/` (reglas puras: disponibilidad, cita_reglas, whatsapp flujos,
  invoice_extractor, classificador_factura, proveedor_resolver, verifactu…).
- **Infraestructura**: `backend/infrastructure/` (BBDD SQLModel + engine, Redis pub/sub SSE,
  scheduler APScheduler, clientes externos Evolution/IMAP/Drive/Orthanc/LLM, seguridad JWT,
  backups, Centinela). **En el rebuild a Oracle+serverless, Redis/scheduler/clientes externos
  deben salir de la función serverless**: el scheduler usa locks de Postgres y `BackgroundScheduler`
  (`infrastructure/scheduler.py:32-45`, `:359-410`) y el bus SSE depende de Redis
  (`infrastructure/realtime.py:1-20`). Esto es riesgo de arquitectura, no de contrato HTTP.
## 7. Resumen por módulo (router → rutas → capas que importa)

Cada fila permite ver de un vistazo qué router toca qué servicios y modelos: la unidad mínima de reconstrucción de un módulo. `—` = el router no importa nada de esa capa directamente.

| Módulo | Router | Rutas | GET | POST | PUT | PATCH | DELETE | WS | Servicios de aplicación importados | Modelos importados |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| `agenda` | `backend/api/agenda_router.py` | 11 | 6 | 1 | 4 | 0 | 0 | 0 | auth_service, config_service, disponibilidad_service | agenda, comunicacion, core, documentos, identidad |
| `agentes_db` | `backend/api/agentes_db_router.py` | 13 | 6 | 6 | 0 | 1 | 0 | 0 | agente_permisos_service, canal_ajuste_service, migrar_agentes_reales, personalidad_service | agentes |
| `agentes` | `backend/api/agentes_router.py` | 18 | 11 | 5 | 0 | 1 | 1 | 0 | agente_service, agentes_config, aura_admin, aura_agente, aura_service, auth_service, config_service, gestor_agente, victor_agente, victor_consulta_service, victor_service | — |
| `app_doctor` | `backend/api/app_doctor_router.py` | 13 | 9 | 3 | 0 | 0 | 1 | 0 | disponibilidad_service, multimedia_service | agenda, core, identidad, ortodoncia |
| `app_paciente` | `backend/api/app_paciente_router.py` | 9 | 8 | 1 | 0 | 0 | 0 | 0 | disponibilidad_service, produccion_service | agenda, core, economico |
| `auth` | `backend/api/auth_router.py` | 8 | 3 | 5 | 0 | 0 | 0 | 0 | auth_service, config_service | core, identidad |
| `casos_ortodoncia` | `backend/api/casos_ortodoncia_router.py` | 9 | 4 | 2 | 3 | 0 | 0 | 0 | comunicacion_service, estudio_ortodoncia_pdf | config, core, ortodoncia |
| `cefalometria` | `backend/api/cefalometria_router.py` | 9 | 5 | 2 | 0 | 0 | 2 | 0 | cefalometria_pdf, cefalometria_service | clinico |
| `chat` | `backend/api/chat_router.py` | 2 | 0 | 2 | 0 | 0 | 0 | 0 | — | — |
| `clinico` | `backend/api/clinico_router.py` | 15 | 6 | 4 | 3 | 0 | 2 | 0 | auth_service, caja_service, presupuesto_service, receta_pdf | agenda, clinico, core, documentos, economico, identidad |
| `comunicacion` | `backend/api/comunicacion_router.py` | 42 | 11 | 26 | 1 | 2 | 2 | 0 | agente_service, automatizacion_service, comunicacion_service, llm_config | comunicacion, config |
| `config` | `backend/api/config_router.py` | 4 | 3 | 0 | 1 | 0 | 0 | 0 | auth_service, config_service | auditoria |
| `configuracion_admin` | `backend/api/configuracion_admin_router.py` | 12 | 6 | 2 | 3 | 0 | 1 | 0 | auth_service, config_service | core, economico |
| `configuracion_agenda` | `backend/api/configuracion_agenda_router.py` | 20 | 1 | 7 | 5 | 0 | 7 | 0 | auth_service, config_service | agenda, core, identidad |
| `configuracion_centro` | `backend/api/configuracion_centro_router.py` | 12 | 3 | 3 | 5 | 0 | 1 | 0 | auth_service, config_service, services | agenda, config, core |
| `configuracion_roles` | `backend/api/configuracion_roles_router.py` | 4 | 1 | 1 | 1 | 0 | 1 | 0 | auth_service | identidad |
| `configuracion_staff` | `backend/api/configuracion_staff_router.py` | 11 | 5 | 3 | 3 | 0 | 0 | 0 | auth_service | agenda, core, documentos, identidad |
| `consentimientos` | `backend/api/consentimientos_router.py` | 14 | 9 | 4 | 0 | 0 | 1 | 0 | auth_service, comunicacion_service, consentimiento_pdf, services | core, documentos |
| `consulta` | `backend/api/consulta_router.py` | 13 | 4 | 7 | 1 | 0 | 1 | 0 | agentes_config, config_service, services | core, documentos |
| `crm` | `backend/api/crm_router.py` | 2 | 2 | 0 | 0 | 0 | 0 | 0 | crm_service | — |
| `dentia` | `backend/api/dentia_router.py` | 3 | 1 | 1 | 1 | 0 | 0 | 0 | multimedia_service | clinico |
| `documentos` | `backend/api/documentos_router.py` | 8 | 3 | 4 | 0 | 0 | 1 | 0 | auth_service, comunicacion_service, config_service | core, documentos, economico, identidad |
| `geo` | `backend/api/geo_router.py` | 5 | 5 | 0 | 0 | 0 | 0 | 0 | — | core |
| `gestor_ia` | `backend/api/gestor_ia_router.py` | 9 | 6 | 3 | 0 | 0 | 0 | 0 | gmail_ai_processor, intake_service | gestor_ia |
| `gestoria` | `backend/api/gestoria_router.py` | 86 | 37 | 35 | 4 | 4 | 6 | 0 | auth_service, conciliacion_service, config_service, extracto_archivo, gastos_export_service, gestoria_service, gmail_ai_processor, gmail_ingest_service, imputacion_service, intake_service, produccion_service | economico, gestoria, identidad |
| `health` | `backend/api/health_router.py` | 3 | 3 | 0 | 0 | 0 | 0 | 0 | — | — |
| `informes` | `backend/api/informes_router.py` | 13 | 5 | 6 | 1 | 0 | 1 | 0 | auth_service | informes |
| `inicio` | `backend/api/inicio_router.py` | 6 | 5 | 1 | 0 | 0 | 0 | 0 | auth_service, caja_service, inicio_paciente_service, pulso_service | — |
| `internal_tenant` | `backend/api/internal_tenant_router.py` | 8 | 1 | 3 | 3 | 0 | 1 | 0 | auth_service, provision_service | config, core, identidad |
| `jarvis_operador` | `backend/api/jarvis_operador_router.py` | 2 | 0 | 2 | 0 | 0 | 0 | 0 | agente_service, aura_agente, gestor_agente, services, victor_agente | — |
| `llm` | `backend/api/llm_router.py` | 2 | 1 | 1 | 0 | 0 | 0 | 0 | — | ortodoncia |
| `media` | `backend/api/media_router.py` | 1 | 1 | 0 | 0 | 0 | 0 | 0 | — | — |
| `motion` | `backend/api/motion_router.py` | 8 | 4 | 1 | 2 | 1 | 0 | 0 | automatizacion_service, automatizacion_triggers | — |
| `ollama_relay` | `backend/api/ollama_relay_router.py` | 1 | 1 | 0 | 0 | 0 | 0 | 0 | auth_service, llm_config | — |
| `paciente_auth` | `backend/api/paciente_auth_router.py` | 2 | 0 | 2 | 0 | 0 | 0 | 0 | paciente_auth_service | — |
| `pacientes` | `backend/api/pacientes_router.py` | 36 | 19 | 8 | 6 | 2 | 1 | 0 | auth_service, caja_service, config_service, formas_pago_service, multimedia_service | clinico, core, dental, documentos, economico, gestoria, identidad |
| `presupuestos` | `backend/api/presupuestos_router.py` | 15 | 4 | 9 | 1 | 0 | 1 | 0 | auth_service, authorization_service, caja_service, comunicacion_service, config_service, consentimiento_service, presupuesto_service | core, economico, identidad |
| `radiologia` | `backend/api/radiologia_router.py` | 18 | 8 | 6 | 1 | 1 | 2 | 0 | cefalometria_service, multimedia_service, radiologia_export_service, radiologia_pptx, radiologia_service | clinico, core |
| `romexis` | `backend/api/romexis_router.py` | 5 | 2 | 3 | 0 | 0 | 0 | 0 | multimedia_service | clinico, core |
| `superuser` | `backend/api/superuser_router.py` | 19 | 8 | 4 | 4 | 2 | 1 | 0 | centinela_service, config_service | — |
| `uploads` | `backend/api/uploads_router.py` | 1 | 0 | 1 | 0 | 0 | 0 | 0 | — | — |
| `voicebot` | `backend/api/voicebot_router.py` | 5 | 4 | 1 | 0 | 0 | 0 | 0 | auth_service, voicebot_service | — |
| `ws` | `backend/api/ws_router.py` | 1 | 0 | 0 | 0 | 0 | 0 | 1 | auth_service | — |


---

## 8. Inventario completo de operaciones (498)

Ordenado por módulo y línea de definición. `Auth` = puerta de autenticación; `Autorización` = permiso fino exigido. La columna `Evidencia` apunta al decorador exacto (`fichero:línea`).


### `agenda` — `backend/api/agenda_router.py` (11 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/agenda/referencias` | JWT centro +X-Centro-Id | citas.ver | Query(agenda_id: Optional[int]=Query(None)) | `dict`/JSON libre | 403,401,400 | `agenda_router.py:43` |
| 2 | GET | `/agenda/pacientes/buscar` | JWT centro +X-Centro-Id | citas.ver | Query(q: str=Query(..., min_length=2)) | `dict`/JSON libre | 403,401,400 | `agenda_router.py:94` |
| 3 | GET | `/agenda/citas` | JWT centro +X-Centro-Id | citas.ver | Query(fecha: Optional[date]=Query(None)) \| Query(desde: Optional[date]=Query(None)) \| Query(hasta: Optional[date]=Query(None)) \| Query(incluir_anuladas: bool=Query(False)) \| Qu… | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `agenda_router.py:129` |
| 4 | GET | `/agenda/panel` | JWT centro +X-Centro-Id | citas.ver | Query(fecha: date=Query(...)) \| Query(agenda_id: Optional[int]=Query(None)) | `dict`/JSON libre | 403,401,400 | `agenda_router.py:176` |
| 5 | GET | `/agenda/huecos` | JWT centro +X-Centro-Id | citas.ver | Query(agenda_id: Optional[int]=Query(None)) \| Query(colaborador_id: Optional[int]=Query(None)) \| Query(dias: int=Query(7, ge=1, le=30)) \| Query(duracion_min: int=Query(30, ge=5,… | `dict`/JSON libre | 403,401,400 | `agenda_router.py:242` |
| 6 | POST | `/agenda/citas` | JWT centro +X-Centro-Id | citas.editar | path/argumento data: CitaIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `agenda_router.py:294` |
| 7 | PUT | `/agenda/citas/{cita_id}` | JWT centro +X-Centro-Id | citas.editar | path/argumento cita_id: int \| path/argumento data: CitaIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `agenda_router.py:318` |
| 8 | PUT | `/agenda/citas/{cita_id}/mover` | JWT centro +X-Centro-Id | citas.editar | path/argumento cita_id: int \| path/argumento data: MoverIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `agenda_router.py:351` |
| 9 | PUT | `/agenda/citas/{cita_id}/anular` | JWT centro +X-Centro-Id | citas.editar | path/argumento cita_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `agenda_router.py:370` |
| 10 | PUT | `/agenda/citas/{cita_id}/estado` | JWT centro +X-Centro-Id | citas.editar | path/argumento cita_id: int \| path/argumento data: EstadoCitaIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `agenda_router.py:393` |
| 11 | GET | `/agenda/citas/{cita_id}/justificante` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento cita_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_400_BAD_REQUEST,403,401,400 | `agenda_router.py:416` |


### `agentes_db` — `backend/api/agentes_db_router.py` (13 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/agentes/db` | JWT centro +X-Centro-Id | config.ver | — | `dict`/JSON libre | 403,401,400 | `agentes_db_router.py:18` |
| 2 | GET | `/agentes/db/capacidades/catalogo` | JWT centro | config.ver | — | `dict`/JSON libre | 403,401 | `agentes_db_router.py:24` |
| 3 | POST | `/agentes/db/migrar-base` | JWT centro +X-Centro-Id | config.editar | — | `dict`/JSON libre | 403,401,400 | `agentes_db_router.py:30` |
| 4 | POST | `/agentes/db` | JWT centro +X-Centro-Id | config.editar | path/argumento data: CrearIn | `dict`/JSON libre | 403,401,400 | `agentes_db_router.py:51` |
| 5 | GET | `/agentes/db/{agente_id}` | JWT centro +X-Centro-Id | config.ver | path/argumento agente_id: int | `dict`/JSON libre | 404,403,401,400 | `agentes_db_router.py:58` |
| 6 | POST | `/agentes/db/{agente_id}/capacidades` | JWT centro +X-Centro-Id | config.editar | path/argumento agente_id: int \| path/argumento data: CapsIn | `dict`/JSON libre | 404,422,403,401,400 | `agentes_db_router.py:72` |
| 7 | PATCH | `/agentes/db/{agente_id}` | JWT centro +X-Centro-Id | config.editar | path/argumento agente_id: int \| path/argumento data: ActivacionIn | `dict`/JSON libre | 422,403,401,400 | `agentes_db_router.py:116` |
| 8 | GET | `/agentes/db/{agente_id}/personalidad/{capa}` | JWT centro +X-Centro-Id | config.ver | path/argumento agente_id: int \| path/argumento capa: str | `dict`/JSON libre | 403,401,400 | `agentes_db_router.py:145` |
| 9 | POST | `/agentes/db/{agente_id}/personalidad/{capa}` | JWT centro +X-Centro-Id | config.editar | path/argumento agente_id: int \| path/argumento capa: str \| path/argumento data: PersonalidadIn | `dict`/JSON libre | 403,401,400 | `agentes_db_router.py:153` |
| 10 | GET | `/agentes/db/{agente_id}/permisos` | JWT centro +X-Centro-Id | config.ver | path/argumento agente_id: int | `dict`/JSON libre | 403,401,400 | `agentes_db_router.py:168` |
| 11 | POST | `/agentes/db/{agente_id}/permisos` | JWT centro +X-Centro-Id | config.editar | path/argumento agente_id: int \| path/argumento data: PermisoIn | `dict`/JSON libre | 403,401,400 | `agentes_db_router.py:176` |
| 12 | GET | `/agentes/db/{agente_id}/canal/{canal}` | JWT centro +X-Centro-Id | config.ver | path/argumento agente_id: int \| path/argumento canal: str | `dict`/JSON libre | 403,401,400 | `agentes_db_router.py:191` |
| 13 | POST | `/agentes/db/{agente_id}/canal/{canal}` | JWT centro +X-Centro-Id | config.editar | path/argumento agente_id: int \| path/argumento canal: str \| path/argumento data: CanalIn | `dict`/JSON libre | 403,401,400 | `agentes_db_router.py:199` |


### `agentes` — `backend/api/agentes_router.py` (18 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/agentes` | JWT centro +X-Centro-Id | config.ver | — | `dict`/JSON libre | 403,401,400 | `agentes_router.py:42` |
| 2 | GET | `/agentes/estado/todos` | JWT centro +X-Centro-Id | config.ver | — | `dict`/JSON libre | 403,401,400 | `agentes_router.py:54` |
| 3 | GET | `/agentes/permisos/catalogo` | JWT centro +X-Centro-Id | config.ver | — | `dict`/JSON libre | 403,401,400 | `agentes_router.py:64` |
| 4 | GET | `/agentes/{agente_id}` | JWT centro +X-Centro-Id | config.ver | path/argumento agente_id: str | `dict`/JSON libre | 403,401,400 | `agentes_router.py:79` |
| 5 | PATCH | `/agentes/{agente_id}/config` | JWT centro +X-Centro-Id | config.editar | path/argumento agente_id: str \| path/argumento data: ToggleIn | `dict`/JSON libre | status.HTTP_403_FORBIDDEN,403,401,400 | `agentes_router.py:95` |
| 6 | POST | `/agentes/victor/agenda/bloquear` | JWT centro +X-Centro-Id | citas.editar | path/argumento data: BloqueoIn | `dict`/JSON libre | 403,401,400 | `agentes_router.py:183` |
| 7 | DELETE | `/agentes/victor/agenda/bloqueo/{bloqueo_id}` | JWT centro +X-Centro-Id | citas.editar | path/argumento bloqueo_id: int | `dict`/JSON libre | 403,401,400 | `agentes_router.py:200` |
| 8 | GET | `/agentes/victor/informes/pacientes-sin-venir` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento meses: int=12 \| path/argumento limite: int=200 | `dict`/JSON libre | 403,401,400 | `agentes_router.py:210` |
| 9 | GET | `/agentes/victor/resumen-dia` | JWT centro +X-Centro-Id | citas.ver | path/argumento fecha: Optional[str]=None | `dict`/JSON libre | 403,401,400 | `agentes_router.py:219` |
| 10 | POST | `/agentes/victor/chat` | JWT centro +X-Centro-Id | citas.ver | path/argumento data: VictorChatIn | `dict`/JSON libre | 403,401,400 | `agentes_router.py:232` |
| 11 | POST | `/agentes/gestor/chat` | JWT centro +X-Centro-Id | gestoria.ver | path/argumento data: GestorChatIn | `dict`/JSON libre | 403,401,400 | `agentes_router.py:249` |
| 12 | GET | `/agentes/victor/consulta/estado` | JWT centro +X-Centro-Id | pacientes.ver | — | `dict`/JSON libre | 403,401,400 | `agentes_router.py:262` |
| 13 | POST | `/agentes/victor/consulta/escuchar` | JWT centro +X-Centro-Id | pacientes.editar | File(audio: UploadFile=File(...)) \| Form(cita_id: int=Form(...)) \| Form(paciente_id: int=Form(...)) | `dict`/JSON libre | 403,401,400 | `agentes_router.py:274` |
| 14 | GET | `/agentes/aura/metricas` | JWT centro +X-Centro-Id | superuser | — | `dict`/JSON libre | 403,401,400 | `agentes_router.py:310` |
| 15 | GET | `/agentes/aura/auditoria` | JWT centro +X-Centro-Id | superuser | path/argumento accion: Optional[str]=None \| path/argumento dias: int=7 | `dict`/JSON libre | 403,401,400 | `agentes_router.py:319` |
| 16 | GET | `/agentes/aura/usuarios` | JWT centro +X-Centro-Id | superuser | — | `dict`/JSON libre | 403,401,400 | `agentes_router.py:329` |
| 17 | POST | `/agentes/aura/chat` | JWT centro +X-Centro-Id | superuser | path/argumento data: AuraChatIn | `dict`/JSON libre | 403,401,400 | `agentes_router.py:343` |
| 18 | GET | `/agentes/aura/centinela` | JWT centro +X-Centro-Id | superuser | — | `dict`/JSON libre | status.HTTP_403_FORBIDDEN,403,401,400 | `agentes_router.py:360` |


### `app_doctor` — `backend/api/app_doctor_router.py` (13 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/app/doctores/me/perfil` | JWT centro +X-Centro-Id | — | — | `dict`/JSON libre | 401,400 | `app_doctor_router.py:74` |
| 2 | GET | `/app/doctores/me/agenda` | JWT centro +X-Centro-Id | — | Query(fecha: Optional[date]=Query(None)) \| Query(solo_mias: bool=Query(False)) | `dict`/JSON libre | 401,400 | `app_doctor_router.py:108` |
| 3 | GET | `/app/doctores/me/pacientes` | JWT centro +X-Centro-Id | — | Query(q: str=Query(..., min_length=2)) | `dict`/JSON libre | 401,400 | `app_doctor_router.py:136` |
| 4 | GET | `/app/doctores/me/pacientes/{paciente_id}` | JWT centro +X-Centro-Id | — | path/argumento paciente_id: int | `dict`/JSON libre | 401,400 | `app_doctor_router.py:155` |
| 5 | GET | `/app/doctores/me/protocolo` | JWT centro | — | — | `dict`/JSON libre | 401 | `app_doctor_router.py:181` |
| 6 | POST | `/app/doctores/me/estudios` | JWT centro +X-Centro-Id | — | path/argumento data: CrearEstudioIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,status.HTTP_400_BAD_REQUEST,401,400 | `app_doctor_router.py:211` |
| 7 | GET | `/app/doctores/me/estudios` | JWT centro +X-Centro-Id | — | Query(paciente_id: int=Query(...)) | `dict`/JSON libre | 401,400 | `app_doctor_router.py:234` |
| 8 | GET | `/app/doctores/me/estudios/{estudio_id}` | JWT centro +X-Centro-Id | — | path/argumento estudio_id: int | `dict`/JSON libre | 401,400 | `app_doctor_router.py:254` |
| 9 | POST | `/app/doctores/me/estudios/{estudio_id}/completar` | JWT centro +X-Centro-Id | — | path/argumento estudio_id: int \| path/argumento data: CompletarEstudioIn | `dict`/JSON libre | 401,400 | `app_doctor_router.py:270` |
| 10 | POST | `/app/doctores/me/estudios/{estudio_id}/fotos` | JWT centro +X-Centro-Id | — | path/argumento estudio_id: int \| Query(tipo: str=Query(...)) \| File(file: UploadFile=File(...)) | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,401,400 | `app_doctor_router.py:286` |
| 11 | GET | `/app/doctores/me/fotos/{foto_id}` | JWT centro +X-Centro-Id | — | path/argumento foto_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,401,400 | `app_doctor_router.py:345` |
| 12 | DELETE | `/app/doctores/me/fotos/{foto_id}` | JWT centro +X-Centro-Id | — | path/argumento foto_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,401,400 | `app_doctor_router.py:359` |
| 13 | GET | `/app/doctores/me/stream` | JWT centro +X-Centro-Id | — | — | `dict`/JSON libre | 401,400 | `app_doctor_router.py:403` |


### `app_paciente` — `backend/api/app_paciente_router.py` (9 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/app/pacientes/me/perfil` | JWT paciente | — | — | `dict`/JSON libre | 401 | `app_paciente_router.py:66` |
| 2 | GET | `/app/pacientes/me/tratamientos` | JWT paciente | — | — | `dict`/JSON libre | 401 | `app_paciente_router.py:77` |
| 3 | GET | `/app/pacientes/me/presupuestos` | JWT paciente | — | — | `dict`/JSON libre | 401 | `app_paciente_router.py:84` |
| 4 | GET | `/app/pacientes/me/huecos` | JWT paciente | — | path/argumento dias: int=14 | `dict`/JSON libre | 401 | `app_paciente_router.py:91` |
| 5 | POST | `/app/pacientes/me/citas/solicitar` | JWT paciente | — | path/argumento data: SolicitarCitaIn | `dict`/JSON libre | status.HTTP_400_BAD_REQUEST,status.HTTP_500_INTERNAL_SERVER_ERROR,401 | `app_paciente_router.py:105` |
| 6 | GET | `/app/pacientes/me/facturas` | JWT paciente | — | — | `dict`/JSON libre | 401 | `app_paciente_router.py:159` |
| 7 | GET | `/app/pacientes/me/facturas/{numero}/pdf` | JWT paciente | — | path/argumento numero: str | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,401 | `app_paciente_router.py:179` |
| 8 | GET | `/app/pacientes/me/justificantes/{acto_id}/pdf` | JWT paciente | — | path/argumento acto_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,401 | `app_paciente_router.py:196` |
| 9 | GET | `/app/pacientes/me/stream` | JWT paciente | — | — | `dict`/JSON libre | 401 | `app_paciente_router.py:226` |


### `auth` — `backend/api/auth_router.py` (8 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/auth/apariencia` | **NINguna** | — | — | `dict`/JSON libre | — | `auth_router.py:22` |
| 2 | GET | `/auth/apariencia/imagen/{campo}` | **NINguna** | — | path/argumento campo: str | `dict`/JSON libre | status.HTTP_404_NOT_FOUND | `auth_router.py:32` |
| 3 | POST | `/auth/login` | **NINguna** | — | path/argumento data: LoginRequest | `dict`/JSON libre | — | `auth_router.py:65` |
| 4 | POST | `/auth/login-cookie` | **NINguna** | — | path/argumento data: LoginRequest | `dict`/JSON libre | — | `auth_router.py:71` |
| 5 | POST | `/auth/logout` |  | — | — | `dict`/JSON libre | 200 | `auth_router.py:94` |
| 6 | POST | `/auth/forgot` | **NINguna** | — | path/argumento data: ForgotRequest | `dict`/JSON libre | — | `auth_router.py:101` |
| 7 | POST | `/auth/reset` | **NINguna** | — | path/argumento data: ResetRequest | `dict`/JSON libre | status.HTTP_400_BAD_REQUEST | `auth_router.py:112` |
| 8 | GET | `/auth/me` | JWT centro +X-Centro-Id | — | — | `dict`/JSON libre | 401,400 | `auth_router.py:122` |


### `casos_ortodoncia` — `backend/api/casos_ortodoncia_router.py` (9 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/pacientes/{paciente_id}/estudios-ortodoncia` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `casos_ortodoncia_router.py:66` |
| 2 | GET | `/pacientes/{paciente_id}/estudios-ortodoncia/{estudio_id}/informe.pdf` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int \| path/argumento estudio_id: int | `dict`/JSON libre | 403,401,400 | `casos_ortodoncia_router.py:91` |
| 3 | POST | `/pacientes/{paciente_id}/estudios-ortodoncia/{estudio_id}/enviar` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int \| path/argumento estudio_id: int \| path/argumento datos: EnviarEstudioIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,status.HTTP_502_BAD_GATEWAY,403,401,400 | `casos_ortodoncia_router.py:107` |
| 4 | POST | `/pacientes/{paciente_id}/casos-ortodoncia` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: CasoOrtodonciaIn | `dict`/JSON libre | 403,401,400 | `casos_ortodoncia_router.py:154` |
| 5 | GET | `/pacientes/{paciente_id}/casos-ortodoncia` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `casos_ortodoncia_router.py:177` |
| 6 | PUT | `/pacientes/{paciente_id}/casos-ortodoncia/{caso_id}/mediciones` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento caso_id: int \| path/argumento data: MedicionesIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `casos_ortodoncia_router.py:206` |
| 7 | PUT | `/pacientes/{paciente_id}/casos-ortodoncia/{caso_id}/diagnostico` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento caso_id: int \| path/argumento data: DiagnosticoIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `casos_ortodoncia_router.py:225` |
| 8 | PUT | `/pacientes/{paciente_id}/casos-ortodoncia/{caso_id}/plan` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento caso_id: int \| path/argumento data: PlanIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `casos_ortodoncia_router.py:246` |
| 9 | GET | `/pacientes/{paciente_id}/casos-ortodoncia/{caso_id}` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int \| path/argumento caso_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `casos_ortodoncia_router.py:265` |


### `cefalometria` — `backend/api/cefalometria_router.py` (9 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/cefalometria/definicion` | JWT centro +X-Centro-Id | — | path/argumento analisis: str='steiner' | DefinicionResp | status.HTTP_404_NOT_FOUND,401,400 | `cefalometria_router.py:98` |
| 2 | GET | `/radiologia/{imagen_id}/cefalometria` | JWT centro +X-Centro-Id | — | path/argumento imagen_id: int | list[TrazadoDTO] | 401,400 | `cefalometria_router.py:119` |
| 3 | POST | `/radiologia/{imagen_id}/cefalometria` | JWT centro +X-Centro-Id | — | path/argumento imagen_id: int \| path/argumento datos: TrazadoIn | TrazadoDTO | status.HTTP_422_UNPROCESSABLE_ENTITY,401,400 | `cefalometria_router.py:128` |
| 4 | GET | `/cefalometria/analisis` | JWT centro +X-Centro-Id | — | — | list[AnalisisCustomDTO] | 401,400 | `cefalometria_router.py:201` |
| 5 | POST | `/cefalometria/analisis` | JWT centro +X-Centro-Id | — | path/argumento datos: AnalisisCustomIn | AnalisisCustomDTO | status.HTTP_422_UNPROCESSABLE_ENTITY,401,400 | `cefalometria_router.py:210` |
| 6 | DELETE | `/cefalometria/analisis/{analisis_id}` | JWT centro +X-Centro-Id | — | path/argumento analisis_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,401,400 | `cefalometria_router.py:231` |
| 7 | GET | `/pacientes/{paciente_id}/cefalometria/comparar` | JWT centro +X-Centro-Id | — | path/argumento paciente_id: int \| path/argumento analisis: str='steiner' | ComparativaResp | 401,400 | `cefalometria_router.py:254` |
| 8 | GET | `/radiologia/{imagen_id}/cefalometria/{analisis}/informe.pdf` | JWT centro +X-Centro-Id | — | path/argumento imagen_id: int \| path/argumento analisis: str | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,401,400 | `cefalometria_router.py:290` |
| 9 | DELETE | `/cefalometria/{trazado_id}` | JWT centro +X-Centro-Id | — | path/argumento trazado_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,401,400 | `cefalometria_router.py:320` |


### `chat` — `backend/api/chat_router.py` (2 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | POST | `/chat/stream` | JWT centro | chat.usar | — | `dict`/JSON libre | 403,401 | `chat_router.py:53` |
| 2 | POST | `/chat/complete` | JWT centro | chat.usar | — | `dict`/JSON libre | 403,401 | `chat_router.py:83` |


### `clinico` — `backend/api/clinico_router.py` (15 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/pacientes/{paciente_id}/recetas` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `clinico_router.py:45` |
| 2 | GET | `/pacientes/{paciente_id}/recetas/{receta_id}/pdf` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int \| path/argumento receta_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `clinico_router.py:79` |
| 3 | POST | `/pacientes/{paciente_id}/actos` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: ActoIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `clinico_router.py:250` |
| 4 | PUT | `/pacientes/{paciente_id}/actos/{acto_id}` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento acto_id: int \| path/argumento data: ActoEdit | `dict`/JSON libre | 403,401,400 | `clinico_router.py:366` |
| 5 | DELETE | `/pacientes/{paciente_id}/actos/{acto_id}` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento acto_id: int | `dict`/JSON libre | 403,401,400 | `clinico_router.py:396` |
| 6 | GET | `/pacientes/{paciente_id}/previstos` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `clinico_router.py:417` |
| 7 | GET | `/pacientes/{paciente_id}/alertas` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `clinico_router.py:457` |
| 8 | POST | `/pacientes/{paciente_id}/alertas` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: AlertaIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `clinico_router.py:493` |
| 9 | PUT | `/pacientes/{paciente_id}/alertas/{alerta_id}` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento alerta_id: int \| path/argumento data: AlertaUpd | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `clinico_router.py:513` |
| 10 | POST | `/pacientes/{paciente_id}/medicaciones` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: MedicIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `clinico_router.py:537` |
| 11 | GET | `/pacientes/{paciente_id}/cascabel` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `clinico_router.py:560` |
| 12 | GET | `/pacientes/{paciente_id}/plan-proxima` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `clinico_router.py:608` |
| 13 | PUT | `/pacientes/{paciente_id}/plan-proxima` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: PlanIn | `dict`/JSON libre | 403,401,400 | `clinico_router.py:634` |
| 14 | DELETE | `/pacientes/{paciente_id}/plan-proxima` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `clinico_router.py:656` |
| 15 | POST | `/pacientes/{paciente_id}/plan-proxima/agendar` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `clinico_router.py:670` |


### `comunicacion` — `backend/api/comunicacion_router.py` (42 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/comunicacion/whatsapp/estado` | JWT centro +X-Centro-Id | comunicacion.ver | — | `dict`/JSON libre | 403,401,400 | `comunicacion_router.py:50` |
| 2 | GET | `/comunicacion/ia/estado` | JWT centro +X-Centro-Id | comunicacion.ver | — | `dict`/JSON libre | 403,401,400 | `comunicacion_router.py:60` |
| 3 | POST | `/comunicacion/ia/pausar` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento data: PausarIaIn | `dict`/JSON libre | 403,401,400 | `comunicacion_router.py:71` |
| 4 | POST | `/comunicacion/ia/reanudar` | JWT centro +X-Centro-Id | comunicacion.editar | — | `dict`/JSON libre | 403,401,400 | `comunicacion_router.py:79` |
| 5 | GET | `/comunicacion/whatsapp/qr` | JWT centro +X-Centro-Id | comunicacion.ver | — | `dict`/JSON libre | 403,401,400 | `comunicacion_router.py:86` |
| 6 | POST | `/comunicacion/whatsapp/desvincular` | JWT centro +X-Centro-Id | comunicacion.editar | — | `dict`/JSON libre | 403,401,400 | `comunicacion_router.py:93` |
| 7 | POST | `/comunicacion/whatsapp/enviar` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento data: EnviarIn | `dict`/JSON libre | status.HTTP_502_BAD_GATEWAY,403,401,400 | `comunicacion_router.py:107` |
| 8 | POST | `/comunicacion/whatsapp/enviar-media` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento telefono: str \| File(file: UploadFile=File(...)) \| Form(caption: str=Form('')) | `dict`/JSON libre | status.HTTP_502_BAD_GATEWAY,403,401,400 | `comunicacion_router.py:124` |
| 9 | GET | `/comunicacion/stream` | JWT centro +X-Centro-Id | comunicacion.ver | — | `dict`/JSON libre | 403,401,400 | `comunicacion_router.py:140` |
| 10 | GET | `/comunicacion/conversaciones` | JWT centro +X-Centro-Id | comunicacion.ver | path/argumento archivadas: bool=False | `dict`/JSON libre | 403,401,400 | `comunicacion_router.py:160` |
| 11 | GET | `/comunicacion/conversaciones/{conv_id}/mensajes` | JWT centro +X-Centro-Id | comunicacion.ver | path/argumento conv_id: int | `dict`/JSON libre | 403,401,400 | `comunicacion_router.py:168` |
| 12 | POST | `/comunicacion/conversaciones/{conv_id}/mensajes` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento conv_id: int \| path/argumento data: ResponderIn | `dict`/JSON libre | status.HTTP_502_BAD_GATEWAY,status.HTTP_500_INTERNAL_SERVER_ERROR,403,401,400 | `comunicacion_router.py:180` |
| 13 | PATCH | `/comunicacion/conversaciones/{conv_id}/mensajes/{msg_id}` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento conv_id: int \| path/argumento msg_id: int \| path/argumento data: EditarMensajeIn | `dict`/JSON libre | status.HTTP_409_CONFLICT,status.HTTP_502_BAD_GATEWAY,403,401,400 | `comunicacion_router.py:205` |
| 14 | DELETE | `/comunicacion/conversaciones/{conv_id}/mensajes/{msg_id}` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento conv_id: int \| path/argumento msg_id: int | `dict`/JSON libre | status.HTTP_409_CONFLICT,status.HTTP_502_BAD_GATEWAY,403,401,400 | `comunicacion_router.py:222` |
| 15 | POST | `/comunicacion/conversaciones/{conv_id}/media` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento conv_id: int \| File(file: UploadFile=File(...)) \| Form(caption: str=Form('')) | `dict`/JSON libre | 403,401,400 | `comunicacion_router.py:239` |
| 16 | POST | `/comunicacion/conversaciones/{conv_id}/leida` | JWT centro +X-Centro-Id | comunicacion.ver | path/argumento conv_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `comunicacion_router.py:251` |
| 17 | PATCH | `/comunicacion/conversaciones/{conv_id}/estado` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento conv_id: int \| path/argumento data: EstadoIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `comunicacion_router.py:265` |
| 18 | POST | `/comunicacion/conversaciones/{conv_id}/archivar` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento conv_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `comunicacion_router.py:275` |
| 19 | POST | `/comunicacion/conversaciones/{conv_id}/desarchivar` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento conv_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `comunicacion_router.py:285` |
| 20 | POST | `/comunicacion/conversaciones/{conv_id}/flujo/cortar` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento conv_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `comunicacion_router.py:295` |
| 21 | POST | `/comunicacion/conversaciones/{conv_id}/ia/pausar` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento conv_id: int \| path/argumento data: PausarConvIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `comunicacion_router.py:311` |
| 22 | POST | `/comunicacion/conversaciones/{conv_id}/ia/reanudar` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento conv_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `comunicacion_router.py:324` |
| 23 | POST | `/comunicacion/conversaciones/{conv_id}/notas` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento conv_id: int \| path/argumento data: NotaIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `comunicacion_router.py:339` |
| 24 | POST | `/comunicacion/conversaciones/{conv_id}/no-leida` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento conv_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `comunicacion_router.py:350` |
| 25 | POST | `/comunicacion/conversaciones/{conv_id}/fijar-conv` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento conv_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `comunicacion_router.py:360` |
| 26 | POST | `/comunicacion/conversaciones/{conv_id}/desfijar-conv` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento conv_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `comunicacion_router.py:370` |
| 27 | POST | `/comunicacion/conversaciones/{conv_id}/urgente` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento conv_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `comunicacion_router.py:380` |
| 28 | POST | `/comunicacion/conversaciones/{conv_id}/no-urgente` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento conv_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `comunicacion_router.py:390` |
| 29 | GET | `/comunicacion/contexto/{telefono}` | JWT centro +X-Centro-Id | comunicacion.ver | path/argumento telefono: str | `dict`/JSON libre | 403,401,400 | `comunicacion_router.py:401` |
| 30 | GET | `/comunicacion/plantillas` | JWT centro +X-Centro-Id | comunicacion.ver | — | `dict`/JSON libre | 403,401,400 | `comunicacion_router.py:419` |
| 31 | PUT | `/comunicacion/plantillas` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento data: PlantillaIn | `dict`/JSON libre | 403,401,400 | `comunicacion_router.py:426` |
| 32 | DELETE | `/comunicacion/plantillas/{pid}` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento pid: int | `dict`/JSON libre | 403,401,400 | `comunicacion_router.py:436` |
| 33 | POST | `/comunicacion/agente/probar` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento data: ProbarAgenteIn | `dict`/JSON libre | 403,401,400 | `comunicacion_router.py:449` |
| 34 | POST | `/comunicacion/agente/chat` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento data: ChatAgenteIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `comunicacion_router.py:480` |
| 35 | POST | `/comunicacion/agente/chat/corregir` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento data: CorreccionIn | `dict`/JSON libre | 403,401,400 | `comunicacion_router.py:505` |
| 36 | GET | `/comunicacion/agente/revisiones` | JWT centro +X-Centro-Id | comunicacion.ver | — | `dict`/JSON libre | 403,401,400 | `comunicacion_router.py:516` |
| 37 | POST | `/comunicacion/agente/revisiones/{revision_id}` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento revision_id: int \| path/argumento data: ResolverRevisionIn | `dict`/JSON libre | 403,401,400 | `comunicacion_router.py:531` |
| 38 | GET | `/comunicacion/estadisticas` | JWT centro +X-Centro-Id | comunicacion.ver | path/argumento dias: int=30 | `dict`/JSON libre | 403,401,400 | `comunicacion_router.py:547` |
| 39 | GET | `/comunicacion/llm/modelos-disponibles` | JWT centro +X-Centro-Id | comunicacion.ver | path/argumento agente: str | `dict`/JSON libre | status.HTTP_409_CONFLICT,status.HTTP_502_BAD_GATEWAY,403,401,400 | `comunicacion_router.py:577` |
| 40 | POST | `/comunicacion/automatizacion/preview` | JWT centro +X-Centro-Id | comunicacion.ver | — | `dict`/JSON libre | 403,401,400 | `comunicacion_router.py:600` |
| 41 | POST | `/comunicacion/automatizacion/ejecutar` | JWT centro +X-Centro-Id | comunicacion.editar | — | `dict`/JSON libre | status.HTTP_409_CONFLICT,403,401,400 | `comunicacion_router.py:608` |
| 42 | POST | `/comunicacion/webhook/{centro_id}` |  | — | path/argumento centro_id: int \| path/argumento token: str \| None=None | `dict`/JSON libre | 401 | `comunicacion_router.py:623` |


### `config` — `backend/api/config_router.py` (4 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/config` | JWT centro +X-Centro-Id | — | path/argumento sistema: Optional[str]=None | `dict`/JSON libre | 401,400 | `config_router.py:27` |
| 2 | PUT | `/config` | JWT centro +X-Centro-Id | config.editar | path/argumento data: ConfigSet | `dict`/JSON libre | 403,401,400 | `config_router.py:39` |
| 3 | GET | `/config/centinela/nivel` | JWT centro +X-Centro-Id | — | — | `dict`/JSON libre | 401,400 | `config_router.py:59` |
| 4 | GET | `/config/centinela/contenedores` | JWT centro | config.editar | — | `dict`/JSON libre | 403,401 | `config_router.py:78` |


### `configuracion_admin` — `backend/api/configuracion_admin_router.py` (12 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/configuracion/admin/tablas` | JWT centro +X-Centro-Id | config.editar | — | `dict`/JSON libre | 403,401,400 | `configuracion_admin_router.py:77` |
| 2 | GET | `/configuracion/admin/tabla/{nombre}` | JWT centro +X-Centro-Id | config.editar | path/argumento nombre: str \| Query(limit: int=Query(50, ge=1, le=500)) \| Query(offset: int=Query(0, ge=0)) | `dict`/JSON libre | 403,401,400 | `configuracion_admin_router.py:98` |
| 3 | GET | `/configuracion/admin/tabla/{nombre}/export` | JWT centro +X-Centro-Id | config.editar | path/argumento nombre: str | `dict`/JSON libre | 403,401,400 | `configuracion_admin_router.py:138` |
| 4 | PUT | `/configuracion/admin/tabla/{nombre}/fila` | JWT centro +X-Centro-Id | config.editar | path/argumento nombre: str \| path/argumento data: FilaIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,status.HTTP_404_NOT_FOUND,status.HTTP_400_BAD_REQUEST,403,401,400 | `configuracion_admin_router.py:177` |
| 5 | POST | `/configuracion/admin/tabla/{nombre}/import` | JWT centro +X-Centro-Id | config.editar | path/argumento nombre: str \| File(file: UploadFile=File(...)) | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,status.HTTP_400_BAD_REQUEST,403,401,400 | `configuracion_admin_router.py:227` |
| 6 | GET | `/configuracion/admin/predisenados-tratamientos` | JWT centro +X-Centro-Id | config.editar | Query(q: str=Query(..., min_length=2)) | `dict`/JSON libre | 403,401,400 | `configuracion_admin_router.py:314` |
| 7 | GET | `/configuracion/admin/presupuestos-predisenados` | JWT centro +X-Centro-Id | config.editar | — | `dict`/JSON libre | 403,401,400 | `configuracion_admin_router.py:335` |
| 8 | POST | `/configuracion/admin/presupuestos-predisenados` | JWT centro +X-Centro-Id | config.editar | path/argumento data: PredisenadoIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `configuracion_admin_router.py:370` |
| 9 | PUT | `/configuracion/admin/presupuestos-predisenados/{pid}` | JWT centro +X-Centro-Id | config.editar | path/argumento pid: int \| path/argumento data: PredisenadoIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,status.HTTP_404_NOT_FOUND,403,401,400 | `configuracion_admin_router.py:391` |
| 10 | DELETE | `/configuracion/admin/presupuestos-predisenados/{pid}` | JWT centro +X-Centro-Id | config.editar | path/argumento pid: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `configuracion_admin_router.py:416` |
| 11 | GET | `/configuracion/admin/documentos` | JWT centro +X-Centro-Id | config.editar | — | `dict`/JSON libre | 403,401,400 | `configuracion_admin_router.py:439` |
| 12 | PUT | `/configuracion/admin/documentos` | JWT centro +X-Centro-Id | config.editar | path/argumento data: DocsIn | `dict`/JSON libre | 403,401,400 | `configuracion_admin_router.py:450` |


### `configuracion_agenda` — `backend/api/configuracion_agenda_router.py` (20 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/configuracion/agenda` | JWT centro +X-Centro-Id | — | — | `dict`/JSON libre | 401,400 | `configuracion_agenda_router.py:75` |
| 2 | POST | `/configuracion/agenda/agendas` | JWT centro +X-Centro-Id | config.editar | path/argumento data: AgendaIn | `dict`/JSON libre | 403,401,400 | `configuracion_agenda_router.py:116` |
| 3 | PUT | `/configuracion/agenda/agendas/{agenda_id}` | JWT centro +X-Centro-Id | config.editar | path/argumento agenda_id: int \| path/argumento data: AgendaIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `configuracion_agenda_router.py:123` |
| 4 | DELETE | `/configuracion/agenda/agendas/{agenda_id}` | JWT centro +X-Centro-Id | config.editar | path/argumento agenda_id: int | `dict`/JSON libre | 403,401,400 | `configuracion_agenda_router.py:134` |
| 5 | POST | `/configuracion/agenda/tipos` | JWT centro +X-Centro-Id | config.editar | path/argumento data: TipoCitaIn | `dict`/JSON libre | 403,401,400 | `configuracion_agenda_router.py:151` |
| 6 | PUT | `/configuracion/agenda/tipos/{tipo_id}` | JWT centro +X-Centro-Id | config.editar | path/argumento tipo_id: int \| path/argumento data: TipoCitaIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `configuracion_agenda_router.py:159` |
| 7 | DELETE | `/configuracion/agenda/tipos/{tipo_id}` | JWT centro +X-Centro-Id | config.editar | path/argumento tipo_id: int | `dict`/JSON libre | 403,401,400 | `configuracion_agenda_router.py:171` |
| 8 | POST | `/configuracion/agenda/estados` | JWT centro +X-Centro-Id | config.editar | path/argumento data: EstadoIn | `dict`/JSON libre | 403,401,400 | `configuracion_agenda_router.py:189` |
| 9 | PUT | `/configuracion/agenda/estados/{estado_id}` | JWT centro +X-Centro-Id | config.editar | path/argumento estado_id: int \| path/argumento data: EstadoIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `configuracion_agenda_router.py:202` |
| 10 | DELETE | `/configuracion/agenda/estados/{estado_id}` | JWT centro +X-Centro-Id | config.editar | path/argumento estado_id: int | `dict`/JSON libre | 403,401,400 | `configuracion_agenda_router.py:213` |
| 11 | POST | `/configuracion/agenda/gabinetes` | JWT centro +X-Centro-Id | config.editar | path/argumento data: GabineteIn | `dict`/JSON libre | 403,401,400 | `configuracion_agenda_router.py:229` |
| 12 | PUT | `/configuracion/agenda/gabinetes/{gabinete_id}` | JWT centro +X-Centro-Id | config.editar | path/argumento gabinete_id: int \| path/argumento data: GabineteIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `configuracion_agenda_router.py:237` |
| 13 | DELETE | `/configuracion/agenda/gabinetes/{gabinete_id}` | JWT centro +X-Centro-Id | config.editar | path/argumento gabinete_id: int | `dict`/JSON libre | 403,401,400 | `configuracion_agenda_router.py:248` |
| 14 | POST | `/configuracion/agenda/horarios` | JWT centro +X-Centro-Id | config.editar | path/argumento data: HorarioIn | `dict`/JSON libre | 403,401,400 | `configuracion_agenda_router.py:270` |
| 15 | PUT | `/configuracion/agenda/horarios/{horario_id}` | JWT centro +X-Centro-Id | config.editar | path/argumento horario_id: int \| path/argumento data: HorarioIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `configuracion_agenda_router.py:278` |
| 16 | DELETE | `/configuracion/agenda/horarios/{horario_id}` | JWT centro +X-Centro-Id | config.editar | path/argumento horario_id: int | `dict`/JSON libre | 403,401,400 | `configuracion_agenda_router.py:290` |
| 17 | POST | `/configuracion/agenda/excepciones` | JWT centro +X-Centro-Id | config.editar | path/argumento data: ExcepcionIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `configuracion_agenda_router.py:311` |
| 18 | DELETE | `/configuracion/agenda/excepciones/{excepcion_id}` | JWT centro +X-Centro-Id | config.editar | path/argumento excepcion_id: int | `dict`/JSON libre | 403,401,400 | `configuracion_agenda_router.py:320` |
| 19 | POST | `/configuracion/agenda/bloqueos` | JWT centro +X-Centro-Id | config.editar | path/argumento data: BloqueoIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `configuracion_agenda_router.py:338` |
| 20 | DELETE | `/configuracion/agenda/bloqueos/{bloqueo_id}` | JWT centro +X-Centro-Id | config.editar | path/argumento bloqueo_id: int | `dict`/JSON libre | 403,401,400 | `configuracion_agenda_router.py:349` |


### `configuracion_centro` — `backend/api/configuracion_centro_router.py` (12 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/configuracion/centro` | JWT centro +X-Centro-Id | — | — | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,401,400 | `configuracion_centro_router.py:127` |
| 2 | PUT | `/configuracion/centro/datos` | JWT centro +X-Centro-Id | config.editar | path/argumento data: CentroIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `configuracion_centro_router.py:150` |
| 3 | PUT | `/configuracion/centro/razon-social/{razon_id}` | JWT centro +X-Centro-Id | config.editar | path/argumento razon_id: int \| path/argumento data: RazonIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `configuracion_centro_router.py:165` |
| 4 | PUT | `/configuracion/centro/config` | JWT centro +X-Centro-Id | config.editar | path/argumento data: ConfigIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `configuracion_centro_router.py:179` |
| 5 | PUT | `/configuracion/centro/integracion` | JWT centro +X-Centro-Id | config.editar | path/argumento data: IntegracionIn | `dict`/JSON libre | 403,401,400 | `configuracion_centro_router.py:189` |
| 6 | GET | `/configuracion/centro/ollama-switch` | JWT centro +X-Centro-Id | config.editar | — | `dict`/JSON libre | 403,401,400 | `configuracion_centro_router.py:215` |
| 7 | POST | `/configuracion/centro/ollama-switch/{accion}` | JWT centro +X-Centro-Id | config.editar | path/argumento accion: str | `dict`/JSON libre | status.HTTP_400_BAD_REQUEST,status.HTTP_409_CONFLICT,403,401,400 | `configuracion_centro_router.py:225` |
| 8 | GET | `/configuracion/centro/ollama-switch/agentes` | JWT centro +X-Centro-Id | config.editar | — | `dict`/JSON libre | 403,401,400 | `configuracion_centro_router.py:243` |
| 9 | POST | `/configuracion/centro/ollama-switch/agentes/{agente}/{accion}` | JWT centro +X-Centro-Id | config.editar | path/argumento agente: str \| path/argumento accion: str | `dict`/JSON libre | status.HTTP_400_BAD_REQUEST,status.HTTP_409_CONFLICT,403,401,400 | `configuracion_centro_router.py:254` |
| 10 | PUT | `/configuracion/centro/estado/{estado_id}` | JWT centro +X-Centro-Id | config.editar | path/argumento estado_id: int \| path/argumento data: EstadoIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `configuracion_centro_router.py:272` |
| 11 | POST | `/configuracion/centro/gabinete` | JWT centro +X-Centro-Id | config.editar | path/argumento data: GabineteIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `configuracion_centro_router.py:284` |
| 12 | DELETE | `/configuracion/centro/gabinete/{gabinete_id}` | JWT centro +X-Centro-Id | config.editar | path/argumento gabinete_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `configuracion_centro_router.py:296` |


### `configuracion_roles` — `backend/api/configuracion_roles_router.py` (4 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/configuracion/roles` | JWT centro +X-Centro-Id | config.ver | — | `dict`/JSON libre | 403,401,400 | `configuracion_roles_router.py:77` |
| 2 | POST | `/configuracion/roles` | JWT centro +X-Centro-Id | config.editar | path/argumento data: RolIn | `dict`/JSON libre | 403,401,400 | `configuracion_roles_router.py:86` |
| 3 | PUT | `/configuracion/roles/{rol_id}` | JWT centro +X-Centro-Id | config.editar | path/argumento rol_id: int \| path/argumento data: RolIn | `dict`/JSON libre | 403,401,400 | `configuracion_roles_router.py:100` |
| 4 | DELETE | `/configuracion/roles/{rol_id}` | JWT centro +X-Centro-Id | config.editar | path/argumento rol_id: int | `dict`/JSON libre | status.HTTP_400_BAD_REQUEST,status.HTTP_409_CONFLICT,403,401,400 | `configuracion_roles_router.py:128` |


### `configuracion_staff` — `backend/api/configuracion_staff_router.py` (11 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/configuracion/personal` | JWT centro +X-Centro-Id | — | — | `dict`/JSON libre | 401,400 | `configuracion_staff_router.py:306` |
| 2 | POST | `/configuracion/personal` | JWT centro +X-Centro-Id | config.editar | path/argumento data: UsuarioIn | `dict`/JSON libre | 403,401,400 | `configuracion_staff_router.py:344` |
| 3 | PUT | `/configuracion/personal/{usuario_id}` | JWT centro +X-Centro-Id | config.editar | path/argumento usuario_id: int \| path/argumento data: UsuarioIn | `dict`/JSON libre | 403,401,400 | `configuracion_staff_router.py:368` |
| 4 | PUT | `/configuracion/personal/{usuario_id}/colaborador` | JWT centro +X-Centro-Id | config.editar | path/argumento usuario_id: int \| path/argumento data: ColabToggle | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `configuracion_staff_router.py:400` |
| 5 | POST | `/configuracion/personal/{usuario_id}/reactivar` | JWT centro +X-Centro-Id | config.editar | path/argumento usuario_id: int \| path/argumento data: ReactivarIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `configuracion_staff_router.py:452` |
| 6 | GET | `/configuracion/colaboradores` | JWT centro +X-Centro-Id | — | — | `dict`/JSON libre | 401,400 | `configuracion_staff_router.py:563` |
| 7 | GET | `/configuracion/tratamientos` | JWT centro +X-Centro-Id | — | — | `dict`/JSON libre | 401,400 | `configuracion_staff_router.py:579` |
| 8 | GET | `/configuracion/tipos-cita` | JWT centro +X-Centro-Id | — | — | `dict`/JSON libre | 401,400 | `configuracion_staff_router.py:589` |
| 9 | GET | `/configuracion/gabinetes` | JWT centro +X-Centro-Id | — | — | `dict`/JSON libre | 401,400 | `configuracion_staff_router.py:599` |
| 10 | PUT | `/configuracion/colaboradores/{colaborador_id}` | JWT centro +X-Centro-Id | config.editar | path/argumento colaborador_id: int \| path/argumento data: ColaboradorIn | `dict`/JSON libre | 403,401,400 | `configuracion_staff_router.py:611` |
| 11 | POST | `/configuracion/colaboradores/{colaborador_id}/talonario/importar` | JWT centro +X-Centro-Id | config.editar | path/argumento colaborador_id: int | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `configuracion_staff_router.py:648` |


### `consentimientos` — `backend/api/consentimientos_router.py` (14 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/consentimientos/firmar/{code}` |  | — | path/argumento code: str | `dict`/JSON libre | 404,410 | `consentimientos_router.py:57` |
| 2 | GET | `/consentimientos/firmar/{code}/pdf` |  | — | path/argumento code: str | `dict`/JSON libre | 404,410 | `consentimientos_router.py:69` |
| 3 | POST | `/consentimientos/firmar/{code}` |  | — | path/argumento code: str \| path/argumento body: 'FirmarIn' | `dict`/JSON libre | 404,410,422 | `consentimientos_router.py:84` |
| 4 | GET | `/consentimientos/plantillas` | JWT centro | pacientes.ver | — | `dict`/JSON libre | 403,401 | `consentimientos_router.py:100` |
| 5 | GET | `/consentimientos/paciente/{paciente_id}` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `consentimientos_router.py:105` |
| 6 | POST | `/consentimientos` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento body: GenerarIn | `dict`/JSON libre | status.HTTP_400_BAD_REQUEST,status.HTTP_404_NOT_FOUND,status.HTTP_500_INTERNAL_SERVER_ERROR,403,401,400 | `consentimientos_router.py:121` |
| 7 | POST | `/consentimientos/{cid}/firmar` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento cid: int \| path/argumento body: FirmarIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_409_CONFLICT,status.HTTP_400_BAD_REQUEST,403,401,400 | `consentimientos_router.py:144` |
| 8 | DELETE | `/consentimientos/{cid}` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento cid: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `consentimientos_router.py:177` |
| 9 | GET | `/consentimientos/requerido` | JWT centro +X-Centro-Id | pacientes.ver | Query(cita_id: int=Query(...)) | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `consentimientos_router.py:210` |
| 10 | GET | `/consentimientos/firma-profesional` | JWT centro +X-Centro-Id | pacientes.ver | Query(colaborador_id: Optional[int]=Query(None)) | `dict`/JSON libre | 403,401,400 | `consentimientos_router.py:222` |
| 11 | GET | `/consentimientos/{cid}/pdf` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento cid: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `consentimientos_router.py:231` |
| 12 | GET | `/consentimientos/{cid}/paginas` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento cid: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `consentimientos_router.py:245` |
| 13 | GET | `/consentimientos/{cid}/pagina/{n}` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento cid: int \| path/argumento n: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `consentimientos_router.py:259` |
| 14 | POST | `/consentimientos/{cid}/enviar` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento cid: int | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,status.HTTP_404_NOT_FOUND,status.HTTP_502_BAD_GATEWAY,403,401,400 | `consentimientos_router.py:277` |


### `consulta` — `backend/api/consulta_router.py` (13 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | POST | `/pacientes/{paciente_id}/consulta/analizar` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: AnalizarIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,status.HTTP_503_SERVICE_UNAVAILABLE,403,401,400 | `consulta_router.py:39` |
| 2 | POST | `/pacientes/{paciente_id}/consulta/cerrar` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: CerrarIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `consulta_router.py:72` |
| 3 | POST | `/pacientes/{paciente_id}/consulta/escucha` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: EscuchaIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,status.HTTP_403_FORBIDDEN,status.HTTP_503_SERVICE_UNAVAILABLE,403,401,400 | `consulta_router.py:97` |
| 4 | POST | `/pacientes/{paciente_id}/consulta/soap` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: SoapIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,status.HTTP_503_SERVICE_UNAVAILABLE,403,401,400 | `consulta_router.py:131` |
| 5 | POST | `/pacientes/{paciente_id}/consulta/receta` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: RecetaIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,status.HTTP_503_SERVICE_UNAVAILABLE,403,401,400 | `consulta_router.py:167` |
| 6 | GET | `/pacientes/{paciente_id}/consulta/recetas-frecuentes` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `consulta_router.py:198` |
| 7 | POST | `/pacientes/{paciente_id}/consulta/recetas-frecuentes` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: RecetaFrecuenteIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `consulta_router.py:231` |
| 8 | PUT | `/pacientes/{paciente_id}/consulta/recetas-frecuentes/{receta_id}` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento receta_id: int \| path/argumento data: RecetaFrecuenteIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `consulta_router.py:262` |
| 9 | DELETE | `/pacientes/{paciente_id}/consulta/recetas-frecuentes/{receta_id}` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento receta_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `consulta_router.py:290` |
| 10 | GET | `/pacientes/{paciente_id}/consulta/camino` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int \| path/argumento cita_id: Optional[int]=None | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `consulta_router.py:313` |
| 11 | GET | `/pacientes/recomendaciones/catalogo` | JWT centro +X-Centro-Id | — | — | `dict`/JSON libre | 401,400 | `consulta_router.py:386` |
| 12 | POST | `/pacientes/{paciente_id}/consulta/recomendaciones` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: RecomendacionesIn | `dict`/JSON libre | 403,401,400 | `consulta_router.py:403` |
| 13 | GET | `/pacientes/{paciente_id}/recomendaciones/{rec_id}/pdf` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int \| path/argumento rec_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_503_SERVICE_UNAVAILABLE,403,401,400 | `consulta_router.py:448` |


### `crm` — `backend/api/crm_router.py` (2 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/crm/inactivos` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento meses: int=12 | `dict`/JSON libre | 403,401,400 | `crm_router.py:13` |
| 2 | GET | `/crm/pipeline` | JWT centro +X-Centro-Id | pacientes.ver | — | `dict`/JSON libre | 403,401,400 | `crm_router.py:21` |


### `dentia` — `backend/api/dentia_router.py` (3 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/pacientes/{paciente_id}/dentia` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int \| Query(file_id: str=Query(min_length=1, max_length=500)) | `dict`/JSON libre | 403,401,400 | `dentia_router.py:94` |
| 2 | PUT | `/pacientes/{paciente_id}/dentia` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento datos: AnalisisIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `dentia_router.py:103` |
| 3 | POST | `/pacientes/{paciente_id}/dentia/detectar` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento datos: DetectarIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_503_SERVICE_UNAVAILABLE,403,401,400 | `dentia_router.py:127` |


### `documentos` — `backend/api/documentos_router.py` (8 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/pacientes/{paciente_id}/documento/{tipo}` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int \| path/argumento tipo: str | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `documentos_router.py:113` |
| 2 | POST | `/pacientes/{paciente_id}/documento/{tipo}/enviar-whatsapp` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento tipo: str \| path/argumento data: EnviarWhatsappIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_400_BAD_REQUEST,status.HTTP_502_BAD_GATEWAY,403,401,400 | `documentos_router.py:194` |
| 3 | GET | `/pacientes/{paciente_id}/documentos/facturas-vinculadas` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `documentos_router.py:232` |
| 4 | POST | `/pacientes/{paciente_id}/documentos/rectificar-factura` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| Form(factura_id: int=Form(...)) \| Form(motivo: str=Form(...)) \| File(file: UploadFile=File(...)) | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,status.HTTP_404_NOT_FOUND,status.HTTP_409_CONFLICT,status.HTTP_400_BAD_REQUEST,403,401,400 | `documentos_router.py:283` |
| 5 | GET | `/pacientes/{paciente_id}/documentos` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int \| path/argumento tipo: Optional[str]=None | `dict`/JSON libre | 403,401,400 | `documentos_router.py:359` |
| 6 | POST | `/pacientes/{paciente_id}/documentos` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| Form(tipo: str=Form(...)) \| Form(descripcion: str=Form('')) \| File(file: UploadFile=File(...)) | `dict`/JSON libre | status.HTTP_400_BAD_REQUEST,403,401,400 | `documentos_router.py:373` |
| 7 | DELETE | `/pacientes/{paciente_id}/documentos/{doc_id}` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento doc_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_409_CONFLICT,403,401,400 | `documentos_router.py:411` |
| 8 | POST | `/pacientes/{paciente_id}/documentos/generar` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int \| path/argumento body: GenerarDocIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_409_CONFLICT,status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `documentos_router.py:442` |


### `geo` — `backend/api/geo_router.py` (5 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/geo/paises` | JWT centro | — | — | `dict`/JSON libre | 401 | `geo_router.py:14` |
| 2 | GET | `/geo/provincias` | JWT centro | — | path/argumento pais_id: int | `dict`/JSON libre | 401 | `geo_router.py:20` |
| 3 | GET | `/geo/municipios` | JWT centro | — | path/argumento provincia_id: int \| path/argumento q: str='' | `dict`/JSON libre | 401 | `geo_router.py:26` |
| 4 | GET | `/geo/cp` | JWT centro | — | path/argumento municipio_id: int | `dict`/JSON libre | 401 | `geo_router.py:35` |
| 5 | GET | `/geo/buscar-cp/{cp}` | JWT centro | — | path/argumento cp: str | `dict`/JSON libre | 401 | `geo_router.py:41` |


### `gestor_ia` — `backend/api/gestor_ia_router.py` (9 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/gestoria/gestor/estado` | JWT centro +X-Centro-Id | gestoria.ver | — | `dict`/JSON libre | 403,401,400 | `gestor_ia_router.py:53` |
| 2 | GET | `/gestoria/gestor/facturas` | JWT centro +X-Centro-Id | gestoria.ver | Query(limite: int=Query(default=200, le=1000)) | `dict`/JSON libre | 403,401,400 | `gestor_ia_router.py:121` |
| 3 | GET | `/gestoria/gestor/proveedores` | JWT centro +X-Centro-Id | gestoria.ver | — | `dict`/JSON libre | 403,401,400 | `gestor_ia_router.py:166` |
| 4 | GET | `/gestoria/gestor/revision` | JWT centro +X-Centro-Id | gestoria.ver | Query(motivo: str=Query(default=None)) \| Query(limite: int=Query(default=100, le=500)) | `dict`/JSON libre | 403,401,400 | `gestor_ia_router.py:196` |
| 5 | GET | `/gestoria/gestor/revision/agrupada` | JWT centro +X-Centro-Id | gestoria.ver | — | `dict`/JSON libre | 403,401,400 | `gestor_ia_router.py:227` |
| 6 | POST | `/gestoria/gestor/revision/resolver` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: ResolverRevisionIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `gestor_ia_router.py:255` |
| 7 | GET | `/gestoria/gestor/descartes` | JWT centro +X-Centro-Id | gestoria.ver | Query(con_senales: bool=Query(default=False)) \| Query(limite: int=Query(default=200, le=1000)) | `dict`/JSON libre | 403,401,400 | `gestor_ia_router.py:295` |
| 8 | POST | `/gestoria/gestor/barrer` | JWT centro +X-Centro-Id | gestoria.editar | Query(carpeta: str=Query(default=None)) \| Query(tope: int=Query(default=None)) \| Query(max_llamadas: int=Query(default=None)) \| Query(mover: bool=Query(default=True)) | `dict`/JSON libre | status.HTTP_400_BAD_REQUEST,403,401,400 | `gestor_ia_router.py:322` |
| 9 | POST | `/gestoria/gestor/revisadas` | JWT centro +X-Centro-Id | gestoria.editar | Query(tope: int=Query(default=None)) | `dict`/JSON libre | 403,401,400 | `gestor_ia_router.py:411` |


### `gestoria` — `backend/api/gestoria_router.py` (86 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/gestoria/produccion/doctores` | JWT centro +X-Centro-Id | gestoria.ver | Query(desde: date=Query(...)) \| Query(hasta: date=Query(...)) | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:61` |
| 2 | GET | `/gestoria/produccion/tratamientos` | JWT centro +X-Centro-Id | gestoria.ver | Query(desde: Optional[date]=Query(None)) \| Query(hasta: Optional[date]=Query(None)) | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:69` |
| 3 | GET | `/gestoria/produccion/pacientes/{paciente_id}/tratamientos` | JWT centro +X-Centro-Id | gestoria.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:78` |
| 4 | POST | `/gestoria/produccion/pacientes/factura` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: PatientInvoiceIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:91` |
| 5 | POST | `/gestoria/produccion/autofactura` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: AutofacturaIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:110` |
| 6 | PATCH | `/gestoria/produccion/tratamientos/{tid}` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento tid: int \| path/argumento data: TratamientoUpdateIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:126` |
| 7 | GET | `/gestoria/dashboard` | JWT centro +X-Centro-Id | gestoria.ver | Query(desde: date=Query(...)) \| Query(hasta: date=Query(...)) | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:143` |
| 8 | GET | `/gestoria/facturas` | JWT centro +X-Centro-Id | gestoria.ver O gestoria.facturacion.ver | path/argumento anyo: Optional[int]=None \| path/argumento search: Optional[str]=None | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:151` |
| 9 | GET | `/gestoria/email-imap/config` | JWT centro +X-Centro-Id | gestoria.ver | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:170` |
| 10 | PUT | `/gestoria/email-imap/config` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: ImapConfigIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:177` |
| 11 | POST | `/gestoria/email-imap/test` | JWT centro +X-Centro-Id | gestoria.editar | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:187` |
| 12 | GET | `/gestoria/facturas/health` | JWT centro +X-Centro-Id | gestoria.ver O gestoria.facturacion.ver | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:197` |
| 13 | POST | `/gestoria/gmail/webhook` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: GmailWebhookIn \| path/argumento background_tasks: BackgroundTasks | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:210` |
| 14 | POST | `/gestoria/gmail/watch` | JWT centro +X-Centro-Id | gestoria.editar | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:221` |
| 15 | DELETE | `/gestoria/gmail/watch` | JWT centro +X-Centro-Id | gestoria.editar | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:232` |
| 16 | POST | `/gestoria/gmail/watch/renovar` | JWT centro +X-Centro-Id | gestoria.editar | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:243` |
| 17 | GET | `/gestoria/gmail/watch/status` | JWT centro +X-Centro-Id | gestoria.ver | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:254` |
| 18 | GET | `/gestoria/ia/config` | JWT centro +X-Centro-Id | gestoria.ver | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:271` |
| 19 | PUT | `/gestoria/ia/config` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: IAConfigIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:281` |
| 20 | POST | `/gestoria/gmail/reprocesar` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: dict \| path/argumento background_tasks: BackgroundTasks | `dict`/JSON libre | 400,403,401 | `gestoria_router.py:292` |
| 21 | GET | `/gestoria/gastos/{gid}/pdf` | JWT centro +X-Centro-Id | gestoria.ver O gestoria.facturacion.ver | path/argumento gid: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `gestoria_router.py:306` |
| 22 | GET | `/gestoria/gastos/{gid}/correo-pdf` | JWT centro +X-Centro-Id | gestoria.ver O gestoria.facturacion.ver | path/argumento gid: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `gestoria_router.py:318` |
| 23 | GET | `/gestoria/gastos/{gid}/paginas` | JWT centro +X-Centro-Id | gestoria.ver O gestoria.facturacion.ver | path/argumento gid: int | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:332` |
| 24 | POST | `/gestoria/facturas/reorganizar-drive` | JWT centro +X-Centro-Id | gestoria.editar | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:339` |
| 25 | POST | `/gestoria/gastos/{gid}/asociar` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento gid: int \| path/argumento data: AsociarIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:353` |
| 26 | DELETE | `/gestoria/gastos/{gid}/asociar` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento gid: int | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:363` |
| 27 | POST | `/gestoria/gastos/asociar-automatico` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento dias: int=30 | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:373` |
| 28 | GET | `/gestoria/movimientos/debe-libres` | JWT centro +X-Centro-Id | gestoria.ver | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:383` |
| 29 | GET | `/gestoria/gastos/libres` | JWT centro +X-Centro-Id | gestoria.ver | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:390` |
| 30 | GET | `/gestoria/movimientos/haber-libres` | JWT centro +X-Centro-Id | gestoria.ver | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:398` |
| 31 | GET | `/gestoria/pagos-pacientes` | JWT centro +X-Centro-Id | gestoria.ver | path/argumento anyo: Optional[int]=None \| path/argumento forma: Optional[str]=None | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:405` |
| 32 | POST | `/gestoria/pagos-pacientes/{pid}/asociar` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento pid: int \| path/argumento data: AsociarIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:413` |
| 33 | DELETE | `/gestoria/pagos-pacientes/{pid}/asociar` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento pid: int | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:423` |
| 34 | GET | `/gestoria/gastos` | JWT centro +X-Centro-Id | gestoria.ver O gestoria.facturacion.ver | path/argumento estado: Optional[str]=None \| path/argumento desde: Optional[date]=None \| path/argumento hasta: Optional[date]=None | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:433` |
| 35 | GET | `/gestoria/gastos/export-excel` | JWT centro +X-Centro-Id | gestoria.ver O gestoria.facturacion.ver | path/argumento desde: Optional[date]=None \| path/argumento hasta: Optional[date]=None | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:441` |
| 36 | GET | `/gestoria/facturas-recibidas/pdfs-zip` | JWT centro +X-Centro-Id | gestoria.ver O gestoria.facturacion.ver | path/argumento estado: Optional[str]=None \| path/argumento desde: Optional[date]=None \| path/argumento hasta: Optional[date]=None | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `gestoria_router.py:461` |
| 37 | GET | `/gestoria/contabilizacion` | JWT centro +X-Centro-Id | gestoria.ver | path/argumento anyo: Optional[int]=None | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:492` |
| 38 | POST | `/gestoria/gastos` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: GastoIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:512` |
| 39 | PATCH | `/gestoria/gastos/{gid}` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento gid: int \| path/argumento data: dict | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:522` |
| 40 | DELETE | `/gestoria/gastos/{gid}` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento gid: int | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:533` |
| 41 | POST | `/gestoria/gastos/reprocesar-lote` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: ReprocesarLoteIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:555` |
| 42 | POST | `/gestoria/gastos/{gid}/reprocesar` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento gid: int \| path/argumento data: ReprocesarIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:574` |
| 43 | POST | `/gestoria/gastos/upload` | JWT centro +X-Centro-Id | gestoria.editar | File(file: UploadFile=File(...)) | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:594` |
| 44 | POST | `/gestoria/gastos/clasificar-ia` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: ExecuteIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:607` |
| 45 | POST | `/gestoria/buzon/procesar` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: ExecuteIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:625` |
| 46 | POST | `/gestoria/buzon/reintentar-incidencias` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: ExecuteIn \| Query(limite: Optional[int]=Query(None, ge=1, le=500)) | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:646` |
| 47 | GET | `/gestoria/buzon/incidencias-count` | JWT centro +X-Centro-Id | gestoria.ver | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:662` |
| 48 | POST | `/gestoria/banco/cuadrar` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: ExecuteIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:681` |
| 49 | GET | `/gestoria/gastos/propuesta-eliminar` | JWT centro +X-Centro-Id | gestoria.ver | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:695` |
| 50 | POST | `/gestoria/gastos/propuesta-eliminar/borrar` | JWT centro +X-Centro-Id | superuser | path/argumento data: BorrarPropuestaIn | `dict`/JSON libre | status.HTTP_409_CONFLICT,403,401,400 | `gestoria_router.py:708` |
| 51 | POST | `/gestoria/gastos/enlazar-proveedores` | JWT centro +X-Centro-Id | gestoria.editar | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:725` |
| 52 | POST | `/gestoria/gastos/completar-formas-pago` | JWT centro +X-Centro-Id | gestoria.editar | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:736` |
| 53 | POST | `/gestoria/colaboradores/renumerar-autofacturas` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: RenumerarIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:753` |
| 54 | POST | `/gestoria/colaboradores/reemitir-autofacturas` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: RenumerarIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:767` |
| 55 | PATCH | `/gestoria/movimientos/{mid}/concepto` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento mid: int \| path/argumento data: ConceptoIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:783` |
| 56 | GET | `/gestoria/banco/revision` | JWT centro +X-Centro-Id | gestoria.ver | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:794` |
| 57 | POST | `/gestoria/banco/revision/{mid}/prestamo` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento mid: int \| path/argumento data: PrestamoIn | `dict`/JSON libre | status.HTTP_400_BAD_REQUEST,403,401,400 | `gestoria_router.py:806` |
| 58 | POST | `/gestoria/pagos/conciliar-tarjetas` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: ExecuteIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:820` |
| 59 | POST | `/gestoria/deudas/imputar` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: ExecuteIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:834` |
| 60 | GET | `/gestoria/deudas/sin-imputar` | JWT centro +X-Centro-Id | gestoria.ver | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:850` |
| 61 | GET | `/gestoria/duplicados` | JWT centro +X-Centro-Id | gestoria.ver | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:859` |
| 62 | GET | `/gestoria/proveedores` | JWT centro +X-Centro-Id | gestoria.ver | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:866` |
| 63 | GET | `/gestoria/proveedores/catalogos` | JWT centro | gestoria.ver | — | `dict`/JSON libre | 403,401 | `gestoria_router.py:873` |
| 64 | GET | `/gestoria/proveedores/sin-categoria` | JWT centro +X-Centro-Id | gestoria.ver | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:879` |
| 65 | POST | `/gestoria/proveedores/unificar-cif` | JWT centro +X-Centro-Id | gestoria.editar | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:887` |
| 66 | POST | `/gestoria/proveedores/fusionar` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: FusionIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:902` |
| 67 | POST | `/gestoria/proveedores` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: ProveedorIn | `dict`/JSON libre | status.HTTP_400_BAD_REQUEST,403,401,400 | `gestoria_router.py:924` |
| 68 | PATCH | `/gestoria/proveedores/{pid}` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento pid: int \| path/argumento data: dict | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:944` |
| 69 | DELETE | `/gestoria/proveedores/{pid}` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento pid: int | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:954` |
| 70 | GET | `/gestoria/movimientos` | JWT centro +X-Centro-Id | gestoria.ver O gestoria.facturacion.ver | path/argumento tipo: Optional[str]=None \| path/argumento anyo: Optional[int]=None | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:964` |
| 71 | POST | `/gestoria/movimientos` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: MovNuevo | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:988` |
| 72 | DELETE | `/gestoria/movimientos/{mid}` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento mid: int | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:998` |
| 73 | POST | `/gestoria/movimientos/import` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento rows: list[MovRow] | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:1008` |
| 74 | POST | `/gestoria/movimientos/import-xlsx` | JWT centro +X-Centro-Id | gestoria.editar | File(file: UploadFile=File(...)) \| Form(iban: str=Form('')) | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:1018` |
| 75 | GET | `/gestoria/extractos` | JWT centro +X-Centro-Id | gestoria.ver O gestoria.facturacion.ver | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:1056` |
| 76 | GET | `/gestoria/extractos/{eid}/descargar` | JWT centro +X-Centro-Id | gestoria.ver O gestoria.facturacion.ver | path/argumento eid: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `gestoria_router.py:1078` |
| 77 | GET | `/gestoria/modelos-fiscales` | JWT centro +X-Centro-Id | gestoria.ver | path/argumento ejercicio: Optional[int]=None | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:1097` |
| 78 | PUT | `/gestoria/modelos-fiscales` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: ModeloIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:1114` |
| 79 | GET | `/gestoria/calendario-tributario` | JWT centro +X-Centro-Id | gestoria.ver | path/argumento ejercicio: int | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:1125` |
| 80 | POST | `/gestoria/modelos-fiscales/generar` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: GenerarModeloIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:1140` |
| 81 | GET | `/gestoria/envio/config` | JWT centro +X-Centro-Id | gestoria.ver | — | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:1150` |
| 82 | PUT | `/gestoria/envio/config` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: EnvioAutoIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:1163` |
| 83 | POST | `/gestoria/envio` | JWT centro +X-Centro-Id | gestoria.editar | path/argumento data: EnvioIn | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:1179` |
| 84 | GET | `/gestoria/envio/csv` | JWT centro +X-Centro-Id | gestoria.ver O gestoria.facturacion.ver | path/argumento tabla: str \| path/argumento anyo: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_403_FORBIDDEN,403,401,400 | `gestoria_router.py:1193` |
| 85 | GET | `/gestoria/historico` | JWT centro +X-Centro-Id | gestoria.ver | Query(q: Optional[str]=Query(default=None)) \| Query(anio: Optional[int]=Query(default=None)) | `dict`/JSON libre | 403,401,400 | `gestoria_router.py:1218` |
| 86 | GET | `/gestoria/historico/{hid}/pdf` | JWT centro +X-Centro-Id | gestoria.ver | path/argumento hid: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `gestoria_router.py:1254` |


### `health` — `backend/api/health_router.py` (3 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/health` |  | — | — | `dict`/JSON libre | 200 | `health_router.py:12` |
| 2 | GET | `/health/db` |  | — | — | `dict`/JSON libre | 200 | `health_router.py:42` |
| 3 | GET | `/health/llm` |  | — | — | `dict`/JSON libre | 200 | `health_router.py:48` |


### `informes` — `backend/api/informes_router.py` (13 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/informes/entidades` | JWT centro | informes.ver | — | `dict`/JSON libre | 403,401 | `informes_router.py:532` |
| 2 | GET | `/informes/tablas` | JWT centro | informes.ver | — | `dict`/JSON libre | 403,401 | `informes_router.py:550` |
| 3 | GET | `/informes/tabla/{nombre}/campos` | JWT centro | informes.ver | path/argumento nombre: str | `dict`/JSON libre | 403,401 | `informes_router.py:559` |
| 4 | POST | `/informes/ejecutar` | JWT centro +X-Centro-Id | informes.ver | path/argumento q: ConsultaIn | `dict`/JSON libre | 403,401,400 | `informes_router.py:572` |
| 5 | POST | `/informes/exportar` | JWT centro +X-Centro-Id | informes.ver | path/argumento q: ConsultaIn | `dict`/JSON libre | 403,401,400 | `informes_router.py:587` |
| 6 | POST | `/informes/pivote` | JWT centro +X-Centro-Id | informes.ver | path/argumento p: PivoteIn | `dict`/JSON libre | 403,401,400 | `informes_router.py:610` |
| 7 | POST | `/informes/multi/ejecutar` | JWT centro +X-Centro-Id | informes.ver | path/argumento q: MultiConsultaIn | `dict`/JSON libre | 403,401,400 | `informes_router.py:642` |
| 8 | POST | `/informes/multi/exportar` | JWT centro +X-Centro-Id | informes.ver | path/argumento q: MultiConsultaIn | `dict`/JSON libre | 403,401,400 | `informes_router.py:657` |
| 9 | GET | `/informes/guardados` | JWT centro +X-Centro-Id | informes.ver | — | `dict`/JSON libre | 403,401,400 | `informes_router.py:680` |
| 10 | GET | `/informes/guardados/{informe_id}` | JWT centro +X-Centro-Id | informes.ver | path/argumento informe_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `informes_router.py:691` |
| 11 | POST | `/informes/guardados` | JWT centro +X-Centro-Id | informes.editar | path/argumento body: GuardarIn | `dict`/JSON libre | status.HTTP_400_BAD_REQUEST,403,401,400 | `informes_router.py:705` |
| 12 | PUT | `/informes/guardados/{informe_id}` | JWT centro +X-Centro-Id | informes.editar | path/argumento informe_id: int \| path/argumento body: GuardarIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `informes_router.py:724` |
| 13 | DELETE | `/informes/guardados/{informe_id}` | JWT centro +X-Centro-Id | informes.editar | path/argumento informe_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `informes_router.py:745` |


### `inicio` — `backend/api/inicio_router.py` (6 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/inicio/pulso` | JWT centro +X-Centro-Id | — | — | `dict`/JSON libre | 401,400 | `inicio_router.py:22` |
| 2 | GET | `/inicio/citas` | JWT centro +X-Centro-Id | — | Query(fecha: Optional[date]=Query(None, description='Día (por defecto, hoy)')) \| Query(agenda_id: Optional[int]=Query(None)) \| Query(colaborador_id: Optional[int]=Query(None)) \|… | `dict`/JSON libre | 401,400 | `inicio_router.py:35` |
| 3 | GET | `/inicio/paciente/{paciente_id}` | JWT centro +X-Centro-Id | — | path/argumento paciente_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,401,400 | `inicio_router.py:54` |
| 4 | GET | `/inicio/conversacion` | JWT centro +X-Centro-Id | — | Query(paciente_id: int \| None=Query(None)) \| Query(telefono: str \| None=Query(None)) | `dict`/JSON libre | 401,400 | `inicio_router.py:68` |
| 5 | GET | `/inicio/paciente/{paciente_id}/caja` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `inicio_router.py:92` |
| 6 | POST | `/inicio/paciente/{paciente_id}/cobro` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: CobroIn | `dict`/JSON libre | 403,401,400 | `inicio_router.py:102` |


### `internal_tenant` — `backend/api/internal_tenant_router.py` (8 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | POST | `/internal/tenant/provisionar` | X-Internal-Key | — | path/argumento body: dict | `dict`/JSON libre | status.HTTP_400_BAD_REQUEST,401 | `internal_tenant_router.py:48` |
| 2 | GET | `/internal/tenant/{centro_id}/detalle` | X-Internal-Key | — | path/argumento centro_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,401 | `internal_tenant_router.py:69` |
| 3 | PUT | `/internal/tenant/{centro_id}` | X-Internal-Key | — | path/argumento centro_id: int \| path/argumento body: dict | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_409_CONFLICT,status.HTTP_422_UNPROCESSABLE_ENTITY,401 | `internal_tenant_router.py:143` |
| 4 | PUT | `/internal/tenant/{centro_id}/asociacion` | X-Internal-Key | — | path/argumento centro_id: int \| path/argumento body: dict | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_400_BAD_REQUEST,401 | `internal_tenant_router.py:179` |
| 5 | POST | `/internal/tenant/{centro_id}/personal` | X-Internal-Key | — | path/argumento centro_id: int \| path/argumento body: dict | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_400_BAD_REQUEST,401 | `internal_tenant_router.py:246` |
| 6 | DELETE | `/internal/tenant/{centro_id}/personal/{usuario_id}` | X-Internal-Key | — | path/argumento centro_id: int \| path/argumento usuario_id: int \| path/argumento actor_usuario_id: Optional[int]=None | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_400_BAD_REQUEST,401 | `internal_tenant_router.py:285` |
| 7 | POST | `/internal/tenant/{centro_id}/personal/{usuario_id}/reset-password` | X-Internal-Key | — | path/argumento centro_id: int \| path/argumento usuario_id: int \| path/argumento body: dict | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,401 | `internal_tenant_router.py:305` |
| 8 | PUT | `/internal/tenant/{centro_id}/personal/{usuario_id}/email` | X-Internal-Key | — | path/argumento centro_id: int \| path/argumento usuario_id: int \| path/argumento body: dict | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_400_BAD_REQUEST,401 | `internal_tenant_router.py:324` |


### `jarvis_operador` — `backend/api/jarvis_operador_router.py` (2 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | POST | `/internal/jarvis/{agente}/contexto` | X-Internal-Key | — | path/argumento agente: str \| path/argumento body: ContextoIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,401 | `jarvis_operador_router.py:58` |
| 2 | POST | `/internal/jarvis/{agente}/herramienta` | X-Internal-Key | — | path/argumento agente: str \| path/argumento body: HerramientaIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,401 | `jarvis_operador_router.py:71` |


### `llm` — `backend/api/llm_router.py` (2 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | POST | `/pacientes/{paciente_id}/casos-ortodoncia/{caso_id}/generar-diagnostico` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento caso_id: int \| path/argumento data: DiagnosticoLLMRequest | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_500_INTERNAL_SERVER_ERROR,403,401,400 | `llm_router.py:37` |
| 2 | GET | `/pacientes/{paciente_id}/casos-ortodoncia/{caso_id}/reporte-pdf` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int \| path/argumento caso_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_500_INTERNAL_SERVER_ERROR,403,401,400 | `llm_router.py:87` |


### `media` — `backend/api/media_router.py` (1 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/media/{ruta:path}` | JWT centro | — | path/argumento ruta: str | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,401 | `media_router.py:28` |


### `motion` — `backend/api/motion_router.py` (8 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/motion/catalogo` | JWT centro | comunicacion.ver | — | `dict`/JSON libre | 403,401 | `motion_router.py:32` |
| 2 | GET | `/motion/reglas` | JWT centro +X-Centro-Id | comunicacion.ver | — | `dict`/JSON libre | 403,401,400 | `motion_router.py:39` |
| 3 | PATCH | `/motion/reglas/{disparador}` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento disparador: str \| path/argumento data: ReglaIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `motion_router.py:50` |
| 4 | PUT | `/motion/reglas/{disparador}/plantilla` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento disparador: str \| path/argumento data: PlantillaReglaIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `motion_router.py:71` |
| 5 | GET | `/motion/maestro` | JWT centro +X-Centro-Id | comunicacion.ver | — | `dict`/JSON libre | 403,401,400 | `motion_router.py:86` |
| 6 | PUT | `/motion/maestro` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento data: ReglaIn | `dict`/JSON libre | 403,401,400 | `motion_router.py:94` |
| 7 | POST | `/motion/preview` | JWT centro +X-Centro-Id | comunicacion.ver | path/argumento data: PreviewIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `motion_router.py:110` |
| 8 | GET | `/motion/flujos` | JWT centro | comunicacion.ver | — | `dict`/JSON libre | 403,401 | `motion_router.py:123` |


### `ollama_relay` — `backend/api/ollama_relay_router.py` (1 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/ollama/{token}/api/tags` |  | — | path/argumento token: str | `dict`/JSON libre | 404,503 | `ollama_relay_router.py:487` |


### `paciente_auth` — `backend/api/paciente_auth_router.py` (2 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | POST | `/app/auth/solicitar-codigo` |  | — | path/argumento data: SolicitarCodigoIn | `dict`/JSON libre | 401,428 | `paciente_auth_router.py:33` |
| 2 | POST | `/app/auth/verificar-codigo` |  | — | path/argumento data: VerificarCodigoIn | `dict`/JSON libre | 401,428 | `paciente_auth_router.py:50` |


### `pacientes` — `backend/api/pacientes_router.py` (36 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/pacientes/formas-pago` | JWT centro | pacientes.ver | Query(solo_caja: bool=Query(True)) | `dict`/JSON libre | 403,401 | `pacientes_router.py:75` |
| 2 | GET | `/pacientes/financieras` | JWT centro +X-Centro-Id | pacientes.ver | — | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:84` |
| 3 | POST | `/pacientes/{paciente_id}/pagos` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: CobroDeudaIn | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:109` |
| 4 | POST | `/pacientes/{paciente_id}/saldo/traspasar` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: TraspasarSaldoIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_400_BAD_REQUEST,403,401,400 | `pacientes_router.py:199` |
| 5 | POST | `/pacientes/{paciente_id}/saldo/devolver` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: DevolverSaldoIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_400_BAD_REQUEST,403,401,400 | `pacientes_router.py:234` |
| 6 | POST | `/pacientes/{paciente_id}/actos/{acto_id}/marcar-fracasado` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento acto_id: int | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:262` |
| 7 | PATCH | `/pacientes/{paciente_id}/pagos/{pago_id}/liberar` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento pago_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_400_BAD_REQUEST,403,401,400 | `pacientes_router.py:279` |
| 8 | PATCH | `/pacientes/{paciente_id}/pagos/{pago_id}/reasignar` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento pago_id: int \| path/argumento data: ReasignarPagoIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_400_BAD_REQUEST,403,401,400 | `pacientes_router.py:304` |
| 9 | GET | `/pacientes/buscar` | JWT centro +X-Centro-Id | pacientes.ver | Query(q: str=Query(..., min_length=2)) \| Query(limite: int=Query(20, ge=1, le=200)) | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:334` |
| 10 | GET | `/pacientes/{paciente_id}` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:383` |
| 11 | GET | `/pacientes/{paciente_id}/filiacion` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:424` |
| 12 | PUT | `/pacientes/{paciente_id}` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: PacienteUpdate | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `pacientes_router.py:478` |
| 13 | GET | `/pacientes/{paciente_id}/tarifas` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:503` |
| 14 | PUT | `/pacientes/{paciente_id}/tarifas` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: TarifasIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `pacientes_router.py:516` |
| 15 | GET | `/pacientes/anamnesis/catalogo` | JWT centro +X-Centro-Id | pacientes.ver | — | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:545` |
| 16 | PUT | `/pacientes/{paciente_id}/anamnesis` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: AnamnesisIn | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:557` |
| 17 | PUT | `/pacientes/{paciente_id}/facturacion` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: FacturacionIn | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:585` |
| 18 | PUT | `/pacientes/{paciente_id}/seguro` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: SeguroIn | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:613` |
| 19 | GET | `/pacientes/{paciente_id}/plan` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:645` |
| 20 | GET | `/pacientes/{paciente_id}/presupuestos` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:846` |
| 21 | GET | `/pacientes/{paciente_id}/previstos` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:855` |
| 22 | GET | `/pacientes/{paciente_id}/actos` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:1039` |
| 23 | GET | `/pacientes/{paciente_id}/multimedia` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:1048` |
| 24 | GET | `/pacientes/{paciente_id}/multimedia/{file_id}` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int \| path/argumento file_id: str \| Query(thumb: bool=Query(False)) | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `pacientes_router.py:1059` |
| 25 | POST | `/pacientes/{paciente_id}/multimedia/{file_id}/analizar-ia` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int \| path/argumento file_id: str | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_503_SERVICE_UNAVAILABLE,403,401,400 | `pacientes_router.py:1076` |
| 26 | POST | `/pacientes/{paciente_id}/foto` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| File(file: UploadFile=File(...)) | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `pacientes_router.py:1124` |
| 27 | POST | `/pacientes/{paciente_id}/foto/drive` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `pacientes_router.py:1151` |
| 28 | DELETE | `/pacientes/{paciente_id}/foto` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:1174` |
| 29 | GET | `/pacientes/{paciente_id}/foto` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `pacientes_router.py:1190` |
| 30 | GET | `/pacientes/{paciente_id}/odontograma` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:1221` |
| 31 | PUT | `/pacientes/{paciente_id}/odontograma` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: OdontogramaIn | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:1264` |
| 32 | GET | `/pacientes/{paciente_id}/periodontograma` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int \| Query(exploracion_id: Optional[int]=Query(None)) | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401,400 | `pacientes_router.py:1333` |
| 33 | GET | `/pacientes/{paciente_id}/periodontograma/estudios` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:1359` |
| 34 | POST | `/pacientes/{paciente_id}/periodontograma` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: PerioStudyIn | `dict`/JSON libre | 403,401,400 | `pacientes_router.py:1398` |
| 35 | GET | `/pacientes/{paciente_id}/ficha` |  | — | path/argumento paciente_id: int | `dict`/JSON libre | 404 | `pacientes_router.py:1433` |
| 36 | GET | `/pacientes/{paciente_id}/citas` |  | — | path/argumento paciente_id: int \| path/argumento estado: str='confirmada' | `dict`/JSON libre | 200 | `pacientes_router.py:1468` |


### `presupuestos` — `backend/api/presupuestos_router.py` (15 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/pacientes/{paciente_id}/catalogo-tratamientos` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int \| Query(q: str=Query(..., min_length=2)) | `dict`/JSON libre | 403,401,400 | `presupuestos_router.py:72` |
| 2 | GET | `/pacientes/{paciente_id}/presupuestos-predisenados` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int | `dict`/JSON libre | 403,401,400 | `presupuestos_router.py:104` |
| 3 | POST | `/pacientes/{paciente_id}/presupuestos` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: PresupuestoIn | `dict`/JSON libre | 403,401,400 | `presupuestos_router.py:219` |
| 4 | PUT | `/pacientes/{paciente_id}/presupuestos/{pre_id}` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento pre_id: int \| path/argumento data: PresupuestoIn | `dict`/JSON libre | status.HTTP_409_CONFLICT,403,401,400 | `presupuestos_router.py:245` |
| 5 | DELETE | `/pacientes/{paciente_id}/presupuestos/{pre_id}` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento pre_id: int | `dict`/JSON libre | status.HTTP_409_CONFLICT,403,401,400 | `presupuestos_router.py:276` |
| 6 | POST | `/pacientes/{paciente_id}/presupuestos/{pre_id}/entregar` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento pre_id: int | `dict`/JSON libre | 403,401,400 | `presupuestos_router.py:300` |
| 7 | POST | `/pacientes/{paciente_id}/presupuestos/{pre_id}/reabrir` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento pre_id: int | `dict`/JSON libre | status.HTTP_409_CONFLICT,403,401,400 | `presupuestos_router.py:313` |
| 8 | POST | `/pacientes/{paciente_id}/presupuestos/{pre_id}/anular` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento pre_id: int | `dict`/JSON libre | status.HTTP_409_CONFLICT,403,401,400 | `presupuestos_router.py:338` |
| 9 | POST | `/pacientes/{paciente_id}/presupuestos/{pre_id}/aceptar` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento pre_id: int \| path/argumento data: AceptarIn | `dict`/JSON libre | status.HTTP_409_CONFLICT,status.HTTP_400_BAD_REQUEST,403,401,400 | `presupuestos_router.py:367` |
| 10 | POST | `/pacientes/{paciente_id}/presupuestos/{pre_id}/duplicar` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento pre_id: int | `dict`/JSON libre | 403,401,400 | `presupuestos_router.py:422` |
| 11 | POST | `/pacientes/{paciente_id}/presupuestos/realizar-en-cita` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento data: RealizarEnCitaIn | `dict`/JSON libre | status.HTTP_400_BAD_REQUEST,status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `presupuestos_router.py:453` |
| 12 | POST | `/pacientes/{paciente_id}/presupuestos/{pre_id}/cancelar` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento pre_id: int \| path/argumento data: CancelarIn | `dict`/JSON libre | status.HTTP_409_CONFLICT,status.HTTP_400_BAD_REQUEST,403,401,400 | `presupuestos_router.py:581` |
| 13 | GET | `/pacientes/{paciente_id}/presupuestos/{pre_id}/documento` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int \| path/argumento pre_id: int | `dict`/JSON libre | 403,401,400 | `presupuestos_router.py:678` |
| 14 | GET | `/pacientes/{paciente_id}/presupuestos/{pre_id}/pdf` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento paciente_id: int \| path/argumento pre_id: int | `dict`/JSON libre | 403,401,400 | `presupuestos_router.py:823` |
| 15 | POST | `/pacientes/{paciente_id}/presupuestos/{pre_id}/enviar-whatsapp` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento paciente_id: int \| path/argumento pre_id: int \| path/argumento data: EnviarWhatsappIn | `dict`/JSON libre | status.HTTP_400_BAD_REQUEST,status.HTTP_502_BAD_GATEWAY,403,401,400 | `presupuestos_router.py:847` |


### `radiologia` — `backend/api/radiologia_router.py` (18 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | POST | `/radiologia/detectar-rx` | JWT centro +X-Centro-Id | — | — | `dict`/JSON libre | 401,400 | `radiologia_router.py:136` |
| 2 | POST | `/radiologia/detectar-rx-interno` | X-Internal-Key | — | Header(x_internal_key: Optional[str]=Header(default=None)) | `dict`/JSON libre | 401 | `radiologia_router.py:146` |
| 3 | GET | `/radiologia/rx-export` | JWT centro +X-Centro-Id | — | — | `dict`/JSON libre | 401,400 | `radiologia_router.py:158` |
| 4 | GET | `/radiologia/modalidades` |  | — | — | ModalidadesResp | 200 | `radiologia_router.py:174` |
| 5 | GET | `/pacientes/{paciente_id}/radiologia` | JWT centro +X-Centro-Id | — | path/argumento paciente_id: int | list[ImagenRxDTO] | 401,400 | `radiologia_router.py:180` |
| 6 | POST | `/pacientes/{paciente_id}/radiologia` | JWT centro +X-Centro-Id | — | path/argumento paciente_id: int \| File(file: UploadFile=File(...)) \| Query(cita_id: Optional[int]=Query(default=None)) \| Query(clasificar: bool=Query(default=True)) | ImagenRxDTO | status.HTTP_422_UNPROCESSABLE_ENTITY,status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,401,400 | `radiologia_router.py:190` |
| 7 | GET | `/radiologia/{imagen_id}/archivo` | JWT centro +X-Centro-Id | — | path/argumento imagen_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,401,400 | `radiologia_router.py:240` |
| 8 | PATCH | `/radiologia/{imagen_id}` | JWT centro +X-Centro-Id | — | path/argumento imagen_id: int \| path/argumento datos: ReclasificarIn | ImagenRxDTO | status.HTTP_422_UNPROCESSABLE_ENTITY,401,400 | `radiologia_router.py:251` |
| 9 | POST | `/radiologia/{imagen_id}/clasificar` | JWT centro +X-Centro-Id | — | path/argumento imagen_id: int | ImagenRxDTO | status.HTTP_422_UNPROCESSABLE_ENTITY,401,400 | `radiologia_router.py:269` |
| 10 | DELETE | `/radiologia/{imagen_id}` | JWT centro +X-Centro-Id | — | path/argumento imagen_id: int | `dict`/JSON libre | 401,400 | `radiologia_router.py:287` |
| 11 | POST | `/radiologia/{imagen_id}/hallazgos` | JWT centro +X-Centro-Id | — | path/argumento imagen_id: int \| path/argumento datos: HallazgoIn | HallazgoDTO | 401,400 | `radiologia_router.py:315` |
| 12 | GET | `/radiologia/{imagen_id}/anotaciones` | JWT centro +X-Centro-Id | — | path/argumento imagen_id: int | AnotacionesResp | 401,400 | `radiologia_router.py:340` |
| 13 | PUT | `/radiologia/{imagen_id}/anotaciones` | JWT centro +X-Centro-Id | — | path/argumento imagen_id: int \| path/argumento datos: AnotacionesIn | AnotacionesResp | 401,400 | `radiologia_router.py:349` |
| 14 | GET | `/pacientes/{paciente_id}/radiologia/informe.pptx` | JWT centro +X-Centro-Id | — | path/argumento paciente_id: int | `dict`/JSON libre | 401,400 | `radiologia_router.py:367` |
| 15 | GET | `/pacientes/{paciente_id}/dicom/series` | JWT centro +X-Centro-Id | — | path/argumento paciente_id: int | list[SerieDicomDTO] | 401,400 | `radiologia_router.py:416` |
| 16 | GET | `/pacientes/{paciente_id}/dicom/slice/{instance_id}` | JWT centro +X-Centro-Id | — | path/argumento paciente_id: int \| path/argumento instance_id: str \| Query(thumb: bool=Query(default=False)) | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,401,400 | `radiologia_router.py:425` |
| 17 | DELETE | `/radiologia/hallazgos/{hallazgo_id}` | JWT centro +X-Centro-Id | — | path/argumento hallazgo_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,401,400 | `radiologia_router.py:439` |
| 18 | POST | `/radiologia/importar-romexis-interno` | X-Internal-Key | — | Header(x_internal_key: Optional[str]=Header(default=None)) \| Header(x_num_historia: Optional[str]=Header(default=None)) \| Header(x_filename: Optional[str]=Header(default=None)) \… | `dict`/JSON libre | 401,422 | `radiologia_router.py:459` |


### `romexis` — `backend/api/romexis_router.py` (5 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | POST | `/pacientes/nuevo` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento datos: PacienteNuevoIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,status.HTTP_409_CONFLICT,403,401,400 | `romexis_router.py:129` |
| 2 | GET | `/integraciones/romexis/pendientes` | X-Internal-Key | — | — | `dict`/JSON libre | 401 | `romexis_router.py:158` |
| 3 | POST | `/integraciones/romexis/{sync_id}/resultado` | X-Internal-Key | — | path/argumento sync_id: int \| path/argumento datos: ResultadoIn | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,status.HTTP_404_NOT_FOUND,401 | `romexis_router.py:177` |
| 4 | GET | `/romexis-sync` | JWT centro +X-Centro-Id | pacientes.ver | path/argumento estado: Optional[str]=None | `dict`/JSON libre | 403,401,400 | `romexis_router.py:204` |
| 5 | POST | `/romexis-sync/{sync_id}/resolver` | JWT centro +X-Centro-Id | pacientes.editar | path/argumento sync_id: int \| path/argumento datos: ResolverIn | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,status.HTTP_409_CONFLICT,status.HTTP_422_UNPROCESSABLE_ENTITY,403,401,400 | `romexis_router.py:220` |


### `superuser` — `backend/api/superuser_router.py` (19 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/superuser/dashboard` | JWT centro | superuser | — | `dict`/JSON libre | 403,401 | `superuser_router.py:86` |
| 2 | GET | `/superuser/apariencia` | JWT centro | superuser | — | `dict`/JSON libre | 403,401 | `superuser_router.py:110` |
| 3 | PUT | `/superuser/apariencia` | JWT centro | superuser | path/argumento data: AparienciaSet | `dict`/JSON libre | 403,401 | `superuser_router.py:115` |
| 4 | GET | `/superuser/db/tables` | JWT centro | superuser | — | `dict`/JSON libre | 403,401 | `superuser_router.py:125` |
| 5 | GET | `/superuser/db/tables/{tabla}/schema` | JWT centro | superuser | path/argumento tabla: str | `dict`/JSON libre | 403,401 | `superuser_router.py:139` |
| 6 | GET | `/superuser/db/tables/{tabla}/rows` | JWT centro | superuser | path/argumento tabla: str \| Query(page: int=Query(1, ge=1)) \| Query(limit: int=Query(50, ge=1, le=200)) \| path/argumento search: str='' \| path/argumento orderBy: str='' \| path… | `dict`/JSON libre | 403,401 | `superuser_router.py:145` |
| 7 | POST | `/superuser/db/query` | JWT centro +X-Centro-Id | superuser | path/argumento body: dict | `dict`/JSON libre | status.HTTP_400_BAD_REQUEST,403,401,400 | `superuser_router.py:188` |
| 8 | GET | `/superuser/centros` | JWT centro | superuser | — | `dict`/JSON libre | 403,401 | `superuser_router.py:229` |
| 9 | POST | `/superuser/centros` | JWT centro | superuser | path/argumento body: dict | `dict`/JSON libre | 403,401 | `superuser_router.py:238` |
| 10 | GET | `/superuser/centros/{centro_id}` | JWT centro | superuser | path/argumento centro_id: int | `dict`/JSON libre | status.HTTP_404_NOT_FOUND,403,401 | `superuser_router.py:262` |
| 11 | PUT | `/superuser/centros/{centro_id}` | JWT centro | superuser | path/argumento centro_id: int \| path/argumento body: dict | `dict`/JSON libre | 403,401 | `superuser_router.py:280` |
| 12 | PUT | `/superuser/centros/{centro_id}/asociacion` | JWT centro | superuser | path/argumento centro_id: int \| path/argumento body: dict | `dict`/JSON libre | 403,401 | `superuser_router.py:298` |
| 13 | POST | `/superuser/centros/{centro_id}/personal` | JWT centro | superuser | path/argumento centro_id: int \| path/argumento body: dict | `dict`/JSON libre | 403,401 | `superuser_router.py:307` |
| 14 | DELETE | `/superuser/centros/{centro_id}/personal/{usuario_id}` | JWT centro | superuser | path/argumento centro_id: int \| path/argumento usuario_id: int | `dict`/JSON libre | 403,401 | `superuser_router.py:314` |
| 15 | POST | `/superuser/centros/{centro_id}/personal/{usuario_id}/reset-password` | JWT centro | superuser | path/argumento centro_id: int \| path/argumento usuario_id: int | `dict`/JSON libre | 403,401 | `superuser_router.py:320` |
| 16 | PUT | `/superuser/centros/{centro_id}/personal/{usuario_id}/email` | JWT centro | superuser | path/argumento centro_id: int \| path/argumento usuario_id: int \| path/argumento body: dict | `dict`/JSON libre | 403,401 | `superuser_router.py:326` |
| 17 | PATCH | `/superuser/centros/{centro_id}/estado` | JWT centro | superuser | path/argumento centro_id: int \| path/argumento body: dict | `dict`/JSON libre | status.HTTP_400_BAD_REQUEST,403,401 | `superuser_router.py:333` |
| 18 | PATCH | `/superuser/centros/{centro_id}/modulos` | JWT centro | superuser | path/argumento centro_id: int \| path/argumento body: dict | `dict`/JSON libre | status.HTTP_400_BAD_REQUEST,403,401 | `superuser_router.py:346` |
| 19 | GET | `/superuser/centinela` | JWT centro +X-Centro-Id | superuser | — | `dict`/JSON libre | 403,401,400 | `superuser_router.py:363` |


### `uploads` — `backend/api/uploads_router.py` (1 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | POST | `/uploads` | JWT centro | config.editar | File(file: UploadFile=File(...)) | `dict`/JSON libre | status.HTTP_422_UNPROCESSABLE_ENTITY,status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,403,401 | `uploads_router.py:26` |


### `voicebot` — `backend/api/voicebot_router.py` (5 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | GET | `/comunicacion/voicebot/voice-config` | JWT centro +X-Centro-Id | comunicacion.ver | — | `dict`/JSON libre | 403,401,400 | `voicebot_router.py:28` |
| 2 | GET | `/comunicacion/voicebot/health` | JWT centro +X-Centro-Id | comunicacion.ver | — | `dict`/JSON libre | 403,401,400 | `voicebot_router.py:35` |
| 3 | POST | `/comunicacion/voicebot/turno` | JWT centro +X-Centro-Id | comunicacion.editar | path/argumento data: TurnoIn | `dict`/JSON libre | 403,401,400 | `voicebot_router.py:48` |
| 4 | GET | `/comunicacion/voicebot/historial` | JWT centro +X-Centro-Id | comunicacion.ver | path/argumento paciente_id: Optional[int]=None \| path/argumento limit: int=50 | `dict`/JSON libre | 403,401,400 | `voicebot_router.py:60` |
| 5 | GET | `/comunicacion/voicebot/stats` | JWT centro +X-Centro-Id | comunicacion.ver | path/argumento dias: int=30 | `dict`/JSON libre | 403,401,400 | `voicebot_router.py:68` |


### `ws` — `backend/api/ws_router.py` (1 rutas)

| # | Método | Ruta | Auth | Autorización | Request relevante | Resp. (`response_model`) | Errores | Evidencia |
|---:|---|---|---|---|---|---|---|---|
| 1 | WEBSOCKET | `/ws/gestoria/{centro_id}` | JWT centro | gestoria.ver | path/argumento centro_id: int \| Query(token: str=Query(...)) | `dict`/JSON libre | 4001,4003 | `ws_router.py:153` |

---

## 9. Contrato estable que consumen las apps móviles (NO romper)

Las ramas `doctor-ios` / `doctor-android` / `paciente-*` están en el árbol (`mobile/`) y consumen
endpoints concretos del backend. Cualquier refactor del rebuild que cambie estos paths, el
transporte de auth o los nombres de campo rompe apps ya distribuidas.

### 9.1 Reglas de transporte

| Regla | Evidencia |
|---|---|
| Profesional: `POST /auth/login` devuelve `access_token` en el JSON; se manda como `Authorization: Bearer` y el centro activo como `X-Centro-Id` | `mobile/doctor-ios/README.md:9-11`; `auth_router.py:65-68`; `auth_deps.py:28-44` |
| Paciente: OTP por `POST /app/auth/solicitar-codigo` + `verificar-codigo`; token Bearer tipo `paciente` | `mobile/doctor-ios/README.md:13-14`, `:124-125`; `paciente_auth_router.py:33,50`; `paciente_auth_deps.py:25-36` |
| Failover de host en la app (Tailscale/LAN) — el backend debe seguir aceptando HTTP en desarrollo (ATS exception) | `mobile/doctor-ios/README.md:37-60` |
| SSE con heartbeat cada 15 s y reconexión de la app con backoff | `mobile/doctor-ios/README.md:80-87`; `app_doctor_router.py:416-424` |
| OTP con teléfono compartido responde **428** (la app pide nombre); no confundir con 401 | `paciente_auth_router.py:40-45`, `:59-64` |

### 9.2 Endpoints exactos consumidos por las apps (lista cerrada)

**Profesional** — prefijo `/app/doctores/me` (`app_doctor_router.py:55`), 13 operaciones:

| Método | Ruta | Evidencia |
|---|---|---|
| GET | `/app/doctores/me/perfil` | `app_doctor_router.py:74` |
| GET | `/app/doctores/me/agenda` | `:108` |
| GET | `/app/doctores/me/pacientes?q=` | `:136` |
| GET | `/app/doctores/me/pacientes/{paciente_id}` | `:155` |
| GET | `/app/doctores/me/protocolo` | `:181` |
| POST | `/app/doctores/me/estudios` | `:211` |
| GET | `/app/doctores/me/estudios` | `:234` |
| GET | `/app/doctores/me/estudios/{estudio_id}` | `:254` |
| POST | `/app/doctores/me/estudios/{estudio_id}/completar` | `:270` |
| POST | `/app/doctores/me/estudios/{estudio_id}/fotos` (multipart, campo `file`) | `:286-290` |
| GET | `/app/doctores/me/fotos/{foto_id}` (binario) | `:345` |
| DELETE | `/app/doctores/me/fotos/{foto_id}` | `:359` |
| GET | `/app/doctores/me/stream` (SSE; eventos `cita.*`, `estudio.foto`, `estudio.foto_borrada`) | `:397-427` |

**Paciente** — prefijo `/app/pacientes/me` (`app_paciente_router.py:41`), 9 operaciones:

| Método | Ruta | Evidencia |
|---|---|---|
| GET | `/app/pacientes/me/perfil` | `app_paciente_router.py:66` |
| GET | `/app/pacientes/me/tratamientos` | `:77` |
| GET | `/app/pacientes/me/presupuestos` | `:84` |
| GET | `/app/pacientes/me/huecos` | `:91` |
| POST | `/app/pacientes/me/citas/solicitar` | `:105` |
| GET | `/app/pacientes/me/facturas` | `:159` |
| GET | `/app/pacientes/me/facturas/{numero}/pdf` (binario) | `:179` |
| GET | `/app/pacientes/me/justificantes/{acto_id}/pdf` (binario) | `:196` |
| GET | `/app/pacientes/me/stream` (SSE; filtra por `paciente_id`) | `:226-250` |

Las apps no usan ningún endpoint de `/pacientes/{id}/ficha` ni `/pacientes/{id}/citas`
(los dos sin auth de §4.5): la ficha de la app se sirve por `/app/pacientes/me/perfil`
(evidencia: `mobile/doctor-ios/README.md:119-125` y `app_paciente_router.py:66`). Eso confirma
que los dos endpoints públicos son **residuo legacy**, no contrato de app.

### 9.3 Invariantes de contrato (además de la URL)

1. **Auth por cabecera Bearer** en apps (nunca cookie): `paciente_auth_deps.py:1-13`
   (docstring: las apps nativas guardan el token en Keychain/EncryptedSharedPreferences).
2. **`X-Centro-Id`** obligatorio si el usuario del doctor tiene más de un acceso;
   las apps lo mandan siempre (`settings`/`auth_deps.py:46-61`).
3. **Formato de error**: `detail` string en JSON; las apps muestran `detail` (mismo criterio que
   el cliente web, `frontend/src/shared/lib/api.ts:15-21`).
4. **Binarios**: PDF (facturas, justificantes, consentimientos, presupuestos, informes) e
   imágenes por `Response`/`FileResponse`; no envolver en JSON.
5. **SSE**: `text/event-stream`; el profesional recibe eventos de todo el centro y filtra por
   tipo; el paciente recibe solo eventos de su `paciente_id` (`events.py:1-35`, `emit(...)`
   propaga `centro_id` y `paciente_id`). Los nombres de evento son contrato
   (`app_doctor_router.py:397-400`).

---

## 10. Riesgos, defectos y lo que queda sin verificar

### 10.1 Defectos/paradojas que el rebuild NO debe reproducir

| # | Hallazgo | Evidencia | Impacto |
|---|---|---|---|
| 1 | `GET /pacientes/{id}/ficha` y `/pacientes/{id}/citas` **sin autenticación** devuelven datos de paciente (nombre, email, alergias, anamnesis) | `pacientes_router.py:1433-1471`, `:1468-1476` | Fuga de PII/RGPD por IDOR. El contrato funcional (app del paciente) ya está cubierto por `/app/pacientes/me/perfil`; al reconstruir, **eliminar o proteger**. |
| 2 | `GET /pacientes/{id}/citas` devuelve **siempre** `{"proximas": [], "total": 0}` (stub) | `pacientes_router.py:1468-1475` | No hay contrato real que preservar; no portar como funcionalidad. |
| 3 | Ruta duplicada `GET /pacientes/{id}/previstos`; la versión rica de `clinico_router.py:417` es inalcanzable | §2.4 | Portar solo la de `pacientes_router.py:855`; no invertir en la muerta. |
| 4 | Umbral de login por defecto **5**, no 4 (enunciado de la tarea) | `settings.py:128` | Parametrizar; no hardcodear 4 ni 5. |
| 5 | `GET /health` llama al proveedor LLM en cada petición (`await llm_provider.health_check()`) | `health_router.py:20-22` | En serverless/Vercel un health caro puede agotar tiempo; separar liveness de readiness al portar. |
| 6 | El scheduler y el bus SSE necesitan proceso vivo + Redis + locks de Postgres | `infrastructure/scheduler.py:32-45`, `infrastructure/realtime.py:1-20` | No son portables a funciones serverless sin rediseño (cola/cron externo). Afecta a WhatsApp automático, intake Gmail, conciliación, detector RX y todos los SSE. |

### 10.2 Lo que NO se pudo verificar (y por qué)

1. **Conteo por import de la app:** la cifra «48» de la auditoría previa está **verificada y
   explicada** como artefacto de `_IncludedRouter` (§2.2-2.3): el import lo ejecutó el lead en un
   venv macOS (FastAPI 0.162.0) y dio 48 objetos de ruta = 43 envoltorios + 5 rutas, con 432 paths
   y ~498 operaciones OpenAPI. **Yo no lo he reproducido personalmente** (mi entorno no tiene el
   venv); el comando de reproducción está en §2.2. Queda **NO VERIFICADO** qué versión exacta de
   FastAPI corre en producción (§2.2).
2. **Valores efectivos de configuración del despliegue** (login 4 vs 5, `cookie_secure`, CORS de
   producción, `ENABLE_AI_OPENAPI`): dependen de variables de entorno; no se ha leído el `.env`
   (contiene secretos; prohibido por RGPD/reglas del proyecto). Los defaults del código sí están
   citados con evidencia. **NO VERIFICADO** el valor real desplegado.
3. **Comportamiento en tiempo de ejecución de cada endpoint** (códigos de error que dependen de
   servicios externos, respuestas reales): el resumen es estático desde el código. Los tests que
   sí lo cubren están inventariados en `PARIDAD-PRUEBAS.md`. **NO VERIFICADO en ejecución aquí**.
4. **Rutas que pudieran registrarse por plugins/montajes externos**: se comprobó que no hay
   `app.mount` (solo el comentario histórico de `/media` en `main.py:154-156` y
   `media_router.py:1-16`); no hay `add_api_route` dinámico. La ausencia de factorías se verificó
   por grep, no por introspección en runtime.

### 10.3 Checklist de verificación de paridad de API por módulo (para el rebuild)

Para declarar un módulo «a la par» deben cumplirse **todas**:

- [ ] Cada operación del módulo en §8 responde en **la misma URL y método**.
- [ ] La **puerta de auth** coincide (JWT centro/paciente, X-Internal-Key, pública, token) y el
      **permiso fino** coincide exactamente con el código listado.
- [ ] Los códigos de estado y el cuerpo de error (`detail`) son compatibles con §5.
- [ ] La forma de respuesta es la misma (modelo PII/binario/SSE/envelope `data`).
- [ ] Multi-tenant: toda operación sobre un paciente devuelve **404** si el paciente no es del
      centro activo (patrón `_get_paciente`, `backend/api/paciente_helper.py:9-13`).
- [ ] Las 23 rutas sin auth se han reproducido **una a una** y las 2 defectuosas de §10.1.1
      se han corregido, no copiado.
