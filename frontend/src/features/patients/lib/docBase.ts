// Base compartida de los generadores de documentos (presupuesto · justificante · documentos genéricos).
// Antes estaba copiado en cada uno (DocResp + clinicKeys + impresión + PDF en cliente). Fuente única aquí.

export type DocResp = {
  plantilla: { html?: string; campos?: Record<string, string> } | null;
  clinic: {
    nombre: string; fiscal: string; dir: string; tel: string; email: string; web: string | null;
    logo_url: string | null; sello_url: string | null; logo_data: string | null; sello_data: string | null;
  };
  datos: Record<string, string>;
};

// Escapa un valor para incrustarlo en un ATRIBUTO HTML (src, etc.) sin poder romperlo.
const attr = (v: string) => String(v ?? "").replace(/[&<>"']/g, (ch) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch] as string
));

// Claves de cabecera de la clínica para renderDoc. Preferimos data-URL (documento autónomo, sin CORS).
// clinicWeb/clinicLogo/sello son HTML estructural (renderDoc no los re-escapa) → escapamos aquí
// los valores dinámicos (web, src) para que un dato con caracteres HTML no inyecte en el documento.
export function clinicKeys(c: DocResp["clinic"]): Record<string, string> {
  const logo = c.logo_data || (c.logo_url ?? "");
  const sello = c.sello_data || (c.sello_url ?? "");
  return {
    clinicName: c.nombre, clinicFiscal: c.fiscal, clinicDir: c.dir, clinicTel: c.tel, clinicEmail: c.email,
    clinicWeb: c.web ? `<br>${attr(c.web)}` : "",
    clinicLogo: logo ? `<img src="${attr(logo)}" style="height:36px;vertical-align:middle;margin-right:10px">` : "",
    sello: sello ? `<img src="${attr(sello)}" style="height:64px;opacity:.9">` : "",
  };
}

// Abre el HTML en ventana nueva y lanza la impresión del navegador.
export function imprimirHtml(html: string): void {
  const w = window.open("", "_blank", "width=900,height=1040");
  if (!w) throw new Error("El navegador bloqueó la ventana de impresión");
  w.document.write(html);
  w.document.close();
  w.focus();
  setTimeout(() => w.print(), 350);
}

// Renderiza el HTML a PDF en cliente → base64 (sin prefijo data:). Para enviar por WhatsApp o archivar.
export async function htmlToPdfBase64(docHtml: string): Promise<string> {
  const iframe = document.createElement("iframe");
  // sandbox SIN allow-scripts → el HTML del documento NO ejecuta <script> (defensa en
  // profundidad frente al stored-XSS); allow-same-origin permite que html2canvas lea el DOM.
  iframe.setAttribute("sandbox", "allow-same-origin");
  iframe.style.cssText = "position:fixed;left:-10000px;top:0;width:820px;height:1200px;border:0";
  document.body.appendChild(iframe);
  try {
    const idoc = iframe.contentDocument!;
    idoc.open(); idoc.write(docHtml); idoc.close();
    await new Promise<void>((res) => {                         // esperar imágenes
      const imgs = Array.from(idoc.images);
      let pend = imgs.filter((i) => !i.complete).length;
      if (!pend) return res();
      const done = () => { if (--pend <= 0) res(); };
      imgs.forEach((i) => { if (!i.complete) { i.addEventListener("load", done, { once: true }); i.addEventListener("error", done, { once: true }); } });
      setTimeout(res, 3500);
    });
    const el = idoc.querySelector(".page") ?? idoc.body;
    const html2pdf = (await import("html2pdf.js")).default as unknown as (...a: unknown[]) => {
      set: (o: unknown) => { from: (e: unknown) => { outputPdf: (t: string) => Promise<ArrayBuffer> } };
    };
    const ab = await html2pdf().set({
      margin: 0, image: { type: "jpeg", quality: 0.95 },
      html2canvas: { scale: 2, useCORS: true, backgroundColor: "#ffffff" },
      jsPDF: { unit: "px", format: [794, 1123], orientation: "portrait" },
    }).from(el).outputPdf("arraybuffer");
    const bytes = new Uint8Array(ab);
    let bin = "";
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin);
  } finally {
    document.body.removeChild(iframe);
  }
}
