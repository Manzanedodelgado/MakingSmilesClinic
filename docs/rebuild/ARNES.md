# ARNÉS DE CONTRATO Y AUTH — MakingSmiles_Studio (S1b)

> **Qué es.** El arnés que congela la superficie HTTP **real** del backend (`app.openapi()`,
> no la spec estática de docs/rebuild) y la matriz de autenticación, para que el rebuild por
> módulos con corte progresivo no pierda rutas, no cambie parámetros por accidente y no
> relaje seguridad sin que nadie lo vea. Es el complemento ejecutable de
> `docs/rebuild/PARIDAD-API.md`/`.csv`: la spec documenta, el arnés **impone**.

- **Frente:** S1b (task-6). **Rama:** `rebuild/vercel-oracle`.
- **Estado medido al escribirlo:** `app.openapi()` → **437 paths / 503 operaciones**
  (432/498 del legacy + los 5 paths de integración de task-4: `/media/firma`,
  `/media/firmado/{ruta}`, `/media/firmado/pacientes/{pid}/{fid}`, `/events/ticket` y
  `POST /pacientes/{pid}/multimedia/{fid}/firma`; `/comunicacion/stream` gana `?ticket=`).
- **Verde actual:** `17 passed, 2 xfailed` (los 2 xfail son la deuda PII conocida, ver §6).
- No hay commits asociados; los ficheros están en el worktree sin trackear para que los revise
  el Lead.

---

## 1. Ficheros

| Fichero | Papel |
|---|---|
| `backend/tests/contract/openapi_paridad.json` | **Snapshot versionado** del contrato (437 paths / 503 operaciones, ~160 KB). Se actualiza solo de forma consciente (§5). |
| `backend/tests/contract/test_openapi_paridad.py` | Deriva de contrato contra el snapshot + contraste con `docs/rebuild/PARIDAD-API.csv` + WebSocket. |
| `backend/tests/contract/test_auth_matriz.py` | Toda operación declara `security` o está en lista blanca justificada; deuda PII con `xfail(strict=True)` por operación. |
| `backend/tests/contract/reglas_auth.py` | La **lista blanca explícita** (una entrada por operación, con motivo y `fichero:línea`) y la tabla de deuda PII. Único sitio donde se justifican excepciones. |
| `backend/tests/contract/test_media_firmada.py` | Contrato de la media firmada (task-4 / INFRA.md §5.2). Se salta con motivo si task-4 no ha aterrizado. |
| `backend/tests/contract/test_sse_ticket.py` | Contrato del ticket SSE (task-4 / INFRA.md §5.3). Se salta con motivo si task-4 no ha aterrizado. |
| `backend/tests/contract/conftest.py` | Fixtures: app real, snapshot (admite `PARIDAD_SNAPSHOT=<ruta>` solo para demos), `scripts/paridad_api.py` como biblioteca y el extractor estático de `docs/rebuild/verificar_rutas.py`. |
| `scripts/paridad_api.py` | Utilidad CLI: captura, compara y **escribe** el snapshot. Misma lógica que usan los tests (una sola fuente de verdad). |

## 2. Qué prueba cada test

### `test_openapi_paridad.py`
1. **`test_snapshot_es_autoconsistente`**: el JSON del snapshot no está editado a mano de forma
   incoherente (conteos cuadran con sus rutas) y registra el `motivo` de su actualización.
2. **`test_sin_deriva_de_contrato`**: la app real debe tener **exactamente** la superficie del
   snapshot. Distingue, con mensaje explícito, entre:
   - `RUTA AÑADIDA` / `RUTA ELIMINADA` (path que aparece/desaparece),
   - `MÉTODO AÑADIDO` / `MÉTODO ELIMINADO` (misma ruta, otro verbo HTTP),
   - `OPERACIÓN CAMBIADA` por campo: `auth` (esquemas de seguridad), `parametros`
     (`in:nombre:requerido`), `request_body` (content-types) y `respuestas` (códigos).
