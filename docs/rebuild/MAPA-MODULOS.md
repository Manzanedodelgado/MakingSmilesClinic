# MAPA-MÓDULOS — MakingSmiles_Studio

> **Qué es.** El mapa de módulos del legacy (`master` @ `a76ee81`) y el plan de reconstrucción
> por módulos con **corte progresivo** (frontend en Vercel, API en Oracle Cloud; cada módulo nuevo
> debe comportarse igual que el legacy antes de cortarse).
>
> **Para qué sirve.** Decide **qué se reconstruye, en qué orden y por qué**, con las dependencias
> verificadas contra el código. Es el puente entre `PARIDAD-API.md`, `PARIDAD-DATOS.md`,
> `PARIDAD-FLUJOS.md` y `PARIDAD-PRUEBAS.md` (contrato) y `INFRA.md` (destino físico).
>
> Evidencia `ruta:línea` en todo. Lo no verificado se marca **NO VERIFICADO**.

---

## 1. Criterio de módulo y método

Un **módulo** aquí es una unidad de corte verificable:

```
1 router (o familia de routers) de backend/api/
  + sus servicios de aplicación (backend/application/services/)
  + sus tablas/modelos (backend/domain/models/)
  + su feature de frontend (frontend/src/features/<x>) y páginas (frontend/src/app/(app)/…)
  + sus flujos (PARIDAD-FLUJOS.md) y tests (PARIDAD-PRUEBAS.md)
```

Base medida: **43 routers / 498 operaciones** (`PARIDAD-API.md` §2), **142 tablas**
(`PARIDAD-DATOS.md` §1), **9 features de frontend** (`frontend/src/features/`: agenda, agentes,
auth, comunicacion, gestoria, ia, informes, inicio, patients) y **39 páginas** de Next
(`frontend/src/app/**/page.tsx`).

Esta agrupación **no la impone el código** (el legacy no tiene módulos explícitos): se ha derivado
del grafo de dependencias real (§3) y de los flujos compartidos. Los routers que quedan fuera de
toda agrupación razonable se marcan en §2.

---

## 2. Mapa de módulos

Leyenda de **destino**: `API` = servicio FastAPI en Oracle (mismo path, contrato de
`PARIDAD-API.md`); `WEB` = feature/página Next en Vercel; `MOBILE` = contrato que consumen las apps;
`EXT` = servicio externo (Evolution, Gmail, Orthanc, Drive, LLM) que se queda fuera del corte.

