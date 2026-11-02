"""Plantillas PDF de documentos generados (recibos/facturas reconstruidas). En la app, reutilizable.

Un solo sitio para generar el PDF de: recibo de alquiler, autofactura de profesional y factura/recibo
genérico de proveedor. Devuelven bytes PDF. Usados por el motor de conciliación (conciliacion_service).
"""
from typing import Optional

import fitz

RECEPTOR = ("TRIDENTAL ODONTÓLOGOS S.L.P.<br>N.I.F. B88393764<br>"
            "Calle José Antonio Aguirre, nº 2, 2º C<br>GETAFE-28905 (Madrid)")


def _esc(v) -> str:
    """Escapa texto de BBDD antes de incrustarlo en el HTML del documento (evita rotura de
    layout/inyección; fitz no ejecuta JS, pero mantenemos la salida robusta)."""
    return (str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


def eur(x: float) -> str:
    return f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _render(html: str) -> bytes:
    doc = fitz.open(); pg = doc.new_page()
    pg.insert_htmlbox(fitz.Rect(40, 40, 555, 802), html)
    out = doc.tobytes(); doc.close()
    return out


def recibo_alquiler(numero: str, fecha: str, base: float,
                    propietario: str, domicilio: str, dni: str) -> bytes:
    numero, propietario, domicilio, dni = _esc(numero), _esc(propietario), _esc(domicilio), _esc(dni)
    iva = round(base * 0.21, 2); irpf = round(base * 0.19, 2); total = round(base + iva - irpf, 2)
    return _render(f'''
    <div style="font-family:sans-serif;font-size:11px;color:#000">
      <table style="width:100%;border-collapse:collapse;table-layout:fixed">
        <tr>
          <td style="border:1px solid #000;padding:6px;width:33%"><b>Recibo Nº</b><br><span style="font-size:14px">{numero}</span></td>
          <td style="border:1px solid #000;padding:6px;width:34%"><b>Localidad de expedición</b><br>Alcorcón</td>
          <td style="border:1px solid #000;padding:6px;width:33%"><table style="width:100%">
            <tr><td>Subtotal</td><td style="text-align:right;white-space:nowrap">{eur(base)}</td></tr>
            <tr><td>I.V.A. 21%</td><td style="text-align:right;white-space:nowrap">{eur(iva)}</td></tr>
            <tr><td>I.R.P.F. 19%</td><td style="text-align:right;white-space:nowrap">{eur(irpf)}</td></tr></table></td>
        </tr>
        <tr>
          <td style="border:1px solid #000;padding:6px"><b>Vencimiento</b><br>{fecha}</td>
          <td style="border:1px solid #000;padding:6px"><b>Fecha de expedición</b><br>{fecha}</td>
          <td style="border:1px solid #000;padding:6px"><b>TOTAL</b> &nbsp; <b>{eur(total)}</b></td>
        </tr>
        <tr><td colspan="3" style="border:1px solid #000;padding:6px"><b>Propietario:</b> {propietario}<br>
          <b>Domicilio:</b> {domicilio}<br><b>DNI:</b> {dni}</td></tr>
      </table><br>
      <table style="width:100%;border-collapse:collapse;table-layout:fixed">
        <tr><td style="border:1px solid #000;padding:5px;width:25%"><b>Renta</b><br>{eur(base)}</td>
            <td style="border:1px solid #000;padding:5px;width:25%"><b>Aumentos legales</b><br>&nbsp;</td>
            <td style="border:1px solid #000;padding:5px;width:25%"><b>I.R.P.F.</b><br>{eur(irpf)}</td>
            <td style="border:1px solid #000;padding:5px;width:25%"><b>I.V.A.</b><br>{eur(iva)}</td></tr>
      </table><br>
      <table style="width:100%"><tr>
        <td style="width:58%;vertical-align:top"><b>Nombre y Domicilio del librado. D.N.I.</b><br>{RECEPTOR}</td>
        <td style="vertical-align:top"><b>Firma</b><div style="border:1px solid #000;height:70px;margin-top:4px"></div></td>
      </tr></table>
    </div>''')


def autofactura(numero: str, fecha: str, nombre: str, nif: Optional[str], colegiado: Optional[str],
                base: float, irpf_pct: float, concepto: str) -> bytes:
    numero, nombre, nif, colegiado, concepto = _esc(numero), _esc(nombre), _esc(nif), _esc(colegiado), _esc(concepto)
    irpf = round(base * irpf_pct, 2); liquido = round(base - irpf, 2)
    ret = (f'<tr><td style="padding:2px">Retención IRPF {int(irpf_pct*100)}%</td>'
           f'<td style="text-align:right;white-space:nowrap">− {eur(irpf)}</td></tr>') if irpf_pct > 0 else ''
    coleg = f"Nº Colegiado: {colegiado}" if colegiado else ""
    return _render(f'''
    <div style="font-family:sans-serif;font-size:11px;color:#000">
      <div style="text-align:center;font-size:16px;font-weight:bold;letter-spacing:2px;margin-bottom:12px">FACTURA</div>
      <table style="width:100%;border-collapse:collapse;table-layout:fixed">
        <tr><td style="border:1px solid #000;padding:6px;width:50%"><b>Nº Factura</b><br><span style="font-size:14px">{numero}</span></td>
            <td style="border:1px solid #000;padding:6px;width:50%"><b>Fecha de expedición</b><br>{fecha}</td></tr>
      </table><br>
      <table style="width:100%;border-collapse:collapse;table-layout:fixed">
        <tr><td style="border:1px solid #000;padding:6px;width:50%;vertical-align:top"><b>EMISOR</b><br>{nombre}<br>N.I.F. {nif or '(pendiente)'}<br>{coleg}</td>
            <td style="border:1px solid #000;padding:6px;width:50%;vertical-align:top"><b>DESTINATARIO</b><br>{RECEPTOR}</td></tr>
      </table><br>
      <table style="width:100%;border-collapse:collapse;table-layout:fixed">
        <tr><td style="border:1px solid #000;padding:5px;width:75%"><b>Concepto</b></td><td style="border:1px solid #000;padding:5px;text-align:right;width:25%"><b>Importe</b></td></tr>
        <tr><td style="border:1px solid #000;padding:5px">{concepto}</td><td style="border:1px solid #000;padding:5px;text-align:right;white-space:nowrap">{eur(base)}</td></tr>
      </table><br>
      <table style="width:60%;margin-left:40%;border-collapse:collapse;table-layout:fixed">
        <tr><td style="padding:2px;width:60%">Base imponible</td><td style="text-align:right;white-space:nowrap">{eur(base)}</td></tr>
        <tr><td style="padding:2px">IVA (exento, art. 20.Uno.5º LIVA)</td><td style="text-align:right;white-space:nowrap">0,00 €</td></tr>
        {ret}
        <tr><td style="padding:4px 2px;border-top:1px solid #000"><b>{'Líquido a percibir' if irpf_pct>0 else 'TOTAL'}</b></td><td style="text-align:right;border-top:1px solid #000;padding-top:4px;white-space:nowrap"><b>{eur(liquido)}</b></td></tr>
      </table>
    </div>''')


def factura_generica(numero: str, fecha: str, emisor: str, emisor_nif: Optional[str],
                     concepto: str, total: float, iva_pct: float = 0.0, nota: str = "") -> bytes:
    numero, emisor, emisor_nif, concepto, nota = _esc(numero), _esc(emisor), _esc(emisor_nif), _esc(concepto), _esc(nota)
    base = round(total / (1 + iva_pct), 2) if iva_pct else total
    iva = round(total - base, 2)
    return _render(f'''
    <div style="font-family:sans-serif;font-size:11px;color:#000">
      <div style="text-align:center;font-size:16px;font-weight:bold;letter-spacing:2px;margin-bottom:12px">FACTURA</div>
      <table style="width:100%;border-collapse:collapse;table-layout:fixed">
        <tr><td style="border:1px solid #000;padding:6px;width:50%"><b>Nº Factura</b><br><span style="font-size:14px">{numero}</span></td>
            <td style="border:1px solid #000;padding:6px;width:50%"><b>Fecha</b><br>{fecha}</td></tr>
      </table><br>
      <table style="width:100%;border-collapse:collapse;table-layout:fixed">
        <tr><td style="border:1px solid #000;padding:6px;width:50%;vertical-align:top"><b>EMISOR</b><br>{emisor}<br>N.I.F. {emisor_nif or '(pendiente)'}</td>
            <td style="border:1px solid #000;padding:6px;width:50%;vertical-align:top"><b>DESTINATARIO</b><br>{RECEPTOR}</td></tr>
      </table><br>
      <table style="width:100%;border-collapse:collapse;table-layout:fixed">
        <tr><td style="border:1px solid #000;padding:5px;width:75%"><b>Concepto</b></td><td style="border:1px solid #000;padding:5px;text-align:right;width:25%"><b>Importe</b></td></tr>
        <tr><td style="border:1px solid #000;padding:5px">{concepto}</td><td style="border:1px solid #000;padding:5px;text-align:right;white-space:nowrap">{eur(base)}</td></tr>
      </table><br>
      <table style="width:60%;margin-left:40%;border-collapse:collapse;table-layout:fixed">
        <tr><td style="padding:2px;width:60%">Base imponible</td><td style="text-align:right;white-space:nowrap">{eur(base)}</td></tr>
        <tr><td style="padding:2px">IVA {int(iva_pct*100)}%</td><td style="text-align:right;white-space:nowrap">{eur(iva)}</td></tr>
        <tr><td style="padding:4px 2px;border-top:1px solid #000"><b>TOTAL</b></td><td style="text-align:right;border-top:1px solid #000;padding-top:4px;white-space:nowrap"><b>{eur(total)}</b></td></tr>
      </table>
      {f'<div style="margin-top:14px;font-size:9px;color:#666">{nota}</div>' if nota else ''}
    </div>''')
