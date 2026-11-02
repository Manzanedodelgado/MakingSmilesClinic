-- Motivo íntegro de la devolución de saldo del paciente.
ALTER TABLE pagos
    ADD COLUMN IF NOT EXISTS motivo varchar(250);
