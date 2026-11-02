-- 086 · Líneas de presupuestos caducados → 6 Caducado (jmd, 18-oct-2026)
-- La caducidad de 3 meses (Nuevo/Entregado → 2 Anulado, job _caducar_presupuestos) cambiaba solo la
-- cabecera. Desde ahora el job pasa también sus líneas Presupuestado a 6 Caducado; esto pone al día
-- las que ya estaban caducadas (45 presupuestos, 789 líneas).
BEGIN;
UPDATE presupuesto_lineas l SET estado = 6, updated_at = now()
  FROM presupuestos p
 WHERE p.id = l.presupuesto_id AND p.estado_id = 2 AND l.estado = 1;
COMMIT;
