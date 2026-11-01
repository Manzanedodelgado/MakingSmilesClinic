# PARIDAD-FLUJOS — MakingSmiles_Studio

> **Qué es.** Los flujos de negocio observables del legacy (`master` @ `a76ee81`) que el rebuild
> por módulos con corte progresivo debe reproducir. Por cada flujo: **objetivo**, **archivos**,
> **contrato observable (HTTP/eventos/estado)**, **reglas de negocio**, **riesgo si se rompe** y
> **cómo se verifica** (tests existentes + comprobación manual).
>
> Cada flujo es una unidad de corte: un módulo puede cortarse cuando los flujos que toca pasan
> sus verificaciones contra el legacy en paralelo.
>
> Evidencia `ruta:línea` en todo. Sin PII ni secretos. Lo no verificado se marca **NO VERIFICADO**.

## 0. Mapa de flujos y cobertura de pruebas

| # | Flujo | Módulos implicados | Tests backend | E2E Playwright |
|---|---|---|---|---|
| F1 | Login/sesión del personal (cookie httpOnly 12 h, freno de intentos, reset) | `auth_*`, `identidad` | `test_f0.py`, `test_auth_settings.py`, `test_roles_permisos.py`, `test_centinela.py` | `paso-1-auth-real.spec.ts` |
| F2 | Media autenticada y multimedia del paciente | `media_router`, `multimedia_service`, `pacientes_router` | `test_multimedia_security.py`, `test_paciente_auth_telefono_compartido.py` | `paso-9-bloqueadores-serial.spec.ts` |
| F3 | Tiempo real SSE (web y apps) | `comunicacion_router`, `app_doctor_router`, `app_paciente_router`, `realtime`, `events` | `test_polls_media.py` (indirecto) | — (verificación manual) |
| F4 | Análisis IA (~30 s): DentIA, multimedia, radiología, consulta | `dentia_router`, `radiologia_router`, `consulta_router`, `ia_dental_client`, `llm_*` | `test_dentia.py`, `test_ia_dental_client.py`, `test_llm_cascada.py`, `test_escucha_determinista.py` | `paso-7-consulta-real.spec.ts`, `paso-10-radiologia-real.spec.ts` |
| F5 | WhatsApp / Evolution (entrante, saliente, automatización, pautas, pausas) | `comunicacion_router`, `comunicacion_service`, `automatizacion_*`, `motion_router`, `voicebot_router`, `evolution_api` | `test_whatsapp_flujos.py`, `test_whatsapp_hora_real.py`, `test_polls_media.py`, `test_voicebot.py`, `test_comunicacion_media_dir.py` | `paso-11-comunicacion-real.spec.ts` |
| F6 | Gmail / intake de facturas + Gestor IA | `gestoria_router`, `gestor_ia_router`, `intake_service`, `gmail_*`, `gestor_*` | `test_intake_service.py`, `test_gmail_ai_processor.py`, `test_gestor_agente.py`, `test_gestor_facturas_reales.py`, `test_acceso_gmail.py`, `test_pipeline_2etapas_mock.py` | `paso-12-gestoria-real.spec.ts` |
| F7 | Facturación / gestoría (producción, gastos, banco, conciliación, asesoría) | `gestoria_router`, `gestor_ia_router`, `gestoria_service`, `conciliacion_service` | `test_gestoria_contrato.py`, `test_conciliacion.py`, `test_verifactu.py`, `test_cuenta_economica.py`, `test_gastos_export_service.py` | `paso-12-gestoria-real.spec.ts` |
| F8 | Agenda (huecos, cita, mover/anular, estados, justificante) | `agenda_router`, `configuracion_agenda_router`, `disponibilidad`, `cita_reglas` | `test_cita_reglas.py`, `test_disponibilidad.py`, `test_agenda_cross_tenant.py`, `test_selectores_doctores.py`, `test_cita_id_cita.py` | `paso-8-agenda-real.spec.ts`, `agenda-cabeceras.visual.ts` |
| F9 | Odontograma / periodontograma | `pacientes_router` (secciones), `dental` | `test_fdi.py`, `test_ficha_layout_config.py` (layout) | `paso-2-pacientes-crud-real.spec.ts` (ficha), `paso-15-integracion-e2e-real.spec.ts` |
| F10 | Caja y cuenta económica (cobro, deuda, saldo, devolución) | `inicio_router`, `pacientes_router`, `presupuestos_router`, `caja_service` | `test_caja_recepcion.py`, `test_cuenta_economica.py`, `test_tratamiento_fracasado.py`, `test_rescate_y_caja_23oct.py` | `paso-9-bloqueadores-serial.spec.ts`, `paso-15` |
| F11 | Apps móviles (doctor/paciente) | `app_doctor_router`, `app_paciente_router`, `paciente_auth_*` | `test_paciente_auth_telefono_compartido.py`, `test_multimedia_security.py` | — (no hay e2e de apps en el repo) |
| F12 | Scheduler y Centinela (transversal) | `infrastructure/scheduler.py`, `centinela_service` | `test_centinela.py` | — |

Inventario detallado de tests en `PARIDAD-PRUEBAS.md`.

---

## F1 · Login y sesión del personal

### Objetivo
Que un usuario del centro obtenga sesión web (cookie httpOnly) o bearer (apps/servicios) con sus
accesos y permisos, con freno a fuerza bruta, recuperación de contraseña y logout que borra sesión.

### Archivos
`backend/api/auth_router.py:22-166`, `backend/api/auth_deps.py:28-90`,
`backend/application/services/auth_service.py:36-200`,
`backend/infrastructure/security.py:28-40`, `backend/domain/config/settings.py:76-92`,
`:126-142`, `frontend/src/shared/lib/api.ts:10-47`.

### Contrato observable
| Paso | HTTP | Respuesta | Evidencia |
|---|---|---|---|
| Login web | `POST /auth/login-cookie` `{email,password}` | 200 `{token_type, usuario:{id,nombre,email}, accesos}` — **sin `access_token`**; set-cookie `access_token` HttpOnly | `auth_router.py:71-91` |
| Login bearer (apps) | `POST /auth/login` | 200 + `access_token` en JSON **y** cookie | `auth_router.py:65-68` |
| Sesión actual | `GET /auth/me` | usuario, `rol_nombre`, `centro_activo`, `accesos`, `permisos`, `colaborador_id` | `auth_router.py:122-160` |
| Logout | `POST /auth/logout` | `{ok:true}` + `delete_cookie` con mismos atributos | `auth_router.py:94-98` |
| Olvidé contraseña | `POST /auth/forgot` `{email}` | **siempre** `{ok:true}` (anti-enumeración) | `auth_router.py:101-109` |
| Reset | `POST /auth/reset` `{token,password}` | 200 o 400 token inválido/caducado; mínimo 6 caracteres | `auth_router.py:112-119`; `auth_service.py:158-171` |
| Branding público | `GET /auth/apariencia`, `/auth/apariencia/imagen/{campo}` | config de marca / imagen (3 campos) | `auth_router.py:22-48` |

