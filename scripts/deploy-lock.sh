#!/bin/bash
# Candado de despliegue. Se «source»a al principio de deploy-web.sh y deploy-backend.sh:  source <ruta>/deploy-lock.sh "nombre"
# Varias sesiones de Claude comparten este árbol; dos despliegues a la vez (o uno que compila ficheros a medias de otra
# sesión) ya causaron incidentes (28-oct, 31-oct). Aquí: un solo despliegue a la vez, y constancia de quién, cuándo y qué
# ficheros SIN commitear entran en la compilación.
exec 9>/tmp/makingsmiles-deploy.lock
if ! flock -n 9; then
  echo "BLOQUEO: hay otro despliegue en curso → $(cat /tmp/makingsmiles-deploy.info 2>/dev/null || echo 'sin datos'). Espera a que termine." >&2
  exit 1
fi
RAIZ_REPO="$(git rev-parse --show-toplevel)"
INFO="$(date '+%F %T') $1 pid=$$ rama=$(git -C "$RAIZ_REPO" rev-parse --abbrev-ref HEAD) commit=$(git -C "$RAIZ_REPO" rev-parse --short HEAD)"
echo "$INFO" > /tmp/makingsmiles-deploy.info
echo "$INFO" >> "$HOME/makingsmiles-despliegues.log"
SIN_COMMIT="$(git -C "$RAIZ_REPO" status --short | grep -v '^??' || true)"
if [ -n "$SIN_COMMIT" ]; then
  echo "AVISO: la compilación incluirá estos cambios SIN commitear (de cualquier sesión):"
  echo "$SIN_COMMIT" | head -20
  echo "$SIN_COMMIT" | sed 's/^/    sin commitear: /' >> "$HOME/makingsmiles-despliegues.log"
fi
