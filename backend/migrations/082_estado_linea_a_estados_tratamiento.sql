-- 082 · presupuesto_lineas.estado apunta a estados_tratamiento (jmd, 17-oct-2026)
-- Orden del usuario: los estados de presupuesto van en la cabecera (presupuestos.estado_id →
-- estados_presupuesto); la línea lleva el estado del TRATAMIENTO (id de estados_tratamiento).
-- Sustituye al catálogo estados_linea_presupuesto de 081, que se elimina. Reparto:
--   1 Pendiente → 1 Presupuestado
--   2 Aceptada  → 5 Realizado si tiene acto realizado y ninguna fase en el plan; si no 3 Previsto
--   3 Anulada   → 7 Cancelado si su presupuesto llegó a aceptarse (3/4/5/6/7); si no 8 Anulado
BEGIN;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM presupuesto_lineas WHERE estado NOT IN (1, 2, 3)) THEN
        RAISE EXCEPTION '082: hay líneas con estado fuera de 1/2/3';
    END IF;
END $$;
ALTER TABLE presupuesto_lineas DROP CONSTRAINT presupuesto_lineas_estado_fkey;
UPDATE presupuesto_lineas l SET estado = CASE l.estado
    WHEN 1 THEN 1
    WHEN 2 THEN CASE WHEN EXISTS (SELECT 1 FROM tratamientos_realizados tr
                                  WHERE tr.presupuesto_linea_id = l.id AND tr.estado_id = 5)
                      AND NOT EXISTS (SELECT 1 FROM tratamientos_previstos tp WHERE tp.presupuesto_linea_id = l.id)
                     THEN 5 ELSE 3 END
    WHEN 3 THEN CASE WHEN p.estado_id IN (3, 4, 5, 6, 7) THEN 7 ELSE 8 END
  END
  FROM presupuestos p WHERE p.id = l.presupuesto_id;
ALTER TABLE presupuesto_lineas
    ADD CONSTRAINT presupuesto_lineas_estado_fkey FOREIGN KEY (estado) REFERENCES estados_tratamiento(id);
COMMENT ON COLUMN presupuesto_lineas.estado IS 'id de estados_tratamiento (nombre histórico).';
DROP TABLE estados_linea_presupuesto;
COMMIT;
