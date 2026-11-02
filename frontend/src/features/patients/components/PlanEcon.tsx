"use client";
import { Wallet, X, Check } from "lucide-react";
/** PLAN ECON. — cuenta corriente del paciente: movimientos (deudas) + saldo. Solo BBDD nueva. */
import { useCallback, useEffect, useState } from "react";
import { ClinicalCard, SectionHeader, Modal, ModalBody, ModalButton, MODAL_INPUT } from "@/shared/components";
import { patientService } from "../services/patientService";
import type { Financiera, FormaPago, MovimientoEcon, PlanEconomico, Presupuesto } from "../types/patient";
import { PlanEconDocs } from "./PlanEconDocs";

const eur = (n: number) => n.toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
const fecha = (s: string | null) => (s ? new Date(s).toLocaleDateString("es-ES") : "—");

const BADGE: Record<MovimientoEcon["estado"], string> = {
  "A FAVOR": "bg-[#FFFFFF] border-[#93c5fd] text-[#1d4ed8]",
  LIQUIDADO: "bg-[#FFFFFF] border-[#9FE6DB] text-[#0F8C7D]",
  PARCIAL: "bg-[#FFFFFF] border-[#7dd3fc] text-[#0369a1]",
  PENDIENTE: "bg-[#FFFFFF] border-[#C4B5FD] text-[#6D28D9]",
  INCOBRABLE: "bg-[#FFFFFF] border-[#E9A8F5] text-[#C026D3]",
};

function Total({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="flex flex-col px-4 py-2 border-l border-[#e5e7eb] first:border-l-0">
      <span className="text-[10px] uppercase tracking-wide text-slate-400">{label}</span>
      <span className="text-[18px] font-semibold" style={{ color }}>{value}</span>
    </div>
  );
}

// Presupuesto que admite pagos asociados: Aceptado, En curso, Finalizado, Aceptado parcial.
const PRESUPUESTO_ACEPTADO = [3, 4, 5, 6];

/** `mov` = cobro de un cargo concreto. Sin `mov` = pago a cuenta o a un presupuesto aceptado:
 *  queda como saldo y se descuenta según se realizan los tratamientos. */
