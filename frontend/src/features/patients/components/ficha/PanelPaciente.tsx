"use client";
/** Foto (o iniciales), nombre y motivo de consulta del paciente. */
import { useEffect, useRef, useState } from "react";
import { patientService } from "../../services/patientService";
import type { ActoClinico, PacienteCabecera } from "../../types/patient";
import { extraerMotivo } from "./fichaDatos";
import { FichaPanel } from "./FichaPanel";
import { fichaTema as T } from "./fichaTema";

const iniciales = (c: PacienteCabecera | null) =>
  c ? `${c.nombre.trim()[0] ?? ""}${c.apellidos.trim()[0] ?? ""}`.toUpperCase() || "?" : "?";

export function PanelPaciente({ patientId, actos }: { patientId: number; actos: ActoClinico[] }) {
  const [cab, setCab] = useState<PacienteCabecera | null>(null);
  const [sinFoto, setSinFoto] = useState(false);
  const [version, setVersion] = useState(0);   // cambia al subir otra foto para que el navegador la recargue
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let vivo = true;
    setSinFoto(false);
    patientService.cabecera(patientId)
      .then((c) => { if (vivo) setCab(c); })
      .catch(() => { if (vivo) setError("No se pudieron cargar los datos del paciente"); });
    return () => { vivo = false; };
  }, [patientId]);

  async function subir(f: File) {
    setSubiendo(true); setError(null);
    try {
      await patientService.subirFoto(patientId, f);
      setSinFoto(false); setVersion((v) => v + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo subir la foto");
    } finally {
      setSubiendo(false);
    }
  }

  const motivo = extraerMotivo(actos);

  return (
    <FichaPanel titulo="Paciente">
      <div className="p-3 flex gap-3 items-start">
        <div className="w-[84px] h-[112px] shrink-0 rounded-md overflow-hidden grid place-items-center" style={{ background: T.fondoSuave }}>
          {sinFoto
            ? <span className="text-[26px] font-semibold" style={{ color: T.cabTexto }}>{iniciales(cab)}</span>
            // eslint-disable-next-line @next/next/no-img-element
            : <img src={`${patientService.fotoUrl(patientId)}?v=${version}`} alt="Foto del paciente"
                className="w-full h-full object-cover" onError={() => setSinFoto(true)} />}
        </div>
        <div className="min-w-0 flex flex-col gap-1">
          {cab && <p className="text-[13px] font-semibold leading-tight" style={{ color: T.cabTexto }}>{cab.apellidos}, {cab.nombre}</p>}
          <button type="button" onClick={() => input.current?.click()} disabled={subiendo}
            className="self-start text-[11px] font-semibold disabled:opacity-50" style={{ color: T.acento }}>
            {subiendo ? "Subiendo…" : sinFoto ? "Subir foto" : "Cambiar foto"}
          </button>
          <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void subir(f); e.target.value = ""; }} />
          {error && <p className="text-[11px] text-[#C026D3]">{error}</p>}
        </div>
      </div>
      <div className="px-3 pb-3">
        <h3 className="text-[11px] font-semibold mb-1" style={{ color: T.acento }}>Motivo de consulta</h3>
        {motivo
          ? <p className="text-[12px] text-[#333] leading-snug">{motivo}</p>
          : <p className="text-[12px] italic" style={{ color: T.textoSuave }}>Aún sin motivo de consulta</p>}
      </div>
    </FichaPanel>
  );
}
