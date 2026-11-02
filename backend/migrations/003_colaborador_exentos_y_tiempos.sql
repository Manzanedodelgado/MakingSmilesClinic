-- Colaboradores · exentos múltiples + tiempos de tipo de cita por colaborador
--   colaborador_tratamiento_exento : N:M colaborador↔tratamiento exento de comisión
--                                    (el precio único sigue en colaboradores.precio_tratamiento_exento)
--   colaborador_tipo_cita          : duración (min) de cada tipo de cita por colaborador (sin default)
-- Migra el exento único actual (colaboradores.tratamiento_exento_id) a la tabla N:M y elimina la columna.
-- Idempotente y transaccional.
BEGIN;

CREATE TABLE IF NOT EXISTS colaborador_tratamiento_exento (
  colaborador_id  INTEGER NOT NULL REFERENCES colaboradores(id) ON DELETE CASCADE,
  tratamiento_id  INTEGER NOT NULL REFERENCES tratamientos(id) ON DELETE CASCADE,
  created_at      TIMESTAMP NOT NULL DEFAULT now(),
  updated_at      TIMESTAMP NOT NULL DEFAULT now(),
  PRIMARY KEY (colaborador_id, tratamiento_id)
);
CREATE INDEX IF NOT EXISTS ix_cte_colaborador ON colaborador_tratamiento_exento (colaborador_id);
CREATE INDEX IF NOT EXISTS ix_cte_tratamiento ON colaborador_tratamiento_exento (tratamiento_id);

CREATE TABLE IF NOT EXISTS colaborador_tipo_cita (
  colaborador_id  INTEGER NOT NULL REFERENCES colaboradores(id) ON DELETE CASCADE,
  tipo_cita_id    INTEGER NOT NULL REFERENCES tipos_cita(id) ON DELETE CASCADE,
  duracion_min    INTEGER NOT NULL,
  created_at      TIMESTAMP NOT NULL DEFAULT now(),
  updated_at      TIMESTAMP NOT NULL DEFAULT now(),
  PRIMARY KEY (colaborador_id, tipo_cita_id)
);
CREATE INDEX IF NOT EXISTS ix_ctc_colaborador ON colaborador_tipo_cita (colaborador_id);
CREATE INDEX IF NOT EXISTS ix_ctc_tipo_cita ON colaborador_tipo_cita (tipo_cita_id);

-- Si las tablas las creó antes el create_all de SQLModel (sin server default), garantízalo:
ALTER TABLE colaborador_tratamiento_exento ALTER COLUMN created_at SET DEFAULT now(), ALTER COLUMN updated_at SET DEFAULT now();
ALTER TABLE colaborador_tipo_cita          ALTER COLUMN created_at SET DEFAULT now(), ALTER COLUMN updated_at SET DEFAULT now();

-- Migrar el exento único existente (si la columna aún existe)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = 'colaboradores' AND column_name = 'tratamiento_exento_id') THEN
    INSERT INTO colaborador_tratamiento_exento (colaborador_id, tratamiento_id)
      SELECT id, tratamiento_exento_id FROM colaboradores
      WHERE tratamiento_exento_id IS NOT NULL
      ON CONFLICT DO NOTHING;
    ALTER TABLE colaboradores DROP COLUMN tratamiento_exento_id;
  END IF;
END $$;

COMMIT;
