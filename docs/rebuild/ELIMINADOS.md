# Código muerto eliminado (verificado)

Registro de bajas ejecutadas sobre `docs/ANALISIS_ARCHIVOS_ELIMINABLES_2026-11-01.md`,
re-verificadas contra `master` @ a76ee81 y con comprobación tras cada lote.

## Lote 1 — 2026-11-01 (13 ficheros)

**Frontend (8, clase M1 del informe):** sin ningún `import` alcanzable.
- `app/(app)/configuracion/_components/`: `AlexChannelToggles.tsx`, `CentinelaToggle.tsx`,
  `GestorToggle.tsx`, `StatusChip.tsx` (solo usado por los tres anteriores), `EstadosCita.tsx`
- `features/ia/components/AuraChat.tsx`, `shared/hooks/useWebSocket.ts`,
  `features/patients/lib/docBase.ts` (solo citado en un comentario)

**Backend (5, clase M2):** módulos sin importar.
- `application/tools.py`, `application/internal_api_client.py` (solo lo usaba tools.py),
  `domain/services/tiempo_clinica.py`, `infrastructure/llm/agent_orchestrator.py`,
  `application/services/tratamientos_pacientes_service.py`

**Se conserva** `domain/services/gestor_registro.py` (contiene `anotar_ilegible` y lo cita la
documentación de gestión de facturas: confianza media, decide el propietario).

## Verificación ejecutada tras el lote

| Comprobación | Resultado |
|---|---|
| `import main` + `app.openapi()["paths"]` | OK, **437 rutas** (432 previas + 5 endpoints nuevos de la integración S2); ninguna ruta perdida |
| `pytest backend/tests/contract` | **17 passed, 2 xfailed** |
| `npx tsc --noEmit` (frontend) | **exit 0** |
| `scripts/deploy-gate.sh master` | verde |
| Gate de "un solo dueño" | OK (deuda: 6 entidades) |

Pendiente (requiere verificación visual antes de tocar): `frontend/public/images` (43,1 MB),
`ODONTOGRAMA COPIA*`, `public/piezas/`, worktrees y `.env.bak-*`. Y los lotes S/P/X del
informe de eliminables (376 ficheros), que se harán por clases y con el mismo protocolo.

## Lote 2 — 2026-11-01 (37 ficheros, clase S)

Residuos sin referencias a la web, según la auditoría (A3/B1/B2):
`node_modules/` de la raíz (7 ficheros rastreados por error), `docs/modelo20-graph/graphify-out/`
(29 generados), `frontend/build-output.txt` y los scripts sueltos de captura
(`captura-mss.cjs`, `captura2/3/4.cjs`, `shot2.cjs`, `shots.cjs`).

Verificación: `import main` mantiene **437 rutas** OpenAPI y `deploy-gate.sh` verde.
Pendiente para lotes siguientes: assets de `public/` (necesitan comprobación visual),
worktrees muertos y `.env.bak-*` (fuera de git; decide el propietario).