| ID | Módulo | Responsabilidad | Backend (routers / servicios / tablas) | Frontend | Destino | Depende de |
|---|---|---|---|---|---|---|
| **M00** | Plataforma, scheduler y Centinela | Proceso vivo, jobs, backups, vigilancia, salud | `main.py`, `infrastructure/scheduler.py`, `centinela_service`, `backup_service`, `jobs_heartbeat`, `health_router` (3 rutas), `docker_client`/`whatsapp_monitor` | — | API (Oracle, proceso continuo) | — |
| **M01** | Identidad, sesión y RBAC | Login web/app, JWT, cookies, permisos, alta de personal/roles, reset | `auth_router` (8), `paciente_auth_router` (2), `configuracion_staff_router` (11), `configuracion_roles_router` (4); `auth_service`, `paciente_auth_service`; tablas `usuarios`, `usuario_periodos`, `roles`, `permisos`, `role_permisos`, `user_center_roles`, `user_center_permisos(_denegados)`, `password_resets`, `paciente_otps`, `platform_users` | `features/auth`, `/login`, `/recuperar`, `/restablecer`, shell `(app)/layout.tsx` (permisos del rail) | API + WEB; MOBILE (Bearer) | — (cimiento) |
| **M02** | Configuración e integraciones | CONFIG como fuente de la verdad (jerarquía plataforma→centro→sistema→usuario), catálogos de centro/agenda/admin, apariencia, uploads | `config_router` (4), `configuracion_centro_router` (12), `configuracion_agenda_router` (20), `configuracion_admin_router` (12), `uploads_router` (1); `config_service`; tablas `configuraciones`, `integraciones`, `centros`, `centro_asociaciones`, `razones_sociales` | `(app)/configuracion/*` (clinica, admin, conectores, automatizaciones, flujos, agentes) | API + WEB; MOBILE (iconos/logo) | M01 |
| **M03** | Núcleo de pacientes | Ficha, filiación, búsqueda, anamnesis, tarifas, foto, geografía | `pacientes_router` (36), `geo_router` (5); `paciente_helper`, `multimedia_service` (foto); tablas `pacientes`, `paciente_seguros`, `consentimientos_paciente`, `colaboradores`(lectura), geo | `features/patients`, `(app)/pacientes/*` (ficha, filiación, alertas, cascabel, documentos, plan-econ, odontograma, periodontograma, dentia, consulta, radiologia, presupuestos) | API + WEB; MOBILE (resumen paciente) | M01, M02 |
| **M04** | Media y multimedia clínica | Servir ficheros clínicos autenticados, proxy anti-IDOR, fuentes local/Drive/Orthanc, fotos de perfil/estudios | `media_router` (1), `app_doctor_router` (fotos), `multimedia_service`, `drive_client`, `orthanc_client`; tablas `imagenes_rx`, `pacientes.foto_url`, ficheros en `backend/media` | ficha/radiología (consumo vía `/api`) | API (Oracle; `/media` **no** por Vercel, ver `INFRA.md` §5.2); MOBILE (fotos) | M03 |
| **M05** | Agenda y recursos | Citas, huecos, mover/anular/estado, justificante, agendas/gabinetes/tipos/estados/horarios/bloqueos | `agenda_router` (11), secciones de agenda de `configuracion_agenda_router`; `cita_reglas`, `disponibilidad_service`, `domain/services/disponibilidad`; tablas `citas`, `agenda*` (agendas, gabinetes, tipos_cita, estados_cita, colaborador_horarios, bloqueos_agenda), `cita_tratamiento` | `features/agenda`, `(app)/agenda` | API + WEB; MOBILE (agenda del doctor) | M01, M02, M03 |
| **M06** | Inicio / pulso y CRM | Panel de Inicio, citas del día, paciente de agenda, conversación, CRM | `inicio_router` (6), `crm_router` (2); `pulso_service`, `inicio_paciente_service`, `crm_service` | `features/inicio`, `(app)/inicio`, `(app)/crm` | API + WEB | M03, M05, M12 |
| **M07** | Historia clínica y consulta | Actos clínicos, recetas, alertas, medicación, plan próxima, consulta viva (analizar/escucha/SOAP/recetas frecuentes/recomendaciones), cefalometría | `clinico_router` (15), `consulta_router` (13), `cefalometria_router` (9); `consulta_service`, `cefalometria_service`, `receta_pdf`, `consulta_service`; tablas clínicas (`tratamientos_realizados`, `soap`, `alertas_paciente`, `recetas`, `receta_lineas`, `plan_proxima_cita`, `recomendaciones_paciente`, `vademecum`, `medic_preescrita`, `cefalometrias`, `analisis_cefalo`) | `(app)/pacientes/[id]/consulta`, `alertas`, `cascabel`, `pacientes/[id]` | API + WEB | M03, M04, M05 |
| **M08** | Odontograma y periodontograma | Estado dental por pieza/sitio, contrato `teeth`, autosave, estudios periodontales | Secciones de `pacientes_router` (`:1215-1430`); modelos `dental.py`; tablas `odontograma_entradas`, `periodontograma_medidas` | `(app)/pacientes/[id]/odontograma`, `/periodontograma` | API + WEB | M03 |
| **M09** | Documentos, recetas y consentimientos | Recetas y PDFs, consentimientos + firma pública, documentos de paciente/admin, plantillas, talonarios | `documentos_router` (8), `consentimientos_router` (14), PDFs de `clinico_router`/`presupuestos_router`; `consentimiento_service`, `consentimiento_pdf`, `documento_pdf`, `receta_pdf`; tablas `documentos_*`, `consentimientos`, `recetas*`, `talonarios`, `plantillas_documento`, `documentos_firmados` | `(app)/pacientes/[id]/documentos`, `app/firmar/[code]` | API + WEB (PDF) | M03, M07 |
| **M10** | Presupuestos y plan económico | Presupuesto con líneas, estados, entrega/aceptación/anulación, previstos, realización en cita, PDF/envío | `presupuestos_router` (15); `presupuesto_service`, `authorization_service`, `presupuesto_service`; tablas `presupuestos`, `presupuesto_lineas`, `estados_presupuesto`, `presupuestos_predisenados*`, `tratamientos_previstos` | `(app)/pacientes/[id]/presupuestos`, `plan-econ` | API + WEB | M03, M07 |
| **M11** | Caja, cobros y cuenta económica | Deudas, pagos, saldo, traspasos/devoluciones, liberar/reasignar, tratamientos fracasados, formas de pago | Secciones de `pacientes_router` (`:75-330`), `inicio_router` caja/cobro; `caja_service`, `formas_pago_service`; tablas `pagos`, `deudas`, `deuda_pago`, `formas_pago`, `financieras`, `liquidaciones*`, `facturas_historico` (lectura) | `(app)/inicio` (caja de recepción), ficha (`plan-econ`) | API + WEB | M10, M07 |
| **M12** | Comunicación / WhatsApp | Bandeja, envío, webhook Evolution, plantillas, pausas de IA, SSE, estadísticas, contexto, automatizaciones de canal | `comunicacion_router` (42), `motion_router` (8), `voicebot_router` (5); `comunicacion_service`, `automatizacion_service`, `automatizacion_triggers`, `voicebot_service`, `agente_service`; tablas `conversaciones`, `mensajes`, `plantillas_mensaje`, `recalls`, `envios_*`, `llamadas_voz`, `poll_contexto`, `acciones_boton` | `features/comunicacion`, `(app)/comunicacion`, `(app)/motion` | API + WEB; **EXT** Evolution | M01, M03, M05 |
| **M13** | Agentes IA conversacionales | Catálogo/config de agentes (Víctor, Aura, Alex, Gestor), personalidad, permisos por canal, chat, revisiones, migración de agentes | `agentes_router` (18), `agentes_db_router` (13); `agente_service`, `agentes_config`, `aura_*`, `victor_*`, `gestor_agente`, `agente_permisos_service`, `personalidad_service`, `canal_ajuste_service`; tablas `agentes*`, `agente_revisiones` | `features/agentes` (Rueda, VictorChat), `(app)/configuracion/agentes/rueda` | API + WEB; **EXT** LLM | M01, M12 |
| **M14** | IA dental, radiología y ortodencia | DentIA (análisis guiado por imagen), radiología (importar, clasificar, hallazgos, anotaciones, PPTX, DICOM), ortopantomografías IA, casos de ortodoncia, LLM diagnóstico | `dentia_router` (3), `radiologia_router` (18), `casos_ortodoncia_router` (9), `llm_router` (2); `radiologia_service`, `radiologia_export_service`, `radiologia_pptx`, `cefalometria_pdf`, `estudio_ortodoncia_pdf`, `ia_dental_client`; tablas `imagenes_rx`, `hallazgos_imagen`, `anotaciones_imagen`, `analisis_dentia`, `casos_ortodoncia`, `intervenciones_ortodoncia`, `estudios_ortodoncia`, `fotos_ortodoncia`, `rx_exportada`, `romexis_sync` | `(app)/pacientes/[id]/dentia`, `/radiologia` | API + WEB (análisis asíncrono, `INFRA.md` §5.4); **EXT** IA dental/Orthanc/Drive | M03, M04 |
| **M15** | Gestoría y Gestor IA | Producción/facturación, gastos, banco, conciliación, extractos, modelos fiscales, envío a asesoría, intake Gmail, motor IA de facturas, VERI\*FACTU | `gestoria_router` (86), `gestor_ia_router` (9); `gestoria_service`, `conciliacion_service`, `imputacion_service`, `intake_service`, `extract_service`, `gmail_ai_processor`, `gmail_ingest_service`, `gastos_export_service`, `factura_archivo`, `gestor_agente`; tablas `gastos`, `gasto_incidencias`, `proveedores`, `movimientos_bancarios`, `extractos_subidos`, `liquidaciones*`, `deudas`, `modelos_fiscales`, `facturas_gestor`, `proveedores_gestor`, `revisiones_gestor`, `descartes_gestor`, `pasadas_gestor`, `facturas_historico`; vistas `informe_contable`, `informe_gastos`, `informe_juan_antonio` | `features/gestoria`, `(app)/gestoria/[modo]` | API + WEB; **EXT** Gmail/IMAP/Drive/SMTP | M01, M02, M11, M12; fiscal |
| **M16** | Informes | Editor de informes/tabla dinámica con allowlist y scoping multi-tenant | `informes_router` (13); `informes_catalogo`, `informes_join`; tabla `informes` | `features/informes`, `(app)/informes` | API + WEB | M01, M02, M07, M11, M15 |
| **M17** | SuperUser y tenant interno | Plataforma de centros, módulos/planes, DB explorer, provisionar centros/personal; router interno servicio-a-servicio | `superuser_router` (19), `internal_tenant_router` (8); `centinela_service`, `provision_service`, `platform_db`; BBDD de plataforma + `centros`, `auditoria` | `(app)/superuser` | API + WEB (BBDD plataforma) | M01, M02 |
| **M18** | Integraciones puente | Romexis (bridge de RX y alta de pacientes), relé Ollama, Jarvis operador, chat LLM | `romexis_router` (5), `ollama_relay_router` (1), `jarvis_operador_router` (2), `chat_router` (2); `multimedia_service`, `llm_config` | — | API; **EXT** Romexis/Ollama/Jarvis | M03, M04, M13, M14 |
| **M19** | Gateways de apps móviles | Contrato de las apps nativas doctor/paciente (Bearer, `X-Centro-Id`, OTP, SSE, PDFs) | `app_doctor_router` (13), `app_paciente_router` (9); `disponibilidad_service`, `multimedia_service`, `produccion_service` | — | API + **MOBILE** | M01, M03, M05, M09, M04 |
| **M20** | Importación/legacy GELITE | No hay router: son migraciones SQL de datos y equivalencias | `backend/migrations/*` (042–057, 061–071, 087, 113…); no es un módulo de API | — | Solo datos (baseline) | Ver `PARIDAD-DATOS.md` §6 |

