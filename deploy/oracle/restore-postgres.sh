#!/usr/bin/env bash
# ============================================================================
# restore-postgres.sh — restauración de una copia de staging.
#
# Dos modos:
#   --scratch   PRUEBA EN SECO REAL: restaura en bases temporales, analiza,
#               cuenta tablas/filas clave, valida también evolution, globals y
#               media, y borra las bases temporales. No toca la base real.
#   (sin --scratch)  restauración REAL sobre POSTGRES_DB. Exige --yes y PARA la
#               API durante el proceso.
#
# Uso:
#   ./restore-postgres.sh --dump backups/makingsmiles-db-<stamp>.dump --scratch
#   ./restore-postgres.sh --dump ... --database makingsmiles --yes \
#       [--media ...] [--evolution ...] [--globals ...]
#
# En --scratch, si no se pasan --evolution/--globals/--media, se autodetectan los
# ficheros hermanos del mismo timestamp (lo normal, porque backup-postgres.sh los
# genera juntos). Exige el .sha256 del dump: sin checksum no se restaura.
#
# Verificado solo por revisión y `bash -n`: en el entorno de escritura no hay
# daemon Docker, así que esto NO se ha ejecutado aquí. Comando exacto y qué
# valida, en docs/rebuild/INFRA.md §9.
# ============================================================================
set -euo pipefail
umask 077

APP_DIR="${APP_DIR:-/opt/makingsmiles}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
DUMP=""; DATABASE=""; SCRATCH=0; CONFIRM=0
MEDIA=""; EVOLUTION=""; GLOBALS=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dump) DUMP="${2:?}"; shift 2 ;;
    --database) DATABASE="${2:?}"; shift 2 ;;
    --media) MEDIA="${2:?}"; shift 2 ;;
    --evolution) EVOLUTION="${2:?}"; shift 2 ;;
    --globals) GLOBALS="${2:?}"; shift 2 ;;
    --scratch) SCRATCH=1; shift ;;
    --yes) CONFIRM=1; shift ;;
    -h|--help) sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "ERROR: argumento desconocido: $1" >&2; exit 1 ;;
  esac
done

log() { printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

[ -f "$ENV_FILE" ] || die "no existe $ENV_FILE"
set -a; . "$ENV_FILE"; set +a
: "${POSTGRES_USER:?falta POSTGRES_USER}"
DATABASE="${DATABASE:-${POSTGRES_DB:?falta POSTGRES_DB}}"
[ -n "$DUMP" ] || die "falta --dump"
[ -f "$DUMP" ] || die "no existe el dump: $DUMP"
COMPOSE=(docker compose --project-directory "$APP_DIR")
compose() { "${COMPOSE[@]}" "$@"; }
psql_db() { compose exec -T postgres psql -U "$POSTGRES_USER" -d "$1" "${@:2}"; }

# Integridad obligatoria antes de tocar nada.
[ -f "$DUMP.sha256" ] || die "falta $DUMP.sha256 (checksum obligatorio): no se restaura a ciegas"
( cd "$(dirname "$DUMP")" && sha256sum -c "$(basename "$DUMP").sha256" ) || die "checksum no coincide: NO se restaura"
log "checksum OK"
compose exec -T postgres pg_restore --list < "$DUMP" >/dev/null 2>&1 \
  || die "pg_restore --list falla: el fichero no es un dump custom válido"
log "dump legible por pg_restore"

# Autodetección de hermanos del mismo timestamp.
STAMP_FILE="$(basename "$DUMP")"
STAMP="${STAMP_FILE#makingsmiles-db-}"; STAMP="${STAMP%.dump}"
SIB_DIR="$(dirname "$DUMP")"
[ -n "$EVOLUTION" ] || EVOLUTION="$SIB_DIR/makingsmiles-evolution-$STAMP.dump"
[ -n "$GLOBALS" ]   || GLOBALS="$SIB_DIR/makingsmiles-globals-$STAMP.sql"
[ -n "$MEDIA" ]     || MEDIA="$SIB_DIR/makingsmiles-media-$STAMP.tar.gz"
[ -f "$EVOLUTION" ] || EVOLUTION=""
[ -f "$GLOBALS" ]   || GLOBALS=""
[ -f "$MEDIA" ]     || MEDIA=""
KEY_TABLES="${RESTORE_KEY_TABLES:-usuarios pacientes citas consentimientos}"

if [ "$SCRATCH" -eq 1 ]; then
  TARGET="restore_check_$(date -u '+%Y%m%d%H%M%S')"
  TARGET_EVO="${TARGET}_evolution"
  CLEANUP_DBS=("$TARGET")
  cleanup() {
    for db in "${CLEANUP_DBS[@]}"; do
      psql_db postgres -c "DROP DATABASE IF EXISTS \"$db\" WITH (FORCE);" >/dev/null 2>&1 || true
    done
  }
  trap cleanup EXIT

  log "PRUEBA EN SECO: dump app -> $TARGET"
  psql_db postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"$TARGET\";" >/dev/null
  compose exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$TARGET" --no-owner --exit-on-error < "$DUMP"

  TABLES=$(psql_db "$TARGET" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")
  [ "${TABLES:-0}" -gt 0 ] || die "la restauración no ha creado tablas en $TARGET"
  # ANALYZE real: n_live_tup de pg_stat_user_tables es 0 hasta que se analiza.
  psql_db "$TARGET" -c "ANALYZE;" >/dev/null
  TOTAL_KEY=0
  ENCONTRADAS=0
  for t in $KEY_TABLES; do
    EXISTS=$(psql_db "$TARGET" -tAc "SELECT to_regclass('public.$t') IS NOT NULL;")
    case "$EXISTS" in
      t|true)
        N=$(psql_db "$TARGET" -tAc "SELECT count(*) FROM \"$t\";")
        ENCONTRADAS=$((ENCONTRADAS+1)); TOTAL_KEY=$((TOTAL_KEY+N))
        log "  tabla clave $t: $N filas"
        ;;
      *) log "  AVISO: tabla clave '$t' no existe en este dump" ;;
    esac
  done
  [ "$ENCONTRADAS" -gt 0 ] || die "ninguna tabla clave existe ($KEY_TABLES): el dump no parece de la app"
  [ "$TOTAL_KEY" -gt 0 ] || die "las tablas clave existen pero están vacías: restauración no demostrada"
  log "PRUEBA EN SECO app OK: $TABLES tablas, $ENCONTRADAS tablas clave, $TOTAL_KEY filas clave"

  if [ -n "$EVOLUTION" ]; then
    log "PRUEBA EN SECO evolution: $EVOLUTION -> $TARGET_EVO"
    [ -f "$EVOLUTION.sha256" ] || die "falta $EVOLUTION.sha256"
    ( cd "$(dirname "$EVOLUTION")" && sha256sum -c "$(basename "$EVOLUTION").sha256" ) || die "checksum evolution no coincide"
    compose exec -T postgres pg_restore --list < "$EVOLUTION" >/dev/null 2>&1 || die "dump evolution ilegible"
    psql_db postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"$TARGET_EVO\";" >/dev/null
    CLEANUP_DBS+=("$TARGET_EVO")
    compose exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$TARGET_EVO" --no-owner --exit-on-error < "$EVOLUTION"
    EVO_TABLES=$(psql_db "$TARGET_EVO" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")
    [ "${EVO_TABLES:-0}" -gt 0 ] || die "el dump de evolution no restaura tablas"
    log "PRUEBA EN SECO evolution OK: $EVO_TABLES tablas"
  else
    log "AVISO: sin dump de evolution para probar (BACKUP_MEDIA/evolution?)"
  fi

  if [ -n "$GLOBALS" ]; then
    [ -s "$GLOBALS" ] || die "globals vacío: $GLOBALS"
    grep -qiE 'CREATE ROLE|ALTER ROLE' "$GLOBALS" || die "globals no contiene CREATE/ALTER ROLE"
    log "PRUEBA EN SECO globals OK ($(wc -l < "$GLOBALS") líneas)"
  else
    log "AVISO: sin fichero de globals"
  fi

  if [ -n "$MEDIA" ]; then
    [ -f "$MEDIA.sha256" ] || die "falta $MEDIA.sha256"
    ( cd "$(dirname "$MEDIA")" && sha256sum -c "$(basename "$MEDIA").sha256" ) || die "checksum media no coincide"
    tar -tzf "$MEDIA" >/dev/null || die "el archivo de media no se puede listar (corrupto)"
    N_MEDIA=$(tar -tzf "$MEDIA" | head -n 2000 | wc -l | tr -d ' ')
    [ "$N_MEDIA" -gt 0 ] || die "el archivo de media está vacío"
    log "PRUEBA EN SECO media OK (primeras ${N_MEDIA} entradas legibles)"
  else
    log "AVISO: sin archivo de media"
  fi

  log "PRUEBA EN SECO COMPLETA OK (las BD temporales se borran al salir)"
  exit 0
fi

# --- Restauración REAL ------------------------------------------------------
[ "$CONFIRM" -eq 1 ] || die "restauración real sin --yes: abortado por seguridad"
log "RESTAURACIÓN REAL de $DUMP sobre la base '$DATABASE'"
compose ps --status running --services | grep -qx api && compose stop api >/dev/null
trap 'compose start api >/dev/null 2>&1 || true' EXIT
psql_db postgres -v ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DATABASE' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS "$DATABASE" WITH (FORCE);
CREATE DATABASE "$DATABASE" OWNER "$POSTGRES_USER";
SQL
compose exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$DATABASE" --no-owner --exit-on-error < "$DUMP"
psql_db "$DATABASE" -c "ANALYZE;" >/dev/null
log "base restaurada; arrancando API"
compose start api >/dev/null
trap - EXIT
for i in $(seq 1 60); do
  if compose exec -T api curl -fsS -m 3 http://127.0.0.1:8000/health/db >/dev/null 2>&1; then
    log "API healthy tras restauración"; break
  fi
  [ "$i" -eq 60 ] && die "API no healthy tras restauración: docker compose logs api"
  sleep 5
done
if [ -n "$MEDIA" ]; then
  [ -f "$MEDIA.sha256" ] || die "falta $MEDIA.sha256"
  ( cd "$(dirname "$MEDIA")" && sha256sum -c "$(basename "$MEDIA").sha256" ) || die "checksum media no coincide"
  log "restaurando media ($MEDIA)"
  compose exec -T api tar -xzf - -C /app < "$MEDIA"
  log "media restaurada"
else
  log "AVISO: no se restauró media (--media). Si el corte incluye ficheros, restáurala."
fi
log "RESTAURACIÓN COMPLETA. Comprueba login y un listado real antes de dar por bueno el corte."
