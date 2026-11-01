#!/usr/bin/env bash
# ============================================================================
# backup-postgres.sh — copia de Postgres (+ media) con verificación, retención,
# cifrado en reposo y copia FUERA del host.
#
# Uso:
#   ./backup-postgres.sh              copia real (verifica todo antes de salir 0)
#   ./backup-postgres.sh --dry-run    enseña qué haría, sin escribir nada
#   ./backup-postgres.sh --verify     valida la ÚLTIMA copia (checksum + pg_restore)
#
# Variables (en $APP_DIR/.env o entorno):
#   POSTGRES_USER POSTGRES_DB BACKUP_DIR BACKUP_RETENTION_DAYS
#   BACKUP_DEST BACKUP_SSH_KEY BACKUP_KNOWN_HOSTS BACKUP_AGE_RECIPIENT
#   BACKUP_OFFSITE_REQUIRED BACKUP_MEDIA
#
# Salidas: 0 OK · 1 error local (incl. media si BACKUP_MEDIA=1) · 2 fallo de la
# copia fuera del host siendo obligatoria (systemd lo marca failed).
#
# Diseño:
#   - El lock vive en $APP_DIR/.deploy/backup.lock (escribible por el usuario del
#     timer); NO en /run, que es root:root y mataba el script.
#   - pg_dump -Fc comprimido + globals + evolution + media (si BACKUP_MEDIA=1).
#     Si el tar de media falla, la copia es FALLO (no se ignora).
#   - Verificación en CADA copia: sha256 + `pg_restore --list` (integridad real).
#   - Offsite: se cifra con `age` a $BACKUP_DIR/offsite/ y se espeja con
#     rsync --delete a un directorio DEDICADO; known_hosts fijado (no accept-new).
#   - Un backup que nunca se ha restaurado no es un backup:
#     restore-postgres.sh --scratch es la prueba en seco.
# ============================================================================
set -euo pipefail
umask 077

APP_DIR="${APP_DIR:-/opt/makingsmiles}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
LOCK_FILE="${LOCK_FILE:-$APP_DIR/.deploy/backup.lock}"
MODE="backup"
DRY_RUN=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --verify) MODE="verify" ;;
    -h|--help) sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "ERROR: argumento desconocido: $arg" >&2; exit 1 ;;
  esac
done

log() { printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"; }
err() { log "ERROR: $*" >&2; }
notify_syslog() { command -v logger >/dev/null 2>&1 && logger -t makingsmiles-backup -- "$*" || true; }

[ -d "$APP_DIR" ] || { err "no existe APP_DIR=$APP_DIR"; exit 1; }
[ -f "$ENV_FILE" ] || { err "no existe $ENV_FILE"; exit 1; }
set -a; . "$ENV_FILE"; set +a
: "${POSTGRES_USER:?falta POSTGRES_USER}"
: "${POSTGRES_DB:?falta POSTGRES_DB}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
BACKUP_OFFSITE_REQUIRED="${BACKUP_OFFSITE_REQUIRED:-1}"
BACKUP_MEDIA="${BACKUP_MEDIA:-1}"
BACKUP_DEST="${BACKUP_DEST:-}"
BACKUP_SSH_KEY="${BACKUP_SSH_KEY:-$APP_DIR/.ssh/backup_key}"
BACKUP_KNOWN_HOSTS="${BACKUP_KNOWN_HOSTS:-$APP_DIR/.ssh/known_hosts}"
BACKUP_AGE_RECIPIENT="${BACKUP_AGE_RECIPIENT:-}"
STAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
DB_FILE="$BACKUP_DIR/makingsmiles-db-$STAMP.dump"
GLOBALS_FILE="$BACKUP_DIR/makingsmiles-globals-$STAMP.sql"
EVOLUTION_FILE="$BACKUP_DIR/makingsmiles-evolution-$STAMP.dump"
MEDIA_FILE="$BACKUP_DIR/makingsmiles-media-$STAMP.tar.gz"
OFFSITE_DIR="$BACKUP_DIR/offsite"
COMPOSE=(docker compose --project-directory "$APP_DIR")

compose() { "${COMPOSE[@]}" "$@"; }
sha_check() { ( cd "$(dirname "$1")" && sha256sum -c "$(basename "$1").sha256" ); }
pg_restore_list_ok() { compose exec -T postgres pg_restore --list < "$1" >/dev/null 2>&1; }

latest_db() { ls -1t "$BACKUP_DIR"/makingsmiles-db-*.dump 2>/dev/null | head -n1; }

verify_dump() {
  local f="$1" what="$2"
  [ -s "$f" ] || { err "$what vacío: $f"; return 1; }
  [ -f "$f.sha256" ] || { err "$what sin .sha256"; return 1; }
  sha_check "$f" >/dev/null || { err "$what checksum NO coincide"; return 1; }
  pg_restore_list_ok "$f" || { err "$what pg_restore --list falla (dump corrupto)"; return 1; }
  log "$what OK (checksum + pg_restore --list)"
}

# --- --verify: comprobar la última copia sin restaurar ----------------------
if [ "$MODE" = "verify" ]; then
  DB="$(latest_db || true)"
  [ -n "$DB" ] || { err "no hay copias en $BACKUP_DIR"; exit 1; }
  log "verificando $DB"
  verify_dump "$DB" "dump app" || exit 1
  EVO="${DB/makingsmiles-db-/makingsmiles-evolution-}"; EVO="${EVO%.dump}.dump"
  [ -s "$EVO" ] && { verify_dump "$EVO" "dump evolution" || exit 1; } || log "sin dump de evolution"
  GLOB="${DB/makingsmiles-db-/makingsmiles-globals-}"; GLOB="${GLOB%.dump}.sql"
  [ -s "$GLOB" ] && log "globals OK ($(wc -l < "$GLOB") líneas)" || err "falta globals"
  log "VERIFY OK. Prueba de restauración completa: restore-postgres.sh --scratch"
  exit 0
fi

# --- --dry-run --------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  log "DRY-RUN: no se escribe nada"
  printf '  destino local     : %s\n' "$BACKUP_DIR"
  printf '  lock              : %s\n' "$LOCK_FILE"
  printf '  dump app          : %s\n' "$DB_FILE"
  printf '  media             : %s (BACKUP_MEDIA=%s, fatal si falla)\n' "$MEDIA_FILE" "$BACKUP_MEDIA"
  printf '  retención         : %s días\n' "$BACKUP_RETENTION_DAYS"
  printf '  offsite           : %s\n' "${BACKUP_DEST:-<sin definir>}"
  printf '  offsite requerido : %s\n' "$BACKUP_OFFSITE_REQUIRED"
  printf '  cifrado age       : %s\n' "${BACKUP_AGE_RECIPIENT:+configurado}${BACKUP_AGE_RECIPIENT:-NO configurado}"
  printf '  ssh key/known_hosts: %s / %s\n' "$BACKUP_SSH_KEY" "$BACKUP_KNOWN_HOSTS"
  command -v docker >/dev/null || { err "docker no está en PATH"; exit 1; }
  compose ps >/dev/null 2>&1 || { err "no se puede hablar con el proyecto compose en $APP_DIR"; exit 1; }
  command -v age >/dev/null 2>&1 || log "AVISO: 'age' no está instalado (necesario para offsite)"
  log "DRY-RUN OK: el stack responde"
  exit 0
fi

# --- copia real -------------------------------------------------------------
mkdir -p "$BACKUP_DIR" "$(dirname "$LOCK_FILE")" "$OFFSITE_DIR"
exec 9>"$LOCK_FILE"
flock -n 9 || { err "ya hay una copia en curso (lock $LOCK_FILE)"; exit 1; }

# Offsite obligatorio: fallar ANTES de gastar tiempo si falta algo.
if [ -n "$BACKUP_DEST" ] || [ "$BACKUP_OFFSITE_REQUIRED" = "1" ]; then
  [ -n "$BACKUP_DEST" ] || { err "BACKUP_OFFSITE_REQUIRED=1 y BACKUP_DEST vacío"; exit 2; }
  [ -n "$BACKUP_AGE_RECIPIENT" ] || { err "falta BACKUP_AGE_RECIPIENT (cifrado en reposo obligatorio antes del offsite)"; exit 2; }
  command -v age >/dev/null 2>&1 || { err "falta el binario age para cifrar la copia offsite"; exit 2; }
  [ -r "$BACKUP_SSH_KEY" ] || { err "BACKUP_SSH_KEY no legible: $BACKUP_SSH_KEY"; exit 2; }
  [ -r "$BACKUP_KNOWN_HOSTS" ] || { err "BACKUP_KNOWN_HOSTS no legible: $BACKUP_KNOWN_HOSTS"; exit 2; }
fi
log "inicio de copia $STAMP"
FREE_MB=$(df -Pm "$BACKUP_DIR" | awk 'NR==2{print $4}')
[ "$FREE_MB" -ge 2048 ] || log "AVISO: solo ${FREE_MB}MB libres en $BACKUP_DIR"
compose ps --status running --services | grep -qx postgres || { err "el contenedor postgres no está corriendo"; exit 1; }

log "pg_dump $POSTGRES_DB (-Fc)"
compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$DB_FILE"
log "pg_dump evolution (-Fc)"
if compose exec -T postgres psql -U "$POSTGRES_USER" -d postgres -tAc \
     "SELECT 1 FROM pg_database WHERE datname='evolution'" 2>/dev/null | grep -qx 1; then
  compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d evolution -Fc > "$EVOLUTION_FILE"
else
  log "AVISO: la base 'evolution' no existe todavía; no se copia"
  EVOLUTION_FILE=""
fi
log "roles/globals"
compose exec -T postgres pg_dumpall -U "$POSTGRES_USER" --globals-only > "$GLOBALS_FILE"

if [ "$BACKUP_MEDIA" = "1" ]; then
  log "media (/app/media desde el contenedor api)"
  if ! compose exec -T api tar -czf - -C /app media > "$MEDIA_FILE" 2>/dev/null; then
    rm -f "$MEDIA_FILE"
    err "BACKUP_MEDIA=1 y el tar de media falló: la copia se considera FALLIDA"
    notify_syslog "backup FAIL media"
    exit 1
  fi
  log "media OK ($(du -m "$MEDIA_FILE" 2>/dev/null | awk '{print $1}') MB)"
fi

for f in "$DB_FILE" "$EVOLUTION_FILE" "$GLOBALS_FILE"; do
  [ -n "$f" ] || continue
  [ -s "$f" ] || { err "$f vacío: copia abortada"; exit 1; }
  ( cd "$(dirname "$f")" && sha256sum "$(basename "$f")" > "$(basename "$f").sha256" )
done
[ -f "$MEDIA_FILE" ] && ( cd "$BACKUP_DIR" && sha256sum "$(basename "$MEDIA_FILE")" > "$(basename "$MEDIA_FILE").sha256" )

# Verificación obligatoria EN CADA COPIA (no solo con --verify).
verify_dump "$DB_FILE" "dump app" || exit 1
[ -n "$EVOLUTION_FILE" ] && { verify_dump "$EVOLUTION_FILE" "dump evolution" || exit 1; }
[ -s "$GLOBALS_FILE" ] || { err "globals vacío"; exit 1; }
log "copias locales verificadas"

# Retención local (incluye offsite/; el remoto se espeja con --delete).
DELETED=$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'makingsmiles-*' -mtime +"$BACKUP_RETENTION_DAYS" -print -delete | wc -l | tr -d ' ')
DELETED_OFF=$(find "$OFFSITE_DIR" -maxdepth 1 -type f -mtime +"$BACKUP_RETENTION_DAYS" -print -delete | wc -l | tr -d ' ')
log "retención: $DELETED local + $DELETED_OFF cifrados con más de $BACKUP_RETENTION_DAYS días borrados"