### Reglas de negocio
1. **JWT HS256, 12 h** (`settings.py:77-78`, `security.py:28-33`). Cookie `HttpOnly`,
   `SameSite=Lax`, `Secure` forzado fuera de development, `max_age=12h`, `path=/`
   (`auth_router.py:84-88`; `settings.py:90-92`, `:145-152`).
2. **Acceso por `user_center_roles`** (no por campo role): el JWT lleva `accesos=[{centro_id,rol_id}]`
   (`auth_service.py:114-125`). `X-Centro-Id` resuelve el centro activo (`auth_deps.py:46-61`).
3. **Permisos efectivos** = (rol − denegados) ∪ directos; `superuser` nunca de rol
   (`auth_service.py:174-197`).
4. **Freno**: N fallos por email dentro de ventana → bloqueo temporal; por defecto **5/15/15 min**,
   configurable, `0` lo desactiva (`settings.py:126-130`, `auth_service.py:68-84`, `:99-112`).
   Cada intento se audita (`auth_service.py:104-126`).
5. **Anti-enumeración**: `forgot` responde igual exista o no el email (`auth_service.py:135-156`);
   el reset usa token aleatorio de un uso con hash SHA-256 y caducidad 1 h (`:141-147`).
6. **No hay token en localStorage** (regla R4, `Archivos MD/CLAUDE.md:34`; cliente con
   `credentials:"include"` en `frontend/src/shared/lib/api.ts:31`).

### Riesgo si se rompe
Todo el sistema (ninguna pantalla entra). Riesgo específico del corte Vercel/Oracle: si el
navegador llama directo a la API y la cookie deja de ser first-party, el login web falla aunque
el endpoint sea idéntico (ver `PARIDAD-API.md` §3). Riesgo de seguridad si se relaja el freno o se
vuelve a exponer el token en JSON.

### Cómo se verifica
- Backend: `backend/tests/test_f0.py` (login, login-cookie, forgot, me, config),
  `test_auth_settings.py` (settings de seguridad), `test_roles_permisos.py` (RBAC),
  `test_centinela.py` (login + Victor).
- E2E: `frontend/e2e/paso-1-auth-real.spec.ts` — 1.1 formulario, 1.2 ruta protegida redirige,
  1.3 login correcto + **cookie httpOnly**, 1.4 contraseña incorrecta, 1.5 ficha, 1.6 logout.
- Manual: `curl -c/-b` contra `/auth/login-cookie`, comprobar `Set-Cookie` con `HttpOnly` y
  `Max-Age=43200`; 5 logins fallidos seguidos → 401 con mensaje de bloqueo.

---

## F2 · Media autenticada y multimedia del paciente

### Objetivo
Servir ficheros clínicos (radiografías, fotos, consentimientos firmados, facturas, media de
WhatsApp) **solo a quien puede verlos**, sin exponer rutas semi-adivinables, y con proxy
anti-IDOR por paciente para el frontend.

### Archivos
`backend/api/media_router.py:1-45`, `backend/api/pacientes_router.py:1048-1120`,
`backend/application/services/multimedia_service.py:1-260`,
`backend/infrastructure/external_apis/drive_client.py`, `orthanc_client.py`,
`backend/api/app_doctor_router.py:345-380` (fotos de estudios).

### Contrato observable
| Operación | Contrato | Evidencia |
|---|---|---|
| `GET /media/{ruta:path}` | Autenticado (JWT personal). 404 si sale de `/media`, si es `media/pacientes/**` (solo por proxy) o si no existe. `Cache-Control: private, max-age=300` | `media_router.py:21-45` |
| `GET /pacientes/{id}/multimedia` | Metadatos de imágenes del paciente (fotos / RX), fuentes local+Drive+Orthanc | `pacientes_router.py:1048-1057`; `multimedia_service.py:1-13` |
| `GET /pacientes/{id}/multimedia/{file_id}?thumb=1` | Binario de la imagen; `file_id` = base64 url-safe de la ruta relativa; 404 si no cuelga de la carpeta del paciente | `pacientes_router.py:1059-1074`; `multimedia_service.py:41-46` |
| `POST /pacientes/{id}/multimedia/{file_id}/analizar-ia` | Sugerencias IA (ver F4) | `pacientes_router.py:1076-1095` |
| `GET /app/doctores/me/fotos/{foto_id}` | Binario de foto de estudio (solo del centro) | `app_doctor_router.py:345-357` |
| `GET /consentimientos/firmar/{code}/pdf` | PDF público **solo** con `signing_code` válido | `consentimientos_router.py:57-99` |

### Reglas de negocio
1. **Nunca `StaticFiles` sin auth** en `/media` (`main.py:154-156`; `media_router.py:1-16`).
2. **Anti-traversal**: `resolve()` + comprobación de que el destino está dentro de `_MEDIA`
   (`media_router.py:30-36`).
3. **Anti-IDOR**: `media/pacientes/**` se rechaza en crudo (404) y solo se sirve por el proxy que
   verifica `paciente.centro_id == centro_id` (`media_router.py:37-39`; `_get_paciente` en
   `paciente_helper.py:9-13`).
4. **Multi-tenant en disco**: si un `num_historia` existe en más de un centro, la fuente local se
   desactiva *fail-closed* para evitar fuga cross-tenant (`multimedia_service.py:74-89`).
5. **Sin base64 en BD**: los ficheros viven en disco/Drive/Orthanc; en BD solo URLs/rutas
   (`multimedia_service.py:1-13`; regla R4 `CLAUDE.md:34`).
6. **Firma pública del consentimiento** es la única excepción sin login, gateada por
   `signing_code` con caducidad (`documentos.py:85-97`).

### Riesgo si se rompe
Fuga de PII clínica (RGPD) si se vuelve a montar `/media` estático, si se sirve `media/pacientes`
por `/media`, o si el proxy pierde el check `paciente∈centro`. Ruptura de la ficha y de la app de
paciente si cambia la forma del `file_id` (es contrato con DentIA y con el frontend).

