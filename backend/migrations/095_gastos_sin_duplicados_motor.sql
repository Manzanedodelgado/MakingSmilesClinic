-- 095: facturas duplicadas por el motor de conciliación + candado para que no vuelva a pasar.
--
-- Por qué: el 11-ago y el 14-oct-2026 dos ejecuciones simultáneas del motor (lanzadas desde la
-- web: subida de extracto + botón Cuadrar, en workers distintos) generaron cada una la misma
-- autofactura para el mismo apunte, con menos de 1 s de diferencia. El motor comprueba
-- "¿existe ya?" antes de crear, pero las dos lo comprobaron antes de que la otra guardase.
-- Nada en la BD lo impedía: `gastos` no tenía restricción de identidad.
--
-- 1) Se borran SOLO las copias evidentes de la misma factura (mismo emisor, nº y total):
--    · las dos enlazadas al MISMO apunte → se queda una (la que tenga PDF; si no, la más antigua)
--    · una enlazada y otra suelta        → se queda la enlazada
--    Los grupos con la misma factura en apuntes DISTINTOS no se tocan: pueden ser facturas
--    distintas mal leídas (mismo nº) y lo decide el usuario.
-- 2) Índice único sobre lo que genera el motor (incidencia = generado_conciliacion): es donde
--    estaba el fallo. La ingesta por correo y la subida manual ya deduplican por identidad.
BEGIN;

CREATE TEMP TABLE _g ON COMMIT DROP AS
SELECT id, centro_id, movimiento_id,
       coalesce(nullif(cif_emisor, ''), proveedor_extraido, '') AS emisor,
       numero_factura, total,
       (coalesce(archivo_pdf_url, '') <> '') AS tiene_pdf
FROM gastos
WHERE coalesce(numero_factura, '') <> '';

-- a) copias enlazadas al mismo apunte
CREATE TEMP TABLE _borrar ON COMMIT DROP AS
SELECT id FROM (
    SELECT id, row_number() OVER (PARTITION BY centro_id, emisor, numero_factura, total, movimiento_id
                                  ORDER BY tiene_pdf DESC, id) AS rn
    FROM _g WHERE movimiento_id IS NOT NULL) t
WHERE rn > 1;

-- b) copia suelta cuando la misma factura ya está enlazada
INSERT INTO _borrar
SELECT s.id FROM _g s
WHERE s.movimiento_id IS NULL
  AND EXISTS (SELECT 1 FROM _g e WHERE e.movimiento_id IS NOT NULL AND e.centro_id = s.centro_id
              AND e.emisor = s.emisor AND e.numero_factura = s.numero_factura AND e.total = s.total);

-- Respaldo de lo que se borra (recuperable sin restaurar la BD entera)
CREATE TABLE IF NOT EXISTS _bak_095_gastos_duplicados AS SELECT * FROM gastos WHERE false;
INSERT INTO _bak_095_gastos_duplicados SELECT g.* FROM gastos g JOIN _borrar b ON b.id = g.id;

DELETE FROM gastos WHERE id IN (SELECT id FROM _borrar);

-- 3) IGS202601 (Irene García Sanz, 1.200 €) salió dos veces el 11-ago por la misma carrera.
--    El 22-ene-2026 hubo DOS pagos reales a Irene de 1.200 € (apuntes 4715 y 5332; el saldo del
--    banco los distingue). La copia (gasto 2388) estaba enlazada a una transferencia a OTRA
--    persona (apunte 4747, Ignacio Ferrro): enlace erróneo. Pasa a ser la autofactura del 2º pago,
--    numerada en serie como hace el motor (-2), y el apunte de Ignacio queda libre.
CREATE TABLE IF NOT EXISTS _bak_095_gastos_reasignados AS SELECT * FROM gastos WHERE false;
INSERT INTO _bak_095_gastos_reasignados SELECT * FROM gastos WHERE id = 2388;
UPDATE gastos SET movimiento_id = 5332, numero_factura = 'IGS202601-2'
 WHERE id = 2388 AND numero_factura = 'IGS202601' AND movimiento_id = 4747;
UPDATE movimientos_bancarios SET estado_concil = 'conciliado' WHERE id = 5332;
UPDATE movimientos_bancarios SET estado_concil = 'abierto'
 WHERE id = 4747 AND NOT EXISTS (SELECT 1 FROM gastos WHERE movimiento_id = 4747);

CREATE UNIQUE INDEX IF NOT EXISTS uq_gastos_motor_identidad
    ON gastos (centro_id, coalesce(nullif(cif_emisor, ''), proveedor_extraido, ''), numero_factura, total)
    WHERE incidencia = 'generado_conciliacion' AND coalesce(numero_factura, '') <> '';

COMMIT;
