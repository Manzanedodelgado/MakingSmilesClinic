"use client";
import { useCallback, useEffect, useState } from "react";
import { Activity, RefreshCw, AlertTriangle, Server, Globe, Cpu, Clock } from "lucide-react";
import { api } from "@/shared/lib/api";
import { ClinicalCard, SectionHeader, ClinicalButton } from "@/shared/components";
import { DOT, ESTADO_TXT, peorEstado, type Chequeo, type Integr, type Salud } from "./estado";

// Cada chequeo del backend (`clave`) cae en un grupo; lo que no esté aquí va a «Otros».
const GRUPOS: { id: string; titulo: string; icono: typeof Server; claves: string[] }[] = [
  { id: "infra", titulo: "Infraestructura", icono: Server, claves: ["db", "stats_bd", "disco", "ram", "servidor"] },
  { id: "servicios", titulo: "Servicios", icono: Globe,
    claves: ["frontend", "app_paciente", "comportamiento", "autenticacion", "whatsapp", "email_saliente", "email_imap", "orthanc", "google_drive"] },
  { id: "ia", titulo: "Inteligencia artificial", icono: Cpu, claves: ["ia", "ia_dental"] },
];

// Integraciones de IA: el backend manda una fila por cada una, con nombres internos y
// repetidas. Aquí se agrupan por tipo y se les pone nombre legible.
const TIPOS_IA: Record<string, string> = {
  llm: "Modelos de lenguaje (LLM)",
  llm_proveedor: "Proveedores de IA",
  stt: "Voz a texto",
  ollama_switch: "Interruptor Alex/Victor/Aura (PC-ESCANER)",
};

type FilaIA = { tipo: string; titulo: string; estado: string; detalle: string };

function resumirIA(integraciones: Integr[], clavesSistema: Set<string>): FilaIA[] {
  const porTipo = new Map<string, Integr[]>();
  for (const i of integraciones) {
    if (clavesSistema.has(i.tipo)) continue; // ya salen como chequeo propio (email, Orthanc, WhatsApp, Drive)
    porTipo.set(i.tipo, [...(porTipo.get(i.tipo) ?? []), i]);
  }
  return [...porTipo.entries()].map(([tipo, filas]) => {
    const activas = filas.filter((f) => f.estado !== "off");
    const inactivas = filas.length - activas.length;
    const estado = peorEstado(filas.map((f) => f.estado));
    const partes: string[] = [];
    if (filas.length === 1) {
      partes.push(ESTADO_TXT[estado] ?? estado);
    } else {
      if (activas.length) partes.push(`${activas.length} ${activas.length === 1 ? "activa" : "activas"}`);
      if (inactivas) partes.push(`${inactivas} ${inactivas === 1 ? "inactiva" : "inactivas"}`);
    }
    return { tipo, titulo: TIPOS_IA[tipo] ?? filas[0].label, estado, detalle: partes.join(" · ") };
  });
}

type Tarea = { nombre: string; texto: string };
function parseTareas(detalle: string): Tarea[] {
  return detalle.split(/;\s*/).map((p) => {
    const i = p.indexOf(":");
    return i < 0 ? { nombre: p.trim(), texto: "" } : { nombre: p.slice(0, i).trim(), texto: p.slice(i + 1).trim() };
  }).filter((t) => t.nombre);
}
const sinDatos = (t: Tarea) => /sin ejecuci[oó]n registrada/i.test(t.texto);

function Fila({ estado, titulo, detalle }: { estado: string; titulo: string; detalle: string }) {
  const aviso = estado !== "ok" && estado !== "off";
  return (
    <div className={`flex items-baseline gap-3 px-2 py-1.5 border-b border-[#f0f2f5] last:border-b-0 ${aviso ? "bg-[#F5F0FF]" : ""}`}>
      <span className={`w-2.5 h-2.5 rounded-full shrink-0 translate-y-[1px] ${DOT[estado] ?? "bg-slate-300"}`} />
      <span className="text-[12px] font-semibold text-[#33415c] w-[210px] shrink-0">{titulo}</span>
      <span className="text-[11.5px] text-[#7f8c8d] min-w-0">{detalle}</span>
    </div>
  );
}

function Grupo({ titulo, icono, filas }: { titulo: string; icono: typeof Server; filas: { estado: string; titulo: string; detalle: string }[] }) {
  const ok = filas.filter((f) => f.estado === "ok").length;
  const peor = peorEstado(filas.map((f) => f.estado));
  return (
    <ClinicalCard>
      <SectionHeader title={titulo} icon={icono}
        action={<span className="flex items-center gap-1.5 text-[11px] text-slate-400">
          <span className={`w-2 h-2 rounded-full ${DOT[peor] ?? "bg-slate-300"}`} />{ok}/{filas.length} OK</span>} />
      <div>{filas.map((f, i) => <Fila key={i} {...f} />)}</div>
    </ClinicalCard>
  );
}

