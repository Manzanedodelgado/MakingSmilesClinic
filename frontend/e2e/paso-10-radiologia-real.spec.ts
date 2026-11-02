/**
 * PASO 10 — Radiología (Real, Aislado, Estricto)
 *
 * Sin mocks. Subida real de imagen + hallazgos + anotaciones contra la API real.
 * Datos: paciente NUEVO ZZ_E2E por test; su imagen y sus hallazgos se borran al borrar
 *        el paciente. La imagen fixture es e2e/fixtures/rx-test.png (real, versionada).
 *
 * Contrato real verificado en /openapi.json + pruebas en vivo (2026-08-29):
 *   GET    /pacientes/{id}/radiologia               -> 200 [ {id,paciente_id,modalidad,archivo_url,hallazgos:[]} ]
 *   POST   /pacientes/{id}/radiologia               -> 201 {id,...}   multipart/form-data campo `file`
 *   GET    /radiologia/modalidades                  -> 200
 *   POST   /radiologia/{imagen_id}/hallazgos        -> 201 {id,descripcion,pieza,confianza}   body {descripcion*, pieza, confianza}
 *   DELETE /radiologia/hallazgos/{hallazgo_id}      -> 204
 *   GET    /radiologia/{imagen_id}/anotaciones      -> 200 {imagen_id, items}
 *   PUT    /radiologia/{imagen_id}/anotaciones      -> 200 {imagen_id, items}   body {items*:[]}
 *   POST   /radiologia/{imagen_id}/clasificar       -> 200
 *   DELETE /radiologia/{imagen_id}                  -> 204
 *
 *   (NO existe POST /radiologia/{pid} con JSON — es multipart y cuelga de /pacientes/{id})
 */
import path from 'path';
import { test, expect, APIRequestContext } from '@playwright/test';
import { API, CENTRO_ID } from './fixtures/constants';
import { PacienteFactory } from './fixtures/factories';
import { borrarPacienteTest } from './fixtures/database';

const H = { 'X-Centro-Id': String(CENTRO_ID) };
const RX_IMG = path.join(__dirname, 'fixtures', 'rx-test.png');

test.describe('Paso 10: Radiología (Real, Aislado, Estricto)', () => {
  let pacienteId: number;

  test.beforeEach(async ({ request }) => {
    pacienteId = (await PacienteFactory.crear(request)).id;
  });

  test.afterEach(async () => {
    if (pacienteId) {
      await borrarPacienteTest(pacienteId);
      pacienteId = 0 as unknown as number;
    }
  });

  async function subirImagen(request: APIRequestContext): Promise<number> {
    const resp = await request.post(`${API}/pacientes/${pacienteId}/radiologia`, {
      headers: H,
      multipart: {
        file: {
          name: 'rx-test.png',
          mimeType: 'image/png',
          buffer: require('fs').readFileSync(RX_IMG),
        },
      },
    });
    expect(resp.status(), await resp.text()).toBe(201);
    return (await resp.json()).id;
  }

  test('10.1: GET /radiologia de paciente nuevo devuelve lista vacía', async ({ request }) => {
    const resp = await request.get(`${API}/pacientes/${pacienteId}/radiologia`, { headers: H });
    expect(resp.status()).toBe(200);
    expect(await resp.json()).toEqual([]);
  });

  test('10.2: POST /radiologia sube la imagen y aparece en el listado', async ({ request }) => {
    const imagenId = await subirImagen(request);
    expect(imagenId).toBeGreaterThan(0);

    const list = await request.get(`${API}/pacientes/${pacienteId}/radiologia`, { headers: H });
    const body = await list.json();
    expect(body).toHaveLength(1);
    expect(body[0].id).toBe(imagenId);
    expect(body[0].archivo_url).toContain(`radiologia/${pacienteId}/`);
  });

  test('10.3: GET /radiologia/modalidades devuelve el catálogo', async ({ request }) => {
    const resp = await request.get(`${API}/radiologia/modalidades`, { headers: H });
    expect(resp.status()).toBe(200);
  });

  test('10.4: POST /radiologia/{id}/hallazgos añade un hallazgo a la imagen', async ({ request }) => {
    const imagenId = await subirImagen(request);

    const resp = await request.post(`${API}/radiologia/${imagenId}/hallazgos`, {
      headers: H,
      data: { descripcion: 'ZZ_E2E caries oclusal', pieza: '16', confianza: 0.8 },
    });
    expect(resp.status()).toBe(201);
    const hallazgo = await resp.json();
    expect(hallazgo.descripcion).toBe('ZZ_E2E caries oclusal');
    expect(hallazgo.pieza).toBe('16');

    const list = await request.get(`${API}/pacientes/${pacienteId}/radiologia`, { headers: H });
    const img = (await list.json()).find((i: any) => i.id === imagenId);
    expect(img.hallazgos.some((h: any) => h.id === hallazgo.id)).toBe(true);
  });

  test('10.5: POST /radiologia/{id}/hallazgos sin descripción es rechazado (422)', async ({ request }) => {
    const imagenId = await subirImagen(request);
    const resp = await request.post(`${API}/radiologia/${imagenId}/hallazgos`, {
      headers: H,
      data: { pieza: '16' },
    });
    expect(resp.status()).toBe(422);
  });

  test('10.6: DELETE /radiologia/hallazgos/{id} elimina el hallazgo', async ({ request }) => {
    const imagenId = await subirImagen(request);
    const post = await request.post(`${API}/radiologia/${imagenId}/hallazgos`, {
      headers: H,
      data: { descripcion: 'ZZ_E2E a borrar' },
    });
    const hallazgoId = (await post.json()).id;

    const del = await request.delete(`${API}/radiologia/hallazgos/${hallazgoId}`, { headers: H });
    expect(del.status()).toBe(204);

    const list = await request.get(`${API}/pacientes/${pacienteId}/radiologia`, { headers: H });
    const img = (await list.json()).find((i: any) => i.id === imagenId);
    expect(img.hallazgos.some((h: any) => h.id === hallazgoId)).toBe(false);
  });

  test('10.7: PUT /radiologia/{id}/anotaciones guarda y GET las devuelve', async ({ request }) => {
    const imagenId = await subirImagen(request);

    const items = [
      { x: 10, y: 20, texto: 'ZZ_E2E anotación 1' },
      { x: 55, y: 60, texto: 'ZZ_E2E anotación 2' },
    ];
    const put = await request.put(`${API}/radiologia/${imagenId}/anotaciones`, {
      headers: H,
      data: { items },
    });
    expect(put.status()).toBe(200);

    const get = await request.get(`${API}/radiologia/${imagenId}/anotaciones`, { headers: H });
    expect(get.status()).toBe(200);
    const body = await get.json();
    expect(body.imagen_id).toBe(imagenId);
    expect(body.items).toHaveLength(2);
  });

  test('10.8: PUT /radiologia/{id}/anotaciones sin items es rechazado (422)', async ({ request }) => {
    const imagenId = await subirImagen(request);
    const put = await request.put(`${API}/radiologia/${imagenId}/anotaciones`, { headers: H, data: {} });
    expect(put.status()).toBe(422);
  });

  test('10.9: DELETE /radiologia/{id} elimina la imagen', async ({ request }) => {
    const imagenId = await subirImagen(request);

    const del = await request.delete(`${API}/radiologia/${imagenId}`, { headers: H });
    expect(del.status()).toBe(204);

    const list = await request.get(`${API}/pacientes/${pacienteId}/radiologia`, { headers: H });
    expect(await list.json()).toEqual([]);
  });
});
