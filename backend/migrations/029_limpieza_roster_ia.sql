-- 029 · Limpieza del roster de IA heredado.
--
-- El área de IAs arrastraba DOS rosters incompatibles:
--   · el del modelo de datos (AURA/VISTA/ESCUCHA/PLUMA/FORENSE), 5 tablas creadas de una
--     visión que nunca se implementó: 0 filas y 0 referencias en el código;
--   · el real (Alex/Victor/Gestor), que es el que funciona.
-- Nadie sabía de qué se hablaba. El roster queda fijado en domain/config/agentes.py.
--
-- Se BORRA lo de los agentes que ya no existen; se CONSERVA lo que el nuevo Aura va a usar:
--   transcripciones → Aura escucha la consulta
--   briefings_aura  → Aura prepara la consulta
--
-- Verificado antes de ejecutar: las cinco tablas tienen 0 filas y ninguna referencia en el
-- código fuera de la definición del modelo. No se pierde ningún dato.

BEGIN;

DO $$
DECLARE n INT;
BEGIN
  SELECT (SELECT COUNT(*) FROM sesiones_agente)
       + (SELECT COUNT(*) FROM analisis_imagen)
       + (SELECT COUNT(*) FROM outputs_clinicos) INTO n;
  IF n > 0 THEN
    RAISE EXCEPTION 'Abortada: las tablas a borrar tienen % filas; ya NO están vacías', n;
  END IF;
END $$;

DROP TABLE IF EXISTS outputs_clinicos;   -- PLUMA (agente inexistente)
DROP TABLE IF EXISTS analisis_imagen;    -- VISTA (agente inexistente)
DROP TABLE IF EXISTS sesiones_agente;    -- orquesta de los 5 agentes viejos

COMMIT;
