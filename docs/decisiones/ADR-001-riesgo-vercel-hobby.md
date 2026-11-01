# ADR-001 · Riesgo aceptado: frontend en Vercel con plan Hobby

- **Estado:** aceptada con riesgo asumido por el propietario (2026-11-01)
- **Decisor:** propietario del proyecto
- **Ámbito:** despliegue del frontend en Vercel; no altera el backend ni la base de datos

## Contexto

El frontend (Next.js 15) se despliega en Vercel y el plan contratado es **Hobby**. La
aplicación procesa datos de salud de pacientes (categoría especial, art. 9 RGPD) y su uso
es comercial (clínica dental). Además, mientras exista el rewrite `/api/*`, Vercel
transporta peticiones y respuestas con datos clínicos, es decir, actúa como encargado del
tratamiento.

## Hechos verificados (2026-11-01, documentación oficial)

1. **Hobby no admite uso comercial.** «Hobby teams are restricted to non-commercial
   personal use only. All commercial usage of the platform requires either a Pro or
   Enterprise plan.»
   — <https://vercel.com/docs/limits/fair-use-guidelines#commercial-usage>
2. **El DPA solo cubre Pro y Enterprise.** «This Addendum applies to Vercel's Processing
   of Personal Data as a Processor under the Agreement for Customers who are on
   Enterprise and Pro plans.»
   — <https://vercel.com/legal/dpa>
3. **Límites de Hobby relevantes para este sistema**: 100 GB de transferencia, 10 GB de
   origin transfer, 100 despliegues/día, 300 s de función, una sola región, 1 h de logs;
   al excederlos, espera de 30 días.
   — <https://vercel.com/docs/plans/hobby> · <https://vercel.com/docs/limits>
4. **Cuerpo máximo por petición en funciones: 4,5 MB.**
   — <https://vercel.com/docs/functions/limitations#request-body-size>
5. **Timeout de petición proxeada a origen externo: 120 s** (`ROUTER_EXTERNAL_TARGET_ERROR`).
   — <https://vercel.com/docs/limits#proxied-request-timeout>
6. **Región de funciones en Hobby: una.** `fra1` está disponible.
   — <https://vercel.com/docs/functions/configuring-functions/region#limits>
7. **Instant Rollback en Hobby solo permite volver al despliegue inmediatamente anterior.**
   — <https://vercel.com/docs/instant-rollback>

## Decisión

Se usa **Vercel Hobby** para el frontend, con el riesgo legal y de plataforma **asumido
explícitamente por el propietario**, que fue informado de los puntos 1 y 2 (uso comercial
no permitido y ausencia de DPA para datos de salud) y aun así eligió continuar.

## Consecuencias y condiciones de contención

El riesgo que se asume es doble:

- **Cumplimiento:** no existe instrumento de encargado del tratamiento (art. 28 RGPD) con
  Vercel en Hobby, y el uso es comercial. El responsable del tratamiento es el propietario.
- **Plataforma:** incumplimiento de los términos de uso puede conllevar suspensión del
  servicio; los límites del punto 3 pueden cortar el servicio y el punto 7 limita el
  rollback.

Mitigaciones que el diseño aplica y que son condiciones para seguir en producción:

1. **Objetivo de contención: ningún dato clínico pasa por Vercel salvo las respuestas JSON
   del rewrite `/api/*`.** Consiste en servir `/media` (radiografías, consentimientos,
   facturas) con URL firmada directamente desde Oracle, y en conectar el SSE directo a Oracle
   con un token firmado de corta vida, **reutilizable durante su ventana** para no romper la
   reconexión nativa de `EventSource`.
   **Estado real a 2026-11-01: DISEÑADO, NO IMPLEMENTADO.** La API aún no emite firmas ni
   tokens, y el frontend sigue llamando a `/api/*` (que pasa por Vercel). Por tanto esta
   contención **no está en vigor** y es un bloqueo del corte a producción (registrado como
   D-2 en `INFRA.md`).
2. **Nada se cachea en Vercel:** las respuestas de `/api/*` van con `no-store`.
3. **Sin datos de salud en logs ni en despliegues de preview:** staging y previews usan
   datos sintéticos; nunca datos de pacientes reales. Es una condición de proceso: el
   repositorio no la garantiza, y por eso queda registrada como no verificada en `INFRA.md` §13.33.
4. **El timeout de 120 s del punto 5 es la razón por la que el análisis de IA (~30 s) pasa
   a asíncrono** (job + polling), y la de que `/media` no use el rewrite. Mientras la
   contención 1 no esté implementada, el rewrite de Vercel sigue sujeto a ese límite: una
   subida o descarga que tarde más de 120 s fallará por diseño de la plataforma.

## Cuándo se revisa esta decisión (bloqueantes antes del corte a producción)

- Antes del primer corte a producción con datos reales: se confirma si el propietario ha
  pasado a **Pro** (lo que resuelve 1 y 2) o si se mantiene Hobby con este riesgo escrito.
- **Bloqueante:** la contención 1 (media/SSE fuera de Vercel) debe estar implementada y
  verificada en navegador; hoy no lo está (D-2 en `INFRA.md`).
- Si el tráfico de datos clínicos a través de Vercel crece por encima de lo previsto (nuevos
  endpoints que devuelvan más datos), se revisa de nuevo el punto 1.
- Si se aproximan los límites del punto 3, hay aviso previo y plan de contención (media y
  SSE ya están fuera de Vercel, que es el mayor consumidor).

## Alternativas descartadas por ahora

- **Plan Pro (de pago; tarifa vigente en <https://vercel.com/pricing>):** resuelve el bloqueo
  legal (uso comercial permitido y DPA); no se descarta, queda como salida natural. No se
  afirma aquí una cifra concreta porque no se ha verificado contra la tarifa vigente.
- **Frontend servido también desde Oracle (Caddy):** elimina el problema de Vercel, pero
  pierde previews/CDN y contradice la decisión de producto.