3. **`test_resumen_de_superficie_no_se_evapora`**: guardia contra un falso verde si la captura
   saliera vacía/rota (compara cifras con el snapshot y exige > 0).
4. **`test_inventario_de_docs_no_pierde_operaciones`**: contraste adicional con
   `docs/rebuild/PARIDAD-API.csv`; ninguna operación inventariada puede desaparecer de la app
   (normaliza el convertidor `{ruta:path}` y excluye la WebSocket, que OpenAPI no lista).
   Si una retirada es intencionada hay que actualizar el CSV en el mismo cambio.
5. **`test_rutas_websocket_inventariadas`**: OpenAPI **no** expone WebSocket; se vigila la lista
   estática con `docs/rebuild/verificar_rutas.py` contra la esperada (hoy, solo
   `/ws/gestoria/{centro_id}`, `ws_router.py:153`).

### `test_auth_matriz.py`
1. **`test_esquema_de_seguridad_declarado`**: el único esquema de seguridad sigue siendo
   `HTTPBearer` (JWT centro/paciente). Un esquema nuevo obliga a revisión de seguridad.
2. **`test_toda_operacion_tiene_auth_o_justificacion_explicita`**: para cada operación, si no
   declara `security` debe estar en `reglas_auth.WHITELIST` (con motivo y evidencia) o en
   `DEUDA_PII`. Una ruta nueva sin auth **rompe la suite**.
3. **`test_sin_auth_es_exactamente_lista_blanca_mas_deuda`**: igualdad de conjuntos
   `sin_auth == WHITELIST ∪ DEUDA_PII`; detecta tanto rutas sin justificar como entradas
   huérfanas (ruta borrada o que ya declara auth).
4. **`test_no_hay_operaciones_con_auth_opcional_anonima`**: rechaza `security: [{}]`
   (auth de adorno que permitiría anónimo).
5. **`test_deuda_pii_requiere_auth`** (`xfail(strict=True)` por operación): las dos rutas PII
   de S1 (`GET /pacientes/{id}/ficha`, `GET /pacientes/{id}/citas`) exigen auth; hoy **fallan**
   y por eso el xfail. Cuando el hotfix las proteja, pasarán a **XPASS**, la suite fallará y
   obligará a quitar el xfail y la entrada.
6. **`test_deuda_pii_rutas_siguen_existiendo`** (sin xfail): si las rutas se **eliminan** en
   vez de corregirse, este test lo detecta (el xfail no puede taparlo).

**Por qué xfail y no test rojo (decidido por el Lead):** un rojo tumbe el gate por deuda
legacy ya trazada con hotfix en curso; el xfail estricto conserva la señal y se autocorrige
(no se puede olvidar limpiarlo). El xfail es **por operación**, nunca genérico.

### `test_media_firmada.py` / `test_sse_ticket.py`
Validan el contrato acordado con task-4 (INFRA.md §5.2-5.3) **solo si los endpoints existen**;
si no, `pytest.skip` con motivo. Hoy existen y pasan:
- `GET /media/firma` (cookie) → emite URL firmada; `GET /media/firmado/{ruta}` y
  `GET /media/firmado/pacientes/{pid}/{fid}` **sin cookie** (HMAC: `exp`/`uid`/`sig`;
  `thumb` opcional en la de paciente); `POST /pacientes/{pid}/multimedia/{fid}/firma` (cookie).
- `GET /events/ticket` (cookie, HTTPBearer declarado) y `GET /comunicacion/stream` con
  `?ticket=` **opcional** sin perder el HTTPBearer declarado.

## 3. Cómo se ejecuta

Desde `backend/` (cwd que asume la suite; el arnés también funciona desde la raíz del repo):

```bash
cd backend
PATH="$TMPDIR/mss-venv/bin:$PATH" python -m pytest tests/contract -q
#   17 passed, 2 xfailed   (estado actual)
```

Desde la raíz del worktree (también válido):

```bash
PATH="$TMPDIR/mss-venv/bin:$PATH" python -m pytest backend/tests/contract -q
```

