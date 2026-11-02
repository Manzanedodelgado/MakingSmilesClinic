// ─── Plantillas de Documentos (Config → Admin → Documentos) ──────────────────
// Cada documento es HTML editable con {{placeholders}}. La pestaña "Campos" edita
// un subconjunto (textos); "HTML avanzado" edita toda la plantilla. La cabecera de
// la clínica ({{clinic*}}) se rellena desde clinicaConfig. Preview = replace + iframe.

export interface CampoDef { key: string; label: string; multiline?: boolean }
export interface DocDef { id: string; label: string; html: string; campos: CampoDef[]; sample?: Record<string, string> }

// Shell CSS compartido (identidad Factura.xlsx: Roboto, navy #283592, magenta #E01B84)
export const DOC_CSS = `
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
:root{--brand:#6D64E8;--navy:#283592;--navy2:#2A3990;--pink:#E01B84;--ink:#434343;--gray:#666;--gray2:#999;--line:#e7e9f0;--ok:#20BEAB}
*{box-sizing:border-box;margin:0;padding:0;font-family:'Roboto',Arial,sans-serif}
html,body{background:#FFFFFF}
.page{width:794px;min-height:1123px;background:#fff;margin:0 auto;padding:54px 60px;color:var(--ink)}
.top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px}
.brand{font-size:22px;color:var(--brand);font-weight:500}
.cinfo{font-size:11px;color:var(--gray);line-height:1.7;text-align:right}.cinfo b{color:#555;font-weight:500}
.h{display:flex;justify-content:space-between;align-items:flex-end;margin:6px 0 18px}
.title{font-size:32px;font-weight:700;color:var(--navy);letter-spacing:.5px}
.date{font-size:13px;font-weight:700;color:var(--pink)}
.meta{display:flex;gap:48px;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:12px 0;margin-bottom:18px}
.meta .l{font-size:11px;font-weight:700;color:var(--ink);text-transform:uppercase;letter-spacing:.04em}.meta .v{font-size:13px;color:var(--gray);margin-top:2px}
.bill{display:flex;justify-content:space-between;margin-bottom:22px}
.bill .l{font-size:12px;font-weight:700;color:var(--ink);margin-bottom:4px}.bill .n{font-size:14px;color:#333;font-weight:500}.bill .s{font-size:12px;color:var(--gray);line-height:1.6}
table{width:100%;border-collapse:collapse;margin-bottom:14px}
thead th{font-size:11px;font-weight:700;color:var(--navy2);text-transform:uppercase;letter-spacing:.04em;text-align:left;padding:9px 10px;border-bottom:2px solid var(--navy2)}
thead th.r{text-align:right}thead th.c{text-align:center}
tbody td{font-size:12.5px;color:#333;padding:9px 10px;border-bottom:1px solid var(--line)}tbody td.r{text-align:right;color:var(--gray)}tbody td.c{text-align:center}tbody td.d{color:#222}
.est{font-size:9.5px;font-weight:700;padding:2px 7px;border-radius:10px;white-space:nowrap}
.odo-wrap{border:1px solid var(--line);border-radius:6px;padding:10px 12px;margin-bottom:16px;background:#FFFFFF}
.odo-h{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--navy2);margin-bottom:6px}
.odo-cap{position:relative;width:100%}
.odo-cap>div{position:relative!important;display:block!important;width:100%!important}
.odo-cap img{width:100%!important;height:auto!important;display:block}
.odo-cap svg{position:absolute;inset:0;width:100%;height:100%}
.odo-cap div[style*="left"]{position:absolute}
.tot{display:flex;justify-content:space-between;align-items:flex-start;margin-top:6px}
.notes{font-size:11px;color:var(--gray2);max-width:320px;line-height:1.6}.notes b{color:var(--gray);display:block;margin-bottom:3px}
.sums{width:300px}.sumr{display:flex;justify-content:space-between;font-size:12.5px;padding:5px 0}.sumr .k{color:var(--navy2);font-weight:500}.sumr .x{color:#333;font-weight:700}
.total{display:flex;justify-content:space-between;align-items:center;margin-top:8px;padding-top:12px;border-top:2px solid var(--line)}
.total .k{font-size:13px;font-weight:700;color:var(--ink);text-transform:uppercase;letter-spacing:.05em}.total .x{font-size:24px;font-weight:700;color:var(--pink)}
.foot{margin-top:40px;border-top:1px solid var(--line);padding-top:12px;font-size:10px;color:var(--gray2);text-align:center;line-height:1.7}
.lead{font-size:13.5px;color:#333;line-height:1.9;margin:8px 0}.lead b{color:var(--navy);font-weight:700}
.amount-box{margin:20px 0;padding:16px 20px;border:1px solid var(--line);border-radius:6px;background:#FFFFFF;display:flex;justify-content:space-between;align-items:center}
.amount-box .k{font-size:12px;font-weight:700;text-transform:uppercase;color:var(--ink)}.amount-box .x{font-size:26px;font-weight:700;color:var(--pink)}
.sign{display:flex;justify-content:space-between;margin-top:60px}.sigbox{width:230px;text-align:center}.sigline{border-top:1px solid #bbb;margin-bottom:6px;height:44px}.sigbox .t{font-size:11px;color:var(--gray)}
.rec{border:1px solid var(--line);border-radius:6px;padding:12px 14px;margin-bottom:10px}.rec .rh{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}.rec .rd{font-size:12px;font-weight:700;color:var(--navy)}.rec .rt{font-size:11px;color:var(--gray)}
.soap{display:grid;grid-template-columns:18px 1fr;gap:6px 8px;font-size:12px;color:#333;margin-top:4px}.soap b{width:18px;height:18px;border-radius:50%;color:#fff;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700}
`;

const TOP = `<div class="top"><div class="brand">{{clinicLogo}}{{clinicName}}</div><div class="cinfo"><b>{{clinicFiscal}}</b><br>{{clinicDir}}<br>{{clinicTel}}<br>{{clinicEmail}}{{clinicWeb}}</div></div>`;
const FOOT = `<div class="foot">{{pie}}</div>`;
const wrap = (body: string) => `<div class="page">${TOP}\n${body}\n${FOOT}</div>`;

// ── Helpers para documentos largos (consentimiento / anamnesis) ──
const sec = (n: string, body: string) =>
  `<div style="margin:15px 0 5px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--navy2);border-bottom:1px solid var(--line);padding-bottom:4px">${n}</div>${body}`;
