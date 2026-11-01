#!/usr/bin/env bash
# ============================================================================
# bootstrap-oracle.sh — prepara una instancia Oracle Cloud (Always Free) para
# staging de MakingSmiles: usuario, Docker, sudo ACOTADO, firewall, SSH
# endurecido, directorios, secretos, claves de backup y timer de copias.
#
# Uso (como root, desde un checkout del repo en el servidor):
#   sudo API_IMAGE=ghcr.io/OWNER/repo-api:staging \
#     bash bootstrap-oracle.sh \
#       --domain example.com \
#       --app-domain staging.example.com \
#       --api-domain api.staging.example.com \
#       --email ops@example.com \
#       --ghcr-user TU_USUARIO_GHCR \
#       --admin-cidr 203.0.113.7/32 \
#       --ssh-pubkey /root/mi_clave.pub
#
# El token de GHCR NO se pasa por argumento (quedaría en `ps`/historial): se lee
# de la variable de entorno GHCR_TOKEN, o se hace `docker login ghcr.io` a mano.
#
# Requisitos: Ubuntu 22.04/24.04 arm64 (A1.Flex), salida a internet. El DNS no
# hace falta para arrancar; Caddy reintenta el certificado cuando apunte.
#
# Qué NO hace: no abre puertos en la Security List de OCI (es API de OCI, no del
# SO), no instala la clave pública en el servidor de backups (hay que hacerlo en
# ese host), no configura el DNS. Ver docs/rebuild/INFRA.md §7.3.
# ============================================================================
set -euo pipefail
umask 077

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-/opt/makingsmiles}"
CONF_DIR="${CONF_DIR:-/etc/makingsmiles}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"
DOMAIN=""; APP_DOMAIN=""; API_DOMAIN=""; ACME_EMAIL=""
GHCR_USER="${GHCR_USER:-}"
ADMIN_CIDR=""
SSH_PUBKEY=""
FORCE_ENV=0; SKIP_DOCKER=0; SKIP_FIREWALL=0; SKIP_PULL=0
GHCR_TOKEN="${GHCR_TOKEN:-}"

usage() { sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }
log()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '    OK: %s\n' "$*"; }
warn() { printf '\033[1;33m    AVISO: %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --domain) DOMAIN="${2:?}"; shift 2 ;;
    --app-domain) APP_DOMAIN="${2:?}"; shift 2 ;;
    --api-domain) API_DOMAIN="${2:?}"; shift 2 ;;
    --email) ACME_EMAIL="${2:?}"; shift 2 ;;
    --ghcr-user) GHCR_USER="${2:?}"; shift 2 ;;
    --admin-cidr) ADMIN_CIDR="${2:?}"; shift 2 ;;
    --ssh-pubkey) SSH_PUBKEY="${2:?}"; shift 2 ;;
    --deploy-user) DEPLOY_USER="${2:?}"; shift 2 ;;
    --app-dir) APP_DIR="${2:?}"; shift 2 ;;
    --force-env) FORCE_ENV=1; shift ;;
    --skip-docker) SKIP_DOCKER=1; shift ;;
    --skip-firewall) SKIP_FIREWALL=1; shift ;;
    --skip-pull) SKIP_PULL=1; shift ;;
    -h|--help) usage 0 ;;
    *) die "argumento desconocido: $1 (usa --help)" ;;
  esac
done

[ "$(id -u)" -eq 0 ] || die "ejecuta como root (sudo bash $0 ...)"
[ -f /etc/os-release ] || die "no se reconoce el SO (falta /etc/os-release)"
. /etc/os-release
[ "${ID:-}" = "ubuntu" ] || warn "SO ${PRETTY_NAME:-desconocido}: probado para Ubuntu 22.04/24.04"
[ -n "$DOMAIN" ] || die "falta --domain"
[ -n "$APP_DOMAIN" ] || die "falta --app-domain"
[ -n "$API_DOMAIN" ] || die "falta --api-domain"
[ -n "$ACME_EMAIL" ] || die "falta --email"
[ -n "$GHCR_USER" ] || die "falta --ghcr-user (se usa en API_IMAGE y en el login GHCR)"
[ -n "$GHCR_TOKEN" ] || warn "sin GHCR_TOKEN: si el paquete GHCR es privado, haz 'docker login ghcr.io' antes del pull"
ARCH="$(uname -m)"; ok "arquitectura: $ARCH (aarch64 en A1.Flex)"

