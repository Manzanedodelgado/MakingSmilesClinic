# Baseline de la rama de reconstrucción (`rebuild/vercel-oracle`)

Medido el 2026-11-01 sobre el worktree `.worktrees/rebuild-vercel-oracle`,
rama `rebuild/vercel-oracle` creada desde `master` (a76ee81).

Todo lo de aquí está **medido**, no supuesto. Lo que no se pudo ejecutar se dice.

## Base de trabajo

| Dato | Valor | Nota |
|---|---|---|
| Worktree | `.worktrees/rebuild-vercel-oracle` | dentro del workspace, excluido vía `.git/info/exclude` |
| Rama base | `master` @ `a76ee81` | = `origin/master` |
| Ficheros rastreados | 1.496 | `git ls-files \| wc -l` |
| Árbol principal | con cambios sin commitear del propietario | no se toca; el rebuild ocurre en el worktree |
| `core.fileMode` | `false` (config compartida) | el volumen de red devuelve todos los ficheros como 0755; sin esto `git status` marca 1.428 ficheros como modificados por modo |

Único pendiente en el worktree tras el arreglo: un PNG sin trackear con nombre Unicode
descompuesto (`frontend/public/images/Making_Smiles_Símbolo_V2.png`), artefacto de
normalización del volumen. No se commitea.

## Herramientas disponibles y no disponibles

| Herramienta | Estado | Consecuencia |
|---|---|---|
| Node.js 24.22 / npm 11.19 | disponible | el frontend se puede construir aquí |
| `frontend/node_modules` | existe en el árbol principal | el worktree NO lo tiene (gitignored): hará falta `npm ci`, symlink o build en un entorno preparado |
| `.venv` del backend | **roto en macOS**: fue creado en Linux (`command = /usr/bin/python3 -m venv /home/jmd/...`) | no se puede usar; se crea un venv macOS aparte |
| Python del sistema | 3.12.14 y 3.14.6 disponibles | 3.12 alinea con el `pyvenv.cfg` del servidor |
| Docker | binario presente, **daemon no corriendo** | `docker compose config`, `docker exec` y los checks de BD de `scripts/check.sh` no se pueden ejecutar aquí |
| Navegadores Playwright | **no instalados** (`~/Library/Caches/ms-playwright` vacío) | la verificación visual del DoD necesita `npx playwright install` |
| Caddy | no instalado | el `Caddyfile` no se puede validar localmente; hay que decirlo en cada informe |

## Requisitos del gate

`scripts/deploy-gate.sh` exige un `.env` en la raíz del worktree con 13 variables
obligatorias no vacías (`DATABASE_URL`, `SECRET_KEY`, `BACKUP_DESTINO`,
`CIFRADO_CREDENCIALES_KEY`, `EVOLUTION_API_KEY`, `IMAP_HOST`, `IMAP_USER`,
`IMAP_PASSWORD`, `GEMINI_API_KEY`, `NVIDIA_API_KEY`, `OPENROUTER_API_KEY`,
`GOOGLE_SERVICE_ACCOUNT_JSON`). Sin ellas el gate **bloquea** antes de mirar el diff.

Para poder ejecutar el gate en el worktree se copió el `.env` del árbol principal
(gitignored, permisos 600, contenido nunca impreso ni commiteado). Es una copia local de
trabajo: no sustituye a la gestión de secretos del despliegue.

## Volumen de datos clínicos

- `backend/media`: **1,2 GB**; fichero mayor: **8,6 MB** (`textos_gastos/132.pdf`), por
  encima del límite de 4,5 MB documentado para cuerpos en funciones serverless. Refuerza
  la decisión de que `/media` no pase por Vercel.
- `frontend/public`: **61 MB** (apto para CDN de Vercel).

## Estado de las auditorías de partida

- Parches: `docs/PARCHES_POR_ARCHIVO_2026-11-01.md` (327 líneas, 543 filas de CSV).
- Eliminables: `docs/ANALISIS_ARCHIVOS_ELIMINABLES_2026-11-01.md` (245 líneas, 392 filas
  de CSV).
- Ambas se hicieron sobre `master` en un commit anterior al actual: **hay que
  re-verificarlas contra `a76ee81` antes de ejecutar borrados**.

## Verificación ejecutable ya disponible (2026-11-01, verificado)

| Qué | Cómo | Resultado |
|---|---|---|
| Superficie HTTP real del backend | venv macOS en `$TMPDIR/mss-venv` (python3.12) + `ENVIRONMENT=development` desde `backend/`: `len(app.openapi()["paths"])` | **432 rutas únicas / ~498 operaciones**. `len(app.routes)` da 48 pero es un artefacto de FastAPI 0.162: 43 `_IncludedRouter` (routers montados, `path==""`) + 4 rutas de docs + `GET /`. La cifra «48 rutas» de auditorías previas NO son rutas |
| Dependencias del backend | `pip install --only-binary=:all: -r backend/requirements.txt` | OK. **No se aplicó `backend/constraints.txt`**: su pin `cryptography==50.0.1` no tiene wheel x86_64-macOS y fuerza build con Rust; el pin de producción (Linux) no se toca |
| Gate `scripts/deploy-gate.sh master` | `PATH="$VENV/bin:$PATH" bash scripts/deploy-gate.sh master` | **verde**: .env OK, sin marcadores ni except silenciosos, sin envoltorios, sin sospechosos, `check-un-solo-dueno` OK (deuda: 6 entidades) |
| Navegadores Playwright | `PLAYWRIGHT_BROWSERS_PATH=<repo>/.cache/playwright npx playwright install chromium` | OK (chromium + headless shell en `.cache/playwright`, fuera de `~/Library/Caches` porque el sandbox no permite escribir ahí). **Toda ejecución de Playwright debe llevar ese `PLAYWRIGHT_BROWSERS_PATH`** |

Nota de honestidad: al principio se intentó contar rutas con `len(app.routes)` y se obtuvieron
5, luego 48 de forma intermitente. La causa real es que en FastAPI 0.162 los routers incluidos
son objetos `_IncludedRouter` y no se aplanan en `app.routes`. La causa de la lectura
intermitente de 5 no se determinó y no afecta a la medición válida. La medición
válida es `app.openapi()["paths"]` = 432, corroborada por la extracción AST de PARIDAD-API
(431 paths / 498 operaciones). El «48 rutas» de las auditorías previas era el conteo de
objetos en `app.routes`, no de rutas: no sirve como prueba de paridad.

## Qué sigue sin poder verificarse aquí

- `docker compose config`, arranque de Postgres/Redis/Evolution y checks de BD de `scripts/check.sh`.
- Validación de `Caddyfile`.
- e2e completo con credenciales reales (necesita backend + BD + frontend levantados).

## Baseline del frontend (verificado 2026-11-01)

- `frontend/node_modules` del worktree es un symlink a `../../../frontend/node_modules`
  del árbol principal (mismo `package-lock`), para no duplicar ~GB en el volumen de red.
  Con eso, `npx tsc --noEmit` en `frontend/` del worktree termina con **exit 0**.
- Playwright: chromium y headless shell instalados en `<repo>/.cache/playwright`; hay que
  exportar `PLAYWRIGHT_BROWSERS_PATH` en cada ejecución.