const checks = (items: string[], cols = 3) =>
  `<div style="display:grid;grid-template-columns:repeat(${cols},1fr);gap:7px 18px;font-size:12px;color:#333;margin:7px 0 6px">${items
    .map((c) => `<span><span style="display:inline-block;width:11px;height:11px;border:1px solid #999;margin-right:7px;vertical-align:-1px"></span>${c}</span>`)
    .join('')}</div>`;
const fill = (label = '', h = 22) =>
  `${label ? `<div style="font-size:11px;color:var(--gray);margin:8px 0 2px">${label}</div>` : ''}<div style="border-bottom:1px solid var(--line);height:${h}px"></div>`;

// ── Code 128 → SVG (espejo de backend/documents/barcode.ts, para la vista previa) ──
const _BC = [
  '212222','222122','222221','121223','121322','131222','122213','122312','132212','221213',
  '221312','231212','112232','122132','122231','113222','123122','123221','223211','221132',
  '221231','213212','223112','312131','311222','321122','321221','312212','322112','322211',
  '212123','212321','232121','111323','131123','131321','112313','132113','132311','211313',
  '231113','231311','112133','112331','132131','113123','113321','133121','313121','211331',
  '231131','213113','213311','213131','311123','311321','331121','312113','312311','332111',
  '314111','221411','431111','111224','111422','121124','121421','141122','141221','112214',
  '112412','122114','122411','142112','142211','241211','221114','413111','241112','134111',
  '111242','121142','121241','114212','124112','124211','411212','421112','421211','212141',
  '214121','412121','111143','111341','131141','114113','114311','411113','411311','113141',
  '114131','311141','411131','211412','211214','211232','2331112',
];
export function code128Svg(data: string, moduleW = 1.5, height = 46): string {
  const clean = String(data ?? '').replace(/\s+/g, '');
  if (!clean) return '';
  const allDigits = /^\d+$/.test(clean);
  const useC = allDigits && clean.length % 2 === 0;
  const codes: number[] = [];
  if (useC) { codes.push(105); for (let i = 0; i < clean.length; i += 2) codes.push(parseInt(clean.substr(i, 2), 10)); }
  else { codes.push(104); for (let i = 0; i < clean.length; i++) { const v = clean.charCodeAt(i) - 32; codes.push(v >= 0 && v <= 94 ? v : 0); } }
  let sum = codes[0];
  for (let k = 1; k < codes.length; k++) sum += codes[k] * k;
  codes.push(sum % 103); codes.push(106);
  const widths = codes.map((c) => _BC[c]).join('');
  let x = 0, rects = '';
  for (let i = 0; i < widths.length; i++) { const w = parseInt(widths[i], 10) * moduleW; if (i % 2 === 0) rects += `<rect x="${x.toFixed(2)}" y="0" width="${w.toFixed(2)}" height="${height}"/>`; x += w; }
  const totalW = Math.ceil(x);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${totalW}" height="${height}" viewBox="0 0 ${totalW} ${height}" fill="#000" shape-rendering="crispEdges">${rects}</svg>`;
}

// ── Receta médica privada (formato oficial) — dos copias en un A4 ─────────────
const RX_STYLE = `<style>
.rx{width:794px;min-height:1123px;background:#fff;padding:22px 24px;color:#000;font-family:Arial,Helvetica,sans-serif}
.rx *{box-sizing:border-box}
.rx-copy{border:1.4px solid #000}
.rx-cut{border-top:1px dashed #999;margin:8px 0;height:0}
.rx-num{font-size:9px;padding:3px 7px;font-weight:normal}.rx-num b{font-weight:bold}
.rx-title{text-align:center;border-top:1px solid #000;border-bottom:1.4px solid #000;padding:5px 0}
.rx-title b{font-size:13px;letter-spacing:.6px}.rx-title span{font-size:11px;font-weight:bold}
.rx-main{display:flex}
.rx-side{width:22px;border-right:1.4px solid #000;writing-mode:vertical-rl;transform:rotate(180deg);text-align:center;font-size:8px;font-weight:bold;letter-spacing:.5px;display:flex;align-items:center;justify-content:center;padding:6px 0}
.rx-content{flex:1}
.rx-grid{display:grid;grid-template-columns:1.15fr 1fr 1.2fr}
.rx-col{border-right:1px solid #000;border-bottom:1px solid #000;padding:6px 7px;min-height:158px}
.rx-col:last-child{border-right:none}
.rx-k{font-size:6.4px;line-height:1.3;color:#000}
.rx-v{font-size:9px;font-weight:bold;margin-top:5px;line-height:1.35}
.rx-vsm{font-size:8px;font-weight:bold}
.rx-env{font-size:7px;margin-top:9px}
.rx-box-in{display:inline-block;min-width:30px;border:1px solid #000;padding:1px 7px;margin-left:5px;font-weight:bold;text-align:center}
.rx-med{font-size:9.5px;font-weight:bold;margin-top:11px;line-height:1.3}
.rx-lblc{font-size:6.8px;text-align:center;border-bottom:1px solid #000;padding-bottom:2px;margin-bottom:2px}
.rx-vc{font-size:8.5px;text-align:center;font-weight:bold;margin-bottom:6px}
.rx-pos{width:100%;border-collapse:collapse;margin-top:5px}
.rx-pos th{font-size:6.4px;border:1px solid #000;padding:2px;font-weight:normal}
.rx-pos td{font-size:8px;border:1px solid #000;padding:4px;text-align:center;height:20px}
.rx-row{display:flex;justify-content:space-between;align-items:baseline;margin-top:5px;border-top:1px solid #ccc;padding-top:3px}
.rx-firma{font-size:7px;border-bottom:1px solid #000;padding:18px 7px 4px;text-align:center}
.rx-info{display:grid;grid-template-columns:1fr 1fr 1fr}
.rx-icol{border-right:1px solid #000;border-bottom:1px solid #000;padding:6px 7px;min-height:50px}.rx-icol:last-child{border-right:none}
.rx-chk{font-size:7.5px;margin-top:4px;display:flex;align-items:center;gap:5px}
.rx-sq{width:8px;height:8px;border:1px solid #000;display:inline-block}
.rx-info2{padding:2px 0}.rx-info2 .rx-k{margin:6px 8px 0}
.rx-blank{border-bottom:1px solid #000;height:32px;margin:3px 8px 0}
.rx-foot{display:grid;grid-template-columns:1fr auto 1fr;border-top:1.4px solid #000;align-items:center}
.rx-legal{font-size:5px;line-height:1.32;padding:5px 6px;text-align:justify;color:#000}
.rx-bar{padding:5px 10px;border-left:1px solid #000;border-right:1px solid #000;text-align:center}
.rx-bar svg{display:block;margin:0 auto}
.rx-barn{font-size:7px;letter-spacing:1px;margin-top:1px}
</style>`;