export function CobroModal({ patientId, mov, onClose, onSaved }: {
  patientId: number; mov: MovimientoEcon | null; onClose: () => void; onSaved: () => void;
}) {
  const [formas, setFormas] = useState<FormaPago[]>([]);
  const [financieras, setFinancieras] = useState<Financiera[]>([]);
  const [formaId, setFormaId] = useState<number | null>(null);
  const [importe, setImporte] = useState(mov ? mov.pendiente : 0);
  const [presupuestos, setPresupuestos] = useState<Presupuesto[]>([]);
  const [presupuestoId, setPresupuestoId] = useState<number | null>(null);
  const [neto, setNeto] = useState<number | "">("");
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Campos de financiación
  const [financieraId, setFinancieraId] = useState<number | null>(null);
  const [entrada, setEntrada] = useState<number | "">("");
  const [numCuotas, setNumCuotas] = useState<number | "">("");
  const [interesPct, setInteresPct] = useState<number | "">("");
  const [cuotaMensual, setCuotaMensual] = useState<number | "">("");

  useEffect(() => {
    patientService.formasPago().then((r) => { setFormas(r.formas); setFormaId((p) => p ?? r.formas[0]?.id ?? null); })
      .catch((e) => setErr(e instanceof Error ? e.message : "No se pudieron cargar las formas de pago"));
    patientService.financieras().then((r) => setFinancieras(r.financieras)).catch(() => {});
  }, []);
  useEffect(() => {
    if (mov) return;
    patientService.presupuestos(patientId)
      .then((r) => setPresupuestos(r.presupuestos.filter((p) => p.estado_id != null && PRESUPUESTO_ACEPTADO.includes(p.estado_id))))
      .catch((e) => setErr(e instanceof Error ? e.message : "No se pudieron cargar los presupuestos"));
  }, [mov, patientId]);
  const esFin = formas.find((f) => f.id === formaId)?.grupo === "Financiación";
  const coste = esFin && neto !== "" ? Math.max(0, importe - Number(neto)) : 0;

  // Auto-calcular neto cuando cambia la financiera
  useEffect(() => {
    if (esFin && financieraId && importe > 0) {
      const fin = financieras.find((f) => f.id === financieraId);
      if (fin) setNeto(Math.round((importe * (100 - fin.comision_pct) / 100) * 100) / 100);
    }
  }, [esFin, financieraId, importe, financieras]);

  const guardar = async () => {
    if (esFin && (neto === "" || Number(neto) <= 0 || Number(neto) > importe)) {
      setErr("En financiación, el neto debe ser mayor que 0 y no superar el bruto."); return;
    }
    if (esFin && !financieraId) { setErr("Selecciona la entidad financiera."); return; }
    if (formaId == null) { setErr("Elige la forma de pago."); return; }
    if (!(importe > 0)) { setErr("El importe debe ser mayor que cero."); return; }
    if (mov && importe > mov.pendiente) { setErr(`El importe supera lo pendiente (${eur(mov.pendiente)}).`); return; }
    setBusy(true); setErr(null);
    try {
      await patientService.registrarCobro(patientId, {
        deuda_id: mov ? mov.id : undefined,
        presupuesto_id: !mov && presupuestoId != null ? presupuestoId : undefined,
        fecha, importe, forma_pago_id: formaId,
        neto: esFin ? Number(neto) : undefined,
        financiera_id: esFin ? financieraId ?? undefined : undefined,
        entrada: esFin && entrada !== "" ? Number(entrada) : undefined,
        num_cuotas: esFin && numCuotas !== "" ? Number(numCuotas) : undefined,
        interes_pct: esFin && interesPct !== "" ? Number(interesPct) : undefined,
        cuota_mensual: esFin && cuotaMensual !== "" ? Number(cuotaMensual) : undefined,
      });
      onSaved();
    } catch (e) { setErr(e instanceof Error ? e.message : "No se pudo registrar el cobro"); }
    finally { setBusy(false); }
  };

  const lbl = "text-[11px] uppercase tracking-wide text-[#21A2E5] font-semibold";
  return (
    <Modal
      title={mov ? "Registrar cobro" : "Cobro a cuenta"}
      subtitle={mov ? `${mov.concepto} · pendiente ${eur(mov.pendiente)}` : undefined}
      onClose={onClose}
      size="sm"
      footer={
        <>
          <ModalButton variant="magenta" icon={X} onClick={onClose}>Cancelar</ModalButton>
          <ModalButton variant="primary" icon={Check} onClick={guardar} disabled={busy}>
            {busy ? "Guardando…" : "Registrar cobro"}
          </ModalButton>
        </>
      }
    >
      <ModalBody>
        <div className="flex flex-col gap-3">
          {!mov && (
            <label className="flex flex-col gap-1"><span className={lbl}>Asociar a</span>
              <select value={presupuestoId ?? ""} onChange={(e) => setPresupuestoId(e.target.value === "" ? null : Number(e.target.value))} className={MODAL_INPUT}>
                <option value="">A cuenta (se descuenta de cualquier tratamiento)</option>
                {presupuestos.map((p) => (
                  <option key={p.id} value={p.id}>
                    {(p.titulo || `Presupuesto ${p.num ?? p.id}`)} · {p.estado} · pendiente {eur(p.pendiente)}
                  </option>
                ))}
              </select>
              <span className="text-[11px] text-slate-400">
                {presupuestoId == null ? "El saldo se irá descontando de los tratamientos que se realicen."
                  : "El saldo solo se descuenta de los tratamientos de este presupuesto."}
              </span>
            </label>
          )}
          <label className="flex flex-col gap-1"><span className={lbl}>Fecha</span>
            <input type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} className={MODAL_INPUT} /></label>
          <label className="flex flex-col gap-1"><span className={lbl}>Forma de pago</span>
            <select value={formaId ?? ""} onChange={(e) => setFormaId(Number(e.target.value))} className={MODAL_INPUT}>
              {formas.map((f) => <option key={f.id} value={f.id}>{f.nombre}</option>)}
            </select></label>
          {!esFin ? (
            <label className="flex flex-col gap-1"><span className={lbl}>Importe</span>
              <input type="number" step="0.01" value={importe} onChange={(e) => setImporte(Number(e.target.value))} className={MODAL_INPUT} /></label>
          ) : (
            <>
              <label className="flex flex-col gap-1"><span className={lbl}>Financiera</span>
                <select value={financieraId ?? ""} onChange={(e) => setFinancieraId(e.target.value ? Number(e.target.value) : null)} className={MODAL_INPUT}>
                  <option value="">— Selecciona financiera —</option>
                  {financieras.map((f) => <option key={f.id} value={f.id}>{f.nombre} ({f.comision_pct}%)</option>)}
                </select></label>
              <label className="flex flex-col gap-1"><span className={lbl}>Bruto (100% que paga el paciente)</span>
                <input type="number" step="0.01" value={importe} onChange={(e) => setImporte(Number(e.target.value))} className={MODAL_INPUT} /></label>
              <div className="grid grid-cols-2 gap-2">
                <label className="flex flex-col gap-1"><span className={lbl}>Entrada</span>
                  <input type="number" step="0.01" value={entrada} onChange={(e) => setEntrada(e.target.value === "" ? "" : Number(e.target.value))} className={MODAL_INPUT} placeholder="0,00" /></label>
                <label className="flex flex-col gap-1"><span className={lbl}>Nº cuotas</span>
                  <input type="number" step="1" min="1" value={numCuotas} onChange={(e) => setNumCuotas(e.target.value === "" ? "" : Number(e.target.value))} className={MODAL_INPUT} placeholder="12" /></label>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <label className="flex flex-col gap-1"><span className={lbl}>% Interés</span>
                  <input type="number" step="0.01" min="0" value={interesPct} onChange={(e) => setInteresPct(e.target.value === "" ? "" : Number(e.target.value))} className={MODAL_INPUT} placeholder="0,00" /></label>
                <label className="flex flex-col gap-1"><span className={lbl}>Cuota mensual</span>
                  <input type="number" step="0.01" value={cuotaMensual} onChange={(e) => setCuotaMensual(e.target.value === "" ? "" : Number(e.target.value))} className={MODAL_INPUT} placeholder="0,00" /></label>
              </div>
              <label className="flex flex-col gap-1"><span className={lbl}>Neto (lo que recibe la clínica)</span>
                <input type="number" step="0.01" value={neto} onChange={(e) => setNeto(e.target.value === "" ? "" : Number(e.target.value))} className={MODAL_INPUT} placeholder="0,00" /></label>
              <div className="text-[12px] text-[#6D28D9] bg-[#FFFFFF] border border-[#C4B5FD] rounded-sm px-2 py-1.5">
                Coste financiero: <b>{eur(coste)}</b> <span className="text-slate-400">(bruto − neto)</span></div>
            </>
          )}
          {err && <div className="text-[12px] text-[#C026D3]">{err}</div>}
        </div>
      </ModalBody>
    </Modal>
  );
}

