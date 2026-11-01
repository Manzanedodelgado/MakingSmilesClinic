# PARIDAD-DATOS — MakingSmiles_Studio

> **Qué es.** El modelo de datos persistente del legacy (`master` @ `a76ee81`) que el rebuild
> por módulos con corte progresivo debe preservar: tablas, columnas relevantes, claves foráneas,
> migraciones, invariantes y qué es dato clínico (RGPD) frente a qué es dato fiscal.
> Es un contrato de datos, no un diseño ideal.
>
> **Método:** extracción **estática** del código (`ast`) + lectura de las 126 migraciones SQL. No
> se ha podido importar SQLModel ni conectar a PostgreSQL en este entorno (`.venv` Linux roto en
> macOS; daemon Docker parado — `docs/rebuild/BASELINE.md`), por lo que **el esquema real de
> producción no se ha volcado**: lo que aquí aparece es lo que **declara el código**. Las
> diferencias código↔BD real son un riesgo explícito (§9).
>
> **Reglas:** cada afirmación con evidencia `ruta:línea`; lo no verificable se marca
> **NO VERIFICADO**; sin PII de pacientes ni valores de secretos.

---

## 1. Método de extracción y cifras

| Medición | Valor | Cómo se obtuvo |
|---|---:|---|
| Tablas declaradas con SQLModel (`table=True`) | **142** | AST sobre `backend/domain/models/*.py` |
| Columnas declaradas (suma, incluyendo mixtos heredados) | **1.359** | AST (herencia de `*Base` + mixins) |
| Claves foráneas declaradas (`foreign_key=`) | **291** | AST |
| Tablas con al menos una FK | **128** | AST |
| Tablas sin FK declarada | **14** | ver §3.3 |
| Tablas con `centro_id` (multi-tenant) vía `TenantMixin` | **74** | AST de la herencia |
| Ficheros de migración SQL | **126** | `ls backend/migrations/*.sql` |
| Migraciones que tocan esquema | **86** | clasificación §6 |
| Migraciones de solo datos | **40** | clasificación §6 |
| Vistas SQL | **3** (`informe_contable`, `informe_gastos`, `informe_juan_antonio`) | migraciones `099`, `100`, `101`/`103` |

Script reproducible del inventario de rutas: `docs/rebuild/verificar_rutas.py`. Para datos, el
método está descrito en §10 y se replica con el SQL de §10.2 contra la BD real.

**Límite importante:** las migraciones SQL **no** están reflejadas una a una en los modelos
SQLModel. El esquema de producción es la unión de `create_all` + 126 migraciones aplicadas a mano
(§2). Por tanto, **un modelo no es prueba de la columna real** y viceversa.

---

## 2. Cómo se crea y evoluciona el esquema (crítico para el rebuild)

### 2.1 No hay Alembic

| Hecho | Evidencia |
|---|---|
| El esquema base se crea con `SQLModel.metadata.create_all(engine)` al arrancar | `backend/infrastructure/config/db.py:13-21` (`init_db`), invocado en `backend/main.py:82` |
| Los modelos deben importarse antes para registrarse en el metadata | `backend/domain/models/__init__.py` (registro) y `db.py:16-18` |
| La evolución se aplica con **ficheros SQL manuales** y se anota en `migraciones_aplicadas` | `scripts/migra.sh:1-63` (bloquea repetición, exige copia previa verificada y anota) |
| El cuaderno de migraciones se creó el 18-oct-2026 tras un incidente real de columnas sin aplicar | `backend/migrations/093_registro_migraciones.sql` y comentario en `scripts/migra.sh:50-53` |
| Existe un verificador de estado de migraciones que pregunta al `information_schema` real | `scripts/migraciones_estado.py:1-40` |
| `create_all` **no altera** tablas existentes: no aplica cambios de columna | comportamiento estándar de SQLAlchemy; evidencia del diseño en `db.py:13-21` |

**Consecuencia para el rebuild:** en Oracle Cloud/Postgres nuevo, `create_all` crea el esquema
*actual de los modelos* pero **no reproduce** los 126 ficheros (índices, constraints, backfills,
vistas, defaults y semillas). El rebuild necesita un **baseline de esquema volcado de producción**
(pg_dump --schema-only) y decidir explícitamente qué migraciones de datos se conservan. Sin eso,
la paridad de datos es imposible.

### 2.2 Dos bases de datos

| Base | Contenido | Evidencia |
|---|---|---|
| Operativa (`DATABASE_URL`) | pacientes, citas, personal, clínica, economía de cada centro | `backend/domain/config/settings.py:11, :64`, `db.py:8` |
| Plataforma (`PLATFORM_DATABASE_URL` o misma instancia/BD distinta) | registro de centros para SuperUser; **sin metadata ORM compartida** | `backend/infrastructure/config/platform_db.py:1-47` |

En SQLite (tests) ambas comparten URL (`platform_db.py:15-20`). El acceso de SuperUser a datos
operativos **solo** pasa por el router interno (`internal_tenant_router.py`), nunca por queries
directas (documentado en `backend/domain/config/settings.py:63-66` y `superuser_router.py:1-5`).

---

## 3. Modelo relacional: nodos-dios, FK e invariantes

### 3.1 Los cinco nodos-dios

`backend/domain/models/core.py:1-16` declara el diseño: **centro · paciente · colaborador · cita ·
tratamiento**, y «toda otra entidad referencia a uno o varios de ellos con FK explícita».

```
centro ──< colaborador (N:M vía colaborador_centro)
centro ──< paciente
centro ──< razon_social (facturación)
paciente ──< cita >── colaborador ── centro
cita ──< cita_tratamiento >── tratamiento
```

### 3.2 Invariantes del modelo (reglas de oro)

Evidencia: `backend/domain/models/_base.py:1-40`.

1. **Multi-tenant**: todo lo operativo lleva `centro_id` FK NOT NULL a `centros.id`
   (`TenantMixin`, `_base.py:30-40`). 74 tablas lo heredan.
2. **Todo lo clínico/económico de un paciente** lleva `paciente_id` FK a `pacientes`.
3. **Cero huérfanos**: las FK deben existir con `ondelete` explícito; RESTRICT por defecto,
   CASCADE solo en hijos puros (`_base.py:11`). **NO VERIFICADO** cuáles tienen `ondelete` en la
   BD real: los modelos **no** lo declaran con `ondelete=` en ningún campo (grep: 0 resultados en
   `backend/domain/models/`), así que el `ondelete` real viene de las migraciones/manual. Es una
   discrepancia modelo↔BD a resolver en el rebuild.
4. **Auditoría mínima**: toda tabla tiene `created_at`/`updated_at`
   (`TimestampMixin`, `_base.py:24-27`), con `utcnow()` de `datetime.now(timezone.utc)`
   (`_base.py:20-21`).
5. **Acceso resuelto por `user_center_roles`**, nunca por un campo `role` plano
   (`backend/application/services/auth_service.py:1-6`).

### 3.3 Tablas sin FK declarada (14) y por qué

`analisis_cefalo`, `capacidades_catalogo`, `diagnosticos`, `estados_presupuesto`,
`estados_tratamiento`, `formas_pago`, `paises`, `permisos`, `platform_users`, `poblaciones`,
`sistemas`, `tipos_antecedente`, `usuarios`, `vademecum`.

- Catálogos globales o casi-globales (`paises`, `poblaciones`, `formas_pago`, `permisos`,
  `sistemas`, `tipos_antecedente`, `vademecum`, `diagnosticos`, `capacidades_catalogo`,
  `estados_presupuesto`, `estados_tratamiento`): su relación con el centro es por columna
  (`centro_id`/`agenda_id`) o por catálogo compartido, no por FK. **Verificar en BD real**.
- `usuarios`: identidad **global** (un usuario puede trabajar en varios centros). La pertenencia
  va por `user_center_roles` y `usuario_periodos` (identidad.py:35-71, :104-113).
- `platform_users`: vive en la BBDD de plataforma (`platform_db.py`).
- `analisis_cefalo`: lleva `imagen_id`/`paciente_id` como enteros sin `foreign_key=` declarado
  (`clinico.py:164-175`) — **deuda de integridad referencial**, no asumir CASCADE.

### 3.4 Entidades de identidad y RBAC (importantes para el corte)

| Tabla | Rol en el contrato | Evidencia |
|---|---|---|
| `usuarios` | identidad global (email, `password_hash`, nombre, color) | `backend/domain/models/identidad.py:35-55` |
| `usuario_periodos` | periodos laborales (alta/baja) por usuario; determina si un login está activo | `identidad.py:57-75`; `auth_service.py:56-65` |
| `roles`, `permisos`, `role_permisos` | techo de permisos por rol | `identidad.py:77-102` |
| `user_center_roles` | acceso (usuario × centro × rol): base del JWT y de `X-Centro-Id` | `identidad.py:104-113` |
| `user_center_permisos` | concesiones directas por persona | `identidad.py:115-123` |
| `user_center_permisos_denegados` | límites por persona sobre el rol | `identidad.py:125-133` |
| `platform_users` | usuarios de plataforma (SuperUser) | `identidad.py:23-33` |

La semilla de permisos está en 3 migraciones de datos: `096_permisos_denegados_por_rol.sql`,
`097_permisos_por_pestana.sql`, `098_permisos_por_seccion.sql` (§6). **Los códigos de permiso son
contrato de API** (ver `PARIDAD-API.md` §4.4).

---

## 4. Columnas relevantes de las tablas críticas

> Solo las columnas con significado de contrato, invariantes o riesgo. El resto, ver §5.
> Los tipos son los **declarados en SQLModel**; el tipo real en Postgres puede diferir
> (`NUMERIC`, `timestamp with time zone`, etc.) — verificar con §10.2.

### 4.1 `pacientes` (`backend/domain/models/core.py:163-183`)

- Clave pública: `num_historia` («NumPac», `core.py:166`) — **se genera por centro** y es la
  carpeta de multimedia en disco (`multimedia_service.py:8-13`, `:74-85`). No puede cambiar de
  formato ni de unicidad.
- FK: `centro_id → centros.id`, `cliente_id → clientes.id`, `agenda_id → agendas.id`,
  `tutor_id → pacientes.id` (self-FK para tutor legal).
- PII: `nombre`, `apellidos`, `nif`, `fecha_nacimiento`, `direccion`, `cp`, `poblacion_id`,
  `telefono_fijo*`, `telefono_movil`, `email`, `foto_url`, `grupo_sanguineo`, `peso`, `altura`,
  `medico_cabecera`, `tel_medico`, `especialista`.
- Clínico: `anamnesis` (JSON `Any`), `alergias` (tabla hija `alergias`), `datos_extra` (JSON).
- Consentimientos/registro: `acepta_lopd`, `acepta_info`, `acepta_whatsapp`, `acepta_bots`,
  `fecha_alta`, `fecha_baja`, `motivo_inactivo`, `activo`.
- Legado app paciente: `app_usuario`, `app_password_hash`, `app_email_registro`,
  `app_fecha_registro/modificacion`, `app_version`, `app_fecha_instalacion` (el login nuevo de
  paciente va por OTP y tabla `paciente_otps`; estos campos son legado — **verificar uso**).
- Trazabilidad: `updated_by → usuarios.id` y los `campo_libre_*`/`notas`.

### 4.2 `citas` (`core.py:341-368`)

- `id_cita` (número visible de cita, migrada en `039_cita_id_cita_fechas.sql`), `fecha`, `hora`,
  `duracion_min`, `fecha_hora_estado`, `fecha_hora_creacion/modificacion`.
