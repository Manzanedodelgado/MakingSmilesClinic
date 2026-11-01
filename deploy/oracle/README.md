# Staging en Oracle Always Free — guía de operación (API)

Esta carpeta levanta la **API** de staging: Caddy (TLS), FastAPI, Postgres 16,
Redis 7 y Evolution API. El **frontend vive en Vercel** (`staging.<dominio>`);
el navegador solo habla con Vercel y este reescribe `/api/*` a
`https://api.staging.<dominio>`. Evolution necesita salida a internet (WSS con
WhatsApp), por eso está en la red `edge`; aun así no publica puertos.

> La guía completa (arquitectura, límites con citas, rollback, backups y lista
> de lo NO validado) es **[docs/rebuild/INFRA.md](../../docs/rebuild/INFRA.md)**.
> Este README es la chuleta de operación diaria.

## Ficheros

| Fichero | Para qué |
|---|---|
| `docker-compose.yml` | la pila. Solo Caddy publica 80/443; el resto en red interna |
| `Caddyfile` | TLS de `api.<dominio>`, límite de cuerpo, CORP para `/media`, SSE sin buffering |
| `env.example` | plantilla de variables (sin secretos) |
| `bootstrap-oracle.sh` | prepara una instancia nueva de cero (Docker, sudo acotado, ufw/SSH, secretos, claves de backup, timer, arranque) |
| `backup-postgres.sh` | copia comprimida y **verificada**, retención, cifrado `age` y copia fuera del host (timer systemd root) |
| `restore-postgres.sh` | restauración; `--scratch` = prueba en seco REAL (ANALYZE, tablas clave, evolution, globals, media) |
| `deploy-staging.sh` | pull + recreate + healthcheck + rollback automático con dos slots (lo llama el wrapper sudo desde Actions) |
| `validate-env.sh` | rechaza placeholders (`CAMBIAR`, `OWNER`, `example.com`) y secretos débiles en `.env` |
| `check-evolution.sh` | comprueba la **sesión real de WhatsApp** (`connectionStatus=open`), no solo que la API responda |
| `postgres-init/01-evolution-db.sql` | crea la BD `evolution` en el primer arranque |
| `.env` (en el servidor, gitignored) | secretos reales, modo 600 |

## Preparar una instancia nueva (resumen)

1. **Instancia OCI**: shape `VM.Standard.A1.Flex` (2 OCPU / 12 GB, Always Free),
   boot volume 50-100 GB, Ubuntu 22.04/24.04 (arm64), IP pública. Abre ingress
   80/443 en la **Security List** del VCN (ufw no basta) y 22 solo desde tu IP.
2. **DNS**: `api.staging.<dominio>` → IP pública de la instancia.
3. **Copiar y ejecutar** desde un checkout del repo:

   ```bash
   # El token GHCR va por entorno (nunca por argv):
   export GHCR_TOKEN='...'
   sudo -E bash deploy/oracle/bootstrap-oracle.sh \
     --domain <dominio> --app-domain staging.<dominio> \
     --api-domain api.staging.<dominio> --email ops@<dominio> \
     --ghcr-user <usuario-github> --admin-cidr <IP-admin>/32 \
     --ssh-pubkey /root/clave-ci.pub --skip-pull
   ```
   El bootstrap NO mete al usuario de deploy en el grupo `docker`: le permite solo
   `sudo /usr/local/sbin/makingsmiles-deploy <acción>`

4. Si aún no hay imagen en GHCR, el bootstrap avisa y no arranca la pila: publica
   la imagen (CI) y haz `cd /opt/makingsmiles && docker compose pull && docker compose up -d`.
   Para preparar el servidor sin imagen usa `--skip-pull`.
5. Cuando el DNS resuelva: `cd /opt/makingsmiles && docker compose restart caddy`
   y comprueba `curl -fsS https://api.staging.<dominio>/health/db`.
6. **Activa el backup offsite**: instala `/opt/makingsmiles/.ssh/backup_key.pub` en
   el host de backups, fija y verifica `known_hosts`, y edita `BACKUP_DEST` +
   `BACKUP_OFFSITE_REQUIRED=1` en `/opt/makingsmiles/.env`. La clave privada `age`
   (`/opt/makingsmiles/.ssh/age.key`) se custodia FUERA del servidor. Prueba:
   `./backup-postgres.sh --dry-run`, `./backup-postgres.sh --verify` y
   `./restore-postgres.sh --scratch --dump <último dump>` (como root).

El bootstrap imprime al final la lista exacta de lo que queda por hacer.

## Operación diaria

```bash
cd /opt/makingsmiles
docker compose ps                       # estado y salud
docker compose logs -f --tail=100 api   # logs de la API
docker compose logs --tail=100 caddy    # TLS, errores de proxy
docker compose exec -T api curl -fsS http://127.0.0.1:8000/health/db
```

### Desplegar una imagen nueva

Normalmente lo hace GitHub Actions (`.github/workflows/deploy-oracle.yml`) al
publicar un tag `staging-*`. A mano:

