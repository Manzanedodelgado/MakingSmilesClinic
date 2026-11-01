# ADR-000 · Estrategia de reconstrucción: módulos con paridad y corte progresivo

- **Estado:** aceptada
- **Fecha:** 2026-11-01
- **Decisor:** propietario del proyecto
- **Rama:** `rebuild/vercel-oracle` (base `master` a76ee81)

## Contexto

La web clínica está en producción con un despliegue híbrido (Next.js por `systemd`,
backend y servicios por Docker Compose, Caddy fuera de ese flujo). Las auditorías del
2026-11-01 midieron el estado real:

- **376 ficheros eliminables** (clases S+P+X, ~54,7 MB) con evidencia de que la web no
  cambia: `tsc --noEmit` sin errores y `next build` exit 0. Ojo: el chequeo de rutas de esa
  auditoría («48 rutas iguales») midió `len(app.routes)`, que en FastAPI 0.162 son
  `_IncludedRouter` y no rutas; la superficie real es **432 rutas / ~498 operaciones** y
  ese chequeo no prueba por sí solo que no se perdieran rutas (corregido en BASELINE.md).
- **542 parches detectados en 160 ficheros**: 16 declarados con `raiz:`, 52 «probables
  válidos» y 271 sin trazar en gravedad alta+media.
- Deuda de acumulación, no de arquitectura: Clean Architecture en backend y
  Feature-First en frontend se sostienen.

El propietario ha decidido reescribir el código para que corra limpio en Vercel
(frontend) y Oracle (API y servicios), sin código muerto y con los parches válidos
integrados.

## Decisión

1. **Reconstruir por módulos, no en big-bang.** Cada módulo se escribe de nuevo contra
   una especificación de paridad (`docs/rebuild/PARIDAD-*.md`) y se corta a producción
   solo cuando su paridad está demostrada.
2. **El legacy es el oráculo y la red de seguridad.** Permanece en producción y sirve de
   referencia mientras el módulo nuevo no demuestre equivalencia. No se borra el legacy
   de `master`; se sustituye en la rama de reconstrucción.
3. **Contrato de API estable.** Las apps móviles (`doctor-ios`, `doctor-android`) y los
   clientes actuales consumen la API: rutas, códigos y semántica se preservan; cualquier
   cambio de contrato exige versión nueva y migración de clientes.
4. **La capa de despliegue se escribe de cero** (Vercel + Oracle), y con ella la
   integración que cambia de forma: media con URL firmada, SSE con token firmado de corta vida
   reutilizable, análisis de IA asíncrono, CSP/CORP.
5. **Los parches no se arrastran.** Un parche entra al código nuevo solo si su motivo
   sigue vigente; si es una decisión de negocio, se implementa de forma explícita en la
   capa propietaria; si tapa un fallo, se corrige la causa.

## Consecuencias

- No hay ventana de riesgo global: el sistema actual sigue sirviendo la clínica.
- El coste es mayor en tiempo (reconstruir + demostrar paridad) que un cambio in situ,
  pero el riesgo de regresión clínica o fiscal se acota por módulo.
- La paridad se demuestra con pruebas, no con opinión: se reutilizan `backend/tests` y
  `frontend/e2e` como especificación ejecutable y se amplían donde falten.
- Un módulo legacy se considera retirado solo cuando su sustituto pasa paridad y su
  código antiguo deja de ser alcanzable (se borra; no queda «por si acaso»).
- Reconstruir obliga a fijar por escrito reglas hoy implícitas: si una regla no se puede
  documentar con evidencia, no se inventa, se marca como bloqueo.

## Alternativas descartadas

- **Big-bang** (sistema nuevo completo y un único corte): un fallo afecta a toda la
  clínica a la vez y no hay paridad demostrada antes del corte.
- **Parchear el legacy en su sitio**: no cumple el objetivo (código muerto y parches) y
  contradice `patches-to-core`.
- **Reescribir solo la capa de despliegue conservando el dominio**: descartada por el
  propietario; se conserva como referencia de lo que sí se reescribe primero.
