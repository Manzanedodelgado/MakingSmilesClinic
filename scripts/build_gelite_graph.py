#!/usr/bin/env python3
"""Genera un grafo HTML interactivo de relaciones GELITE desde la extracción JSON.

Lee tables.json + foreign_keys.json + columns.json de la extracción y emite un
HTML autocontenido (vis-network por CDN). Nodo = tabla; arista = FK.
Tamaño/color del nodo por GRADO (nº de relaciones); tooltip con filas y columnas.

Uso: python3 scripts/build_gelite_graph.py [extract_dir] [out.html]
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "gelite-extract-20260618"
out = Path(sys.argv[2]) if len(sys.argv) > 2 else base / "gelite_relaciones.html"

tables = json.loads((base / "tables.json").read_text(encoding="utf-8"))
fks = json.loads((base / "foreign_keys.json").read_text(encoding="utf-8"))
columns = json.loads((base / "columns.json").read_text(encoding="utf-8"))

rows_by = {t["tbl"]: (t["rows"] or 0) for t in tables}
cols_by = defaultdict(int)
for c in columns:
    cols_by[c["tbl"]] += 1

# Grado por nº de FKs entrantes+salientes (relaciones distintas tabla↔tabla)
degree = defaultdict(int)
edge_set = set()
for f in fks:
    a, b = f["parent_tbl"], f["ref_tbl"]
    if a == b:
        continue
    key = tuple(sorted((a, b)))
    if key not in edge_set:
        edge_set.add(key)
        degree[a] += 1
        degree[b] += 1

def color(d):
    if d >= 40: return "#b21f35"   # hub fuerte
    if d >= 15: return "#e8590c"
    if d >= 6:  return "#f08c00"
    if d >= 1:  return "#1c7ed6"
    return "#adb5bd"               # tabla suelta (sin FK)

nodes = []
for t in tables:
    name = t["tbl"]
    d = degree.get(name, 0)
    nodes.append({
        "id": name, "label": name,
        "value": max(d, 1),
        "color": color(d),
        "title": f"{name}\\nfilas: {rows_by.get(name,0):,}\\ncolumnas: {cols_by.get(name,0)}\\nrelaciones: {d}",
    })

edges = [{"from": a, "to": b} for (a, b) in edge_set]

html = """<!doctype html><html lang=es><head><meta charset=utf-8>
<title>GELITE — relaciones (extracción 2026-06-18)</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
 html,body{margin:0;height:100%;background:#0b1020;color:#e9ecef;font-family:system-ui}
 #net{width:100%;height:100vh}
 #hud{position:fixed;top:10px;left:10px;background:#11182fcc;padding:10px 14px;border-radius:8px;font-size:13px;z-index:10}
 #hud b{color:#4dabf7} input{padding:4px 8px;border-radius:5px;border:1px solid #333;background:#1a2238;color:#fff}
 .lg{display:inline-block;width:11px;height:11px;border-radius:50%;margin:0 3px 0 8px;vertical-align:middle}
</style></head><body>
<div id=hud>
 <b>GELITE</b> · __NT__ tablas · __NE__ relaciones (FK)
 <br><input id=q placeholder="buscar tabla…" oninput="find(this.value)" autocomplete=off>
 <br><span style="font-size:11px">grado:
   <span class=lg style="background:#b21f35"></span>40+
   <span class=lg style="background:#e8590c"></span>15+
   <span class=lg style="background:#f08c00"></span>6+
   <span class=lg style="background:#1c7ed6"></span>1+
   <span class=lg style="background:#adb5bd"></span>0</span>
</div>
<div id=net></div>
<script>
const nodes=new vis.DataSet(__NODES__);
const edges=new vis.DataSet(__EDGES__);
const net=new vis.Network(document.getElementById('net'),{nodes,edges},{
 nodes:{shape:'dot',scaling:{min:6,max:60},font:{color:'#dfe6f3',size:12}},
 edges:{color:{color:'#3a4straat',opacity:0.35},width:0.5,smooth:false,arrows:{to:{enabled:true,scaleFactor:0.4}}},
 physics:{stabilization:{iterations:200},barnesHut:{gravitationalConstant:-8000,springLength:120,springConstant:0.02}},
 interaction:{hover:true,tooltipDelay:120}
});
function find(v){v=v.toLowerCase().trim();if(!v)return;
 const hit=nodes.get().find(n=>n.id.toLowerCase().includes(v));
 if(hit){net.selectNodes([hit.id]);net.focus(hit.id,{scale:1.2,animation:true});}}
</script></body></html>"""

html = (html.replace("__NODES__", json.dumps(nodes, ensure_ascii=False))
            .replace("__EDGES__", json.dumps(edges, ensure_ascii=False))
            .replace("__NT__", str(len(nodes)))
            .replace("__NE__", str(len(edges))))
# fix typo placeholder color
html = html.replace("#3a4straat", "#3a4a6a")
out.write_text(html, encoding="utf-8")
print("GRAFO HTML →", out)
print(f"  nodos: {len(nodes)}  aristas: {len(edges)}")
