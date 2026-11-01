# MakingSmilesClinic

Reconstrucción limpia de **MakingSmiles_Studio** para producción, sin código muerto y con
los parches válidos integrados en la causa raíz. El sistema legado es referencia de
comportamiento (solo lectura) y **no se modifica**.

## Arquitectura objetivo

| Componente | Destino | Qué |
|---|---|---|
| Frontend | **Vercel** (Next.js, región `fra1`) | Toda la UI. Root Directory = `frontend/` |
| Backend API | **Oracle Cloud** (Always Free A1) tras Caddy | FastAPI, TLS, `/api/*` |
| Postgres 16 · Redis 7 · Evolution (WhatsApp) | **Oracle** (Docker) | Datos, pub/sub, WhatsApp |

Reglas de integración (ver `docs/decisiones/ADR-001` y `docs/rebuild/INFRA.md`):
- El navegador llama a `/api/*` del frontend y Next reescribe a `https://api.<dominio>`
  → cookie `access_token` **httpOnly first-party** (sin CORS de credenciales).
- `/media` (radiografías, consentimientos, facturas) y el SSE **NO pasan por Vercel**:
  media con **URL firmada HMAC de corta vida** y SSE con **token JWT de corta vida
  reutilizable** (scope `sse`). Diseñado, pendiente de reimplementar limpio en este repo.
- El análisis de IA (~30 s) pasa a **asíncrono** (job + polling) para no chocar con el
  timeout de proxy de 120 s de Vercel.

## Estado actual (2026-11-01)

`main` = **semilla**. Contiene infraestructura, gate y especificación de paridad.
**El código de aplicación (`frontend/` y `backend/`) está vacío: es lo que se reconstruye.**

Sí está aquí:
- `deploy/oracle/` — compose (Caddy, FastAPI, Postgres, Redis, Evolution), Caddyfile,
  bootstrap, backups (cifrado `age`, verificación, offsite), restore, deploy-staging,
  `validate-env.sh`, `check-evolution.sh`.
- `vercel.json` + `frontend/vercel.json` (idénticos; 5 placeholders `api.staging.example.com`).
- `.github/workflows/` — gate + deploy Oracle (build arm64→GHCR, SSH, rollback por slots).
- `scripts/` — `deploy-gate.sh`, `check-silent-except.py`, `check-un-solo-dueno.py`,
  `check.sh`, `deploy-lock.sh`, `paridad_api.py`. **Nada de scripts legacy.**
- `docs/rebuild/` — contrato del legado y plan.
- `docs/decisiones/` — ADR-000 y ADR-001.

## Cómo continuar (resume para una sesión nueva)

El estado está en disco; **no depende de ninguna conversación**. En una sesión nueva
cuyo workspace sea `/Volumes/Compartida_JMD/MakingSmilesClinic`, leer en este orden:

1. `README.md` (este fichero)
2. `docs/rebuild/MAPA-MODULOS.md` — 21 módulos (M00–M20), dependencias y orden en 10 fases
3. `docs/rebuild/PARIDAD-API.md` + `.csv` — 432 rutas / 498 operaciones, con `fichero:línea`
4. `docs/rebuild/PARIDAD-DATOS.md` — 142 tablas / 291 FK / 126 migraciones, invariantes
5. `docs/rebuild/BASELINE.md` — entorno, límites medidos, toolchain
6. `docs/decisiones/ADR-000` (estrategia) y `ADR-001` (riesgo Vercel Hobby asumido)

Primer bloque de trabajo (código-primero, sin documentación larga):
1. Esqueleto limpio: `backend/` (FastAPI + Clean Architecture) y `frontend/` (Next 15
   feature-first), con `main` arrancando y una ruta `/health`.
2. **M01 Identidad** (auth: JWT cookie httpOnly, login-cookie vs login bearer,
   `X-Centro-Id` multi-tenant, `require_permission`). Es la base: 475/498 operaciones exigen JWT.
3. **M02 Config** (CONFIG = fuente de verdad, permiso `config.editar`, auditado).
4. De ahí, por el orden de `MAPA-MODULOS.md`.

Verificación antes de avanzar (siempre):
```bash
# backend (venv macOS en $TMPDIR/mss-venv, ver BASELINE.md)
cd backend && ENVIRONMENT=development PYTHONPATH=. "$TMPDIR/mss-venv/bin/python" -m pytest tests -q
# frontend
cd frontend && npx tsc --noEmit
# gate (desde la raíz del repo)
PATH="$TMPDIR/mss-venv/bin:$PATH" bash scripts/deploy-gate.sh main
```

## Contrato del legado (referencia solo lectura)

- Repo legado: `/Volumes/Compartida_JMD/MakingSmiles_Studio`. **No se toca.**
- Superficie real: **432 rutas / 498 operaciones** (FastAPI 0.162). OJO: `len(app.routes)`
  devuelve 48 por los `_IncludedRouter`; la medida válida es `app.openapi()["paths"]`.
- 142 tablas, 291 claves foráneas, 126 migraciones.
- 542 parches detectados (16 declarados `raiz:`, 52 probables, 271 sin trazar alta/media,
  239 supresiones de tipos baja). Se integran en la causa raíz, no se arrastran.
- 376 ficheros eliminables; el nuevo repo nace sin ellos. Registro de lo retirado y de lo
  que exige verificación visual: `docs/rebuild/ELIMINADOS.md`.

## Decisiones registradas (ADR)

- **ADR-000** — reconstrucción por módulos con paridad y corte progresivo (nunca big-bang).
- **ADR-001** — Vercel **plan Hobby aceptado por el propietario** pese a: uso comercial no
  permitido y sin DPA (datos de salud). Citado de la documentación oficial. Contenciones
  obligatorias (media/SSE fuera de Vercel) = **bloqueo D-2** hasta implementarse.

## Seguridad — pendiente urgente

`GET /pacientes/{paciente_id}/ficha` y `.../citas` del legado devuelven PII sin
autenticación (detalle en `docs/rebuild/HALLAZGOS-SEGURIDAD.md`). Hotfix preparado en la
rama `hotfix/pii-ficha-sin-auth` del repo legado (subida a GitHub, **sin fusionar** por
decisión del propietario). El sistema nuevo **no debe reproducir** ese patrón: la matriz
de auth (`test_auth_matriz.py` en el legado) es el modelo a portar.

## Entorno y toolchain (quirks medidos)

- El volumen es de red y lento; `git status`/checkout tardan minutos.
- Las herramientas `write`/`edit` **fallan con ENOTSUP** en este volumen → escribir con
  `cat > fichero <<'EOF'` o `python3`.
- El `.venv` del legado es de Linux; en macOS crear venv propio con
  `pip install --only-binary=:all:` (el pin `cryptography==50.0.1` de constraints no tiene
  wheel x86_64-macOS).
- Docker daemon no disponible localmente; Caddy no instalado → validar con parser, declarar lo no validado.
- Playwright: `PLAYWRIGHT_BROWSERS_PATH=<repo>/.cache/playwright`.
- `core.fileMode=false` en config de git (el volumen devuelve todo 0755).

## Qué necesita del propietario

1. Accesos de **Oracle** (forma A1 4/24 o micro AMD, región UE, SSH) y **DNS**
   (`app-staging` / `api-staging`).
2. Proyecto **Vercel** con Root Directory `frontend/`.
3. Secretos de CI (SSH de deploy, GHCR) o despliegue manual inicial.
4. Decisión de Vercel Pro vs Hobby (ADR-001) antes del primer corte con datos reales.
