"use client";
/**
 * Red de seguridad para pestañas con JS obsoleto tras un despliegue — dos capas:
 *
 *  1. REACTIVA (complementa a `global-error.tsx`, que solo atrapa errores que llegan al
 *     límite de error de React). Encontrado en vivo (20-sep-2026): una pestaña abierta desde
 *     antes de un despliegue, al navegar del lado del cliente a una ruta cuyo chunk cambió de
 *     hash, entra en un BUCLE INFINITO de reintentos ("ChunkLoadError" cada ~150ms, cientos de
 *     veces) — Next.js gestiona ese reintento internamente, ANTES de que nada llegue a un
 *     error boundary de React. Aquí se escucha a nivel de `window` (error + unhandledrejection),
 *     donde SÍ se ve el fallo de red del <script> aunque React no lo capture.
 *
 *  2. PROACTIVA: no espera a que nadie haga clic y falle. Cada minuto compara la marca de
 *     build que llevaba grabada al cargar la página (`NEXT_PUBLIC_BUILD_MARCA`, fijada en
 *     tiempo de compilación por `deploy-web.sh`) contra `/build-marca.txt` — un fichero
 *     estático que el navegador SIEMPRE lee fresco de disco (nunca desde el bundle JS ya
 *     cargado). Si difieren, hay un despliegue nuevo: se recarga sola, sin esperar a que la
 *     pestaña se rompa usándola.
 */
import { useCallback, useEffect, useState } from "react";

const MARCA = "mkss_recarga_obsoleta";

function esFalloDeChunkObsoleto(texto: string): boolean {
  return (
    texto.includes("ChunkLoadError") ||
    texto.includes("Loading chunk") ||
    texto.includes("Server Reference ID") ||
    texto.includes("Failed to find Server Action") ||
    /_next\/static\/chunks\/.*\.js/.test(texto)
  );
}

/** ¿Hay una pantalla con trabajo a medias (dibujando, guardando…)? Se registra en `window.__msOcupado` (p. ej. DentIA).
 *  Recargar en ese momento hacía perder lo que el usuario tenía entre manos (31-oct: tres despliegues en 40 min). */
function ocupado(): boolean {
  try {
    const f = (window as unknown as { __msOcupado?: () => boolean }).__msOcupado;
    return typeof f === "function" && !!f();
  } catch { return false; }   // raíz: si el registro falla, se comporta como antes (recarga)
}

function recargarUnaVez() {
  try {
    if (sessionStorage.getItem(MARCA)) return;   // ya se recargó por esto — no reintentar en bucle
    sessionStorage.setItem(MARCA, "1");
  } catch { /* sessionStorage bloqueado (privado/incógnito) — recarga igual, mejor una vez de más */ }
  window.location.reload();
}

export function ClienteObsoletoGuard() {
  const [pendiente, setPendiente] = useState(false);

  // Hay versión nueva: se recarga ya, o —si el usuario está a medias— se avisa y se espera a que termine.
  const pedirRecarga = useCallback(() => {
    if (ocupado()) setPendiente(true); else recargarUnaVez();
  }, []);

  useEffect(() => {
    if (!pendiente) return;
    const id = setInterval(() => { if (!ocupado()) recargarUnaVez(); }, 3_000);
    return () => clearInterval(id);
  }, [pendiente]);

  useEffect(() => {
    const onError = (e: ErrorEvent) => {
      const texto = `${e.message ?? ""} ${(e.error && e.error.stack) || ""} ${(e.target as HTMLScriptElement)?.src || ""}`;
      if (esFalloDeChunkObsoleto(texto)) pedirRecarga();
    };
    const onRejection = (e: PromiseRejectionEvent) => {
      const texto = `${e.reason?.message ?? e.reason ?? ""}`;
      if (esFalloDeChunkObsoleto(texto)) pedirRecarga();
    };
    // capture:true — los fallos de carga de <script> (chunks) solo burbujean en fase de captura.
    window.addEventListener("error", onError, true);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      window.removeEventListener("error", onError, true);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, [pedirRecarga]);

  // Limpia la marca al cabo de un rato: una recarga legítima por despliegue no debe
  // impedir detectar un despliegue FUTURO durante la misma sesión de pestaña.
  useEffect(() => {
    const t = setTimeout(() => { try { sessionStorage.removeItem(MARCA); } catch {} // raiz: storage bloqueado, la marca caduca con la pestaña
    }, 30_000);
    return () => clearTimeout(t);
  }, []);

  // Comprobación proactiva cada minuto: ¿sigue vigente el build con el que se cargó esta
  // pestaña? Si `/build-marca.txt` cambió, hay un despliegue nuevo — se recarga sola.
  useEffect(() => {
    const marcaPropia = process.env.NEXT_PUBLIC_BUILD_MARCA;
    if (!marcaPropia) return; // en dev no hay marca — no molestar
    const comprobar = async () => {
      try {
        const res = await fetch("/build-marca.txt", { cache: "no-store" });
        if (!res.ok) return;
        const marcaActual = (await res.text()).trim();
        if (marcaActual && marcaActual !== marcaPropia) pedirRecarga();
      } catch { /* sin red ahora mismo — se reintenta en el siguiente ciclo */ }
    };
    comprobar(); // primera comprobación inmediata — no esperar al primer intervalo
    const id = setInterval(comprobar, 60_000);
    return () => clearInterval(id);
  }, [pedirRecarga]);

  if (!pendiente) return null;
  return (
    <div role="status" style={{
      position: "fixed", left: 12, bottom: 12, zIndex: 100000, background: "#1500A0", color: "#fff", padding: "8px 12px",
      borderRadius: 8, fontSize: 12, fontFamily: "system-ui", display: "flex", gap: 10, alignItems: "center",
      boxShadow: "0 4px 14px rgba(0,0,0,.25)",
    }}>
      Hay una versión nueva de la web. Se actualizará sola cuando termines lo que estás haciendo.
      <button type="button" onClick={() => window.location.reload()}
        style={{ border: "none", borderRadius: 6, padding: "4px 8px", background: "#fff", color: "#1500A0", fontWeight: 700, cursor: "pointer" }}>
        Actualizar ahora
      </button>
    </div>
  );
}