function LiberarModal({ patientId, pago, onClose, onSaved }: {
  patientId: number; pago: PlanEconomico["pagos"][0]; onClose: () => void; onSaved: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const liberar = async () => {
    setBusy(true); setErr(null);
    try {
      await patientService.liberarPago(patientId, pago.id);
      onSaved();
    } catch (e) { setErr(e instanceof Error ? e.message : "No se pudo liberar el pago"); }
    finally { setBusy(false); }
  };
  return (
    <Modal
      title="Liberar pago"
      onClose={onClose}
      size="sm"
      footer={
        <>
          <ModalButton variant="magenta" icon={X} onClick={onClose}>Cancelar</ModalButton>
          <ModalButton variant="primary" icon={Check} onClick={liberar} disabled={busy}>
            {busy ? "Liberando…" : "Liberar"}
          </ModalButton>
        </>
      }
    >
      <ModalBody>
        <div className="flex flex-col gap-3">
          <p className="text-[12px] text-slate-600">
            ¿Liberar <b>{eur(pago.saldo)}</b> del presupuesto <b>{pago.asociado_a}</b>?
          </p>
          <p className="text-[11px] text-slate-400">
            El saldo quedará como "a cuenta" y podrá descontarse de cualquier tratamiento.
          </p>
          {err && <div className="text-[12px] text-[#C026D3]">{err}</div>}
        </div>
      </ModalBody>
    </Modal>
  );
}

function ReasignarModal({ patientId, pago, onClose, onSaved }: {
  patientId: number; pago: PlanEconomico["pagos"][0]; onClose: () => void; onSaved: () => void;
}) {
  const [presupuestos, setPresupuestos] = useState<Presupuesto[]>([]);
  const [presupuestoId, setPresupuestoId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    patientService.presupuestos(patientId)
      .then((r) => setPresupuestos(r.presupuestos.filter((p) => p.estado_id != null && PRESUPUESTO_ACEPTADO.includes(p.estado_id) && p.id !== pago.presupuesto_id)))
      .catch((e) => setErr(e instanceof Error ? e.message : "No se pudieron cargar los presupuestos"));
  }, [patientId, pago.presupuesto_id]);
  const reasignar = async () => {
    setBusy(true); setErr(null);
    try {
      await patientService.reasignarPago(patientId, pago.id, presupuestoId);
      onSaved();
    } catch (e) { setErr(e instanceof Error ? e.message : "No se pudo reasignar el pago"); }
    finally { setBusy(false); }
  };
  return (
    <Modal
      title="Reasignar pago"
      onClose={onClose}
      size="md"
      footer={
        <>
          <ModalButton variant="magenta" icon={X} onClick={onClose}>Cancelar</ModalButton>
          <ModalButton variant="primary" icon={Check} onClick={reasignar} disabled={busy}>
            {busy ? "Reasignando…" : "Reasignar"}
          </ModalButton>
        </>
      }
    >
      <ModalBody>
        <div className="flex flex-col gap-3">
          <p className="text-[12px] text-slate-600">
            Reasignar <b>{eur(pago.saldo)}</b> de <b>{pago.asociado_a || "A cuenta"}</b> a:
          </p>
          <select value={presupuestoId ?? ""} onChange={(e) => setPresupuestoId(e.target.value === "" ? null : Number(e.target.value))} className={MODAL_INPUT}>
            <option value="">A cuenta (se descuenta de cualquier tratamiento)</option>
            {presupuestos.map((p) => (
              <option key={p.id} value={p.id}>
                {(p.titulo || `Presupuesto ${p.num ?? p.id}`)} · {p.estado} · pendiente {eur(p.pendiente)}
              </option>
            ))}
          </select>
          <p className="text-[11px] text-slate-400">
            {presupuestoId == null ? "El saldo se irá descontando de los tratamientos que se realicen."
              : "El saldo solo se descuenta de los tratamientos del presupuesto elegido."}
          </p>
          {err && <div className="text-[12px] text-[#C026D3]">{err}</div>}
        </div>
      </ModalBody>
    </Modal>
  );
}