### Cómo se verifica
- `backend/tests/test_multimedia_security.py` (guards de `MultimediaService`),
  `test_comunicacion_media_dir.py` (media de WhatsApp escribible).
- Manual: pedir `/media/pacientes/<ruta>` con sesión válida → **404**; pedir
  `/pacientes/{id}/multimedia/{file_id}` de otro centro → **404**; pedir `/media/../.env` → 404.
- E2E `paso-9-bloqueadores-serial.spec.ts` (bloqueadores de ficha/paciente).

---

## F3 · Tiempo real SSE (web y apps)

### Objetivo
Empujar al navegador y a las apps los cambios (mensajes de WhatsApp, citas, fotos de estudio,
facturas) sin polling, funcionando con varios workers.

### Archivos
`backend/infrastructure/realtime.py:1-159` (bus Redis + fallback memoria),
`backend/infrastructure/events.py:1-35` (`emit`), `backend/api/comunicacion_router.py:140-158`,
`backend/api/app_doctor_router.py:397-426`, `backend/api/app_paciente_router.py:226-250`,
`backend/main.py:86-92` (bind/connect/aclose en lifespan).

### Contrato observable
| Endpoint | Formato | Filtro | Evidencia |
|---|---|---|---|
| `GET /comunicacion/stream` | `text/event-stream`; `data: {json}` por evento; heartbeat `: heartbeat` cada 15 s | todo el centro (pub/sub `centro:<id>`) | `comunicacion_router.py:140-158` |
| `GET /app/doctores/me/stream` | SSE con `event: <tipo>` + `data: {...}`; heartbeat `: ping` 15 s | solo `cita.*`, `estudio.foto`, `estudio.foto_borrada` | `app_doctor_router.py:397-426` |
| `GET /app/pacientes/me/stream` | SSE; solo eventos con su `paciente_id` | por paciente | `app_paciente_router.py:226-250` |
| `WEBSOCKET /ws/gestoria/{centro_id}?token=` | JSON `{event, data, timestamp}` | centro | `ws_router.py:153-230` |

Eventos de dominio emitidos (contrato de nombres): `cita.creada|actualizada|movida|anulada|
solicitada`, `estudio.foto|foto_borrada`, `presupuesto.creado`, `factura.emitida`, y desde webhook:
`estado_mensaje` (`events.py:1-35`; grep `emit(` en `api/`).

### Reglas de negocio
1. **El payload debe llevar `centro_id`** para propagarse; si afecta a un paciente, también
   `paciente_id` (clave de filtrado del stream del paciente) — `events.py:10-20`.
2. **Redis pub/sub con fallback a memoria**: sin Redis funciona con 1 worker (dev); en producción
   con `--workers 4` es obligatorio Redis para no perder eventos entre workers
   (`realtime.py:1-20`, `:60-90`).
3. **Un único task por proceso** escucha `centro:*` y reparte a colas locales
   (`realtime.py:93-120`).
4. **Heartbeat 15 s** para atravesar proxies; cabeceras `Cache-Control: no-cache` y
   `X-Accel-Buffering: no` en la app del doctor (`app_doctor_router.py:424-426`).
5. **El SSE no transporta estado**: la app, al reconectar, hace refetch completo
   (`mobile/doctor-ios/README.md:80-87`; `app_paciente_router.py:228-231`).
6. El webhook publica eventos tras actualizar BD (`comunicacion_service.py:900-903`).

### Riesgo si se rompe
Web y apps dejan de refrescar (mensajes/citas no aparecen hasta recargar); en Vercel/serverless
las conexiones SSE no pueden vivir en una función (hay que usar streaming compatible o mover el
SSE al servidor de Oracle). Si se pierde Redis con varios workers, fallo silencioso e intermitente
(ya ocurrió: `realtime.py:1-8`).

### Cómo se verifica
- No hay test directo del bus SSE en `backend/tests/` (**NO VERIFICADO por test**). El webhook
  tiene `test_polls_media.py`.
- Manual: `curl -N -H "Cookie: access_token=…" http://…/comunicacion/stream` y enviar un mensaje
  desde otra sesión → debe llegar el `data:`; matar Redis → el stream sigue (modo memoria, 1 worker).
- E2E: no hay spec de SSE; verificar manualmente con la web abierta.

---

## F4 · Análisis IA (incluido el de radiografía de ~30 s)

### Objetivo
Que la IA **sugiera** (nunca imponga): análisis de ortopantomografía (FDI, impactados, canal
dentario, seno maxilar), clasificación de modalidad radiológica, escucha/SOAP de la consulta y el
chat de agentes. La ficha nunca se rompe si la IA cae.

### Archivos
`backend/api/dentia_router.py:1-154`, `backend/api/radiologia_router.py:180-310` y `:459`,
`backend/api/pacientes_router.py:1076-1095`, `backend/api/consulta_router.py:1-200`,
`backend/infrastructure/ia_dental_client.py:1-103`,
`backend/application/services/consulta_service.py`, `backend/infrastructure/llm/*`,
`frontend/next.config.ts:19-20`.

### Contrato observable
| Operación | Contrato | Evidencia |
|---|---|---|
| `POST /pacientes/{id}/dentia/detectar` | `{file_id}` → patrones sugeridos `origen:"ia"` **sin guardar**; 404 si la imagen no es del paciente | `dentia_router.py:127-154` |
| `GET/PUT /pacientes/{id}/dentia?file_id=` | estado por `(paciente, file_id)`; PUT valida categorías/geometría (422) | `dentia_router.py:94-125`, `:70-92` |
| `POST /pacientes/{id}/multimedia/{file_id}/analizar-ia` | sugerencias IA; **503** si el servicio no está configurado/caído | `pacientes_router.py:1076-1095`; `ia_dental_client.py:11-22` |
| `POST /radiologia/{imagen_id}/clasificar` | reclasificación manual/IA de modalidad | `radiologia_router.py:269-285` |
| `POST /pacientes/{id}/radiologia` | sube imagen y responde **antes** de clasificar (clasificación en background) | `radiologia_router.py:190-235` |
| `POST /pacientes/{id}/consulta/analizar` | evidencia hablada → incógnitas; **503** si LLM no disponible (el frontend cae a heurístico) | `consulta_router.py:39-66` |
| `POST /pacientes/{id}/consulta/escucha` | texto de la visita → SOAP sugerido; 403 si Victor/`transcribir_consulta` desactivado; 503 si LLM cae | `consulta_router.py:97-125` |
| `POST /chat/stream` | SSE de tokens del LLM (`text/event-stream`) | `chat_router.py:29-80` |

