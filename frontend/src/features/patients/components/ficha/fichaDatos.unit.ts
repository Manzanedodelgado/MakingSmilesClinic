import { test, expect } from "@playwright/test";
import type { ActoClinico } from "../../types/patient";
import { agruparVisitas, extraerMotivo, fechaCorta, alertasImportantes, ultimasCitas } from "./fichaDatos";

let n = 0;
const acto = (p: Partial<ActoClinico> = {}): ActoClinico => ({
  id: ++n, fecha: "2026-03-01", piezas: null, doctor: "Ana", tratamiento: "Revisión",
  observaciones: null, importe: 0, estado: "realizado", facturado: false, ...p,
});

test("agruparVisitas de nada devuelve nada", () => {
  expect(agruparVisitas([])).toEqual([]);
});

test("agruparVisitas junta en una visita los actos del mismo día", () => {
  const v = agruparVisitas([acto({ tratamiento: "Limpieza" }), acto({ tratamiento: "Revisión" })]);
  expect(v).toHaveLength(1);
  expect(v[0].tratamientos).toEqual(["Limpieza", "Revisión"]);
});

test("agruparVisitas trata como el mismo día una fecha con hora y otra sin ella", () => {
  const v = agruparVisitas([acto({ fecha: "2026-03-01T10:00:00" }), acto({ fecha: "2026-03-01" })]);
  expect(v).toHaveLength(1);
  expect(v[0].fecha).toBe("2026-03-01");
});

test("agruparVisitas ordena de más reciente a más antigua y deja la fecha nula al final", () => {
  const v = agruparVisitas([acto({ fecha: null }), acto({ fecha: "2026-01-10" }), acto({ fecha: "2026-05-02" })]);
  expect(v.map((x) => x.fecha)).toEqual(["2026-05-02", "2026-01-10", null]);
});

test("agruparVisitas lista a los doctores del día sin repetirlos", () => {
  const v = agruparVisitas([acto({ doctor: "Ana" }), acto({ doctor: "Luis" }), acto({ doctor: "Ana" })]);
  expect(v[0].doctor).toBe("Ana, Luis");
});

test("extraerMotivo de nada devuelve null", () => {
  expect(extraerMotivo([])).toBeNull();
});

test("extraerMotivo devuelve lo que cuenta el paciente hasta el siguiente apartado", () => {
  expect(extraerMotivo([acto({ observaciones: "S: Dolor al masticar · O: Caries 36" })])).toBe("Dolor al masticar");
});

test("extraerMotivo corta también en Dx y en Plan", () => {
  expect(extraerMotivo([acto({ observaciones: "S: Fiebre · Dx: Pulpitis" })])).toBe("Fiebre");
  expect(extraerMotivo([acto({ observaciones: "S: Molestia · Plan: Endodoncia" })])).toBe("Molestia");
});

test("extraerMotivo usa un acto anterior si el más reciente no tiene motivo", () => {
  const nuevo = acto({ id: 90, fecha: "2026-03-01", observaciones: "PAGO: RECONSTRUCCION" });
  const viejo = acto({ id: 80, fecha: "2026-01-10", observaciones: "S: Revisión" });
  expect(extraerMotivo([nuevo, viejo])).toBe("Revisión");
});

test("extraerMotivo no se inventa nada con observaciones nulas o sin prefijo S", () => {
  expect(extraerMotivo([acto({ observaciones: null })])).toBeNull();
  expect(extraerMotivo([acto({ observaciones: "PAGO: RECONSTRUCCION" })])).toBeNull();
});

test("extraerMotivo con la misma fecha gana el acto de id mayor", () => {
  const a = acto({ id: 5, fecha: "2026-03-01", observaciones: "S: Primero" });
  const b = acto({ id: 7, fecha: "2026-03-01", observaciones: "S: Segundo" });
  expect(extraerMotivo([a, b])).toBe("Segundo");
});

test("fechaCorta pone día/mes/año, ignora la hora y avisa si no hay fecha", () => {
  expect(fechaCorta("2026-03-01")).toBe("01/03/2026");
  expect(fechaCorta("2026-03-01T23:30:00")).toBe("01/03/2026");
  expect(fechaCorta(null)).toBe("Sin fecha");
});

const alerta = (p: object) => ({ id: 1, texto: "x", severidad: null, activo: true, fecha: "2026-01-01", ...p }) as never;

test("alertasImportantes pone primero las graves, luego moderadas y leves, y a igual gravedad la más reciente", () => {
  const r = alertasImportantes([
    alerta({ id: 1, severidad: "LEVE", fecha: "2026-05-01" }),
    alerta({ id: 2, severidad: "GRAVE", fecha: "2026-01-01" }),
    alerta({ id: 3, severidad: "GRAVE", fecha: "2026-03-01" }),
    alerta({ id: 4, severidad: "MODERADA", fecha: "2026-04-01" }),
  ]);
  expect(r.map((a) => a.id)).toEqual([3, 2, 4, 1]);
});

test("alertasImportantes corta en 5, deja las sin severidad al final y no falla con nada", () => {
  expect(alertasImportantes([])).toEqual([]);
  const muchas = Array.from({ length: 8 }, (_, i) => alerta({ id: i + 1, severidad: i === 0 ? null : "LEVE", fecha: `2026-01-0${i + 1}` }));
  const r = alertasImportantes(muchas);
  expect(r).toHaveLength(5);
  expect(r.map((a) => a.id)).not.toContain(1);
});

const cita = (p: Partial<{ id: number; fecha: string; hora: string }>) => ({ id: 1, fecha: "2026-03-01", hora: "10:00", ...p });

test("ultimasCitas devuelve las 5 más recientes hasta hoy, de más nueva a más antigua", () => {
  const cs = ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01", "2026-05-01", "2026-06-01", "2026-07-01"].map((f, i) => cita({ id: i + 1, fecha: f }));
  expect(ultimasCitas(cs, "2026-06-15").map((c) => c.id)).toEqual([6, 5, 4, 3, 2]);
});

test("ultimasCitas no incluye citas futuras y a igual día ordena por hora", () => {
  const cs = [cita({ id: 1, fecha: "2026-06-15", hora: "09:00" }), cita({ id: 2, fecha: "2026-06-15", hora: "17:00" }), cita({ id: 3, fecha: "2026-09-01" })];
  expect(ultimasCitas(cs, "2026-06-15").map((c) => c.id)).toEqual([2, 1]);
  expect(ultimasCitas([], "2026-06-15")).toEqual([]);
});
