-- Migration 030: Soporte para los 3 caminos de consulta clínica
-- A2: Campo consentimiento_tipo en tratamientos
-- A3: Tabla recomendaciones_paciente

-- A2: Añadir columna consentimiento_tipo a tratamientos
ALTER TABLE tratamientos
ADD COLUMN consentimiento_tipo VARCHAR(40) DEFAULT NULL;

COMMENT ON COLUMN tratamientos.consentimiento_tipo IS
  'Tipo de consentimiento COEM requerido (implante, endodoncia, ortodoncia, etc.) o NULL si no requiere';

-- A3: Crear tabla recomendaciones_paciente
CREATE TABLE recomendaciones_paciente (
    id SERIAL PRIMARY KEY,
    centro_id INTEGER NOT NULL REFERENCES centros(id) ON DELETE CASCADE,
    paciente_id INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
    cita_id INTEGER DEFAULT NULL REFERENCES citas(id) ON DELETE SET NULL,
    items JSONB DEFAULT NULL,  -- claves del catálogo marcadas como dict
    texto_generado TEXT DEFAULT NULL,
    archivo_url VARCHAR(500) DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_recomendaciones_paciente_centro_id ON recomendaciones_paciente(centro_id);
CREATE INDEX idx_recomendaciones_paciente_paciente_id ON recomendaciones_paciente(paciente_id);
CREATE INDEX idx_recomendaciones_paciente_cita_id ON recomendaciones_paciente(cita_id);

COMMENT ON TABLE recomendaciones_paciente IS
  'Recomendaciones seleccionadas al final de la consulta (Caminos 1, 2, 3)';