```bash
cd /opt/makingsmiles
sudo /usr/local/sbin/makingsmiles-deploy deploy ghcr.io/<owner>/<repo>-api:<sha>
# a mano como root (equivale):
./deploy-staging.sh --dry-run        # enseña current/previous/objetivo, sin cambios
```

Si el healthcheck falla, el script vuelve **solo** a la imagen anterior
(registrada en `.deploy/previous_image`) y sale con error.

### Rollback

```bash
cd /opt/makingsmiles
sudo /usr/local/sbin/makingsmiles-deploy rollback   # vuelve a la anterior
./deploy-staging.sh --dry-run --rollback            # prueba en seco
cat .deploy/current_image .deploy/previous_image    # dos slots
```
En GitHub: Actions → *deploy-oracle-staging* → Run workflow → `action=rollback`.

### Copias y restauración

```bash
cd /opt/makingsmiles
sudo /opt/makingsmiles/backup-postgres.sh --dry-run   # plan
sudo /opt/makingsmiles/backup-postgres.sh             # copia + verificación + cifrado + offsite
sudo /opt/makingsmiles/backup-postgres.sh --verify    # checksum + pg_restore --list de la última
# prueba en seco REAL (app+evolution en BD temporales, ANALYZE, tablas clave, globals, media):
sudo /opt/makingsmiles/restore-postgres.sh --scratch --dump backups/makingsmiles-db-<fecha>.dump
# restauración real (para la API, pide --yes):
./restore-postgres.sh --dump backups/makingsmiles-db-<fecha>.dump --yes \
  --media backups/makingsmiles-media-<fecha>.tar.gz
```
El timer `makingsmiles-backup.timer` corre la copia a diario (03:15, retardo
aleatorio) como **root** (el `.env` es root 600). Cada copia se verifica
(checksum + `pg_restore --list`), se cifra con `age` y se espeja con
`rsync --delete` a un directorio remoto **dedicado**. Si `BACKUP_MEDIA=1` y falla
el tar, o si falla el offsite con `BACKUP_OFFSITE_REQUIRED=1`, el script sale
2/1 y systemd marca **failed**: es intencionado.

### Rotar un secreto

1. Genera el valor nuevo (`openssl rand -hex 32`).
2. Edita `/opt/makingsmiles/.env` (modo 600).
3. `docker compose up -d --no-deps api` (recrea la API con el valor nuevo).
4. Los secretos de Postgres (`POSTGRES_PASSWORD`) **no** se pueden cambiar solo
   en `.env`: hay que cambiarla dentro de Postgres (`ALTER ROLE`) y luego
   recrear API y Evolution. Hazlo en ventana de mantenimiento.

## Problemas típicos

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| Caddy no emite certificado | DNS aún no apunta / Security List bloquea 80 | `dig +short api.<dominio>`; corrige DNS/ingress; `docker compose restart caddy` |
| `pull` con 401/denied | paquete GHCR privado y servidor sin login | `docker login ghcr.io` en el servidor (token con `read:packages`) |
| API `unhealthy` tras deploy | migración/esquema, variable obligatoria vacía | `docker compose logs api`; el deploy debería haber hecho rollback |
| Evolution `unhealthy` | healthcheck autenticado o config de BD | `docker compose logs evolution`; la **sesión** de WhatsApp se comprueba aparte: `./check-evolution.sh` (exit 2 = hay instancias pero ninguna `open`) |
| `backup` systemd en failed | offsite sin configurar o media rota | `journalctl -u makingsmiles-backup -n 50`; revisa `BACKUP_DEST`, `BACKUP_AGE_RECIPIENT`, `known_hosts` y permisos root de `.ssh` |
| deploy abortado: `.env` inválido | placeholders o secretos débiles | `./validate-env.sh /opt/makingsmiles/.env` y corrige lo que liste |
| `/media` 403/401 | URL firmada caducada (TTL corto a propósito) | pedir URL nueva al endpoint de la API; no alargar el TTL |
| SSE se corta | proxy intermedio con timeout/buffering | el SSE va directo a `api.<dominio>` (nunca por Vercel). Ver INFRA §5 |

## Seguridad — reglas que no se negocian

- Nada de secretos en git. `.env` solo en el servidor, modo 600.
- Postgres/Redis/Evolution **sin puertos publicados**. Si necesitas `psql`,
  entra por `docker compose exec postgres psql`.
- El usuario de deploy **no está en el grupo docker** (sería root): solo puede
  ejecutar `sudo /usr/local/sbin/makingsmiles-deploy <acción>`, y el wrapper corre
  copias root-owned de los scripts en `/usr/local/lib/makingsmiles`. Si cambian los
  scripts en el repo hay que reinstalarlos como root (re-ejecutar bootstrap). SSH
  solo con clave, `PermitRootLogin no` y `PasswordAuthentication no` (el bootstrap
  lo aplica si le pasas `--ssh-pubkey`).
- SSH `22` restringido por Security List **y** por `ufw` a tu IP (`--admin-cidr`).
- `ufw` + Security List + fail2ban: las tres capas.
- El staging no debe contener datos reales de pacientes salvo autorización
  explícita y base legal; ver el bloqueo de Vercel Hobby en INFRA §6.
