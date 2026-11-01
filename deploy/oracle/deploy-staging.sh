#!/usr/bin/env bash
# ============================================================================
# deploy-staging.sh — despliegue/rollback de la API en el servidor Oracle.
# Lo invoca el wrapper root /usr/local/sbin/makingsmiles-deploy (sudo acotado,
# ver bootstrap-oracle.sh) desde GitHub Actions; también se puede usar a mano
# como root. NUNCA desde el portátil: necesita el proyecto compose vivo.
#
# Uso:
#   ./deploy-staging.sh ghcr.io/OWNER/repo-api:<sha>   desplegar imagen
#   ./deploy-staging.sh --rollback                     volver a la anterior
#   ./deploy-staging.sh --dry-run [<imagen>]           enseñar el plan
#   ./deploy-staging.sh <imagen> --reload-caddy        + recargar Caddy
#
# Estado en $APP_DIR/.deploy/ (DOS slots + historial, nunca se pisa el anterior
# con la imagen mala):
#   current_image   imagen que está sirviendo
#   previous_image  imagen anterior sana (destino de --rollback)
#   history.log     una línea por operación con resultado
#
# Garantías:
#   - El estado solo se escribe TRAS un deploy sano.
#   - Si el healthcheck de la imagen nueva falla, se vuelve sola a la imagen que
#     estaba sirviendo y el estado queda como estaba (previous_image intacto).
#   - En --rollback NO se toca previous_image antes de aplicar; al terminar bien
#     se intercambian los slots (previous pasa a ser la que se acaba de dejar).
# ============================================================================
set -euo pipefail
umask 077

APP_DIR="${APP_DIR:-/opt/makingsmiles}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
STATE_DIR="$APP_DIR/.deploy"
CURRENT_FILE="$STATE_DIR/current_image"
PREV_FILE="$STATE_DIR/previous_image"
DEPLOY_LOG="$STATE_DIR/history.log"
HEALTH_RETRIES="${HEALTH_RETRIES:-36}"
MODE="deploy"; DRY_RUN=0; RELOAD_CADDY=0; IMAGE_REF=""

for arg in "$@"; do
  case "$arg" in
    --rollback) MODE="rollback" ;;
    --dry-run) DRY_RUN=1 ;;
    --reload-caddy) RELOAD_CADDY=1 ;;
    -h|--help) sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "ERROR: opción desconocida: $arg" >&2; exit 1 ;;
    *) [ -z "$IMAGE_REF" ] || { echo "ERROR: sobra '$arg'" >&2; exit 1; }; IMAGE_REF="$arg" ;;
  esac
done

log() { printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }
compose() { docker compose --project-directory "$APP_DIR" "$@"; }
image_in_env() { awk -F= '/^API_IMAGE=/{sub(/^API_IMAGE=/,""); print; exit}' "$ENV_FILE"; }
set_image_in_env() {
  local img="$1" tmp
  tmp="$(mktemp "$ENV_FILE.XXXXXX")"
  awk -v img="$img" 'BEGIN{done=0} /^API_IMAGE=/{print "API_IMAGE=" img; done=1; next} {print} END{if(!done) print "API_IMAGE=" img}' "$ENV_FILE" > "$tmp"
  chmod 600 "$tmp"; mv "$tmp" "$ENV_FILE"
}
slot() { local f="$1"; [ -s "$f" ] && awk 'NR==1{print $1}' "$f" || true; }
record_state() { local img="$1" old="$2" action="$3" result="$4"
  printf '%s %s\n' "$img" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" > "$CURRENT_FILE"
  [ -n "$old" ] && [ "$old" != "$img" ] && printf '%s %s\n' "$old" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" > "$PREV_FILE"
  printf '%s action=%s from=%s to=%s result=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$action" "$old" "$img" "$result" >> "$DEPLOY_LOG"
}
wait_healthy() { local i
  for i in $(seq 1 "$HEALTH_RETRIES"); do
    if compose exec -T api curl -fsS -m 3 http://127.0.0.1:8000/health/db >/dev/null 2>&1; then
      log "health OK tras $((i*5))s"; return 0
    fi
    sleep 5
  done; return 1
}
caddy_reload() {
  compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 \
    && log "Caddyfile recargado" || log "AVISO: no se pudo recargar Caddy (¿Caddyfile inválido? se mantiene el anterior)"
}

[ -f "$ENV_FILE" ] || die "no existe $ENV_FILE"
[ -f "$APP_DIR/docker-compose.yml" ] || die "no existe $APP_DIR/docker-compose.yml"
mkdir -p "$STATE_DIR"