function recetaCopy(side: string, mode: 'farm' | 'pac'): string {
  const grid = `<div class="rx-grid">
    <div class="rx-col rx-presc">
      <div class="rx-k">PRESCRIPCIÓN. Consignar el medicamento: DCI o marca, forma farmacéutica, vía de administración, dosis por unidad y unidades por envase (Datos correspondientes en su caso de producto sanitario)</div>
      <div class="rx-env">Nº envases/unidades:<span class="rx-box-in">{{numEnvases}}</span></div>
      <div class="rx-med">{{medicamento}}</div>
    </div>
    <div class="rx-col rx-dur">
      <div class="rx-lblc">Duración del tratamiento</div><div class="rx-vc">{{duracion}}</div>
      <div class="rx-lblc">Posología</div><div class="rx-vc">{{formaFarmaceutica}}</div>
      <table class="rx-pos"><tr><th>Unidades</th><th>Pauta</th></tr><tr><td>{{unidades}}</td><td>{{pauta}}</td></tr></table>
    </div>
    <div class="rx-col rx-pac" style="position:relative">
      <div class="rx-k">PACIENTE (Nombre, apellidos, año de nacimiento y nº de DNI/NIE o nº de Pasaporte)</div>
      <div class="rx-v">{{paciente}}<br><span class="rx-vsm">{{pacienteNacim}}</span></div>
      <div class="rx-row"><span class="rx-k">Nº Orden dispensación</span><b class="rx-vsm">{{numOrden}}</b></div>
      <div class="rx-row"><span class="rx-k">Fecha prevista dispensación</span><b class="rx-vsm">{{fechaDispensacion}}</b></div>
      <div class="rx-k" style="margin-top:6px">PRESCRIPTOR (Nombre, apellidos, nº colegiado, especialidad, dirección, población y firma)</div>
      <div class="rx-v">{{prescriptor}}<br><span class="rx-vsm">Nº Colegiado {{numColegiado}}<br>{{prescriptorDir}}<br>{{prescriptorPob}}</span></div>
      <div class="rx-row"><span class="rx-k">Fecha de la prescripción</span><b class="rx-vsm">{{fechaPrescripcion}}</b></div>
      <!-- Firma/sello del profesional: SUPERPUESTO encima del texto (como un cuño real), z-index
           arriba, sin alterar la maqueta (position:absolute). Vacío = invisible. -->
      <div style="position:absolute;left:6px;right:6px;bottom:10px;height:62px;display:flex;align-items:center;justify-content:center;z-index:5;pointer-events:none;overflow:visible">{{firma}}</div>
    </div>
  </div>`;
  const mid = mode === 'farm'
    ? `<div class="rx-firma">Firma de Farmacéutico</div>
       <div class="rx-info">
         <div class="rx-icol"><div class="rx-k">Información al farmacéutico, en su caso:</div></div>
         <div class="rx-icol"><div class="rx-k">Motivo de la sustitución:</div><div class="rx-chk"><span class="rx-sq"></span> Urgencia</div><div class="rx-chk"><span class="rx-sq"></span> Desabastecimiento</div></div>
         <div class="rx-icol"><div class="rx-k">FARMACIA (NIF/CIF, datos de identificación y fecha de dispensación)</div></div>
       </div>`
    : `<div class="rx-info2">
         <div class="rx-k">Diagnóstico (si procede)</div><div class="rx-blank"></div>
         <div class="rx-k">Instrucciones al paciente (si procede)</div><div class="rx-blank"></div>
       </div>`;
  return `<div class="rx-copy">
    <div class="rx-num">Nº Receta: <b>{{numeroReceta}}</b></div>
    <div class="rx-title"><b>RECETA MÉDICA</b><br><span>ASISTENCIA SANITARIA PRIVADA</span></div>
    <div class="rx-main"><div class="rx-side">${side}</div><div class="rx-content">${grid}${mid}
      <div class="rx-foot"><div class="rx-legal">{{legalIzq}}</div><div class="rx-bar">{{barcode}}<div class="rx-barn">{{barcodeNum}}</div></div><div class="rx-legal">{{legalDer}}</div></div>
    </div></div>
  </div>`;
}

const recetaHtml = `${RX_STYLE}<div class="rx">${recetaCopy('RECETA MÉDICA PRIVADA', 'farm')}<div class="rx-cut"></div>${recetaCopy('INFORMACIÓN AL PACIENTE · ASISTENCIA PRIVADA', 'pac')}</div>`;

