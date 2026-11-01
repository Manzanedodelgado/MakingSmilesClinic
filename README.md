# MakingSmilesClinic

Reconstrucción limpia de MakingSmiles_Studio para producción, sin código muerto y con
los parches válidos integrados en la causa raíz.

- **frontend** → Vercel (Next.js, región fra1)
- **backend + Postgres + Redis + Evolution** → Oracle Cloud (Caddy delante)
- El sistema legado es referencia de comportamiento (solo lectura) y no se modifica.

## Estado
`main` = semilla: infraestructura, gate y especificación de paridad. El código de
aplicación se reconstruye módulo a módulo contra `docs/rebuild/PARIDAD-*.md`.

## Estructura
- `frontend/`  Next.js (Vercel)
- `backend/`   FastAPI (Oracle)
- `deploy/`    Caddy, docker-compose, backups, bootstrap
- `scripts/`   gate de despliegue (`deploy-gate.sh`)
- `docs/`      paridad, decisiones (ADR), hallazgos de seguridad, eliminados

## Cómo se construye
1. `docs/rebuild/PARIDAD-API.md` (+CSV) y `PARIDAD-DATOS.md` son el contrato observable.
2. Cada módulo se escribe de cero y se verifica contra sus tests de contrato.
3. `deploy-gate.sh` en verde antes de cada avance; corte a producción solo con paridad demostrada.

## Referencia (solo lectura)
El código legado vive en el repositorio original MakingSmiles_Studio y no se toca.