# --- 1. Paquetes base -------------------------------------------------------
log "1/10 Paquetes base"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg jq ufw fail2ban unattended-upgrades \
  logrotate rsync openssl age >/dev/null
ok "ca-certificates curl gnupg jq ufw fail2ban unattended-upgrades logrotate rsync openssl age"

# --- 2. Docker (repositorio oficial) ---------------------------------------
if [ "$SKIP_DOCKER" -eq 0 ] && ! command -v docker >/dev/null 2>&1; then
  log "2/10 Docker Engine + Compose plugin (repo oficial)"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
  ok "Docker instalado: $(docker --version)"
else
  log "2/10 Docker ya presente o --skip-docker"
  command -v docker >/dev/null 2>&1 || die "docker no está instalado y se pasó --skip-docker"
fi
systemctl enable --now docker >/dev/null 2>&1 || true
docker compose version >/dev/null 2>&1 || die "falta el plugin 'docker compose'"

# --- 3. Usuario de despliegue SIN grupo docker + sudo acotado --------------
log "3/10 Usuario de despliegue y sudo acotado"
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$DEPLOY_USER"
  ok "creado usuario $DEPLOY_USER"
fi
# NO se añade a 'docker': el grupo docker equivale a root en el host. El deploy
# solo puede ejecutar el wrapper root con acciones fijas (deploy/rollback/...).
if id -nG "$DEPLOY_USER" 2>/dev/null | tr ' ' '\n' | grep -qx docker; then
  warn "$DEPLOY_USER YA está en el grupo docker (equivale a root). Quítalo: gpasswd -d $DEPLOY_USER docker"
fi

install -d -m 0755 /usr/local/sbin
cat > /usr/local/sbin/makingsmiles-deploy <<'WRAPPER'
#!/usr/bin/env bash
# Wrapper root de despliegue (única orden que sudo permite al usuario deploy).
# Valida la acción y la referencia de imagen; nunca ejecuta shell libre.
set -euo pipefail
APP_DIR="${APP_DIR:-/opt/makingsmiles}"
LIB_DIR="${LIB_DIR:-/usr/local/lib/makingsmiles}"
ACTION="${1:-}"; shift || true
case "$ACTION" in
  deploy)
    [ $# -eq 1 ] || { echo "uso: makingsmiles-deploy deploy <ghcr.io/...:tag>" >&2; exit 2; }
    IMG="$1"
    printf '%s' "$IMG" | grep -Eq '^ghcr\.io/[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9._-]+$' \
      || { echo "imagen no válida: $IMG" >&2; exit 2; }
    exec bash "$LIB_DIR/deploy-staging.sh" "$IMG" --reload-caddy
    ;;
  rollback)
    exec bash "$LIB_DIR/deploy-staging.sh" --rollback --reload-caddy
    ;;
  reload-caddy)
    docker compose --project-directory "$APP_DIR" exec -T caddy caddy reload --config /etc/caddy/Caddyfile
    ;;
  check-evolution)
    if [ -x "$LIB_DIR/check-evolution.sh" ]; then bash "$LIB_DIR/check-evolution.sh"; else bash "$APP_DIR/check-evolution.sh"; fi
    ;;
  backup-dry-run)
    if [ -x "$LIB_DIR/backup-postgres.sh" ]; then bash "$LIB_DIR/backup-postgres.sh" --dry-run; else bash "$APP_DIR/backup-postgres.sh" --dry-run; fi
    ;;
  *) echo "acción no permitida: '$ACTION' (deploy|rollback|reload-caddy|check-evolution|backup-dry-run)" >&2; exit 2 ;;
