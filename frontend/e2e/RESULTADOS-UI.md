# Resultados de prueba funcional de la UI

Siguiendo `docs/INVENTARIO-UI.md`. App real (100.86.41.61) · Test Admin (SUPERADMIN) · paciente 4134.
5/9/2026, 19:54:05

Cada acción guarda captura `antes`/`después` en `e2e/pruebas-ui/`.
**Leyenda:** ✅ efecto claro · ➡️ navega · 🪟 abre panel · 🔄 llama API · ⚠️ sin cambio visible · 🔲 no encontrado · ❌ error

---

## 1. `/login`

- ⚠️ **Icono ojo (ver/ocultar contraseña)** — clic aceptado, sin cambio visible  · [antes](pruebas-ui/001_login-ojo_antes.png) · [después](pruebas-ui/001_login-ojo_despues.png)
- ⚠️ **Icono ojo — 2º clic (vuelve a ocultar)** — clic aceptado, sin cambio visible  · [antes](pruebas-ui/002_login-ojo2_antes.png) · [después](pruebas-ui/002_login-ojo2_despues.png)
- ⚠️ **Checkbox "Recordar usuario"** — clic aceptado, sin cambio visible  · [antes](pruebas-ui/003_login-recordar_antes.png) · [después](pruebas-ui/003_login-recordar_despues.png)
- **Enlace "¿Olvidaste tu contraseña?"** — ➡️ `/recuperar`  · [antes](pruebas-ui/004_login-olvido_antes.png) · [después](pruebas-ui/004_login-olvido_despues.png)
- ⚠️ **Botón "Acceder" sin credenciales** — clic aceptado, sin cambio visible  · [antes](pruebas-ui/005_login-acceder-vacio_antes.png) · [después](pruebas-ui/005_login-acceder-vacio_despues.png)

## 2. `/recuperar`

- ⚠️ **Botón "Enviar enlace" sin email** — clic aceptado, sin cambio visible  · [antes](pruebas-ui/006_recuperar-vacio_antes.png) · [después](pruebas-ui/006_recuperar-vacio_despues.png)
- **Botón "Enviar enlace" con email** — 🔄 `POST /api/auth/forgot`  · [antes](pruebas-ui/007_recuperar-envio_antes.png) · [después](pruebas-ui/007_recuperar-envio_despues.png)
- **Enlace "← Volver al acceso"** — ➡️ `/login`  · [antes](pruebas-ui/008_recuperar-volver_antes.png) · [después](pruebas-ui/008_recuperar-volver_despues.png)

## 3. `/restablecer` (sin token)

- **Enlace "Solicitar uno nuevo"** — ➡️ `/recuperar`  · [antes](pruebas-ui/009_restablecer-solicitar_antes.png) · [después](pruebas-ui/009_restablecer-solicitar_despues.png)

_(parte A1 escrita — 9 elementos)_

_(login OK → `/agenda`)_


## 0. Chrome — rail lateral

- ⚠️ **Rail → "Inicio"** — clic aceptado, sin cambio visible  · [antes](pruebas-ui/001_rail-inicio_antes.png) · [después](pruebas-ui/001_rail-inicio_despues.png)
- **Rail → "Agenda"** — ➡️ `/agenda`  · [antes](pruebas-ui/002_rail-agenda_antes.png) · [después](pruebas-ui/002_rail-agenda_despues.png)
- **Rail → "Pacientes"** — ➡️ `/pacientes`  · [antes](pruebas-ui/003_rail-pacientes_antes.png) · [después](pruebas-ui/003_rail-pacientes_despues.png)
- **Rail → "WhatsApp"** — ➡️ `/comunicacion`  · [antes](pruebas-ui/004_rail-whatsapp_antes.png) · [después](pruebas-ui/004_rail-whatsapp_despues.png)
- **Rail → "Gestoría"** — ➡️ `/gestoria/facturacion`  · [antes](pruebas-ui/005_rail-gestoria_antes.png) · [después](pruebas-ui/005_rail-gestoria_despues.png)
- **Rail → "Informes"** — ➡️ `/informes`  · [antes](pruebas-ui/006_rail-informes_antes.png) · [después](pruebas-ui/006_rail-informes_despues.png)
- **Rail → "Config"** — ➡️ `/configuracion/clinica/centro`  · [antes](pruebas-ui/007_rail-config_antes.png) · [después](pruebas-ui/007_rail-config_despues.png)
- **Rail → "SuperUser"** — ➡️ `/superuser`  · [antes](pruebas-ui/008_rail-superuser_antes.png) · [después](pruebas-ui/008_rail-superuser_despues.png)

## 0. Chrome — barra superior

- ⚠️ **Logo "gota" (esquina sup. izq.)** — clic aceptado, sin cambio visible  · [antes](pruebas-ui/009_top-logo_antes.png) · [después](pruebas-ui/009_top-logo_despues.png)
- ⚠️ **Chip "SUPERADMINISTRADOR"** — clic aceptado, sin cambio visible  · [antes](pruebas-ui/010_top-rol_antes.png) · [después](pruebas-ui/010_top-rol_despues.png)
- ⚠️ **"Test Admin"** — clic aceptado, sin cambio visible  · [antes](pruebas-ui/011_top-user_antes.png) · [después](pruebas-ui/011_top-user_despues.png)

