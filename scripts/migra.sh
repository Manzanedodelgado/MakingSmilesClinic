#!/usr/bin/env bash
# Único camino para escribir en la BD de producción.
#
# No existe para ser cómodo: existe porque prometí "copia verificada antes de escribir en
# producción" y esa promesa me la salto. Esto no se la salta. Si no hay copia fresca y
# comprobada, la migración NO se ejecuta.
#
#   bash scripts/migra.sh backend/migrations/050_lo_que_sea.sql
set -euo pipefail

SQL="${1:?uso: migra.sh <fichero.sql>}"
[ -f "$SQL" ] || { echo "BLOQUEO: no existe $SQL"; exit 1; }

# Una migración ya anotada NO se repite: muchas son de DATOS (p. ej. 064 vacía `pagos`) y
# volver a lanzarlas borra o duplica lo que hay hoy (23-oct-2026). Para repetir una a
# sabiendas: MIGRA_REPETIR=1 bash scripts/migra.sh <fichero.sql>
NOMBRE_SQL="$(basename "$SQL")"
case "$NOMBRE_SQL" in *"'"*) echo "BLOQUEO: nombre de fichero con comilla"; exit 1 ;; esac
YA=$(docker exec makingsmiles-postgres psql -U makingsmiles -d makingsmiles -Atc \
  "select aplicada_en || ' (' || origen || ')' from migraciones_aplicadas where nombre = '$NOMBRE_SQL'" 2>/dev/null || true)
if [ -n "$YA" ] && [ "${MIGRA_REPETIR:-0}" != "1" ]; then
  echo "BLOQUEO: $NOMBRE_SQL ya está aplicada: $YA. No se repite (MIGRA_REPETIR=1 para forzar)."
  exit 1
fi

DEST="$HOME/makingsmiles-backups/pre-migracion-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DEST"
echo "== 1/4 copia de seguridad previa =="
docker exec makingsmiles-postgres pg_dump -U makingsmiles -d makingsmiles -Fc > "$DEST/makingsmiles.dump"

echo "== 2/4 la copia se comprueba, no se supone =="
BYTES=$(stat -c%s "$DEST/makingsmiles.dump")
if [ "$BYTES" -lt 10000000 ]; then
  echo "BLOQUEO: la copia pesa $BYTES bytes, demasiado poco. No se migra."; exit 1
fi
if ! pg_restore --list "$DEST/makingsmiles.dump" > "$DEST/indice.txt" 2>"$DEST/err.txt"; then
  echo "BLOQUEO: la copia no se puede leer (pg_restore --list falla). No se migra."
  head -3 "$DEST/err.txt"; exit 1
fi
TABLAS=$(grep -c "TABLE DATA" "$DEST/indice.txt" || true)
if [ "${TABLAS:-0}" -lt 50 ]; then
  echo "BLOQUEO: la copia solo trae $TABLAS tablas con datos. No se migra."; exit 1
fi
echo "   copia OK: $DEST/makingsmiles.dump ($BYTES bytes, $TABLAS tablas)"

echo "== 3/5 aplicando $SQL =="
docker exec -i makingsmiles-postgres psql -U makingsmiles -d makingsmiles -v ON_ERROR_STOP=1 < "$SQL"

# Anotar que se aplicó. Sin esto no hay forma de saber si la BD va por detrás del código:
# el 18-oct-2026 se desplegó un backend que usaba cuatro columnas de las migraciones 091 y
# 092 sin haberlas aplicado — 16 errores UndefinedColumn en producción y leer un tratamiento
# rompía. Nadie se enteró porque no existía este cuaderno. Va DESPUÉS del psql y con
# ON_ERROR_STOP arriba: si la migración falla, el script muere y no se anota nada.
echo "== 4/5 anotando en el registro =="
docker exec -i makingsmiles-postgres psql -U makingsmiles -d makingsmiles -v ON_ERROR_STOP=1 \
  -c "insert into migraciones_aplicadas (nombre, origen, nota)
      values ('$(basename "$SQL")', 'migra.sh', 'Copia previa: $DEST/makingsmiles.dump')
      on conflict (nombre) do update set aplicada_en = now(), origen = 'migra.sh',
                                         nota = excluded.nota" \
  || echo "   AVISO: la migración SÍ se aplicó pero no se pudo anotar (¿falta la tabla migraciones_aplicadas? -> backend/migrations/093_registro_migraciones.sql)"

echo "== 5/5 hecho =="
echo "Para deshacer:  pg_restore -c -d makingsmiles $DEST/makingsmiles.dump"
