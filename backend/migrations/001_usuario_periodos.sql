-- Fase 1 · Periodos laborales por persona
-- usuarios = identidad fija; cada etapa alta/baja pasa a usuario_periodos;
-- el económico de colaborador cuelga del periodo (no del usuario).
-- Idempotente y transaccional. No pierde datos (los id de colaboradores se mantienen).
BEGIN;

-- 1) Tabla de periodos
CREATE TABLE IF NOT EXISTS usuario_periodos (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    orden INTEGER NOT NULL DEFAULT 0,          -- 0 = etapa original; 1,2… = reactivaciones
    staff_tipo VARCHAR(40),
    tipo_contrato VARCHAR(40),
    fecha_alta DATE,
    fecha_baja DATE,                            -- vacía = abierto = activo
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_usuario_periodos_usuario_id ON usuario_periodos(usuario_id);
CREATE INDEX IF NOT EXISTS ix_usuario_periodos_orden ON usuario_periodos(orden);
CREATE INDEX IF NOT EXISTS ix_usuario_periodos_staff_tipo ON usuario_periodos(staff_tipo);

-- 2) Columnas nuevas
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS nif VARCHAR(20);
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS periodo_id INTEGER;

-- 3) Un periodo (orden 0) por cada usuario, con sus datos actuales
INSERT INTO usuario_periodos (usuario_id, orden, staff_tipo, tipo_contrato, fecha_alta, fecha_baja, created_at, updated_at)
SELECT id, 0, staff_tipo, tipo_contrato, fecha_alta, fecha_baja, now(), now()
FROM usuarios
WHERE NOT EXISTS (SELECT 1 FROM usuario_periodos p WHERE p.usuario_id = usuarios.id);

-- 4) Cada colaborador cuelga del periodo (orden 0) de su usuario
UPDATE colaboradores c
SET periodo_id = p.id
FROM user_collaborator uc
JOIN usuario_periodos p ON p.usuario_id = uc.usuario_id AND p.orden = 0
WHERE uc.colaborador_id = c.id AND c.periodo_id IS NULL;

-- 5) Mover NIF a la persona (identidad)
UPDATE usuarios u
SET nif = c.nif
FROM user_collaborator uc
JOIN colaboradores c ON c.id = uc.colaborador_id
WHERE uc.usuario_id = u.id AND c.nif IS NOT NULL AND u.nif IS NULL;

-- 6) FK + unicidad de periodo_id
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='colaboradores_periodo_id_fkey') THEN
    ALTER TABLE colaboradores ADD CONSTRAINT colaboradores_periodo_id_fkey
      FOREIGN KEY (periodo_id) REFERENCES usuario_periodos(id);
  END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS ix_colaboradores_periodo_id ON colaboradores(periodo_id);

-- 7) Limpiar lo viejo (ya migrado)
ALTER TABLE colaboradores DROP COLUMN IF EXISTS nif;
ALTER TABLE usuarios DROP COLUMN IF EXISTS fecha_alta;
ALTER TABLE usuarios DROP COLUMN IF EXISTS fecha_baja;
ALTER TABLE usuarios DROP COLUMN IF EXISTS staff_tipo;
ALTER TABLE usuarios DROP COLUMN IF EXISTS tipo_contrato;
ALTER TABLE usuarios DROP COLUMN IF EXISTS activo;
DROP TABLE IF EXISTS user_collaborator;

COMMIT;