_(parte A2 escrita — 11 elementos)_

## 4. `/inicio` — Panel

- **SISTEMAS · "WhatsApp"** — ➡️ `/comunicacion`  · [antes](pruebas-ui/001_inicio-sist-whatsapp_antes.png) · [después](pruebas-ui/001_inicio-sist-whatsapp_despues.png)
- **SISTEMAS · "Alex"** — ➡️ `/configuracion/ias/alex`  · [antes](pruebas-ui/002_inicio-sist-alex_antes.png) · [después](pruebas-ui/002_inicio-sist-alex_despues.png)
- **SISTEMAS · "Victor"** — ➡️ `/configuracion/ias/victor`  · [antes](pruebas-ui/003_inicio-sist-victor_antes.png) · [después](pruebas-ui/003_inicio-sist-victor_despues.png)
- **SISTEMAS · "Aura"** — ➡️ `/configuracion/ias/aura`  · [antes](pruebas-ui/004_inicio-sist-aura_antes.png) · [después](pruebas-ui/004_inicio-sist-aura_despues.png)
- **SISTEMAS · "Centinela"** — ➡️ `/configuracion/ias/centinela`  · [antes](pruebas-ui/005_inicio-sist-centinela_antes.png) · [después](pruebas-ui/005_inicio-sist-centinela_despues.png)
- **SISTEMAS · "Buzón"** — ➡️ `/configuracion/ias/gestor`  · [antes](pruebas-ui/006_inicio-sist-buzon_antes.png) · [después](pruebas-ui/006_inicio-sist-buzon_despues.png)
- **SISTEMAS · "Drive"** — ➡️ `/configuracion/ias/gestor`  · [antes](pruebas-ui/007_inicio-sist-drive_antes.png) · [después](pruebas-ui/007_inicio-sist-drive_despues.png)
- **Tarjeta WHATSAPP SIN RESPONDER · 1ª fila** — ➡️ `/comunicacion`  · [antes](pruebas-ui/008_inicio-wa-fila_antes.png) · [después](pruebas-ui/008_inicio-wa-fila_despues.png)
- ⚠️ **Tarjeta PRESUPUESTOS SIN RESPUESTA · 1ª fila** — clic aceptado, sin cambio visible  · [antes](pruebas-ui/009_inicio-presu-fila_antes.png) · [después](pruebas-ui/009_inicio-presu-fila_despues.png)
- **Tarjeta IMPUESTOS Y PLAZOS · "Modelo 303"** — ➡️ `/gestoria/facturacion`  · [antes](pruebas-ui/010_inicio-imp-fila_antes.png) · [después](pruebas-ui/010_inicio-imp-fila_despues.png)
- 🔲 **Tarjeta FACTURAS Y BANCO** — no visible

_(parte B escrita — 11 elementos)_

## 5. `/agenda`

- ⚠️ **Selector "AGENDA 1" ▾** — ⚠️ cambio menor en pantalla  · [antes](pruebas-ui/001_agenda-selector_antes.png) · [después](pruebas-ui/001_agenda-selector_despues.png)
- **Flecha "‹" día anterior** — ✅ el contenido cambia (111 car.)  · [antes](pruebas-ui/002_agenda-prev_antes.png) · [después](pruebas-ui/002_agenda-prev_despues.png)
- **Flecha "›" día siguiente** — ✅ el contenido cambia (160 car.)  · [antes](pruebas-ui/003_agenda-next_antes.png) · [después](pruebas-ui/003_agenda-next_despues.png)
- ⚠️ **Botón "HOY"** — clic aceptado, sin cambio visible  · [antes](pruebas-ui/004_agenda-hoy_antes.png) · [después](pruebas-ui/004_agenda-hoy_despues.png)
- **Botón "SEMANA"** — ✅ el contenido cambia (2003 car.)  · [antes](pruebas-ui/005_agenda-semana_antes.png) · [después](pruebas-ui/005_agenda-semana_despues.png)
- ⚠️ **Botón "DÍA"** — clic aceptado, sin cambio visible  · [antes](pruebas-ui/006_agenda-dia_antes.png) · [después](pruebas-ui/006_agenda-dia_despues.png)
- ⚠️ **Botón "ANULADAS"** — clic aceptado, sin cambio visible  · [antes](pruebas-ui/007_agenda-anuladas_antes.png) · [después](pruebas-ui/007_agenda-anuladas_despues.png)
- ⚠️ **Desplegable "GABINETES" ▾** — ⚠️ cambio menor en pantalla  · [antes](pruebas-ui/008_agenda-gabinetes_antes.png) · [después](pruebas-ui/008_agenda-gabinetes_despues.png)
- **Desplegable "DOCTORES" ▾** — ✅ el contenido cambia (115 car.)  · [antes](pruebas-ui/009_agenda-doctores_antes.png) · [después](pruebas-ui/009_agenda-doctores_despues.png)
- **Botón "+ NUEVA CITA"** — ✅ el contenido cambia (76 car.)  · [antes](pruebas-ui/010_agenda-nueva-cita_antes.png) · [después](pruebas-ui/010_agenda-nueva-cita_despues.png)
- ⚠️ **Panel dcha · "WHATSAPP URGENTES" 1ª fila** — clic aceptado, sin cambio visible  · [antes](pruebas-ui/011_agenda-wa-urgente_antes.png) · [después](pruebas-ui/011_agenda-wa-urgente_despues.png)

