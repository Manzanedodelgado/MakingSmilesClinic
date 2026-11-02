/**
 * Captura de pantalla de TODA la web navegable.
 *
 * Login real por UI. Recorre cada ruta (params resueltos: [id]->4767 paciente 4134),
 * captura la pantalla, y en las pantallas con pestañas internas conocidas pincha cada
 * pestaña por su texto exacto y vuelve a capturar.
 *
 * Salida: e2e/screenshots/*.png  +  e2e/screenshots/index.html
 * Ejecutar: npx playwright test e2e/capturas.spec.ts --project=chromium
 */
import fs from 'fs';
import path from 'path';
import { test, expect, Page } from '@playwright/test';

test.use({ storageState: { cookies: [], origins: [] } }); // este spec gestiona su sesión

const EMAIL = 'test_4134@saas-audit.com';
const PASSWORD = 'password123';
const P = '4767'; // id interno del paciente real 4134
const OUT = path.join(__dirname, 'screenshots');

/** ruta -> pestañas internas (texto exacto del botón/enlace) a capturar además de la vista base */
interface Ruta {
  slug: string;
  url: string;
  grupo: string;
  tabs?: string[];
  fullPage?: boolean; // por defecto true; false en pantallas con scroll infinito / grid en vivo
}

const RUTAS: Ruta[] = [
  // auth (sin sesión)
  { grupo: 'auth', slug: 'login', url: '/login' },
  { grupo: 'auth', slug: 'recuperar', url: '/recuperar' },
  { grupo: 'auth', slug: 'restablecer', url: '/restablecer' },

  // núcleo
  { grupo: 'app', slug: 'inicio', url: '/inicio' },
  { grupo: 'app', slug: 'agenda', url: '/agenda', fullPage: false },
  { grupo: 'app', slug: 'pacientes-lista', url: '/pacientes' },
  { grupo: 'app', slug: 'comunicacion', url: '/comunicacion', fullPage: false },
  { grupo: 'app', slug: 'gestoria', url: '/gestoria' },
  { grupo: 'app', slug: 'gestoria-produccion', url: '/gestoria/produccion' },
  { grupo: 'app', slug: 'gestoria-facturacion', url: '/gestoria/facturacion' },
  { grupo: 'app', slug: 'informes', url: '/informes' },
  { grupo: 'app', slug: 'crm', url: '/crm' },
  { grupo: 'app', slug: 'iconos', url: '/iconos' },
  { grupo: 'app', slug: 'superuser', url: '/superuser' },

  // paciente 4134
  { grupo: 'paciente', slug: 'paciente', url: `/pacientes/${P}` },
  {
    grupo: 'paciente',
    slug: 'paciente-ficha',
    url: `/pacientes/${P}/ficha`,
    tabs: ['Facturas', 'Recibo', 'Primera visita', 'Recetas', 'Consentimientos', 'Informes', 'Otros', 'Todos'],
  },
  { grupo: 'paciente', slug: 'paciente-filiacion', url: `/pacientes/${P}/filiacion` },
  { grupo: 'paciente', slug: 'paciente-alertas', url: `/pacientes/${P}/alertas` },
  { grupo: 'paciente', slug: 'paciente-cascabel', url: `/pacientes/${P}/cascabel` },
  { grupo: 'paciente', slug: 'paciente-consulta', url: `/pacientes/${P}/consulta`, fullPage: false },
  { grupo: 'paciente', slug: 'paciente-documentos', url: `/pacientes/${P}/documentos` },
  { grupo: 'paciente', slug: 'paciente-odontograma', url: `/pacientes/${P}/odontograma` },
  { grupo: 'paciente', slug: 'paciente-periodontograma', url: `/pacientes/${P}/periodontograma` },
  { grupo: 'paciente', slug: 'paciente-plan-econ', url: `/pacientes/${P}/plan-econ` },
  { grupo: 'paciente', slug: 'paciente-presupuestos', url: `/pacientes/${P}/presupuestos` },
  { grupo: 'paciente', slug: 'paciente-radiologia', url: `/pacientes/${P}/radiologia` },

  // configuración: clínica (4 pestañas en la misma pantalla)
  {
    grupo: 'config',
    slug: 'config-clinica',
    url: '/configuracion/clinica/centro',
    tabs: ['CENTRO', 'AGENDA', 'PERSONAL', 'COLABORADORES'],
  },
  // configuración: admin
  { grupo: 'config', slug: 'config-admin-diseno', url: '/configuracion/admin/diseno' },
  { grupo: 'config', slug: 'config-admin-documentos', url: '/configuracion/admin/documentos' },
  { grupo: 'config', slug: 'config-admin-tablas', url: '/configuracion/admin/tablas' },
  { grupo: 'config', slug: 'config-admin-predisenados-tratamientos', url: '/configuracion/admin/predisenados-tratamientos' },
  { grupo: 'config', slug: 'config-admin-presupuestos-predisenados', url: '/configuracion/admin/presupuestos-predisenados' },
  // configuración: resto
  { grupo: 'config', slug: 'config-conectores-whatsapp', url: '/configuracion/conectores/whatsapp' },
  { grupo: 'config', slug: 'config-automatizaciones-reglas', url: '/configuracion/automatizaciones/reglas' },
  { grupo: 'config', slug: 'config-flujos', url: '/configuracion/flujos/flujos' },
  { grupo: 'config', slug: 'config-agentes-alex', url: '/configuracion/agentes/alex' },
];

const AUTH = new Set(['login', 'recuperar', 'restablecer']);

interface Shot { file: string; grupo: string; ruta: string; titulo: string; nota: string }
const shots: Shot[] = [];