export const DOC_DEFAULTS: DocDef[] = [
  {
    id: 'factura', label: 'Factura paciente',
    html: wrap(`<div class="h"><div class="title">Factura</div></div>
<div class="meta" style="justify-content:space-between"><div><div class="l">Titular de la factura</div><div class="v" style="font-size:14px;color:#333;font-weight:500">{{paciente}}</div><div class="v">NIF {{nif}} · {{pacienteDir}}</div></div><div style="display:flex;gap:32px"><div style="text-align:right"><div class="l">N.º de factura</div><div class="v">{{numero}}</div></div><div style="text-align:right"><div class="l">Fecha</div><div class="v">{{fecha}}</div></div></div></div>
<table><thead><tr><th>Descripción</th><th class="r">Cantidad</th><th class="r">Precio unitario</th><th class="r">Precio total</th></tr></thead><tbody>{{lineas}}</tbody></table>
<div class="tot"><div class="notes"><b>Notas</b>{{notas}}</div><div class="sums"><div class="sumr"><span class="k">Subtotal</span><span class="x">{{subtotal}}</span></div><div class="sumr"><span class="k">{{ivaLabel}}</span><span class="x">{{iva}}</span></div><div class="total"><span class="k">Total</span><span class="x">{{total}}</span></div></div></div>
<div class="sign"><div class="sigbox" style="text-align:left">{{sello}}</div></div>`),
    campos: [
      { key: 'notas', label: 'Notas', multiline: true },
      { key: 'ivaLabel', label: 'Etiqueta IVA' },
      { key: 'pie', label: 'Pie de página', multiline: true },
    ],
  },
  {
    id: 'recibo', label: 'Recibo paciente',
    html: wrap(`<div class="h"><div class="title">Recibo</div><div class="date">{{fecha}}</div></div>
<div class="meta"><div><div class="l">N.º de recibo</div><div class="v">{{numero}}</div></div><div><div class="l">Forma de pago</div><div class="v">{{formaPago}}</div></div><div><div class="l">Factura asociada</div><div class="v">{{facturaRef}}</div></div></div>
<p class="lead">{{cuerpo}}</p>
<div class="amount-box"><span class="k">Cantidad recibida</span><span class="x">{{total}}</span></div>
<div class="sign"><div class="sigbox">{{sello}}<div class="sigline"></div><div class="t">Firma y sello de la clínica</div></div><div class="sigbox"><div class="sigline"></div><div class="t">Recibí — el paciente</div></div></div>`),
    campos: [
      { key: 'cuerpo', label: 'Texto del recibo', multiline: true },
      { key: 'pie', label: 'Pie de página', multiline: true },
    ],
  },
  {
    id: 'facturaDoctor', label: 'Factura doctores',
    html: wrap(`<div class="h"><div class="title">Factura</div><div class="date">Fecha: {{fecha}}</div></div>
<div class="meta"><div><div class="l">N.º de factura</div><div class="v">{{numero}}</div></div><div><div class="l">Periodo</div><div class="v">{{periodo}}</div></div><div><div class="l">Estado</div><div class="v" style="color:var(--pink);font-weight:700">{{estado}}</div></div></div>
<div class="bill"><div><div class="l">Facturar a</div><div class="n">{{doctor}}</div><div class="s">{{doctorInfo}}</div></div><div style="text-align:right"><div class="l">NIF</div><div class="n">{{doctorNif}}</div></div></div>
<table><thead><tr><th>Concepto · producción</th><th class="r">Actos</th><th class="r">Importe</th><th class="r">% Colab.</th><th class="r">Total</th></tr></thead><tbody>{{lineas}}</tbody></table>
<div class="tot"><div class="notes"><b>Notas</b>{{notas}}</div><div class="sums"><div class="sumr"><span class="k">Base honorarios</span><span class="x">{{base}}</span></div><div class="sumr"><span class="k">{{irpfLabel}}</span><span class="x">{{irpf}}</span></div><div class="total"><span class="k">Líquido a percibir</span><span class="x">{{total}}</span></div></div></div>
<div class="sign"><div class="sigbox" style="text-align:left">{{sello}}</div></div>`),
    campos: [
      { key: 'notas', label: 'Notas', multiline: true },
      { key: 'irpfLabel', label: 'Etiqueta retención IRPF' },
      { key: 'pie', label: 'Pie de página', multiline: true },
    ],
  },
  {
    id: 'justificante', label: 'Justificante de asistencia',
    html: wrap(`<div class="h"><div class="title">Justificante</div><div class="date">{{fecha}}</div></div>
<div class="meta"><div><div class="l">Paciente</div><div class="v">{{paciente}}</div></div><div><div class="l">NIF</div><div class="v">{{nif}}</div></div><div><div class="l">Fecha de consulta</div><div class="v">{{fechaLarga}}</div></div><div><div class="l">Horario</div><div class="v">{{horaIni}} – {{horaFin}} h</div></div></div>
<div class="bill"><div><div class="l">Centro</div><div class="n">{{clinicName}}</div><div class="s">{{clinicDir}} · {{clinicTel}}</div></div><div style="text-align:right"><div class="l">Facultativo</div><div class="n">{{doctor}}</div><div class="s">{{firmante}}</div></div></div>
<div style="border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:10px 0;margin:18px 0 20px"><span style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--ink)">{{subtitulo}}</span></div>
<p class="lead">{{cuerpo}}</p>
<p class="lead">{{cierre}}</p>
<div class="sign"><div class="sigbox">{{sello}}<div class="sigline"></div><div class="t">{{firmante}}<br>Firma y sello de la clínica</div></div></div>`),
    campos: [
      { key: 'subtitulo', label: 'Subtítulo' },
      { key: 'cuerpo', label: 'Texto de certificación', multiline: true },
      { key: 'cierre', label: 'Cierre', multiline: true },
      { key: 'firmante', label: 'Firmante (número de colegiado)' },
      { key: 'pie', label: 'Pie de página', multiline: true },
    ],
  },
  {
    id: 'receta', label: 'Receta',
    html: recetaHtml,
    campos: [
      { key: 'legalIzq', label: 'Texto legal (izquierda)', multiline: true },
      { key: 'legalDer', label: 'Texto legal (derecha)', multiline: true },
    ],
  },
  {
    id: 'presupuesto', label: 'Presupuesto',
    html: wrap(`<div class="h"><div class="title" style="font-size:25.6px;margin-top:-10px">Presupuesto</div><div class="date">Fecha: {{fecha}}</div></div>
<div class="bill" style="border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:12px 0"><div><div class="n">{{paciente}}</div><div class="s">{{pacienteInfo}}</div></div><div><div class="l">Doctor</div><div class="n">{{profesional}}</div></div><div><div class="l">N.º de presupuesto</div><div class="n">{{numero}}</div></div></div>
{{odontograma}}
<table><thead><tr><th>Pza</th><th>Tratamiento</th><th class="r">Cant</th><th class="r">Precio</th><th class="r">Dto</th><th class="r">Total</th></tr></thead><tbody>{{lineas}}</tbody></table>
<div class="tot"><div class="notes"><b>Notas / financiación</b>{{notas}}</div><div class="sums"><div class="sumr"><span class="k">Subtotal</span><span class="x">{{subtotal}}</span></div><div class="sumr"><span class="k">Descuento</span><span class="x" style="color:var(--ok)">{{descuento}}</span></div><div class="sumr"><span class="k">Pendiente</span><span class="x" style="color:var(--navy2)">{{pendiente}}</span></div><div class="total"><span class="k">Total</span><span class="x">{{total}}</span></div></div></div>
<div class="sign"><div class="sigbox"><div class="sigline"></div><div class="t">Acepto el presupuesto — el paciente</div></div><div class="sigbox"><div class="sigline"></div><div class="t">Fecha de aceptación</div></div></div>`),
    // Muestra de 6 columnas para la vista previa (coincide con la cabecera Pza/Tratamiento/Cant/Precio/Dto/Total).
    sample: {
      lineas: '<tr><td>14</td><td class="d">Obturación composite</td><td class="r">1</td><td class="r">120,00 €</td><td class="r">10 %</td><td class="r">108,00 €</td></tr><tr><td>—</td><td class="d">Higiene dental · arcada superior</td><td class="r">1</td><td class="r">60,00 €</td><td class="r">—</td><td class="r">60,00 €</td></tr>',
    },
    campos: [
      { key: 'notas', label: 'Notas / financiación', multiline: true },
      { key: 'validez', label: 'Texto de validez' },
      { key: 'pie', label: 'Pie de página', multiline: true },
    ],
  },
  {
    id: 'historia', label: 'Copia historia clínica',
    html: wrap(`<div class="h"><div class="title">Historia clínica</div><div class="date">Copia · {{fecha}}</div></div>
<div class="bill"><div><div class="l">Paciente</div><div class="n">{{paciente}}</div><div class="s">{{pacienteInfo}}</div></div><div style="text-align:right"><div class="l">Alergias</div><div class="n" style="color:var(--pink)">{{alergias}}</div></div></div>
<div style="border-top:1px solid var(--line);padding-top:14px">{{registros}}</div>
<div class="sign" style="margin-top:44px"><div class="sigbox"><div class="sigline"></div><div class="t">El paciente<br>{{paciente}}</div></div><div class="sigbox" style="position:relative">
  <!-- Firma del profesional + sello del centro, SUPERPUESTOS como un cuño real (no alteran la maqueta). Vacío = invisible. -->
  <div style="position:absolute;left:0;right:0;bottom:20px;height:60px;display:flex;align-items:center;justify-content:center;z-index:5;pointer-events:none;overflow:visible">{{firma}}</div>
  <div class="sigline"></div><div class="t">{{doctor}} · Nº col. {{numColegiado}}<br>El facultativo · sello del centro</div></div></div>`),
    campos: [
      { key: 'pie', label: 'Pie de página (RGPD)', multiline: true },
    ],
  },
  {
    id: 'consentimiento', label: 'Consentimiento informado',
    html: wrap(`<div class="h"><div class="title">Consentimiento informado</div><div class="date">{{fecha}}</div></div>
<div class="meta"><div><div class="l">Paciente</div><div class="v">{{paciente}}</div></div><div><div class="l">NIF</div><div class="v">{{nif}}</div></div><div><div class="l">F. nacimiento</div><div class="v">{{fechaNac}}</div></div><div><div class="l">Nº historia</div><div class="v">{{numPaciente}}</div></div></div>
<div class="bill"><div><div class="l">Facultativo responsable</div><div class="n">{{doctor}}</div><div class="s">Nº colegiado {{numColegiado}}</div></div><div style="text-align:right"><div class="l">Tratamiento / procedimiento</div><div class="n">{{tratamiento}}</div><div class="s">{{piezas}}</div></div></div>
${sec('1 · Naturaleza y objetivo del tratamiento', '<p class="lead">{{cuerpo}}</p>')}
${sec('2 · Beneficios esperados', '<p class="lead">{{beneficios}}</p>')}
${sec('3 · Alternativas terapéuticas', '<p class="lead">{{alternativas}}</p>')}
${sec('4 · Riesgos y complicaciones', '<p class="lead">{{riesgos}}</p>' + checks(['Inflamación y dolor', 'Infección', 'Hemorragia', 'Reacción a la anestesia', 'Lesión de tejidos vecinos', 'Fractura de instrumental', 'Parestesia transitoria', 'Fracaso del tratamiento', 'Necesidad de retratamiento']))}
${sec('5 · Consecuencias de no realizar el tratamiento', '<p class="lead">{{noTratar}}</p>')}
${sec('6 · Cuidados y recomendaciones posteriores', '<p class="lead">{{cuidados}}</p>')}
${sec('7 · Declaración y autorización del paciente', '<p class="lead">{{declaracion}}</p>' + checks(['He comprendido la información recibida', 'He podido preguntar y aclarar dudas', 'He facilitado mis antecedentes de forma veraz', 'Autorizo la realización del tratamiento'], 1))}
${sec('Protección de datos', '<p class="lead" style="font-size:11px;color:var(--gray2)">{{rgpd}}</p>')}
<div class="sign" style="margin-top:30px"><div class="sigbox"><div class="sigline"></div><div class="t">El paciente / representante legal<br>{{paciente}}</div></div><div class="sigbox">{{sello}}<div class="sigline"></div><div class="t">{{doctor}} · Nº col. {{numColegiado}}<br>El facultativo</div></div></div>
<div style="margin-top:24px;border:1px dashed var(--line);border-radius:6px;padding:10px 14px"><div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--navy2);margin-bottom:6px">Revocación del consentimiento</div><p class="lead" style="font-size:11px;margin:0">{{revocacion}}</p><div class="sign" style="margin-top:16px"><div class="sigbox"><div class="sigline"></div><div class="t">Firma (revocación) · Fecha</div></div></div></div>`),
    campos: [
      { key: 'cuerpo', label: 'Naturaleza y objetivo', multiline: true },
      { key: 'beneficios', label: 'Beneficios esperados', multiline: true },
      { key: 'alternativas', label: 'Alternativas', multiline: true },
      { key: 'riesgos', label: 'Riesgos (texto)', multiline: true },
      { key: 'noTratar', label: 'Consecuencias de no tratarse', multiline: true },
      { key: 'cuidados', label: 'Cuidados posteriores', multiline: true },
      { key: 'declaracion', label: 'Declaración del paciente', multiline: true },
      { key: 'revocacion', label: 'Texto de revocación', multiline: true },
      { key: 'rgpd', label: 'Cláusula RGPD', multiline: true },
      { key: 'pie', label: 'Pie de página', multiline: true },
    ],
  },
  {
    id: 'primeraVisita', label: 'Formulario de primera visita',
    html: wrap(`<div class="h"><div class="title">Primera visita · Anamnesis</div><div class="date">{{fecha}}</div></div>
<p class="lead" style="margin-top:0">{{intro}}</p>
${sec('Datos del paciente', '<div class="meta" style="margin-bottom:0"><div><div class="l">Nombre y apellidos</div><div class="v">{{paciente}}</div></div><div><div class="l">F. nacimiento</div><div class="v">{{fechaNac}}</div></div><div><div class="l">NIF</div><div class="v">{{nif}}</div></div></div><div class="meta" style="border-top:none"><div><div class="l">Teléfono</div><div class="v">{{telefono}}</div></div><div><div class="l">Email</div><div class="v">{{email}}</div></div><div><div class="l">Profesión</div><div class="v">{{profesion}}</div></div></div>' + fill('Dirección'))}
${sec('Motivo de la consulta', fill('', 26) + fill('¿Cómo nos ha conocido?'))}
${sec('Antecedentes médicos', '<p class="lead" style="margin:4px 0">¿Padece o ha padecido alguna de estas condiciones? Marque lo que proceda:</p>' + checks(['Cardiopatía / soplo', 'Hipertensión arterial', 'Diabetes', 'Problemas de coagulación', 'Toma anticoagulantes', 'Hepatitis / enf. hepática', 'VIH', 'Asma / enf. respiratoria', 'Epilepsia', 'Alergias medicamentosas', 'Bifosfonatos', 'Marcapasos / prótesis', 'Cáncer / quimio-radioterapia', 'Enf. renal', 'Trastorno tiroideo', 'Reumatismo / artritis', 'Trasplante de órgano', 'Embarazo / lactancia']) + fill('¿Está bajo tratamiento médico actualmente? ¿Cuál?'))}
${sec('Medicación actual', fill('Indique medicamentos y dosis', 26))}
${sec('Alergias', checks(['Penicilina / antibióticos', 'Anestésicos locales', 'Látex', 'AINEs / aspirina', 'Metales', 'Otras']) + fill('Especifique'))}
${sec('Hábitos', checks(['Tabaco', 'Alcohol', 'Bruxismo / rechinar', 'Onicofagia'], 4))}
${sec('Antecedentes odontológicos', fill('Fecha de la última visita al dentista') + '<p class="lead" style="margin:8px 0 2px">Nivel de ansiedad ante el tratamiento dental:</p>' + checks(['Ninguno', 'Leve', 'Moderado', 'Alto'], 4))}
${sec('Higiene bucal', checks(['Cepillado 1 vez/día', 'Cepillado 2+ veces/día', 'Uso de seda dental', 'Uso de colutorio'], 2))}
${sec('Declaración y protección de datos', '<p class="lead">Declaro que los datos facilitados son veraces y completos, y me comprometo a comunicar cualquier cambio en mi estado de salud.</p><p class="lead" style="font-size:11px;color:var(--gray2)">{{rgpd}}</p>')}
<div class="sign" style="margin-top:26px"><div class="sigbox"><div class="sigline"></div><div class="t">Firma del paciente / representante</div></div><div class="sigbox"><div class="sigline"></div><div class="t">Fecha</div></div></div>`),
    campos: [
      { key: 'intro', label: 'Texto introductorio', multiline: true },
      { key: 'rgpd', label: 'Cláusula RGPD', multiline: true },
      { key: 'pie', label: 'Pie de página', multiline: true },
    ],
  },
  {
    id: 'recomendaciones', label: 'Recomendaciones post-tratamiento',
    html: wrap(`<div class="h"><div class="title">Recomendaciones</div><div class="date">{{fecha}}</div></div>
<div class="bill"><div><div class="l">Paciente</div><div class="n">{{paciente}}</div><div class="s">Nº historia {{numPaciente}}</div></div><div style="text-align:right"><div class="l">Tratamiento</div><div class="n">{{tratamiento}}</div><div class="s">{{doctor}}</div></div></div>
<p class="lead" style="margin-top:0">{{intro}}</p>
${sec('Cuidados recomendados', '<p class="lead">{{cuerpo}}</p>')}
${sec('Medicación pautada', '<p class="lead">{{medicacion}}</p>')}
${sec('Cuándo contactar con la clínica', '<p class="lead">{{avisos}}</p>')}
<div class="amount-box" style="margin-top:20px"><div class="k">Próxima revisión</div><div class="x" style="font-size:16px">{{revision}}</div></div>
<div class="sign" style="margin-top:30px"><div class="sigbox">{{sello}}<div class="sigline"></div><div class="t">{{doctor}}<br>El facultativo</div></div><div class="sigbox"><div class="sigline"></div><div class="t">Fecha de entrega</div></div></div>`),
    campos: [
      { key: 'intro', label: 'Texto introductorio', multiline: true },
      { key: 'cuerpo', label: 'Cuidados recomendados', multiline: true },
      { key: 'medicacion', label: 'Medicación pautada', multiline: true },
      { key: 'avisos', label: 'Cuándo contactar con la clínica', multiline: true },
      { key: 'revision', label: 'Próxima revisión' },
      { key: 'pie', label: 'Pie de página', multiline: true },
    ],
  },
  {
    id: 'cuestionario', label: 'Cuestionario clínico',
    html: wrap(`<div class="h"><div class="title">{{titulo}}</div><div class="date">{{fecha}}</div></div>
<div class="meta"><div><div class="l">Paciente</div><div class="v">{{paciente}}</div></div><div><div class="l">Nº historia</div><div class="v">{{numPaciente}}</div></div><div><div class="l">Fecha</div><div class="v">{{fecha}}</div></div></div>
<p class="lead" style="margin-top:0">{{intro}}</p>
${sec('Estado desde la última visita', '<p class="lead" style="margin:4px 0">Marque lo que corresponda:</p>' + checks(['Dolor o molestias', 'Sangrado de encías', 'Sensibilidad al frío/calor', 'Movilidad de algún diente', 'Dificultad al masticar', 'Mal aliento persistente', 'Aftas o llagas', 'Bruxismo / rechinar'], 2))}
${sec('Grado de satisfacción con el tratamiento', checks(['Muy satisfecho', 'Satisfecho', 'Regular', 'Insatisfecho'], 4))}
${sec('Higiene y hábitos', checks(['Cepillado 2+ veces/día', 'Uso de seda dental', 'Uso de colutorio', 'Revisiones periódicas'], 2))}
${sec('Observaciones', fill('', 26) + fill(''))}
${sec('Declaración', '<p class="lead">{{declaracion}}</p>')}
<div class="sign" style="margin-top:26px"><div class="sigbox"><div class="sigline"></div><div class="t">Firma del paciente / representante</div></div><div class="sigbox"><div class="sigline"></div><div class="t">Fecha</div></div></div>`),
    campos: [
      { key: 'titulo', label: 'Título del cuestionario' },
      { key: 'intro', label: 'Texto introductorio', multiline: true },
      { key: 'declaracion', label: 'Declaración', multiline: true },
      { key: 'pie', label: 'Pie de página', multiline: true },
    ],
  },
];

