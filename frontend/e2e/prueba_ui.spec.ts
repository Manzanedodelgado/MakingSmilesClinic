/**
 * Prueba funcional de la UI con captura visual antes/después de cada acción.
 * Para cada elemento del inventario: navega, captura estado previo, pulsa, captura
 * estado resultante, y registra un resumen automático. Las capturas quedan en
 * e2e/pruebas-ui/NNN_slug_{antes,despues}.png para revisión visual.
 *
 * Ejecutar por partes: PARTE=A|B|C|... npx playwright test e2e/prueba_ui.spec.ts
 */
import fs from 'fs';
import path from 'path';
import { test, expect, Page, Locator } from '@playwright/test';

test.use({ storageState: { cookies: [], origins: [] } });

const EMAIL = 'test_4134@saas-audit.com';
const PASSWORD = 'password123';
const PID = '4767';
const PARTE = process.env.PARTE || 'A';
const DIR = path.join(__dirname, 'pruebas-ui');
const MD = path.join(__dirname, 'RESULTADOS-UI.md');

let n = 0;
// escritura INCREMENTAL: cada w() se vuelca al fichero al momento, nada se pierde si el proceso muere
const w = (s: string) => { fs.appendFileSync(MD, s + '\n'); process.stdout.write(s + '\n'); };
const H2 = (s: string) => w(`\n## ${s}\n`);
function flush(reset = false) {
  if (reset) {
    fs.mkdirSync(DIR, { recursive: true });
    fs.writeFileSync(MD,
      `# Resultados de prueba funcional de la UI\n\n` +
      `Siguiendo \`docs/INVENTARIO-UI.md\`. App real (100.86.41.61) · Test Admin (SUPERADMIN) · paciente 4134.\n` +
      `${new Date().toLocaleString('es-ES')}\n\n` +
      `Cada acción guarda captura \`antes\`/\`después\` en \`e2e/pruebas-ui/\`.\n` +
      `**Leyenda:** ✅ efecto claro · ➡️ navega · 🪟 abre panel · 🔄 llama API · ⚠️ sin cambio visible · 🔲 no encontrado · ❌ error\n\n---\n`);
  }
}

async function login(page: Page) {
  await page.context().clearCookies();
  await page.goto('/login', { waitUntil: 'domcontentloaded' });
  await page.fill('input[type="email"]', EMAIL, { timeout: 5000 });
  await page.fill('input[type="password"]', PASSWORD, { timeout: 5000 });
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/auth/login')).catch(() => null),
    page.locator('button[type="submit"]').click(),
  ]);
  await page.waitForTimeout(4000);
}

async function snap(page: Page, slug: string, sufijo: string) {
  const f = `${String(n).padStart(3, '0')}_${slug}_${sufijo}.png`;
  await page.screenshot({ path: path.join(DIR, f), timeout: 4000 }).catch(() => {});
  return f;
}

/**
 * Prueba un elemento: captura antes, clic, captura después, describe el cambio.
 * `find`: callback que devuelve el locator (se re-evalúa por si la página cambió).
 */
async function E(
  page: Page,
  desc: string,
  find: () => Locator,
  opt: { slug?: string; red?: RegExp; volver?: string; hover?: () => Locator; escapar?: boolean } = {}
) {
  try {
    await Promise.race([
      Eimpl(page, desc, find, opt),
      new Promise((_, rej) => setTimeout(() => rej(new Error('timeout-duro-15s')), 15000)),
    ]);
  } catch (e: any) {
    w(`- ❌ **${desc}** — abortado por timeout duro (15s): ${String(e.message).slice(0, 60)}`);
    await page.keyboard.press('Escape').catch(() => {});
  }
}