async function estabiliza(page: Page) {
  await page.waitForLoadState('domcontentloaded').catch(() => {});
  await page.waitForTimeout(1500);
}

async function captura(page: Page, slug: string, grupo: string, ruta: string, fullPage: boolean, nota = '') {
  const file = `${String(shots.length + 1).padStart(3, '0')}_${slug}.png`;
  try {
    await page.screenshot({ path: path.join(OUT, file), fullPage, timeout: 15000 });
  } catch {
    await page.screenshot({ path: path.join(OUT, file), timeout: 15000 }).catch(() => {});
  }
  const titulo = (await page.title().catch(() => '')) || slug;
  shots.push({ file, grupo, ruta, titulo, nota });
  process.stdout.write(`  📸 ${file}  ${ruta}${nota ? '  · ' + nota : ''}\n`);
}

test('capturas de toda la web', async ({ page, context }) => {
  test.setTimeout(25 * 60 * 1000);

  fs.mkdirSync(OUT, { recursive: true });
  for (const f of fs.readdirSync(OUT)) if (f.endsWith('.png') || f === 'index.html') fs.rmSync(path.join(OUT, f));

  // 1) auth sin sesión
  await context.clearCookies();
  for (const r of RUTAS.filter((r) => AUTH.has(r.slug))) {
    await page.goto(r.url, { waitUntil: 'domcontentloaded' }).catch(() => {});
    await estabiliza(page);
    await captura(page, r.slug, r.grupo, r.url, true);
  }

  // 2) login real por UI
  process.stdout.write('\n  🔐 login por UI...\n');
  await page.goto('/login', { waitUntil: 'domcontentloaded' });
  await page.locator('input[type="email"]').fill(EMAIL);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/auth/login')).catch(() => null),
    page.locator('button[type="submit"]').click(),
  ]);
  await page.waitForTimeout(4000);
  if (new URL(page.url()).pathname.startsWith('/login')) {
    await page.goto('/inicio', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
  }
  process.stdout.write(`  🔓 sesión -> ${page.url()}\n`);

  // 3) rutas con sesión
  for (const r of RUTAS.filter((r) => !AUTH.has(r.slug))) {
    const fp = r.fullPage !== false;
    try {
      await page.goto(r.url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    } catch {
      process.stdout.write(`  ⚠️  goto lento: ${r.url}\n`);
    }
    await estabiliza(page);
    await captura(page, r.slug, r.grupo, r.url, fp);

    // pestañas internas: clic + captura, cada una aislada con timeout propio
    for (const tab of r.tabs ?? []) {
      try {
        const loc = page.getByRole('button', { name: tab, exact: true })
          .or(page.getByRole('tab', { name: tab, exact: true }))
          .or(page.getByText(tab, { exact: true }))
          .first();
        await loc.click({ timeout: 4000 });
        await page.waitForTimeout(1200);
        const s = tab.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^\w]+/g, '-').toLowerCase();
        await captura(page, `${r.slug}--${s}`, r.grupo, r.url, fp, `pestaña: ${tab}`);
      } catch {
        process.stdout.write(`  ·  pestaña omitida: ${tab} (${r.url})\n`);
      }
    }
    // cierra cualquier modal abierto por los clics de pestaña antes de la siguiente ruta
    await page.keyboard.press('Escape').catch(() => {});
    await page.waitForTimeout(300);
  }

  // 4) índice HTML
  const porGrupo = shots.reduce<Record<string, Shot[]>>((a, s) => ((a[s.grupo] ??= []).push(s), a), {});
  const html = `<!doctype html><meta charset="utf-8"><title>Capturas · MakingSmiles Studio</title>
<style>
 body{font:14px/1.5 system-ui;margin:0;background:#0f1115;color:#e6e6e6}
 header{padding:20px 28px;background:#161a22;border-bottom:1px solid #262b36}
 h1{margin:0;font-size:18px}.meta{color:#8b93a1;font-size:12px;margin-top:4px}
 h2{margin:30px 28px 10px;font-size:15px;color:#9ecbff;text-transform:capitalize}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:18px;padding:0 28px 28px}
 .card{background:#161a22;border:1px solid #262b36;border-radius:10px;overflow:hidden}
 .card img{width:100%;display:block;background:#fff;max-height:250px;object-fit:cover;object-position:top}
 .cap{padding:10px 12px}.ruta{font:12px ui-monospace,monospace;color:#7ee0b8;word-break:break-all}
 .titulo{font-size:12px;color:#c9cfda;margin-top:3px}.nota{font-size:11px;color:#e0a96d;margin-top:3px}
</style>
<header><h1>Capturas · MakingSmiles Studio</h1>
<div class="meta">${shots.length} capturas · ${new Date().toLocaleString('es-ES')} · paciente 4134 · host 100.86.41.61</div></header>
${Object.entries(porGrupo).map(([g, ss]) => `<h2>${g} — ${ss.length}</h2><div class="grid">${ss.map((s) =>
  `<div class="card"><a href="${s.file}" target="_blank"><img src="${s.file}" loading="lazy"></a>
  <div class="cap"><div class="ruta">${s.ruta}</div><div class="titulo">${s.titulo}</div>${s.nota ? `<div class="nota">${s.nota}</div>` : ''}</div></div>`).join('')}</div>`).join('')}`;
  fs.writeFileSync(path.join(OUT, 'index.html'), html);
  process.stdout.write(`\n✅ ${shots.length} capturas + index.html en ${OUT}\n`);
  expect(shots.length).toBeGreaterThan(35);
});
