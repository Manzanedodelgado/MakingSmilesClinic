-- 090: Saldo consolidado por paciente (deuda real = tratamientos - descuentos - pagos)
-- Se actualiza automáticamente con triggers en tratamientos_realizados y pagos.

-- Tabla de saldo por paciente (una fila por paciente)
CREATE TABLE IF NOT EXISTS saldo_paciente (
    paciente_id INTEGER PRIMARY KEY REFERENCES pacientes(id) ON DELETE CASCADE,
    centro_id INTEGER NOT NULL REFERENCES centros(id),
    total_tratamientos NUMERIC(12,2) NOT NULL DEFAULT 0,   -- Σ importe tratamientos realizados
    total_descuentos NUMERIC(12,2) NOT NULL DEFAULT 0,     -- Σ descuentos aplicados
    total_pagado NUMERIC(12,2) NOT NULL DEFAULT 0,         -- Σ pagos (importe bruto)
    saldo NUMERIC(12,2) NOT NULL DEFAULT 0,                -- = tratamientos - descuentos - pagos (+ = debe, - = a favor)
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_saldo_paciente_centro ON saldo_paciente(centro_id);
CREATE INDEX IF NOT EXISTS ix_saldo_paciente_saldo ON saldo_paciente(saldo) WHERE saldo <> 0;

-- Función para recalcular el saldo de un paciente
CREATE OR REPLACE FUNCTION recalcular_saldo_paciente(p_paciente_id INTEGER) RETURNS VOID AS $$
DECLARE
    v_centro_id INTEGER;
    v_tratamientos NUMERIC(12,2);
    v_descuentos NUMERIC(12,2);
    v_pagado NUMERIC(12,2);
BEGIN
    -- Obtener centro del paciente
    SELECT centro_id INTO v_centro_id FROM pacientes WHERE id = p_paciente_id;
    IF v_centro_id IS NULL THEN RETURN; END IF;

    -- Sumar tratamientos realizados (estado 5 = Realizado, no anulados)
    SELECT COALESCE(SUM(importe), 0), COALESCE(SUM(descuento), 0)
    INTO v_tratamientos, v_descuentos
    FROM tratamientos_realizados
    WHERE paciente_id = p_paciente_id AND estado_id = 5;

    -- Sumar pagos (no anulados)
    SELECT COALESCE(SUM(importe), 0)
    INTO v_pagado
    FROM pagos
    WHERE paciente_id = p_paciente_id AND anulado = FALSE;

    -- Insertar o actualizar
    INSERT INTO saldo_paciente (paciente_id, centro_id, total_tratamientos, total_descuentos, total_pagado, saldo, updated_at)
    VALUES (p_paciente_id, v_centro_id, v_tratamientos, v_descuentos, v_pagado,
            v_tratamientos - v_descuentos - v_pagado, NOW())
    ON CONFLICT (paciente_id) DO UPDATE SET
        total_tratamientos = EXCLUDED.total_tratamientos,
        total_descuentos = EXCLUDED.total_descuentos,
        total_pagado = EXCLUDED.total_pagado,
        saldo = EXCLUDED.saldo,
        updated_at = NOW();
END;
$$ LANGUAGE plpgsql;

-- Trigger en tratamientos_realizados
CREATE OR REPLACE FUNCTION trg_saldo_tratamiento() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM recalcular_saldo_paciente(OLD.paciente_id);
    ELSE
        PERFORM recalcular_saldo_paciente(NEW.paciente_id);
        IF TG_OP = 'UPDATE' AND OLD.paciente_id <> NEW.paciente_id THEN
            PERFORM recalcular_saldo_paciente(OLD.paciente_id);
        END IF;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_saldo_tratamiento ON tratamientos_realizados;
CREATE TRIGGER trg_saldo_tratamiento
    AFTER INSERT OR UPDATE OR DELETE ON tratamientos_realizados
    FOR EACH ROW EXECUTE FUNCTION trg_saldo_tratamiento();

-- Trigger en pagos
CREATE OR REPLACE FUNCTION trg_saldo_pago() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM recalcular_saldo_paciente(OLD.paciente_id);
    ELSE
        PERFORM recalcular_saldo_paciente(NEW.paciente_id);
        IF TG_OP = 'UPDATE' AND OLD.paciente_id IS DISTINCT FROM NEW.paciente_id THEN
            IF OLD.paciente_id IS NOT NULL THEN
                PERFORM recalcular_saldo_paciente(OLD.paciente_id);
            END IF;
        END IF;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_saldo_pago ON pagos;
CREATE TRIGGER trg_saldo_pago
    AFTER INSERT OR UPDATE OR DELETE ON pagos
    FOR EACH ROW EXECUTE FUNCTION trg_saldo_pago();

-- Poblar con datos actuales (puede tardar unos segundos)
INSERT INTO saldo_paciente (paciente_id, centro_id, total_tratamientos, total_descuentos, total_pagado, saldo)
SELECT
    p.id,
    p.centro_id,
    COALESCE(t.total, 0),
    COALESCE(t.desc, 0),
    COALESCE(pg.total, 0),
    COALESCE(t.total, 0) - COALESCE(t.desc, 0) - COALESCE(pg.total, 0)
FROM pacientes p
LEFT JOIN (
    SELECT paciente_id, SUM(importe) as total, SUM(COALESCE(descuento, 0)) as desc
    FROM tratamientos_realizados WHERE estado_id = 5
    GROUP BY paciente_id
) t ON t.paciente_id = p.id
LEFT JOIN (
    SELECT paciente_id, SUM(importe) as total
    FROM pagos WHERE anulado = FALSE
    GROUP BY paciente_id
) pg ON pg.paciente_id = p.id
WHERE COALESCE(t.total, 0) > 0 OR COALESCE(pg.total, 0) > 0
ON CONFLICT (paciente_id) DO UPDATE SET
    total_tratamientos = EXCLUDED.total_tratamientos,
    total_descuentos = EXCLUDED.total_descuentos,
    total_pagado = EXCLUDED.total_pagado,
    saldo = EXCLUDED.saldo,
    updated_at = NOW();

-- Comentarios
COMMENT ON TABLE saldo_paciente IS 'Saldo consolidado por paciente. Actualizado automáticamente por triggers.';
COMMENT ON COLUMN saldo_paciente.saldo IS 'Deuda real: tratamientos - descuentos - pagos. Positivo = debe, negativo = saldo a favor.';
