/**
 * PASO 12 — Gestoría (Real, Aislado, Estricto)
 *
 * Sin mocks. Contabilidad del centro contra la API real.
 * Datos: los tests que crean gasto/movimiento usan concepto con prefijo ZZ_E2E y los
 *        borran en el mismo test (la API sí expone DELETE de gasto y de movimiento).
 *        Los tests de lectura operan sobre la contabilidad real ya existente.
 *
 * Contrato real verificado en /openapi.json + pruebas en vivo (2026-08-29):
 *   GET    /gestoria/facturas               -> 200 {total, data:[{id,numero,fecha,cliente}]}
 *   GET    /gestoria/gastos                 -> 200 {data:[{id,fecha,proveedor,...}]}
 *   POST   /gestoria/gastos                 -> 201 {id}   body {fecha*, concepto, base_imponible, iva_pct, total, estado}
 *   PATCH  /gestoria/gastos/{gid}           -> 200
 *   DELETE /gestoria/gastos/{gid}           -> 200
 *   GET    /gestoria/movimientos            -> 200 {data:[{id,fechaOperacion,conceptoBanco,...}]}
 *   POST   /gestoria/movimientos            -> 201 {id,tipo}   body {fecha_operacion*, concepto_banco*, importe*}
 *   DELETE /gestoria/movimientos/{mid}      -> 200
 *   GET    /gestoria/deudas/sin-imputar     -> 200 {deudasConAdeudo, imputadas, sinImputar, importeSinImputar}
 *   GET    /gestoria/extractos              -> 200 {extractos:[{id,nombre,fecha,tamano}]}
 *   GET    /gestoria/duplicados             -> 200 {data:[...]}
 *
 *   (NO existe POST/PUT/DELETE /gestoria/facturas, ni /resumen /balance /caja /impuestos /reportes)
 */
import { test, expect } from '@playwright/test';
import { API, CENTRO_ID } from './fixtures/constants';

const H = { 'X-Centro-Id': String(CENTRO_ID) };

test.describe('Paso 12: Gestoría (Real, Aislado, Estricto)', () => {
  test('12.1: GET /gestoria/facturas devuelve el libro de facturas emitidas', async ({ request }) => {
    const resp = await request.get(`${API}/gestoria/facturas`, { headers: H });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(typeof body.total).toBe('number');
    expect(Array.isArray(body.data)).toBe(true);
  });

  test('12.2: GET /gestoria/facturas?search= filtra', async ({ request }) => {
    const resp = await request.get(`${API}/gestoria/facturas?search=xxxx-no-existe-zzz`, { headers: H });
    expect(resp.status()).toBe(200);
    expect((await resp.json()).data).toEqual([]);
  });

  test('12.3: GET /gestoria/gastos devuelve el libro de gastos', async ({ request }) => {
    const resp = await request.get(`${API}/gestoria/gastos`, { headers: H });
    expect(resp.status()).toBe(200);
    expect(Array.isArray((await resp.json()).data)).toBe(true);
  });

  test('12.4: POST /gestoria/gastos crea un gasto, PATCH lo edita y DELETE lo elimina', async ({ request }) => {
    const crear = await request.post(`${API}/gestoria/gastos`, {
      headers: H,
      data: {
        fecha: '2026-08-29',
        concepto: 'ZZ_E2E gasto de prueba',
        base_imponible: 100,
        iva_pct: 21,
        total: 121,
        estado: 'pendiente',
      },
    });
    expect(crear.status()).toBe(201);
    const gastoId = (await crear.json()).id;
    expect(gastoId).toBeGreaterThan(0);

    const list = await (await request.get(`${API}/gestoria/gastos`, { headers: H })).json();
    expect(list.data.some((g: any) => g.id === gastoId)).toBe(true);

    const patch = await request.patch(`${API}/gestoria/gastos/${gastoId}`, {
      headers: H,
      data: { concepto: 'ZZ_E2E gasto editado' },
    });
    expect(patch.status()).toBe(200);

    const del = await request.delete(`${API}/gestoria/gastos/${gastoId}`, { headers: H });
    expect(del.status()).toBe(200);

    const list2 = await (await request.get(`${API}/gestoria/gastos`, { headers: H })).json();
    expect(list2.data.some((g: any) => g.id === gastoId)).toBe(false);
  });

  test('12.5: POST /gestoria/gastos sin fecha es rechazado (422)', async ({ request }) => {
    const resp = await request.post(`${API}/gestoria/gastos`, {
      headers: H,
      data: { concepto: 'ZZ_E2E sin fecha', base_imponible: 10, iva_pct: 21, total: 12.1, estado: 'pendiente' },
    });
    expect(resp.status()).toBe(422);
  });

  test('12.6: GET /gestoria/movimientos devuelve los movimientos bancarios', async ({ request }) => {
    const resp = await request.get(`${API}/gestoria/movimientos`, { headers: H });
    expect(resp.status()).toBe(200);
    expect(Array.isArray((await resp.json()).data)).toBe(true);
  });

  test('12.7: POST /gestoria/movimientos crea un movimiento y DELETE lo elimina', async ({ request }) => {
    const crear = await request.post(`${API}/gestoria/movimientos`, {
      headers: H,
      data: {
        fecha_operacion: '2026-08-29',
        concepto_banco: 'ZZ_E2E movimiento de prueba',
        importe: -50.5,
      },
    });
    expect(crear.status()).toBe(201);
    const body = await crear.json();
    expect(body.id).toBeGreaterThan(0);
    expect(body.tipo).toBe('debe'); // importe negativo

    const del = await request.delete(`${API}/gestoria/movimientos/${body.id}`, { headers: H });
    expect(del.status()).toBe(200);
  });

  test('12.8: POST /gestoria/movimientos sin importe es rechazado (422)', async ({ request }) => {
    const resp = await request.post(`${API}/gestoria/movimientos`, {
      headers: H,
      data: { fecha_operacion: '2026-08-29', concepto_banco: 'ZZ_E2E sin importe' },
    });
    expect(resp.status()).toBe(422);
  });

  test('12.9: GET /gestoria/deudas/sin-imputar devuelve el resumen de deudas', async ({ request }) => {
    const resp = await request.get(`${API}/gestoria/deudas/sin-imputar`, { headers: H });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(typeof body.sinImputar).toBe('number');
    expect(typeof body.importeSinImputar).toBe('number');
  });

  test('12.10: GET /gestoria/extractos lista los extractos bancarios subidos', async ({ request }) => {
    const resp = await request.get(`${API}/gestoria/extractos`, { headers: H });
    expect(resp.status()).toBe(200);
    expect(Array.isArray((await resp.json()).extractos)).toBe(true);
  });

  test('12.11: GET /gestoria/duplicados detecta facturas duplicadas', async ({ request }) => {
    const resp = await request.get(`${API}/gestoria/duplicados`, { headers: H });
    expect(resp.status()).toBe(200);
    expect(Array.isArray((await resp.json()).data)).toBe(true);
  });
});