esac
WRAPPER
chmod 0750 /usr/local/sbin/makingsmiles-deploy
chown root:root /usr/local/sbin/makingsmiles-deploy
cat > "$CONF_DIR/sudoers-deploy" <<SUDOERS
# Solo el wrapper, sin contraseña. No se concede docker ni shell root.
$DEPLOY_USER ALL=(root) NOPASSWD: /usr/local/sbin/makingsmiles-deploy
SUDOERS
chmod 0440 "$CONF_DIR/sudoers-deploy"
install -m 0440 "$CONF_DIR/sudoers-deploy" /etc/sudoers.d/makingsmiles-deploy
visudo -cf /etc/sudoers.d/makingsmiles-deploy >/dev/null || die "sudoers inválido"
ok "$DEPLOY_USER puede ejecutar SOLO /usr/local/sbin/makingsmiles-deploy (PASSWD: no)"

# --- 4. Directorios y ficheros de la pila ----------------------------------
log "4/10 Directorios y ficheros"
install -d -m 0755 "$APP_DIR" "$APP_DIR/.deploy" "$APP_DIR/postgres-init"
install -d -m 0700 "$CONF_DIR" "$APP_DIR/.ssh"
install -d -m 0750 "$APP_DIR/backups" "$APP_DIR/backups/offsite"
for f in docker-compose.yml Caddyfile env.example backup-postgres.sh restore-postgres.sh \
         deploy-staging.sh validate-env.sh check-evolution.sh; do
  [ -f "$SRC_DIR/$f" ] || die "falta $SRC_DIR/$f (ejecuta el script desde deploy/oracle del repo)"
  install -m 0755 "$SRC_DIR/$f" "$APP_DIR/$f"
done
install -m 0644 "$SRC_DIR/postgres-init/01-evolution-db.sql" "$APP_DIR/postgres-init/01-evolution-db.sql"
# Copias OPERATIVAS root-owned: el wrapper sudo ejecuta SIEMPRE desde aquí, no
# desde /opt (que es escribible por el usuario de deploy y sería una escalada).
install -d -m 0755 /usr/local/lib/makingsmiles
for f in deploy-staging.sh validate-env.sh check-evolution.sh backup-postgres.sh restore-postgres.sh; do
  install -m 0755 -o root -g root "$SRC_DIR/$f" "/usr/local/lib/makingsmiles/$f"
done
ok "scripts operativos root-owned en /usr/local/lib/makingsmiles"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"
# Media: el contenedor corre como appuser (uid 1001 en deploy/backend.Dockerfile).
install -d -m 0750 -o 1001 -g 1001 "$APP_DIR/media"
# .env y claves: root, no legibles por el usuario de deploy.
chown root:root "$APP_DIR/backups" "$APP_DIR/.ssh"; chmod 0700 "$APP_DIR/backups" "$APP_DIR/.ssh"
ok "pila copiada a $APP_DIR (media 1001:1001; backups y .ssh root 0700)"

# --- 5. .env con secretos generados ---------------------------------------
log "5/10 .env"
ENV_FILE="$APP_DIR/.env"
if [ -f "$ENV_FILE" ] && [ "$FORCE_ENV" -eq 0 ]; then
  ok "$ENV_FILE ya existe; no se toca (usa --force-env para regenerar)"
else
  PG_PASS="$(openssl rand -hex 24)"; SECRET_KEY="$(openssl rand -hex 48)"
  INTERNAL_KEY="$(openssl rand -hex 32)"; EVOLUTION_KEY="$(openssl rand -hex 24)"
  cp "$SRC_DIR/env.example" "$ENV_FILE"   # umask 077 global: nace 600
  python3 - "$ENV_FILE" "$PG_PASS" "$SECRET_KEY" "$INTERNAL_KEY" "$EVOLUTION_KEY" \
    "$DOMAIN" "$APP_DOMAIN" "$API_DOMAIN" "$ACME_EMAIL" "$GHCR_USER" <<'PY'
