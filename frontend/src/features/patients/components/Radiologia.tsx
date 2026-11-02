"use client";
/**
 * RADIOLOGÍA — importación, clasificación por IA y hallazgos de imágenes radiológicas.
 *
 * Diseño:
 *   · Zona drag-drop + botón para importar (jpg/png/webp/dcm). La IA propone la MODALIDAD.
 *   · Rejilla de imágenes: miniatura, badge de modalidad (corregible con el selector), botón de
 *     reclasificar con IA, borrar, y hallazgos (pieza + descripción) por imagen.
 *
 * Sobre el backend /radiologia (modelos imagenes_rx + hallazgos_imagen). Multi-tenant por paciente.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { Loader2, X, Radiation, Upload, Trash2, Sparkles, Plus, ScanSearch, Crosshair, TrendingUp, Layers, PenLine, Layers2, Presentation } from "lucide-react";
import { SectionHeader, Modal, ModalBody } from "@/shared/components";
import { api, API_BASE } from "@/shared/lib/api";
import { Cefalometria } from "./Cefalometria";
import { ComparativaCefalo } from "./ComparativaCefalo";
import { VisorDicom } from "./VisorDicom";
import { AnotadorRx } from "./AnotadorRx";
import { SuperposicionRx } from "./SuperposicionRx";
import { Dicom3DViewer } from "./Dicom3DViewer";

type Hallazgo = { id: number; descripcion: string; pieza: string | null; confianza: number | null };
type ImagenRx = {
  id: number; paciente_id: number; cita_id: number | null;
  modalidad: string; modalidad_label: string;
  archivo_url: string; orthanc_study_id: string | null; hallazgos: Hallazgo[];
};

const ACEPTA = "image/jpeg,image/png,image/webp,application/dicom,.dcm";

export function Radiologia({ patientId }: { patientId: number }) {
  const [imgs, setImgs] = useState<ImagenRx[]>([]);
  const [modalidades, setModalidades] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<number | "import" | null>(null);
  const [dragActivo, setDragActivo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cefaOpen, setCefaOpen] = useState<number | null>(null);   // imagenId con el trazador abierto
  const [evolucion, setEvolucion] = useState(false);               // comparativa longitudinal
  const [dicom, setDicom] = useState(false);                       // visor DICOM del PACS
  // IA 2D integration state
  const [ia2dOpen, setIa2dOpen] = useState(false);
  const [ia2dLoading, setIa2dLoading] = useState(false);
  const [ia2dResult, setIa2dResult] = useState<any>(null);
  const API_IA2D_URL = "http://localhost:8000/process-dental-rx";
  const [denctStudyId, setDenctStudyId] = useState<string | undefined>(undefined); // study ID para DenCT
  const [denctOpen, setDenctOpen] = useState(false);
  const [anotar, setAnotar] = useState<number | null>(null);       // imagenId a anotar
  const [superponer, setSuperponer] = useState(false);             // superposición de imágenes
  const [loadingPaciente, setLoadingPaciente] = useState(false);
  const [patient, setPatient] = useState<any>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const cargar = useCallback(async () => {
    setLoading(true);
    try { setImgs(await api.get<ImagenRx[]>(`/pacientes/${patientId}/radiologia`)); }
    catch { setImgs([]); }
    finally { setLoading(false); }
  }, [patientId]);

  useEffect(() => { void cargar(); }, [cargar]);
  useEffect(() => {
    api.get<{ modalidades: Record<string, string> }>("/radiologia/modalidades")
      .then((r) => setModalidades(r.modalidades)).catch(() => setModalidades({}));
  }, []);

  // Cargar datos del paciente y study ID para DenCT
  useEffect(() => {
    void cargarPaciente();
  }, [patientId]);

  async function cargarPaciente() {
    setLoadingPaciente(true);
    try {
      const paciente = await api.get(`/pacientes/${patientId}`);
      setPatient(paciente);
      // Intentar obtener study ID para DenCT desde Orthanc
      try {
        const series = await api.get<{ series: any[] }>(`/pacientes/${patientId}/dicom/series`);
        const cbctSeries = series.series?.find((s: any) =>  // Array.prototype.find - standard JS method, not a custom function
          s.modalidad?.toLowerCase().includes('cbct') ||
          s.descripcion?.toLowerCase().includes('cbct')
        );
        if (cbctSeries && cbctSeries.series_id) {
          setDenctStudyId(cbctSeries.series_id);
        }
      } catch (e) {
        console.log("No se pudieron obtener series DenCT, usando sample:", e);
      }
    } catch (e) {
      console.error("Error cargando paciente:", e);
    } finally {
      setLoadingPaciente(false);
    }
  }

  const importar = useCallback(async (files: FileList | File[]) => {
    const lista = Array.from(files);
    if (lista.length === 0) return;
    setBusy("import"); setError(null);
    try {
      for (const f of lista) {
        await api.upload<ImagenRx>(`/pacientes/${patientId}/radiologia?clasificar=true`, f);
      }
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message.slice(0, 160) : "No se pudo importar");
    } finally { setBusy(null); }
  }, [patientId, cargar]);

  const reclasificarManual = async (id: number, modalidad: string) => {
    setImgs((prev) => prev.map((i) => (i.id === id ? { ...i, modalidad, modalidad_label: modalidades[modalidad] ?? modalidad } : i)));
    try { await api.patch<ImagenRx>(`/radiologia/${id}`, { modalidad }); } catch { void cargar(); }
  };
  const reclasificarIA = async (id: number) => {
    setBusy(id);
    try { const r = await api.post<ImagenRx>(`/radiologia/${id}/clasificar`, {}); setImgs((p) => p.map((i) => (i.id === id ? r : i))); }
    catch { /* best-effort */ } finally { setBusy(null); }
  };
  const borrar = async (id: number) => {
    if (!confirm("¿Eliminar esta imagen y sus hallazgos?")) return;
    setBusy(id);
    try { await api.del(`/radiologia/${id}`); setImgs((p) => p.filter((i) => i.id !== id)); }
    catch { void cargar(); } finally { setBusy(null); }
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <SectionHeader className="h-[34px]" variant="dark" title="Radiología" icon={Radiation}
        action={
          <div className="flex items-center gap-3">
            <button type="button" onClick={() => window.open(`${API_BASE}/pacientes/${patientId}/radiologia/informe.pptx`, "_blank")}
              title="Descargar presentación del caso (PPTX)"
              className="flex items-center gap-1 text-[11px] text-white/90 hover:text-white cursor-pointer">
              <Presentation className="w-3.5 h-3.5" /> PPTX
            </button>
            <button type="button" onClick={() => setSuperponer(true)} title="Superponer dos radiografías"
              className="flex items-center gap-1 text-[11px] text-white/90 hover:text-white cursor-pointer">
              <Layers2 className="w-3.5 h-3.5" /> Superponer
            </button>
            <button type="button" onClick={() => setDicom(true)} title="Visor DICOM (estudios del PACS: CBCT, TAC…)"
              className="flex items-center gap-1 text-[11px] text-white/90 hover:text-white cursor-pointer">
              <Layers className="w-3.5 h-3.5" /> DICOM
            </button>
            <button type="button" onClick={() => setIa2dOpen(true)} title="IA 2D (Detección/Segmentación)"
              className="flex items-center gap-1 text-[11px] text-white/90 hover:text-white cursor-pointer">
              <Layers className="w-3.5 h-3.5" /> IA 2D
            </button>
            <button type="button" onClick={() => setEvolucion(true)} title="Evolución cefalométrica (comparar trazados por fecha)"
              className="flex items-center gap-1 text-[11px] text-white/90 hover:text-white cursor-pointer">
              <TrendingUp className="w-3.5 h-3.5" /> Evolución
            </button>
          </div>
        } />

      {/* Zona de importación (drag-drop + botón) */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragActivo(true); }}
        onDragLeave={() => setDragActivo(false)}
        onDrop={(e) => { e.preventDefault(); setDragActivo(false); if (e.dataTransfer.files.length) void importar(e.dataTransfer.files); }}
        className={`m-2 rounded-sm border-2 border-dashed transition-colors ${dragActivo ? "border-[#1ca0d1] bg-[#1ca0d1]/5" : "border-slate-300 bg-white"}`}
      >
        <button
          type="button" onClick={() => fileRef.current?.click()} disabled={busy === "import"}
          className="w-full flex items-center justify-center gap-2 py-3 text-sm text-slate-600 hover:text-[#013b82] cursor-pointer disabled:opacity-60"
        >
          {busy === "import" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
          {busy === "import" ? "Importando…" : "Arrastra una radiografía aquí o pulsa para importar (JPG · PNG · DICOM)"}
        </button>
        <input ref={fileRef} type="file" accept={ACEPTA} multiple hidden
          onChange={(e) => { if (e.target.files?.length) { setIa2dOpen(true); } e.target.value = ""; }} />
      </div>

      {error && <div className="mx-2 mb-2 rounded-sm bg-[#FFFFFF] text-[#C026D3] text-xs px-3 py-2">{error}</div>}

      {/* Rejilla */}
      <div className="flex-1 min-h-0 overflow-y-auto px-2 pb-2">
        {loading ? (
          <div className="h-32 grid place-items-center text-slate-400"><Loader2 className="w-5 h-5 animate-spin" /></div>
        ) : imgs.length === 0 ? (
          <div className="h-32 grid place-items-center text-slate-400 text-sm">
            <div className="flex flex-col items-center gap-1"><ScanSearch className="w-6 h-6" />Sin radiografías. Importa la primera.</div>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
            {imgs.map((img) => (
              <TarjetaRx
                key={img.id} img={img} modalidades={modalidades} busy={busy === img.id}
                onModalidad={(m) => reclasificarManual(img.id, m)}
                onIA={() => reclasificarIA(img.id)} onBorrar={() => borrar(img.id)}
                onCefalo={() => setCefaOpen(img.id)} onAnotar={() => setAnotar(img.id)} onRefrescar={cargar}
              />
            ))}
          </div>
        )}
      </div>

      {/* Trazador cefalométrico (emergente sobre la ficha) */}
      {cefaOpen != null && (
        <Modal title="Cefalometría" size="full" onClose={() => setCefaOpen(null)} closeOnBackdrop={false} zIndex={60}
          className="h-[90vh] !max-w-[1180px]">
          <ModalBody className="!p-0 !overflow-hidden">
            <Cefalometria imagenId={cefaOpen} onCerrar={() => setCefaOpen(null)} />
          </ModalBody>
        </Modal>
      )}

      {/* Comparativa longitudinal */}
      {evolucion && (
        <Modal title="Evolución cefalométrica" size="lg" onClose={() => setEvolucion(false)} closeOnBackdrop={false} zIndex={60}
          className="h-[80vh] !max-w-[760px]">
          <ModalBody className="!p-0 !overflow-hidden">
            <ComparativaCefalo patientId={patientId} onCerrar={() => setEvolucion(false)} />
          </ModalBody>
        </Modal>
      )}

      {/* Visor DICOM del PACS */}
      {dicom && (
        <Modal title="Visor DICOM · PACS" size="full" onClose={() => setDicom(false)} closeOnBackdrop={false} zIndex={60}
          className="h-[90vh] !max-w-[1100px]">
          <ModalBody className="!p-0 !overflow-hidden">
            <VisorDicom patientId={patientId} onCerrar={() => setDicom(false)} />
          </ModalBody>
        </Modal>
      )}

      {/* IA 2D modal */}
      {ia2dOpen && (
        <Modal title="IA 2D – Detección y Segmentación" size="lg" onClose={() => setIa2dOpen(false)} closeOnBackdrop={false} zIndex={60}
          className="h-[80vh] !max-w-[1000px]">
          <ModalBody className="!p-4 !overflow-auto">
            {ia2dLoading ? (
              <div className="flex items-center justify-center h-full"><Loader2 className="w-6 h-6 animate-spin" /></div>
            ) : ia2dResult ? (
              <div className="flex flex-col gap-4">
                <div className="flex-1">
                  <h4 className="text-sm font-semibold mb-2">Imagen de análisis (detección + segmentación)</h4>
                  <img src={`data:image/png;base64,${ia2dResult.img_analisis}`} alt="Análisis IA" className="max-w-full border rounded" />
                </div>
                <div className="flex-1">
                  <h4 className="text-sm font-semibold mb-2">Resultado post‑tratamiento</h4>
                  <img src={`data:image/png;base64,${ia2dResult.img_post_tratamiento}`} alt="Post‑tratamiento IA" className="max-w-full border rounded" />
                </div>
                <pre className="bg-white p-2 rounded text-xs overflow-auto">{JSON.stringify(ia2dResult.piezas_y_caries_detectadas, null, 2)}</pre>
              </div>
            ) : (
              <div className="text-center text-sm text-gray-500">Presione “Procesar” para iniciar el análisis IA.</div>
            )}
            <div className="mt-4 flex gap-2">
              <button type="button" onClick={async () => {
                setIa2dLoading(true);
                const formData = new FormData();
                if (fileRef.current?.files?.[0]) {
                  formData.append("file", fileRef.current.files[0]);
                } else {
                  alert("Seleccione una imagen antes de procesar.");
                  setIa2dLoading(false);
                  return;
                }
                formData.append("presupuesto", JSON.stringify({}));
                const resp = await fetch(API_IA2D_URL, { method: "POST", body: formData });
                const data = await resp.json();
                setIa2dResult(data);
                setIa2dLoading(false);
              }} className="px-4 py-2 bg-[#013b82]/5 hover:bg-[#013b82]/10 text-[#013b82] rounded">
                Procesar IA
              </button>
              <button type="button" onClick={() => setIa2dOpen(false)} className="px-4 py-2 bg-gray-200 hover:bg-gray-300 rounded">Cerrar</button>
            </div>
          </ModalBody>
        </Modal>
      )}

      {denctOpen && (
        <Modal title="Visor CBCT 3D · DenCT" size="full" onClose={() => setDenctOpen(false)} closeOnBackdrop={false} zIndex={60}
          className="h-[95vh] !max-w-[1200px]">
          <ModalBody className="!p-0 !overflow-hidden">
            <Dicom3DViewer
              orthancStudyId={denctStudyId}
              numHistoria={patient.num_historia || undefined}
              pacienteId={patient.id}
              onPlanChange={(plan) => console.log("Plan changed:", plan)}
              onImplantsChange={(implants) => console.log("Implants changed:", implants.length)}
            />
          </ModalBody>
        </Modal>
      )}

      {/* Anotador de radiografía */}
      {anotar != null && (
        <Modal title="Anotar radiografía" size="full" onClose={() => setAnotar(null)} closeOnBackdrop={false} zIndex={60}
          className="h-[92vh] !max-w-[1100px]">
          <ModalBody className="!p-0 !overflow-hidden">
            <AnotadorRx imagenId={anotar} onCerrar={() => setAnotar(null)} />
          </ModalBody>
        </Modal>
      )}

      {/* Superposición de imágenes */}
      {superponer && (
        <Modal title="Superposición de imágenes" size="xl" onClose={() => setSuperponer(false)} closeOnBackdrop={false} zIndex={60}
          className="h-[90vh] !max-w-[1000px]">
          <ModalBody className="!p-0 !overflow-hidden">
            <SuperposicionRx patientId={patientId} onCerrar={() => setSuperponer(false)} />
          </ModalBody>
        </Modal>
      )}
    </div>
  );
}

