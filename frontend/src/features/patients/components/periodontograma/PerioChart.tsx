"use client";
/**
 * PerioChart — render EXACTO del periodontograma del .37 (vestibular + palatina, recorte de
 * dientes calibrado + curvas de encía/bolsa SVG). Read-only: los datos vienen del backend
 * (periodontograma_medidas). Sin almacenamiento del navegador ni modo edición (R4). Calibración = CAL_DEFAULT.
 */
import React, { CSSProperties, useState } from "react";
import { baseOdontograma } from "../odontograma/odontogramaUtils";

const IMG_W = 726, IMG_H = 386;
const MIN_COL_W = 15;
const COL_LABEL = 92;

export interface CalLines {
  yU1: number; yU2: number; yL1: number; yL2: number;
  xDivU: number[]; xDivL: number[];
  gumUPct: number; gumLPct: number; mmPx: number; colWidths?: number[];
}
const XDIVU_DEFAULT = [0, 8.1, 15.7, 23.4, 28.1, 33.1, 38.3, 43.1, 49.4, 56.0, 60.7, 66.4, 71.5, 76.6, 84.7, 92.0, 100];
const XDIVL_DEFAULT = [0, 9.0, 16.0, 24.4, 29.5, 34.3, 39.7, 44.6, 49.6, 54.7, 59.5, 65.4, 70.8, 76.2, 84.3, 91.6, 100];
export const CAL_DEFAULT: CalLines = {
  yU1: 18.0, yU2: 53.0, yL1: 53.0, yL2: 80.7,
  xDivU: [...XDIVU_DEFAULT], xDivL: [...XDIVL_DEFAULT],
  gumUPct: 56.6, gumLPct: 38.3, mmPx: 5,
};

export interface Pt { ps: number; rec: number; ss: boolean; ip: boolean; }
export interface Td {
  num: number; v: [Pt, Pt, Pt]; p: [Pt, Pt, Pt];
  mob: 0 | 1 | 2 | 3; furca: 0 | 1 | 2 | 3; missing: boolean; implante: boolean;
  corona: boolean; puente: boolean;   // estados estructurales derivados de O1
}
const mkPt = (): Pt => ({ ps: 0, rec: 0, ss: false, ip: false });
const mkTd = (n: number): Td => ({ num: n, v: [mkPt(), mkPt(), mkPt()], p: [mkPt(), mkPt(), mkPt()], mob: 0, furca: 0, missing: false, implante: false, corona: false, puente: false });
export const SUP = [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28];
export const INF = [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38];
export function blankTeeth(): Record<number, Td> {
  const t: Record<number, Td> = {};
  [...SUP, ...INF].forEach((n) => { t[n] = mkTd(n); });
  return t;
}
function colW(cl: CalLines, idx: number, upper: boolean): number {
  const xd = upper ? cl.xDivU : cl.xDivL;
  return Math.max(MIN_COL_W, Math.round(((xd[idx + 1] - xd[idx]) / 100) * IMG_W));
}

