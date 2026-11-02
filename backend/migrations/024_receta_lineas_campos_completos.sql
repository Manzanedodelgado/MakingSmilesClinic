-- Migración: Agregar campos completos a receta_lineas
-- Fecha: 25-08-2026
-- Descripción: Agregar pauta, duracion, envases, unidades a la tabla receta_lineas
--              para soportar el flujo completo de recetas (6 campos medicamento/posologia/pauta/duracion/envases/unidades)

BEGIN;

-- Agregar las 4 columnas faltantes a receta_lineas
-- pauta: cuando tomar (ej: "cada 8 horas", "una vez al día")
-- duracion: cuánto tiempo (ej: "1 semana", "10 días")
-- envases: número de envases del medicamento (ej: 2 cajas)
-- unidades: unidades por envase (ej: 20 comprimidos)

ALTER TABLE public.receta_lineas
ADD COLUMN IF NOT EXISTS pauta character varying(300),
ADD COLUMN IF NOT EXISTS duracion character varying(60),
ADD COLUMN IF NOT EXISTS envases integer,
ADD COLUMN IF NOT EXISTS unidades integer;

-- Crear índice sobre orden_dispensacion si no existe (para ordenar líneas en la receta)
CREATE INDEX IF NOT EXISTS ix_receta_lineas_orden ON public.receta_lineas(receta_id, orden_dispensacion);

COMMIT;