**Routers inclasificables o transversales:** `health_router` (3) → M00; `uploads_router` (1) → M02
(subida de marca); `chat_router` (2) → M18 (LLM genérico); `jarvis_operador_router` (2) → M18.

---

## 3. Grafo de dependencias (deducido del código y de los flujos)

```
M01 Identidad ──► M02 Config ──► M03 Pacientes ──► M04 Media
                        │               ├──► M05 Agenda ──► M06 Inicio/CRM
                        │               ├──► M07 Clínica ──► M08 Odontograma
                        │               │        └──► M09 Documentos
                        │               ├──► M10 Presupuestos ──► M11 Caja/Economía
                        │               └──► M19 Apps móviles
                        └──► M12 Comunicación ──► M13 Agentes IA ──► M14 IA dental/Ortodoncia
                                                      │
M11 + M12 ──► M15 Gestoría (fiscal; último del bloque económico)
M15 + M11 + M07 ──► M16 Informes
M01/M02 ──► M17 SuperUser/tenant
M04/M13/M14 ──► M18 Integraciones puente
M00 Plataforma acompaña a TODOS (jobs, SSE, backups, vigilancia)
```

Evidencia de las aristas principales:

- **Todo depende de M01**: 475 de las 498 operaciones exigen JWT (`PARIDAD-API.md` §4.5) y todas
  las de escritura exigen permiso (`auth_deps.py:64-79`).