CLI de paridad (sin pytest):

```bash
python3 scripts/paridad_api.py            # compara; exit 1 si hay deriva
python3 scripts/paridad_api.py --resumen  # 437 paths / 503 operaciones
```

No hay dependencias nuevas: usa el venv del backend (`$TMPDIR/mss-venv`) y SQLite/TestClient
solo cuando hace falta la app; **importar `main:app` no ejecuta el lifespan**, así que no toca
PostgreSQL ni servicios externos. Los tests no requieren marcador `integration`.

### CI / deploy-gate
`.github/workflows/patches-gate.yml` **no se toca** (fuera del alcance de S1b) y
`scripts/deploy-gate.sh` **no se ha modificado**: el gate solo ejecuta tests del área
detectada en el diff, y los ficheros de S1b entran sin trackear (no salen en
`git diff --name-only`). Para que el arnés bloquee de verdad en el gate, el Lead/propietario
de `deploy-gate.sh` puede añadir en la sección `2/3 tests del área afectada`:

```bash
echo "== 2b/3 contract tests (paridad + matriz de auth) =="
( cd backend && python3 -m pytest tests/contract -q ) 2>&1 | tail -n 3
```

Aviso operativo para quien añada código nuevo: el escáner de marcadores del gate busca la
subcadena literal `T-O-D-O-:` (sin guiones) **en cualquier .py nuevo**, y esa subcadena aparece
también dentro de la palabra METODO/MÉTODO seguida de dos puntos. En este arnés se evita
escribiendo `METODO_Y_FIRMA` u otra formulación;
si el gate bloquea con "marcador sin trazar: None", casi seguro es eso.

## 4. Qué NO cubre (honestidad)

- **Semántica de la autenticación**: comprueba que `security` está **declarado**, no que la
  dependencia realmente valide (un `Depends` que no hiciera nada seguiría pareciendo
  protegido). Las pruebas funcionales de cada flujo son de la suite existente
  (`test_security_surface.py`, `test_integracion_firmada.py`, cross-tenant, etc.).
- **Cuerpos de request/response**: compara content-types y códigos de respuesta, **no** los
  esquemas de campos de los modelos Pydantic. Un cambio de campo no se detecta aquí.
- **WebSocket**: solo su existencia vía extracción estática; no su protocolo ni sus mensajes.
- **Runtime**: no arranca uvicorn, no habla con PostgreSQL/Redis/Evolution/Gmail. No sustituye
  al gate ni a la suite completa.
- **OpenAPI no incluye** rutas montadas fuera de FastAPI ni las documentales (`/docs`,
  `/openapi.json`, que se desactivan fuera de development).
- **Lista blanca = confianza revisada, no infalible**: la matriz no puede saber si
  `X-Internal-Key` está bien rotada o si el `webhook_secret` de un centro es fuerte. Es una
  lista de excepciones **revisadas una a una**, no un barrido de seguridad.
- No compara `operationId` ni descripciones (ruido de documentación, no contrato observable).

## 5. Actualización consciente del snapshot (nunca auto-aceptar)

El snapshot es la referencia del contrato: **no se actualiza nunca de forma automática** (ni
el CLI ni los tests lo hacen). Procedimiento obligatorio:

1. Ejecuta `python3 scripts/paridad_api.py` y **lee cada diferencia** (`RUTA AÑADIDA`,
   `RUTA ELIMINADA`, `MÉTODO …`, `OPERACIÓN CAMBIADA …`).
2. Decide caso por caso:
   - **NO intencionado** → corrige el código. El snapshot manda.
   - **Intencionado** (nueva ruta de un módulo reconstruido, retirada aprobada, cambio de
     contrato acordado con las apps móviles/el Lead) → sigue.
3. `python3 scripts/paridad_api.py --escribir-snapshot --motivo "<qué cambia y por qué, con
   la task/PR>"`. El motivo es **obligatorio**: sin él el comando se niega. El script imprime
   el diff completo que acepta (queda en el log del PR).
