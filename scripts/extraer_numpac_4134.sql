/* ============================================================================
   VOLCADO COMPLETO DE UN PACIENTE DESDE GELITE  (origen, SOLO LECTURA)
   NumPac 4134  =  IdPac 4767
   ----------------------------------------------------------------------------
   SELECT *  de TODAS las tablas que contienen la columna IdPac.
   No se elige ninguna columna: se devuelve TODO (todas las columnas, todas las filas).
   100% lectura. Prohibido cualquier UPDATE/INSERT/DELETE sobre GELITE.
   ============================================================================ */

SET NOCOUNT ON;

DECLARE @NumPac VARCHAR(20) = '4134';
DECLARE @IdPac  INT;
SELECT  @IdPac = IdPac FROM Pacientes WHERE NumPac = @NumPac;   -- 4134 -> 4767

DECLARE @sql NVARCHAR(MAX) = N'';

/* Genera un "SELECT * FROM <tabla> WHERE IdPac = @IdPac" por CADA tabla
   base que tenga una columna llamada IdPac. */
SELECT @sql = @sql
    + 'PRINT ''===== ' + c.TABLE_NAME + ' ====='';' + CHAR(13) + CHAR(10)
    + 'SELECT * FROM [' + c.TABLE_NAME + '] WHERE IdPac = ' + CAST(@IdPac AS VARCHAR(12)) + ';'
    + CHAR(13) + CHAR(10)
FROM INFORMATION_SCHEMA.COLUMNS c
INNER JOIN INFORMATION_SCHEMA.TABLES t
        ON t.TABLE_NAME = c.TABLE_NAME AND t.TABLE_TYPE = 'BASE TABLE'
WHERE c.COLUMN_NAME = 'IdPac'
ORDER BY c.TABLE_NAME;

EXEC sp_executesql @sql;

/* ----------------------------------------------------------------------------
   Tablas que NO enganchan por IdPac sino por una clave derivada
   (líneas de receta van por IdRecetaIdent del paciente):
   ---------------------------------------------------------------------------- */
SELECT d.*
FROM RecetasDet d
INNER JOIN RecetasCab c ON c.IdRecetaIdent = d.IdRecetaIdent
WHERE c.IdPac = @IdPac;
