# PARIDAD-PRUEBAS — MakingSmiles_Studio

> **Qué es.** Inventario y mapeo de la red de seguridad existente del legacy (`master` @
> `a76ee81`): los tests de `backend/tests` y las suites Playwright de `frontend/e2e`, relacionados
> con los flujos de `PARIDAD-FLUJOS.md` y con las rutas de `PARIDAD-API.md`.
>
> **Para qué sirve.** Antes de cortar un módulo, el rebuild debe poder ejecutar un subconjunto de
> esta red contra el legacy y contra el módulo nuevo y comparar. Este documento dice **qué tests
> cubren qué** y, sobre todo, **qué NO está cubierto**.
>
> Sin PII ni secretos. Lo no ejecutable aquí se marca **NO VERIFICADO** (no hay `.venv` macOS ni
> navegadores Playwright instalados: `docs/rebuild/BASELINE.md:22-32`).

---

## 1. Cifras medidas (y contraste con «76 ficheros»)

| Medición | Valor | Evidencia |
|---|---:|---|
| Entradas en `backend/tests/` | **74** | `ls -1 backend/tests \| wc -l` |
| Ficheros `test_*.py` | **71** | `ls -1 backend/tests/test_*.py \| wc -l` |
| Otros ficheros de tests | 3 (`__init__.py`, `conftest.py`, `conftest_patch.py`) | `ls backend/tests` |
| Especificaciones Playwright E2E (`.spec.ts`) | **17** | `ls frontend/e2e/*.spec.ts \| wc -l` |
| Prueba visual Playwright (`.visual.ts`) | **1** (`agenda-cabeceras.visual.ts`) | `playwright.visual.config.ts` |
| Tests unitarios de frontend (`*.unit.ts`) | **2** | `find frontend/src -name "*.unit.ts"` |
| Ficheros de soporte E2E | `helpers.ts`, `fixtures/{constants,database,factories,global.teardown}.ts`, `rx-test.png`, `global.setup.ts`, `global.teardown.ts`, `RESULTADOS-UI(.md)` | `ls frontend/e2e` |

**Contraste con el enunciado («76 ficheros»):** el árbol de `a76ee81` tiene **74 entradas y 71
ficheros de test** en `backend/tests` (hay exactamente 3 ficheros no-`test_`: `__init__.py`,
`conftest.py`, `conftest_patch.py`). No he encontrado ninguna medición que dé 76 en el repo (ni en
`docs/` ni en `Pytest.ini`): la diferencia no se puede explicar con la evidencia disponible y la
trato como **NO VERIFICADA**. Es posible que la cifra contara `__pycache__`/`.pytest_cache` o
ficheros de otra rama; no se debe planificar con 76.

## 2. Cómo se ejecuta hoy (y por qué no se ha ejecutado aquí)

| Suite | Comando | Requisitos | Estado en este entorno |
|---|---|---|---|
| Backend | `cd backend && python -m pytest` | venv con `requirements.txt`, BD SQLite para la suite rápida (fixtures) | **NO EJECUTADO** (`.venv` Linux roto en macOS, `BASELINE.md:28`) |
| Backend integración | `python -m pytest -m integration` | servicios reales (BD/Postgres, Gmail/IMAP) | **NO EJECUTADO** (Docker parado) |
| E2E Playwright | `cd frontend && npm run test:e2e` | `node_modules`, navegadores (`npx playwright install`), `.env.e2e`, backend+Postgres reales, `npm run dev` | **NO EJECUTADO** (sin node_modules/navegadores) |
| Visual Playwright | `npm run test:visual` | app en marcha + `MS_EMAIL`/`MS_PASS` | **NO EJECUTADO** |
| Unit frontend | `npm run test:unit` (`src/**/*.unit.ts`) | node_modules | **NO EJECUTADO** |

Configuración relevante:

- `backend/pytest.ini`: `testpaths = tests`, `python_files = test_*.py`,
  `addopts = -v -m "not integration"`; marker `integration` = toca servicios reales y **no corre en
  la suite rápida** (`backend/pytest.ini:1-6`).
- `backend/tests/conftest.py:1-40`: fuerza `ENVIRONMENT=development`, claves **de test** (no
  secretos reales) y `DATABASE_URL=sqlite://`; crea todas las tablas con `SQLModel.metadata` y usa
  `TestClient(app)` sin lifespan; siembra `seed_dev`; fixture `token` hace `POST /auth/login` con
  el usuario admin de desarrollo. **La suite rápida corre sobre SQLite, no Postgres**: valida
  lógica, no fidelidad de SQL/constraints (importante para el rebuild).
- `frontend/playwright.config.ts:1-52`: `testDir=./e2e`, `baseURL=http://localhost:3000`,
  `webServer: npm run dev`, reporter HTML+JSON, `globalTeardown` purga pacientes `ZZ_E2E`
  (`e2e/global.teardown.ts:1-30`). **`globalSetup` está desactivado** (comentario
  `playwright.config.ts:42`) aunque el fichero `e2e/global.setup.ts` existe; por tanto los tests
  que asumen sesión de BD pueden no tenerla salvo que se reactive.
- `frontend/playwright.unit.config.ts:1-8` (`src/**/*.unit.ts`), `playwright.visual.config.ts:1-10`
  (`e2e/**/*.visual.ts`, `MS_BASE`, canal Chrome).
- `frontend/e2e/fixtures/constants.ts:1-40`: los valores reales se leen de `e2e/.env.e2e`
  (gitignored). **`e2e/.env.e2e.example` no existe en el árbol `a76ee81`** aunque el docstring lo
  referencia y `.gitignore:12` lo exceptúa: **NO VERIFICADO** cómo se rellena en un entorno nuevo.

---

## 3. Cobertura por flujo (resumen)

Recuento de ficheros de test backend que tocan cada flujo (un test puede tocar varios):

| Flujo | Nº tests backend | Tests E2E |
|---|---:|---|
| F1 Login/sesión | 11 | `paso-1-auth-real.spec.ts` |
| F2 Media/multimedia | 7 | `paso-9` (bloqueadores) |
| F3 SSE/tiempo real | 2 (indirectos) | — |
| F4 IA (DentIA/LLM/consulta/radiología) | 20 | `paso-7`, `paso-10` |
| F5 WhatsApp/comunicación/agentes | 19 | `paso-11` |
| F6 Gmail/intake/Gestor IA | 13 | `paso-12` |
| F7 Facturación/gestoría | 11 | `paso-12` |
| F8 Agenda | 7 | `paso-8`, `agenda-cabeceras.visual.ts` |
| F9 Odontograma/periodontograma | 2 | `paso-2`, `paso-15` |
| F10 Caja/cuenta económica | 6 | `paso-9`, `paso-15` |
| F11 Apps móviles | 4 (parcial) | — |
| F12 Scheduler/Centinela | 3 | — |

**Cobertura HTTP directa (medida conservadora):** buscando en los tests literales de ruta HTTP
(`client.get/post/...("/…")`), solo **63 de las 498 operaciones** (≈13 %) de la API aparecen
referenciadas directamente por su path literal. **22 de los 43 routers no tienen ninguna referencia
directa por path** en los tests
(nombres en §6). Muchos tests ejercitan **servicios de aplicación y dominio** directamente, no el
HTTP; y el E2E cubre más rutas que los tests backend. Conclusión honesta: **la paridad de API no
se puede acreditar solo con la suite existente**; hay que construir tests de contrato por módulo
(ver §7).

---

## 4. Inventario de `backend/tests` (71 ficheros)

Mapeo automático por nombre+docstring y extracción de los literales de ruta usados en cada fichero.
`Flujo(s)` referencia los códigos de `PARIDAD-FLUJOS.md`; «Otros» = test transversal sin flujo
asignado por nombre.

