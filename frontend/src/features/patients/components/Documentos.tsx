"use client";
/**
 * Tab DOCUMENTOS — archivo de documentos del paciente sobre la BBDD nueva.
 *
 * Diseño (petición del usuario):
 *   · Pestañas de TIPO (Facturas, Recibo, Primera visita, Recetas, Consentimientos,
 *     Informes, Otros, Todos) = filtro del HISTÓRICO listado debajo.
 *   · A la derecha: botón GENERAR y botón SUBIR DOCUMENTO. Al pulsar cualquiera se
 *     pregunta QUÉ TIPO de documento es, y se archiva en su categoría (tabla
 *     `documentos_paciente`, fichero en media/documentos_paciente).
 *
 * Recetas (tabla `recetas`) y Consentimientos (flujo COEM) mantienen su panel propio.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { Loader2, X, FileText, Upload, FilePlus2, Pill, Trash2, Eye, Receipt, ShieldCheck } from "lucide-react";
import { ClinicalCard, SectionHeader, Modal, ModalBody, ModalButton, MODAL_INPUT } from "@/shared/components";
import { API_BASE } from "@/shared/lib/api";
import { patientService } from "../services/patientService";
import { generarDocumentoPdf } from "../lib/documentoDoc";
import { ConsentimientosPanel } from "./ConsentimientosPanel";
import type { RecetaEmitida, DocArchivado } from "../types/patient";

type Categoria = "Facturas" | "Recibo" | "Primera visita" | "Recetas" | "Consentimientos" | "Informes" | "Otros" | "Todos";
const CATEGORIAS: Categoria[] = ["Facturas", "Recibo", "Primera visita", "Recetas", "Consentimientos", "Informes", "Otros", "Todos"];

// Categorías donde se archiva un fichero libre al SUBIR (Recetas/Consentimientos tienen flujo propio).
const TIPOS_SUBIR: string[] = ["Facturas", "Recibo", "Primera visita", "Informes", "Otros"];
// Plantillas que se pueden GENERAR → (id del generador, categoría donde se archiva).
const GENERABLES: Array<{ id: string; label: string; cat: string }> = [
  { id: "factura", label: "Factura", cat: "Facturas" },
  { id: "recibo", label: "Recibo", cat: "Recibo" },
  { id: "primeraVisita", label: "Primera visita", cat: "Primera visita" },
  { id: "justificante", label: "Justificante", cat: "Otros" },
  { id: "presupuesto", label: "Presupuesto", cat: "Otros" },
  { id: "historia", label: "Historia clínica", cat: "Informes" },
];

function base64ToFile(b64: string, filename: string): File {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new File([bytes], filename, { type: "application/pdf" });
}

const fmtDate = (iso: string | null) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
};

export function Documentos({ patientId, categoriaInicial, onFacturaActualizada }: { patientId: number; categoriaInicial?: string; onFacturaActualizada?: () => void }) {
  const [cat, setCat] = useState<Categoria>((CATEGORIAS as string[]).includes(categoriaInicial ?? "") ? (categoriaInicial as Categoria) : "Facturas");
  const [recetas, setRecetas] = useState<RecetaEmitida[]>([]);
  const [docs, setDocs] = useState<DocArchivado[]>([]);
  const [facturas, setFacturas] = useState<Array<{ factura_id: number | null; numero: string; fecha?: string | null; estado: string; verifactu: boolean; rectificativa_url?: string | null; rectificativa_descripcion?: string | null }>>([]);
  const [rectificar, setRectificar] = useState<{ id: number; numero: string } | null>(null);
  const [motivoRectificacion, setMotivoRectificacion] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);          // acción en curso (texto del spinner)
  const [picker, setPicker] = useState<null | "generar" | "subir">(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const rectifFileRef = useRef<HTMLInputElement>(null);
  const tipoSubir = useRef<string>("Otros");                       // categoría elegida para la subida pendiente

  const loadRecetas = useCallback(async () => {
    try { const r = await patientService.recetas(patientId); setRecetas(Array.isArray(r.recetas) ? r.recetas : []); }
    catch { setRecetas([]); }
  }, [patientId]);

  const loadDocs = useCallback(async (tipo: Categoria) => {
    if (tipo === "Recetas" || tipo === "Consentimientos") { setDocs([]); return; }
    setLoading(true);
    try { setDocs(await patientService.docListar(patientId, tipo)); }
    catch { setDocs([]); }
    finally { setLoading(false); }
  }, [patientId]);

  useEffect(() => { loadRecetas(); }, [loadRecetas]);
  useEffect(() => { loadDocs(cat); }, [cat, loadDocs]);
  useEffect(() => {
    patientService.facturasVinculadas(patientId).then(setFacturas).catch(() => setFacturas([]));
  }, [patientId]);

  // ── SUBIR: elegir tipo → abrir selector de fichero → subir ──
  function elegirSubir(tipo: string) {
    tipoSubir.current = tipo;
    setPicker(null);
    fileRef.current?.click();
  }
  async function onFileElegido(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setBusy("Subiendo documento…");
    try {
      await patientService.docSubir(patientId, f, tipoSubir.current, f.name);
      setCat(tipoSubir.current as Categoria);
      await loadDocs(tipoSubir.current as Categoria);
    } catch (err) {
      alert(err instanceof Error ? err.message : "No se pudo subir el documento");
    } finally { setBusy(null); }
  }

  // ── GENERAR: elegir plantilla → renderizar PDF → archivar ──
  async function elegirGenerar(g: { id: string; label: string; cat: string }) {
    setPicker(null);
    setBusy(`Generando ${g.label}…`);
    try {
      const b64 = await generarDocumentoPdf(patientId, g.id);
      const file = base64ToFile(b64, `${g.label}.pdf`);
      await patientService.docSubir(patientId, file, g.cat, g.label);
      setCat(g.cat as Categoria);
      await loadDocs(g.cat as Categoria);
    } catch (err) {
      alert(err instanceof Error ? err.message : "No se pudo generar el documento");
    } finally { setBusy(null); }
  }

  async function guardarRectificativa(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !rectificar) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      alert("Selecciona el PDF de la factura rectificativa emitida."); return;
    }
    setBusy("Archivando rectificativa…");
    try {
      await patientService.rectificarFactura(patientId, rectificar.id, motivoRectificacion, file);
      setRectificar(null); setMotivoRectificacion("");
      setFacturas(await patientService.facturasVinculadas(patientId));
      setCat("Facturas"); await loadDocs("Facturas"); onFacturaActualizada?.();
    } catch (err) { alert(err instanceof Error ? err.message : "No se pudo registrar la rectificativa"); }
    finally { setBusy(null); }
  }

  async function borrar(docId: number) {
    if (!confirm("¿Borrar este documento archivado?")) return;
    try { await patientService.docBorrar(patientId, docId); await loadDocs(cat); }
    catch (err) { alert(err instanceof Error ? err.message : "No se pudo borrar"); }
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 bg-white">
      <input ref={fileRef} type="file" hidden onChange={onFileElegido}
        accept=".pdf,.jpg,.jpeg,.png,.webp,.gif,.doc,.docx,.odt,.xls,.xlsx" />
      <input ref={rectifFileRef} type="file" hidden onChange={guardarRectificativa} accept="application/pdf,.pdf" />

      <ClinicalCard className="mb-4">
        <SectionHeader title="Documentos del paciente" icon={FileText} />

        {busy && (
          <div className="flex items-center gap-2 mb-3 text-[12px] text-[#065AED]">
            <Loader2 className="w-4 h-4 animate-spin" /> {busy}
          </div>
        )}

        {/* Barra: botones de TIPO (izquierda, filtro del histórico) + Generar/Subir (derecha) */}
        <div className="flex items-start gap-3 mb-3 border-b border-[#e5e7eb] pb-3">
          <div className="flex gap-1 flex-wrap flex-1 min-w-0">
            {CATEGORIAS.map((c) => (
              <button key={c} onClick={() => setCat(c)}
                className={`px-3 py-1 text-[12px] rounded-sm cursor-pointer transition-colors ${
                  cat === c ? "bg-[#1500A0] text-white font-semibold" : "bg-[#FFFFFF] text-[#7f8c8d] hover:bg-[#E6EDFF]"
                }`}>
                {c}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button type="button" onClick={() => setPicker("generar")} disabled={busy !== null}
              className="inline-flex items-center gap-1.5 px-3 h-9 rounded-md text-[12px] font-semibold text-white bg-[#1500A0] hover:bg-[#0d0072] disabled:opacity-50">
              <FilePlus2 className="w-4 h-4" /> Generar
            </button>
            <button type="button" onClick={() => setPicker("subir")} disabled={busy !== null}
              className="inline-flex items-center gap-1.5 px-3 h-9 rounded-md text-[12px] font-semibold text-[#1500A0] bg-[#FFFFFF] border border-[#cfe1ff] hover:bg-[#E6EDFF] disabled:opacity-50">
              <Upload className="w-4 h-4" /> Subir documento
            </button>
          </div>
        </div>

        {cat === "Facturas" && facturas.length > 0 && (
          <div className="mb-4 rounded-md border border-[#cfe1ff] bg-[#FFFFFF] p-3">
            <div className="mb-2 flex items-center gap-2 text-[12px] font-bold text-[#1500A0]"><Receipt className="h-4 w-4" /> Facturas vinculadas a tratamientos</div>
            <div className="space-y-2">
              {facturas.map((f) => (
                <div key={`${f.numero}-${f.factura_id ?? "sin-registro"}`} className="flex flex-wrap items-center justify-between gap-2 rounded border border-[#e5e7eb] bg-white px-3 py-2 text-[12px]">
                  <div><b className="text-[#1500A0]">{f.numero}</b><span className="ml-2 text-slate-500">{f.fecha || ""}</span><span className={`ml-2 uppercase text-[10px] ${f.estado === "rectificada" ? "text-[#0F8C7D]" : f.estado === "anulada_sin_rectificativa" ? "text-[#A21CAF]" : "text-slate-500"}`}>{f.estado.replace("_", " ")}</span></div>
                  {f.rectificativa_url ? (
                    <a href={`${API_BASE}${f.rectificativa_url}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[#0F8C7D]"><ShieldCheck className="h-3.5 w-3.5" /> Ver rectificativa</a>
                  ) : f.estado === "emitida" && f.factura_id && !f.verifactu ? (
                    <button type="button" onClick={() => { setRectificar({ id: f.factura_id!, numero: f.numero }); setMotivoRectificacion(""); }} className="rounded border border-[#1500A0] px-2.5 py-1 font-semibold text-[#1500A0] hover:bg-[#E6EDFF]">Registrar rectificativa</button>
                  ) : f.verifactu ? <span className="text-[#6D28D9]">Rectificar en el sistema fiscal antes de archivarla</span> : f.estado === "sin_registro" || f.estado === "referencia_ambigua" ? <span className="text-[#6D28D9]">Referencia histórica ambigua; revisar antes de marcar fracaso</span> : f.estado === "anulada_sin_rectificativa" ? <span className="text-[#A21CAF]">Factura sin PDF rectificativo enlazado; tratamiento aún bloqueado</span> : null}
                </div>
              ))}
            </div>
            <p className="mt-2 text-[10px] text-slate-500">Adjunta el PDF rectificativo ya emitido. Se conserva la factura original y el tratamiento se desbloquea tras registrar la rectificativa.</p>
          </div>
        )}

        {/* ── Contenido según la categoría ── */}
        {cat === "Recetas" ? (
          <RecetasTabla recetas={recetas} />
        ) : cat === "Consentimientos" ? (
          <ConsentimientosPanel patientId={patientId} />
        ) : (
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-bold text-[#065AED] uppercase tracking-wide">
                {cat === "Todos" ? "Todos los documentos archivados" : `Documentos · ${cat}`}
              </span>
              {loading && <Loader2 className="w-3.5 h-3.5 animate-spin text-[#7f8c8d]" />}
            </div>
            {docs.length === 0 && !loading ? (
              <div className="border-2 border-dashed border-[#c8d8e8] rounded-sm py-8 text-center bg-white">
                <Upload className="w-6 h-6 text-[#3388FF] mx-auto mb-1 opacity-50" />
                <div className="text-[12px] text-[#7f8c8d]">No hay documentos archivados en «{cat}».</div>
                <div className="text-[11px] text-[#9aa7b2] mt-0.5">Usa «Generar» o «Subir documento» para añadir.</div>
              </div>
            ) : (
              <div className="border border-[#e5e7eb] rounded-sm bg-white overflow-hidden">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="bg-[#FFFFFF] text-[10px] font-bold text-[#7f8c8d] uppercase">
                      <th className="px-3 py-2 text-left w-24">Fecha</th>
                      <th className="px-3 py-2 text-left w-32">Tipo</th>
                      <th className="px-3 py-2 text-left">Documento</th>
                      <th className="px-3 py-2 text-right w-24">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {docs.map((d) => (
                      <tr key={d.id} className="border-t border-[#f0f2f5] hover:bg-[#E6EDFF]">
                        <td className="px-3 py-2 text-[#1500A0] whitespace-nowrap">{fmtDate(d.fecha)}</td>
                        <td className="px-3 py-2 text-[#7f8c8d]">{d.tipo || "—"}</td>
                        <td className="px-3 py-2 font-semibold text-[#065AED] truncate" title={d.descripcion ?? undefined}>{d.descripcion || "Documento"}</td>
                        <td className="px-3 py-2">
                          <div className="flex items-center justify-end gap-1">
                            {d.archivo_url && (
                              <a href={`${API_BASE}${d.archivo_url}`} target="_blank" rel="noreferrer"
                                title="Ver documento" className="p-1.5 rounded-sm text-[#065AED] hover:bg-[#E6EDFF]">
                                <Eye className="w-4 h-4" />
                              </a>
                            )}
                            {!d.factura_origen_id && <button onClick={() => borrar(d.id)} title="Borrar"
                              className="p-1.5 rounded-sm text-[#C026D3] hover:bg-[#E6EDFF]">
                              <Trash2 className="w-4 h-4" />
                            </button>}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </ClinicalCard>

      {rectificar && (
        <Modal
          title={`Registrar rectificativa · ${rectificar.numero}`}
          onClose={() => setRectificar(null)}
          size="md"
          footer={
            <>
              <ModalButton variant="magenta" icon={X} onClick={() => setRectificar(null)}>Cerrar</ModalButton>
              <ModalButton
                variant="primary"
                icon={Upload}
                disabled={!motivoRectificacion.trim() || busy !== null}
                onClick={() => rectifFileRef.current?.click()}
              >
                Seleccionar PDF rectificativo
              </ModalButton>
            </>
          }
        >
          <ModalBody>
            <div className="flex flex-col gap-3">
              <p className="text-[12px] text-slate-600">Adjunta la rectificativa emitida por el sistema fiscal. Al archivarla se conservará la factura original y se desbloqueará la gestión del tratamiento.</p>
              <label className="flex flex-col gap-1 text-[11px] font-semibold text-[#21A2E5]">Motivo
                <textarea value={motivoRectificacion} onChange={(e) => setMotivoRectificacion(e.target.value)} maxLength={500} rows={3}
                  className={MODAL_INPUT} placeholder="Describe por qué se rectifica la factura" />
              </label>
            </div>
          </ModalBody>
        </Modal>
      )}

      {/* ── Selector de tipo (Generar / Subir) ── */}
      {picker && (
        <Modal
          title={picker === "generar" ? "¿Qué documento generar?" : "¿Qué tipo de documento subes?"}
          onClose={() => setPicker(null)}
          size="sm"
        >
          <ModalBody>
            <div className="flex flex-col gap-1.5">
              {picker === "generar"
                ? GENERABLES.map((g) => (
                    <button key={g.id} onClick={() => elegirGenerar(g)}
                      className="flex items-center justify-between px-3 py-2 rounded-md text-[13px] text-left bg-[#FFFFFF] hover:bg-[#E6EDFF] border border-[#BFE4F7]">
                      <span className="font-medium text-[#1a1a1a]">{g.label}</span>
                      <span className="text-[11px] text-[#7f8c8d]">→ {g.cat}</span>
                    </button>
                  ))
                : TIPOS_SUBIR.map((t) => (
                    <button key={t} onClick={() => elegirSubir(t)}
                      className="px-3 py-2 rounded-md text-[13px] text-left font-medium text-[#1a1a1a] bg-[#FFFFFF] hover:bg-[#E6EDFF] border border-[#BFE4F7]">
                      {t}
                    </button>
                  ))}
            </div>
          </ModalBody>
        </Modal>
      )}
    </div>
  );
}

// ── Recetas emitidas (datos reales, tabla propia) ──
function RecetasTabla({ recetas }: { recetas: RecetaEmitida[] }) {
  return (
    <div>
      <div className="flex items-center gap-1 mb-2">
        <Pill className="w-3.5 h-3.5 text-[#065AED]" />
        <span className="text-[11px] font-bold text-[#065AED] uppercase tracking-wide">Recetas emitidas</span>
      </div>
      {recetas.length === 0 ? (
        <div className="border border-dashed border-[#c8d8e8] rounded-sm py-2 text-center bg-white">
          <span className="text-[12px] text-[#7f8c8d]">No hay recetas emitidas para este paciente</span>
        </div>
      ) : (
        <div className="border border-[#e5e7eb] rounded-sm bg-white overflow-hidden">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="bg-[#FFFFFF] text-[10px] font-bold text-[#7f8c8d] uppercase">
                <th className="px-3 py-2 text-left w-24">Fecha</th>
                <th className="px-3 py-2 text-left">Medicamento</th>
                <th className="px-3 py-2 text-left">Posología</th>
                <th className="px-3 py-2 text-left w-28">Doctor</th>
                <th className="px-3 py-2 text-left w-40">Nº receta</th>
                <th className="px-3 py-2 text-center w-16">Líneas</th>
              </tr>
            </thead>
            <tbody>
              {recetas.map((r) => (
                <tr key={r.id} className="border-t border-[#f0f2f5] hover:bg-[#E6EDFF]">
                  <td className="px-3 py-2 text-[#1500A0] whitespace-nowrap">{fmtDate(r.fecha)}</td>
                  <td className="px-3 py-2 font-semibold text-[#065AED]">{r.medicamento}</td>
                  <td className="px-3 py-2 text-[#7f8c8d] max-w-xs truncate" title={r.posologia ?? undefined}>{r.posologia || "—"}</td>
                  <td className="px-3 py-2 text-[#7f8c8d] truncate">{r.doctor || "—"}</td>
                  <td className="px-3 py-2 font-mono text-[11px] text-[#065AED] truncate" title={r.num_receta ?? undefined}>{r.num_receta || "—"}</td>
                  <td className="px-3 py-2 text-center text-[#7f8c8d]">{r.n_lineas}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