function SaldoOperacionModal({ patientId, mode, maxAmount, onClose, onSaved }: {
  patientId: number; mode: "transfer" | "refund";
  maxAmount: number; onClose: () => void; onSaved: () => void;
}) {
  const [importe, setImporte] = useState(maxAmount);
  const [fechaOp, setFechaOp] = useState(new Date().toISOString().slice(0, 10));
  const [motivo, setMotivo] = useState("Devolución de saldo");
  const [query, setQuery] = useState("");
  const [resultados, setResultados] = useState<Awaited<ReturnType<typeof patientService.buscar>>["pacientes"]>([]);
  const [destino, setDestino] = useState<Awaited<ReturnType<typeof patientService.buscar>>["pacientes"][number] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (mode !== "transfer" || query.trim().length < 2 || destino) { setResultados([]); return; }
    const timer = setTimeout(() => patientService.buscar(query.trim(), 10)
      .then((r) => setResultados(r.pacientes.filter((p) => p.id !== patientId)))
      .catch(() => setResultados([])), 250);
    return () => clearTimeout(timer);
  }, [mode, query, destino, patientId]);
  const guardar = async () => {
    if (!(importe > 0) || importe > maxAmount) { setErr(`El importe debe estar entre 0,01 € y ${eur(maxAmount)}.`); return; }
    if (mode === "transfer" && !destino) { setErr("Selecciona el paciente destinatario."); return; }
    if (mode === "refund" && !motivo.trim()) { setErr("Indica el motivo de la devolución."); return; }
    setBusy(true); setErr(null);
    try {
      if (mode === "transfer" && destino) await patientService.traspasarSaldo(patientId, destino.id, importe, fechaOp);
      else if (mode === "refund") await patientService.devolverSaldo(patientId, importe, fechaOp, motivo.trim());
      onSaved();
    } catch (e) { setErr(e instanceof Error ? e.message : "No se pudo guardar la operación"); }
    finally { setBusy(false); }
  };
  const title = mode === "transfer" ? "Traspasar saldo a otro paciente" : "Devolver saldo a favor";
  return (
    <Modal
      title={title}
      onClose={onClose}
      size="md"
      footer={
        <>
          <ModalButton variant="magenta" icon={X} onClick={onClose}>Cancelar</ModalButton>
          <ModalButton variant="primary" icon={Check} onClick={guardar} disabled={busy}>
            {busy ? "Guardando…" : mode === "refund" ? "Registrar devolución" : "Traspasar saldo"}
          </ModalButton>
        </>
      }
    >
      <ModalBody>
        <div className="flex flex-col gap-3">
          {mode === "transfer" && (
            <div className="flex flex-col gap-1">
              <label className="text-[11px] uppercase tracking-wide text-[#21A2E5] font-semibold">Paciente destinatario</label>
              {destino ? <div className="flex justify-between items-center border border-[#BFE4F7] rounded-md p-2 text-[12px]">
                <span>{destino.num_historia ? `Historia ${destino.num_historia} · ` : ""}{destino.nombre} {destino.apellidos}</span>
                <button onClick={() => { setDestino(null); setQuery(""); }} className="text-[#065AED] underline">Cambiar</button>
              </div> : <>
                <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Nº historia o nombre" className={MODAL_INPUT} />
                {resultados.map((p) => <button key={p.id} onClick={() => { setDestino(p); setQuery(""); }}
                  className="text-left px-2 py-1.5 text-[12px] border-b border-[#BFE4F7] hover:bg-[#E6EDFF]">
                  {p.num_historia ? `Historia ${p.num_historia} · ` : ""}{p.nombre} {p.apellidos}
                </button>)}
              </>}
            </div>
          )}
          <label className="flex flex-col gap-1"><span className="text-[11px] uppercase tracking-wide text-[#21A2E5] font-semibold">Importe (máximo {eur(maxAmount)})</span>
            <input type="number" min="0.01" max={maxAmount} step="0.01" value={importe}
              onChange={(e) => setImporte(Number(e.target.value))} className={MODAL_INPUT} /></label>
          {mode === "refund" && <label className="flex flex-col gap-1"><span className="text-[11px] uppercase tracking-wide text-[#21A2E5] font-semibold">Motivo</span>
            <input value={motivo} onChange={(e) => setMotivo(e.target.value)} maxLength={250} className={MODAL_INPUT} /></label>}
          <label className="flex flex-col gap-1"><span className="text-[11px] uppercase tracking-wide text-[#21A2E5] font-semibold">Fecha</span>
            <input type="date" value={fechaOp} onChange={(e) => setFechaOp(e.target.value)} className={MODAL_INPUT} /></label>
          {err && <div className="text-[12px] text-[#C026D3]">{err}</div>}
        </div>
      </ModalBody>
    </Modal>
  );
}


