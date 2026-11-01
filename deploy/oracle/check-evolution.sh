#!/usr/bin/env bash
# ============================================================================
# check-evolution.sh — comprueba la SESIÓN REAL de WhatsApp, no solo que la API
# de Evolution responda.
#
# Consulta /instance/fetchInstances (autenticado con AUTHENTICATION_API_KEY, que
# vive dentro del contenedor) y muestra el connectionStatus de cada instancia.
#
# Códigos:
#   0  API responde y (no hay instancias todavía  o  alguna está 'open')
#   2  API responde, hay instancias, pero NINGUNA está 'open' (WhatsApp caído /
#      pendiente de emparejar: es un diagnóstico, no un fallo del deploy)
#   1  la API de Evolution no responde o devuelve error
#
# Uso: ./check-evolution.sh            (lee /opt/makingsmiles/.env)
# ============================================================================
set -euo pipefail
APP_DIR="${APP_DIR:-/opt/makingsmiles}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
[ -f "$ENV_FILE" ] || { echo "ERROR: no existe $ENV_FILE" >&2; exit 1; }
set -a; . "$ENV_FILE"; set +a
compose() { docker compose --project-directory "$APP_DIR" "$@"; }

JSON="$(compose exec -T evolution node -e '
const http=require("http");
const req=http.request({host:"127.0.0.1",port:8080,path:"/instance/fetchInstances",
  headers:{apikey:process.env.AUTHENTICATION_API_KEY||""}},res=>{
  let b="";res.on("data",d=>b+=d);
  res.on("end",()=>{ if(res.statusCode!==200){process.stderr.write("HTTP "+res.statusCode+"\n");process.exit(1)} process.stdout.write(b); });
});
req.on("error",e=>{process.stderr.write(String(e)+"\n");process.exit(1)});
req.end();' 2>/dev/null)" || { echo "EVOLUTION: la API no responde o rechaza la apikey" >&2; exit 1; }

printf '%s' "$JSON" | python3 -c '
import json,sys
data=json.load(sys.stdin)
inst=data if isinstance(data,list) else [data]
if not inst:
    print("EVOLUTION OK: API responde; no hay instancias creadas todavía (sin sesión de WhatsApp)")
    sys.exit(0)
estados=[]
for i in inst:
    name=i.get("name") or i.get("instanceName") or i.get("instance",{}).get("instanceName") or "?"
    st=i.get("connectionStatus") or i.get("instance",{}).get("state") or i.get("state") or "?"
    estados.append((name,st))
    print(f"  instancia={name} connectionStatus={st}")
if any(st=="open" for _,st in estados):
    print("EVOLUTION OK: al menos una instancia tiene sesión de WhatsApp abierta")
    sys.exit(0)
print("EVOLUTION: hay instancias pero NINGUNA con connectionStatus=open (revisar emparejamiento/QR)", file=sys.stderr)
sys.exit(2)
'
