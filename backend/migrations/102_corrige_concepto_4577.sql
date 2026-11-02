-- 29-oct-2026: el apunte 4577 (1-oct-2025) decía "Nómina Agosto" igual que el 4541; es la de septiembre.
-- El texto del banco (concepto_banco) NO se toca: la corrección va en concepto_corregido.
-- La vista informe_juan_antonio que muestra el concepto corregido la define la 103 (esta solo corrige el dato; antes traía también la vista y fallaba al cambiar el tipo de la columna).
UPDATE movimientos_bancarios SET concepto_corregido = 'Transferencia Inmediata A Favor De Juan Antonio Manzanedo Concepto Nómina Septiembre'
 WHERE id = 4577 AND concepto_corregido IS NULL;
