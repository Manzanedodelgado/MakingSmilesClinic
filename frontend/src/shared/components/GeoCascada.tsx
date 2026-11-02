"use client";
/**
 * Selector geográfico en cascada País → Provincia → Ciudad → CP, contra el catálogo
 * oficial (INE/ISO) servido por /geo/*. Reemplaza los campos de texto libre de
 * ciudad/provincia/CP (ver auditoría 27-sep-2026: el catálogo legado `poblaciones`
 * está corrupto — duplicados y CPs mal vinculados). Reutilizable en cualquier
 * formulario de dirección (Centro, Superuser, Filiación de pacientes...).
 */
import { useEffect, useState } from "react";
import { api } from "@/shared/lib/api";
import { LABEL } from "./config-styles";

type GeoItem = { id: number; nombre: string; iso2?: string; cp?: string };
const SEL = "w-full min-w-0 border border-[#e5e7eb] rounded-md outline-none bg-white text-[#333] text-[12px] px-2 py-1 cursor-pointer focus:border-[#1ca0d1]";

export function GeoCascada({ provincia, poblacion, cp, onChange, wPais, wProvincia, wCiudad, wCp }: {
  provincia: string; poblacion: string; cp: string;
  onChange: (g: { provincia: string; poblacion: string; cp: string }) => void;
  wPais?: string; wProvincia?: string; wCiudad?: string; wCp?: string;
}) {
  const [paises, setPaises] = useState<GeoItem[]>([]);
  const [paisId, setPaisId] = useState<number | null>(null);
  const [provincias, setProvincias] = useState<GeoItem[]>([]);
  const [provinciaId, setProvinciaId] = useState<number | null>(null);
  const [municipios, setMunicipios] = useState<GeoItem[]>([]);
  const [municipioId, setMunicipioId] = useState<number | null>(null);
  const [cps, setCps] = useState<GeoItem[]>([]);

  // Países: cargar una vez y preseleccionar España por defecto.
  useEffect(() => {
    api.get<GeoItem[]>("/geo/paises").then((ps) => {
      const es = ps.find((p) => p.iso2 === "ES");
      setPaises(es ? [es] : []);
      setPaisId(es?.id ?? null);
    }).catch(() => setPaises([]));
  }, []);

  // Provincias del país elegido; preseleccionar la que coincida con el texto actual.
  useEffect(() => {
    if (!paisId) return;
    api.get<GeoItem[]>(`/geo/provincias?pais_id=${paisId}`).then((ps) => {
      setProvincias(ps);
      const match = ps.find((p) => p.nombre.toUpperCase() === provincia.trim().toUpperCase());
      setProvinciaId(match ? match.id : null);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paisId]);

  // Municipios de la provincia elegida; preseleccionar el que coincida con la ciudad actual.
  useEffect(() => {
    if (!provinciaId) { setMunicipios([]); setMunicipioId(null); return; }
    api.get<GeoItem[]>(`/geo/municipios?provincia_id=${provinciaId}`).then((ms) => {
      setMunicipios(ms);
      const match = ms.find((m) => m.nombre.toUpperCase() === poblacion.trim().toUpperCase());
      setMunicipioId(match ? match.id : null);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provinciaId]);

  // CPs del municipio elegido.
  useEffect(() => {
    if (!municipioId) { setCps([]); return; }
    api.get<GeoItem[]>(`/geo/cp?municipio_id=${municipioId}`).then(setCps);
  }, [municipioId]);

  function elegirProvincia(id: number) {
    setProvinciaId(id || null);
    setMunicipios([]);
    setMunicipioId(null);
    setCps([]);
    const p = provincias.find((x) => x.id === id);
    onChange({ provincia: p?.nombre ?? "", poblacion: "", cp: "" });
  }
  function elegirMunicipio(id: number) {
    setMunicipioId(id || null);
    const m = municipios.find((x) => x.id === id);
    const p = provincias.find((x) => x.id === provinciaId);
    onChange({ provincia: p?.nombre ?? provincia, poblacion: m?.nombre ?? "", cp: "" });
  }
  function elegirCp(valor: string) {
    const p = provincias.find((x) => x.id === provinciaId);
    const m = municipios.find((x) => x.id === municipioId);
    onChange({ provincia: p?.nombre ?? provincia, poblacion: m?.nombre ?? poblacion, cp: valor });
  }

  return (
    <>
      <div className={wPais ?? "w-40"}>
        <label className={LABEL}>País</label>
        <select className={SEL} value={paisId ?? ""} disabled>
          {paises.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}
        </select>
      </div>
      <div className={wProvincia ?? "w-40"}>
        <label className={LABEL}>Provincia</label>
        <select className={SEL} value={provinciaId ?? ""} onChange={(e) => elegirProvincia(Number(e.target.value))}>
          <option value="">—</option>
          {provincias.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}
        </select>
      </div>
      <div className={wCiudad ?? "w-48"}>
        <label className={LABEL}>Ciudad</label>
        <select className={SEL} value={municipioId ?? ""} onChange={(e) => elegirMunicipio(Number(e.target.value))} disabled={!provinciaId}>
          <option value="">—</option>
          {municipios.map((m) => <option key={m.id} value={m.id}>{m.nombre}</option>)}
        </select>
      </div>
      <div className={wCp ?? "w-28"}>
        <label className={LABEL}>CP</label>
        <select className={SEL} value={cp} onChange={(e) => elegirCp(e.target.value)} disabled={!municipioId}>
          <option value="">—</option>
          {cps.map((c) => <option key={c.id} value={c.cp}>{c.cp}</option>)}
        </select>
      </div>
    </>
  );
}