- FK: `centro_id`, `agenda_id`, `estado_id → estados_cita`, `paciente_id`, `tutor_id`,
  `colaborador_id`, `usuario_id`, `gabinete_id`, `tipo_cita_id`, `tarifa_id`.
- Snapshot del paciente en la cita: `num_historia`, `nombre`, `apellidos`, `telefono_movil`,
  `nif`, `email`, `fecha_nacimiento` (la agenda puede crear citas sin ficha).
- Estado/tiempos: `gratuita`, `hora_llegada`, `retraso_min`, `hora_ini_real`, `hora_fin_real`,
  `recordada`, `confirmada`, `envio_doc`, `firmado`, `aceptada`, `anulacion_gestionada`.
- Regla de negocio (validada en `application/services/cita_reglas.py:1-20`): obligatorios fecha,
  hora, duración, tipo, nombre, apellidos, teléfono y gabinete; catálogos del centro; sin festivo
  ni bloqueo; gabinete↔doctor desde `colaborador_horarios`; duración por doctor+tipo.

### 4.3 `colaboradores` (`core.py:244-257`)

- `periodo_id → usuario_periodos.id` (único), `talonario_id → talonarios.id`.
- `num_colegiado`, `firma_url`, `contrato_inicio/fin`, `factura_produccion`, `pct_produccion`,
  `aplica_laboratorio`, `tpc_gastos`, `aplica_irpf`, `irpf_pct`, `ausencia_inicio/fin`, `activo`,
  `precio_tratamiento_exento`.
- **No tiene `centro_id`**: la pertenencia a centros va por `colaborador_centro` (N:M). Es la
  corrección documentada de C5 (`docs/AUDITORIA-CODIGO.md:114` y migración `020`).

### 4.4 `tratamientos_realizados` (`backend/domain/models/economico.py:297-338`) — 35 columnas

- FK: `centro_id`, `paciente_id`, `cliente_id`, `tratamiento_id`, `tarifa_precio_id`,
  `presupuesto_linea_id`, `colaborador_id`, `colaborador_aux_id`, `estado_id →
  estados_tratamiento`, `factura_documento_id → documentos_admin`.
- Identidad/origen: `num_tto`, `origen`, `origen_id_gelite`, `origen_fecha`.
- Clínico: `piezas`, `zona_boca`, `fecha_inicio`, `fecha_fin`, `actos`, `tiempo_min`.
- Económico: `importe`, `descuento`, `descuento_aplica_doctor`, `coste_laboratorio`,
  `importe_descuento`, `importe_privado`, `importe_mutua`, `pendiente`, `num_factura_e`,
  `num_transaccion`, `notas`, `campo_libre_1`.
- **R4 del proyecto: aquí NO hay líneas de pago/cobro** (`Archivos MD/CLAUDE.md:34`). Los cobros
  viven en `pagos`/`movimientos_bancarios`; un "acto" realizado no es un pago.

### 4.5 `tratamientos_previstos` (`economico.py:353-384`)

- Plan de lo aceptado y no realizado. FK a centro/paciente/cliente/tratamiento/presupuesto_linea/
  tarifa/colaboradores/estado; `piezas`, `zona_boca`, `fecha_inicio/fin`, `actos`, `tiempo_min`,
  importes, `num_factura_e`, `num_transaccion`, `notas`, `estado_id`.
- **Discrepancia documental:** `clinico_router.py:421` afirma «tratamientos_previstos no tiene
  SQLModel: SQL crudo», pero **sí existe** `TratamientoPrevisto` (`economico.py:353-355`). El
  comentario está obsoleto; el modelo manda. No propagar el comentario al rebuild.
- **Ruta muerta:** la implementación viva de `GET /pacientes/{id}/previstos` es la de
  `pacientes_router.py:855` (ver `PARIDAD-API.md` §2.4).

### 4.6 `presupuestos` + `presupuesto_lineas` (`economico.py:132-188`)

- Cabecera: `num_serie`, `num_pre`, `titulo`, `fecha`, `fecha_aceptacion`, `estado_id →
  estados_presupuesto`, `tipo_presupuesto`, `financiacion`, `es_alternativa`,
  `alternativa_de_id → presupuestos.id`, `total`, `aprobado`, `serie`, `num_serie_presu`,
  **`hash_factura`**, `codigo_atcud`, **`codigo_qr`**, `fecha_aceptado_digital`,
  `fecha_entrega_digital`, `fecha_recibido_cliente`.
- Línea: `presupuesto_id`, `num_linea`, `tratamiento_id`, `tarifa_precio_id`, `colaborador_id`,
  `pieza`, `zona_boca`, **`estado`** (id de `estados_tratamiento` desde la migración `082`, no el
  catálogo efímero de `081`), `cantidad`, `unidades`, `precio_unitario`, `descuento`,
  `descuento_pct`, `base_imponible`, `tipo_iva`, `importe_iva`.
- Semántica de estados de línea: **1 Presupuestado, 3 Previsto, 5 Realizado, 7 Cancelado,
  8 Anulado** (`backend/migrations/082_estado_linea_a_estados_tratamiento.sql:5-7`). El
  `estado_id == 5` está **hardcodeado** en el código como «Realizado» (p. ej.
  `pacientes_router.py:982`, `:1241`; `clinico_router.py:158`) — **invariante de datos que no
  puede cambiar** sin tocar el código (ver §8).

### 4.7 `pagos`, `formas_pago`, `movimientos_bancarios` (dinero)

- `pagos` (`economico.py:251-284`): `centro_id`, `cliente_id`, `paciente_id`, `presupuesto_id`,
  `fecha`, `importe`, `neto`, `financiera_id`, `entrada`, `num_cuotas`, `interes_pct`,
  `cuota_mensual`, `forma_pago_id`, `banco_id`, `iban`, `num_recibo`, `motivo`, `num_factura`,
  `num_transaccion`, `automatico`, `anulado`, `liquidado`, `liquidacion_mov_id`,
  `origen`, `origen_id_gelite`, `origen_fecha`.
  Migraciones 058–070, 090 (saldo del paciente), 092 (motivo de devolución) cambian su
  significado (cobros legacy → pagos). **Datos fiscales**: no se puede "limpiar" sin decisión
  del propietario.
- `formas_pago` (`economico.py:227-238`): catálogo global con `codigo`, `nombre`, `grupo`,
  `en_caja`, `orden`; migración `040` + `107` (comisión de financieras).
- `movimientos_bancarios` (`gestoria.py:163-195`): `iban_cuenta`, `fecha_operacion`,
  `concepto_banco`, `concepto_corregido`, `importe`, `saldo_posterior`, `categoria`,
  `estado_concil`, `documento_admin_id`, `pago_id`. Único por (centro, iban, fecha, importe,
  saldo) según `023_mov_banc_unique_saldo.sql`.

### 4.8 `gastos`, `facturas_gestor`, `facturas_historico` (fiscal)

- `gastos` (`gestoria.py:34-68`): `proveedor_id`, `fecha`, `concepto`, `numero_factura`,
  `proveedor_extraido`, `cif_emisor`, `emisor_datos`, `base_imponible`, `iva_pct`, `retencion`,
  `suplido`, `total`, `divisa`, `tipo_documento`, `forma_pago`, `condiciones_pago`,
  `es_gasto_lab`, `estado`, `fiable`, `categoria`, `incidencia(s)`, `archivo_pdf_url`,
  `gmail_message_id`, `movimiento_id`.
- `facturas_gestor` (`gestor_ia.py:20-74`): factura extraída por IA del correo;
  `gmail_message_id` **único**, `numero_factura`, `fecha_emision`, `proveedor_nombre`,
  `id_fiscal`, IRPF, `iva_desglose` (JSON), `base_total`, `total`, `divisa`, `drive_url`,
  `drive_file_id`, `reconstruida`, `origen_dato`, `estado`.
- `facturas_historico` (`economico.py:386-404`): histórico fiscal por año/mes con `num_factura`,
  `base`, `iva`, `retencion`, `total`, `pdf_ruta`, `origen`.
- **VERI\*FACTU**: la huella encadenada y el QR de cotejo son **contrato fiscal**; el cálculo vive
  en `backend/domain/services/verifactu.py` (huella SHA-256 en mayúsculas, orden exacto de campos
  documentado en `:1-20` y `:78`) y está fijado con los ejemplos oficiales de la AEAT en
  `backend/tests/test_verifactu.py`. **No puede cambiar** ni el algoritmo ni el formato de
  fechas/importes.

### 4.9 `odontograma_entradas` / `periodontograma_medidas` (`dental.py:17-60`)

- `odontograma_entradas`: `paciente_id`, `pieza` (FDI como texto), `cara`, `estado`, `obs`,
  `tipo_registro` (INICIAL/…), `tratamiento_id`, `cita_id`, `fecha`. El contrato JSON que sirve la
  API usa `teeth` con claves `pieza`, `cara`, `estado`, `obs`, `tipoRegistro`, `fecha`
  (`pacientes_router.py:1221-1249`), **idéntico al .37** (docstring).
- `periodontograma_medidas`: 6 sitios por pieza (`bolsa_1..6`, `recesion_1..6`, `sangrado_1..4`,
  `placa_1..4`), `movilidad`, `exploracion_id`, `fecha`. La API traduce índices 0–31 a FDI con
  `_PERIO_FDI` (`pacientes_router.py:1290-1300`).
- El odontograma **se reemplaza completo** en cada PUT (delete+insert,
  `pacientes_router.py:1264-1290`): el rebuild debe mantener ese contrato de autosave.

### 4.10 Documentos clínicos: `consentimientos`, `recetas`, `documentos_paciente`

- `consentimientos` (`documentos.py:85-97`): `paciente_id`, `tratamiento_id`, `tipo`, `estado`,
  `firma_url`, `archivo_url`, **`signing_code`**, `signing_code_expira`. El `signing_code` es la
  autorización del enlace público de firma (`consentimientos_router.py:57-99`); migración `036`
  añade seguridad.
- `recetas` (`documentos.py:45-68`): `colaborador_id`, `cita_id`, `talonario_receta_id`, `fecha`,
  `tipo_receta`, `diagnostico`, `notas`, `urgencia`, `desabastecimiento`, `cve`, `publico`,
  `dispensada`, `anulada`, `aprobada`. Receta electrónica privada: **dato clínico sensible**.
- `documentos_paciente` (`documentos.py:156-170`): `tipo_doc`, `archivo_url`, `factura_origen_id`,
  `motivo_rectificacion` (migración `091` rectificativas).

### 4.11 Comunicación: `conversaciones`, `mensajes`

- `conversaciones` (`comunicacion.py:73-96`): `canal`, `telefono`, `estado`, `chatwoot_id`,
  `no_leidos`, `ultimo_mensaje(_at)`, `archivada`, `fijada`, `urgente`, `ultima_direccion`,
  `ia_pausada_hasta`, `mensaje_fijado_id`, `estado_flujo` (JSON de la máquina de estados de
  WhatsApp). **El estado del flujo es estado de negocio**: `domain/services/whatsapp_flujos.py`
  (tests `test_whatsapp_flujos.py`) y migraciones `007/008_whatsapp*`.
- `mensajes` (`comunicacion.py:98-122`): `direccion`, `cuerpo`, `enviado_at`, `message_id`,
  `estado`, `media_url/tipo/nombre`, `responde_a_id/texto`, `fijado`, `generado_por_ia`,
  `aprobado`, `eliminado`, `editado`. La hora real de los entrantes se corrigió en
  `114_hora_real_mensajes_whatsapp.sql`.