function NumCell({ val, onChange }: { val: number; onChange?: (v: number) => void }) {
  const color = val >= 4 ? "#1500A0" : val >= 3 ? "#7C3AED" : val > 0 ? "#1e3a5f" : "#a0aec0";
  if (onChange) return (
    <input type="text" inputMode="numeric" value={val || ""} placeholder="·"
      onChange={(e) => onChange(Math.max(0, Math.min(20, parseInt(e.target.value.replace(/[^0-9]/g, "")) || 0)))}
      style={{ width: "100%", textAlign: "center", fontSize: 13, fontWeight: 700, color, border: "none", outline: "none", background: "transparent", padding: 0 }} />
  );
  return <span style={{ width: "100%", textAlign: "center", fontSize: 13, fontWeight: 700, color }}>{val > 0 ? val : "·"}</span>;
}
function CheckCell({ active, color, onChange }: { active: boolean; color: string; onChange?: () => void }) {
  const box = <div style={{ width: 13, height: 13, borderRadius: 3, background: active ? color : "transparent", border: `1.5px solid ${active ? color : "#c8d6e8"}` }} />;
  if (onChange) return <button type="button" onClick={onChange} style={{ border: "none", background: "transparent", padding: 0, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>{box}</button>;
  return box;
}
function FurcaCell({ val }: { val: 0 | 1 | 2 | 3 }) {
  return <span style={{ fontSize: 12, fontWeight: 800, color: ["#c8d6e8", "#1CA0D1", "#7C3AED", "#1500A0"][val] }}>{["·", "I", "II", "III"][val]}</span>;
}

function ToothCrop({ missing, implante, corona, puente, cl, colIdx, upper, displayW, baseImg }: {
  missing: boolean; implante: boolean; corona: boolean; puente: boolean; cl: CalLines; colIdx: number; upper: boolean; displayW: number; baseImg: string;
}) {
  const y1 = upper ? cl.yU1 : cl.yL1, y2 = upper ? cl.yU2 : cl.yL2;
  const xd = upper ? cl.xDivU : cl.xDivL;
  const srcH = Math.max(1, ((y2 - y1) / 100) * IMG_H);
  const srcX = (xd[colIdx] / 100) * IMG_W;
  const srcW = Math.max(1, ((xd[colIdx + 1] - xd[colIdx]) / 100) * IMG_W);
  const w = Math.max(MIN_COL_W, displayW), dispH = Math.round(srcH);
  const sx = w / srcW, bgX = Math.round(-srcX * sx), bgY = Math.round((-y1 / 100) * IMG_H);
  if (missing) return (
    <div style={{ width: w, height: dispH, background: "#FFFFFF", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <svg width={14} height={14} viewBox="0 0 14 14">
        <line x1="2" y1="2" x2="12" y2="12" stroke="#cbd5e1" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="12" y1="2" x2="2" y2="12" stroke="#cbd5e1" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    </div>
  );
  return (
    <div style={{ position: "relative", width: w, height: dispH, overflow: "hidden",
      backgroundImage: `url(${baseImg})`, backgroundRepeat: "no-repeat",
      backgroundSize: `${Math.round(IMG_W * sx)}px ${IMG_H}px`, backgroundPosition: `${bgX}px ${bgY}px` }}>
      {(() => {
        // Un solo badge por pieza (prioridad implante > corona > puente). Derivado de O1.
        const b = implante ? { t: "IMP", c: "#0891b2" } : corona ? { t: "COR", c: "#0F8C7D" } : puente ? { t: "PTE", c: "#C026D3" } : null;
        return b ? (
          <div style={{ position: "absolute", bottom: 2, left: "50%", transform: "translateX(-50%)", background: b.c, color: "white", fontSize: 7, fontWeight: 700, padding: "1px 3px", borderRadius: 2, letterSpacing: "0.05em" }}>{b.t}</div>
        ) : null;
      })()}
    </div>
  );
}

export function PerioChart({ teeth, cl = CAL_DEFAULT, editable = false, onCell, onMob, edad = null }: {
  teeth: Record<number, Td>; cl?: CalLines; editable?: boolean;
  onCell?: (n: number, face: "v" | "p", i: number, field: "ps" | "rec" | "ss" | "ip", value: number | boolean) => void;
  onMob?: (n: number, value: number) => void;
  edad?: number | null;   // dentición infantil/mixta por edad (imagen de fondo)
}) {
  const baseImg = baseOdontograma(edad);
  const [arcada, setArcada] = useState<"sup" | "inf">("sup");   // pestañas: arcada superior / inferior
  const totalDataW = SUP.map((_, i) => ((cl.colWidths?.[i] ?? 0) > 0 ? cl.colWidths![i] : colW(cl, i, true))).reduce((s, w) => s + w, 0);
  const totalW = COL_LABEL + totalDataW;
  const eqBase = Math.floor(totalDataW / 16), eqRem = totalDataW - eqBase * 16;
  const uW = Array.from({ length: 16 }, (_, i) => (i < eqRem ? eqBase + 1 : eqBase));
  const nCols = 1 + 16;
  const ROW_H = 42, bd = "1px solid #e4eaf3";
  const dc = (alt?: boolean): CSSProperties => ({ height: ROW_H, padding: 0, borderRight: bd, borderBottom: bd, background: alt ? "#FFFFFF" : "white", verticalAlign: "middle" });
  const lblS = (extra?: CSSProperties): CSSProperties => ({ width: COL_LABEL, minWidth: COL_LABEL, fontSize: 9, fontWeight: 600, color: "#6b7e99", textTransform: "uppercase", letterSpacing: "0.03em", paddingLeft: 6, paddingRight: 2, borderRight: "1px solid #dde5f0", borderBottom: bd, whiteSpace: "nowrap", background: "#FFFFFF", verticalAlign: "middle", ...extra });

  const hdr = (label: string, accent: string) => {
    const lightBg = accent === "#065AED" ? "#FFFFFF" : "#FFFFFF";
    const borderColor = accent === "#065AED" ? "#c7d8ff" : "#99e6d8";
    return (<tr key={`hdr-${label}`}><td colSpan={nCols} style={{ background: lightBg, padding: "8px 12px 8px 16px", borderBottom: `1px solid ${borderColor}`, borderLeft: `3px solid ${accent}` }}>
      <span style={{ fontSize: 9, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.22em", color: accent }}>{label}</span></td></tr>);
  };
  const numR = (key: string, label: string, piezas: number[], face: "v" | "p", field: "ps" | "rec", alt?: boolean) => (
    <tr key={key} style={{ height: ROW_H }}><td style={lblS(alt ? { background: "#FFFFFF" } : undefined)}>{label}</td>
      {piezas.map((n) => (<td key={n} style={dc(alt)}>{!teeth[n].missing && (<div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
        {[0, 1, 2].map((i) => (<div key={i} style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", borderBottom: i < 2 ? "1px solid #e4eaf3" : "none" }}><NumCell val={teeth[n][face][i][field]} onChange={editable && onCell ? (vv) => onCell(n, face, i, field, vv) : undefined} /></div>))}
      </div>)}</td>))}</tr>
  );
  const chkR = (key: string, label: string, piezas: number[], face: "v" | "p", field: "ss" | "ip", color: string, alt?: boolean) => (
    <tr key={key} style={{ height: ROW_H }}><td style={lblS(alt ? { background: "#FFFFFF" } : undefined)}>{label}</td>
      {piezas.map((n) => (<td key={n} style={dc(alt)}>{!teeth[n].missing && (<div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
        {[0, 1, 2].map((i) => (<div key={i} style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", borderBottom: i < 2 ? "1px solid #e4eaf3" : "none" }}><CheckCell active={teeth[n][face][i][field]} color={color} onChange={editable && onCell ? () => onCell(n, face, i, field, !teeth[n][face][i][field]) : undefined} /></div>))}
      </div>)}</td>))}</tr>
  );
  const niR = (key: string, label: string, piezas: number[], face: "v" | "p", alt?: boolean) => (
    <tr key={key} style={{ height: ROW_H }}><td style={lblS(alt ? { background: "#FFFFFF" } : undefined)}>{label}</td>
      {piezas.map((n) => (<td key={n} style={dc(alt)}>{!teeth[n].missing && (<div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
        {[0, 1, 2].map((i) => { const ni = teeth[n][face][i].ps + teeth[n][face][i].rec; const c = ni >= 5 ? "#1500A0" : ni >= 4 ? "#7C3AED" : ni > 0 ? "#1e3a5f" : "#a0aec0";
          return (<div key={i} style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", borderBottom: i < 2 ? "1px solid #e4eaf3" : "none" }}><span style={{ fontSize: 13, fontWeight: 700, color: c, width: "100%", textAlign: "center" }}>{ni > 0 ? ni : "·"}</span></div>); })}
      </div>)}</td>))}</tr>
  );
  const furcaR = (key: string, piezas: number[], alt?: boolean) => (
    <tr key={key} style={{ height: ROW_H }}><td style={lblS(alt ? { background: "#FFFFFF" } : undefined)}>Furcas</td>
      {piezas.map((n) => (<td key={n} style={dc(alt)}>{!teeth[n].missing && <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}><FurcaCell val={teeth[n].furca} /></div>}</td>))}</tr>
  );
  const toothRowR = (key: string, piezas: number[], upper: boolean, face: "v" | "p") => {
    const H = Math.round(((upper ? cl.yU2 - cl.yU1 : cl.yL2 - cl.yL1) / 100) * IMG_H);
    const gumY = upper ? (cl.gumUPct / 100) * H : (cl.gumLPct / 100) * H;
    const dir = upper ? -1 : 1;
    const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
    const pts: { x: number; gY: number; pY: number; ss: boolean }[] = [];
    let xOff = 0;
    piezas.forEach((n, idx) => { const w = uW[idx];
      [0, 1, 2].forEach((i) => { const x = xOff + ((i + 0.5) * w) / 3; const m = teeth[n][face][i];
        const gY = clamp(gumY + dir * m.rec * cl.mmPx, 0, H); const pY = clamp(gY + dir * m.ps * cl.mmPx, 0, H);
        pts.push({ x, gY, pY, ss: m.ss }); });
      xOff += w; });
    const gPath = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.gY.toFixed(1)}`).join(" ");
    const pPath = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.pY.toFixed(1)}`).join(" ");
    const rGum = [...pts].reverse().map((p) => `L${p.x.toFixed(1)},${p.gY.toFixed(1)}`).join(" ");
    return (
      <tr key={key}><td style={lblS({ fontSize: 9, color: "#8fa3be", textAlign: "center", paddingLeft: 0, letterSpacing: 0, textTransform: "none", background: "#FFFFFF" })}>Nº / Mob</td>
        <td colSpan={16} style={{ padding: 0, borderBottom: bd, verticalAlign: "top", background: "white" }}>
          <div style={{ position: "relative", width: totalDataW }}>
            <div style={{ display: "flex" }}>
              {piezas.map((n, idx) => (<div key={n} style={{ width: uW[idx], flexShrink: 0, display: "flex", flexDirection: "column", alignItems: "center", boxShadow: "inset -1px 0 0 #e8edf6" }}>
                <ToothCrop missing={teeth[n].missing} implante={teeth[n].implante} corona={teeth[n].corona} puente={teeth[n].puente} cl={cl} colIdx={idx} upper={upper} displayW={uW[idx]} baseImg={baseImg} />
                <div style={{ display: "flex", alignItems: "center", gap: 2, padding: "3px 0", background: upper ? "#FFFFFF" : "#FFFFFF", width: "100%", justifyContent: "center", borderTop: upper ? "1px solid #d0deff" : "1px solid #9FE6DB" }}>
                  <div style={{ width: 20, height: 20, borderRadius: 4, background: teeth[n].missing ? "#94a3b8" : upper ? "#065AED" : "#0e7490", color: "white", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 9, fontWeight: 700, flexShrink: 0, letterSpacing: "-0.02em" }}>{n}</div>
                  {editable && onMob ? (
                    <button type="button" onClick={() => onMob(n, (teeth[n].mob + 1) % 4)} title="Movilidad (clic para cambiar)"
                      style={{ border: "none", background: "transparent", padding: 0, cursor: "pointer", fontSize: 10, fontWeight: 700, color: teeth[n].mob > 0 ? "#1500A0" : "#b8c8d8" }}>{teeth[n].mob > 0 ? `M${teeth[n].mob}` : "·"}</button>
                  ) : (
                    <span style={{ fontSize: 10, fontWeight: 700, color: teeth[n].mob > 0 ? "#1500A0" : "#b8c8d8" }}>{teeth[n].mob > 0 ? `M${teeth[n].mob}` : "·"}</span>
                  )}
                </div>
              </div>))}
            </div>
            <svg style={{ position: "absolute", top: 0, left: 0, pointerEvents: "none" }} width={totalDataW} height={H}>
              <path d={`${pPath} ${rGum} Z`} fill="rgba(232,69,122,0.18)" />
              <line x1={0} y1={gumY} x2={totalDataW} y2={gumY} stroke="#2DD9C3" strokeWidth={1.5} strokeDasharray="5,3" opacity={0.85} />
              <path d={gPath} stroke="#2DD9C3" strokeWidth={1.5} fill="none" opacity={0.7} />
              <path d={pPath} stroke="#1500A0" strokeWidth={2} fill="none" />
              {pts.map((p, i) => (<circle key={i} cx={p.x} cy={p.pY} r={3} fill={p.ss ? "#1500A0" : "rgba(59,130,246,0.9)"} stroke="white" strokeWidth={0.8} />))}
            </svg>
          </div>
        </td></tr>
    );
  };
  const card: CSSProperties = { background: "white", border: "1px solid #dce5f2", borderRadius: 6, boxShadow: "0 2px 12px rgba(1,59,130,0.07)", flexShrink: 0 };
  const colgroup = () => (<colgroup><col style={{ width: COL_LABEL }} />{uW.map((w, i) => <col key={i} style={{ width: w }} />)}</colgroup>);

  // Un bloque = una cara (vestibular/palatina) de una arcada: medidas + fila de dientes.
  const bloque = (piezas: number[], upper: boolean, face: "v" | "p", label: string, accent: string) => (
    <div style={card}>
      <table style={{ borderCollapse: "collapse", tableLayout: "fixed", width: totalW }}>{colgroup()}<tbody>
        {hdr(label, accent)}
        {furcaR(`fu-${label}`, piezas)}{chkR(`ip-${label}`, "Placa", piezas, face, "ip", "#1ca0d1", true)}{chkR(`ss-${label}`, "Sangrado", piezas, face, "ss", "#1500A0")}
        {niR(`ni-${label}`, "P. Inserción", piezas, face, true)}{numR(`ps-${label}`, "Bolsa Per.", piezas, face, "ps")}{numR(`rec-${label}`, "Recesión G.", piezas, face, "rec", true)}
        {toothRowR(`tr-${label}`, piezas, upper, face)}
      </tbody></table>
    </div>
  );
  const tab = (id: "sup" | "inf", lbl: string) => (
    <button type="button" onClick={() => setArcada(id)} style={{
      padding: "7px 18px", fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em",
      border: `1px solid ${arcada === id ? "#1500A0" : "#c7d8ff"}`, borderRadius: 6, cursor: "pointer",
      background: arcada === id ? "#1500A0" : "white", color: arcada === id ? "white" : "#1500A0",
    }}>{lbl}</button>
  );

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        {tab("sup", "Arcada Superior")}
        {tab("inf", "Arcada Inferior")}
      </div>
      <div style={{ overflowX: "auto" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, width: "max-content" }}>
          {arcada === "sup" ? (<>
            {bloque(SUP, true, "v", "Vestibular — Arcada Superior", "#065AED")}
            {bloque(SUP, true, "p", "Palatina — Arcada Superior", "#065AED")}
          </>) : (<>
            {bloque(INF, false, "v", "Vestibular — Arcada Inferior", "#0e7490")}
            {bloque(INF, false, "p", "Lingual — Arcada Inferior", "#0e7490")}
          </>)}
        </div>
      </div>
    </div>
  );
}
