-- 027 · Corrección del concepto de un apunte, SIN tocar el texto del banco.
--
-- El concepto que escribe la clínica al ordenar una transferencia se equivoca a veces
-- (dos pagos seguidos rotulados "Produccion Dic" cuando el segundo era enero). Corregirlo
-- machacando `concepto_banco` tendría dos daños:
--   1. La identidad anti-duplicados al importar un extracto es
--      (iban, fecha, concepto_banco, importe, saldo). Si se altera, volver a subir el MISMO
--      PDF metería el apunte por segunda vez.
--   2. Se perdería lo que el banco dijo de verdad, que es el documento probatorio.
--
-- Por eso la corrección vive aparte: el extracto es inmutable, la lectura contable se anota.
ALTER TABLE movimientos_bancarios
  ADD COLUMN IF NOT EXISTS concepto_corregido VARCHAR(300);