// Valores por defecto de los campos editables (se guardan en clinic_settings).
export const CAMPOS_DEFAULT: Record<string, Record<string, string>> = {
  factura: {
    notas: 'Gracias por su confianza. El pago puede realizarse en clínica o por transferencia. IVA exento (art. 20.Uno.3º Ley 37/1992 — asistencia sanitaria).',
    ivaLabel: 'IVA exento (0%)',
    pie: 'Tridental Odontólogos SLP · B88393764 · C/ Mayor 19, 28921 Alcorcón (Madrid) · Inscrita en el Registro Mercantil de Madrid',
  },
  recibo: {
    cuerpo: 'He recibido de <b>{{paciente}}</b> (NIF {{nif}}) la cantidad de <b>{{totalLetra}} ({{total}})</b> en concepto de tratamiento odontológico realizado en la fecha indicada.',
    pie: 'Tridental Odontólogos SLP · B88393764 · C/ Mayor 19, 28921 Alcorcón (Madrid)',
  },
  facturaDoctor: {
    notas: 'Liquidación de honorarios por producción del periodo. Retención IRPF aplicada según normativa vigente.',
    irpfLabel: 'Retención IRPF (15%)',
    pie: 'Tridental Odontólogos SLP · B88393764 · C/ Mayor 19, 28921 Alcorcón (Madrid)',
  },
  justificante: {
    subtitulo: 'Justificante de asistencia a consulta',
    cuerpo: 'Se certifica que <b>D./Dña. {{paciente}}</b>, con NIF <b>{{nif}}</b>, ha asistido a consulta odontológica en este centro el día <b>{{fechaLarga}}</b>, de <b>{{horaIni}}</b> a <b>{{horaFin}}</b> horas.',
    cierre: 'Se expide el presente justificante a petición de la persona interesada, a los efectos oportunos.',
    firmante: '{{clinicFiscal}}',
    pie: 'Tridental Odontólogos SLP · B88393764 · C/ Mayor 19, 28921 Alcorcón (Madrid)',
  },
  presupuesto: {
    notas: 'Presupuesto sin compromiso, válido 3 meses. Formas de pago y financiación disponibles en clínica. No incluye tratamientos no detallados.',
    validez: '{{validezFecha}}', pie: 'Tridental Odontólogos SLP · B88393764 · C/ Mayor 19, 28921 Alcorcón (Madrid)',
  },
  historia: {
    pie: 'Documento confidencial — datos de salud (RGPD/LOPDGDD). Entregado al titular a petición propia. Tridental Odontólogos SLP · B88393764',
  },
  consentimiento: {
    cuerpo: 'Se me ha explicado de forma comprensible el diagnóstico y la naturaleza del tratamiento propuesto, su finalidad y en qué consiste, así como el número de sesiones previsto y el tipo de anestesia a emplear.',
    beneficios: 'El tratamiento persigue eliminar la patología existente y restaurar la función masticatoria, la salud y la estética dental, mejorando mi calidad de vida.',
    alternativas: 'Se me han expuesto las alternativas terapéuticas razonables, incluida la opción de no realizar ningún tratamiento, con sus ventajas e inconvenientes.',
    riesgos: 'Todo acto odontológico conlleva riesgos generales y otros específicos del procedimiento, que se me han detallado verbalmente. Entre los más frecuentes:',
    noTratar: 'De no realizarse el tratamiento, la patología puede progresar, agravando el cuadro y pudiendo requerir intervenciones más complejas o la pérdida de piezas dentales.',
    cuidados: 'Me comprometo a seguir las indicaciones de higiene, medicación y revisiones, y a acudir a las citas programadas para el correcto desarrollo del tratamiento.',
    declaracion: 'He recibido información suficiente, he podido formular las preguntas que he considerado oportunas y me han sido aclaradas. En consecuencia, presto libremente mi consentimiento:',
    revocacion: 'Revoco el consentimiento anteriormente otorgado y manifiesto mi decisión de no continuar con el tratamiento, sin que ello suponga responsabilidad alguna para el centro.',
    rgpd: 'En cumplimiento del RGPD (UE) 2016/679 y la LOPDGDD 3/2018, sus datos de salud se incorporan a los ficheros de Tridental Odontólogos SLP con la finalidad de la prestación asistencial. Puede ejercer sus derechos de acceso, rectificación, supresión, oposición, limitación y portabilidad dirigiéndose al centro.',
    pie: 'Tridental Odontólogos SLP · B88393764 · C/ Mayor 19, 28921 Alcorcón (Madrid)',
  },
  primeraVisita: {
    intro: 'Para ofrecerle la mejor atención, le rogamos complete sus datos de salud. La información es confidencial y se trata conforme al RGPD.',
    rgpd: 'En cumplimiento del RGPD (UE) 2016/679 y la LOPDGDD 3/2018, sus datos se incorporan a los ficheros de Tridental Odontólogos SLP con la finalidad de la prestación asistencial. Puede ejercer sus derechos de acceso, rectificación, supresión y oposición dirigiéndose al centro.',
    pie: 'Tridental Odontólogos SLP · B88393764 · C/ Mayor 19, 28921 Alcorcón (Madrid)',
  },
  receta: {
    legalIzq: 'La validez de esta receta es de 10 días naturales a partir de la fecha prevista para la dispensación. En caso de no constar la fecha de prescripción, la medicación prescrita no podrá superar los 3 meses de tratamiento. La receta es válida para una única dispensación en la farmacia.',
    legalDer: 'En cumplimiento de lo establecido en el artículo 5 de la Ley Orgánica 15/1999, se le informa de que sus datos serán incorporados a un fichero de titularidad del prescriptor para la gestión de la prescripción y dispensación, en cumplimiento de la obligación establecida en el RD 1718/2010. Podrá ejercer sus derechos de acceso, rectificación, cancelación y oposición ante el prescriptor y/o la farmacia dispensadora.',
  },
  recomendaciones: {
    intro: 'Tras el tratamiento realizado hoy, le facilitamos estas indicaciones para su cuidado. Si tiene cualquier duda, contacte con la clínica.',
    cuerpo: 'Evite comer hasta que pase el efecto de la anestesia. Los primeros días, mastique por el lado contrario y prefiera alimentos blandos y templados. Mantenga una buena higiene, cepillando con suavidad la zona.',
    medicacion: 'Tome la medicación pautada según las indicaciones. No supere las dosis indicadas. Si aparece alergia o malestar, suspenda y contacte con la clínica.',
    avisos: 'Contacte con nosotros si aparece dolor intenso que no cede con la medicación, hinchazón creciente, sangrado que no se detiene o fiebre.',
    revision: 'A concretar con la clínica',
    pie: 'Tridental Odontólogos SLP · B88393764 · C/ Mayor 19, 28921 Alcorcón (Madrid)',
  },
  cuestionario: {
    titulo: 'Cuestionario de seguimiento',
    intro: 'Le rogamos dedique un momento a responder este cuestionario. Nos ayuda a mejorar su atención. La información es confidencial y se trata conforme al RGPD.',
    declaracion: 'Declaro que las respuestas facilitadas son veraces y autorizo su uso para el seguimiento de mi tratamiento.',
    pie: 'Tridental Odontólogos SLP · B88393764 · C/ Mayor 19, 28921 Alcorcón (Madrid)',
  },
};