# Offsite: cifrar con age y espejar.
if [ -n "$BACKUP_DEST" ]; then
  log "cifrando con age (recipient=${BACKUP_AGE_RECIPIENT:0:16}...)"
  rm -f "$OFFSITE_DIR"/*.age 2>/dev/null || true
  for f in "$DB_FILE" "$EVOLUTION_FILE" "$GLOBALS_FILE" "$MEDIA_FILE"; do
    [ -n "$f" ] && [ -f "$f" ] || continue
    age -r "$BACKUP_AGE_RECIPIENT" -o "$OFFSITE_DIR/$(basename "$f").age" "$f" \
      || { err "age falló cifrando $f"; exit 2; }
  done
  [ -s "$OFFSITE_DIR/$(basename "$DB_FILE").age" ] || { err "no se generó el cifrado del dump"; exit 2; }
  log "copia FUERA del host -> $BACKUP_DEST (--delete: espejo de la retención)"
  RSYNC_SSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$BACKUP_KNOWN_HOSTS -o ConnectTimeout=20 -i $BACKUP_SSH_KEY"
  if rsync -az --delete --delete-after --timeout=300 -e "$RSYNC_SSH" "$OFFSITE_DIR/" "$BACKUP_DEST/"; then
    log "offsite OK (cifrado)"
  else
    err "falló la copia fuera del host"
    notify_syslog "offsite FAIL"
    [ "$BACKUP_OFFSITE_REQUIRED" = "1" ] && exit 2
    log "AVISO: BACKUP_OFFSITE_REQUIRED=0; se continúa solo con copia local"
  fi
else
  err "BACKUP_DEST vacío: la copia NO sale del host"
  notify_syslog "offsite sin destino"
  [ "$BACKUP_OFFSITE_REQUIRED" = "1" ] && exit 2
fi

log "copia terminada y verificada: $DB_FILE"
notify_syslog "backup OK $STAMP"