| # | Fichero | Qué cubre (docstring) | Flujo(s) | Rutas ejercitadas (muestra) |
|---:|---|---|---|---|
| 1 | `backend/tests/test_acceso_gmail.py` | Plan Gestión de Facturas · Punto 1 — Comprobación de acceso a Gmail y buzones. | F6 | — |
| 2 | `backend/tests/test_agenda_cross_tenant.py` | crear_cita / editar_cita (agenda) — regresión IDOR cross-tenant. | F8 | `/agenda/citas`, `/agenda/citas/{cita_id}`, `/auth/login`, `/auth/me` |
| 3 | `backend/tests/test_agente.py` | Test del loop del agente (capa B) con un LLM simulado — sin proveedor ni BBDD real. | F4, F5 | — |
| 4 | `backend/tests/test_agente_cableado.py` | — | F5 | — |
| 5 | `backend/tests/test_agente_permisos_canal.py` | — | F1, F5 | — |
| 6 | `backend/tests/test_agentes_contrato.py` | Contrato del área de IAs: los invariantes que NO pueden desaparecer sin avisar. | F5 | — |
| 7 | `backend/tests/test_agentes_cross_tenant.py` | agentes_router → POST /agentes/victor/consulta/escuchar — regresión IDOR cross-tenant. | F4, F5 | `/agentes/victor/consulta/escuchar`, `/auth/login`, `/auth/me` |
| 8 | `backend/tests/test_agentes_db_router.py` | — | F5 | `/agentes/db`, `/agentes/db/capacidades/catalogo`, `/agentes/db/migrar-base`, `/agentes/db/{agente_id}` |
| 9 | `backend/tests/test_agentes_limites_permisos.py` | Config → Agentes IA: LÍMITES editables y PERMISOS de la app que cortan de verdad. | F1, F5 | `/agentes/alex/config`, `/agentes/permisos/catalogo`, `/agentes/victor/config`, `/config?sistema=ia` |
| 10 | `backend/tests/test_agentes_modelo.py` | — | F5 | — |
| 11 | `backend/tests/test_alta_paciente_drive.py` | Alta de paciente → carpeta en Drive (num_historia + apellidos + nombre, con RX e Imágenes). | F2 | `/pacientes/nuevo` |
| 12 | `backend/tests/test_aura_v2.py` | Aura v2 (14-oct-2026): poder total tras PIN de SuperUser + vigilancia de Centinela. | F1, F12 | `/agentes/aura/centinela` |
| 13 | `backend/tests/test_auth_settings.py` | — | F1 | — |
| 14 | `backend/tests/test_caja_recepcion.py` | Caja de recepción (INICIO): cargar el acto realizado y cobrarlo, enlazando deuda↔pago. | F7, F10 | `/inicio/paciente/{ajeno.id}/caja`, `/inicio/paciente/{pa.id}/cobro`, `/inicio/paciente/{pac.id}/caja`, `/inicio/paciente/{pac.id}/cobro` |
| 15 | `backend/tests/test_capacidades_service.py` | — | F5 | — |
| 16 | `backend/tests/test_centinela.py` | Centinela/Victor — piezas nuevas verificables sin Postgres real (SQLite de test): | F1, F12 | `/auth/login`, `/login` |
| 17 | `backend/tests/test_cita_id_cita.py` | id_cita y sellos de la cita — regla de identidad (jmd, 12-oct-2026). | F8 | — |
| 18 | `backend/tests/test_cita_reglas.py` | Reglas de cita (application/services/cita_reglas.py): obligatorios, campos desconocidos, | F8 | `/agenda/citas` |
| 19 | `backend/tests/test_clasificador_no_factura.py` | Clasificación a nivel de correo (buckets B/C del backlog). | F6 | — |
| 20 | `backend/tests/test_comunicacion_media_dir.py` | ComunicacionService comprueba que el directorio de media WhatsApp admite escritura al | F2, F4, F5 | — |
| 21 | `backend/tests/test_conciliacion.py` | Tests del motor de conciliación banco↔factura y de las plantillas PDF. | F6, F7 | — |
| 22 | `backend/tests/test_consentimientos.py` | Consentimientos: enlace público de firma (signing_code) — auditoría de seguridad. | F2 | `/consentimientos/firma-profesional?colaborador_id={col.id}`, `/consentimientos/firmar/{c.signing_code}`, `/consentimientos/firmar/{c.signing_code}/pdf`, `/consentimientos/requerido?cita_id={cita.id}` |
| 23 | `backend/tests/test_consulta_cross_tenant.py` | guardar_soap / guardar_receta — regresión IDOR cross-tenant. | F4 | `/auth/login`, `/auth/me`, `/pacientes/999999/consulta/receta`, `/pacientes/999999/consulta/soap` |
| 24 | `backend/tests/test_cuenta_economica.py` | Cuenta económica del paciente: pago a un tratamiento, a un presupuesto aceptado o a cuenta. | F7, F10 | `/auth/me`, `/inicio/paciente/{pac.id}/cobro`, `/pacientes/{pac.id}/actos`, `/pacientes/{pac.id}/consulta/cerrar` |
| 25 | `backend/tests/test_dentia.py` | DentIA: persistencia del análisis por imagen, validación, aislamiento por centro y mapeo de la IA. | F4 | `/pacientes/{ajeno.id}/dentia`, `/pacientes/{otro.id}/dentia`, `/pacientes/{p.id}/dentia`, `/pacientes/{p.id}/dentia/detectar` |
| 26 | `backend/tests/test_disponibilidad.py` | Tests del motor de huecos (dominio puro). | F8 | — |
| 27 | `backend/tests/test_escucha_determinista.py` | Escucha activa: lo que llega al paciente y al doctor no depende de lo que alucine el LLM | F4 | — |
| 28 | `backend/tests/test_extract_qwen35.py` | Lectura de facturas con qwen3.5 (21-sep→22-oct-2026 no entró ninguna por correo). | F4, F6 | — |
| 29 | `backend/tests/test_f0.py` | Tests F0 — Genoma: CENTINELA (auth/RBAC) + CEREBRO (config jerárquica). | F1, F12 | `/auth/forgot`, `/auth/login`, `/auth/login-cookie`, `/auth/me` |
| 30 | `backend/tests/test_factura_1515_consenur.py` | Regresión de la factura real más difícil del backlog: id=1515, SRCL Consenur, con SUPLIDO. | F6 | — |
| 31 | `backend/tests/test_factura_archivo_anio.py` | Archivado de facturas en CLINICA/FACTURAS/<año> (oct-2026: las carpetas fijas estaban borradas). | F6 | `/media/facturas/` |
| 32 | `backend/tests/test_fdi.py` | — | F4, F9 | — |
| 33 | `backend/tests/test_ficha_layout_config.py` | Confirma que la clave ficha_layout (feature: cajas movibles de la ficha de paciente) | F7, F9, F10 | `/auth/login`, `/config` |
| 34 | `backend/tests/test_gasto_ia.py` | Tests unitarios para el Modelo IA Multimodal (Gestor IA). | F6, F7 | — |
| 35 | `backend/tests/test_gastos_export_service.py` | Cobertura de gastos_export_service: export a Excel de gastos (vista de apoyo para la asesoría). | F7 | — |
| 36 | `backend/tests/test_gestor_agente.py` | Gestor IA (chat de Gestoría): una sola herramienta, de solo lectura, sobre el informe contable. | F5, F6 | — |
| 37 | `backend/tests/test_gestor_facturas_reales.py` | Las facturas REALES ya verificadas contra el papel, una a una. | F6 | — |
| 38 | `backend/tests/test_gestoria_contrato.py` | Contrato de GESTORÍA: los invariantes que costaron horas de trabajo y no pueden | F4, F6, F7 | — |
| 39 | `backend/tests/test_gmail_ai_processor.py` | `GmailAIProcessor._llamar_ia_multimodal` usa `LLMClient` (infraestructura) con su | F4, F6 | — |
| 40 | `backend/tests/test_health.py` | Tests de humo de la API. | F1 (salud del servicio) | `/health` |
| 41 | `backend/tests/test_ia_dental_client.py` | Cliente ia-dental: error controlado si no hay servicio (la ficha nunca se rompe) y paso correcto de la imagen. | F1, F4 | — |
| 42 | `backend/tests/test_imagen_para_ollama.py` | Ollama solo carga JPEG/PNG: el resto de imágenes del correo se convierte o se omite. | F4 | — |
| 43 | `backend/tests/test_importar_romexis.py` | Endpoint /radiologia/importar-romexis-interno: recibe imágenes del bridge de Romexis. | F4 | `/radiologia/importar-romexis-interno` |
| 44 | `backend/tests/test_inicio_paciente.py` | INICIO · el paciente de agenda: citas, automatizaciones y flujo de WhatsApp en una llamada. | F5, F8 | `/comunicacion/conversaciones/{conv.id}/flujo/cortar`, `/inicio/conversacion?telefono=655000111`, `/inicio/paciente/999999`, `/inicio/paciente/{pac.id}` |
| 45 | `backend/tests/test_intake_service.py` | Cobertura del orquestador IntakeService sobre SQLite (red/Drive mockeados). | F2, F6 | — |
| 46 | `backend/tests/test_llm_cascada.py` | PLAN B en la raíz LLMClient: si el motor local cae, la MISMA llamada baja por los | F4 | — |
| 47 | `backend/tests/test_llm_client_reasoning.py` | LLMClient: `reasoning_effort` de la conexión (Config) viaja al proveedor; sin él no se envía. | F4 | — |
| 48 | `backend/tests/test_llm_relay.py` | PLAN B de los operadores de OpenJarvis: el relé Ollama del backend. | F4 | `/ollama/otro-token/api/chat`, `/ollama/otro-token/api/tags`, `/ollama/{TOKEN}/api/chat`, `/ollama/{TOKEN}/api/tags` |
| 49 | `backend/tests/test_migrar_agentes_reales.py` | — | F5 | — |
| 50 | `backend/tests/test_multimedia_security.py` | Regresión de seguridad de multimedia_service (fase SERVICES, prioridad WRITE>READ). | F2, F4, F11 | — |
| 51 | `backend/tests/test_paciente_auth_telefono_compartido.py` | Login paciente con teléfono compartido: el nombre se exige ANTES de enviar. | F1, F11 | `/app/auth/solicitar-codigo` |
| 52 | `backend/tests/test_personalidad_service.py` | — | F5 | — |
| 53 | `backend/tests/test_pipeline_2etapas_mock.py` | Pipeline 2-etapas end-to-end con httpx mockeado (sin red, sin claves reales). | F4 | — |
| 54 | `backend/tests/test_polls_media.py` | Tests de polls y media del webhook (sin BBDD ni Evolution reales). | F2, F3 | — |
| 55 | `backend/tests/test_portal_browser.py` | Tests de `leer_portal` (lectura de portales de proveedor con navegador real). | F6 | — |
| 56 | `backend/tests/test_presupuesto_cross_patient.py` | crear_acto (clinico_router) → aceptar_entero/volcar_a_previstos — regresión IDOR | F7 | `/auth/me`, `/pacientes/{pac_a.id}/actos` |
| 57 | `backend/tests/test_pulso_citas_hoy.py` | INICIO · citas del día (Cover Flow): cada campo sale de SU columna y los filtros acotan. | F3, F8 | `/inicio/citas` |
| 58 | `backend/tests/test_rescate_y_caja_23oct.py` | Correcciones del 23-oct-2026. | F4, F7, F10 | — |
| 59 | `backend/tests/test_revision_agente_link.py` | — | F5 | — |
| 60 | `backend/tests/test_roles_permisos.py` | Roles y permisos: efectivos = (rol − límites por persona) ∪ directos; edición de roles. | F1 | `/auth/login`, `/configuracion/personal`, `/configuracion/personal/{p['id']}`, `/configuracion/roles` |
| 61 | `backend/tests/test_secretos_integracion.py` | Secretos de integración: enmascarado y fusión a cualquier profundidad. | F1 (config/integraciones) | — |
| 62 | `backend/tests/test_security_surface.py` | — | F2 | `/apps/pacientes/1/ficha`, `/uploads` |
| 63 | `backend/tests/test_seed_capacidades.py` | — | F5 | — |
| 64 | `backend/tests/test_selectores_doctores.py` | Selectores de doctor de Agenda y Config › Agenda: solo personal ACTIVO y de ESTE centro. | F8 | `/agenda/referencias`, `/configuracion/agenda` |
| 65 | `backend/tests/test_soap_urgencia.py` | guardar_soap — regla nueva de urgencia automática (jmd, 12-oct-2026). | F4 | — |
| 66 | `backend/tests/test_tratamiento_fracasado.py` | Tratamiento fracasado: abono en negativo + crédito a favor (CajaService, un solo dueño). | F7, F10 | `/pacientes/{otro.id}/actos/{a.id}/marcar-fracasado`, `/pacientes/{p.id}/actos/{a.id}/marcar-fracasado` |
| 67 | `backend/tests/test_un_solo_dueno.py` | Una entidad se escribe desde un solo sitio. Si no, este test falla. | F10 | — |
| 68 | `backend/tests/test_verifactu.py` | VERI*FACTU — la huella se comprueba contra los EJEMPLOS OFICIALES de la AEAT. | F7 | `/ValidarQRNoVerifactu?` |
| 69 | `backend/tests/test_voicebot.py` | Tests del canal de voz: el agente en modo voz no envía por WhatsApp y devuelve | F5 | — |
| 70 | `backend/tests/test_whatsapp_flujos.py` | Tests de la máquina de estados de WhatsApp (dominio puro, sin BBDD). | F5, F11 | — |
| 71 | `backend/tests/test_whatsapp_hora_real.py` | Hora real de los mensajes de WhatsApp entrantes (29-oct-2026). | F5, F11 | — |
---