// Datos de muestra para la vista previa.
export const SAMPLE: Record<string, string> = {
  clinicName: 'Rubio García Dental', clinicFiscal: 'Tridental Odontólogos SLP · B88393764',
  clinicDir: 'C/ Mayor 19, 28921 Alcorcón (Madrid)', clinicTel: '916 410 841 · 664 218 253', clinicEmail: 'info@rubiogarciadental.com',
  clinicLogo: '<div style="display:inline-block;width:36px;height:36px;border-radius:6px;background:#6D64E8;color:#fff;font-weight:700;font-size:13px;text-align:center;line-height:36px;vertical-align:middle;margin-right:10px">RG</div>', clinicWeb: '<br>www.rubiogarciadental.com',
  sello: '<div style="border:1.5px solid #283592;border-radius:8px;padding:6px 12px;color:#283592;font-size:8.5px;font-weight:700;line-height:1.4;display:inline-block;transform:rotate(-4deg);opacity:.85;text-align:center">TRIDENTAL ODONTOLOGOS S.L.P.<br>CIF B-88393764<br>C/ Mayor 19 · 28921 Alcorcón</div>',
  fecha: '04/06/2026', fechaPago: '18/06/2026', fechaLarga: '4 de junio de 2026', validezFecha: '04/09/2026',
  numero: 'FAC-2026-00123', estado: 'Pendiente', paciente: 'García López, Ana', nif: '12345678A',
  pacienteDir: 'C/ del Sol 12, 3º B · 28922 Alcorcón (Madrid)', pacienteInfo: 'NIF 12345678A · Nº paciente 4754 · F. nac. 12/03/1985',
  alergias: 'Penicilina · Látex', formaPago: 'Tarjeta', facturaRef: 'FAC-2026-00123',
  tratamiento: 'Endodoncia y reconstrucción · pieza 26', fechaNac: '12/03/1985', telefono: '664 218 253',
  numPaciente: '4754', piezas: 'Piezas 26, 27', email: 'ana.garcia@email.com', profesion: 'Administrativa',
  total: '300,00 €', totalLetra: 'trescientos euros', subtotal: '300,00 €', iva: '0,00 €', descuento: '−90,00 €',
  doctor: 'Dra. Irene García Sanz', doctorInfo: 'Colaboradora odontóloga · Nº col. 28004567', doctorNif: '50123456B',
  periodo: 'Mayo 2026', base: '1.926,00 €', irpf: '−288,90 €', horaIni: '10:00', horaFin: '10:45',
  lineas: '<tr><td class="d">Obturación composite · pieza 14</td><td class="r">1</td><td class="r">120,00 €</td><td class="r">120,00 €</td></tr><tr><td class="d">Higiene dental</td><td class="r">1</td><td class="r">60,00 €</td><td class="r">60,00 €</td></tr>',
  registros: '<div class="rec"><div class="rh"><span class="rd">Obturación composite · 14, 15</span><span class="rt">04/06/2026 · Dr. Rubio</span></div><div class="soap"><b style="background:#1ca0d1">S</b><span>Dolor al frío lado derecho.</span><b style="background:#3388FF">O</b><span>Caries interproximal 14-15.</span><b style="background:#7C3AED">A</b><span>Caries activa sin afectación pulpar.</span><b style="background:#2DD9C3">P</b><span>Obturación composite en dos sesiones.</span></div></div>',
  // Receta (datos de muestra para la vista previa)
  numeroReceta: '28-0468972', medicamento: 'AMOXICILINA 750 MG COMPRIMIDOS', numEnvases: '1',
  duracion: '1 semana', formaFarmaceutica: 'comprimidos', unidades: '1', pauta: 'cada 8 horas',
  pacienteNacim: '26/07/1970 · 12345678A', numOrden: '1', fechaDispensacion: '02/07/2025',
  prescriptor: 'Dr./Dra. MARIO RUBIO GARCIA', numColegiado: '28007352',
  prescriptorDir: 'CL MAYOR 19,', prescriptorPob: '28921 ALCORCON', fechaPrescripcion: '02/07/2025',
  barcode: code128Svg('2800735272025122643'), barcodeNum: '2800735272025122643',
  // Firma de MUESTRA (solo preview): hoy se estampa el SELLO del centro (aún no hay firmas de
  // colaborador subidas); cuando las haya, el backend usará la del colaborador.
  firma: '<div style="border:1.5px solid #283592;border-radius:8px;padding:6px 10px;color:#283592;font-size:8.5px;font-weight:700;line-height:1.4;display:inline-block;transform:rotate(-4deg);opacity:.9;text-align:center">TRIDENTAL ODONTOLOGOS S.L.P.<br>CIF B-88393764</div>',
};

