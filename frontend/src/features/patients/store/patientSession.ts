"use client";
/**
 * Sesión de paciente ABIERTO — store global ligero (sin dependencias, useSyncExternalStore).
 *
 * El paciente se mantiene "cargado" aunque cambies de sección (Agenda, Gestoría…): el rail
 * muestra Pacientes sombreado + submenú desplegado mientras `openId` esté puesto. Solo se
 * cierra con la X, al cargar otro paciente, o explícitamente.
 *
 * Cambios sin guardar: cada formulario editable se registra como "sucio" (registerDirty) con
 * su función de guardar; al cerrar/cambiar de paciente con formularios sucios se lanza el
 * emergente [Cancelar · No guardar · Guardar]. "Guardar" ejecuta TODOS los save registrados.
 */
import { useEffect, useRef, useSyncExternalStore } from "react";
import type { PacienteCabecera } from "../types/patient";

type SaveFn = () => Promise<void> | void;

interface SessionState {
  openId: number | null;
  cab: PacienteCabecera | null;
  dirty: boolean;            // hay ≥1 formulario sin guardar
  closing: boolean;          // el emergente de cambios pendientes está visible
}

let state: SessionState = { openId: null, cab: null, dirty: false, closing: false };
const dirtyForms = new Map<string, SaveFn>();     // clave → su saveFn (presencia = sucio)
let pending: (() => void) | null = null;          // acción a ejecutar tras resolver el guard
const listeners = new Set<() => void>();

const KEY = "ms_open_patient";   // persistencia ligera (solo el id) en cookie de sesión → sobrevive recargas sin usar storage del navegador (R4)
const persist = (id: number | null) => {
  if (typeof document === "undefined") return;
  document.cookie = id ? `${KEY}=${id}; path=/; SameSite=Lax` : `${KEY}=; Max-Age=0; path=/; SameSite=Lax`;
};
const readOpenId = (): number => {
  if (typeof document === "undefined") return 0;
  const c = document.cookie.split("; ").find((x) => x.startsWith(`${KEY}=`));
  return c ? Number(c.slice(KEY.length + 1)) || 0 : 0;
};

const emit = () => listeners.forEach((l) => l());
const set = (p: Partial<SessionState>) => { state = { ...state, ...p }; emit(); };
const syncDirty = () => { const d = dirtyForms.size > 0; if (d !== state.dirty) set({ dirty: d }); else emit(); };

export const patientSession = {
  subscribe(l: () => void) { listeners.add(l); return () => { listeners.delete(l); }; },
  snapshot() { return state; },

  // ── paciente abierto ──
  open(id: number, cab: PacienteCabecera | null) { persist(id); state = { ...state, openId: id, cab }; emit(); },
  setCab(cab: PacienteCabecera | null) { if (cab?.id === state.openId || state.openId == null) set({ cab }); },
  /** Vacía el paciente y descarta el registro de sucios (sin preguntar: úsalo tras resolver el guard). */
  clear() { persist(null); dirtyForms.clear(); state = { openId: null, cab: null, dirty: false, closing: false }; emit(); },
  /** Rehidrata el id desde la cookie de sesión tras una recarga (llámalo una vez al montar el shell). */
  hydrate() {
    if (state.openId != null) return;
    const v = readOpenId();
    if (v) { state = { ...state, openId: v }; emit(); }
  },

  // ── registro de formularios sucios ──
  registerDirty(key: string, saveFn: SaveFn) { dirtyForms.set(key, saveFn); syncDirty(); },
  clearDirty(key: string) { if (dirtyForms.delete(key)) syncDirty(); },
  isDirty() { return dirtyForms.size > 0; },
  async saveAll() { for (const fn of Array.from(dirtyForms.values())) { await fn(); } dirtyForms.clear(); syncDirty(); },
  discardAll() { dirtyForms.clear(); syncDirty(); },

  // ── guard de cierre / cambio de paciente ──
  /** Pide ejecutar `run`; si hay cambios sin guardar abre el emergente, si no lo ejecuta ya. */
  requestClose(run: () => void) {
    if (dirtyForms.size > 0) { pending = run; set({ closing: true }); }
    else run();
  },
  /** Respuesta del emergente. */
  resolveClose(action: "cancel" | "discard" | "save"): Promise<void> {
    if (action === "cancel") { pending = null; set({ closing: false }); return Promise.resolve(); }
    const run = pending;
    const finish = () => { pending = null; set({ closing: false }); run?.(); };
    if (action === "discard") { dirtyForms.clear(); state = { ...state, dirty: false }; finish(); return Promise.resolve(); }
    return this.saveAll().then(finish);   // "save"
  },
};

/** Estado reactivo del paciente abierto. */
export function usePatientSession(): SessionState {
  return useSyncExternalStore(patientSession.subscribe, patientSession.snapshot, patientSession.snapshot);
}

/**
 * Marca un formulario como "sucio" mientras `dirty` sea true, registrando su `save` para que
 * el emergente de cierre pueda guardarlo. Se desregistra al limpiarse o al desmontar.
 * Uso: useDirtyForm("filiacion", hayCambios, async () => { await guardar(); });
 */
export function useDirtyForm(key: string, dirty: boolean, save: SaveFn) {
  const saveRef = useRef(save);
  saveRef.current = save;
  useEffect(() => {
    if (dirty) patientSession.registerDirty(key, () => saveRef.current());
    else patientSession.clearDirty(key);
    return () => patientSession.clearDirty(key);
  }, [key, dirty]);
}