## 5. Suite E2E de `frontend/e2e` (17 specs + 1 visual + soporte)

Los specs están escritos como **pasos numerados** de un plan de pruebas real (login, pacientes,
actos, clínica, presupuestos, consulta, agenda, bloqueadores, radiología, comunicación, gestoría,
configuración, informes, integración completa). **Falta el `paso-4`**: no existe
`paso-4-*.spec.ts` en el árbol — hueco de la serie.

| Fichero | Qué cubre | Rutas principales | Flujo |
|---|---|---|---|
| `e2e/paso-1-auth-real.spec.ts` | Login real: formulario, redirección sin sesión, cookie httpOnly, credenciales malas, ficha, logout | `/login`, `/auth/login-cookie`, `/auth/me`, `/auth/logout` | F1 |
| `e2e/paso-2-pacientes-crud-real.spec.ts` | Paciente: GET real, 404, búsqueda por apellido/num_historia, filiación, ficha | `/pacientes/{id}`, `/pacientes/buscar`, `/pacientes/{id}/filiacion`, `/pacientes/{id}/ficha` | F2/F9 |
| `e2e/paso-3-actos-clinicos-real.spec.ts` | Actos clínicos: 422 sin colaborador/fecha, POST/PUT/DELETE | `/pacientes/{id}/actos` | F7/F9 |
| `e2e/paso-5-clinico-real.spec.ts` | Historia clínica: recetas, previstos, alertas (CRUD + 422) | `/pacientes/{id}/recetas`, `/previstos`, `/alertas` | F9 |
| `e2e/paso-6-presupuestos-backend-real.spec.ts` | Presupuestos: crear con líneas, editar, entregar, aceptar sin líneas → 400 | `/pacientes/{id}/presupuestos…` | F7/F10 |
| `e2e/paso-7-consulta-real.spec.ts` | Consulta viva: camino, escucha (SOAP), 422 sin texto, SOAP no duplica, analizar | `/pacientes/{id}/consulta/*` | F4 |
| `e2e/paso-8-agenda-real.spec.ts` | Agenda: referencias, huecos, crear cita, 422 sin fecha/hora, filtro, mover | `/agenda/*` | F8 |
| `e2e/paso-9-bloqueadores-serial.spec.ts` | Bloqueadores críticos (`mode: serial`): alta de paciente en BD, etc. | `/pacientes/nuevo` y otros | F2/F10 |
| `e2e/paso-10-radiologia-real.spec.ts` | Radiología: lista vacía, subir imagen, modalidades, hallazgos, 422 sin descripción, borrar hallazgo | `/pacientes/{id}/radiologia`, `/radiologia/*` | F4 |
| `e2e/paso-11-comunicacion-real.spec.ts` | Comunicación: conversaciones, estadísticas, mensajes, plantillas CRUD + 422 | `/comunicacion/*` | F5 |
| `e2e/paso-12-gestoria-real.spec.ts` | Gestoría: facturas, búsqueda, gastos CRUD + 422, movimientos | `/gestoria/*` | F6/F7 |
| `e2e/paso-13-configuracion-real.spec.ts` | Config: GET/PUT `/config` + 422, centro, agenda, colaboradores | `/config`, `/configuracion/*` | F1/F12 |
| `e2e/paso-14-informes-real.spec.ts` | Informes: entidades, tablas, campos, ejecutar, filtros, pivote | `/informes/*` | F7 |
| `e2e/paso-15-integracion-e2e-real.spec.ts` | Flujo completo: alta → cita → RX+hallazgo → consulta → presupuesto → previsto | cadena de varios módulos | F2/F8/F9/F10 |
| `e2e/paso-X-ficha-layout-movible.spec.ts` | Ficha de paciente: cajas movibles/redimensionables con backend+Postgres reales | `/config` (`ficha_layout`), ficha | F9 |
| `e2e/capturas.spec.ts` | Captura de pantalla de toda la web navegable (inventario visual, no aserción funcional) | navegación global | transversal |
| `e2e/prueba_ui.spec.ts` | Prueba funcional de UI con captura antes/después por elemento (por partes `PARTE=A|B|C…`) | navegación global | transversal |
| `e2e/agenda-cabeceras.visual.ts` | Visual estricto: alineación de la línea inferior de «Citas del día» con la cabecera azul (1×/2×, clásico y 3D) | `/agenda` | F8 |
| `e2e/helpers.ts` | `loginAsDoctor`, `navigateToPatient`, `searchAndOpenPatient`, `abrirConsulta`, `waitForModal` | — | soporte |
| `e2e/fixtures/constants.ts`, `database.ts`, `factories.ts` | Datos E2E desde `.env.e2e`; pool `pg`; paciente NUEVO por test y purga; **cero datos aleatorios/faker** | — | soporte |
| `e2e/global.setup.ts` | Crea/asegura usuario de test contra la BD (bcrypt `crypt`/`gen_salt`) | — | soporte |
| `e2e/global.teardown.ts` | Purga `ZZ_E2E` huérfanos, documentos y misc | — | soporte |
| `e2e/RESULTADOS-UI.md` + `RESULTADOS-UI/` | Resultados y capturas de la prueba UI | — | evidencia |

