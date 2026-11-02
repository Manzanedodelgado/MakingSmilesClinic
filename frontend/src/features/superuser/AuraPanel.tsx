"use client";
import { useCallback, useEffect, useState } from "react";
import { Activity, RefreshCw, ChevronRight, Cog, Fingerprint, ListChecks } from "lucide-react";
import { api } from "@/shared/lib/api";
import { errMsg } from "@/shared/lib/errores";
import { ClinicalCard, SectionHeader, ClinicalButton, INPUT } from "@/shared/components";
import { AuraConfig } from "@/features/agentes/RuedaAgentes";
import { DOT, ESTADO_TXT, type EspejoCentinela } from "./estado";

type EstadoAura = {
  id: string; activa: boolean; operativa: boolean; modelo: string; baseUrl: string | null;
  capacidadesActivas: string[]; capacidadesTotales: number;
};
type FichaAura = { id: string; nombre: string; parcela: string; capacidades: Record<string, string> };

const LAB = "block text-[11px] font-semibold text-[#1500A0] mb-1";
const SUBTABS = [
  { id: "estado", label: "Estado" },
  { id: "seguridad", label: "Seguridad" },
  { id: "capacidades", label: "Capacidades" },
  { id: "config", label: "Configuración" },
] as const;
type SubTab = (typeof SUBTABS)[number]["id"];

