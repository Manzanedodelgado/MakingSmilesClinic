-- 039 · Identidad de la cita — id_cita + fecha_hora_creacion / fecha_hora_modificacion
-- Regla (jmd, 12-oct-2026):
--   · id_cita se asigna UNA vez, al crear la cita, y no cambia nunca al modificarla (hora,
--     día, estado…). Copiar una cita de estado final (finalizada, cancelada, anulada) —lo
--     que hace el personal para abrir la nueva del paciente— es una cita NUEVA: id_cita nuevo.
--   · fecha_hora_creacion se fija al nacer el id_cita (inmutable); fecha_hora_modificacion
--     marca la última modificación y se renueva en cada UPDATE.
-- La asignación infranqueable vive en application/services/cita_reglas.py (before_insert /
-- before_update, igual que el resto de reglas de la cita). Esta migración aporta la secuencia,
-- el DEFAULT para inserts hechos a SQL directo y el backfill de la historia: Getite dejó
-- id_cita lleno en 48.387 filas (a veces un mismo hilo para varias citas de tratamiento) y la
-- web nueva no la asignaba — 18 citas creadas desde el 5-oct-2026 se quedaron sin id.
-- OJO: hay que aplicarse ANTES de desplegar el backend nuevo (sin estas columnas el INSERT
-- de una cita fallaría). Idempotente: se puede reejecutar.
BEGIN;

CREATE SEQUENCE IF NOT EXISTS citas_id_cita_seq;

-- Por encima de lo máximo ya usado (histórico: 54218) y de lo que la propia secuencia haya
-- emitido ya (re-ejecución): nunca hacia atrás.
SELECT setval('citas_id_cita_seq',
              GREATEST((SELECT COALESCE(MAX(id_cita), 0) FROM citas),
                       (SELECT last_value FROM citas_id_cita_seq)) + 1,
              false);

ALTER TABLE citas ALTER COLUMN id_cita SET DEFAULT nextval('citas_id_cita_seq');
ALTER SEQUENCE citas_id_cita_seq OWNED BY citas.id_cita;

ALTER TABLE citas ADD COLUMN IF NOT EXISTS fecha_hora_creacion timestamp;
ALTER TABLE citas ADD COLUMN IF NOT EXISTS fecha_hora_modificacion timestamp;

-- Historia (lo mejor que se sabe de cada fila):
--   alta      = fecha_alta de Getite si existe, si no created_at del import.
--   modificación = updated_at (solo se fijaba al insertar, así que para las filas viejas
--   coincide con el alta: antes de esta migración nadie registraba cambios).
UPDATE citas
   SET fecha_hora_creacion     = COALESCE(fecha_alta, created_at),
       fecha_hora_modificacion = COALESCE(updated_at, created_at)
 WHERE fecha_hora_creacion IS NULL;

-- Las citas creadas por la web nueva sin id_cita.
UPDATE citas SET id_cita = nextval('citas_id_cita_seq')
 WHERE id_cita IS NULL;

COMMIT;