### Reglas de negocio
1. **Nada se guarda sin confirmar el doctor**: DentIA devuelve sugerencias que la pantalla
   acepta/descarta y luego guarda con PUT (`dentia_router.py:1-9`, `:132-140`).
2. **La subida de radiología no espera a la IA**: clasificación en `BackgroundTasks`
   (`radiologia_router.py:190-210`, `:216-235`).
3. **Timeout del cliente IA dental**: `IA_DENTAL_TIMEOUT` por defecto **120 s**
   (`ia_dental_client.py:8`). El proxy de Next sube el corte a **180 s** por el análisis de
   radiografía (~30 s) (`frontend/next.config.ts:19-20`).
4. **Degradación controlada**: si IA no disponible → 503 y la pantalla sigue funcionando;
   consulta cae al heurístico local (`consulta_router.py:54-60`, `:120-123`).
5. **Cascada LLM**: si el motor local cae, la misma llamada baja por los proveedores de respaldo
   (`infrastructure/llm/fallback_provider.py`; `tests/test_llm_cascada.py`).
6. **Capacidades por agente**: la escucha depende de `capacidad_activa(..., "victor",
   "transcribir_consulta")` (`consulta_router.py:105-109`).
7. **Persistencia DentIA por imagen**: `analisis_dentia` con `file_id` del proxy de multimedia
   (`clinico.py:187-199`).

### Riesgo si se rompe
Diagnóstico asistido inoperativo o, peor, **sugerencias guardadas sin validación** (riesgo clínico
y legal). En Vercel, una función con límite de ejecución <30 s corta el análisis de radiografía;
debe servirse desde Oracle o con el proxy de 180 s. La pérdida de la cascada LLM deja agentes
(chat, escucha, gestor) caídos.

### Cómo se verifica
- Backend: `test_dentia.py` (persistencia, validación, aislamiento por centro, mapeo IA),
  `test_ia_dental_client.py` (error controlado + envío correcto de la imagen),
  `test_llm_cascada.py`, `test_llm_client_reasoning.py`, `test_escucha_determinista.py`,
  `test_pipeline_2etapas_mock.py`, `test_imagen_para_ollama.py`.
- E2E: `paso-7-consulta-real.spec.ts` (camino, escucha, soap, analizar),
  `paso-10-radiologia-real.spec.ts` (subida, hallazgos, modalidades).
- Manual: con `IA_DENTAL_URL` vacía, `POST …/dentia/detectar` → 503 y la ficha responde; con el
  servicio real, medir latencia (objetivo ~30 s) y que la petición no supere 180 s.

---

## F5 · WhatsApp / Evolution

### Objetivo
Bandeja de WhatsApp multi-tenant: recibir mensajes por webhook, guardarlos con dedup, responder
automáticamente (agente Alex / flujos / automatizaciones) o con intervención humana, enviar
mensajes y media, gestionar QR/estado de la instancia y pausas de IA.

### Archivos
`backend/api/comunicacion_router.py:1-645`, `backend/api/motion_router.py`,
`backend/api/voicebot_router.py`, `backend/application/services/comunicacion_service.py:1-1100`,
`backend/application/services/automatizacion_service.py`, `automatizacion_triggers.py`,
`backend/application/services/agente_service.py`, `backend/infrastructure/external_apis/evolution_api.py:1-90`,
`backend/infrastructure/debounce.py:1-48`, `backend/infrastructure/whatsapp_monitor.py:1-36`,
`backend/infrastructure/scheduler.py:57-79`, `comunicacion_router.py:620-640`,
`backend/api/configuracion_centro_router.py:189-215` (integración).

### Contrato observable
| Operación | Contrato | Evidencia |
|---|---|---|
| `GET /comunicacion/whatsapp/estado` | estado operativo de la instancia | `comunicacion_router.py:50-57` |
| `GET /comunicacion/whatsapp/qr` | QR para vincular | `:86-91` |
| `POST /comunicacion/whatsapp/desvincular` | desvincula instancia | `:93-104` |
| `POST /comunicacion/whatsapp/enviar` `{telefono,texto}` | envía; 502 si pasarela caída; 422 si nº inválido | `:107-121`; handler `main.py:130-137` |
| `POST /comunicacion/whatsapp/enviar-media` (multipart) | envía media | `:124-137` |
| `GET /comunicacion/conversaciones` / `…/{id}/mensajes` | bandeja y mensajes | `:160-178` |
| `POST /comunicacion/conversaciones/{id}/mensajes` `{texto}` | respuesta humana | `:180-203` |
| PATCH/DELETE mensaje, leída, archivar, fijar, urgente | estado de la conversación | `:205-400` |
| `POST /comunicacion/webhook/{centro_id}?token=` | entrante de Evolution (público con secreto) | `:620-640` |
| `GET /comunicacion/stream` | SSE (F3) | `:140-158` |
| `POST /comunicacion/agente/probar`, `/agente/chat` | probar/chat del agente | `:449-515` |
| `POST /comunicacion/automatizacion/preview|ejecutar` | automatizaciones | `:600-618` |

### Reglas de negocio
1. **Multi-tenant por integración**: credenciales (url, api_key, instancia) en
   `integraciones.config` del centro (`comunicacion_service.py:86-99`; `evolution_api.py:1-10`).
2. **Dedup atómico por `message_id`** (índice UNIQUE) — no check-then-act
   (`comunicacion_service.py:1-13`, `_insertar_mensaje`).
3. **Match de paciente por teléfono**: igualdad por los últimos 9 dígitos, no subcadena
   (`comunicacion_service.py:185-205`).
4. **Flujo entrante**: guardar entrante → comprobar pausas (conversación, global, paciente sin
   bots) → debounce por ráfaga → agente/flujos → responder (`comunicacion_service.py:883-1000`,
   `debounce.py:1-16`).
5. **Estados de cita por código semántico**, nunca números mágicos del .37
   (`comunicacion_service.py:1-13`).
6. **Pausas**: `conversaciones.ia_pausada_hasta` (por conversación), `ia.pausa_global_hasta`
   (config, por centro, caduca sola), `pacientes.acepta_bots` (`comunicacion_router.py:71-84`,
   `:311-337`; `comunicacion_service.py:436-512`).