**Regla de datos de la suite E2E** (`e2e/fixtures/constants.ts:9-15`): lecturas/navegación contra el
paciente real configurado; crear/editar/borrar **solo** con paciente nuevo vía
`POST /pacientes/nuevo`, registrado y borrado al final. **Nunca se modifica ni se borra el paciente
real.** No hay faker ni datos aleatorios.

**Tests unitarios frontend** (2): `frontend/src/features/patients/components/fichaLayoutDefault.unit.ts`
y `frontend/src/features/patients/components/ficha/fichaDatos.unit.ts` (lógica de layout/datos de la
ficha, sin navegador).

---

## 6. Qué NO está cubierto (huecos a cerrar en el rebuild)

Routers sin ninguna referencia directa por path en `backend/tests` (**22 de 43**):
`app_doctor_router`, `app_paciente_router`, `casos_ortodoncia_router`, `cefalometria_router`,
`chat_router`, `configuracion_admin_router`, `configuracion_centro_router`, `crm_router`,
`documentos_router`, `geo_router`, `gestor_ia_router`, `gestoria_router`, `informes_router`,
`internal_tenant_router`, `jarvis_operador_router`, `llm_router`, `media_router`, `motion_router`,
`ollama_relay_router`, `superuser_router`, `voicebot_router`, `ws_router`.

