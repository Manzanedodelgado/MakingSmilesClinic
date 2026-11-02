/**
 * PASO 11 — Comunicación (Real, Aislado, Estricto)
 *
 * Sin mocks. Solo endpoints que NO envían nada al exterior: la instancia de WhatsApp
 * está conectada de verdad (Evolution), así que /whatsapp/enviar y POST .../mensajes
 * quedan FUERA de la suite E2E — enviarían un mensaje real a un teléfono real.
 *
 * Se testean: lecturas (conversaciones, estadísticas, plantillas, estado IA/WhatsApp,
 * voicebot/health) y operaciones locales reversibles (CRUD de una plantilla ZZ_E2E,
 * pausar/reanudar la IA).
 *
 * Contrato real verificado en /openapi.json + pruebas en vivo (2026-08-29):
 *   GET    /comunicacion/conversaciones           -> 200 {data:[{id,telefono,nombre,pacienteId,estado,...}]}
 *   GET    /comunicacion/estadisticas             -> 200 {conversaciones_abiertas, revisiones_pendientes, ...}
 *   GET    /comunicacion/plantillas               -> 200 {data:[{id,nombre,cuerpo}]}
 *   PUT    /comunicacion/plantillas               -> 200 {id}   body {nombre*, cuerpo*, id?}  (id => editar; sin id => crear)
 *   DELETE /comunicacion/plantillas/{pid}         -> 200
 *   GET    /comunicacion/ia/estado                -> 200 {pausada, hasta, iaActiva}
 *   POST   /comunicacion/ia/pausar                -> 200 {pausada:true, hasta}   body {minutos}
 *   POST   /comunicacion/ia/reanudar              -> 200 {pausada:false}
 *   GET    /comunicacion/whatsapp/estado          -> 200 {evolution, estado, conectado, numero}
 *   GET    /comunicacion/voicebot/health          -> 200 {sip_configurado, canal_activo}
 */
import { test, expect } from '@playwright/test';
import { API, CENTRO_ID } from './fixtures/constants';

const H = { 'X-Centro-Id': String(CENTRO_ID) };

test.describe('Paso 11: Comunicación (Real, Aislado, Estricto)', () => {
  test('11.1: GET /comunicacion/conversaciones devuelve la lista', async ({ request }) => {
    const resp = await request.get(`${API}/comunicacion/conversaciones`, { headers: H });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(Array.isArray(body.data)).toBe(true);
    if (body.data.length > 0) {
      expect(body.data[0]).toHaveProperty('id');
      expect(body.data[0]).toHaveProperty('telefono');
    }
  });

  test('11.2: GET /comunicacion/estadisticas trae contadores coherentes', async ({ request }) => {
    const resp = await request.get(`${API}/comunicacion/estadisticas`, { headers: H });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(typeof body.conversaciones_abiertas).toBe('number');
    expect(body.conversaciones_abiertas).toBeGreaterThanOrEqual(0);
  });

  test('11.3: GET /comunicacion/conversaciones/{id}/mensajes de una conversación real', async ({ request }) => {
    const convs = await (await request.get(`${API}/comunicacion/conversaciones`, { headers: H })).json();
    test.skip(convs.data.length === 0, 'sin conversaciones reales en la BD');

    const convId = convs.data[0].id;
    const resp = await request.get(`${API}/comunicacion/conversaciones/${convId}/mensajes`, { headers: H });
    expect(resp.status()).toBe(200);
  });

  test('11.4: GET /comunicacion/plantillas devuelve el catálogo del centro', async ({ request }) => {
    const resp = await request.get(`${API}/comunicacion/plantillas`, { headers: H });
    expect(resp.status()).toBe(200);
    expect(Array.isArray((await resp.json()).data)).toBe(true);
  });

  test('11.5: PUT /comunicacion/plantillas crea, edita y DELETE elimina una plantilla', async ({ request }) => {
    // crear
    const crear = await request.put(`${API}/comunicacion/plantillas`, {
      headers: H,
      data: { nombre: 'ZZ_E2E plantilla', cuerpo: 'Hola {{nombre}}, mensaje de prueba E2E' },
    });
    expect(crear.status()).toBe(200);
    const plantillaId = (await crear.json()).id;
    expect(plantillaId).toBeGreaterThan(0);

    // aparece en el listado
    const list = await (await request.get(`${API}/comunicacion/plantillas`, { headers: H })).json();
    expect(list.data.some((p: any) => p.id === plantillaId)).toBe(true);

    // editar
    const editar = await request.put(`${API}/comunicacion/plantillas`, {
      headers: H,
      data: { id: plantillaId, nombre: 'ZZ_E2E plantilla editada', cuerpo: 'cuerpo nuevo' },
    });
    expect(editar.status()).toBe(200);

    // borrar
    const borrar = await request.delete(`${API}/comunicacion/plantillas/${plantillaId}`, { headers: H });
    expect(borrar.status()).toBe(200);

    const list2 = await (await request.get(`${API}/comunicacion/plantillas`, { headers: H })).json();
    expect(list2.data.some((p: any) => p.id === plantillaId)).toBe(false);
  });

  test('11.6: PUT /comunicacion/plantillas sin cuerpo es rechazado (422)', async ({ request }) => {
    const resp = await request.put(`${API}/comunicacion/plantillas`, {
      headers: H,
      data: { nombre: 'ZZ_E2E incompleta' },
    });
    expect(resp.status()).toBe(422);
  });

  test('11.7: POST /comunicacion/ia/pausar y /reanudar controlan el estado de la IA', async ({ request }) => {
    const estadoInicial = await (await request.get(`${API}/comunicacion/ia/estado`, { headers: H })).json();

    const pausar = await request.post(`${API}/comunicacion/ia/pausar`, {
      headers: H,
      data: { minutos: 5 },
    });
    expect(pausar.status()).toBe(200);
    expect((await pausar.json()).pausada).toBe(true);

    const estadoPausado = await (await request.get(`${API}/comunicacion/ia/estado`, { headers: H })).json();
    expect(estadoPausado.pausada).toBe(true);

    const reanudar = await request.post(`${API}/comunicacion/ia/reanudar`, { headers: H });
    expect(reanudar.status()).toBe(200);
    expect((await reanudar.json()).pausada).toBe(false);

    // restaura el estado tal como estaba
    if (estadoInicial.pausada) {
      await request.post(`${API}/comunicacion/ia/pausar`, { headers: H, data: { minutos: 60 } });
    }
  });

  test('11.8: GET /comunicacion/whatsapp/estado informa de la conexión', async ({ request }) => {
    const resp = await request.get(`${API}/comunicacion/whatsapp/estado`, { headers: H });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty('conectado');
    expect(body).toHaveProperty('estado');
  });

  test('11.9: GET /comunicacion/voicebot/health responde', async ({ request }) => {
    const resp = await request.get(`${API}/comunicacion/voicebot/health`, { headers: H });
    expect(resp.status()).toBe(200);
    expect(await resp.json()).toHaveProperty('sip_configurado');
  });
});
