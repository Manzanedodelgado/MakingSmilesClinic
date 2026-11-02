-- 004 · Toda la config de agenda pasa a ser POR AGENDA.
-- Se añade agenda_id a estados_cita, gabinetes y colaborador_horarios,
-- y vista_defecto a agendas (la granularidad ya vivía en agendas.intervalo_min).
ALTER TABLE estados_cita        ADD COLUMN IF NOT EXISTS agenda_id INTEGER REFERENCES agendas(id);
ALTER TABLE gabinetes           ADD COLUMN IF NOT EXISTS agenda_id INTEGER REFERENCES agendas(id);
ALTER TABLE colaborador_horarios ADD COLUMN IF NOT EXISTS agenda_id INTEGER REFERENCES agendas(id);
ALTER TABLE agendas             ADD COLUMN IF NOT EXISTS vista_defecto VARCHAR(20);

CREATE INDEX IF NOT EXISTS ix_estados_cita_agenda_id ON estados_cita(agenda_id);
CREATE INDEX IF NOT EXISTS ix_gabinetes_agenda_id ON gabinetes(agenda_id);
CREATE INDEX IF NOT EXISTS ix_colaborador_horarios_agenda_id ON colaborador_horarios(agenda_id);

-- Datos existentes → primera agenda de su centro (orden, luego id).
UPDATE estados_cita e SET agenda_id = (
  SELECT a.id FROM agendas a WHERE a.centro_id = e.centro_id ORDER BY a.orden NULLS LAST, a.id LIMIT 1
) WHERE e.agenda_id IS NULL;
UPDATE gabinetes g SET agenda_id = (
  SELECT a.id FROM agendas a WHERE a.centro_id = g.centro_id ORDER BY a.orden NULLS LAST, a.id LIMIT 1
) WHERE g.agenda_id IS NULL;
UPDATE colaborador_horarios h SET agenda_id = (
  SELECT a.id FROM agendas a WHERE a.centro_id = h.centro_id ORDER BY a.orden NULLS LAST, a.id LIMIT 1
) WHERE h.agenda_id IS NULL;
UPDATE tipos_cita t SET agenda_id = (
  SELECT a.id FROM agendas a WHERE a.centro_id = t.centro_id ORDER BY a.orden NULLS LAST, a.id LIMIT 1
) WHERE t.agenda_id IS NULL;