import sys
path, pg, secret, internal, evolution, domain, app, api, email, ghcr = sys.argv[1:11]
env = {}
for line in open(path, encoding="utf-8"):
    line = line.rstrip("\n")
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1); env[k] = v
user, db = env.get("POSTGRES_USER", "makingsmiles"), env.get("POSTGRES_DB", "makingsmiles")
env["POSTGRES_PASSWORD"] = pg
env["DATABASE_URL"] = f"postgresql+psycopg://{user}:{pg}@postgres:5432/{db}"
env["EVOLUTION_DATABASE_URI"] = f"postgresql://{user}:{pg}@postgres:5432/evolution?schema=public"
env["SECRET_KEY"] = secret; env["INTERNAL_API_KEY"] = internal; env["EVOLUTION_API_KEY"] = evolution
env["DOMAIN"] = domain; env["APP_DOMAIN"] = app; env["API_DOMAIN"] = api
env["ACME_EMAIL"] = email
env["PUBLIC_API_URL"] = f"https://{api}"
env["API_IMAGE"] = env["API_IMAGE"].replace("OWNER", ghcr.lower())
env["BACKUP_OFFSITE_REQUIRED"] = "0"   # se activa al configurar el offsite (INFRA §9)
out = ["# Generado por bootstrap-oracle.sh — NO versionar, NO copiar a git."]
out += [f"{k}={v}" for k, v in env.items()]
open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
PY
  chown root:root "$ENV_FILE"; chmod 0600 "$ENV_FILE"
  ok "$ENV_FILE generado (root 600)"
  warn "guarda copia de $ENV_FILE fuera del servidor: sin SECRET_KEY no se validan tokens"
fi
# Autotest del validador: la plantilla DEBE fallar; el .env real DEBE pasar.
if bash "$APP_DIR/validate-env.sh" "$SRC_DIR/env.example" >/dev/null 2>&1; then
  warn "validate-env.sh aceptó la plantilla con placeholders: revisa el validador"
else
  ok "validate-env.sh rechaza la plantilla con placeholders (como debe)"
fi
bash "$APP_DIR/validate-env.sh" --allow-incomplete-backup "$ENV_FILE" \
  || die "el .env generado no pasa validate-env.sh: revisa los valores"
ok ".env generado pasa validate-env.sh"

# Claves de backup (SSH y age) si no existen; el offsite se activa cuando el
# operador instale la clave pública en el host de backups y rellene BACKUP_DEST.
if [ ! -f "$APP_DIR/.ssh/backup_key" ]; then
  ssh-keygen -q -t ed25519 -N '' -C "makingsmiles-backup@staging" -f "$APP_DIR/.ssh/backup_key"
  ok "par de claves SSH de backup generado; pública:"
  sed 's/^/      /' "$APP_DIR/.ssh/backup_key.pub"
fi
if [ ! -f "$APP_DIR/.ssh/age.key" ]; then
  age-keygen -o "$APP_DIR/.ssh/age.key" 2>/dev/null
  AGE_PUB="$(grep -o 'age1[0-9a-z]*' "$APP_DIR/.ssh/age.key" | head -n1 || true)"
  if [ -n "$AGE_PUB" ]; then
    sed -i "s|^BACKUP_AGE_RECIPIENT=.*|BACKUP_AGE_RECIPIENT=$AGE_PUB|" "$ENV_FILE"
    ok "clave age generada; BACKUP_AGE_RECIPIENT=$AGE_PUB"
  else
    warn "no se pudo extraer la clave pública de age; rellena BACKUP_AGE_RECIPIENT a mano"
  fi
fi
chown -R root:root "$APP_DIR/.ssh"; chmod 0700 "$APP_DIR/.ssh"; chmod 0600 "$APP_DIR/.ssh/"*
ok "claves de backup en $APP_DIR/.ssh (root 600)"

# --- 6. Swap y sysctl -------------------------------------------------------
log "6/10 Swap y sysctl"
if ! swapon --show | grep -q .; then
  MEM_MB=$(( $(awk '/MemTotal/{print $2}' /proc/meminfo) / 1024 ))
  if [ "$MEM_MB" -lt 16384 ]; then
    fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
    chmod 600 /swapfile; mkswap /swapfile >/dev/null; swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    ok "swap 2G activado (RAM ${MEM_MB}MB)"
  else ok "RAM ${MEM_MB}MB; sin swap"; fi
else ok "ya hay swap"; fi
cat > /etc/sysctl.d/99-makingsmiles.conf <<'SYSCTL'
vm.overcommit_memory = 1
net.core.somaxconn = 1024
SYSCTL
sysctl --system >/dev/null 2>&1 || true
ok "sysctl aplicado"