7. **Automatización**: scheduler cada minuto, L-S 8:00-20:59 hora Madrid, solo centros con
   integración WhatsApp activa y `agente.alex.automatizacion` (`scheduler.py:57-79`).
8. **Resiliencia de la pasarela**: fallos reales de envío se persisten en auditoría y alimentan la
   máquina de reparación de Centinela (`whatsapp_monitor.py:1-36`); `EvolutionError` se traduce a
   422/502 (`main.py:130-137`).
9. **La IA propone, la persona dispone**: mensajes generados quedan `generado_por_ia` y pueden
   requerir aprobación (`mensajes.generado_por_ia/aprobado`, `comunicacion.py:98-122`).

### Riesgo si se rompe
WhatsApp es el canal principal con pacientes: pérdida de mensajes (dedup mal), respuestas
duplicadas (multi-worker sin lock/debounce), respuestas de IA con pausa activa (molestia a
pacientes), y conflicto con citas. En serverless el webhook puede reintentarse: **el dedup es la
garantía de idempotencia**. La automatización y el webhook dependen de proceso vivo/proxy público:
en Vercel hay que mantener el webhook apuntando a Oracle.

### Cómo se verifica
- Backend: `test_whatsapp_flujos.py` (máquina de estados pura), `test_whatsapp_hora_real.py`
  (hora de entrantes), `test_polls_media.py` (polls y media del webhook sin BD/Evolution),
  `test_voicebot.py`, `test_comunicacion_media_dir.py`, `test_agente*.py`.
- E2E: `paso-11-comunicacion-real.spec.ts` (conversaciones, estadísticas, mensajes, plantillas
  CRUD y validación 422) — **no** envía WhatsApp real.
- Manual: `POST /comunicacion/webhook/{centro_id}?token=<secreto>` con payload de Evolution de
  prueba; repetir el mismo `message_id` → no duplica; con la IA pausada → no responde.

---

## F6 · Gmail / intake de facturas + Gestor IA

### Objetivo
Convertir correos de facturas en `gastos` (o incidencias) de forma clasificada, extraída y
validada, sin duplicados; y que el Gestor IA pueda barrer, revisar y resolver incidencias.

### Archivos
`backend/api/gestoria_router.py:170-340`, `:555-735`; `backend/api/gestor_ia_router.py:1-440`;
`backend/application/services/intake_service.py:1-80` (+ resto),
`extract_service.py`, `gmail_ai_processor.py`, `gmail_ingest_service.py`,
`backend/infrastructure/external_apis/gmail_imap.py:1-60`, `gmail_watch.py:1-40`,
`backend/infrastructure/scheduler.py:81-107`, `:128-145`.

### Contrato observable
| Operación | Contrato | Evidencia |
|---|---|---|
| `GET/PUT /gestoria/email-imap/config`, `POST …/test` | config y prueba IMAP | `gestoria_router.py:170-195` |
| `POST /gestoria/gmail/webhook` `{message_id,history_id}` | encola procesamiento en background | `:210-216` |
| `POST /gestoria/gmail/watch` / `DELETE` / `renovar` / `GET status` | push de Gmail (expira 7 días) | `:221-267`; `gmail_watch.py:1-12` |
| `POST /gestoria/buzon/procesar` / `reintentar-incidencias` / `GET incidencias-count` | barrido del buzón e incidencias | `:625-680` |
| `POST /gestoria/gastos/upload`, `clasificar-ia`, `reprocesar`, `reprocesar-lote` | alta/reproceso de gastos | `:555-624` |
| `GET /gestoria/gestor/estado|facturas|proveedores|revision|revision/agrupada|descartes` | motor IA | `gestor_ia_router.py:53-320` |
| `POST /gestoria/gestor/revision/resolver`, `/barrer`, `/revisadas` | resolver y barrer | `gestor_ia_router.py:255-440` |

### Reglas de negocio
1. **Pipeline en 3 etapas**: clasificador (factura/no factura/portal) → extracción OCR 2 etapas →
   validador (IVA/IRPF/suplidos) → proveedor por CIF (sin duplicados) (`intake_service.py:1-20`).
2. **Carpetas reales del buzón** (corregidas 22-oct-2026): `Gastos/1. Gastos sin procesar`,
   `Gastos/4. Gastos Procesados`, `Gastos/5. Incidencias`, `Gastos/3. Gastos revisados`
   (`intake_service.py:40-56`). No inventar nombres de carpeta.
3. **Facturas revisadas se registran SIEMPRE**; incidencias no registran nada hasta decisión humana
   (`intake_service.py:10-32`).
4. **Idempotencia** por `gmail_message_id` (único en `facturas_gestor`, `gestor_ia.py:20-40`) y por
   proveedor normalizado.
5. **Scheduler**: ingesta 2×/día (08:00 y 20:00 Madrid) y conciliación 08:30
   (`scheduler.py:366-380`).
6. **Gmail watch** expira a los 7 días y debe renovarse (`gmail_watch.py:1-8`).
7. **Acceso a Gmail** se valida por IMAP real; hay prueba de acceso (`tests/test_acceso_gmail.py`).

### Riesgo si se rompe
Facturas sin registrar (pérdida fiscal) o duplicadas (descuadre contable). Cambiar nombres de
carpeta rompe el flujo en silencio (ya pasó: 827 correos esperando, `intake_service.py:40-48`).
El webhook de Gmail debe apuntar al backend que esté vivo (Oracle), no a Vercel.

### Cómo se verifica
- Backend: `test_intake_service.py` (orquestador sobre SQLite, red mockeada),
  `test_gmail_ai_processor.py`, `test_clasificador_no_factura.py`, `test_extract_qwen35.py`,
  `test_pipeline_2etapas_mock.py`, `test_factura_1515_consenur.py` (factura real difícil),
  `test_factura_archivo_anio.py`, `test_gestor_facturas_reales.py`, `test_acceso_gmail.py`.
- E2E: `paso-12-gestoria-real.spec.ts` (facturas/gastos/movimientos; no Gmail real).
- Manual: reenviar el mismo correo dos veces → un solo gasto; cargar un PDF no-factura → incidencia.

---

## F7 · Facturación / gestoría

### Objetivo
Cerrar el circuito económico-fiscal: producción por doctor, facturas emitidas, gastos, banco,
conciliación, liquidaciones, modelos fiscales y envío a la asesoría, con trazabilidad VERI\*FACTU.