- **M03 antes que todo lo clínico**: `_get_paciente` valida `paciente.centro_id == centro_id` en
  cada operación con paciente (`paciente_helper.py:9-13`), y las tablas clínicas/económicas llevan
  `paciente_id` FK (`_base.py:1-40`).
- **M04 antes que M14**: DentIA/radiología resuelven la imagen por `MultimediaService`
  (`dentia_router.py:104-125`; `multimedia_service.py:1-46`).
- **M05 antes que M07/M09**: actos, recetas y documentos referencian `cita_id`
  (`documentos.py:45-68`; `core.py:341-368`).
- **M10 antes que M11**: Caja aplica pagos a tratamientos/presupuestos aceptados
  (`caja_service.py:1-31`).
- **M11 antes que M15**: conciliación usa `pagos` y `movimientos_bancarios`
  (`conciliacion_service.py:1-30`).
- **M12 antes que M13**: el agente Alex responde desde el webhook de WhatsApp
  (`comunicacion_service.py:883-1000`).
- **M15 es fiscal**: VERI\*FACTU y `facturas_gestor` son datos con obligación AEAT
  (`domain/services/verifactu.py:1-20`; `PARIDAD-DATOS.md` §7.2).

## 4. Orden de reconstrucción propuesto (justificado)

### Fase 0 — Baseline y arnés de paridad (sin corte)
- Congelar/volcar el esquema y datos reales (`PARIDAD-DATOS.md` §10.2) y montar el staging de
  `INFRA.md`.