export function AuraPanel({ onVerCentinela }: { onVerCentinela: () => void }) {
  const [tab, setTab] = useState<SubTab>("estado");
  const [estado, setEstado] = useState<EstadoAura | null>(null);
  const [ficha, setFicha] = useState<FichaAura | null>(null);
  const [cent, setCent] = useState<EspejoCentinela | null>(null);
  const [cargandoCent, setCargandoCent] = useState(false);

  const [pinFijado, setPinFijado] = useState<boolean | null>(null);
  const [pinError, setPinError] = useState(false);
  const [pinNuevo, setPinNuevo] = useState("");
  const [guardandoPin, setGuardandoPin] = useState(false);
  const [msgPin, setMsgPin] = useState("");

  const [guardandoCap, setGuardandoCap] = useState("");
  const [msgCap, setMsgCap] = useState("");

  const load = useCallback(() => {
    api.get<{ fijado: boolean }>("/agentes/aura/pin")
      .then((r) => setPinFijado(Boolean(r.fijado))).catch(() => setPinError(true));
    api.get<{ agentes: EstadoAura[] }>("/agentes/estado/todos")
      .then((r) => setEstado(r.agentes.find((a) => a.id === "aura") ?? null)).catch(() => {});
    api.get<{ agentes: FichaAura[] }>("/agentes")
      .then((r) => setFicha(r.agentes.find((a) => a.id === "aura") ?? null)).catch(() => {});
  }, []);
  const cargarCent = useCallback(() => {
    setCargandoCent(true);
    api.get<EspejoCentinela>("/agentes/aura/centinela")
      .then(setCent).catch(() => {}).finally(() => setCargandoCent(false));
  }, []);
  useEffect(() => { load(); cargarCent(); }, [load, cargarCent]);

  // Sin try/catch: el gate prohíbe envolver en `try` llamadas a raíces que no toco —
  // la promesa baja por su propio `.catch` (mismo patrón que `load` de aquí arriba).
  function guardarPin() {
    setGuardandoPin(true);
    api.put<{ ok: boolean }>("/agentes/aura/pin", { pin: pinNuevo })
      .then(() => {
        setPinFijado(true);
        setPinNuevo("");
        setMsgPin("PIN guardado ✓ — cualquier sesión desbloqueada queda cerrada");
        setTimeout(() => setMsgPin(""), 3000);
      })
      .catch((e) => {
        // p.ej. "El PIN debe tener entre 4 y 8 dígitos." (HTTP 400 con detail)
        setMsgPin(errMsg(e));
        setTimeout(() => setMsgPin(""), 4500);
      })
      .finally(() => setGuardandoPin(false));
  }

  // Interruptor de una capacidad de Aura: PATCH /agentes/aura/config (solo SuperUser en el backend).
  function alternar(clave: string, valor: boolean) {
    setGuardandoCap(clave);
    setMsgCap("");
    api.patch<{ ok: boolean; motivo?: string; estado?: EstadoAura | null }>("/agentes/aura/config", { capacidad: clave, valor })
      .then((r) => {
        if (r.ok && r.estado) setEstado(r.estado);
        else setMsgCap(r.motivo ?? "No se pudo cambiar la capacidad.");
      })
      .catch((e) => setMsgCap(errMsg(e)))
      .finally(() => setGuardandoCap(""));
  }

  const caps = Object.entries(ficha?.capacidades ?? {}).map(([clave, texto]) => ({
    clave, texto, on: estado ? estado.capacidadesActivas.includes(clave) : false,
  }));

  return (
    <div className="space-y-4">
      <div className="flex gap-1 border-b border-[#e5e7eb]">
        {SUBTABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-3.5 py-2 text-[12px] font-semibold -mb-px border-b-2 transition-colors ${
              tab === t.id ? "border-[#1500A0] text-[#1500A0]" : "border-transparent text-slate-400 hover:text-[#1500A0]"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "estado" && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
          <ClinicalCard>
            <SectionHeader title="Aura — la asistente de administración" icon={Cog} />
            <p className="text-[12px] text-[#7f8c8d] mb-3">{ficha?.parcela ?? "Cargando…"}</p>
            <div className="grid grid-cols-3 gap-2">
              <div className="border border-[#e5e7eb] rounded-sm bg-white px-3 py-2">
                <div className="text-[10.5px] uppercase tracking-wide text-slate-400">Estado</div>
                <div className="flex items-center gap-2 mt-1 text-[12px] font-semibold text-[#1500A0]">
                  <span className={`w-2.5 h-2.5 rounded-full ${estado?.operativa ? "bg-[#20BEAB]" : estado?.activa ? "bg-[#7C3AED]" : "bg-slate-300"}`} />
                  {estado ? (estado.operativa ? "Operativa" : estado.activa ? "Encendida · no operativa" : "Apagada") : "…"}
                </div>
              </div>
              <div className="border border-[#e5e7eb] rounded-sm bg-white px-3 py-2">
                <div className="text-[10.5px] uppercase tracking-wide text-slate-400">Capacidades</div>
                <div className="mt-1 text-[12px] font-semibold text-[#1500A0]">
                  {estado ? `${estado.capacidadesActivas.length} de ${estado.capacidadesTotales} activas` : "…"}
                </div>
              </div>
              <div className="border border-[#e5e7eb] rounded-sm bg-white px-3 py-2">
                <div className="text-[10.5px] uppercase tracking-wide text-slate-400">Escritura</div>
                <div className="mt-1 text-[12px] font-semibold text-[#1500A0]">
                  {pinError ? "No se pudo consultar" : pinFijado === null ? "…" : pinFijado ? "Protegida con PIN" : "Sin PIN fijado"}
                </div>
              </div>
            </div>
            <p className="text-[11.5px] text-[#7f8c8d] mt-3">
              Modelo: <b className="text-[#33415c]">{estado?.modelo ?? "…"}</b>
              {estado?.baseUrl ? <span> · {estado.baseUrl}</span> : null}
            </p>
          </ClinicalCard>

          <ClinicalCard>
            <SectionHeader title="Centinela bajo su mirada" icon={Activity}
              action={
                <div className="flex gap-1">
                  <ClinicalButton variant="ghost" size="sm" icon={RefreshCw} disabled={cargandoCent} onClick={cargarCent}>
                    {cargandoCent ? "Comprobando…" : "Actualizar"}
                  </ClinicalButton>
                  <ClinicalButton variant="ghost" size="sm" icon={ChevronRight} onClick={onVerCentinela}>
                    Ver Centinela
                  </ClinicalButton>
                </div>} />
            {!cent ? (
              <div className="text-[12px] text-slate-400 italic py-4 text-center">Comprobando…</div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-[12px]">
                  <span className={`w-2.5 h-2.5 rounded-full ${DOT[cent.nivel_actual] ?? "bg-slate-300"}`} />
                  <span className="font-semibold text-[#1500A0]">
                    Nivel actual: {ESTADO_TXT[cent.nivel_actual] ?? cent.nivel_actual}
                  </span>
                  {cent.ultima_revision && (
                    <span className="text-slate-400">
                      · última revisión {new Date(cent.ultima_revision).toLocaleString("es-ES")}
                      {cent.origen ? ` (${cent.origen})` : ""}
                    </span>
                  )}
                </div>
                {cent.avisos.length === 0 ? (
                  <div className="text-[12px] text-[#7f8c8d]">Sin avisos en los últimos 2 días — todo tranquilo.</div>
                ) : (
                  <div className="space-y-2">
                    {cent.avisos.slice(0, 3).map((av, i) => (
                      <div key={i} className="bg-[#FFFFFF] border border-[#e5e7eb] rounded-sm px-3 py-2">
                        <div className="flex items-center gap-2 text-[11px]">
                          <span className={`w-2 h-2 rounded-full ${DOT[av.nivel ?? ""] ?? "bg-slate-300"}`} />
                          <span className="font-semibold text-[#33415c]">
                            Aviso {ESTADO_TXT[av.nivel ?? ""] ?? av.nivel ?? ""}
                          </span>
                          <span className="text-slate-400">
                            {av.cuando ? new Date(av.cuando).toLocaleString("es-ES") : ""}
                            {av.enviados.length ? ` · enviado por ${av.enviados.join(", ")}` : ""}
                          </span>
                        </div>
                        {av.fallando.length > 0 && (
                          <div className="text-[11px] text-[#7f8c8d] mt-1">
                            {av.fallando.slice(0, 2).map((f, j) => (
                              <div key={j} className="truncate" title={f.detalle}>· {f.sistema} — {ESTADO_TXT[f.estado] ?? f.estado}: {f.detalle}</div>
                            ))}
                            {av.fallando.length > 2 && <div className="text-slate-400">+ {av.fallando.length - 2} más</div>}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
                <p className="text-[11px] text-[#7f8c8d]">
                  Así lo ve Aura en su chat. Cuando hay fuego, ella lo apaga con{" "}
                  <b>revisar Centinela</b> — acción de escritura que exige su PIN desbloqueado.
                </p>
              </div>
            )}
          </ClinicalCard>
        </div>
      )}

      {tab === "seguridad" && (
        <div className="max-w-3xl">
          <ClinicalCard>
            <SectionHeader title="PIN de escritura" icon={Fingerprint} />
            <p className="text-[12px] text-[#7f8c8d] mb-2.5">
              Segundo factor de SuperUser: sin PIN desbloqueado, Aura solo consulta — crear o
              modificar le queda vetado. El desbloqueo dura 15 minutos, se guarda hasheado
              (aquí nunca se muestra) y cambiarlo cierra al instante cualquier sesión abierta.
              Tres fallos seguidos bloquean la verificación 15 minutos.
            </p>
            <div className="flex flex-wrap items-end gap-2">
              <div>
                <label className={LAB}>
                  {pinError ? "No se pudo consultar el estado del PIN" : pinFijado === null ? "Consultando…" : pinFijado ? "PIN fijado (4–8 dígitos)" : "Sin fijar (4–8 dígitos)"}
                </label>
                <input className={INPUT} type="password" inputMode="numeric" maxLength={8}
                  value={pinNuevo} onChange={(e) => setPinNuevo(e.target.value.replace(/\D/g, ""))}
                  placeholder={pinFijado ? "•••• para cambiar" : "4–8 dígitos"} />
              </div>
              <ClinicalButton variant="save" onClick={guardarPin} disabled={guardandoPin || pinNuevo.length < 4}>
                {guardandoPin ? "Guardando…" : pinFijado ? "Cambiar PIN" : "Fijar PIN"}
              </ClinicalButton>
              {msgPin && <span className="text-[11px] text-[#1ca0d1] pb-1.5">{msgPin}</span>}
            </div>
          </ClinicalCard>
        </div>
      )}

      {tab === "capacidades" && (
        <div className="max-w-3xl">
          <ClinicalCard>
            <SectionHeader title="Capacidades de Aura" icon={ListChecks}
              action={<span className="text-[11px] text-slate-400">
                {estado ? `${estado.capacidadesActivas.length}/${estado.capacidadesTotales} activas` : ""}</span>} />
            <p className="text-[11.5px] text-[#7f8c8d] mb-2">
              Apagar una la corta en su chat y en REST al instante. Las que escriben siguen exigiendo el PIN.
            </p>
            {caps.length === 0 ? (
              <div className="text-[12px] text-slate-400 italic py-2 text-center">Cargando…</div>
            ) : (
              <div>
                {caps.map((c) => (
                  <label key={c.clave} className="flex items-start gap-3 px-2 py-2 border-b border-[#f0f2f5] last:border-b-0 cursor-pointer">
                    <input type="checkbox" className="mt-0.5" style={{ accentColor: "#1500A0" }}
                      checked={c.on} disabled={guardandoCap === c.clave || !estado}
                      onChange={(e) => alternar(c.clave, e.target.checked)} />
                    <span className="min-w-0">
                      <span className="block text-[12px] font-semibold text-[#33415c]">{c.texto || c.clave}</span>
                      <span className="block text-[11px] text-[#7f8c8d]">{c.clave}</span>
                    </span>
                  </label>
                ))}
              </div>
            )}
            {msgCap && <p className="text-[11.5px] text-[#C026D3] mt-2">{msgCap}</p>}
          </ClinicalCard>
        </div>
      )}

      {tab === "config" && <AuraConfig tituloCapacidades="Capacidades del motor de agentes" />}
    </div>
  );
}
