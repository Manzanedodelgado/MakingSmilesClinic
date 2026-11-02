-- Migración: Agregar consentimiento_tipo a tabla tratamientos
-- Fecha: 25-08-2026
-- Descripción: Campo para referenciar qué tipo de consentimiento requiere cada tratamiento
--              (implante, extraccion, ortodoncia, etc.) en función de PLANTILLAS del servicio

BEGIN;

-- Agregar columna consentimiento_tipo si no existe
ALTER TABLE public.tratamientos
ADD COLUMN IF NOT EXISTS consentimiento_tipo character varying(40);

-- Crear índice para búsqueda rápida por tipo
CREATE INDEX IF NOT EXISTS ix_tratamientos_consentimiento_tipo ON public.tratamientos(consentimiento_tipo);

COMMIT;