### Archivos
`backend/api/gestoria_router.py:61-1254` (86 endpoints), `backend/api/gestor_ia_router.py`,
`backend/application/services/gestoria_service.py:1-40`, `conciliacion_service.py:1-30`,
`imputacion_service.py`, `gastos_export_service.py`, `factura_archivo.py`,
`backend/domain/services/verifactu.py:1-100`, `backend/infrastructure/scheduler.py:128-199`.

### Contrato observable (subconjunto representativo)
| Operación | Contrato | Evidencia |
|---|---|---|
| `GET /gestoria/produccion/doctores|tratamientos` | producción por doctor/tratamiento | `gestoria_router.py:61-90` |
| `POST /gestoria/produccion/pacientes/factura`, `/autofactura` | factura de producción/autofactura | `:91-125` |
| `GET /gestoria/facturas`, `GET /gestoria/historico` | facturación emitida | `:151-170`, `:1218-1254` |
| `POST /gestoria/gastos`, `PATCH`, `DELETE`, `GET export-excel` | gastos | `:433-460`, `:512-535` |
| `POST /gestoria/banco/cuadrar`, `GET /gestoria/banco/revision` | conciliación | `:681-695`, `:794-820` |
| `GET /gestoria/movimientos`, `POST /import-xlsx` | extractos/movimientos | `:964-1056` |
| `GET/PUT /gestoria/modelos-fiscales`, `POST …/generar` | modelos fiscales | `:1097-1150` |
| `POST /gestoria/envio`, `GET /gestoria/envio/csv` | envío a la asesoría | `:1179-1218` |
| `GET /gestoria/contabilizacion` | informe contable (vista SQL) | `:492-511` |
| `GET /gestoria/gestor/*` | motor IA de facturas (F6) | `gestor_ia_router.py` |

### Reglas de negocio
1. **Un solo dueño del dato**: `tratamientos_realizados` no lleva cobros; deudas en `deudas`,
   dinero en `pagos`, enlace en `deuda_pago` (`caja_service.py:1-13`).
2. **Conciliación idempotente y con dry-run**: casar factura → recurrentes → bandeja de revisión
   (`conciliacion_service.py:1-15`).
3. **Formas de pago canónicas**: efectivo/metálico/caja y tarjeta personal de Manzanedo son pagos
   **no bancarios** (no conciliables contra extracto) (`gestoria_service.py:32-40`).
4. **VERI\*FACTU**: huella encadenada (SHA-256 mayúsculas), formato de fechas/importes fijo,
   QR de cotejo; los valores se persisten en `presupuestos.hash_factura/codigo_qr` y documentos
   (`domain/services/verifactu.py:1-20`, `:53`, `:78`; `tests/test_verifactu.py`).
5. **Envío programado a la asesoría**: cada día 07:00 se comprueba `gestoria.envio_auto` y se
   envía solo el día programado, sin duplicar el mes (`scheduler.py:128-145`).
6. **Modelos fiscales y calendario tributario**: catálogo y generación por centro
   (`gestoria_router.py:1097-1150`).
7. **Importes `Decimal` y 2 decimales fiscales**; no floats (ver `PARIDAD-DATOS.md` §7.2).

### Riesgo si se rompe
Descuadre contable/fiscal, presentaciones erróneas, pérdida de trazabilidad AEAT. Un cambio de
redondeo o del orden de campos en la huella **invalida las facturas**. La conciliación toca
`pagos`/movimientos: un fallo puede duplicar o borrar movimientos (idempotencia obligatoria).

### Cómo se verifica
- Backend: `test_gestoria_contrato.py` (invariantes del área), `test_conciliacion.py`,
  `test_verifactu.py` (ejemplos AEAT), `test_cuenta_economica.py`, `test_gastos_export_service.py`,
  `test_gestor_agente.py` (solo lectura), `test_factura_1515_consenur.py`.
- E2E: `paso-12-gestoria-real.spec.ts` (facturas, gastos CRUD, 422, movimientos).
- Manual: generar una factura y validar huella/QR contra el ejemplo de la AEAT; ejecutar
  `/gestoria/banco/cuadrar` con `execute=false` (dry-run) y comprobar que no escribe.

---

## F8 · Agenda

### Objetivo
Gestionar la agenda del centro: ver huecos, crear/mover/anular citas, cambiar estado y emitir
justificante, con las mismas reglas que aplicaba la pantalla del .37.

### Archivos
`backend/api/agenda_router.py:1-460`, `backend/api/configuracion_agenda_router.py:1-355`,
`backend/application/services/cita_reglas.py:1-200`,
`backend/application/services/disponibilidad_service.py:1-95`,
`backend/domain/services/disponibilidad.py`, `backend/api/agenda_router.py:416-460` (PDF).

### Contrato observable
| Operación | Contrato | Evidencia |
|---|---|---|
| `GET /agenda/referencias` | agendas, gabinetes, estados, tipos, colaboradores del centro | `agenda_router.py:43-92` |
| `GET /agenda/citas?fecha=` | citas del día (vista calendario) | `:129-174` |
| `GET /agenda/huecos` | huecos disponibles | `:242-292`; `disponibilidad_service.py:42-95` |
| `POST /agenda/citas` | crea cita (201) | `:294-316` |
| `PUT /agenda/citas/{id}` / `/mover` / `/anular` / `/estado` | edita/mueve/anula/estado | `:318-414` |
| `GET /agenda/citas/{id}/justificante` | PDF justificante | `:416-460` |
| `GET /agenda/panel` | panel de agenda | `:176-240` |
| `GET/POST/PUT/DELETE /configuracion/agenda/…` | agendas, tipos, estados, gabinetes, horarios, excepciones, bloqueos | `configuracion_agenda_router.py:75-355` |

### Reglas de negocio (una sola fuente: `cita_reglas.py`)
1. **Obligatorios**: fecha, hora, duración, tipo, nombre, apellidos, teléfono y gabinete; con ficha
   se completan desde el paciente (`cita_reglas.py:1-16`, `:60-140`).
2. **Catálogos del centro**: tipo, gabinete, doctor, agenda y estado deben existir en el centro
   (`cita_reglas.py:11-12`).
3. **Disponibilidad**: ni festivo, ni día cerrado, ni fuera de turnos del centro, ni franja
   bloqueada (`cita_reglas.py:13`, `:66-100`; festivos/horario en config `centro.festivos`,
   `centro.horario`).
