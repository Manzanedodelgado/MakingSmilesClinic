#!/usr/bin/env python3
"""Grafo a nivel de COLUMNA: columnas como nodos, FK columna→columna como aristas."""
import json, math
from collections import defaultdict

cols = [l.rstrip("\n").split("\t") for l in open("/tmp/cols_20.tsv") if "\t" in l]
fks = [l.rstrip("\n").split("\t") for l in open("/tmp/fkcols_20.tsv") if "\t" in l]
counts = {a: int(b) for a, b in (l.rstrip("\n").split("\t") for l in open("/tmp/counts_20.tsv") if "\t" in l)}

def dom(t):
    if t in ("centros","razones_sociales","pacientes","colaboradores","citas","tratamientos","colaborador_centro","cita_tratamiento","tratamiento_fases","poblaciones","codigos_postales","dispositivos_paciente","especialidades","colaborador_especialidad"): return ("núcleo","#1c7ed6")
    if t.startswith(("tarifa","presupuesto","pago","cliente","paciente_tarifa","tratamientos_realizados")) or t in ("deudas","deuda_pago","clientes"): return ("económico","#2f9e44")
    if t.startswith(("alert","alerg","medic","imagen","hallazg","soap","odonto","periodonto","diagn","vademec","tipos_antece","subtipos_antece")): return ("clínico","#e8590c")
    if t.startswith(("agenda","gabinete","estados_cita","tipos_cita","colaborador_hor","colaborador_exc","bloqueo")): return ("agenda","#9c36b5")
    if t.startswith(("conversac","mensaje","recall","envio","integ")): return ("comunicación","#0ca678")
    if t.startswith(("receta","talon","documento","plantilla","consent")): return ("documentos","#f08c00")
    if t.startswith(("usuario","rol","permiso","platform","user_","sistema","area","password","auditoria","configurac")): return ("identidad/cfg","#e64980")
    if t.startswith(("gasto","proveed","liquidac")): return ("gestoría","#868e96")
    return ("otros","#adb5bd")

by_table = defaultdict(list)
for t, c in cols:
    by_table[t].append(c)

# columnas referenciadas (destino de FK) → más grandes
referenced = set(f"{r}.{rc}" for _, _, r, rc in fks)
fk_part = set()
for s, sc, r, rc in fks:
    fk_part.add(f"{s}.{sc}"); fk_part.add(f"{r}.{rc}")

nodes, edges = [], []
for t, clist in by_table.items():
    d, color = dom(t)
    for c in clist:
        nid = f"{t}.{c}"
        is_pk = (c == "id")
        is_ref = nid in referenced
        val = 14 if is_pk else (8 if is_ref else (4 if nid in fk_part else 2))
        nodes.append({"id": nid, "label": c, "group": t, "color": color, "value": val,
                      "title": f"{t}.{c}" + ("  [PK]" if is_pk else "") + (f"\\n{counts.get(t,0):,} filas" if is_pk else "")})
        # arista estructural columna→id de su tabla (clusteriza la tabla)
        if not is_pk and f"{t}.id" in (f"{t}.{x}" for x in clist):
            edges.append({"from": nid, "to": f"{t}.id", "color": {"color": "#2a3344", "opacity": 0.25}, "width": 0.3})
# aristas FK columna→columna (las interrelaciones entre tablas) — destacadas
for s, sc, r, rc in fks:
    edges.append({"from": f"{s}.{sc}", "to": f"{r}.{rc}",
                  "color": {"color": "#4dd4ff", "opacity": 0.9}, "width": 1.6,
                  "arrows": {"to": {"enabled": True, "scaleFactor": 0.5}},
                  "title": f"{s}.{sc} → {r}.{rc}"})

html = """<!doctype html><html lang=es><head><meta charset=utf-8>
<title>MakingSmiles 2.0 — relaciones por COLUMNA</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>html,body{margin:0;height:100%;background:#0b1020;color:#e9ecef;font-family:system-ui}
#net{width:100%;height:100vh}#hud{position:fixed;top:10px;left:10px;background:#11182fcc;padding:10px 14px;border-radius:8px;font-size:13px;z-index:9;max-width:320px}
b{color:#4dabf7} input{padding:5px 9px;border-radius:6px;border:1px solid #2a3756;background:#1a2238;color:#fff}
label{font-size:12px}</style></head><body>
<div id=hud><b>MakingSmiles 2.0</b> · __NC__ columnas · __NF__ FK columna→columna
<br><input id=q placeholder="buscar tabla.columna…" oninput="f(this.value)">
<br><label><input type=checkbox id=onlyfk onchange="toggle()"> solo columnas con relación FK</label>
<br><span style="font-size:11px"><span style="color:#4dd4ff">━</span> FK entre tablas &nbsp; <span style="color:#2a3344">━</span> columna→PK</span></div>
<div id=net></div><script>
const ALL=__NODES__, ALLE=__EDGES__, FKP=new Set(__FKPART__);
let nodes=new vis.DataSet(ALL), edges=new vis.DataSet(ALLE);
const net=new vis.Network(document.getElementById('net'),{nodes,edges},{
 nodes:{shape:'dot',scaling:{min:3,max:30},font:{color:'#cdd6f4',size:10}},
 edges:{smooth:false},
 physics:{stabilization:{iterations:300},barnesHut:{gravitationalConstant:-7000,springLength:90,springConstant:0.02,avoidOverlap:0.1}},
 interaction:{hover:true,tooltipDelay:80}});
function f(v){v=v.toLowerCase().trim();if(!v)return;const h=ALL.find(n=>n.id.toLowerCase().includes(v));if(h){net.selectNodes([h.id]);net.focus(h.id,{scale:1.4,animation:true});}}
function toggle(){const on=document.getElementById('onlyfk').checked;
 if(on){nodes=new vis.DataSet(ALL.filter(n=>FKP.has(n.id)));edges=new vis.DataSet(ALLE.filter(e=>e.color&&e.color.color==='#4dd4ff'));}
 else{nodes=new vis.DataSet(ALL);edges=new vis.DataSet(ALLE);}
 net.setData({nodes,edges});}
</script></body></html>"""
html = (html.replace("__NODES__", json.dumps(nodes, ensure_ascii=False))
            .replace("__EDGES__", json.dumps(edges, ensure_ascii=False))
            .replace("__FKPART__", json.dumps(sorted(fk_part)))
            .replace("__NC__", str(len(nodes))).replace("__NF__", str(len(fks))))
open("/home/jmd/MakingSmiles_Studio/modelo20_columnas.html", "w", encoding="utf-8").write(html)
print("grafo columnas →", len(nodes), "nodos,", len(edges), "aristas (", len(fks), "FK columna→columna )")
