/**
 * PASO 14 — Informes / Reporting (Real, Aislado, Estricto)
 *
 * Sin mocks. Motor de informes contra la API real y la BD real.
 * Datos: los informes guardados de prueba llevan prefijo ZZ_E2E y se borran en el mismo
 *        test; las consultas se ejecutan sobre los datos reales del centro.
 *
 * Contrato real verificado en /openapi.json + pruebas en vivo (2026-08-29):
 *   GET  /informes/entidades              -> 200 {entidades:[{key,label,campos:[...]}]}
 *   GET  /informes/tablas                 -> 200 {tablas:[{nombre,label}]}
 *   GET  /informes/tabla/{nombre}/campos  -> 200 {campos:[{key,label,tipo,operadores}]}
 *   POST /informes/ejecutar               -> 200 {columnas, filas, total, limite, truncado}   body {entidad, columnas:[...], filtros:[...], limite}
 *   POST /informes/pivote                 -> 200 {dimensiones, filas, n_filas}   body {entidad, filas:[...], filtros:[...]}
 *   GET  /informes/guardados              -> 200 [ {...} ]
 *   POST /informes/guardados              -> 200 {id}   body {nombre*, entidad*, definicion}
 *   GET  /informes/guardados/{id}         -> 200
 *   PUT  /informes/guardados/{id}         -> 200
 *   DELETE /informes/guardados/{id}       -> 200
 *
 *   (NO existe /informes/{id}/pdf /informes/programados /informes/compartidos ...)
 */
import { test, expect } from '@playwright/test';
import { API, CENTRO_ID } from './fixtures/constants';

const H = { 'X-Centro-Id': String(CENTRO_ID) };

test.describe('Paso 14: Informes (Real, Aislado, Estricto)', () => {
  test('14.1: GET /informes/entidades trae las entidades reportables', async ({ request }) => {
    const resp = await request.get(`${API}/informes/entidades`, { headers: H });
    expect(resp.status()).toBe(200);
    const ents = (await resp.json()).entidades;
    expect(ents.some((e: any) => e.key === 'pacientes')).toBe(true);
  });

  test('14.2: GET /informes/tablas lista las tablas disponibles', async ({ request }) => {
    const resp = await request.get(`${API}/informes/tablas`, { headers: H });
    expect(resp.status()).toBe(200);
    expect(Array.isArray((await resp.json()).tablas)).toBe(true);
  });

  test('14.3: GET /informes/tabla/pacientes/campos describe los campos', async ({ request }) => {
    const resp = await request.get(`${API}/informes/tabla/pacientes/campos`, { headers: H });
    expect(resp.status()).toBe(200);
    const campos = (await resp.json()).campos;
    expect(campos.length).toBeGreaterThan(0);
    expect(campos[0]).toHaveProperty('operadores');
  });

  test('14.4: POST /informes/ejecutar sobre pacientes devuelve filas reales', async ({ request }) => {
    const resp = await request.post(`${API}/informes/ejecutar`, {
      headers: H,
      data: { entidad: 'pacientes', columnas: ['nombre', 'apellidos'], filtros: [], limite: 5 },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.filas.length).toBeLessThanOrEqual(5);
    expect(body.total).toBeGreaterThan(0);
    expect(body.columnas.map((c: any) => c.key)).toEqual(['nombre', 'apellidos']);
  });

  test('14.5: POST /informes/ejecutar con filtro reduce el total', async ({ request }) => {
    const sinFiltro = await request.post(`${API}/informes/ejecutar`, {
      headers: H,
      data: { entidad: 'pacientes', columnas: ['nombre'], filtros: [], limite: 1 },
    });
    const totalSin = (await sinFiltro.json()).total;

    const conFiltro = await request.post(`${API}/informes/ejecutar`, {
      headers: H,
      data: {
        entidad: 'pacientes',
        columnas: ['nombre'],
        filtros: [{ campo: 'apellidos', op: 'contiene', valor: 'MANZANEDO' }],
        limite: 50,
      },
    });
    expect(conFiltro.status()).toBe(200);
    const totalCon = (await conFiltro.json()).total;
    expect(totalCon).toBeGreaterThan(0);
    expect(totalCon).toBeLessThan(totalSin);
  });

  test('14.6: POST /informes/pivote agrega por dimensión', async ({ request }) => {
    const resp = await request.post(`${API}/informes/pivote`, {
      headers: H,
      data: { entidad: 'pacientes', filas: ['activo'], filtros: [] },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(Array.isArray(body.filas)).toBe(true);
    expect(body.n_filas).toBeGreaterThan(0);
  });

  test('14.7: CRUD de informe guardado (crear -> leer -> editar -> borrar)', async ({ request }) => {
    const crear = await request.post(`${API}/informes/guardados`, {
      headers: H,
      data: {
        nombre: 'ZZ_E2E informe pacientes',
        entidad: 'pacientes',
        definicion: { columnas: ['nombre'], filtros: [] },
      },
    });
    expect(crear.status()).toBe(200);
    const informeId = (await crear.json()).id;

    const list = await (await request.get(`${API}/informes/guardados`, { headers: H })).json();
    const arr = Array.isArray(list) ? list : list.data ?? [];
    expect(arr.some((i: any) => i.id === informeId)).toBe(true);

    const leer = await request.get(`${API}/informes/guardados/${informeId}`, { headers: H });
    expect(leer.status()).toBe(200);

    const editar = await request.put(`${API}/informes/guardados/${informeId}`, {
      headers: H,
      data: {
        nombre: 'ZZ_E2E informe editado',
        entidad: 'pacientes',
        definicion: { columnas: ['nombre', 'apellidos'], filtros: [] },
      },
    });
    expect(editar.status()).toBe(200);

    const borrar = await request.delete(`${API}/informes/guardados/${informeId}`, { headers: H });
    expect(borrar.status()).toBe(200);

    const list2 = await (await request.get(`${API}/informes/guardados`, { headers: H })).json();
    const arr2 = Array.isArray(list2) ? list2 : list2.data ?? [];
    expect(arr2.some((i: any) => i.id === informeId)).toBe(false);
  });

  test('14.8: POST /informes/guardados sin nombre es rechazado (422)', async ({ request }) => {
    const resp = await request.post(`${API}/informes/guardados`, {
      headers: H,
      data: { entidad: 'pacientes', definicion: {} },
    });
    expect(resp.status()).toBe(422);
  });

  test('14.9: POST /informes/ejecutar sobre entidad inexistente responde 4xx', async ({ request }) => {
    const resp = await request.post(`${API}/informes/ejecutar`, {
      headers: H,
      data: { entidad: 'entidad_que_no_existe_zzz', columnas: ['x'], filtros: [] },
    });
    expect(resp.status()).toBeGreaterThanOrEqual(400);
    expect(resp.status()).toBeLessThan(500);
  });
});