export function CentinelaPanel() {
  const [data, setData] = useState<Salud | null>(null);
  const [cargando, setCargando] = useState(false);
  const cargar = useCallback(() => {
    setCargando(true);
    api.get<Salud>("/superuser/centinela").then(setData).catch(() => {}).finally(() => setCargando(false));
  }, []);
  useEffect(() => { cargar(); }, [cargar]);

  if (!data) {
    return (
      <ClinicalCard>
        <SectionHeader title="Centinela" icon={Activity} />
        <div className="text-[12px] text-slate-400 italic py-4 text-center">Comprobando…</div>
      </ClinicalCard>
    );
  }

  const trabajos = data.sistema.find((s) => s.clave === "trabajos_programados");
  const sistema = data.sistema.filter((s) => s.clave !== "trabajos_programados");
  const tareas = trabajos ? parseTareas(trabajos.detalle) : [];
  const tareasSinDatos = tareas.filter(sinDatos).length;
  const cuenta = (e: string) => data.sistema.filter((s) => s.estado === e).length;

  const conocidas = new Set(GRUPOS.flatMap((g) => g.claves));
  const clavesSistema = new Set(data.sistema.map((s) => s.clave));
  const filasIA = resumirIA(data.integraciones, clavesSistema);
  const grupos = [
    ...GRUPOS.map((g) => ({
      ...g,
      filas: [
        ...g.claves.map((c) => sistema.find((s) => s.clave === c)).filter((s): s is Chequeo => !!s)
          .map((s) => ({ estado: s.estado, titulo: s.label, detalle: s.detalle })),
        ...(g.id === "ia" ? filasIA.map((f) => ({ estado: f.estado, titulo: f.titulo, detalle: f.detalle })) : []),
      ],
    })),
    { id: "otros", titulo: "Otros", icono: Server, claves: [],
      filas: sistema.filter((s) => !conocidas.has(s.clave)).map((s) => ({ estado: s.estado, titulo: s.label, detalle: s.detalle })) },
  ].filter((g) => g.filas.length > 0);

  // Lo que requiere atención sube arriba del todo. «Trabajos programados» no vuelca las 12 tareas.
  const avisos = [
    ...sistema.filter((s) => s.estado !== "ok").map((s) => ({ estado: s.estado, titulo: s.label, detalle: s.detalle })),
    ...(trabajos && trabajos.estado !== "ok"
      ? [{ estado: trabajos.estado, titulo: trabajos.label,
          detalle: tareasSinDatos > 0 ? `${tareasSinDatos} de ${tareas.length} tareas sin ejecución registrada todavía` : trabajos.detalle }]
      : []),
  ];

  return (
    <div className="space-y-4">
      <ClinicalCard>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <div className="flex items-center gap-2.5">
            <span className={`w-3.5 h-3.5 rounded-full ${DOT[data.nivel] ?? "bg-slate-300"}`} />
            <div>
              <div className="text-[15px] font-semibold text-[#1500A0] leading-tight">Centinela · {ESTADO_TXT[data.nivel] ?? data.nivel}</div>
              <div className="text-[11px] text-slate-400">comprobado a las {new Date(data.comprobado).toLocaleTimeString("es-ES")}</div>
            </div>
          </div>
          <div className="flex gap-2 text-[11.5px]">
            <span className="px-2 py-1 border border-[#e5e7eb] rounded-sm bg-white"><b className="text-[#0F8C7D]">{cuenta("ok")}</b> OK</span>
            <span className="px-2 py-1 border border-[#e5e7eb] rounded-sm bg-white"><b className="text-[#7C3AED]">{cuenta("warn")}</b> atención</span>
            <span className="px-2 py-1 border border-[#e5e7eb] rounded-sm bg-white"><b className="text-[#C026D3]">{cuenta("error")}</b> error</span>
          </div>
          <div className="ml-auto">
            <ClinicalButton variant="ghost" size="sm" icon={RefreshCw} disabled={cargando} onClick={cargar}>
              {cargando ? "Comprobando…" : "Actualizar"}
            </ClinicalButton>
          </div>
        </div>
      </ClinicalCard>

      {avisos.length > 0 && (
        <ClinicalCard>
          <SectionHeader title="Requiere atención" icon={AlertTriangle} />
          <div>{avisos.map((a, i) => <Fila key={i} {...a} />)}</div>
        </ClinicalCard>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
        {[grupos.filter((g) => g.id === "infra" || g.id === "ia"), grupos.filter((g) => g.id !== "infra" && g.id !== "ia")].map((col, i) => (
          <div key={i} className="space-y-4">
            {col.map((g) => <Grupo key={g.id} titulo={g.titulo} icono={g.icono} filas={g.filas} />)}
          </div>
        ))}
      </div>

      {tareas.length > 0 && (
        <ClinicalCard>
          <SectionHeader title="Tareas programadas" icon={Clock}
            action={<span className="text-[11px] text-slate-400">
              {tareas.length - tareasSinDatos}/{tareas.length} con ejecución registrada</span>} />
          <details open={tareasSinDatos < tareas.length}>
            <summary className="text-[11.5px] text-[#1ca0d1] cursor-pointer select-none mb-1.5">Ver las {tareas.length} tareas</summary>
            <table className="w-full text-[11.5px] border-collapse">
              <thead>
                <tr className="text-left text-[#1500A0]">
                  <th className="font-semibold px-2 py-1 border-b border-[#e5e7eb]">Tarea</th>
                  <th className="font-semibold px-2 py-1 border-b border-[#e5e7eb]">Última ejecución</th>
                </tr>
              </thead>
              <tbody>
                {tareas.map((t) => (
                  <tr key={t.nombre}>
                    <td className="px-2 py-1 border-b border-[#f0f2f5] text-[#33415c] font-medium whitespace-nowrap">{t.nombre.replace(/_/g, " ")}</td>
                    <td className={`px-2 py-1 border-b border-[#f0f2f5] ${sinDatos(t) ? "text-slate-400 italic" : "text-[#33415c]"}`}>
                      {sinDatos(t) ? "sin ejecución registrada todavía" : t.texto}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </ClinicalCard>
      )}
    </div>
  );
}