# --- 7. Firewall, fail2ban, SSH --------------------------------------------
if [ "$SKIP_FIREWALL" -eq 0 ]; then
  log "7/10 Firewall (ufw), fail2ban y SSH"
  # SSH solo desde la IP/CIDR del administrador si se indica; si no, /32 de la
  # sesión actual. NUNCA abrir 22 a 0.0.0.0/0 por defecto.
  SSH_RULE="${ADMIN_CIDR:-}"
  if [ -z "$SSH_RULE" ] && [ -n "${SSH_CLIENT:-}" ]; then SSH_RULE="$(awk '{print $1"/32"}' <<<"$SSH_CLIENT")"; fi
  if [ -n "$SSH_RULE" ]; then
    ufw allow from "$SSH_RULE" to any port 22 proto tcp >/dev/null
    ok "SSH 22 permitido solo desde $SSH_RULE"
  else
    warn "no se pudo determinar la IP admin: ejecuta 'ufw allow from <IP>/32 to any port 22' TÚ MISMO antes de cerrar la sesión"
  fi
  ufw default deny incoming >/dev/null; ufw default allow outgoing >/dev/null
  ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; ufw allow 443/udp >/dev/null
  ufw --force enable >/dev/null
  systemctl enable --now fail2ban >/dev/null 2>&1 || true
  ok "ufw activo (deny incoming; 80/443; 22 restringido) y fail2ban activo"
  warn "En Oracle Cloud la Security List del VCN manda ADEMÁS de ufw: abre 80/443 y 22 solo desde tu IP (§7.3.1 de INFRA)"

  # Endurecimiento SSH, con validación previa y sin dejarte fuera: solo se aplica
  # si hay al menos una clave pública instalada.
  if [ -n "$SSH_PUBKEY" ] && [ -f "$SSH_PUBKEY" ]; then
    install -d -m 0700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
    cat "$SSH_PUBKEY" >> "/home/$DEPLOY_USER/.ssh/authorized_keys"
    chown "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh/authorized_keys"
    chmod 0600 "/home/$DEPLOY_USER/.ssh/authorized_keys"
    ok "clave pública de CI instalada para $DEPLOY_USER"
  else
    warn "sin --ssh-pubkey: NO se endurece SSH (sería quedarte fuera). Instala la clave de CI y vuelve a ejecutar con --ssh-pubkey"
  fi
  if [ -n "$SSH_PUBKEY" ] && [ -f "$SSH_PUBKEY" ] && [ -s "/home/$DEPLOY_USER/.ssh/authorized_keys" ]; then
    cat > /etc/ssh/sshd_config.d/99-makingsmiles.conf <<'SSHD'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
PermitEmptyPasswords no
MaxAuthTries 4
SSHD
    if sshd -t; then
      systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || warn "no se pudo recargar sshd"
      ok "SSH endurecido (PermitRootLogin no, PasswordAuthentication no)"
    else
      rm -f /etc/ssh/sshd_config.d/99-makingsmiles.conf
      die "la config SSH nueva no valida: se ha revertido"
    fi
  fi
else
  log "7/10 Firewall y SSH omitidos (--skip-firewall)"
fi

# --- 8. Copias de seguridad (systemd timer, root) -------------------------
log "8/10 Timer de copias de seguridad (root)"
cat > /etc/systemd/system/makingsmiles-backup.service <<UNIT
[Unit]
Description=MakingSmiles staging — copia de Postgres + media verificada y cifrada
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
User=root
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=/usr/local/lib/makingsmiles/backup-postgres.sh
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
UNIT
cat > /etc/systemd/system/makingsmiles-backup.timer <<UNIT
[Unit]
Description=MakingSmiles staging — copia diaria

[Timer]
OnCalendar=*-*-* 03:15:00
Persistent=true
RandomizedDelaySec=600
Unit=makingsmiles-backup.service

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now makingsmiles-backup.timer >/dev/null 2>&1 || warn "no se pudo habilitar el timer"
ok "timer diario 03:15 UTC (systemctl list-timers | grep makingsmiles)"