## 6. `/pacientes` — lista

- ⚠️ **Cabecera-filtro "ALERTAS"** — clic aceptado, sin cambio visible  · [antes](pruebas-ui/012_pac-h-alertas_antes.png) · [después](pruebas-ui/012_pac-h-alertas_despues.png)
- ⚠️ **Cabecera-filtro "Edad"** — clic aceptado, sin cambio visible  · [antes](pruebas-ui/013_pac-h-edad_antes.png) · [después](pruebas-ui/013_pac-h-edad_despues.png)
- ⚠️ **Cabecera-filtro "Teléfono"** — clic aceptado, sin cambio visible  · [antes](pruebas-ui/014_pac-h-tel_antes.png) · [después](pruebas-ui/014_pac-h-tel_despues.png)
- ⚠️ **Cabecera-filtro "Tarifa"** — clic aceptado, sin cambio visible  · [antes](pruebas-ui/015_pac-h-tarifa_antes.png) · [después](pruebas-ui/015_pac-h-tarifa_despues.png)
- **Botón "+ NUEVO"** — ✅ el contenido cambia (579 car.)  · [antes](pruebas-ui/016_pac-nuevo_antes.png) · [después](pruebas-ui/016_pac-nuevo_despues.png)
- ❌ **Buscador "4134" → abrir paciente** — clic falló (locator.click: Timeout 3000ms exceeded.) · [antes](pruebas-ui/017_pac-buscar-abrir_antes.png)

## 7. `/comunicacion` — WhatsApp

- 🔲 **Botón "⏸ PAUSAR IA"** — no visible
- 🔲 **Botón "▶ REANUDAR IA" (tras pausar)** — no visible
- **Pestaña "No leídas"** — ✅ el contenido cambia (5753 car.)  · [antes](pruebas-ui/020_wa-tab-noleidas_antes.png) · [después](pruebas-ui/020_wa-tab-noleidas_despues.png)
- **Pestaña "Urgentes"** — ✅ el contenido cambia (2721 car.)  · [antes](pruebas-ui/021_wa-tab-urgentes_antes.png) · [después](pruebas-ui/021_wa-tab-urgentes_despues.png)
- **Pestaña "Todas"** — ✅ el contenido cambia (8474 car.)  · [antes](pruebas-ui/022_wa-tab-todas_antes.png) · [después](pruebas-ui/022_wa-tab-todas_despues.png)
- ⚠️ **1ª conversación de la lista** — clic aceptado, sin cambio visible  · [antes](pruebas-ui/023_wa-conv-1_antes.png) · [después](pruebas-ui/023_wa-conv-1_despues.png)

## 11. `/crm`

- **Pestaña "Reactivación"** — ✅ el contenido cambia (2868 car.)  · [antes](pruebas-ui/024_crm-reactivacion_antes.png) · [después](pruebas-ui/024_crm-reactivacion_despues.png)
- **Pestaña "Pipeline de presupuestos"** — ✅ el contenido cambia (134 car.)  · [antes](pruebas-ui/025_crm-pipeline_antes.png) · [después](pruebas-ui/025_crm-pipeline_despues.png)

## 12. `/iconos`

- ⚠️ **Icono ilustrado "diente"** — clic aceptado, sin cambio visible  · [antes](pruebas-ui/026_iconos-diente_antes.png) · [después](pruebas-ui/026_iconos-diente_despues.png)

## 13. `/superuser`

- 🔲 **Pestaña "CENTINELA"** — no visible
- 🔲 **Pestaña "APARIENCIA"** — no visible
- 🔲 **Pestaña "BASE DE DATOS"** — no visible
- 🔲 **Pestaña "CENTROS"** — no visible
- **Botón "+ NUEVO CENTRO"** — ✅ el contenido cambia (217 car.)  · [antes](pruebas-ui/031_su-nuevo-centro_antes.png) · [después](pruebas-ui/031_su-nuevo-centro_despues.png)
- **Fila "RUBIO GARCIA DENTAL"** — ✅ el contenido cambia (938 car.)  · [antes](pruebas-ui/032_su-fila-centro_antes.png) · [después](pruebas-ui/032_su-fila-centro_despues.png)

_(parte B2 escrita — 32 elementos)_

_(parte A escrita — 0 elementos)_

_(parte A escrita — 0 elementos)_

_(parte A escrita — 0 elementos)_