- `recalls` (`comunicacion.py:17-39`, 20 columnas) y `envios_email`/`envios_automaticos`
  (idempotencia de automatizaciones: `ENVIO_AUTOMATICO` y log) son el soporte de los flujos
  Motion/recordatorios.

### 4.12 `integraciones` y `configuraciones` (contrato de configuración)

- `integraciones` (`config.py:58-66`): `centro_id`, `tipo` (`whatsapp`, `email_imap`,
  `google_drive`, `orthanc`, …), `nombre`, **`config` (JSON)**, `activo`, `agente`. **Nunca
  contiene secretos en claro en este documento**; en código se enmascaran
  (`tests/test_secretos_integracion.py`).
- `configuraciones` (`config.py:44-56`): jerarquía **plataforma → centro → sistema → usuario**
  resuelta por `ConfigService.resolve` (`application/services/config_service.py:21-56`).
  Claves JSON relevantes citadas en otro lugares de esta spec: `plataforma.apariencia`,
  `centro.horario`, `centro.festivos`, `ficha_layout`, `centinela.config`, `gestor.config`,
  `gestor_multimodal.config`, `gmail.watch`. **Las claves y la forma de su JSON son contrato**
  entre frontend y backend; no se pueden renombrar sin migrar datos.

### 4.13 `auditoria` (`auditoria.py:15-28`)

`platform_user_id`, `usuario_id`, `centro_id`, `accion`, `recurso`, `detalle` (JSON), `ip`,
`exito`, `created_at`. Es la **prueba de trazabilidad** de login, accesos y operaciones
clínicas/económicas; el freno de login se calcula leyendo esta tabla
(`auth_service.py:68-84`). No se puede vaciar en el corte.

### 4.14 `analisis_dentia`, `imagenes_rx` y multimedia

- `imagenes_rx` (`clinico.py:111-121`): `paciente_id`, `cita_id`, `modalidad`, `archivo_url`,
  `orthanc_study_id`.
- `analisis_dentia` (`clinico.py:187-199`): `paciente_id`, `file_id`, `paso`, `patrones_json`,
  `plan_json`. El `file_id` es el identificador del proxy de Multimedia (base64 url-safe de la
  ruta relativa, `multimedia_service.py:41-46`) — **no** una URL: es contrato entre frontend y
  backend (DentIA).
- El **contenido** de las imágenes/PDF vive en `backend/media/` (1,2 GB), no en la BD
  (`MEDIA_PAC` en `multimedia_service.py:29`). Tablas y ficheros comparten `num_historia`; esa
  relación es el punto frágil del corte (ver §8 y `PARIDAD-FLUJOS.md` §2).
## 5. Inventario de tablas (142) por módulo de modelo

Leyenda: `FK` = claves foráneas declaradas en el modelo (`columna → tabla.destino`), `U` = columnas con `unique=True`.
Todas las tablas heredan `created_at`/`updated_at` de `TimestampMixin` (`backend/domain/models/_base.py:24-27`); las multi-tenant heredan `centro_id` NOT NULL de `TenantMixin` (`_base.py:30-40`).

### `backend/domain/models/comunicacion.py` — Comunicación: conversaciones, mensajes, plantillas, envíos de email, recalls, agente y voicebot.