- Portar el arnés de tests: contract tests generados desde `PARIDAD-API.csv` + golden files +
  `pytest`/Playwright del legacy (`PARIDAD-PRUEBAS.md` §7).
- **Justificación:** sin baseline de datos y sin arnés no hay forma de decir «se comporta igual»;
  y el legacy seguirá vivo durante todo el corte, así que ambos entornos deben poder ejecutar la
  misma red. Es el único trabajo que no se puede paralelizar con nada.

### Fase 1 — M01 Identidad + M02 Config
- **Por qué primero:** 475/498 operaciones exigen JWT y permisos finos, y CONFIG es la fuente de
  la verdad (`config_service.py:1-56`). Si estos cimientos cambian después, todos los módulos
  ya cortados habría que re-verificarlos.
- **Corte:** login web/móvil, `/auth/me`, RBAC y CONFIG a la par. Se puede cortar el login antes
  que el resto de la web (es el punto de entrada).

### Fase 2 — M03 Pacientes + M04 Media
- **Por qué:** es el nodo central del dominio; sin pacientes no hay citas, actos, presupuestos ni
  documentos. Media antes de IA porque las imágenes son el insumo de M14.
- **Corte:** búsqueda/ficha/filiación y proxy de multimedia. Mantener `/media` autenticado y
  anti-IDOR (`PARIDAD-FLUJOS.md` F2).

### Fase 3 — M05 Agenda (+ M06 Inicio/CRM en paralelo)
- **Por qué:** la agenda es el segundo nodo-dios y la usan recepción, consulta, comunicación
  (confirmar/cancelar cita) y la app del doctor. Inicio/pulso solo lee y puede ir en paralelo una
  vez hay agenda y pacientes.
- **Corte:** `/agenda/*`, citas y huecos; el resto de webs puede seguir llamando al legacy.

### Fase 4 — M07 Clínica + M08 Odontograma + M09 Documentos
- **Por qué:** dependen de pacientes y citas. Van juntos porque la ficha del paciente los presenta
  en la misma pantalla y comparten PDFs/firma.
- **Riesgo específico:** el odontograma es PUT destructivo (`PARIDAD-FLUJOS.md` F9); exige test de
  contrato antes del corte.

### Fase 5 — M10 Presupuestos → M11 Caja/Economía
- **Por qué:** el presupuesto aceptado genera previstos, y la caja aplica pagos contra esos
  previstos/deudas (`caja_service.py:1-31`). Orden obligatorio para no dejar cobros huérfanos.
- **Corte:** presupuestos y después cobros. El flujo de dinero no se corta a medias.