4. **Gabinete↔doctor** por `colaborador_horarios`: si el gabinete tiene doctor asignado a esa
   hora, la cita es de ese doctor (`cita_reglas.py:14-15`).
5. **Duración**: si no viene, la configurada por doctor+tipo (Config → Colaboradores)
   (`cita_reglas.py:16`).
6. **Estados por código semántico**, no ids hardcodeados salvo el 5 de tratamientos
   (`disponibilidad_service.py:25-40`).
7. **Eventos**: cada cambio publica `cita.*` para SSE (`agenda_router.py:313`, `:341`, `:365`,
   `:385`, `:410`).
8. **Cross-tenant**: toda operación sobre una cita valida centro (IDOR cubierto por test).

### Riesgo si se rompe
Doble reserva de gabinete/doctor, citas fuera de horario o sin gabinete (ya pasó: citas 49004/49005,
`cita_reglas.py:1-8`), pacientes citados en festivo. En el rebuild, si el frontend de Vercel
calcula huecos localmente y el backend también, hay dos verdades: el cálculo debe quedarse en el
backend (`disponibilidad_service.py`).

### Cómo se verifica
- Backend: `test_cita_reglas.py` (obligatorios, desconocidos, disponibilidad), `test_disponibilidad.py`
  (motor de huecos puro), `test_agenda_cross_tenant.py` (IDOR), `test_selectores_doctores.py`,
  `test_cita_id_cita.py` (identidad de cita), `test_pulso_citas_hoy.py` (Inicio).
- E2E: `paso-8-agenda-real.spec.ts` (referencias, huecos, crear, 422 sin fecha/hora, filtro, mover),
  `agenda-cabeceras.visual.ts` (visual).
- Manual: crear cita en festivo y sin gabinete → 422 con mensaje legible; mover cita a hueco
  ocupado → 422.

---

## F9 · Odontograma y periodontograma

### Objetivo
Registrar el estado dental por pieza (hallazgos editables) y las exploraciones periodontales por
sitio, con el mismo contrato JSON que el .37 (`teeth`), y pintar también los tratamientos realizados.

### Archivos
`backend/api/pacientes_router.py:1215-1430`, `backend/domain/models/dental.py:1-60`,
`backend/api/pacientes_router.py:1039-1046` (actos realizados), frontend
`frontend/src/features/patients/**` (ficha).

### Contrato observable
| Operación | Contrato | Evidencia |
|---|---|---|
| `GET /pacientes/{id}/odontograma` | `{teeth:[{pieza,cara,estado,obs,tipoRegistro,fecha}], realizados:[…]}` | `pacientes_router.py:1221-1259` |
| `PUT /pacientes/{id}/odontograma` `{teeth:[…]}` | autosave: **reemplaza** todos los hallazgos; devuelve `{ok,n}` | `:1264-1290` |
| `GET /pacientes/{id}/periodontograma?exploracion_id=` | `{piezas:{FDI:{v:[6],p:[6],mob}}, bop, bolsas4, fecha, exploracion_id}` | `:1333-1357`, `_perio_response` `:1300-1330` |
| `GET /pacientes/{id}/periodontograma/estudios` | lista de exploraciones | `:1359-1396` |
| `POST /pacientes/{id}/periodontograma` | crea exploración | `:1398-1430` |

### Reglas de negocio
1. **Contrato `teeth` idéntico al .37** (`pacientes_router.py:1224`).
2. **Autosave que reemplaza**: PUT borra e inserta (no merge) — el cliente manda el estado completo
   (`:1269-1288`).
3. **Solo se pintan realizados con estado 5 (Realizado) e importe** (`:1238-1259`): el odontograma
   no muestra previstos.
4. **Piezas FDI como texto**; en periodontograma se migra índice 0-31 → FDI con tabla fija
   (`:1293-1300`).
5. **6 sitios por pieza** (vestibular 1-3, palatino/lingual 4-6), BOP% y bolsas ≥4 calculados
   (`:1300-1330`).
6. **Hallazgos ligados a paciente (y opcionalmente tratamiento/cita)** (`dental.py:17-30`).

### Riesgo si se rompe
Pérdida del historial dental (el PUT destructivo es el mayor riesgo: un cliente que mande una lista
parcial borra hallazgos), o desalineación FDI (pieza equivocada). Cambiar el contrato `teeth` rompe
la ficha y el editor.

### Cómo se verifica
- Backend: `test_fdi.py` (numeración), `test_ficha_layout_config.py` (layout de ficha configurable).
  **NO hay test específico del endpoint de odontograma** — hueco a cubrir en el rebuild.
- E2E: `paso-2-pacientes-crud-real.spec.ts` (ficha 2.6) y `paso-15-integracion-e2e-real.spec.ts`
  (flujo completo del paciente).
- Manual: guardar 2 hallazgos, recargar → persisten; guardar lista vacía → se vacía; comparar JSON
  byte a byte con el legacy para el mismo paciente.

---

## F10 · Caja y cuenta económica

### Objetivo
Cobrar en recepción (Inicio) con el modelo deuda↔pago↔saldo, sin duplicar dinero ni dejar cobros
huérfanos, y con devoluciones/traspasos de saldo correctos.

### Archivos
`backend/api/inicio_router.py:1-114`, `backend/api/pacientes_router.py:109-330`,
`backend/application/services/caja_service.py:1-40` (+ resto),
`backend/api/presupuestos_router.py` (aceptar/realizar).

### Contrato observable
| Operación | Contrato | Evidencia |
|---|---|---|
| `GET /inicio/paciente/{id}/caja` | deudas abiertas + actos sin cargo + formas de pago de caja | `inicio_router.py:92-100` |
| `POST /inicio/paciente/{id}/cobro` | 201; aplicaciones a deuda/acto, saldo a cuenta o a presupuesto | `:102-115` |
| `POST /pacientes/{id}/pagos` | registrar cobro (ruta antigua/compatibilidad) | `pacientes_router.py:109-196` |
| `POST /pacientes/{id}/saldo/traspasar` / `/devolver` | mover/devolver saldo | `:199-260` |
| PATCH pago `/liberar` / `/reasignar` | deshacer/imputar pagos | `:279-330` |
| `POST /pacientes/{id}/actos/{id}/marcar-fracasado` | abono negativo + crédito | `:262-277` |

### Reglas de negocio
1. **Tres formas de aplicar un pago**: a tratamiento (nunca más que el pendiente), a presupuesto
   aceptado (solo tratamientos de ese presupuesto), o a cuenta (`caja_service.py:1-20`).
