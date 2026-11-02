"use client";
/**
 * useEventStream — suscripción al bus de tiempo real del backend (SSE).
 *
 * El backend publica en `/comunicacion/stream` TODOS los eventos del centro como
 * líneas `data: {json}` (sin `event:`): mensajes de WhatsApp (`{tipo:"mensaje",...}`)
 * y —desde el bloque de tiempo real app↔web— cambios de agenda, estudios de
 * ortodoncia, presupuestos y facturas (`{tipo:"cita.movida",...}` etc.).
 *
 * Este hook abre UNA conexión EventSource y despacha cada evento al handler
 * registrado para su `tipo`.
 *
 * Uso:
 *   useEventStream({
 *     "cita.movida":  () => recargarAgenda(),
 *     "cita.creada":  () => recargarAgenda(),
 *     "cita.anulada": () => recargarAgenda(),
 *   }, [dep]);
 *
 * El stream NO transporta estado: avisa de que algo cambió; el consumidor recarga.
 * EventSource reconecta solo; si el navegador cierra la conexión del todo, reabrimos.
 */
import { useEffect, useRef } from "react";
import { API_BASE } from "@/shared/lib/api";

type Handler = (data: Record<string, unknown>) => void;
type Handlers = Record<string, Handler>;

export function useEventStream(handlers: Handlers, deps: unknown[] = []) {
  // Ref viva: los handlers se recrean en cada render pero no reabrimos el stream.
  const ref = useRef<Handlers>(handlers);
  ref.current = handlers;

  useEffect(() => {
    let es: EventSource | null = null;
    let cerrado = false;
    let reintento: ReturnType<typeof setTimeout> | null = null;

    const abrir = () => {
      if (cerrado) return;
      es = new EventSource(`${API_BASE}/comunicacion/stream`, { withCredentials: true });

      es.onmessage = (e) => {
        let data: Record<string, unknown> = {};
        try { data = e.data ? JSON.parse(e.data) : {}; } catch { return; }
        const tipo = typeof data.tipo === "string" ? data.tipo : "";
        const h = ref.current[tipo];
        if (h) h(data);
      };

      es.onerror = () => {
        if (es && es.readyState === EventSource.CLOSED && !cerrado) {
          reintento = setTimeout(abrir, 3000);
        }
      };
    };

    abrir();
    return () => {
      cerrado = true;
      if (reintento) clearTimeout(reintento);
      es?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