export function PlanEcon({ patientId }: { patientId: number }) {
  const [plan, setPlan] = useState<PlanEconomico | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sub, setSub] = useState<"movimientos" | "documentos">("movimientos");
  const [cobrando, setCobrando] = useState<MovimientoEcon | null>(null);
  const [aCuenta, setACuenta] = useState(false);
  const [liberando, setLiberando] = useState<PlanEconomico["pagos"][0] | null>(null);
  const [reasignando, setReasignando] = useState<PlanEconomico["pagos"][0] | null>(null);
  const [operacionSaldo, setOperacionSaldo] = useState<{ mode: "transfer" | "refund"; maxAmount: number } | null>(null);

  const cargar = useCallback(async () => {
    setLoading(true); setError(null);
    try { setPlan(await patientService.plan(patientId)); }
    catch (e) { setError(e instanceof Error ? e.message : "No se pudo cargar el plan económico"); }
    finally { setLoading(false); }
  }, [patientId]);
  useEffect(() => { cargar(); }, [cargar]);

  const TABS: { id: "movimientos" | "documentos"; label: string }[] = [
    { id: "movimientos", label: "Movimientos" }, { id: "documentos", label: "Documentos" },
  ];

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center bg-white border-b border-[#e5e7eb] px-3 shrink-0">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setSub(t.id)}
            className={`px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider border-b-2 transition-colors ${sub === t.id ? "text-[#1500A0] border-[#1ca0d1] bg-[#FFFFFF]" : "text-[#7f8c8d] border-transparent hover:text-[#1500A0]"}`}>
            {t.label}
          </button>
        ))}
      </div>
      <div className="flex-1 min-h-0 overflow-hidden">
        {sub === "documentos" ? <PlanEconDocs patientId={patientId} /> : (
          loading ? <p className="text-[12px] text-slate-400 p-4">Cargando plan económico…</p> :
          error ? <p className="text-[12px] text-[#C026D3] p-4">{error}</p> :
          !plan ? null :
    <div className="p-4 space-y-3 overflow-y-auto">
      <ClinicalCard noPadding>
        <SectionHeader
          variant="dark" title="Movimientos económicos" icon={Wallet}
          action={
            <div className="flex items-center gap-3">
              <span className="text-[10px] text-white/80 uppercase tracking-wide">{plan.movimientos.length} movimiento(s)</span>
              <button onClick={() => setACuenta(true)}
                className="px-2 py-0.5 text-[11px] font-semibold rounded-sm bg-white text-[#1500A0] hover:bg-[#E6EDFF]">Cobro a cuenta</button>
            </div>
          }
        />
        <table className="w-full text-[12px]">
          <thead>
            <tr className="bg-[#FFFFFF] text-[#1ca0d1] text-[10px] uppercase tracking-wide border-b border-[#e5e7eb]">
              <th className="text-left px-3 py-1.5 font-semibold">Fecha</th>
              <th className="text-left px-3 py-1.5 font-semibold">Concepto</th>
              <th className="text-right px-3 py-1.5 font-semibold">Importe</th>
              <th className="text-right px-3 py-1.5 font-semibold">Abonado</th>
              <th className="text-right px-3 py-1.5 font-semibold">Pendiente</th>
              <th className="text-center px-3 py-1.5 font-semibold">Estado</th>
              <th className="text-right px-3 py-1.5 font-semibold"></th>
            </tr>
          </thead>
          <tbody>
            {plan.movimientos.map((m) => (
              <tr key={m.id} className="border-b border-[#f0f2f5] hover:bg-[#E6EDFF]">
                <td className="px-3 py-1.5 text-slate-600">{fecha(m.fecha)}</td>
                <td className="px-3 py-1.5 text-[#333333]">{m.concepto}{m.num_factura ? <span className="text-slate-400"> · {m.num_factura}</span> : null}</td>
                <td className="px-3 py-1.5 text-right text-[#333333]">{eur(m.importe)}</td>
                <td className="px-3 py-1.5 text-right text-[#2DD9C3] font-semibold">{eur(m.abonado)}</td>
                <td className={`px-3 py-1.5 text-right font-semibold ${m.pendiente > 0 ? "text-[#C026D3]" : "text-[#0F8C7D]"}`}>{eur(m.pendiente)}</td>
                <td className="px-3 py-1.5 text-center">
                  <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold border ${BADGE[m.estado]}`}>{m.estado}</span>
                </td>
                <td className="px-3 py-1.5 text-right">
                  {m.pendiente > 0 && (
                    <button onClick={() => setCobrando(m)}
                      className="text-[11px] font-semibold text-[#065AED] hover:text-[#054AC2] underline">Cobrar</button>
                  )}
                            </td>
              </tr>
            ))}
            {plan.movimientos.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-6 text-center text-[12px] text-slate-400 italic">Sin movimientos económicos</td></tr>
            )}
          </tbody>
        </table>
      </ClinicalCard>

      <ClinicalCard noPadding>
        <SectionHeader variant="dark" title="Pagos" icon={Wallet}
          action={<div className="flex items-center gap-2">
            {plan.totales.saldo_a_favor > 0 && <button onClick={() => setOperacionSaldo({ mode: "transfer", maxAmount: plan.totales.saldo_a_favor })}
              className="px-2 py-0.5 text-[11px] font-semibold rounded-sm bg-white text-[#1500A0]">Traspasar saldo</button>}
            {plan.totales.saldo_a_favor > 0 && <button onClick={() => setOperacionSaldo({ mode: "refund", maxAmount: plan.totales.saldo_a_favor })}
              className="px-2 py-0.5 text-[11px] font-semibold rounded-sm bg-white text-[#1500A0]">Devolver saldo</button>}
            <span className="text-[10px] text-white/80 uppercase tracking-wide">{plan.pagos.length} pago(s)</span>
          </div>} />
        <table className="w-full text-[12px]">
          <thead>
            <tr className="bg-[#FFFFFF] text-[#1ca0d1] text-[10px] uppercase tracking-wide border-b border-[#e5e7eb]">
              <th className="text-left px-3 py-1.5 font-semibold">Fecha</th>
              <th className="text-left px-3 py-1.5 font-semibold">Forma de pago</th>
              <th className="text-left px-3 py-1.5 font-semibold">Asociado a</th>
              <th className="text-right px-3 py-1.5 font-semibold">Importe</th>
              <th className="text-right px-3 py-1.5 font-semibold">Saldo</th>
              <th className="text-right px-3 py-1.5 font-semibold"></th>
            </tr>
          </thead>
          <tbody>
            {[...plan.pagos].reverse().map((p) => (
              <tr key={p.id} className="border-b border-[#f0f2f5] hover:bg-[#E6EDFF]">
                <td className="px-3 py-1.5 text-slate-600">{fecha(p.fecha)}</td>
                <td className="px-3 py-1.5 text-[#333333]">{p.forma_pago ?? "—"}</td>
                <td className={"px-3 py-1.5 " + (p.asociado_a === "Histórico GELITE" ? "text-slate-400" : "text-[#333333]")}>
                  {p.asociado_a}
                  {p.referencia && <span className="block text-[9px] text-slate-400" title={p.referencia}>Ref. {p.referencia.split(":")[1]?.slice(0, 8) || p.referencia}</span>}
                </td>
                <td className={`px-3 py-1.5 text-right ${p.importe < 0 ? "text-[#C026D3]" : "text-[#333333]"}`}>{eur(p.importe)}</td>
                <td className={`px-3 py-1.5 text-right font-semibold ${p.saldo > 0 ? "text-[#065AED]" : "text-slate-400"}`}>{p.saldo > 0 ? eur(p.saldo) : "—"}</td>
                <td className="px-3 py-1.5 text-right">
                  {p.saldo > 0 && p.asociado_a !== "Histórico GELITE" && (
                    <div className="flex gap-2 justify-end">
                      {p.presupuesto_id && (
                        <button onClick={() => setLiberando(p)}
                          className="text-[11px] font-semibold text-[#065AED] hover:text-[#054AC2] underline">Liberar</button>
                      )}
                      <button onClick={() => setReasignando(p)}
                        className="text-[11px] font-semibold text-slate-500 hover:text-slate-700 underline">Reasignar</button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {plan.pagos.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-[12px] text-slate-400 italic">Sin pagos</td></tr>
            )}
          </tbody>
        </table>
      </ClinicalCard>

      <ClinicalCard noPadding>
        <div className="flex items-center flex-wrap">
          <Total label="Cargado (detalle)" value={eur(plan.totales.cargado)} color="#065AED" />
          <Total label="Abonado (detalle)" value={eur(plan.totales.abonado)} color="#2DD9C3" />
          <Total label="Pendiente (detalle)" value={eur(plan.totales.pendiente)} color={plan.totales.pendiente > 0 ? "#C026D3" : "#0F8C7D"} />
          {plan.totales.saldo_a_favor > 0 &&
            <Total label="A favor (caja)" value={eur(plan.totales.saldo_a_favor)} color="#065AED" />}
          {plan.totales.saldo_historico !== 0 &&
            <Total label={plan.totales.saldo_historico > 0 ? "Deuda histórica" : "Crédito histórico"}
              value={eur(Math.abs(plan.totales.saldo_historico))}
              color={plan.totales.saldo_historico > 0 ? "#C026D3" : "#065AED"} />}
          <Total label={plan.totales.saldo_total > 0 ? "Saldo neto: debe" : plan.totales.saldo_total < 0 ? "Saldo neto: a favor" : "Saldo neto"}
            value={eur(Math.abs(plan.totales.saldo_total))}
            color={plan.totales.saldo_total > 0 ? "#C026D3" : plan.totales.saldo_total < 0 ? "#065AED" : "#0F8C7D"} />
          {plan.totales.costeFinanciero > 0 &&
            <Total label="Coste financiero" value={eur(plan.totales.costeFinanciero)} color="#6D28D9" />}
        </div>
      </ClinicalCard>
      {cobrando && <CobroModal patientId={patientId} mov={cobrando}
        onClose={() => setCobrando(null)} onSaved={() => { setCobrando(null); cargar(); }} />}
      {aCuenta && <CobroModal patientId={patientId} mov={null}
        onClose={() => setACuenta(false)} onSaved={() => { setACuenta(false); cargar(); }} />}
      {liberando && <LiberarModal patientId={patientId} pago={liberando}
        onClose={() => setLiberando(null)} onSaved={() => { setLiberando(null); cargar(); }} />}
      {reasignando && <ReasignarModal patientId={patientId} pago={reasignando}
        onClose={() => setReasignando(null)} onSaved={() => { setReasignando(null); cargar(); }} />}
      {operacionSaldo && <SaldoOperacionModal patientId={patientId} {...operacionSaldo}
        onClose={() => setOperacionSaldo(null)} onSaved={() => { setOperacionSaldo(null); cargar(); }} />}
    </div>
        )}
      </div>
    </div>
  );
}