Huecos concretos por flujo:

| Hueco | Riesgo | Cómo cubrirlo |
|---|---|---|
| **SSE** (`/comunicacion/stream`, `/app/*/stream`, `/ws/gestoria`) sin test | F3 roto silenciosamente | Test de integración con `TestClient.stream` + publicar en el bus; e2e de dos pestañas |
| **`/media/{ruta}` auth directa** sin test | fuga de PII (F2) | Test HTTP: 401 sin sesión; 404 para `media/pacientes/**`; 404 traversal |
| **Endpoint de odontograma/periodontograma** sin test | pérdida de hallazgos por PUT destructivo (F9) | Test de contrato PUT→GET y PUT con lista vacía |
| **Apps móviles** sin e2e y sin compilar (`mobile/*/README.md`) | contrato roto para apps instaladas (F11) | Contract tests de los 22 endpoints de `PARIDAD-API.md` §9 |
| **Informes** (motor SQL) sin test backend | inyección/scoping multi-tenant | Tests de allowlist y scoping por centro |
| **Superuser / internal tenant** sin test | escalada cross-tenant | Tests de auth por `X-Internal-Key` y de aislamiento |
| **Scheduler con lock** sin test | duplicación de jobs (F12) | Test de que solo un proceso adquiere el advisory lock |
| **`gestoria_router`** (86 endpoints) sin test HTTP directo | regresiones fiscales | Contract tests + e2e ya existente (`paso-12`) como base |
| **Playwright sin `globalSetup`** activo | tests dependientes de sesión pueden fallar | Reactivar `globalSetup` y documentar `.env.e2e` |
| **Suite rápida en SQLite** | no valida FKs/constraints/vistas Postgres | Matriz de tests de integración contra Postgres antes del corte |

---

## 7. Plan de verificación de paridad por módulo (para el rebuild)

Para cada módulo que se corte, ejecutar **en paralelo legacy vs nuevo** y comparar:

1. **Contract tests derivados de `PARIDAD-API.csv`**: para cada operación del módulo, mismo método,
   path, código de éxito y de error, forma de respuesta y puerta de auth/permiso. Base: tabla §8 de
   `PARIDAD-API.md` (498 operaciones).
2. **Golden files de respuesta** (sin PII: usar datos sintéticos o el paciente de test E2E) para
   GETs de ficha, agenda, odontograma, presupuestos, facturación.
3. **Tests de flujo existentes**: reutilizar tal cual los ficheros de §4 que mapean al módulo,
   apuntándolos al nuevo backend (los tests usan `TestClient`/`API_BASE`).
4. **E2E Playwright** de §5 con el nuevo backend detrás del proxy: deben pasar los pasos del 1 al 15
   (y añadir el hueco del paso-4 o justificar su ausencia).
5. **Criterio de corte**: ningún endpoint del módulo sin, al menos, un contract test; los flujos del
   módulo con e2e en verde; y paridad numérica de los golden files.
