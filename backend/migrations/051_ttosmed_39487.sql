-- 051 · Escribir en MakingSmiles las 39.487 filas de GELITE (jmd, 17-oct-2026)
-- TtosMed con StaTto=5 e IdTto con tarifa válida = 39.487 filas.
-- Sin duplicar: la clave (paciente_id, num_tto) es única en las dos bases, así que las 38.496
-- que ya están se actualizan y las 991 que faltan se insertan.
-- Mapeos: IdTto → Tratamientos_Tarifas.IdTratamiento (tratamiento) y el propio IdTto (tarifa);
-- IdCol → colaboradores.id_gelite.
BEGIN;

CREATE TEMP TABLE _g (
  id_pac int, num_tto int, id_tratamiento int, id_tto_tarifa int,
  id_col int, id_col_aux int, id_cli int, fec_ini date, fec_fin date,
  importe numeric, dto numeric, importe_dto numeric, importe_privado numeric,
  importe_mutua numeric, pendiente numeric, actos int, tiempo int,
  piezas text, zonas text, nfactura text, ntransaccion text, notas text, comodin text
) ON COMMIT DROP;
\copy _g FROM '/tmp/ttos_39487.tsv' WITH (FORMAT text, NULL '\N')

CREATE TABLE IF NOT EXISTS tratamientos_realizados_bk_051 AS
    SELECT * FROM tratamientos_realizados;

UPDATE tratamientos_realizados r SET
    tratamiento_id   = g.id_tratamiento,
    tarifa_precio_id = g.id_tto_tarifa,
    colaborador_id   = c.id,
    colaborador_aux_id = ca.id,
    cliente_id       = g.id_cli,
    fecha_inicio     = g.fec_ini,
    fecha_fin        = g.fec_fin,
    importe          = g.importe,
    descuento        = g.dto,
    importe_descuento= g.importe_dto,
    importe_privado  = g.importe_privado,
    importe_mutua    = g.importe_mutua,
    pendiente        = g.pendiente,
    actos            = g.actos,
    tiempo_min       = g.tiempo,
    piezas           = g.piezas,
    zona_boca        = g.zonas,
    num_factura_e    = g.nfactura,
    num_transaccion  = g.ntransaccion,
    notas            = g.notas,
    campo_libre_1    = g.comodin,
    estado_id        = 5,
    updated_at       = now()
  FROM _g g
  LEFT JOIN colaboradores c  ON c.id_gelite = g.id_col
  LEFT JOIN colaboradores ca ON ca.id_gelite = g.id_col_aux
 WHERE r.paciente_id = g.id_pac AND r.num_tto = g.num_tto;

INSERT INTO tratamientos_realizados
    (created_at, updated_at, centro_id, paciente_id, cliente_id, num_tto, tratamiento_id,
     tarifa_precio_id, colaborador_id, colaborador_aux_id, piezas, zona_boca,
     fecha_inicio, fecha_fin, actos, tiempo_min, importe, descuento, importe_descuento,
     importe_privado, importe_mutua, pendiente, num_factura_e, num_transaccion,
     notas, campo_libre_1, estado_id)
SELECT now(), now(), 1, g.id_pac, g.id_cli, g.num_tto, g.id_tratamiento,
       g.id_tto_tarifa, c.id, ca.id, g.piezas, g.zonas,
       g.fec_ini, g.fec_fin, g.actos, g.tiempo, g.importe, g.dto, g.importe_dto,
       g.importe_privado, g.importe_mutua, g.pendiente, g.nfactura, g.ntransaccion,
       g.notas, g.comodin, 5
  FROM _g g
  LEFT JOIN colaboradores c  ON c.id_gelite = g.id_col
  LEFT JOIN colaboradores ca ON ca.id_gelite = g.id_col_aux
 WHERE NOT EXISTS (SELECT 1 FROM tratamientos_realizados r
                    WHERE r.paciente_id = g.id_pac AND r.num_tto = g.num_tto);

DO $$ DECLARE n integer; BEGIN
    SELECT count(*) INTO n FROM _g g
     WHERE NOT EXISTS (SELECT 1 FROM tratamientos_realizados r
                        WHERE r.paciente_id = g.id_pac AND r.num_tto = g.num_tto);
    IF n > 0 THEN RAISE EXCEPTION '051: faltan % filas de GELITE por escribir', n; END IF;
    SELECT count(*) - count(DISTINCT (paciente_id::text||'-'||num_tto::text))
      INTO n FROM tratamientos_realizados;
    IF n > 0 THEN RAISE EXCEPTION '051: hay % duplicados por paciente+num_tto', n; END IF;
END $$;

COMMIT;