# Rechaza placeholders y secretos débiles ANTES de tocar nada. El validador es la
# copia root-owned que instala el bootstrap (no el fichero escribible de /opt).
VALIDATE_SCRIPT="${VALIDATE_SCRIPT:-/usr/local/lib/makingsmiles/validate-env.sh}"
[ -x "$VALIDATE_SCRIPT" ] || VALIDATE_SCRIPT="$APP_DIR/validate-env.sh"
# El estado del backup offsite se avisa pero no bloquea un deploy de la API.
bash "$VALIDATE_SCRIPT" --allow-incomplete-backup "$ENV_FILE" \
  || die "el .env no pasa la validación: corrige los placeholders/secretos antes de desplegar"
if [ "${BACKUP_OFFSITE_REQUIRED:-0}" = "1" ] && { [ -z "${BACKUP_DEST:-}" ] || [ -z "${BACKUP_AGE_RECIPIENT:-}" ]; }; then
  log "AVISO: copia fuera del host INCOMPLETA (BACKUP_DEST/BACKUP_AGE_RECIPIENT). El timer fallará (exit 2)."
fi

CURRENT_ENV="$(image_in_env)"
[ -n "$CURRENT_ENV" ] || die "API_IMAGE no está definido en $ENV_FILE"
CURRENT_STATE="$(slot "$CURRENT_FILE")"; CURRENT_STATE="${CURRENT_STATE:-$CURRENT_ENV}"
PREV_STATE="$(slot "$PREV_FILE")"

if [ "$MODE" = "rollback" ]; then
  [ -n "$PREV_STATE" ] || die "no hay imagen anterior registrada en $PREV_FILE (nada que revertir)"
  TARGET="$PREV_STATE"
else
  TARGET="${IMAGE_REF:-$CURRENT_ENV}"
fi
printf '%s' "$TARGET" | grep -Eq '^ghcr\.io/[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9._-]+$' \
  || die "referencia de imagen no válida: '$TARGET'"
[ -n "$PREV_STATE" ] && printf '%s' "$PREV_STATE" | grep -Eq '^ghcr\.io/[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9._-]+$' \
  || { [ "$MODE" = "rollback" ] && die "previous_image corrupta: '$PREV_STATE'" || true; }

if [ "$DRY_RUN" -eq 1 ]; then
  log "DRY-RUN (no se cambia nada)"
  printf '  APP_DIR          : %s\n' "$APP_DIR"
  printf '  imagen en .env   : %s\n' "$CURRENT_ENV"
  printf '  current_image    : %s\n' "$CURRENT_STATE"
  printf '  previous_image   : %s\n' "${PREV_STATE:-<ninguna>}"
  printf '  imagen objetivo  : %s (%s)\n' "$TARGET" "$MODE"
  printf '  pasos            : validar env -> pull -> up -d --no-deps api -> health /health/db (%ss)\n' "$((HEALTH_RETRIES*5))"
  printf '  estado solo se escribe si el health check pasa; si falla, vuelve a %s\n' "$CURRENT_STATE"
  printf '  caddy reload     : %s\n' "$RELOAD_CADDY"
  compose config --services >/dev/null 2>&1 && log "DRY-RUN OK: compose responde" || log "AVISO: 'compose config' no responde"
  exit 0
fi

log "deploy: current=$CURRENT_STATE previous=${PREV_STATE:-<ninguna>} objetivo=$TARGET modo=$MODE"

restore_previous() {
  log "volviendo a la imagen que estaba sirviendo: $CURRENT_STATE"
  set_image_in_env "$CURRENT_STATE"
  compose pull --quiet api || true
  compose up -d --no-deps api
  wait_healthy && { log "servicio restaurado con $CURRENT_STATE"; return 0; }
  return 1
}

TARGET_DIRTY=0
trap 'if [ "$TARGET_DIRTY" = "1" ]; then restore_previous || true; fi' ERR

set_image_in_env "$TARGET"
TARGET_DIRTY=1
if ! compose pull --quiet api; then
  log "no se pudo descargar $TARGET (¿login GHCR? ¿tag inexistente?)"
  record_state "$CURRENT_STATE" "$PREV_STATE" "$MODE" "FAIL_PULL target=$TARGET"
  restore_previous || true
  exit 1
fi
compose up -d --no-deps api

if ! wait_healthy; then
  log "la imagen $TARGET NO está sana"
  compose logs --tail=80 api >&2 || true
  record_state "$CURRENT_STATE" "$PREV_STATE" "$MODE" "FAIL_HEALTH target=$TARGET"
  restore_previous || { log "ERROR: tampoco se pudo restaurar $CURRENT_STATE"; exit 1; }
  TARGET_DIRTY=0
  exit 1
fi

# Solo aquí se considera bueno: se actualizan los dos slots.
record_state "$TARGET" "$CURRENT_STATE" "$MODE" "OK"
TARGET_DIRTY=0
[ "$RELOAD_CADDY" -eq 1 ] && caddy_reload
log "OK: $TARGET (anterior sano: $CURRENT_STATE)"
exit 0
