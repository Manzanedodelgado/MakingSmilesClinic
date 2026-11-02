import { test, expect } from "@playwright/test";
import { FICHA_LAYOUT_DEFAULT, FICHA_LAYOUT_IDS, esLayoutValido } from "./fichaLayoutDefault";

test("el layout por defecto es válido", () => {
  expect(esLayoutValido(FICHA_LAYOUT_DEFAULT)).toBe(true);
});

test("rechaza null", () => {
  expect(esLayoutValido(null)).toBe(false);
});

test("rechaza una caja con w=13", () => {
  const roto = FICHA_LAYOUT_DEFAULT.map((c, i) => (i === 0 ? { ...c, w: 13 } : c));
  expect(esLayoutValido(roto)).toBe(false);
});

test("rechaza coordenadas decimales", () => {
  const roto = FICHA_LAYOUT_DEFAULT.map((c, i) => (i === 0 ? { ...c, x: 0.5 } : c));
  expect(esLayoutValido(roto)).toBe(false);
});

test("las cajas de la ficha son estas siete, en este orden", () => {
  expect([...FICHA_LAYOUT_IDS]).toEqual(["paciente", "alertas", "medicacion", "citas", "historial", "odontograma", "multimedia"]);
});

test("ninguna caja del layout por defecto se solapa con otra", () => {
  const L = FICHA_LAYOUT_DEFAULT;
  for (let i = 0; i < L.length; i++) for (let j = i + 1; j < L.length; j++) {
    const a = L[i], b = L[j];
    const solapa = a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
    expect(solapa, `${a.i} y ${b.i}`).toBe(false);
  }
});

test("primera columna: paciente, alertas, medicación y citas apiladas en ese orden", () => {
  const col = ["paciente", "alertas", "medicacion", "citas"].map((id) => FICHA_LAYOUT_DEFAULT.find((c) => c.i === id)!);
  expect(col.every((c) => c.x === 0 && c.w === 2)).toBe(true);
  expect(col.map((c) => c.y)).toEqual([...col.map((c) => c.y)].sort((a, b) => a - b));
  expect(col[0].y).toBe(0);
});

test("historial y odontograma son las columnas 2 y 3 y multimedia va debajo de ambas", () => {
  const g = (id: string) => FICHA_LAYOUT_DEFAULT.find((c) => c.i === id)!;
  expect(g("historial").x).toBe(2);
  expect(g("odontograma").x).toBe(g("historial").x + g("historial").w);
  expect(g("odontograma").h).toBeGreaterThanOrEqual(9);
  expect(g("multimedia").x).toBe(2);
  expect(g("multimedia").x + g("multimedia").w).toBe(12);
  expect(g("multimedia").y).toBe(Math.max(g("historial").y + g("historial").h, g("odontograma").y + g("odontograma").h));
});

test("el layout por defecto ocupa 21 filas", () => {
  expect(Math.max(...FICHA_LAYOUT_DEFAULT.map((c) => c.y + c.h))).toBe(21);
});

test("un layout guardado con las 4 cajas antiguas ya no es válido y la ficha usará el nuevo", () => {
  const antiguo = [
    { i: "historial", x: 0, y: 0, w: 8, h: 9 }, { i: "nuevo_acto", x: 0, y: 9, w: 8, h: 10 },
    { i: "odontograma", x: 8, y: 0, w: 4, h: 9 }, { i: "multimedia", x: 8, y: 9, w: 4, h: 10 },
  ];
  expect(esLayoutValido(antiguo)).toBe(false);
});