### Fase 6 — M12 Comunicación/WhatsApp → M13 Agentes → M14 IA dental/Ortodoncia
- **Por qué:** la comunicación depende de pacientes/agenda; los agentes IA dependen de la
  comunicación; la IA de imagen depende de Media. El webhook de Evolution debe apuntar al backend
  nuevo solo cuando el módulo esté a la par (dedup y pausas probadas).
- **Riesgo:** el webhook es un punto externo que hay que redirigir; ventana de doble entrega.

### Fase 7 — M15 Gestoría / Gestor IA (bloque fiscal, al final)
- **Por qué:** es el único bloque con obligación legal AEAT (VERI\*FACTU) y arrastra Gmail/IMAP,
  banco, conciliación y modelos fiscales. Se corta **después** de economía y comunicación porque
  consume pagos, movimientos y proveedores. Además es el de mayor coste de error.
- **Corte:** primero lectura (facturas/gastos/movimientos), después escritura (conciliación,
  envío a asesoría) y por último el motor IA de facturación.

### Fase 8 — M16 Informes + M17 SuperUser/tenant + M18 Integraciones puente
- **Por qué:** Informes es lectura transversal (mejor cuando los datos están consolidados);
  SuperUser toca la BBDD de plataforma y provisiona centros (no bloquea el uso clínico);
  Romexis/Ollama/Jarvis son integraciones opcionales.
- **Riesgo:** SuperUser es la puerta de administración de la plataforma; cortarlo antes que el
  núcleo no aporta y añade riesgo de privilegios.

### Fase 9 — M19 Gateways móviles (cierre)
- **Por qué:** las apps ya instaladas no se actualizan al ritmo de la web; hay que cortar el
  gateway `/app/*` **al final**, con el resto estable, y mantener el host antiguo o plan de
  actualización forzosa (`PARIDAD-API.md` §9; `PARIDAD-FLUJOS.md` F11).
- **Corte:** cambiar la URL base de las apps es un corte de cliente, no de servidor: exigir
  versión mínima o mantener ambas APIs temporalmente.

### Transversal (todas las fases) — M00
El scheduler (automatización WhatsApp, ingesta, conciliación, detector RX, backups) es proceso
vivo con locks de Postgres (`infrastructure/scheduler.py:35-55`, `:359-410`): **se queda en
Oracle como contenedor de larga vida** (`INFRA.md`). No debe intentarse en Vercel.

### Paralelización posible
Tras la Fase 2 pueden ir en paralelo: (M05 Agenda) ∥ (M12 Comunicación) ∥ (M07 Clínica) si hay
equipo; (M16 Informes) puede desarrollarse en paralelo pero **no cortarse** hasta Fase 8.
M04 y M08 son pequeños y pueden colarse como sub-fases de M03/M07.

---

## 5. Mecánica del corte progresivo (crítico)

El corte es **por módulo y por ruta**, con un único punto de enrutado:

1. **El navegador sigue hablando solo con el dominio de Vercel** (`/api/*`) para conservar la
   cookie first-party (`PARIDAD-API.md` §3; `INFRA.md` §2.3). El router de módulos debe mapear
   prefijos de path → backend legacy o backend nuevo. Prefijos disjuntos por módulo:
   `/auth`, `/config*`, `/pacientes`, `/agenda`, `/comunicacion`, `/gestoria`, `/informes`,
   `/superuser`, `/app/*`…
2. **Un módulo se corta cuando su prefijo completo responde igual** (no se puede partir un router
   por la mitad sin un mapeo más fino; si se parte, hacerlo por operación con un mapa explícito y
   tests de contrato por operación).
3. **Móviles**: no pasan por Vercel. Apuntan a un host fijo (`mobile/doctor-ios/README.md:37-60`);
   el corte de M19 exige que el host nuevo sirva el contrato de `PARIDAD-API.md` §9 o mantener el
   host antiguo.
4. **SSE y `/media` no van por Vercel** (`INFRA.md` §3): el corte de M04/M12 incluye adaptar la URL
   (firmada / ticket) **sin cambiar el contrato de datos** que consume el frontend.
