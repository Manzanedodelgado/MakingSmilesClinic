-- Se ejecuta SOLO cuando el volumen pgdata está vacío (primer arranque).
-- Evolution API v2 guarda su estado en una base de datos propia (no en el
-- esquema public de la app). Idempotente por si el script se re-ejecuta.
SELECT 'CREATE DATABASE evolution OWNER ' || quote_ident(current_user)
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'evolution')\gexec