// Claves cuyo valor es HTML ESTRUCTURAL deliberado (logo/sello/odontograma/filas de tabla/
// código de barras/web con <br>). El resto de valores (nombre, notas, tratamiento…) son TEXTO
// y se ESCAPAN para no inyectar HTML/JS en el documento (evita el stored-XSS al imprimir/PDF).
const DOC_HTML_KEYS = new Set(['clinicLogo', 'sello', 'clinicWeb', 'odontograma', 'lineas', 'registros', 'barcode', 'firma']);
function htmlEscape(v: string): string {
  return String(v ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string
  ));
}

/** Reemplaza {{key}} por su valor (campos → sample → vacío). Doble pasada para campos que
 *  contienen placeholders. Los valores de TEXTO se escapan; las claves de HTML estructural no. */
export function renderDoc(html: string, campos: Record<string, string>, data: Record<string, string>): string {
  const vars = { ...data, ...campos };
  const sub = (s: string) => s.replace(/\{\{(\w+)\}\}/g, (_, k) => {
    const v = (vars[k] ?? data[k] ?? '') as string;
    return DOC_HTML_KEYS.has(k) ? String(v) : htmlEscape(String(v));
  });
  return `<!doctype html><html lang="es"><head><meta charset="utf-8"><style>${DOC_CSS}</style></head><body>${sub(sub(html))}</body></html>`;
}