5. **Datos**: los dos backends no comparten cookie ni sesión entre dominios; durante el corte el
   legacy y el nuevo deben ver **la misma BD** (o replicación controlada) para no dividir el
   estado. Decisión pendiente del propietario — **NO VERIFICADO** qué opción se tomará.
6. **El webhook de WhatsApp/Evolution y el push de Gmail** son URLs externas: se redirigen al
   backend nuevo al cortar M12/M15, con ventana de idempotencia (dedup por `message_id`, §F5;
   `gmail_message_id`, §F6).

## 6. Criterios de aceptación del corte de un módulo

Tomados de `docs/DEFINITION-OF-DONE.md` (R3) y concretados para paridad:

- [ ] Todas las operaciones del módulo del inventario responden igual (URL, método, auth, permisos,
      códigos, forma) — `PARIDAD-API.md` §8 + checklist §10.3.
- [ ] Las tablas del módulo se leen/escriben con el mismo esquema y las mismas invariantes
      (`PARIDAD-DATOS.md` §8).
- [ ] Los flujos del módulo pasan sus verificaciones (`PARIDAD-FLUJOS.md`).
- [ ] Los tests existentes del módulo en `backend/tests` y los e2e aplicables están en verde
      (`PARIDAD-PRUEBAS.md`).
- [ ] `scripts/check.sh` en verde y `import OK` (`DEFINITION-OF-DONE.md:21-24`; `scripts/check.sh`).
- [ ] Sin PII en logs/informes; secretos fuera del repo (R4).
- [ ] Rollback probado: volver el prefijo al backend legacy sin migración de datos irreversible.

## 7. Riesgos del plan y lo no verificado

| # | Riesgo | Evidencia / motivo | Mitigación |
|---|---|---|---|
| 1 | **Cortar M19 (apps) sin actualizar apps** deja usuarios sin servicio | `mobile/doctor-ios/README.md:20-30`, §9 `PARIDAD-API.md` | Cortar al final; mantener host antiguo; versión mínima |
| 2 | **Cortar M15 (fiscal) con cualquier divergencia** tiene consecuencias legales | `domain/services/verifactu.py`; `PARIDAD-DATOS.md` §7.2 | Al final; golden files AEAT; validación con la asesora |
| 3 | **Doble scheduler** si ambos backends conviven | `infrastructure/scheduler.py:35-55` | Solo el host que tenga los jobs activos; lock de Postgres |
| 4 | **Dos verdades de huecos de agenda** si el frontend calcula y el backend también | `PARIDAD-FLUJOS.md` F8 | Mantener el cálculo de huecos en API |
| 5 | **SSE/multimedia no pasan por Vercel** y el contrato cambia (URL firmada/ticket) | `INFRA.md` §3, §5.2-5.3 | Adaptar en el corte de M04/M12 sin tocar el contrato de datos |
| 6 | **BD compartida vs dividida** durante el corte no decidida | §5.5 | Decisión explícita del propietario antes de la Fase 2 |
| 7 | **Orden real de arranque del legacy** (router include order) condiciona rutas | `backend/main.py:159-206`; duplicado en `PARIDAD-API.md` §2.4 | Preservar precedencia en el nuevo backend (o corregir el duplicado con aprobación) |
| 8 | **Cobertura de tests insuficiente** en 21 routers | `PARIDAD-PRUEBAS.md` §6 | Arnés de contract tests en Fase 0 |
| 9 | **Sin ejecución real** de la app en este entorno: cifras del plan son estáticas | `BASELINE.md:22-32`; todo el documento | Validar con el entorno preparado (venv macOS / staging Oracle) |

### Lo que este mapa NO afirma

- No afirma que los módulos del legacy estén bien separados: varios routers tienen lógica de
  negocio *inline* (p. ej. `pacientes_router.py:1221-1290`, `radiologia_router.py:190-235`), lo que
  hace que el "módulo" sea una unidad de corte, no de diseño ideal. Al reconstruir se puede (y se
  debe) mover esa lógica a `application/`, manteniendo el contrato observable.
- No afirma plazos ni esfuerzo: no hay estimaciones verificables en el repo.
- No sustituye a `INFRA.md` para la parte de despliegue.