async function Eimpl(
  page: Page,
  desc: string,
  find: () => Locator,
  opt: { slug?: string; red?: RegExp; volver?: string; hover?: () => Locator; escapar?: boolean } = {}
) {
  n++;
  const slug = (opt.slug || desc).normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[^\w]+/g, '-').replace(/^-|-$/g, '').toLowerCase().slice(0, 40);

  if (opt.hover) await opt.hover().hover().catch(() => {});
  let loc: Locator;
  try { loc = find(); } catch { w(`- 🔲 **${desc}** — selector inválido`); return; }

  if (!(await loc.first().isVisible({ timeout: 2500 }).catch(() => false))) {
    w(`- 🔲 **${desc}** — no visible`);
    return;
  }
  // el rail lateral se expande con una animación al hover; dar tiempo antes del click
  await loc.first().hover({ timeout: 2000 }).catch(() => {});
  await page.waitForTimeout(500);

  const fA = await snap(page, slug, 'antes');
  const urlA = page.url();
  const htmlA = (await page.locator('body').innerText().catch(() => '')).replace(/\s+/g, ' ');

  const reqP = opt.red ? page.waitForRequest(opt.red, { timeout: 6000 }).catch(() => null) : Promise.resolve(null);

  try {
    await loc.first().click({ timeout: 3000 });
  } catch (e: any) {
    w(`- ❌ **${desc}** — clic falló (${String(e.message).split('\n')[0].slice(0, 80)}) · [antes](pruebas-ui/${fA})`);
    return;
  }
  await page.waitForTimeout(1100);

  const fD = await snap(page, slug, 'despues');
  const urlD = page.url();
  const htmlD = (await page.locator('body').innerText().catch(() => '')).replace(/\s+/g, ' ');
  const req = await reqP;

  const ef: string[] = [];
  if (urlD !== urlA) ef.push(`➡️ \`${new URL(urlD).pathname}\``);
  if (req) ef.push(`🔄 \`${req.method()} ${new URL(req.url()).pathname}\``);
  const modal = page.locator('[role="dialog"], [class*="modal" i], [class*="Modal" i]').first();
  if (await modal.isVisible().catch(() => false)) {
    const t = (await modal.innerText().catch(() => '')).replace(/\s+/g, ' ').slice(0, 70);
    ef.push(`🪟 panel ("${t}")`);
  }
  // diff de texto: cuánto cambió el contenido
  if (urlD === urlA && !ef.length) {
    const cambio = Math.abs(htmlD.length - htmlA.length);
    const distinto = htmlD !== htmlA;
    if (distinto && cambio > 40) ef.push(`✅ el contenido cambia (${cambio} car.)`);
    else if (distinto) ef.push(`⚠️ cambio menor en pantalla`);
  }

  const marca = ef.some((x) => x.startsWith('➡️') || x.startsWith('🔄') || x.startsWith('🪟') || x.startsWith('✅')) ? '' : '⚠️ ';
  w(`- ${marca}**${desc}** — ${ef.length ? ef.join(' · ') : 'clic aceptado, sin cambio visible'}  · [antes](pruebas-ui/${fA}) · [después](pruebas-ui/${fD})`);

  if (opt.escapar !== false) { await page.keyboard.press('Escape').catch(() => {}); await page.waitForTimeout(300); }
  if (opt.volver) { await page.goto(opt.volver, { waitUntil: 'domcontentloaded' }).catch(() => {}); await page.waitForTimeout(800); }
}

// ═══════════════════════════════════════════════════════════════════

