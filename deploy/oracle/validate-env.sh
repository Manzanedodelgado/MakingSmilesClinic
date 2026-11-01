#!/usr/bin/env bash
# ============================================================================
# validate-env.sh — valida un fichero .env de staging ANTES de desplegar.
#
# Un `.env` con los placeholders de la plantilla (CAMBIAR, OWNER, example.com)
# es "no vacío" y docker compose lo acepta: el stack arrancaría con una
# contraseña conocida. Este validador lo impide.
#
# Uso:
#   ./validate-env.sh /opt/makingsmiles/.env
#   ./validate-env.sh --allow-incomplete-backup /opt/makingsmiles/.env
#   ./validate-env.sh deploy/oracle/env.example   # DEBE fallar (es la plantilla)
#
# Códigos: 0 válido · 1 inválido
# ============================================================================
set -euo pipefail
ENV_FILE=""
ALLOW_INCOMPLETE=0
for arg in "$@"; do
  case "$arg" in
    --allow-incomplete-backup) ALLOW_INCOMPLETE=1 ;;
    -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "ERROR: opción desconocida: $arg" >&2; exit 1 ;;
    *) [ -z "$ENV_FILE" ] || { echo "ERROR: sobra '$arg'" >&2; exit 1; }; ENV_FILE="$arg" ;;
  esac
done
ENV_FILE="${ENV_FILE:-/opt/makingsmiles/.env}"
[ -f "$ENV_FILE" ] || { echo "ERROR: no existe $ENV_FILE" >&2; exit 1; }

# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a

ERRORES=()
error() { ERRORES+=("$*"); }

REQUIRED=(
  API_DOMAIN APP_DOMAIN ACME_EMAIL API_IMAGE
  POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB
  DATABASE_URL EVOLUTION_DATABASE_URI
  SECRET_KEY INTERNAL_API_KEY EVOLUTION_API_KEY
  ENVIRONMENT REDIS_URL
  BACKUP_DIR BACKUP_RETENTION_DAYS BACKUP_OFFSITE_REQUIRED BACKUP_MEDIA
)
# Compose deriva estas dos de los dominios; si el .env las trae, además deben
# coincidir con ellos.
PUBLIC_FRONTEND_URL="${PUBLIC_FRONTEND_URL:-https://${APP_DOMAIN:-}}"
PUBLIC_API_URL="${PUBLIC_API_URL:-https://${API_DOMAIN:-}}"
for v in "${REQUIRED[@]}"; do
  [ -n "${!v:-}" ] || error "falta o está vacía: $v"
done

# Placeholders de la plantilla: no son valores utilizables.
placeholders='CAMBIAR|OWNER|example\.com|example\.org|CHANGEME|changeme|dev-secret-change-me|dev-internal-key-change-me|cambiar'
for v in "${REQUIRED[@]}" API_WORKERS BACKUP_DEST BACKUP_AGE_RECIPIENT; do
  val="${!v:-}"
  if printf '%s' "$val" | grep -Eq "$placeholders"; then
    error "$v contiene un placeholder no sustituido: '$val'"
  fi
done

# Dominios y email.
for v in API_DOMAIN APP_DOMAIN; do
  val="${!v:-}"
  [ -n "$val" ] || continue
  printf '%s' "$val" | grep -Eq '^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$' \
    || error "$v no parece un FQDN válido: '$val'"
  case "$val" in
    *example.com|*example.org|*localhost) error "$v sigue siendo placeholder: '$val'" ;;
  esac
done
printf '%s' "${ACME_EMAIL:-}" | grep -Eq '^[^@[:space:]]+@[^@[:space:]]+\.[A-Za-z]{2,}$' \
  || error "ACME_EMAIL no parece un email válido"

# Imagen de la API: GHCR y tag limpio.
printf '%s' "${API_IMAGE:-}" | grep -Eq '^ghcr\.io/[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9._-]+$' \
  || error "API_IMAGE no es una referencia GHCR válida: '${API_IMAGE:-}'"

# Longitud mínima de secretos.
check_len() { [ "${#1}" -ge "$2" ] || error "$3 demasiado corto (${#1} < $2)"; }
check_len "${POSTGRES_PASSWORD:-}" 16 POSTGRES_PASSWORD
check_len "${SECRET_KEY:-}" 32 SECRET_KEY
check_len "${INTERNAL_API_KEY:-}" 32 INTERNAL_API_KEY
check_len "${EVOLUTION_API_KEY:-}" 16 EVOLUTION_API_KEY

# URLs coherentes con los dominios.
[ "${PUBLIC_FRONTEND_URL:-}" = "https://${APP_DOMAIN:-}" ] \
  || error "PUBLIC_FRONTEND_URL debe ser https://${APP_DOMAIN:-<APP_DOMAIN>}"
[ "${PUBLIC_API_URL:-}" = "https://${API_DOMAIN:-}" ] \
  || error "PUBLIC_API_URL debe ser https://${API_DOMAIN:-<API_DOMAIN>}"
case "${DATABASE_URL:-}" in
  *@postgres:*|*@postgres/*|*@postgres:5432*) ;;
  *) error "DATABASE_URL no apunta al servicio postgres de la red interna" ;;
esac
case "${REDIS_URL:-}" in
  redis://redis:*) ;;
  *) error "REDIS_URL no apunta al servicio redis de la red interna" ;;
esac

# Backup offsite: si es obligatorio, debe estar TODO configurado.
if [ "${BACKUP_OFFSITE_REQUIRED:-0}" = "1" ] && [ "$ALLOW_INCOMPLETE" -eq 0 ]; then
  [ -n "${BACKUP_DEST:-}" ] || error "BACKUP_OFFSITE_REQUIRED=1 pero BACKUP_DEST está vacío"
  [ -n "${BACKUP_AGE_RECIPIENT:-}" ] || error "BACKUP_OFFSITE_REQUIRED=1 pero falta BACKUP_AGE_RECIPIENT (cifrado en reposo)"
  [ -f "${BACKUP_SSH_KEY:-}" ] && [ -r "${BACKUP_SSH_KEY:-}" ] || error "BACKUP_SSH_KEY no existe o no es legible: '${BACKUP_SSH_KEY:-}'"
  [ -f "${BACKUP_KNOWN_HOSTS:-}" ] && [ -r "${BACKUP_KNOWN_HOSTS:-}" ] || error "BACKUP_KNOWN_HOSTS no existe o no es legible: '${BACKUP_KNOWN_HOSTS:-}'"
fi
[ -d "${BACKUP_DIR:-}" ] || error "BACKUP_DIR no existe: '${BACKUP_DIR:-}'"
command -v age >/dev/null 2>&1 || error "falta el binario 'age' (cifrado de copias)"

if [ "${#ERRORES[@]}" -gt 0 ]; then
  echo "ENV INVÁLIDO: $ENV_FILE" >&2
  printf ' - %s\n' "${ERRORES[@]}" >&2
  exit 1
fi
echo "ENV VÁLIDO: $ENV_FILE"