2. **Saldo = importe − aplicado**; se aplica por fecha (`deuda_pago`) (`caja_service.py:18-20`).
3. **Cargar el acto al cobrar** si aún no tiene deuda, para que deuda y pago queden enlazados
   (`caja_service.py:1-8`).
4. **Presupuesto que admite pagos**: estado 3/4/5/6 (`caja_service.py:31`).
5. **`CajaError` → 422 y `CajaNoEncontrado` → 404** por handlers globales (`main.py:120-127`).
6. **Tratamiento fracasado**: abono en negativo + crédito a favor; un solo dueño del dato
   (`tests/test_tratamiento_fracasado.py`, `test_un_solo_dueno.py`).

### Riesgo si se rompe
Cobros duplicados/perdidos, saldos mal calculados, descuadre con gestoría. Es el flujo con más
tests de dinero del repo: cualquier divergencia es detectable.

### Cómo se verifica
- Backend: `test_caja_recepcion.py` (cargar acto y cobrar, enlazando deuda↔pago),
  `test_cuenta_economica.py` (tres formas de pago, liberar/reasignar),
  `test_tratamiento_fracasado.py`, `test_rescate_y_caja_23oct.py`, `test_un_solo_dueno.py`.
- E2E: `paso-9-bloqueadores-serial.spec.ts`, `paso-15-integracion-e2e-real.spec.ts`.
- Manual: cobrar un acto dos veces → 422; devolver más que el saldo → 422.

---

## F11 · Apps móviles (doctor/paciente)

### Objetivo
Mantener el contrato que consumen las apps nativas (agenda del día, pacientes, toma de fotos de
estudios, login OTP del paciente, facturas/justificantes PDF) sobre el gateway `/app/*`.

### Archivos
`mobile/doctor-ios/README.md:1-130`, `mobile/doctor-android/**`,
`backend/api/app_doctor_router.py:1-426`, `backend/api/app_paciente_router.py:1-251`,
`backend/api/paciente_auth_router.py:1-64`.

### Contrato observable
Ver `PARIDAD-API.md` §9 (lista cerrada de 22 endpoints + transporte Bearer + `X-Centro-Id` + SSE +
códigos 401/428). Resumen: 13 del doctor (`app_doctor_router.py:55`) + 9 del paciente
(`app_paciente_router.py:41`).

### Reglas de negocio
1. **Token en el almacén seguro del sistema**, nunca cookie (apps) — `paciente_auth_deps.py:1-13`.
2. **OTP**: 6 dígitos, hash, 10 min, máx 5 intentos/15 min, 428 si falta nombre por teléfono
   compartido (`settings.py:137-141`; `paciente_auth_router.py:40-64`).
3. **Foto de estudio**: subida multipart, metadatos de protocolo, borrado con evento
   (`app_doctor_router.py:286-380`).
4. **SSE del doctor**: eventos de su centro filtrados por tipo (F3).

### Riesgo si se rompe
Las apps ya instaladas dejan de funcionar (no hay actualización forzosa garantizada). Es el contrato
más caro de romper. No debe tocarse sin versionar la API (`/v2`) o mantener compatibilidad.

### Cómo se verifica
- Backend: `test_paciente_auth_telefono_compartido.py`, `test_multimedia_security.py`,
  `test_agenda_cross_tenant.py` (indirecto).
- **No hay e2e de apps móviles en el repo** (no compilables aquí): verificación manual con las
  apps reales. El README del doctor afirma que no se ha podido compilar en el entorno del proyecto
  (`mobile/doctor-ios/README.md:20-30`). **NO VERIFICADO en ejecución**.

---

## F12 · Scheduler y Centinela (transversal a todos los flujos)

### Objetivo
Ejecutar los trabajos periódicos de forma **idempotente y única** aunque haya 4 workers, y vigilar
la salud del sistema (BD, disco, servicios, comportamiento web, WhatsApp zombi) con reparación y
alertas.

### Archivos
`backend/infrastructure/scheduler.py:1-423`, `backend/application/services/centinela_service.py`,
`backend/infrastructure/jobs_heartbeat.py`, `error_monitor.py`, `docker_client.py`,
`backend/main.py:140-152`.

### Contrato observable (jobs)
| Job | Cadencia | Evidencia |
|---|---|---|
| Automatización WhatsApp | 1 min, L-S 8:00-20:59 Madrid | `scheduler.py:366` |
| Ingesta facturas (IMAP) | 08:00 y 20:00 | `:369` |
| Conciliación banco | 08:30 | `:372` |
| Envío a asesoría | 07:00 diario (condicional) | `:375` |
| Caducidad presupuestos | 06:00 | `:378` |
| Caducidad contratos | 06:10 | `:381` |
| Detector RX (Orthanc→Drive) | cada 30 s | `:384` |
| Centinela (vigilancia) | tick 10 s, por centro según slider | `:388` |
| ANALYZE nocturno / purgas / disco | 03:00 / 04:00 / 04:30 / 05:00 | `:391-397` |
| Heartbeat Centinela | 06:30 | `:399` |
| Copia de seguridad | L-V 15:00 y 22:00 | `:404` |

**Contrato crítico:** un único scheduler por despliegue mediante **lock consultivo de Postgres**
(`pg_try_advisory_lock`, `scheduler.py:35-55`); sin él, 4 workers duplicarían WhatsApp, alertas y
reparaciones (`:26-32`).

### Reglas de negocio
1. **Idempotencia** de todos los jobs (los comentarios del fichero la exigen job a job).
2. **Un centro no puede tumbar el tick** (try/except por centro; p. ej. `:110-120`).
3. **Centinela cuenta errores 5xx reales** con middleware para avisar de "la web falla"
   (`main.py:140-152`).
4. **Backups verificados** y aviso si fallan (`scheduler.py:309-340`).

### Riesgo si se rompe
En Vercel/serverless no hay proceso vivo ni `BackgroundScheduler`: automatizaciones, ingesta,
conciliación, detector RX y backups **dejan de ejecutarse**. Hay que externalizarlos (cron/cola en
Oracle). Si se despliegan varios schedulers sin el lock, WhatsApp automático se duplica.

### Cómo se verifica
- Backend: `test_centinela.py`, `test_rescate_y_caja_23oct.py` (parte de reparación).
- Manual: arrancar dos procesos backend y comprobar que solo uno loguea "scheduler activo" (el
  lock); revisar `jobs_heartbeat` (tabla de latidos) para ver el último éxito de cada job.
