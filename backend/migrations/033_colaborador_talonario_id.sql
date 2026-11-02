-- Agregar columna talonario_id a colaboradores
ALTER TABLE colaboradores
ADD COLUMN talonario_id INTEGER REFERENCES talonarios(id) ON DELETE SET NULL;

CREATE INDEX ix_colaboradores_talonario_id ON colaboradores(talonario_id);
