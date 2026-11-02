import { test, expect, type Page, type BrowserContext } from "@playwright/test";

/**
 * La línea inferior de «Citas del día» y la de la cabecera azul de la rejilla deben caer en la MISMA fila de píxeles.
 * Se mide sobre lo pintado (captura), no sobre cajas, en estética clásica y 3D, a escala 1 y 2.
 * Ventana de 1920×950: monitor 1920×1080 menos el marco del navegador (ver CLAUDE.md §5), no 1920×1080 exactos.
 * Historial: se desalineaban 15 px (clásico) y 8 px (3D, por un p-2 del panel).
 */
const EMAIL = process.env.MS_EMAIL, PASS = process.env.MS_PASS;

async function filasPintadas(contexto: BrowserContext, png: Buffer, dpr: number) {
  const hoja = await contexto.newPage();   // página en blanco: sin la CSP de la app, que bloquea data: en <img>
  const r = await hoja.evaluate(async ({ b64, dpr }) => {
    const img = new Image(); img.src = "data:image/png;base64," + b64; await img.decode();
    const c = document.createElement("canvas"); c.width = img.width; c.height = img.height;
    const g = c.getContext("2d")!; g.drawImage(img, 0, 0);
    const px = (x: number, y: number) => g.getImageData(Math.round(x * dpr), y, 1, 1).data;
    // x=200: dentro de la cabecera de «Citas del día»; x=700: dentro de la cabecera azul de la rejilla.
    let borde = -1, azul = -1;
    for (let y = 0; y < img.height; y++) {
      const [r1, g1, b1] = px(200, y);
      if (Math.abs(r1 - 0xE0) <= 6 && Math.abs(g1 - 0xE6) <= 6 && Math.abs(b1 - 0xED) <= 6) borde = y;   // última fila de la línea gris-azulada
      const [r2, g2, b2] = px(700, y);
      if (r2 < 60 && g2 > 110 && b2 > 190) azul = y;                                                    // última fila azul de la cabecera
    }
    // Raíl izquierdo (x=8): filas donde cambia de color (separadores entre iconos). Y primera fila azul de la cabecera en x=700.
    let primerAzul = -1;
    for (let y = 0; y < img.height; y++) { const [r3, g3, b3] = px(700, y); if (r3 < 60 && g3 > 110 && b3 > 190) { primerAzul = y; break; } }
    const raiz: number[] = [];
    let ant = px(8, 0);
    for (let y = 1; y < img.height; y++) { const cur = px(8, y); if (Math.abs(ant[0] - cur[0]) + Math.abs(ant[1] - cur[1]) + Math.abs(ant[2] - cur[2]) > 24) raiz.push(y); ant = cur; }
    return { borde, azul, primerAzul, raiz };
  }, { b64: png.toString("base64"), dpr });
  await hoja.close();
  return r;
}

async function entrar(page: Page) {
  await page.goto("/login", { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  await page.locator('input[type="email"]').fill(EMAIL!);
  await page.locator('input[type="password"]').fill(PASS!);
  await Promise.all([page.waitForResponse((r) => r.url().includes("/auth/login")).catch(() => null), page.locator('button[type="submit"]').click()]);
  await page.waitForTimeout(3500);
}

for (const clay of ["0", "1"]) for (const dpr of [1, 2]) {
  test(`cabeceras de la agenda alineadas · estética ${clay === "1" ? "3D" : "clásica"} · escala ${dpr}`, async ({ browser }) => {
    test.skip(!EMAIL || !PASS, "definir MS_EMAIL y MS_PASS");
    const ctx = await browser.newContext({ viewport: { width: 1920, height: 950 }, deviceScaleFactor: dpr, bypassCSP: !!process.env.MS_BYPASS_CSP });
    await ctx.addInitScript((c) => { try { localStorage.setItem("agenda-clay", c); } catch { /* sin almacenamiento */ } }, clay);
    const page = await ctx.newPage();
    await entrar(page);
    await page.goto("/agenda", { waitUntil: "domcontentloaded" });
    await page.getByText("Citas del día").first().waitFor();
    await page.waitForTimeout(2500);
    const png = await page.screenshot({ clip: { x: 0, y: 40, width: 1000, height: 130 } });
    const { borde, azul } = await filasPintadas(ctx, png, dpr);
    // La captura va a escala `dpr`: ambas filas están en píxeles de dispositivo. Tolerancia: 1 píxel de dispositivo.
    expect(borde, "no se encontró la línea de «Citas del día»").toBeGreaterThan(0);
    expect(azul, "no se encontró la cabecera azul de la rejilla").toBeGreaterThan(0);
    expect(Math.abs(borde - azul), `línea en fila ${borde} y cabecera azul termina en ${azul} (px de dispositivo)`).toBeLessThanOrEqual(1);
    // Los separadores del raíl de iconos deben coincidir con el final de la barra de herramientas y con el de la cabecera.
    const { primerAzul, raiz } = await filasPintadas(ctx, png, dpr);
    const cerca = (fila: number) => raiz.some((r) => Math.abs(r - fila) <= 1 * dpr + 1);
    expect(cerca(primerAzul), `raíl sin separador junto al final de la barra de herramientas (fila ${primerAzul}); separadores en ${raiz.join(", ")}`).toBe(true);
    expect(cerca(azul), `raíl sin separador junto al final de la cabecera (fila ${azul}); separadores en ${raiz.join(", ")}`).toBe(true);
    await ctx.close();
  });
}