4. Revisa `git diff`/`git status` del `openapi_paridad.json` (se sella `fecha_utc` y `motivo`)
   y pégalo en la descripción del cambio.
5. `cd backend && python -m pytest tests/contract -q` y el deploy-gate en verde.

Añadir una ruta **pública legítima**: además del snapshot, añade su entrada a
`reglas_auth.WHITELIST` (método + path exactos) con motivo y evidencia `fichero:línea`. Si no,
`test_auth_matriz.py` falla: es el comportamiento buscado. Si una entrada de la lista deja de
aplicar, los tests fallan hasta que se limpia.

**Cómo NO se actualiza:** nunca editar el JSON a mano, nunca borrar `reglas_auth.DEUDA_PII`
para "verde", nunca añadir rutas a la lista blanca sin motivo, nunca ejecutar
`--escribir-snapshot` sin haber leído el diff.

## 6. Deuda PII conocida (S1 HALLAZGOS-SEGURIDAD)

`GET /pacientes/{paciente_id}/ficha` (`backend/api/pacientes_router.py:1433`) y
`GET /pacientes/{paciente_id}/citas` (`:1468`) no exigen autenticación y devuelven PII. Son
endpoints heredados de las apps móviles antiguas. Decisión del Lead: **xfail estricto
documentado** (no test rojo) con referencia a `docs/rebuild/HALLAZGOS-SEGURIDAD.md` y "hotfix
en curso". Cuando el hotfix añada auth: XPASS → quitar el xfail de `test_deuda_pii_requiere_auth`
y la entrada de `reglas_auth.DEUDA_PII`. Si las rutas se eliminan, el test de existencia falla
y obliga a actualizar snapshot + inventario de paridad.

## 7. Demostración de que el arnés detecta rupturas (verificada, con reversión)

**A) Deriva de contrato** (snapshot mutado en `/tmp`, sin tocar el versionado):

```bash
# se elimina /agenda/citas del snapshot, se añade una ruta inexistente y se quita la auth
# declarada de /agenda/panel; luego:
cd backend && PARIDAD_SNAPSHOT=/tmp/snapshot_roto.json \
  python -m pytest tests/contract/test_openapi_paridad.py -q -k "deriva or resumen"
```

Resultado observado (`2 failed`, exit 1):

```
AssertionError: El contrato HTTP real derivó del snapshot versionado (3 diferencia(s)):
  · RUTA AÑADIDA: /agenda/citas (GET, POST)
  · RUTA ELIMINADA: /demo/ruta-que-no-existe (GET)
  · OPERACIÓN CAMBIADA: GET /agenda/panel · auth: None -> ['HTTPBearer']
...
conteos: {'paths': 437, 'operaciones': 502} -> {'paths': 437, 'operaciones': 503}
```

**B) Ruta nueva sin auth** (test temporal in-memory, sin tocar código de producción, borrado
después): se añade `GET /demo-ruta-sin-auth` a la app y se pasan las reglas reales
(`reglas_auth.violaciones`).

Resultado observado (`1 failed`):

```
AssertionError: SIN AUTH NO JUSTIFICADA: GET /demo-ruta-sin-auth — añade la dependencia de auth
(get_current_user/require_permission, X-Internal-Key o firma) o justifica la excepción por
operación en reglas_auth.WHITELIST
```

**Reversión:** los dos ficheros temporales (`/tmp/snapshot_roto.json` y
`backend/tests/contract/test_demo_negativo_auth.py`) se eliminaron; la suite vuelve a
`17 passed, 2 xfailed` y el snapshot versionado nunca se tocó en las demos.

## 8. Nota sobre FastAPI 0.162

`len(app.routes)` **no** mide la superficie: `include_router` deja un `_IncludedRouter` por
router (de ahí el artefacto de 48-50). La métrica de paridad es **siempre**
`len(app.openapi()["paths"])` y las operaciones, `sum(len(ops) …)`. Documentado también en
`docs/rebuild/verificar_rutas.py`.