const esDicom = (url: string) => url.toLowerCase().endsWith(".dcm");

function TarjetaRx({ img, modalidades, busy, onModalidad, onIA, onBorrar, onCefalo, onAnotar, onRefrescar }: {
  img: ImagenRx; modalidades: Record<string, string>; busy: boolean;
  onModalidad: (m: string) => void; onIA: () => void; onBorrar: () => void; onCefalo: () => void; onAnotar: () => void; onRefrescar: () => void;
}) {
  const [nuevoHallazgo, setNuevoHallazgo] = useState(false);
  const [desc, setDesc] = useState("");
  const [pieza, setPieza] = useState("");
  const [guardando, setGuardando] = useState(false);
  const sinClasificar = img.modalidad === "sin_clasificar";

  const addHallazgo = async () => {
    if (!desc.trim()) return;
    setGuardando(true);
    try { await api.post<Hallazgo>(`/radiologia/${img.id}/hallazgos`, { descripcion: desc.trim(), pieza: pieza.trim() || null }); setDesc(""); setPieza(""); setNuevoHallazgo(false); onRefrescar(); }
    finally { setGuardando(false); }
  };
  const delHallazgo = async (hid: number) => { try { await api.del(`/radiologia/hallazgos/${hid}`); onRefrescar(); } catch { /* noop */ } };

  return (
    <div className="rounded-sm border border-slate-200 bg-white overflow-hidden flex flex-col">
      <div className="relative aspect-video bg-slate-900 grid place-items-center">
        {esDicom(img.archivo_url) ? (
          <div className="text-slate-300 text-xs flex flex-col items-center gap-1"><ScanSearch className="w-6 h-6" />DICOM</div>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={`${API_BASE}/radiologia/${img.id}/archivo`} alt={img.modalidad_label}
            className="w-full h-full object-contain" loading="lazy" />
        )}
        <span className={`absolute top-1 left-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-sm ${sinClasificar ? "bg-[#7C3AED] text-white" : "bg-[#013b82] text-white"}`}>
          {img.modalidad_label}
        </span>
        <div className="absolute top-1 right-1 flex gap-1">
          {!esDicom(img.archivo_url) && (
            <button type="button" onClick={onAnotar} title="Anotar"
              className="bg-black/45 hover:bg-[#013b82] text-white rounded-sm p-1 cursor-pointer">
              <PenLine className="w-3.5 h-3.5" />
            </button>
          )}
          <button type="button" onClick={onBorrar} disabled={busy} title="Eliminar"
            className="bg-black/45 hover:bg-[#C026D3] text-white rounded-sm p-1 cursor-pointer">
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      <div className="p-2 flex flex-col gap-2">
        {/* Corrección de modalidad */}
        <div className="flex items-center gap-1.5">
          <select value={img.modalidad} onChange={(e) => onModalidad(e.target.value)}
            className="flex-1 text-xs border border-slate-300 rounded-sm px-1.5 py-1 bg-white cursor-pointer">
            {Object.entries(modalidades).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          {!esDicom(img.archivo_url) && (
            <button type="button" onClick={onIA} disabled={busy} title="Reclasificar con IA"
              className="text-[#1ca0d1] hover:text-[#013b82] p-1 cursor-pointer disabled:opacity-50">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
            </button>
          )}
        </div>

        {/* Cefalometría: solo en telerradiografía lateral */}
        {img.modalidad === "lateral_cefalica" && !esDicom(img.archivo_url) && (
          <button type="button" onClick={onCefalo}
            className="w-full text-[11px] bg-[#013b82]/5 hover:bg-[#013b82]/10 text-[#013b82] rounded-sm px-2 py-1.5 flex items-center justify-center gap-1 cursor-pointer">
            <Crosshair className="w-3.5 h-3.5" /> Cefalometría (Steiner)
          </button>
        )}

        {/* Hallazgos */}
        <div className="flex flex-col gap-1">
          {img.hallazgos.map((h) => (
            <div key={h.id} className="flex items-center gap-1.5 text-xs bg-white rounded-sm px-1.5 py-1">
              {h.pieza && <span className="font-semibold text-[#013b82] shrink-0">{h.pieza}</span>}
              <span className="flex-1 text-slate-600 truncate" title={h.descripcion}>{h.descripcion}</span>
              {h.confianza != null && <span className="text-[10px] text-slate-400 shrink-0">{Math.round(h.confianza * 100)}%</span>}
              <button type="button" onClick={() => delHallazgo(h.id)} title="Borrar hallazgo" className="text-slate-400 hover:text-[#C026D3] cursor-pointer"><X className="w-3 h-3" /></button>
            </div>
          ))}
          {nuevoHallazgo ? (
            <div className="flex items-center gap-1.5">
              <input value={pieza} onChange={(e) => setPieza(e.target.value)} placeholder="Pieza" maxLength={10}
                className="w-14 text-xs border border-slate-300 rounded-sm px-1.5 py-1" />
              <input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Hallazgo…" maxLength={200}
                onKeyDown={(e) => { if (e.key === "Enter") void addHallazgo(); }}
                className="flex-1 text-xs border border-slate-300 rounded-sm px-1.5 py-1" autoFocus />
              <button type="button" onClick={addHallazgo} disabled={guardando || !desc.trim()}
                className="text-[#2DD9C3] hover:text-[#013b82] cursor-pointer disabled:opacity-40">
                {guardando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              </button>
              <button type="button" onClick={() => { setNuevoHallazgo(false); setDesc(""); setPieza(""); }} className="text-slate-400 hover:text-slate-600 cursor-pointer"><X className="w-4 h-4" /></button>
            </div>
          ) : (
            <button type="button" onClick={() => setNuevoHallazgo(true)}
              className="self-start text-[11px] text-slate-500 hover:text-[#013b82] flex items-center gap-1 cursor-pointer">
              <Plus className="w-3 h-3" /> Añadir hallazgo
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
  // IA 2D Integration
  // denctOpen: controla el visor CBCT 3D · DenCT
  // Cuando denctOpen es true, muestra el Modal con el visor 3D
  // Fallback: si falla el cargue, oculta el modal y muestra error
