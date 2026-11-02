"use client";
/**
 * Página PÚBLICA de firma de consentimiento (enlace enviado por WhatsApp tras confirmar la cita).
 * Sin login: protegida por el código del enlace. El paciente lee el PDF COEM y firma con el dedo.
 * Portado del flujo de la .37 (SigningPage). Fuera del route group (app) → sin shell autenticado.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { API_BASE } from "@/shared/lib/api";

type Info = { tipo: string; clinica: string; pdf_url: string | null; firmado: boolean };

export default function FirmarConsentimientoPage() {
  const params = useParams<{ code: string }>();
  const code = params?.code ?? "";
  const [info, setInfo] = useState<Info | null>(null);
  const [estado, setEstado] = useState<"cargando" | "listo" | "firmado" | "error">("cargando");
  const [acepta, setAcepta] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dibujando = useRef(false);
  const [hayTrazo, setHayTrazo] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/consentimientos/firmar/${code}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d: Info) => { setInfo(d); setEstado(d.firmado ? "firmado" : "listo"); })
      .catch(() => setEstado("error"));
  }, [code]);

  const initCtx = useCallback(() => {
    const c = canvasRef.current; if (!c) return null;
    const ctx = c.getContext("2d"); if (!ctx) return null;
    ctx.strokeStyle = "#013b82"; ctx.lineWidth = 2.5; ctx.lineCap = "round"; ctx.lineJoin = "round";
    return ctx;
  }, []);
  useEffect(() => { if (estado === "listo") initCtx(); }, [estado, initCtx]);

  // Escala el punto del dedo/ratón al sistema de coordenadas interno del lienzo (640×200)
  // para que el trazo salga justo bajo el dedo aunque el canvas se muestre a otro ancho.
  const pos = (e: React.PointerEvent) => {
    const c = canvasRef.current!;
    const r = c.getBoundingClientRect();
    return { x: (e.clientX - r.left) * (c.width / r.width), y: (e.clientY - r.top) * (c.height / r.height) };
  };
  const down = (e: React.PointerEvent) => { dibujando.current = true; const ctx = initCtx()!; const { x, y } = pos(e); ctx.beginPath(); ctx.moveTo(x, y); canvasRef.current!.setPointerCapture(e.pointerId); };
  const move = (e: React.PointerEvent) => { if (!dibujando.current) return; const ctx = canvasRef.current!.getContext("2d")!; const { x, y } = pos(e); ctx.lineTo(x, y); ctx.stroke(); setHayTrazo(true); };
  const up = () => { dibujando.current = false; };
  const limpiar = () => { const c = canvasRef.current!; c.getContext("2d")!.clearRect(0, 0, c.width, c.height); setHayTrazo(false); };

  async function enviar() {
    if (!hayTrazo) { setError("Firma en el recuadro antes de continuar."); return; }
    if (!acepta) { setError("Marca la casilla de aceptación."); return; }
    setEnviando(true); setError(null);
    try {
      const r = await fetch(`${API_BASE}/consentimientos/firmar/${code}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ firma: canvasRef.current!.toDataURL("image/png") }),
      });
      if (!r.ok) throw new Error();
      setEstado("firmado");
    } catch { setError("No se pudo registrar la firma. Inténtalo de nuevo."); }
    finally { setEnviando(false); }
  }

  return (
    <div className="min-h-screen bg-[#FFFFFF] text-[#333]">
      <div className="w-full max-w-[720px] mx-auto px-4 pt-5 pb-[160px] flex flex-col gap-4">
        <header className="text-center">
          <div className="text-[13px] font-semibold text-[#065AED] uppercase tracking-wide">{info?.clinica || "Clínica dental"}</div>
          <h1 className="text-[20px] font-bold text-[#1500A0] mt-1">Consentimiento informado{info?.tipo ? ` · ${info.tipo}` : ""}</h1>
        </header>

        {estado === "cargando" && <p className="text-center text-[13px] text-[#7f8c8d] py-10">Cargando…</p>}
        {estado === "error" && <p className="text-center text-[13px] text-[#C026D3] py-10">Enlace no válido o caducado.</p>}
        {estado === "firmado" && (
          <div className="bg-white border border-[#9FE6DB] rounded-lg p-6 text-center">
            <div className="mx-auto w-14 h-14 rounded-full bg-[#0F8C7D] flex items-center justify-center">
              <svg viewBox="0 0 24 24" className="w-8 h-8" fill="none" stroke="white" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round"><path d="M5 13l4 4L19 7" /></svg>
            </div>
            <p className="text-[15px] font-semibold text-[#0F8C7D] mt-3">¡Consentimiento firmado!</p>
            <p className="text-[13px] text-[#7f8c8d] mt-1">Gracias. Ya puedes cerrar esta página.</p>
          </div>
        )}

        {estado === "listo" && info && (
          <>
            {info.pdf_url && (
              <div className="bg-white border border-[#e5e7eb] rounded-lg overflow-hidden">
                <iframe src={`${API_BASE}${info.pdf_url}`} title="Consentimiento" className="w-full h-[38vh]" />
                <a href={`${API_BASE}${info.pdf_url}`} target="_blank" rel="noreferrer"
                  className="block text-center text-[12px] text-[#065AED] underline py-2">Abrir documento en pantalla completa</a>
              </div>
            )}

            <div className="bg-white border border-[#e5e7eb] rounded-lg p-4 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <p className="text-[13px] font-semibold text-[#1500A0]">Firma del paciente</p>
                <button type="button" onClick={limpiar}
                  className="flex items-center gap-1 h-9 px-3 rounded-md border border-[#e5e7eb] text-[13px] font-semibold text-[#C026D3] active:bg-[#E6EDFF]">
                  ✕ Borrar
                </button>
              </div>
              <canvas ref={canvasRef} width={640} height={200} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerLeave={up}
                className="w-full h-[200px] border-2 border-dashed border-[#c8d8e8] rounded-md bg-white touch-none cursor-crosshair" />
              <p className="text-[12px] text-[#7f8c8d]">Firma dentro del recuadro con el dedo. Si te equivocas, pulsa «Borrar».</p>
            </div>
          </>
        )}
      </div>

      {estado === "listo" && info && (
        <div className="fixed bottom-0 inset-x-0 bg-white border-t border-[#e5e7eb] shadow-[0_-2px_12px_rgba(0,0,0,0.08)]">
          <div className="w-full max-w-[720px] mx-auto px-4 py-3 flex flex-col gap-2">
            <label className="flex items-start gap-2 text-[12px] leading-snug text-[#374151]">
              <input type="checkbox" checked={acepta} onChange={(e) => setAcepta(e.target.checked)} className="mt-0.5 shrink-0" />
              He leído y comprendido el documento, he podido aclarar mis dudas y <b>doy mi consentimiento</b>.
            </label>
            {error && <p className="text-[12px] text-[#C026D3]">{error}</p>}
            <button onClick={enviar} disabled={enviando}
              className="h-12 rounded-md text-white text-[15px] font-semibold uppercase tracking-wide bg-[#1500A0] active:bg-[#0d0072] disabled:opacity-50">
              {enviando ? "Enviando…" : "Firmar y enviar"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
