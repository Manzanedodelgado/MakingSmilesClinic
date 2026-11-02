#!/usr/bin/env python3
"""Grafo HTML interactivo del modelo 2.0 (tablas + FKs reales + nº de filas)."""
import json
from collections import defaultdict

fks = [l.split("\t") for l in open("/tmp/fks_20.tsv") if "\t" in l]
counts = {a: int(b) for a, b in (l.rstrip("\n").split("\t") for l in open("/tmp/counts_20.tsv") if "\t" in l)}

# dominio por prefijo/nombre (color)
def dom(t):
    if t in ("centros","razones_sociales","pacientes","colaboradores","citas","tratamientos","colaborador_centro","cita_tratamiento","tratamiento_fases","poblaciones","codigos_postales","dispositivos_paciente","especialidades","colaborador_especialidad"): return ("núcleo","#1c7ed6")
    if t.startswith(("tarifa","presupuesto","pago","cliente","paciente_tarifa","tratamientos_realizados")) or t in ("deudas","deuda_pago","clientes"): return ("económico","#2f9e44")
    if t.startswith(("alert","alerg","medic","imagen","hallazg","soap","odonto","periodonto","diagn","vademec","tipos_antece","subtipos_antece")): return ("clínico","#e8590c")
    if t.startswith(("agenda","gabinete","estados_cita","tipos_cita","colaborador_hor","colaborador_exc","bloqueo")): return ("agenda","#9c36b5")
    if t.startswith(("conversac","mensaje","recall","envio","integ")): return ("comunicación","#0ca678")
    if t.startswith(("receta","talon","documento","plantilla","consent")): return ("documentos","#f08c00")
    if t.startswith(("usuario","rol","permiso","platform","user_","sistema","area","password","auditoria","configurac")): return ("identidad/cfg","#e64980")
    if t.startswith(("gasto","proveed","liquidac")): return ("gestoría","#495057")
    return ("otros","#adb5bd")

deg = defaultdict(int)
edges = []
for a, b in fks:
    if a == b: continue
    deg[a] += 1; deg[b] += 1
    edges.append({"from": a, "to": b})

nodes = []
maxr = max(counts.values()) or 1
import math
for t, n in counts.items():
    d, color = dom(t)
    val = max(1, round(40 * math.log10(n + 1) / math.log10(maxr + 1))) if n else 1
    nodes.append({"id": t, "label": t, "value": val, "color": color, "group": d,
                  "title": f"{t}\\ndominio: {d}\\nfilas: {n:,}\\nrelaciones: {deg.get(t,0)}"})

doms = sorted(set(dom(t)[0] for t in counts))
colors = {dom(t)[0]: dom(t)[1] for t in counts}
legend = " ".join(f'<span style="color:{colors[d]}">●</span>{d}' for d in doms)

html = """<!doctype html><html lang=es><head><meta charset=utf-8>
<title>MakingSmiles 2.0 — modelo de datos</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>html,body{margin:0;height:100%;background:#0b1020;color:#e9ecef;font-family:system-ui}
#net{width:100%;height:100vh}#hud{position:fixed;top:10px;left:10px;background:#11182fcc;padding:10px 14px;border-radius:8px;font-size:13px;z-index:9}
b{color:#4dabf7} input{padding:5px 9px;border-radius:6px;border:1px solid #2a3756;background:#1a2238;color:#fff}</style></head><body>
<div id=hud><b>MakingSmiles 2.0</b> · __NT__ tablas · __NE__ FKs · datos reales<br>
<input id=q placeholder="buscar tabla…" oninput="f(this.value)"><br><span style="font-size:11px">__LEG__</span></div>
<div id=net></div><script>
const nodes=new vis.DataSet(__NODES__), edges=new vis.DataSet(__EDGES__);
const net=new vis.Network(document.getElementById('net'),{nodes,edges},{
 nodes:{shape:'dot',scaling:{min:6,max:55},font:{color:'#dfe6f3',size:12}},
 edges:{color:{color:'#3a4a6a',opacity:0.4},width:0.6,arrows:{to:{enabled:true,scaleFactor:0.4}},smooth:false},
 physics:{stabilization:{iterations:250},barnesHut:{gravitationalConstant:-9000,springLength:130,springConstant:0.02}},
 interaction:{hover:true,tooltipDelay:100}});
function f(v){v=v.toLowerCase().trim();if(!v)return;const h=nodes.get().find(n=>n.id.toLowerCase().includes(v));if(h){net.selectNodes([h.id]);net.focus(h.id,{scale:1.3,animation:true});}}
</script></body></html>"""
html = (html.replace("__NODES__", json.dumps(nodes, ensure_ascii=False))
            .replace("__EDGES__", json.dumps(edges, ensure_ascii=False))
            .replace("__NT__", str(len(nodes))).replace("__NE__", str(len(edges)))
            .replace("__LEG__", legend))
open("/home/jmd/MakingSmiles_Studio/modelo20_graph.html", "w", encoding="utf-8").write(html)
print("grafo →", "modelo20_graph.html", "·", len(nodes), "nodos", len(edges), "aristas")
