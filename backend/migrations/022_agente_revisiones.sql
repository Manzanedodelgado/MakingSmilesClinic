-- Bandeja IA: cola de aprobación humana para las respuestas de Alex.
-- Cuando agente.alex.revision_humana está activo, Alex NO envía directo — deja la
-- propuesta aquí (estado='pendiente') hasta que un humano la aprueba tal cual, la aprueba
-- editada (estado='editada', y esa corrección se reutiliza como ejemplo few-shot futuro
-- en _ejemplos_activos) o la descarta. Con revision_humana=false (default) no se inserta
-- nada aquí — comportamiento actual sin cambios.
BEGIN;

CREATE TABLE IF NOT EXISTS agente_revisiones (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    centro_id INTEGER NOT NULL REFERENCES centros(id),
    conversacion_id INTEGER NOT NULL REFERENCES conversaciones(id),
    telefono VARCHAR(50) NOT NULL,
    entrada VARCHAR(2000) NOT NULL,
    propuesta VARCHAR(2000) NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente',
    respuesta_final VARCHAR(2000),
    revisado_por INTEGER REFERENCES usuarios(id),
    revisado_at TIMESTAMP WITHOUT TIME ZONE,
    CONSTRAINT agente_revisiones_estado_check
        CHECK (estado IN ('pendiente', 'aprobada', 'editada', 'descartada'))
);
CREATE INDEX IF NOT EXISTS ix_agente_revisiones_centro_estado ON agente_revisiones (centro_id, estado);

COMMIT;