| Tabla | Clase | Línea | FK | U | Propósito (docstring) |
|---|---|---|---|---|---|
| `acciones_boton` | `AccionBoton` | :192 | `centro_id→centros.id` | — | Catálogo de acciones de botón/encuesta (qué hace cada opción). |
| `agente_revisiones` | `AgenteRevision` | :154 | `centro_id→centros.id`, `agente_id→agentes.id`, `conversacion_id→conversaciones.id`, `revisado_por→usuarios.id` | — | Correcciones/entrenamiento por agente. Dos orígenes posibles (`conversacion_id` |
| `conversaciones` | `Conversacion` | :73 | `centro_id→centros.id`, `paciente_id→pacientes.id` | — |  |
| `envio_email_destinatarios` | `EnvioEmailDestinatario` | :63 | `envio_id→envios_email.id`, `paciente_id→pacientes.id`, `cliente_id→clientes.id` | — | Destinatario de una tirada de email. Origen: EdMailL. |
| `envios_automaticos` | `EnvioAutomatico` | :179 | `centro_id→centros.id`, `paciente_id→pacientes.id` | — | Log de envíos de automatización (idempotencia). Origen .37: automation_sent_log. |
| `envios_email` | `EnvioEmail` | :52 | `centro_id→centros.id`, `usuario_id→usuarios.id` | — | Tirada de envío masivo de email (Motion). Origen: EdMail. |
| `llamadas_voz` | `LlamadaVoz` | :205 | `centro_id→centros.id`, `paciente_id→pacientes.id` | — | Registro de una llamada/turno de voz atendido por el agente. Origen .37: voicebotCall. |
| `mensajes` | `Mensaje` | :98 | `conversacion_id→conversaciones.id` | — |  |
| `mensajes_paciente` | `MensajeInterno` | :41 | `paciente_id→pacientes.id`, `usuario_de_id→usuarios.id` | — | Mensaje/nota interna sobre un paciente (entre staff). Origen: PacMensajes. |
| `plantillas_mensaje` | `PlantillaMensaje` | :124 | `centro_id→centros.id`, `updated_by→usuarios.id` | — | Plantilla editable de mensaje (CONFIG = fuente de la verdad; nada hardcodeado). |
| `poll_contexto` | `PollContexto` | :139 | `centro_id→centros.id`, `plantilla_id→plantillas_mensaje.id` | — | Contexto para resolver el voto de una encuesta de WhatsApp. |
| `recalls` | `Recall` | :17 | `centro_id→centros.id`, `paciente_id→pacientes.id`, `colaborador_id→colaboradores.id` | — | Recordatorio / revisión programada del paciente. Origen: Recalls. |

### `backend/domain/models/agenda.py` — Recursos de agenda: agendas, gabinetes, tipos/estados de cita, horarios y bloqueos.

| Tabla | Clase | Línea | FK | U | Propósito (docstring) |
|---|---|---|---|---|---|
| `agendas` | `Agenda` | :19 | `centro_id→centros.id` | — | Calendario por especialidad/servicio del centro (Odontología, Fisioterapia…). |
| `bloqueos_agenda` | `BloqueoAgenda` | :97 | `centro_id→centros.id`, `colaborador_id→colaboradores.id`, `gabinete_id→gabinetes.id` | — | Hueco no disponible: vacaciones, festivo, mantenimiento. |
| `colaborador_excepciones` | `ColaboradorExcepcion` | :83 | `colaborador_id→colaboradores.id` | — | Excepción puntual de horario de un colaborador (rango de fechas, horas a medida). |
| `colaborador_horarios` | `ColaboradorHorario` | :67 | `centro_id→centros.id`, `agenda_id→agendas.id`, `colaborador_id→colaboradores.id`, `gabinete_id→gabinetes.id` | — | Franja de trabajo de un colaborador (día de la semana, con pausa opcional). |
| `estados_cita` | `EstadoCita` | :44 | `centro_id→centros.id`, `agenda_id→agendas.id` | — | Catálogo de estados de cita (Planificada, Anulada, Finalizada…) con color. |
| `gabinetes` | `Gabinete` | :57 | `centro_id→centros.id`, `agenda_id→agendas.id` | — | Recurso físico donde se atiende (sillón/box). |
| `tipos_cita` | `TipoCita` | :32 | `centro_id→centros.id`, `agenda_id→agendas.id` | — | Tipo/motivo de cita que se muestra en la agenda (catálogo; NO el tratamiento clínico). |

### `backend/domain/models/agentes.py` — Agentes IA configurables y revisiones/canal.

| Tabla | Clase | Línea | FK | U | Propósito (docstring) |
|---|---|---|---|---|---|
| `agente_canal_ajuste` | `AgenteCanalAjuste` | :84 | `agente_id→agentes.id` | — | Ajuste fino por canal (Sección 7), capa sobre personalidad base+aprendida. |
| `agente_capacidades` | `AgenteCapacidad` | :47 | `agente_id→agentes.id`, `capacidad_id→capacidades_catalogo.id` | — | Tabla puente: qué capacidades tiene activas cada agente. |
| `agente_permisos_admin` | `AgentePermisoAdmin` | :74 | `agente_id→agentes.id` | — | Quién puede administrar un agente (Sección 6). Reutiliza roles existentes. |
| `agente_personalidad` | `AgentePersonalidad` | :56 | `agente_id→agentes.id` | — | Personalidad en dos capas (Sección 4 spec): base + aprendida. Prompt final = base + aprendida. |
| `agentes` | `Agente` | :18 | `centro_id→centros.id` | — | Un agente de IA configurable, de base o creado por un centro. |
| `capacidades_catalogo` | `CapacidadCatalogo` | :36 | — | clave | Biblioteca compartida de capacidades reales — cada fila apunta a una |

### `backend/domain/models/clinico.py` — Entidades clínicas del paciente (alergias, diagnósticos, recetas preescritas, radiología, dentia, cefalometría, SOAP).

| Tabla | Clase | Línea | FK | U | Propósito (docstring) |
|---|---|---|---|---|---|
| `alergias` | `Alergia` | :38 | `paciente_id→pacientes.id` | — |  |
| `alertas_paciente` | `AlertaPaciente` | :28 | `paciente_id→pacientes.id` | — |  |
| `analisis_cefalo` | `AnalisisCefalo` | :164 | — | — | Análisis cefalométrico definido por el centro (a medida). `landmarks_json` = puntos a colocar |
| `analisis_dentia` | `AnalisisDentia` | :187 | `paciente_id→pacientes.id` | — | Análisis DentIA de UNA imagen de Multimedia (identificada por su `file_id`, no por ImagenRx): |
| `anotaciones_imagen` | `AnotacionImagen` | :177 | `imagen_id→imagenes_rx.id`, `paciente_id→pacientes.id` | — | Anotaciones gráficas sobre una imagen radiológica (flechas, líneas/medidas, ángulos, texto). |
| `cefalometrias` | `Cefalometria` | :201 | `imagen_id→imagenes_rx.id`, `paciente_id→pacientes.id` | — | Trazado cefalométrico sobre una telerradiografía lateral: landmarks colocados por el doctor + |
| `diagnosticos` | `Diagnostico` | :65 | — | — | Catálogo de diagnósticos (CIE / ICD-9). |
| `hallazgos_imagen` | `HallazgoImagen` | :123 | `imagen_id→imagenes_rx.id`, `cita_tratamiento_id→cita_tratamiento.id` | — | Hallazgo detectado en una imagen, cruzado con el acto clínico (pieza). |
| `imagenes_rx` | `ImagenRx` | :111 | `paciente_id→pacientes.id`, `cita_id→citas.id` | — |  |
| `medic_preescrita` | `MedicPreescrita` | :91 | `paciente_id→pacientes.id`, `centro_id→centros.id`, `vademecum_id→vademecum.id` | — | Medicación prescrita a un paciente: fármaco, dosis, vía y pauta. |
| `plan_proxima_cita` | `PlanProximaCita` | :229 | `centro_id→centros.id`, `paciente_id→pacientes.id`, `colaborador_id→colaboradores.id`, `presupuesto_id→presupuestos.id` | — | Lo que el doctor deja planificado para la PRÓXIMA cita del paciente: tratamientos |
| `romexis_sync` | `RomexisSync` | :137 | `paciente_id→pacientes.id` | — | Cola/máquina de estados del puente de pacientes web → Romexis (PMBridge). |
| `rx_exportada` | `RxExportada` | :245 | `centro_id→centros.id`, `paciente_id→pacientes.id` | — | Registro de cada instancia DICOM de Orthanc ya procesada por el detector de RX nuevas. |
| `soap` | `Soap` | :215 | `cita_id→citas.id`, `paciente_id→pacientes.id` | cita_id |  |
| `subtipos_antecedente` | `SubtipoAntecedente` | :55 | `tipo_antecedente_id→tipos_antecedente.id` | — | Subtipo de antecedente médico. Origen: TSubTipoAntecedentes. |
| `tipos_antecedente` | `TipoAntecedente` | :47 | — | — | Tipo de antecedente médico (catálogo). |
| `vademecum` | `Vademecum` | :74 | — | — | Catálogo de fármacos: descripción, presentación, clasificación ATC y precio. |

### `backend/domain/models/identidad.py` — Identidad y RBAC en dos niveles (usuario global × acceso por centro × rol × permisos finos) + usuarios de plataforma.

| Tabla | Clase | Línea | FK | U | Propósito (docstring) |
|---|---|---|---|---|---|
| `areas` | `Area` | :151 | `sistema_id→sistemas.id` | — | Sección de la app (pantalla). Pertenece a un sistema. |
| `password_resets` | `PasswordReset` | :172 | `usuario_id→usuarios.id` | — | Token de recuperación de contraseña (un solo uso, con caducidad). |
| `permisos` | `Permiso` | :86 | — | codigo | Catálogo de permisos finos. |
| `platform_users` | `PlatformUser` | :23 | — | email | Operador del SaaS (superadmin). SEPARADO de los usuarios de centro. |
| `rol_area` | `RolArea` | :165 | `rol_id→roles.id`, `area_id→areas.id` | — | Acceso de un rol a un área (qué pantallas ve cada rol). |
| `role_permisos` | `RolePermiso` | :95 | `rol_id→roles.id`, `permiso_id→permisos.id` | — | N:M rol↔permiso. |
| `roles` | `Rol` | :77 | `centro_id→centros.id` | — |  |
| `sistemas` | `Sistema` | :140 | — | codigo | Sistema del organismo (CUIDARTE, ESCÚCHARTE, GESTIÓNALO, IA, Configuración, SuperUser). |
| `user_center_permisos` | `UserCenterPermiso` | :115 | `usuario_id→usuarios.id`, `centro_id→centros.id`, `permiso_id→permisos.id` | — | PERMISOS efectivos por persona: usuario × centro × permiso (concesión directa). |
| `user_center_permisos_denegados` | `UserCenterPermisoDenegado` | :125 | `usuario_id→usuarios.id`, `centro_id→centros.id`, `permiso_id→permisos.id` | — | LIMITES por persona: permisos que su rol concede pero a ESTA persona se le quitan |
| `user_center_roles` | `UserCenterRole` | :104 | `usuario_id→usuarios.id`, `centro_id→centros.id`, `rol_id→roles.id` | — | La tabla de ACCESOS (MEMBRESÍA): usuario × centro. Da acceso al centro y construye |
| `usuario_periodos` | `UsuarioPeriodo` | :57 | `usuario_id→usuarios.id`, `centro_id→centros.id` | — | Una etapa laboral de la persona (alta→baja). Una persona puede tener varias. |
| `usuarios` | `Usuario` | :35 | — | — | La PERSONA (IdStaff). Identidad fija, única — nunca se duplica. |

### `backend/domain/models/almacen.py` — Inventario de material por centro.

| Tabla | Clase | Línea | FK | U | Propósito (docstring) |
|---|---|---|---|---|---|
| `articulos` | `Articulo` | :17 | `centro_id→centros.id` | — |  |
| `stock_movimientos` | `StockMovimiento` | :30 | `articulo_id→articulos.id`, `proveedor_id→proveedores.id`, `cita_tratamiento_id→cita_tratamiento.id` | — | Entrada (compra) o salida (consumo) de un artículo. |

### `backend/domain/models/auditoria.py` — Registro de auditoría (CENTINELA).

| Tabla | Clase | Línea | FK | U | Propósito (docstring) |
|---|---|---|---|---|---|
| `auditoria` | `Auditoria` | :15 | `platform_user_id→platform_users.id`, `usuario_id→usuarios.id`, `centro_id→centros.id` | — |  |

### `backend/domain/models/ia.py` — Artefactos de IA (briefings de AURA, transcripciones).

| Tabla | Clase | Línea | FK | U | Propósito (docstring) |
|---|---|---|---|---|---|
| `briefings_aura` | `BriefingAura` | :26 | `cita_id→citas.id`, `paciente_id→pacientes.id` | cita_id | Preparación previa generada por AURA antes de la cita. |
| `transcripciones` | `Transcripcion` | :37 | `cita_id→citas.id`, `paciente_id→pacientes.id` | — | Escucha activa (ESCUCHA): transcripción de la conversación de consulta. |

### `backend/domain/models/ortodoncia.py` — Casos de ortodoncia, intervenciones, estudios y fotos.

| Tabla | Clase | Línea | FK | U | Propósito (docstring) |
|---|---|---|---|---|---|
| `casos_ortodoncia` | `CasoOrtodoncia` | :18 | `centro_id→centros.id`, `paciente_id→pacientes.id`, `colaborador_id→colaboradores.id`, `tratamiento_id→tratamientos.id` | — |  |
| `estudios_ortodoncia` | `EstudioOrtodoncia` | :48 | `centro_id→centros.id`, `paciente_id→pacientes.id`, `caso_id→casos_ortodoncia.id`, `colaborador_id→colaboradores.id` | — | Sesión de registros fotográficos del paciente en un momento del tratamiento. |
| `fotos_ortodoncia` | `FotoOrtodoncia` | :72 | `estudio_id→estudios_ortodoncia.id`, `centro_id→centros.id`, `paciente_id→pacientes.id` | — | Una foto de un estudio, ocupando UNA ranura del protocolo (tipo). |
| `intervenciones_ortodoncia` | `IntervencionOrtodoncia` | :37 | `caso_id→casos_ortodoncia.id`, `cita_id→citas.id` | — | Revisión/ajuste del caso (cada visita de control de orto). |

### `backend/domain/models/core.py` — Los 5 nodos-dios (centro, paciente, colaborador, cita, tratamiento) y sus entidades de primer nivel.

| Tabla | Clase | Línea | FK | U | Propósito (docstring) |
|---|---|---|---|---|---|
| `centro_asociaciones` | `CentroAsociacion` | :65 | `centro_id→centros.id`, `asociado_a_centro_id→centros.id` | — | Un centro asociado a otro, con lo que comparte elegido independientemente (ninguno, |
| `centros` | `Centro` | :44 | `razon_social_compartida_id→razones_sociales.id` | — |  |
| `cita_tratamiento` | `CitaTratamiento` | :399 | `cita_id→citas.id`, `tratamiento_id→tratamientos.id` | — | N:M cita↔tratamiento (qué se hace/realiza en cada cita). |
| `citas` | `Cita` | :341 | `centro_id→centros.id`, `agenda_id→agendas.id`, `estado_id→estados_cita.id`, `paciente_id→pacientes.id`, `tutor_id→pacientes.id`, `colaborador_id→colaboradores.id`, `usuario_id→usuarios.id`, `gabinete_id→gabinetes.id`, `tipo_cita_id→tipos_cita.id`, `tarifa_id→tarifas.id` | — |  |
| `codigos_postales` | `CodigoPostal` | :438 | `poblacion_id→poblaciones.id` | — | CP ↔ población LEGADO — ver aviso en Poblacion. No usar para nada nuevo. |
| `codigos_postales_geo` | `CodigoPostalGeo` | :472 | `municipio_id→municipios.id` | — | CP ↔ municipio oficial (INE). Un municipio puede tener varios CP y, |
| `colaborador_centro` | `ColaboradorCentro` | :293 | `colaborador_id→colaboradores.id`, `centro_id→centros.id` | — | N:M colaborador↔centro (un doctor trabaja en varios centros). |
| `colaborador_especialidad` | `ColaboradorEspecialidad` | :269 | `colaborador_id→colaboradores.id`, `especialidad_id→especialidades.id` | — | N:M colaborador↔especialidad (idEspecia múltiple). |
| `colaborador_tipo_cita` | `ColaboradorTipoCita` | :285 | `colaborador_id→colaboradores.id`, `tipo_cita_id→tipos_cita.id` | — | Duración (min) de un tipo de cita para un colaborador concreto. Sin default global. |
| `colaborador_tratamiento_exento` | `ColaboradorTratamientoExento` | :277 | `colaborador_id→colaboradores.id`, `tratamiento_id→tratamientos.id` | — | N:M colaborador↔tratamiento exento de comisión. |
| `colaboradores` | `Colaborador` | :244 | `periodo_id→usuario_periodos.id`, `talonario_id→talonarios.id` | periodo_id |  |
| `consentimientos_paciente` | `ConsentimientoPaciente` | :209 | `paciente_id→pacientes.id`, `centro_id→centros.id` | — | Histórico de consentimientos RGPD del paciente: qué se aceptó, cuándo y qué versión. |
| `dispositivos_paciente` | `DispositivoPaciente` | :481 | `paciente_id→pacientes.id` | — | Dispositivo del paciente (app/push/firma). Origen: DispositivoPac. |
| `especialidades` | `Especialidad` | :259 | `centro_id→centros.id` | — | Catálogo de especialidades (un colaborador puede tener varias). |
| `municipios` | `Municipio` | :463 | `provincia_id→provincias.id` | — | Catálogo oficial de municipios españoles (INE, Callejero del Censo Electoral). |
| `paciente_otps` | `PacienteOtp` | :196 | `paciente_id→pacientes.id`, `centro_id→centros.id` | — | Código OTP de acceso a la app del paciente (un solo uso, con caducidad). |
| `paciente_seguros` | `PacienteSeguro` | :185 | `paciente_id→pacientes.id` | — | Seguro / mutua del paciente (un paciente puede tener varios). |
| `pacientes` | `Paciente` | :163 | `centro_id→centros.id`, `cliente_id→clientes.id`, `agenda_id→agendas.id`, `tutor_id→pacientes.id` | — |  |
| `paises` | `Pais` | :446 | — | iso2 | Catálogo oficial de países (ISO 3166-1 alpha-2). |
| `poblaciones` | `Poblacion` | :427 | — | — | Catálogo LEGADO de poblaciones (datos sucios heredados de la migración GELITE, |
| `provincias` | `Provincia` | :454 | `pais_id→paises.id` | — | Catálogo oficial de provincias españolas (INE). |
| `razones_sociales` | `RazonSocial` | :97 | `centro_id→centros.id` | — |  |
| `tratamiento_fases` | `TratamientoFase` | :413 | `tratamiento_id→tratamientos.id` | — | Fase del catálogo de un tratamiento (orden, duración, % a facturar). |
| `tratamientos` | `Tratamiento` | :387 | `centro_id→centros.id`, `especialidad_id→especialidades.id`, `tipo_cita_id→tipos_cita.id` | — |  |

### `backend/domain/models/economico.py` — Dominio económico: tarifas, presupuestos, tratamientos realizados/previstos, pagos, formas de pago, histórico de facturas.

| Tabla | Clase | Línea | FK | U | Propósito (docstring) |
|---|---|---|---|---|---|
| `clientes` | `Cliente` | :22 | `centro_id→centros.id` | — | Identidad económica / titular de facturación (IdCli). |
| `estados_presupuesto` | `EstadoPresupuesto` | :121 | — | — | Catálogo de estados de presupuesto (Nuevo, Entregado, Aceptado, En curso, Finalizado). |
| `estados_tratamiento` | `EstadoTratamiento` | :286 | — | — | Catálogo de estados de tratamiento realizado (Planificado, En curso, Finalizado). |
| `facturas_historico` | `FacturaHistorico` | :386 | `centro_id→centros.id` | — | Archivo DOCUMENTAL de consulta: filas de los LIBROFACTURAS.xls históricos + sus PDFs. |
| `financieras` | `Financiera` | :240 | `centro_id→centros.id` | — | Entidad financiera (Cetelem, Pepper, Sabadell Consumer…). |
| `formas_pago` | `FormaPago` | :227 | — | — | Catálogo ÚNICO de formas de pago de pacientes (migración 040). ids 1-15 = TForPago de Gesden. |
| `laboratorio_trabajos` | `LaboratorioTrabajo` | :87 | `centro_id→centros.id`, `proveedor_id→proveedores.id` | — | Lista de precios de un laboratorio (proveedores.es_laboratorio): un trabajo y su coste. |
| `paciente_tarifas` | `PacienteTarifa` | :50 | `paciente_id→pacientes.id`, `tarifa_id→tarifas.id` | — | Tarifa/póliza asignada a un paciente (puede tener varias). Origen: Pacientes_Tarifas. |
| `pagos` | `Pago` | :251 | `centro_id→centros.id`, `cliente_id→clientes.id`, `paciente_id→pacientes.id`, `presupuesto_id→presupuestos.id`, `financiera_id→financieras.id`, `forma_pago_id→formas_pago.id`, `liquidacion_mov_id→movimientos_bancarios.id` | — |  |
| `presupuesto_lineas` | `PresupuestoLinea` | :166 | `presupuesto_id→presupuestos.id`, `tratamiento_id→tratamientos.id`, `tarifa_precio_id→tarifa_precios.id`, `colaborador_id→colaboradores.id`, `estado→estados_tratamiento.id` | — |  |
| `presupuestos` | `Presupuesto` | :132 | `centro_id→centros.id`, `paciente_id→pacientes.id`, `razon_social_id→razones_sociales.id`, `colaborador_id→colaboradores.id`, `estado_id→estados_presupuesto.id`, `alternativa_de_id→presupuestos.id` | — |  |
| `presupuestos_predisenados` | `PresupuestoPredisenado` | :190 | `centro_id→centros.id`, `colaborador_id→colaboradores.id` | — | Plantilla de presupuesto: un título + un conjunto de tratamientos (líneas). |
| `presupuestos_predisenados_lineas` | `PresupuestoPredisenadoLinea` | :207 | `predisenado_id→presupuestos_predisenados.id`, `tratamiento_id→tratamientos.id` | — |  |
| `tarifa_precio_trabajos` | `TarifaPrecioTrabajo` | :99 | `tarifa_precio_id→tarifa_precios.id`, `laboratorio_trabajo_id→laboratorio_trabajos.id` | — | Trabajo de laboratorio de un precio de tarifa (p. ej. corona + interfase + tornillo). |
| `tarifa_precios` | `TarifaPrecio` | :76 | `tarifa_id→tarifas.id`, `tratamiento_id→tratamientos.id` | — | Precio de un tratamiento dentro de una tarifa (tarifa × tratamiento). |
| `tarifas` | `Tarifa` | :65 | `centro_id→centros.id` | — |  |
| `tratamientos_previstos` | `TratamientoPrevisto` | :353 | `centro_id→centros.id`, `paciente_id→pacientes.id`, `cliente_id→clientes.id`, `tratamiento_id→tratamientos.id`, `presupuesto_linea_id→presupuesto_lineas.id`, `tarifa_precio_id→tarifa_precios.id`, `colaborador_id→colaboradores.id`, `colaborador_aux_id→colaboradores.id`, `estado_id→estados_tratamiento.id` | — | Tratamiento pendiente de realizar (plan tras aceptar presupuesto). |
| `tratamientos_realizados` | `TratamientoRealizado` | :297 | `centro_id→centros.id`, `paciente_id→pacientes.id`, `cliente_id→clientes.id`, `tratamiento_id→tratamientos.id`, `tarifa_precio_id→tarifa_precios.id`, `presupuesto_linea_id→presupuesto_lineas.id`, `colaborador_id→colaboradores.id`, `colaborador_aux_id→colaboradores.id`, `estado_id→estados_tratamiento.id`, `factura_documento_id→documentos_admin.id` | — | Acto clínico realizado (producción). Origen GELITE: TtosMed. |
| `tratamientos_realizados_fases` | `TratamientoRealizadoFase` | :340 | `tratamiento_realizado_id→tratamientos_realizados.id`, `colaborador_id→colaboradores.id` | — |  |

### `backend/domain/models/config.py` — Configuración jerárquica (la única fuente de la verdad) e integraciones externas.

| Tabla | Clase | Línea | FK | U | Propósito (docstring) |
|---|---|---|---|---|---|
| `configuraciones` | `Configuracion` | :44 | `centro_id→centros.id`, `usuario_id→usuarios.id` | — | Una entrada de configuración en un ámbito concreto. |
| `integraciones` | `Integracion` | :58 | `centro_id→centros.id` | — | Conector externo del centro (WhatsApp/Evolution, email, pasarela…) con su config JSON. |

### `backend/domain/models/documentos.py` — Documentos: recetas, consentimientos, PDFs, talonarios y documentos de paciente/admin.

| Tabla | Clase | Línea | FK | U | Propósito (docstring) |
|---|---|---|---|---|---|
| `consentimientos` | `Consentimiento` | :85 | `centro_id→centros.id`, `paciente_id→pacientes.id`, `tratamiento_id→tratamientos.id` | — |  |
| `documentos_admin` | `DocumentoAdmin` | :123 | `centro_id→centros.id`, `cliente_id→clientes.id`, `razon_social_id→razones_sociales.id` | — | Documento administrativo / factura (con datos fiscales). Origen: DocAdmin. |
| `documentos_firmados` | `DocumentoFirmado` | :172 | `paciente_id→pacientes.id`, `firma_usuario_id→usuarios.id`, `colaborador_firma_id→colaboradores.id` | — | Documento firmado (digitalmente) por paciente o colaborador. Origen: DocsFirmados. |
| `documentos_generados` | `DocumentoGenerado` | :111 | `centro_id→centros.id`, `paciente_id→pacientes.id`, `razon_social_id→razones_sociales.id`, `presupuesto_id→presupuestos.id` | — | PDF generado (factura/recibo/justificante) con membrete del centro + sello. |
| `documentos_paciente` | `DocumentoPaciente` | :156 | `paciente_id→pacientes.id`, `usuario_id→usuarios.id`, `factura_origen_id→documentos_admin.id` | — | Documento/fichero adjunto a la ficha del paciente. Origen: TDocumentosPac. |
| `plantillas_documento` | `PlantillaDocumento` | :201 | `centro_id→centros.id`, `especialidad_id→especialidades.id`, `colaborador_id→colaboradores.id` | — | Plantilla de documento (carta, informe…). Origen: EdDocs. |
| `receta_lineas` | `RecetaLinea` | :70 | `receta_id→recetas.id`, `tratamiento_id→tratamientos.id` | — |  |
| `recetas` | `Receta` | :45 | `centro_id→centros.id`, `paciente_id→pacientes.id`, `colaborador_id→colaboradores.id`, `cita_id→citas.id`, `talonario_receta_id→talonario_recetas.id` | — |  |
| `recetas_frecuentes` | `RecetaFrecuente` | :190 | `centro_id→centros.id`, `colaborador_id→colaboradores.id` | — | Receta frecuente del doctor (plantilla para reutilizar rápidamente). |
| `recomendaciones_paciente` | `RecomendacionPaciente` | :99 | `centro_id→centros.id`, `paciente_id→pacientes.id`, `cita_id→citas.id` | — | Recomendaciones seleccionadas al final de la consulta (Caminos 1, 2, 3). |
| `talonario_recetas` | `TalonarioReceta` | :33 | `talonario_id→talonarios.id` | — | Número individual de un talonario (cve oficial, marcado al usarse). |
| `talonarios` | `Talonario` | :20 | `centro_id→centros.id`, `colaborador_id→colaboradores.id` | — | Talonario oficial de recetas asignado a un colaborador (lote numerado). |

### `backend/domain/models/gestor_ia.py` — Motor IA de facturación: facturas extraídas del correo, proveedores, revisiones, descartes y pasadas.

| Tabla | Clase | Línea | FK | U | Propósito (docstring) |
|---|---|---|---|---|---|
| `descartes_gestor` | `DescarteGestor` | :152 | `centro_id→centros.id` | gmail_message_id | Correo que el motor determinó que NO es un documento facturable (§2). |
| `excepciones_gestor` | `ExcepcionGestor` | :95 | `centro_id→centros.id` | — | Reglas manuales del usuario que corrigen al motor en casos concretos. |
| `facturas_gestor` | `FacturaGestor` | :20 | `centro_id→centros.id`, `proveedor_id→proveedores_gestor.id` | gmail_message_id | Factura válida leída de un correo (§1). |
| `pasadas_gestor` | `PasadaGestor` | :174 | `centro_id→centros.id` | — | Registro de cada barrido: qué se procesó, cuánto costó y en qué acabó. |
| `proveedores_gestor` | `ProveedorGestor` | :76 | `centro_id→centros.id` | id_fiscal | Directorio propio (§8). Identidad = ID fiscal; jamás se fusiona por nombre. |
| `revisiones_gestor` | `RevisionGestor` | :125 | `centro_id→centros.id` | gmail_message_id | Correo que SÍ parece facturable pero que el motor no pudo resolver (§9). |

### `backend/domain/models/gestoria.py` — Gestoría/contabilidad: proveedores, gastos, movimientos bancarios, extractos, liquidaciones, deudas, modelos fiscales.

| Tabla | Clase | Línea | FK | U | Propósito (docstring) |
|---|---|---|---|---|---|
| `deuda_pago` | `DeudaPago` | :130 | `deuda_id→deudas.id`, `pago_id→pagos.id` | — | Aplicación de un pago a una deuda (N:M deuda↔pago). Origen: DeudaPago. |
| `deudas` | `Deuda` | :111 | `centro_id→centros.id`, `paciente_id→pacientes.id`, `cliente_id→clientes.id`, `presupuesto_id→presupuestos.id`, `tratamiento_realizado_id→tratamientos_realizados.id` | — |  |
| `extractos_subidos` | `ExtractoSubido` | :141 | `centro_id→centros.id`, `subido_por→usuarios.id` | — | Fichero de extracto bancario TAL CUAL se subió (PDF/XLSX/CSV), archivado. |
| `gasto_incidencias` | `GastoIncidencia` | :70 | `centro_id→centros.id` | — | Correo del buzón que NO se convirtió en gasto (ruido, sin datos legibles…). |
| `gastos` | `Gasto` | :34 | `centro_id→centros.id`, `proveedor_id→proveedores.id`, `movimiento_id→movimientos_bancarios.id` | — | Factura recibida / gasto. |
| `liquidacion_lineas` | `LiquidacionLinea` | :98 | `liquidacion_id→liquidaciones.id`, `presupuesto_linea_id→presupuesto_lineas.id` | — | Acto facturado que se liquida al doctor (enlaza con la línea de presupuesto). |
| `liquidaciones` | `Liquidacion` | :83 | `centro_id→centros.id`, `colaborador_id→colaboradores.id` | — | Paga de un colaborador en un periodo. |
| `modelos_fiscales` | `ModeloFiscal` | :197 | `centro_id→centros.id` | — | Presentación de modelo fiscal (303/130/111/390…). |
| `movimientos_bancarios` | `MovimientoBancario` | :163 | `centro_id→centros.id`, `documento_admin_id→documentos_admin.id`, `pago_id→pagos.id` | — | Apunte del extracto bancario; se concilia con gasto o factura emitida. |
| `proveedores` | `Proveedor` | :18 | `centro_id→centros.id` | — |  |

### `backend/domain/models/informes.py` — Definiciones de informes guardados.

| Tabla | Clase | Línea | FK | U | Propósito (docstring) |
|---|---|---|---|---|---|
| `informes` | `Informe` | :16 | `centro_id→centros.id` | — |  |

### `backend/domain/models/dental.py` — Odontograma y periodontograma (estado dental por pieza y por sitio).

| Tabla | Clase | Línea | FK | U | Propósito (docstring) |
|---|---|---|---|---|---|
| `odontograma_entradas` | `OdontogramaEntrada` | :17 | `paciente_id→pacientes.id`, `tratamiento_id→tratamientos.id`, `cita_id→citas.id` | — | Estado/hallazgo de una pieza (caries, corona, implante, ausente…). |
| `periodontograma_medidas` | `PeriodontogramaMedida` | :33 | `paciente_id→pacientes.id`, `cita_id→citas.id` | — | Medidas periodontales de una pieza por SITIOS (6): bolsa, recesión, sangrado, placa, movilidad. |

### `backend/domain/models/protesis.py` — Trabajos protésicos y sus fases.

| Tabla | Clase | Línea | FK | U | Propósito (docstring) |
|---|---|---|---|---|---|
| `trabajo_protesico_fases` | `TrabajoProtesicoFase` | :35 | `trabajo_id→trabajos_protesicos.id`, `cita_id→citas.id` | — | Fase/prueba de un trabajo (prueba de metal, bizcocho, colocación…). |
| `trabajos_protesicos` | `TrabajoProtesico` | :18 | `centro_id→centros.id`, `paciente_id→pacientes.id`, `cita_tratamiento_id→cita_tratamiento.id`, `proveedor_id→proveedores.id` | — |  |
## 6. Inventario de migraciones (126 ficheros SQL)

`S` = toca esquema (CREATE/ALTER/INDEX/VIEW/DROP/SEQUENCE); `D` = toca datos (INSERT/UPDATE/DELETE).
Un fichero puede ser `S+D` (esquema + backfill). Las de solo datos son **decisiones de negocio**,
no reproducibles por ingeniería inversa: hay que decidir una a una si se portan al rebuild.

| # | Fichero | Líneas | S | D | Tipos detectados | Tablas creadas/alteradas |
|---|---|---:|---|---|---|---|
| 1 | `001_usuario_periodos.sql` | 65 | S | D | CREATE TABLE, INDEX, ALTER TABLE, INSERT, UPDATE, DROP | USUARIO_PERIODOS · COLABORADORES, USUARIOS |
| 2 | `002_paciente_anamnesis_extra.sql` | 12 | S |  | ALTER TABLE |  · PACIENTES |
| 3 | `003_colaborador_exentos_y_tiempos.sql` | 47 | S | D | CREATE TABLE, INDEX, ALTER TABLE, INSERT, DROP | COLABORADOR_TIPO_CITA, COLABORADOR_TRATAMIENTO_EXENTO · COLABORADORES, COLABORADOR_TIPO_CITA, COLABORADOR_TRATAMIENTO_EXENTO |
| 4 | `003_tipos_cita_drop_duracion.sql` | 3 | S |  | ALTER TABLE, DROP |  · TIPOS_CITA |
| 5 | `004_config_agenda_por_agenda.sql` | 25 | S | D | INDEX, ALTER TABLE, UPDATE |  · AGENDAS, COLABORADOR_HORARIOS, ESTADOS_CITA |
| 6 | `004_odontograma_hallazgos.sql` | 10 | S |  | ALTER TABLE |  · ODONTOGRAMA_ENTRADAS |
| 7 | `005_filiacion_normalizada.sql` | 28 | S |  | CREATE TABLE, INDEX, ALTER TABLE | PACIENTE_SEGUROS · CLIENTES, PACIENTES |
| 8 | `006_gestoria.sql` | 50 | S |  | CREATE TABLE, INDEX, ALTER TABLE | MODELOS_FISCALES, MOVIMIENTOS_BANCARIOS · GASTOS, PROVEEDORES |
| 9 | `007_colaborador_pct.sql` | 7 | S | D | ALTER TABLE, UPDATE |  · COLABORADORES |
| 10 | `007_whatsapp.sql` | 93 | S |  | CREATE TABLE, INDEX, ALTER TABLE | ACCIONES_BOTON, PLANTILLAS_MENSAJE, POLL_CONTEXTO · CONVERSACIONES, MENSAJES |
| 11 | `008_gasto_incidencias.sql` | 15 | S |  | CREATE TABLE, INDEX, ALTER TABLE | GASTO_INCIDENCIAS · GASTOS |
| 12 | `008_whatsapp_flujo.sql` | 5 | S |  | ALTER TABLE |  · CONVERSACIONES |
| 13 | `009_automatizacion.sql` | 17 | S |  | CREATE TABLE, INDEX | ENVIOS_AUTOMATICOS |
| 14 | `010_voicebot.sql` | 19 | S |  | CREATE TABLE, INDEX | LLAMADAS_VOZ |
| 15 | `011_presupuesto_estados.sql` | 9 |  | D | INSERT | — |
| 16 | `012_movimiento_pago.sql` | 3 | S |  | INDEX, ALTER TABLE |  · MOVIMIENTOS_BANCARIOS |
| 17 | `013_proveedor_directorio.sql` | 4 | S |  | ALTER TABLE |  · PROVEEDORES |
| 18 | `014_gasto_fiscal.sql` | 14 | S |  | INDEX, ALTER TABLE |  · GASTOS |
| 19 | `015_gasto_campos.sql` | 8 | S |  | ALTER TABLE |  · GASTOS |
| 20 | `016_gasto_suplido.sql` | 8 | S |  | ALTER TABLE |  · GASTOS |
| 21 | `017_pago_neto.sql` | 3 | S |  | ALTER TABLE |  · PAGOS |
| 22 | `018_descuento_aplica_doctor.sql` | 4 | S |  | ALTER TABLE |  · TRATAMIENTOS_REALIZADOS |
| 23 | `019_pago_liquidacion.sql` | 3 | S |  | INDEX, ALTER TABLE |  · PAGOS |
| 24 | `020_usuario_periodo_centro.sql` | 26 | S | D | INDEX, ALTER TABLE, UPDATE |  · USUARIO_PERIODOS |
| 25 | `021_centro_asociaciones.sql` | 31 | S |  | CREATE TABLE, INDEX, ALTER TABLE | CENTRO_ASOCIACIONES · CENTROS |
| 26 | `022_agente_revisiones.sql` | 27 | S |  | CREATE TABLE, INDEX | AGENTE_REVISIONES |
| 27 | `023_integracion_agente.sql` | 11 | S |  | ALTER TABLE |  · INTEGRACIONES |
| 28 | `023_mov_banc_unique_saldo.sql` | 21 | S |  | ALTER TABLE |  · MOVIMIENTOS_BANCARIOS |
| 29 | `024_agente_revisiones_por_agente.sql` | 11 | S |  | ALTER TABLE |  · AGENTE_REVISIONES |
| 30 | `024_extractos_subidos.sql` | 24 | S |  | CREATE TABLE, INDEX | EXTRACTOS_SUBIDOS |
| 31 | `024_receta_lineas_campos_completos.sql` | 23 | S |  | INDEX, ALTER TABLE |  · PUBLIC.RECETA_LINEAS |
| 32 | `025_gasto_movimiento_link.sql` | 34 | S | D | CREATE TABLE, INDEX, ALTER TABLE, UPDATE | _SNAP_MOV_GASTO_LINK · GASTOS |
| 33 | `026_drop_mov_gasto_id.sql` | 27 | S |  | ALTER TABLE, DROP |  · MOVIMIENTOS_BANCARIOS |
| 34 | `027_mov_concepto_corregido.sql` | 13 | S |  | ALTER TABLE |  · MOVIMIENTOS_BANCARIOS |
| 35 | `028_gasto_condiciones_pago.sql` | 11 | S |  | ALTER TABLE |  · GASTOS |
| 36 | `029_limpieza_roster_ia.sql` | 33 | S |  | DROP | — |
| 37 | `029_mensajes_editar_borrar.sql` | 4 | S |  | ALTER TABLE |  · MENSAJES |
| 38 | `030_consulta_viva_endpoints.sql` | 30 | S |  | CREATE TABLE, INDEX, ALTER TABLE | RECOMENDACIONES_PACIENTE · TRATAMIENTOS |
| 39 | `030_tto_coste_laboratorio.sql` | 12 | S |  | ALTER TABLE |  · TRATAMIENTOS_REALIZADOS |
| 40 | `031_agente_revisiones_agente_id.sql` | 19 | S |  | INDEX, ALTER TABLE |  · AGENTE_REVISIONES |
| 41 | `032_tratamiento_consentimiento_tipo.sql` | 15 | S |  | INDEX, ALTER TABLE |  · PUBLIC.TRATAMIENTOS |
| 42 | `033_colaborador_talonario_id.sql` | 5 | S |  | INDEX, ALTER TABLE |  · COLABORADORES |
| 43 | `034_conversaciones_pin_direccion.sql` | 13 | S | D | ALTER TABLE, UPDATE |  · CONVERSACIONES |
| 44 | `035_conversaciones_urgente_manual.sql` | 4 | S |  | ALTER TABLE |  · CONVERSACIONES |
| 45 | `036_consentimientos_signing_code_seguridad.sql` | 9 | S |  | ALTER TABLE |  · CONSENTIMIENTOS |
| 46 | `037_receta_urgencia_desabastecimiento.sql` | 6 | S |  | ALTER TABLE |  · RECETAS |
| 47 | `038_geo_catalogo_oficial.sql` | 22599 | S | D | CREATE TABLE, INDEX, INSERT, UPDATE, SEQUENCE | CODIGOS_POSTALES_GEO, MUNICIPIOS, PAISES |
| 48 | `039_cita_id_cita_fechas.sql` | 45 | S | D | ALTER TABLE, UPDATE, SEQUENCE |  · CITAS |
| 49 | `040_formas_pago.sql` | 87 | S | D | CREATE TABLE, INDEX, ALTER TABLE, INSERT, UPDATE | FORMAS_PAGO · PAGOS |
| 50 | `041_pagos_sin_forma_texto.sql` | 16 | S |  | ALTER TABLE, DROP |  · PAGOS |
| 51 | `042_cobros_legacy_fuera_de_realizados.sql` | 51 | S | D | CREATE TABLE, INSERT, UPDATE, DELETE | PRESUPUESTO_LINEAS_ORIGEN_BK_042, TRATAMIENTOS_REALIZADOS_BK_042, TRATAMIENTOS_REALIZADOS_FASES_BK_042 |
| 52 | `043_cobros_legacy_a_eurodent.sql` | 20 |  | D | UPDATE, DELETE | — |
| 53 | `044_notas_gelite_como_revision.sql` | 36 | S | D | CREATE TABLE, INSERT | TRATAMIENTOS_REALIZADOS_IDS_044 |
| 54 | `045_colaboradores_id_gelite.sql` | 23 | S | D | INDEX, ALTER TABLE, UPDATE |  · COLABORADORES |
| 55 | `046_colaboradores_que_faltaban.sql` | 32 | S | D | INSERT, SEQUENCE | — |
| 56 | `046_doctores_equivalencia_y_correccion.sql` | 69 | S | D | CREATE TABLE, INSERT, UPDATE, SEQUENCE | TRATAMIENTOS_REALIZADOS_COLAB_BK_046 |
| 57 | `047_gelite_equivalencias.sql` | 36 | S | D | CREATE TABLE, INDEX, INSERT, DROP | GELITE_EQUIVALENCIAS |
| 58 | `048_equivalencias_solo_en_una.sql` | 18 |  | D | INSERT | — |
| 59 | `049_equivalencias_colaboradores_reales.sql` | 32 |  | D | INSERT, DELETE | — |
| 60 | `050_notas_044_marcar_dudosas.sql` | 42 | S | D | ALTER TABLE, UPDATE |  · TRATAMIENTOS_REALIZADOS_IDS_044 |
| 61 | `051_ttosmed_39487.sql` | 77 | S | D | CREATE TABLE, INSERT, UPDATE | TRATAMIENTOS_REALIZADOS_BK_051 |
| 62 | `052_procedencia_realizados.sql` | 37 | S | D | ALTER TABLE, UPDATE |  · TRATAMIENTOS_REALIZADOS |
| 63 | `053_idcol6_a_lucia.sql` | 37 | S | D | CREATE TABLE, INSERT, UPDATE | TRATAMIENTOS_REALIZADOS_COLAB_BK_053 |
| 64 | `054_corregir_053.sql` | 20 |  | D | UPDATE | — |
| 65 | `055_sacar_notas_de_realizados.sql` | 33 | S | D | CREATE TABLE, DELETE | NOTAS_GELITE_SIN_TRATAMIENTO |
| 66 | `056_devolver_1271_sacar_111.sql` | 36 | S | D | INSERT, DELETE, SEQUENCE | — |
| 67 | `057_borrar_991_cobros_legacy.sql` | 21 |  | D | DELETE | — |
| 68 | `058_cobros_y_devoluciones_a_pagos.sql` | 25 | S | D | ALTER TABLE, INSERT |  · PAGOS |
| 69 | `059_descuentos_a_favor_paciente.sql` | 13 |  | D | INSERT | — |
| 70 | `059_descuentos_como_devoluciones.sql` | 14 |  | D | INSERT | — |
| 71 | `060_resto3_a_favor_paciente.sql` | 12 |  | D | INSERT | — |
| 72 | `061_pagos_origen_ident.sql` | 22 |  | D | UPDATE | — |
| 73 | `062_pagos_sin_ttosmed.sql` | 25 |  | D | UPDATE | — |
| 74 | `063_pagos_origen_pagocli.sql` | 15 |  | D | UPDATE | — |
| 75 | `064_vaciar_pagos.sql` | 10 |  | D | DELETE | — |
| 76 | `065_los991_a_pagos.sql` | 17 |  | D | INSERT | — |
| 77 | `066_los991_procedencia_real.sql` | 17 |  | D | UPDATE | — |
| 78 | `067_equivalencias_pagos.sql` | 13 |  | D | INSERT | — |
| 79 | `068_pagos_gelite_pagocli.sql` | 38 |  | D | INSERT | — |
| 80 | `069_equivalencias_sin_pagos.sql` | 10 |  | D | DELETE | — |
| 81 | `070_pagos_negativos_regularizacion.sql` | 19 |  | D | INSERT | — |
| 82 | `071_formas_desde_sep2019_a_efectivo.sql` | 10 |  | D | UPDATE | — |
| 83 | `072_pago_tratamiento.sql` | 42 | S | D | CREATE TABLE, INDEX, INSERT | PAGO_TRATAMIENTO |
| 84 | `073_laboratorio_trabajos.sql` | 29 | S |  | CREATE TABLE, INDEX, ALTER TABLE | LABORATORIO_TRABAJOS · TARIFA_PRECIOS |
| 85 | `074_quitar_coste_lab_antiguo.sql` | 16 | S |  | ALTER TABLE, DROP |  · TARIFA_PRECIOS, TRATAMIENTOS |
| 86 | `075_lista_precios_hexa3dental.sql` | 29 |  | D | INSERT, UPDATE | — |
| 87 | `076_tarifa_precio_trabajos.sql` | 31 | S | D | CREATE TABLE, INDEX, INSERT | TARIFA_PRECIO_TRABAJOS |
| 88 | `077_quitar_laboratorio_trabajo_id.sql` | 12 | S |  | ALTER TABLE, DROP |  · TARIFA_PRECIOS |
| 89 | `078_lab_coronas_provisionales.sql` | 19 |  | D | INSERT | — |
| 90 | `079_lab_provisionales_corregido.sql` | 30 |  | D | INSERT, DELETE | — |
| 91 | `080_quitar_tratamiento_realizado_origen.sql` | 7 | S |  | ALTER TABLE, DROP |  · PRESUPUESTO_LINEAS |
| 92 | `081_estados_linea_presupuesto.sql` | 33 | S | D | CREATE TABLE, INDEX, ALTER TABLE, INSERT | ESTADOS_LINEA_PRESUPUESTO · PRESUPUESTO_LINEAS |
| 93 | `082_estado_linea_a_estados_tratamiento.sql` | 28 | S | D | ALTER TABLE, UPDATE, DROP |  · PRESUPUESTO_LINEAS |
| 94 | `083_enlazar_realizados_y_estados_presupuesto.sql` | 42 |  | D | UPDATE | — |
| 95 | `084_ortodoncia_24_meses.sql` | 31 |  | D | UPDATE | — |
| 96 | `085_implantes_9_meses.sql` | 33 |  | D | UPDATE | — |
| 97 | `086_lineas_de_presupuestos_caducados.sql` | 9 |  | D | UPDATE | — |
| 98 | `087_equivalencias_pacientes.sql` | 15 |  | D | INSERT, UPDATE, DELETE | — |
| 99 | `088_id_cita_unico.sql` | 26 | S | D | INDEX, INSERT, DELETE, SEQUENCE | — |
| 100 | `089_financiacion_completa.sql` | 44 | S | D | CREATE TABLE, INDEX, ALTER TABLE, INSERT | FINANCIERAS · FINANCIERAS, PAGOS |
| 101 | `090_saldo_paciente.sql` | 126 | S | D | CREATE TABLE, INDEX, INSERT, UPDATE | SALDO_PACIENTE |
| 102 | `091_rectificativas_pacientes.sql` | 28 | S | D | INDEX, ALTER TABLE, UPDATE |  · DOCUMENTOS_PACIENTE, TRATAMIENTOS_REALIZADOS |
| 103 | `092_motivo_devolucion_pagos.sql` | 3 | S |  | ALTER TABLE |  · PAGOS |
| 104 | `093_registro_migraciones.sql` | 30 | S |  | CREATE TABLE | MIGRACIONES_APLICADAS |
| 105 | `094_completar_incompletas.sql` | 52 | S |  | INDEX, ALTER TABLE |  · TARIFA_PRECIOS |
| 106 | `095_gastos_sin_duplicados_motor.sql` | 64 | S | D | CREATE TABLE, INDEX, INSERT, UPDATE, DELETE | _BAK_095_GASTOS_DUPLICADOS, _BAK_095_GASTOS_REASIGNADOS |
| 107 | `096_permisos_denegados_por_rol.sql` | 37 | S | D | CREATE TABLE, INDEX, INSERT | USER_CENTER_PERMISOS_DENEGADOS |
| 108 | `097_permisos_por_pestana.sql` | 55 |  | D | INSERT | — |
| 109 | `098_permisos_por_seccion.sql` | 67 |  | D | INSERT | — |
| 110 | `099_informe_contable.sql` | 24 | S |  | VIEW | — |
| 111 | `100_informe_gastos.sql` | 17 | S |  | VIEW | — |
| 112 | `101_informe_juan_antonio.sql` | 26 | S |  | VIEW | — |
| 113 | `102_corrige_concepto_4577.sql` | 5 |  | D | UPDATE | — |
| 114 | `103_vista_juan_antonio_concepto_corregido.sql` | 27 | S |  | VIEW | — |
| 115 | `104_garaje_efectivo_60.sql` | 4 |  | D | UPDATE | — |
| 116 | `105_reembolsos_juan_sin_irpf.sql` | 15 |  | D | UPDATE | — |
| 117 | `106_reembolsos_juan_sin_irpf_2.sql` | 18 |  | D | UPDATE | — |
| 118 | `107_comision_financieras.sql` | 42 | S | D | VIEW, INSERT | — |
| 119 | `108_financiacion_neto_como_pago.sql` | 27 | S | D | VIEW, DELETE | — |
| 120 | `109_financiacion_datos_en_pago.sql` | 134 |  | D | INSERT, UPDATE | — |
| 121 | `110_devolucion_efectivo_llarena.sql` | 11 |  | D | INSERT | — |
| 122 | `111_reclasifica_efectivo_a_financiacion.sql` | 16 |  | D | UPDATE | — |
| 123 | `112_elimina_pago_prueba_juan_antonio.sql` | 3 |  | D | DELETE | — |
| 124 | `113_importa_pagos_gelite_21oct.sql` | 36 |  | D | INSERT | — |
| 125 | `114_hora_real_mensajes_whatsapp.sql` | 87 |  | D | UPDATE | — |
| 126 | `platform_001_centros.sql` | 18 | S |  | CREATE TABLE, INDEX | PLATFORM_CENTROS |
---

## 7. Clasificación del dato: clínico vs fiscal vs operativo

### 7.1 Datos clínicos (RGPD / PII — categoría especial)

| Qué | Tablas / campos | Evidencia |
|---|---|---|
| Identidad y contacto del paciente | `pacientes` (nombre, apellidos, NIF, nacimiento, dirección, teléfonos, email, foto) | `domain/models/core.py:163-183` |
| Historia clínica | `alergias`, `diagnosticos`, `soap`, `vademecum`/`medic_preescrita`, `plan_proxima_cita`, `alertas_paciente` | `domain/models/clinico.py:28-243` |
| Odontograma/periodontograma | `odontograma_entradas`, `periodontograma_medidas` | `domain/models/dental.py:17-60` |
| Documentos clínicos | `recetas`+`receta_lineas`, `consentimientos`, `documentos_paciente`, `recomendaciones_paciente`, `documentos_firmados` | `domain/models/documentos.py:45-199` |
| Imagenología | `imagenes_rx`, `hallazgos_imagen`, `anotaciones_imagen`, `analisis_cefalo`, `cefalometrias`, `analisis_dentia`, `estudios_ortodoncia`, `fotos_ortodoncia` + ficheros de `backend/media/pacientes/**` | `domain/models/clinico.py:111-243`, `ortodoncia.py:48-88`, `multimedia_service.py:8-46` |
| Comunicación con el paciente | `conversaciones`, `mensajes`, `llamadas_voz`, `envios_email` | `domain/models/comunicacion.py:17-216` |
| Identidad de acceso del paciente | `paciente_otps`, dispositivos | `core.py:196-207`, `core.py:481-488` |

**Reglas del proyecto aplicables** (`Archivos MD/CLAUDE.md:31-35`, R4):
- Datos clínicos = RGPD/PII: cifrado en reposo, **no reproducir PII en informes** ni en documentos
  de trabajo (esta spec no contiene PII).
- GELITE (sistema anterior) = **solo lectura (SELECT)**. Las migraciones `042`–`057`, `061`–`071`,
  `087`, `113` importan/corrigen datos de GELITE: son decisiones de negocio irreversibles
  documentadas en SQL, no un ETL repetible.
- En `tratamientos_realizados` no hay líneas de pago/cobro (R4).

### 7.2 Datos fiscales / económicos (obligación de conservación)

| Qué | Tablas / campos | Evidencia |
|---|---|---|
| Facturación emitida | `clientes`, `presupuestos`, `presupuesto_lineas`, `facturas_historico`, `documentos_admin` (factura), `documentos_firmados` | `economico.py:22-120`, `:132-188`, `:386-404`; `documentos.py:123-170` |
| Cobros/pagos | `pagos`, `deudas`/`deuda_pago`, `liquidaciones`/`liquidacion_lineas`, `movimientos_bancarios`, `formas_pago`, `financieras` | `economico.py:227-284`; `gestoria.py:83-139`, `:163-195` |
| Gastos y proveedores | `gastos`, `gasto_incidencias`, `proveedores`, `facturas_gestor`, `proveedores_gestor`, `revisiones_gestor`, `descartes_gestor`, `pasadas_gestor` | `gestoria.py:18-80`; `gestor_ia.py:20-186` |
| Fiscalidad | `modelos_fiscales`, `razones_sociales` (CIF, serie, IBAN, sello), `facturas_gestor` (IVA desglosado, IRPF), VERI\*FACTU (`hash_factura`, `codigo_qr`, huella) | `gestoria.py:197-208`; `core.py:97-110`; `economico.py:132-188`; `domain/services/verifactu.py` |
| Conciliación bancaria | `movimientos_bancarios.estado_concil`, `extractos_subidos`, `conciliacion_service` | `gestoria.py:141-195`; `application/services/conciliacion_service.py` |
| Producción/liquidación de doctores | `tratamientos_realizados` (importes, `pct_produccion`), `liquidaciones`, `colaboradores.pct_produccion/irpf_pct` | `economico.py:297-338`; `gestoria.py:83-109`; `core.py:244-257` |

**Invariante fiscal:** los importes son `Decimal`/`NUMERIC`, no float (en modelos:
`Optional[Decimal]`, p. ej. `economico.py:297-338`). VERI\*FACTU fija 2 decimales y hash en
mayúsculas (`domain/services/verifactu.py:53`, `:78`). **Cualquier cambio de redondeo rompe la
huella y la validez ante la AEAT.**

### 7.3 Datos operativos (no clínicos ni fiscales)

`centros`, `centro_asociaciones`, `agenda*`, `gabinetes`, `tipos_cita`, `estados_cita`,
`colaborador_horario`, `bloqueos_agenda`, `configuraciones`, `integraciones`, `agentes*`,
`capacidades_catalogo`, `permisos`/`roles`, `auditoria`, `informes`, `almacen`/`stock_movimientos`,
geo (`paises`/`poblaciones`/`provincias`/`municipios`/`codigos_postales*`), `agente_revisiones`,
`envios_automaticos`.

### 7.4 Tabla resumen (para decidir en el corte)

| Criterio | Clínico | Fiscal | Operativo |
|---|---|---|---|
| ¿Se puede regenerar? | **No** (historia clínica) | **No** (obligación legal) | Parcialmente (catálogos) |
| ¿Se puede migrar con ETL transformador? | Solo con validación clínica | Solo con validación fiscal | Sí |
| ¿Borrado permitido? | No (RGPD: conservación/anonimización) | No (plazos legales) | Sí, con criterio |
| ¿Cifrado en reposo exigido? | Sí | Sí | Configurable |
| ¿Exportable a Vercel? | **Nunca** (backend Oracle) | **Nunca** | Config no sensible |

---

## 8. Qué NO puede cambiar en el corte (contrato de datos)

1. **Identificadores**: `pacientes.id`, `num_historia` (por centro), `citas.id`/`id_cita`,
   `presupuestos.num_pre`/`serie`, `facturas`/`num_factura`, `tratamientos_realizados.num_tto`,
   `gastos.numero_factura`, `documentos.*.id`. Cambiarlos rompe enlaces, PDFs, contabilidad y
   apps móviles. Evidencia de su uso: `core.py:166`, `:341-368`; `economico.py:132-188`.
2. **Semántica de estados numéricos**: `estados_tratamiento` (1/3/5/7/8, ver §4.6),
   `estados_presupuesto`, `presupuestos.estado_id`, `citas.estado_id` resuelto por **código**
   semántico, nunca por id hardcodeado salvo el 5 ya citado
   (`application/services/disponibilidad_service.py:25-40`).
3. **VERI\*FACTU**: huella encadenada, QR y formato (algoritmo en `domain/services/verifactu.py`,
   tests con ejemplos AEAT en `tests/test_verifactu.py`).
4. **Importes y redondeo** con `Decimal`/2 decimales fiscales; `pagos.importe`/`neto` con el
   significado corregido por las migraciones 058–070 (`pagos` es la fuente de cobros).
5. **Series y numeración fiscal** de `razones_sociales` (`serie`, `iban`, `cif`) y de
   `presupuestos.num_serie`/`facturas_historico.num_factura`: no renumerar.
6. **Jerarquía de configuración** (`configuraciones.clave` + `centro_id/sistema/usuario_id`) y la
   forma JSON de las claves listadas en §4.12: el frontend y el motor de agentes dependen de ella.
7. **`estado_flujo` de WhatsApp** (`conversaciones.estado_flujo`): es la máquina de estados; si se
   pierde o se transforma, los pacientes que están a mitad de un flujo reciben mensajes erróneos
   (`domain/services/whatsapp_flujos.py`, `tests/test_whatsapp_flujos.py`).
8. **`signing_code`** de consentimientos y su expiración: cambia el contrato del enlace de firma.
9. **`auditoria`**: no borrar ni reescribir; el freno de login y CENTINELA dependen de ella.
10. **Relación tabla↔fichero**: `pacientes.num_historia` ↔ carpeta `backend/media/pacientes/`
    (nombrada con num_historia y apellidos/nombre, `multimedia_service.py:8-13`). Si se migra la
    BD a Oracle y los ficheros a otro almacenamiento, **el mapeo debe resolverse sin renombrar**
    (o migrando ficheros y BD de forma atómica).
11. **Bases separadas**: la operativa y la de plataforma (`platform_db.py:1-47`) no se pueden
    fusionar sin cambiar el contrato de SuperUser/tenant.

---

## 9. Riesgos de datos para Vercel + Oracle Cloud (y cómo mitigarlos)

| # | Riesgo | Evidencia | Mitigación |
|---|---|---|---|
| 1 | El esquema de producción **no es reproducible** desde el repo: `create_all` + 126 SQL aplicadas a mano | `db.py:13-21`; §2.1 | Volcar `pg_dump --schema-only` de producción como baseline y versionarlo en el rebuild; comparar con los modelos (§10.2). |
| 2 | 40 migraciones de **solo datos** (normalizaciones, equivalentes GELITE, vaciados de `pagos`) son irreversibles y no están en los modelos | §6 (`S=`, `D=`) | No re-ejecutarlas: migrar la BD tal cual. Tratar el baseline de datos como artefacto de despliegue, no como seed. |
| 3 | `ondelete` real desconocido (los modelos no lo declaran) | §3.2 punto 3 | Revisar `pg_constraint` en producción; restaurar FKs en Oracle con el mismo `ondelete`. |
| 4 | Vistas SQL (`informe_contable`, `informe_gastos`, `informe_juan_antonio`) son código SQL en migraciones, no en Python | migraciones `099`, `100`, `101`/`103`, `107`/`108` | Portarlas como migraciones del rebuild y comparar resultados numéricos contra producción (son la fuente del Gestor IA). |
| 5 | Catálogo geográfico de **22.599 líneas** (`038_geo_catalogo_oficial.sql`) | migración 038 | Copiar tal cual; no regenerar (los ids referencian `poblacion_id` de pacientes/centros). |
| 6 | `backend/media` = 1,2 GB con PII; Vercel no puede servirlo | `docs/rebuild/BASELINE.md:48-49`; `multimedia_service.py:29` | Mantener `/media` autenticado en Oracle/objeto; prohibido mover a `public/` o CDN público. Ver `PARIDAD-FLUJOS.md` §2. |
| 7 | Cifrado en reposo: el proyecto lo exige (R4) pero **no se ha verificado** el mecanismo real en producción (¿cifrado de disco? ¿columnas?) | `Archivos MD/CLAUDE.md:35` | **NO VERIFICADO**; verificar con el propietario antes de mover datos entre nubes (RGPD). |
| 8 | Shell SQL asume Postgres (`psql`, `pg_dump`, `pg_advisory_lock`, `information_schema`) | `scripts/migra.sh`, `infrastructure/scheduler.py:33-58` | Oracle Cloud puede ser PostgreSQL gestionado (compatible) o no; si no es Postgres, **el rebuild necesita reescribir migraciones, scheduler y vistas**. Decisión de arquitectura pendiente. |

---

## 10. Cómo verificar la paridad de datos (procedimiento)

### 10.1 Checks estáticos (ya hechos, reproducibles)

- Recuento de tablas/FK/columnas desde SQLModel: descrito en §1. Repetible con un script `ast`
  sobre `backend/domain/models/`.
- Recuento y clasificación de las 126 migraciones: §6 (regex sobre `CREATE/ALTER/INSERT/UPDATE/…`).
- Coherencia modelo↔migración: buscar en `backend/migrations/` cualquier tabla/columna que no
  exista como modelo (o al revés). **Pendiente de automatizar** en el rebuild.

### 10.2 Check contra la BD real (NO ejecutado aquí; requiere el entorno con Postgres)

Cuando el lead prepare un entorno con la BD accesible:

```sql
-- 1) Tablas y columnas reales
SELECT table_name, column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position;

-- 2) Claves foráneas y reglas de borrado
SELECT tc.constraint_name, tc.table_name, kcu.column_name,
       ccu.table_name AS foreign_table, rc.delete_rule
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name
JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
JOIN information_schema.referential_constraints rc ON rc.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY';

-- 3) Índices y unicidades
SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = 'public';

-- 4) Vistas (las 3 del informe)
SELECT table_name FROM information_schema.views WHERE table_schema = 'public';

-- 5) Migraciones anotadas vs ficheros
SELECT nombre, aplicada_en, origen FROM migraciones_aplicadas ORDER BY nombre;
```

Criterio de aceptación de paridad de datos: el esquema volcado del rebuild debe coincidir en
**tablas, columnas, tipos, nullables, FKs, delete_rule, índices y vistas** con el de producción;
las migraciones anotadas deben cubrir todos los ficheros (usar
`backend/scripts/migraciones_estado.py` o `scripts/migraciones_estado.py`).
