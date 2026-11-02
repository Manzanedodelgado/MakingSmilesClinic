-- 011 · Estados de presupuesto para el flujo de aceptación/anulación.
--   Protocolo: crear → entregar (imprimir/WhatsApp) → reeditar/anular; aceptar todo
--   (→ aceptado, bloqueado para editar; reabrir lo devuelve a entregado) o aceptar
--   parcial (→ aceptado_parcial; las líneas no aceptadas se anulan o pasan a un
--   presupuesto nuevo). Catálogo global (sin centro). ids 2 y 6 estaban libres.
INSERT INTO estados_presupuesto (id, codigo, nombre, orden, activo, created_at, updated_at)
VALUES (2, 'anulado',          'Anulado',          6, true, now(), now()),
       (6, 'aceptado_parcial', 'Aceptado parcial', 7, true, now(), now())
ON CONFLICT (id) DO NOTHING;
