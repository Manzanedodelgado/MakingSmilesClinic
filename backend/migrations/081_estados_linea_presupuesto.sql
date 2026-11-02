-- 081 · Estados de LÍNEA de presupuesto en su propio catálogo (jmd, 17-oct-2026)
-- Orden del usuario: presupuesto_lineas.estado se mantiene (con ese nombre) pero guarda el id de un
-- catálogo nuevo, distinto de estados_presupuesto (que es el de la cabecera).
--   1 pendiente · 2 aceptada · 3 anulada  (antes texto 'PENDIENTE' / 'ACEPTADA' / 'ANULADA')
BEGIN;
CREATE TABLE estados_linea_presupuesto (
    id         integer PRIMARY KEY,
    codigo     varchar(40) NOT NULL UNIQUE,
    nombre     varchar(80) NOT NULL,
    orden      integer NOT NULL DEFAULT 100,
    activo     boolean NOT NULL DEFAULT true,
    created_at timestamp NOT NULL DEFAULT now(),
    updated_at timestamp NOT NULL DEFAULT now()
);
COMMENT ON TABLE estados_linea_presupuesto IS 'Estados de una línea de presupuesto; presupuesto_lineas.estado guarda su id.';
INSERT INTO estados_linea_presupuesto (id, codigo, nombre, orden) VALUES
    (1, 'pendiente', 'Pendiente', 1),
    (2, 'aceptada',  'Aceptada',  2),
    (3, 'anulada',   'Anulada',   3);

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM presupuesto_lineas WHERE estado IS NULL OR estado NOT IN ('PENDIENTE','ACEPTADA','ANULADA')) THEN
        RAISE EXCEPTION '081: hay líneas con estado vacío o desconocido';
    END IF;
END $$;
ALTER TABLE presupuesto_lineas
    ALTER COLUMN estado TYPE integer USING CASE estado WHEN 'PENDIENTE' THEN 1 WHEN 'ACEPTADA' THEN 2 WHEN 'ANULADA' THEN 3 END,
    ALTER COLUMN estado SET DEFAULT 1,
    ALTER COLUMN estado SET NOT NULL,
    ADD CONSTRAINT presupuesto_lineas_estado_fkey FOREIGN KEY (estado) REFERENCES estados_linea_presupuesto(id);
CREATE INDEX ix_presupuesto_lineas_estado ON presupuesto_lineas (estado);
COMMENT ON COLUMN presupuesto_lineas.estado IS 'id de estados_linea_presupuesto (nombre histórico).';
COMMIT;