# --- 9. GHCR + arranque ----------------------------------------------------
log "9/10 Imagen y arranque"
cd "$APP_DIR"
if [ -n "$GHCR_TOKEN" ]; then
  printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin >/dev/null
  ok "docker login ghcr.io como $GHCR_USER (token por stdin, no por argv)"
fi
if [ "$SKIP_PULL" -eq 0 ]; then
  docker compose --project-directory "$APP_DIR" pull --quiet || warn "pull falló (¿imagen publicada? ¿login GHCR?)"
  if ! docker compose --project-directory "$APP_DIR" up -d --remove-orphans; then
    warn "no se pudo arrancar la pila (normal si la imagen aún no está en GHCR)."
    warn "Publica la imagen y: cd $APP_DIR && docker compose pull && docker compose up -d"
  else
    ok "pila arrancada"
    for i in $(seq 1 60); do
      if docker compose --project-directory "$APP_DIR" exec -T api curl -fsS -m 3 http://127.0.0.1:8000/health/db >/dev/null 2>&1; then
        ok "API healthy (/health/db)"; break
      fi
      [ "$i" -eq 60 ] && die "la API no llegó a healthy en 5 min: docker compose logs api"
      sleep 5
    done
    # Prueba de la copia de seguridad con el MISMO usuario/servicio que el timer:
    # comprueba lock escribible, compose alcanzable y configuración leída.
    if bash "$APP_DIR/backup-postgres.sh" --dry-run >/dev/null 2>&1; then
      ok "backup --dry-run OK como root (lock en $APP_DIR/.deploy)"
    else
      warn "backup --dry-run falló: revisa $APP_DIR/.env y permisos de $APP_DIR/.deploy"
    fi
    if bash "$APP_DIR/check-evolution.sh" >/dev/null 2>&1; then
      ok "Evolution: API autenticada responde"
    else
      warn "Evolution no responde todavía (normal si no está emparejado/configurado); revisa docker compose logs evolution"
    fi
  fi
else
  warn "--skip-pull: no se arranca nada (prepara el servidor sin imagen)"
fi

# --- 10. Resumen -----------------------------------------------------------
log "10/10 Hecho"
cat <<SUMMARY

============================================================================
 Bootstrap terminado. QUÉ FALTA (todo en docs/rebuild/INFRA.md):
============================================================================
 1) Security List de OCI: ingress TCP 80/443 y 22 solo desde tu IP.
 2) DNS: $API_DOMAIN -> IP de esta instancia; $APP_DOMAIN -> Vercel.
    Cuando $API_DOMAIN resuelva: cd $APP_DIR && docker compose restart caddy
    y comprueba: curl -fsS https://$API_DOMAIN/health/db
 3) GHCR: si el paquete es privado, 'docker login ghcr.io' (o exporta GHCR_TOKEN
    y re-ejecuta). Publica la imagen y arranca la pila.
 4) Backup fuera del host (OBLIGATORIO antes de producción):
    - instala $APP_DIR/.ssh/backup_key.pub en el host de backups;
    - 'ssh-keyscan -H <host-backup> > $APP_DIR/.ssh/known_hosts' y VERIFICA la huella;
    - edita BACKUP_DEST y BACKUP_OFFSITE_REQUIRED=1 en $ENV_FILE;
    - ./backup-postgres.sh --dry-run && ./backup-postgres.sh && ./restore-postgres.sh --scratch --dump <último>
    - guarda la clave privada age ($APP_DIR/.ssh/age.key) FUERA del servidor.
 5) Vercel: importa el repo con Root Directory=frontend/; sustituye el placeholder
    de dominio en vercel.json Y frontend/vercel.json (§7.2.1); añade el dominio.
 6) SSH: el usuario $DEPLOY_USER NO está en el grupo docker; solo puede ejecutar
    'sudo /usr/local/sbin/makingsmiles-deploy <acción>'. CI necesita su clave
    pública autorizada y known_hosts fijado en los secrets.
    Los scripts que ejecuta el wrapper son COPIAS root-owned en
    /usr/local/lib/makingsmiles: si cambian en el repo, un admin debe
    reinstalarlas (re-ejecutar el bootstrap o copiarlas a mano como root).
 7) Sesión de WhatsApp: ./check-evolution.sh (declara si hay instancia 'open').
============================================================================
SUMMARY