test(`prueba UI — parte ${PARTE}`, async ({ page, request }) => {
  test.setTimeout(8 * 60 * 1000); // corto a propósito: si algo cuelga, que muera solo y no bloquee la sesión SSH
  flush(PARTE === 'A1');

  // comprobación de salud: si el frontend dev server no responde, abortar con mensaje claro
  // en vez de producir falsos "sin cambio visible" en cada elemento.
  const salud = await request.get('http://localhost:3000/login', { timeout: 8000 }).catch(() => null);
  if (!salud || salud.status() >= 500) {
    w(`\n\n> ⚠️ **FRONTEND NO RESPONDE** (status ${salud?.status() ?? 'sin respuesta'}) — parte ${PARTE} abortada sin ejecutar. Reiniciar \`npm run dev\` en el servidor antes de reintentar.\n`);
    return;
  }

  if (PARTE === 'A1') {
    // ── auth ──
    await page.context().clearCookies();
    H2('1. `/login`');
    await page.goto('/login', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(800);
    await E(page, 'Icono ojo (ver/ocultar contraseña)', () => page.locator('.lg-eye, button[aria-label*="contrase" i]'), { slug: 'login-ojo', escapar: false });
    await page.fill('input[type="password"]', 'algo', { timeout: 5000 }).catch(() => {});
    await E(page, 'Icono ojo — 2º clic (vuelve a ocultar)', () => page.locator('.lg-eye, button[aria-label*="contrase" i]'), { slug: 'login-ojo2', escapar: false });
    await E(page, 'Checkbox "Recordar usuario"', () => page.locator('input[type="checkbox"]'), { slug: 'login-recordar', escapar: false });
    await E(page, 'Enlace "¿Olvidaste tu contraseña?"', () => page.getByText('¿Olvidaste tu contraseña?'), { slug: 'login-olvido', volver: '/login' });
    await E(page, 'Botón "Acceder" sin credenciales', () => page.getByRole('button', { name: /Acceder/ }), { slug: 'login-acceder-vacio', escapar: false });

    H2('2. `/recuperar`');
    await page.goto('/recuperar', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(800);
    await E(page, 'Botón "Enviar enlace" sin email', () => page.getByRole('button', { name: /enviar enlace/i }), { slug: 'recuperar-vacio', escapar: false });
    await page.fill('input[type="email"]', EMAIL, { timeout: 5000 }).catch(() => {});
    await E(page, 'Botón "Enviar enlace" con email', () => page.getByRole('button', { name: /enviar enlace/i }), { slug: 'recuperar-envio', red: /\/auth\/forgot/, escapar: false });
    await E(page, 'Enlace "← Volver al acceso"', () => page.getByText('Volver al acceso'), { slug: 'recuperar-volver', volver: '/recuperar' });

    H2('3. `/restablecer` (sin token)');
    await page.goto('/restablecer', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(800);
    await E(page, 'Enlace "Solicitar uno nuevo"', () => page.getByText('Solicitar uno nuevo'), { slug: 'restablecer-solicitar' });
  }

  if (PARTE === 'A2') {
    await login(page);
    w(`\n_(login OK → \`${new URL(page.url()).pathname}\`)_\n`);

    H2('0. Chrome — rail lateral');
    for (const [name, re] of [['Inicio', /inicio/], ['Agenda', /agenda/], ['Pacientes', /pacientes/], ['WhatsApp', /comunicacion/], ['Gestoría', /gestoria/], ['Informes', /informes/], ['Config', /configuracion/], ['SuperUser', /superuser/]] as [string, RegExp][]) {
      await page.goto('/inicio', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(900);
      await E(page, `Rail → "${name}"`, () => page.getByRole('button', { name: new RegExp(`${name}`) }).first(), { slug: `rail-${name}` });
    }

    H2('0. Chrome — barra superior');
    await page.goto('/inicio', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1200);
    await E(page, 'Logo "gota" (esquina sup. izq.)', () => page.locator('header').locator('img,svg').first(), { slug: 'top-logo' });
    await E(page, 'Chip "SUPERADMINISTRADOR"', () => page.getByText('SUPERADMINISTRADOR').first(), { slug: 'top-rol' });
    await E(page, '"Test Admin"', () => page.getByText('Test Admin').first(), { slug: 'top-user' });
  }

  if (PARTE === 'B') {
    await login(page);

    H2('4. `/inicio` — Panel');
    await page.goto('/inicio', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1800);
    for (const s of ['WhatsApp', 'Alex', 'Victor', 'Aura', 'Centinela', 'Buzón', 'Drive']) {
      await E(page, `SISTEMAS · "${s}"`, () => page.locator(`text="${s}"`).first(), { slug: `inicio-sist-${s}`, volver: '/inicio' });
    }
    await E(page, 'Tarjeta WHATSAPP SIN RESPONDER · 1ª fila', () => page.locator('text=/hace \\d+ d[ií]as/').first(), { slug: 'inicio-wa-fila', volver: '/inicio' });
    await E(page, 'Tarjeta PRESUPUESTOS SIN RESPUESTA · 1ª fila', () => page.locator('text=/Presupuesto/').first(), { slug: 'inicio-presu-fila', volver: '/inicio' });
    await E(page, 'Tarjeta IMPUESTOS Y PLAZOS · "Modelo 303"', () => page.getByText(/Modelo 303/).first(), { slug: 'inicio-imp-fila', volver: '/inicio' });
    await E(page, 'Tarjeta FACTURAS Y BANCO', () => page.getByText(/FACTURAS Y BANCO/).first(), { slug: 'inicio-fact', volver: '/inicio' });
  }

  if (PARTE === 'B2') {
    await login(page);
    H2('5. `/agenda`');
    await page.goto('/agenda', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(2200);
    await E(page, 'Selector "AGENDA 1" ▾', () => page.getByRole('button', { name: /AGENDA 1/i }), { slug: 'agenda-selector' });
    await page.goto('/agenda', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1500);
    await E(page, 'Flecha "‹" día anterior', () => page.locator('button svg.lucide-chevron-left').first(), { slug: 'agenda-prev', volver: '/agenda' });
    await E(page, 'Flecha "›" día siguiente', () => page.locator('button svg.lucide-chevron-right').first(), { slug: 'agenda-next', volver: '/agenda' });
    await E(page, 'Botón "HOY"', () => page.getByRole('button', { name: /^HOY$/i }), { slug: 'agenda-hoy', volver: '/agenda' });
    await E(page, 'Botón "SEMANA"', () => page.getByRole('button', { name: /^SEMANA$/i }), { slug: 'agenda-semana', volver: '/agenda' });
    await E(page, 'Botón "DÍA"', () => page.getByRole('button', { name: /^D[IÍ]A$/i }), { slug: 'agenda-dia', volver: '/agenda' });
    await E(page, 'Botón "ANULADAS"', () => page.getByRole('button', { name: /ANULADAS/i }), { slug: 'agenda-anuladas', volver: '/agenda' });
    await E(page, 'Desplegable "GABINETES" ▾', () => page.getByRole('button', { name: /GABINETES/i }), { slug: 'agenda-gabinetes', volver: '/agenda' });
    await E(page, 'Desplegable "DOCTORES" ▾', () => page.getByRole('button', { name: /DOCTORES/i }), { slug: 'agenda-doctores', volver: '/agenda' });
    await E(page, 'Botón "+ NUEVA CITA"', () => page.getByRole('button', { name: /NUEVA CITA/i }), { slug: 'agenda-nueva-cita', volver: '/agenda' });
    await E(page, 'Panel dcha · "WHATSAPP URGENTES" 1ª fila', () => page.getByText(/urgencia/i).first(), { slug: 'agenda-wa-urgente', volver: '/agenda' });

    H2('6. `/pacientes` — lista');
    await page.goto('/pacientes', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1600);
    await E(page, 'Cabecera-filtro "ALERTAS"', () => page.getByText('ALERTAS', { exact: true }).first(), { slug: 'pac-h-alertas' });
    await E(page, 'Cabecera-filtro "Edad"', () => page.getByText('Edad', { exact: true }).first(), { slug: 'pac-h-edad' });
    await E(page, 'Cabecera-filtro "Teléfono"', () => page.getByText(/Tel[eé]fono/i).first(), { slug: 'pac-h-tel' });
    await E(page, 'Cabecera-filtro "Tarifa"', () => page.getByText('Tarifa', { exact: true }).first(), { slug: 'pac-h-tarifa' });
    await E(page, 'Botón "+ NUEVO"', () => page.getByRole('button', { name: /^\+?\s*NUEVO$/i }).first(), { slug: 'pac-nuevo' });
    // buscar 4134
    const b = page.locator('input[placeholder*="Buscar" i]').first();
    if (await b.isVisible().catch(() => false)) {
      await b.fill('4134'); await page.waitForTimeout(1600);
      await E(page, 'Buscador "4134" → abrir paciente', () => page.getByText('MANZANEDO').first(), { slug: 'pac-buscar-abrir' });
    }

    H2('7. `/comunicacion` — WhatsApp');
    await page.goto('/comunicacion', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(2500);
    await E(page, 'Botón "⏸ PAUSAR IA"', () => page.getByRole('button', { name: /PAUSAR IA/i }), { slug: 'wa-pausar', red: /ia\/pausar/, volver: '/comunicacion' });
    await page.waitForTimeout(1000);
    await E(page, 'Botón "▶ REANUDAR IA" (tras pausar)', () => page.getByRole('button', { name: /REANUDAR IA/i }), { slug: 'wa-reanudar', red: /ia\/reanudar/, volver: '/comunicacion' });
    await E(page, 'Pestaña "No leídas"', () => page.getByText(/No le[ií]das/).first(), { slug: 'wa-tab-noleidas' });
    await E(page, 'Pestaña "Urgentes"', () => page.getByText(/^Urgentes/).first(), { slug: 'wa-tab-urgentes' });
    await E(page, 'Pestaña "Todas"', () => page.getByText(/^Todas$/).first(), { slug: 'wa-tab-todas' });
    await E(page, '1ª conversación de la lista', () => page.getByText(/URGENTE/i).first(), { slug: 'wa-conv-1', volver: '/comunicacion' });

    H2('11. `/crm`');
    await page.goto('/crm', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(2500);
    await E(page, 'Pestaña "Reactivación"', () => page.getByText('Reactivación', { exact: true }), { slug: 'crm-reactivacion' });
    await E(page, 'Pestaña "Pipeline de presupuestos"', () => page.getByText('Pipeline de presupuestos', { exact: true }), { slug: 'crm-pipeline' });

    H2('12. `/iconos`');
    await page.goto('/iconos', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1200);
    await E(page, 'Icono ilustrado "diente"', () => page.getByText('diente', { exact: true }), { slug: 'iconos-diente' });

    H2('13. `/superuser`');
    await page.goto('/superuser', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1500);
    await E(page, 'Pestaña "CENTINELA"', () => page.getByText('CENTINELA', { exact: true }).first(), { slug: 'su-tab-centinela', volver: '/superuser' });
    await E(page, 'Pestaña "APARIENCIA"', () => page.getByText('APARIENCIA', { exact: true }).first(), { slug: 'su-tab-apariencia', volver: '/superuser' });
    await E(page, 'Pestaña "BASE DE DATOS"', () => page.getByText('BASE DE DATOS', { exact: true }).first(), { slug: 'su-tab-bd', volver: '/superuser' });
    await E(page, 'Pestaña "CENTROS"', () => page.getByText('CENTROS', { exact: true }).first(), { slug: 'su-tab-centros', volver: '/superuser' });
    await E(page, 'Botón "+ NUEVO CENTRO"', () => page.getByRole('button', { name: /NUEVO CENTRO/i }), { slug: 'su-nuevo-centro', volver: '/superuser' });
    await E(page, 'Fila "RUBIO GARCIA DENTAL"', () => page.getByText('RUBIO GARCIA DENTAL').last(), { slug: 'su-fila-centro' });
  }

  if (PARTE === 'C1') {
    await login(page);
    H2('14. `/pacientes/4767/ficha` — Ficha del paciente');
    await page.goto(`/pacientes/${PID}/ficha`, { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(2200);
    await E(page, 'Botón "ALERTAS" (cabecera)', () => page.getByText('ALERTAS', { exact: true }).first(), { slug: 'ficha-alertas', volver: `/pacientes/${PID}/ficha` });
    await E(page, 'Icono portapapeles (odontograma)', () => page.locator('button svg.lucide-clipboard, button[aria-label*="portapapeles" i]').first(), { slug: 'ficha-odo-clip', volver: `/pacientes/${PID}/ficha` });
    await E(page, 'Botón "🎤 CONSULTA"', () => page.getByRole('button', { name: /^CONSULTA$/i }), { slug: 'ficha-consulta', volver: `/pacientes/${PID}/ficha` });
    await E(page, 'Botón "✍ ESCUCHA PRO"', () => page.getByRole('button', { name: /ESCUCHA PRO/i }), { slug: 'ficha-escucha', volver: `/pacientes/${PID}/ficha` });
    await E(page, 'Botón "📋 INSTRUCCIONES"', () => page.getByRole('button', { name: /INSTRUCCIONES/i }), { slug: 'ficha-instrucciones', volver: `/pacientes/${PID}/ficha` });
    await E(page, 'Botón "REVISIÓN / EVALUACIÓN"', () => page.getByRole('button', { name: /REVISI[OÓ]N.*EVALUACI[OÓ]N/i }), { slug: 'ficha-revision', volver: `/pacientes/${PID}/ficha` });
    await E(page, 'Botón "TRATAMIENTO PLANIFICADO"', () => page.getByRole('button', { name: /TRATAMIENTO PLANIFICADO/i }), { slug: 'ficha-tto-plan', volver: `/pacientes/${PID}/ficha` });
    for (const tab of ['Facturas', 'Recibo', 'Primera visita', 'Recetas', 'Consentimientos', 'Informes', 'Otros', 'Todos']) {
      await E(page, `Pestaña documentos "${tab}"`, () => page.getByRole('button', { name: tab, exact: true }), { slug: `ficha-doc-${tab}`, volver: `/pacientes/${PID}/ficha` });
    }
    await E(page, 'Enlace "⚭ Radiología" (multimedia)', () => page.getByText('Radiología', { exact: false }).first(), { slug: 'ficha-multimedia-rx', volver: `/pacientes/${PID}/ficha` });
  }

  if (PARTE === 'C2') {
    await login(page);
    H2('15. `/pacientes/4767/filiacion`');
    await page.goto(`/pacientes/${PID}/filiacion`, { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1600);
    await E(page, 'Checkbox "Tratamiento datos (RGPD)"', () => page.getByText('Tratamiento datos', { exact: false }).first(), { slug: 'fil-rgpd', volver: `/pacientes/${PID}/filiacion` });
    await E(page, 'Chip tarifa "PRIVADA"', () => page.getByText('PRIVADA', { exact: true }), { slug: 'fil-privada', volver: `/pacientes/${PID}/filiacion` });
    await E(page, 'Chip tarifa "SEGURIDAD SOCIAL"', () => page.getByText('SEGURIDAD SOCIAL', { exact: true }), { slug: 'fil-ss', volver: `/pacientes/${PID}/filiacion` });

    H2('16. `/pacientes/4767/alertas`');
    await page.goto(`/pacientes/${PID}/alertas`, { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1600);
    await E(page, 'Botón "+ NUEVA ALERTA"', () => page.getByRole('button', { name: /NUEVA ALERTA/i }), { slug: 'alertas-nueva', volver: `/pacientes/${PID}/alertas` });
    await E(page, 'Botón "GUARDAR" (notas médicas)', () => page.getByRole('button', { name: /^GUARDAR$/i }), { slug: 'alertas-guardar', volver: `/pacientes/${PID}/alertas` });
    await E(page, 'Botón "+ AÑADIR" (medicación)', () => page.getByRole('button', { name: /A[NÑ]ADIR/i }), { slug: 'alertas-anadir-med', volver: `/pacientes/${PID}/alertas` });

    H2('17. `/pacientes/4767/cascabel`');
    await page.goto(`/pacientes/${PID}/cascabel`, { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1800);
    await E(page, 'Icono recargar (anillo adherencia)', () => page.locator('svg.lucide-refresh-cw, svg.lucide-rotate-cw').first(), { slug: 'cascabel-recargar', volver: `/pacientes/${PID}/cascabel` });
    await E(page, '1ª fila historial de citas', () => page.getByText(/Planificad|Solicitada/).first(), { slug: 'cascabel-cita-fila', volver: `/pacientes/${PID}/cascabel` });

    H2('19. `/pacientes/4767/documentos`');
    await page.goto(`/pacientes/${PID}/documentos`, { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1600);
    await E(page, 'Botón "Generar"', () => page.getByRole('button', { name: /^Generar$/i }), { slug: 'docs-generar', volver: `/pacientes/${PID}/documentos` });
    await E(page, 'Botón "Subir documento"', () => page.getByRole('button', { name: /Subir documento/i }), { slug: 'docs-subir', volver: `/pacientes/${PID}/documentos` });
    await E(page, 'Pestaña "Recetas"', () => page.getByRole('button', { name: 'Recetas', exact: true }), { slug: 'docs-tab-recetas', volver: `/pacientes/${PID}/documentos` });
  }

  if (PARTE === 'C3') {
    await login(page);
    H2('20. `/pacientes/4767/odontograma`');
    await page.goto(`/pacientes/${PID}/odontograma`, { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1800);
    await E(page, 'Botón "+ NUEVA EXPLORACIÓN"', () => page.getByRole('button', { name: /NUEVA EXPLORACI[OÓ]N/i }), { slug: 'odo-nueva-exp', volver: `/pacientes/${PID}/odontograma` });
    await E(page, '1er diente del odontograma (clic)', () => page.locator('svg, img').filter({ hasNotText: '' }).nth(3), { slug: 'odo-diente', volver: `/pacientes/${PID}/odontograma` });

    H2('21. `/pacientes/4767/periodontograma`');
    await page.goto(`/pacientes/${PID}/periodontograma`, { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1600);
    await E(page, 'Botón "+ NUEVO ESTUDIO"', () => page.getByRole('button', { name: /NUEVO ESTUDIO/i }).first(), { slug: 'perio-nuevo', volver: `/pacientes/${PID}/periodontograma` });

    H2('22. `/pacientes/4767/plan-econ`');
    await page.goto(`/pacientes/${PID}/plan-econ`, { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1600);
    await E(page, 'Pestaña "DOCUMENTOS"', () => page.getByRole('button', { name: /^DOCUMENTOS$/i }), { slug: 'planecon-tab-docs', volver: `/pacientes/${PID}/plan-econ` });
    await E(page, 'Pestaña "MOVIMIENTOS"', () => page.getByRole('button', { name: /^MOVIMIENTOS$/i }), { slug: 'planecon-tab-mov', volver: `/pacientes/${PID}/plan-econ` });
  }

  if (PARTE === 'C4') {
    await login(page);
    H2('23. `/pacientes/4767/presupuestos`');
    await page.goto(`/pacientes/${PID}/presupuestos`, { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(2200);
    await E(page, 'Botón "+ NUEVO PRESUPUESTO"', () => page.getByRole('button', { name: /NUEVO PRESUPUESTO/i }), { slug: 'presu-nuevo', volver: `/pacientes/${PID}/presupuestos` });
    await E(page, 'Botón "Cargar plantilla"', () => page.getByRole('button', { name: /Cargar plantilla/i }), { slug: 'presu-plantilla', volver: `/pacientes/${PID}/presupuestos` });
    await E(page, 'Icono guardar (barra desglose)', () => page.locator('svg.lucide-save').first(), { slug: 'presu-guardar', volver: `/pacientes/${PID}/presupuestos` });
    await E(page, 'Icono imprimir (barra desglose)', () => page.locator('svg.lucide-printer').first(), { slug: 'presu-imprimir', volver: `/pacientes/${PID}/presupuestos` });
    await E(page, 'Selector "Todos los estados" ▾', () => page.getByRole('button', { name: /Todos los estados/i }), { slug: 'presu-estados', volver: `/pacientes/${PID}/presupuestos` });

    H2('24. `/pacientes/4767/radiologia`');
    await page.goto(`/pacientes/${PID}/radiologia`, { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1800);
    await E(page, 'Botón "PPTX"', () => page.getByRole('button', { name: /PPTX/i }), { slug: 'rx-pptx', volver: `/pacientes/${PID}/radiologia` });
    await E(page, 'Botón "Superponer"', () => page.getByRole('button', { name: /Superponer/i }), { slug: 'rx-superponer', volver: `/pacientes/${PID}/radiologia` });
    await E(page, 'Botón "DICOM"', () => page.getByRole('button', { name: /DICOM/i }), { slug: 'rx-dicom', volver: `/pacientes/${PID}/radiologia` });
    await E(page, 'Botón "Evolución"', () => page.getByRole('button', { name: /Evoluci[oó]n/i }), { slug: 'rx-evolucion', volver: `/pacientes/${PID}/radiologia` });
    await E(page, 'Icono lápiz (editar imagen)', () => page.locator('svg.lucide-pencil, svg.lucide-edit').first(), { slug: 'rx-editar', volver: `/pacientes/${PID}/radiologia` });
    await E(page, 'Selector de tipo de imagen ▾', () => page.locator('select').first(), { slug: 'rx-tipo-select', volver: `/pacientes/${PID}/radiologia` });
  }

  if (PARTE === 'D1') {
    await login(page);
    H2('25. `/configuracion/clinica/centro`');
    await page.goto('/configuracion/clinica/centro', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1800);
    await E(page, 'Pestaña "AGENDA"', () => page.getByRole('button', { name: /^AGENDA$/i }), { slug: 'cfg-clinica-tab-agenda', volver: '/configuracion/clinica/centro' });
    await E(page, 'Pestaña "PERSONAL"', () => page.getByRole('button', { name: /^PERSONAL$/i }), { slug: 'cfg-clinica-tab-personal', volver: '/configuracion/clinica/centro' });
    await E(page, 'Pestaña "COLABORADORES"', () => page.getByRole('button', { name: /^COLABORADORES$/i }), { slug: 'cfg-clinica-tab-colab', volver: '/configuracion/clinica/centro' });
    await E(page, 'Checkbox día "Lunes" (horario)', () => page.getByText('Lunes', { exact: true }).locator('..').locator('input[type=checkbox]').first(), { slug: 'cfg-clinica-lunes', volver: '/configuracion/clinica/centro' });
    await E(page, 'Botón "+ AÑADIR" (día festivo)', () => page.getByRole('button', { name: /A[ÑN]ADIR/i }), { slug: 'cfg-clinica-festivo', volver: '/configuracion/clinica/centro' });

    H2('26. `/configuracion/admin/diseno`');
    await page.goto('/configuracion/admin/diseno', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1800);
    await E(page, 'Pestaña "DOCUMENTOS"', () => page.getByRole('button', { name: /^DOCUMENTOS$/i }), { slug: 'cfg-admin-tab-docs', volver: '/configuracion/admin/diseno' });
    await E(page, 'Pestaña "TABLAS"', () => page.getByRole('button', { name: /^TABLAS$/i }), { slug: 'cfg-admin-tab-tablas', volver: '/configuracion/admin/diseno' });
    await E(page, 'Item lista "Receta"', () => page.getByText('Receta', { exact: true }).first(), { slug: 'cfg-admin-item-receta', volver: '/configuracion/admin/diseno' });
    await E(page, 'Sub-pestaña "HTML avanzado"', () => page.getByText('HTML avanzado', { exact: false }), { slug: 'cfg-admin-html', volver: '/configuracion/admin/diseno' });
    await E(page, 'Botón "GUARDAR"', () => page.getByRole('button', { name: /^GUARDAR$/i }), { slug: 'cfg-admin-guardar', volver: '/configuracion/admin/diseno' });
  }

  if (PARTE === 'D2') {
    await login(page);
    H2('27. `/configuracion/admin/documentos`');
    await page.goto('/configuracion/admin/documentos', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1800);
    await E(page, 'Sub-pestaña "CONSENTIMIENTOS"', () => page.getByRole('button', { name: /CONSENTIMIENTOS/i }), { slug: 'cfg-docs-tab-consent', volver: '/configuracion/admin/documentos' });
    await E(page, 'Sub-pestaña "PRIMERA VISITA"', () => page.getByRole('button', { name: /PRIMERA VISITA/i }), { slug: 'cfg-docs-tab-1v', volver: '/configuracion/admin/documentos' });
    await E(page, 'Sub-pestaña "RECOMENDACIONES"', () => page.getByRole('button', { name: /RECOMENDACIONES/i }), { slug: 'cfg-docs-tab-reco', volver: '/configuracion/admin/documentos' });
    await E(page, 'Sub-pestaña "CUESTIONARIOS"', () => page.getByRole('button', { name: /CUESTIONARIOS/i }), { slug: 'cfg-docs-tab-cuest', volver: '/configuracion/admin/documentos' });
    await E(page, 'Categoría "CONSERVADORA / ENDODONCIA"', () => page.getByText('CONSERVADORA', { exact: false }).first(), { slug: 'cfg-docs-categoria', volver: '/configuracion/admin/documentos' });

    H2('28. `/configuracion/admin/tablas`');
    await page.goto('/configuracion/admin/tablas', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1800);
    await E(page, 'Campo "Buscar tabla…"', () => page.locator('input[placeholder*="Buscar tabla" i]'), { slug: 'cfg-tablas-buscar', volver: '/configuracion/admin/tablas' });
    await E(page, 'Item tabla "agendas"', () => page.getByText('agendas', { exact: true }), { slug: 'cfg-tablas-agendas', volver: '/configuracion/admin/tablas' });
    await E(page, 'Item tabla "auditoria"', () => page.getByText('auditoria', { exact: true }), { slug: 'cfg-tablas-auditoria', volver: '/configuracion/admin/tablas' });

    H2('30. `/configuracion/conectores/whatsapp`');
    await page.goto('/configuracion/conectores/whatsapp', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1800);
    await E(page, 'Pestaña "VOICEBOT"', () => page.getByRole('button', { name: /^VOICEBOT$/i }), { slug: 'cfg-conn-tab-voicebot', volver: '/configuracion/conectores/whatsapp' });
    await E(page, 'Pestaña "MAIL"', () => page.getByRole('button', { name: /^MAIL$/i }), { slug: 'cfg-conn-tab-mail', volver: '/configuracion/conectores/whatsapp' });
    await E(page, 'Pestaña "DRIVE"', () => page.getByRole('button', { name: /^DRIVE$/i }), { slug: 'cfg-conn-tab-drive', volver: '/configuracion/conectores/whatsapp' });
    await E(page, 'Pestaña "RADIOGRAFÍAS"', () => page.getByRole('button', { name: /RADIOGRAF/i }), { slug: 'cfg-conn-tab-rx', volver: '/configuracion/conectores/whatsapp' });
    await E(page, 'Pestaña "SERVIDOR"', () => page.getByRole('button', { name: /^SERVIDOR$/i }), { slug: 'cfg-conn-tab-servidor', volver: '/configuracion/conectores/whatsapp' });
    await E(page, 'Botón "ACTUALIZAR" (estado)', () => page.getByRole('button', { name: /ACTUALIZAR/i }), { slug: 'cfg-conn-actualizar', volver: '/configuracion/conectores/whatsapp' });
    await E(page, 'Botón "OBTENER QR"', () => page.getByRole('button', { name: /OBTENER QR/i }), { slug: 'cfg-conn-qr', volver: '/configuracion/conectores/whatsapp' });
  }

  if (PARTE === 'D3') {
    await login(page);
    H2('31. `/configuracion/automatizaciones/reglas`');
    await page.goto('/configuracion/automatizaciones/reglas', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1800);
    await E(page, 'Toggle "Envío de automatizaciones"', () => page.locator('input[type=checkbox], [role=switch]').first(), { slug: 'cfg-auto-toggle-motor', volver: '/configuracion/automatizaciones/reglas' });
    await E(page, 'Filtro "CITAS"', () => page.getByRole('button', { name: /^CITAS/i }), { slug: 'cfg-auto-filtro-citas', volver: '/configuracion/automatizaciones/reglas' });
    await E(page, 'Filtro "PACIENTES"', () => page.getByRole('button', { name: /^PACIENTES/i }), { slug: 'cfg-auto-filtro-pac', volver: '/configuracion/automatizaciones/reglas' });
    await E(page, 'Toggle ON/OFF 1ª regla', () => page.locator('table input[type=checkbox], table [role=switch]').first(), { slug: 'cfg-auto-toggle-regla', volver: '/configuracion/automatizaciones/reglas' });
    await E(page, 'Pestaña "EDITOR"', () => page.getByRole('button', { name: /^EDITOR$/i }), { slug: 'cfg-auto-tab-editor', volver: '/configuracion/automatizaciones/reglas' });
    await E(page, 'Pestaña "PLANTILLAS"', () => page.getByRole('button', { name: /^PLANTILLAS$/i }), { slug: 'cfg-auto-tab-plantillas', volver: '/configuracion/automatizaciones/reglas' });

    H2('32. `/configuracion/flujos/flujos`');
    await page.goto('/configuracion/flujos/flujos', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1800);
    await E(page, 'Tarjeta flujo "Urgencia / Dolor"', () => page.getByText('Urgencia / Dolor', { exact: false }), { slug: 'cfg-flujos-urgencia', volver: '/configuracion/flujos/flujos' });
    await E(page, 'Pestaña "EDITOR"', () => page.getByRole('button', { name: /^EDITOR$/i }), { slug: 'cfg-flujos-tab-editor', volver: '/configuracion/flujos/flujos' });

    H2('33. `/configuracion/agentes/alex`');
    await page.goto('/configuracion/agentes/alex', { waitUntil: 'domcontentloaded' }); await page.waitForTimeout(1800);
    await E(page, 'Pestaña "ENTRENAMIENTO"', () => page.getByRole('button', { name: /ENTRENAMIENTO/i }), { slug: 'cfg-agentes-tab-entren', volver: '/configuracion/agentes/alex' });
    await E(page, 'Pestaña "GESTOR IA (FACTURACIÓN)"', () => page.getByRole('button', { name: /GESTOR IA/i }), { slug: 'cfg-agentes-tab-gestoria', volver: '/configuracion/agentes/alex' });
    await E(page, 'Pestaña "MODELOS DE IA"', () => page.getByRole('button', { name: /MODELOS DE IA/i }), { slug: 'cfg-agentes-tab-modelos', volver: '/configuracion/agentes/alex' });
    await E(page, 'Pestaña "AGENTES"', () => page.getByRole('button', { name: /^AGENTES$/i }), { slug: 'cfg-agentes-tab-agentes', volver: '/configuracion/agentes/alex' });
    await E(page, 'Pestaña "CENTINELA (SALUD)"', () => page.getByRole('button', { name: /CENTINELA/i }), { slug: 'cfg-agentes-tab-centinela', volver: '/configuracion/agentes/alex' });
    await E(page, 'Botón "+ AÑADIR REGLA"', () => page.getByRole('button', { name: /A[ÑN]ADIR REGLA/i }), { slug: 'cfg-agentes-anadir-regla', volver: '/configuracion/agentes/alex' });
  }

  flush();
  w(`\n_(parte ${PARTE} escrita — ${n} elementos)_`);
  expect(true).toBe(true);
});
