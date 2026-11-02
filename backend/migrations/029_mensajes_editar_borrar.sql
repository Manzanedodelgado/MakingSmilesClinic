-- 029 · Editar/borrar mensajes salientes de WhatsApp (solo si aún no se han leído,
-- "delete for everyone" real vía Evolution — no un borrado local que finge que se borró).
ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS eliminado BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS editado BOOLEAN NOT NULL DEFAULT FALSE;
