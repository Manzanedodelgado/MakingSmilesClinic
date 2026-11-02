/**
 * PASO 13 — Configuración (Real, Aislado, Estricto)
 *
 * Sin mocks. Configuración del centro contra la API real.
 * Datos: los tests que escriben usan claves/títulos con prefijo zz_e2e / ZZ_E2E y los
 *        borran en el mismo test; globalTeardown barre cualquier resto.
 *
 * Contrato real verificado en /openapi.json + pruebas en vivo (2026-08-29):
 *   GET  /config                                          -> 200 {centro_id, sistema, valores:{clave:valor}}
 *   PUT  /config                                          -> 200 {id, clave, valor}   body {clave*, valor, sistema?}
 *   GET  /configuracion/centro                            -> 200 {centro:{nombre,email,activo,...}}
 *   GET  /configuracion/agenda                            -> 200 {agendas, ...}
 *   GET  /configuracion/colaboradores                     -> 200 {colaboradores:[{id,nombre,apellidos,...}]}
 *   GET  /configuracion/personal                          -> 200 {personal:[...]}
 *   GET  /configuracion/tratamientos                      -> 200 {tratamientos:[{id,codigo,nombre}]}
 *   GET  /configuracion/tipos-cita                        -> 200 {tipos_cita:[{id,nombre,color}]}
 *   GET  /configuracion/gabinetes                         -> 200 {gabinetes:[{id,nombre}]}
 *   GET  /config/centinela/nivel                          -> 200 {nivel, comprobado}
 *   POST /configuracion/admin/presupuestos-predisenados   -> 201 {id}
 *   PUT  /configuracion/admin/presupuestos-predisenados/{pid} -> 200
 *   DELETE /configuracion/admin/presupuestos-predisenados/{pid} -> 204
 *
 *   (NO existe /config/clinica /config/horarios /config/backup /config/salud /config/version ...)
 */
import { test, expect } from '@playwright/test';
import { API, CENTRO_ID, TRATAMIENTO_REAL } from './fixtures/constants';

const H = { 'X-Centro-Id': String(CENTRO_ID) };

test.describe('Paso 13: Configuración (Real, Aislado, Estricto)', () => {
  test('13.1: GET /config devuelve el mapa de valores del centro', async ({ request }) => {
    const resp = await request.get(`${API}/config`, { headers: H });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.centro_id).toBe(CENTRO_ID);
    expect(typeof body.valores).toBe('object');
  });

  test('13.2: PUT /config escribe una clave y GET /config la refleja', async ({ request }) => {
    const put = await request.put(`${API}/config`, {
      headers: H,
      data: { clave: 'zz_e2e.test', valor: 'valor-prueba-e2e' },
    });
    expect(put.status()).toBe(200);
    expect((await put.json()).valor).toBe('valor-prueba-e2e');

    const get = await (await request.get(`${API}/config`, { headers: H })).json();
    expect(get.valores['zz_e2e.test']).toBe('valor-prueba-e2e');

    // sobrescribe con otro valor (idempotencia)
    const put2 = await request.put(`${API}/config`, {
      headers: H,
      data: { clave: 'zz_e2e.test', valor: 'valor-2' },
    });
    expect(put2.status()).toBe(200);
    const get2 = await (await request.get(`${API}/config`, { headers: H })).json();
    expect(get2.valores['zz_e2e.test']).toBe('valor-2');
  });

  test('13.3: PUT /config sin clave es rechazado (422)', async ({ request }) => {
    const resp = await request.put(`${API}/config`, { headers: H, data: { valor: 'x' } });
    expect(resp.status()).toBe(422);
  });

  test('13.4: GET /configuracion/centro trae los datos del centro', async ({ request }) => {
    const resp = await request.get(`${API}/configuracion/centro`, { headers: H });
    expect(resp.status()).toBe(200);
    expect((await resp.json()).centro.nombre).toBe('RUBIO GARCIA DENTAL');
  });

  test('13.5: GET /configuracion/agenda trae agendas y recursos', async ({ request }) => {
    const resp = await request.get(`${API}/configuracion/agenda`, { headers: H });
    expect(resp.status()).toBe(200);
    expect(Array.isArray((await resp.json()).agendas)).toBe(true);
  });

  test('13.6: GET /configuracion/colaboradores lista el personal clínico', async ({ request }) => {
    const resp = await request.get(`${API}/configuracion/colaboradores`, { headers: H });
    expect(resp.status()).toBe(200);
    expect(Array.isArray((await resp.json()).colaboradores)).toBe(true);
  });

  test('13.7: GET /configuracion/personal lista el personal del centro', async ({ request }) => {
    const resp = await request.get(`${API}/configuracion/personal`, { headers: H });
    expect(resp.status()).toBe(200);
    expect(Array.isArray((await resp.json()).personal)).toBe(true);
  });

  test('13.8: GET /configuracion/tratamientos trae el catálogo del centro', async ({ request }) => {
    const resp = await request.get(`${API}/configuracion/tratamientos`, { headers: H });
    expect(resp.status()).toBe(200);
    const trat = (await resp.json()).tratamientos;
    expect(trat.some((t: any) => t.id === TRATAMIENTO_REAL.id)).toBe(true);
  });

  test('13.9: GET /configuracion/tipos-cita y /gabinetes responden', async ({ request }) => {
    const tipos = await request.get(`${API}/configuracion/tipos-cita`, { headers: H });
    expect(tipos.status()).toBe(200);
    expect(Array.isArray((await tipos.json()).tipos_cita)).toBe(true);

    const gab = await request.get(`${API}/configuracion/gabinetes`, { headers: H });
    expect(gab.status()).toBe(200);
    expect(Array.isArray((await gab.json()).gabinetes)).toBe(true);
  });

  test('13.10: GET /config/centinela/nivel informa del estado de seguridad', async ({ request }) => {
    const resp = await request.get(`${API}/config/centinela/nivel`, { headers: H });
    expect(resp.status()).toBe(200);
    expect(await resp.json()).toHaveProperty('nivel');
  });

  test('13.11: CRUD de presupuesto predisenado (crear -> editar -> borrar)', async ({ request }) => {
    const crear = await request.post(`${API}/configuracion/admin/presupuestos-predisenados`, {
      headers: H,
      data: {
        titulo: 'ZZ_E2E predisenado',
        activo: true,
        lineas: [{ tratamiento_id: TRATAMIENTO_REAL.id, cantidad: 1, descuento_pct: false, orden: 0 }],
      },
    });
    expect(crear.status()).toBe(201);
    const pid = (await crear.json()).id;

    const list = await (await request.get(`${API}/configuracion/admin/presupuestos-predisenados`, { headers: H })).json();
    const arr = Array.isArray(list) ? list : list.data ?? list.predisenados ?? [];
    expect(arr.some((p: any) => p.id === pid)).toBe(true);

    const editar = await request.put(`${API}/configuracion/admin/presupuestos-predisenados/${pid}`, {
      headers: H,
      data: {
        titulo: 'ZZ_E2E predisenado editado',
        activo: true,
        lineas: [{ tratamiento_id: TRATAMIENTO_REAL.id, cantidad: 2, descuento_pct: false, orden: 0 }],
      },
    });
    expect(editar.status()).toBe(200);

    const borrar = await request.delete(`${API}/configuracion/admin/presupuestos-predisenados/${pid}`, { headers: H });
    expect(borrar.status()).toBe(204);
  });
});
