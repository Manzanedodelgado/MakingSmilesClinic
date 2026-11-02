/**
 * Se ejecuta UNA vez al terminar toda la suite.
 * Red de seguridad: purga cualquier paciente ZZ_E2E que un afterEach no llegara a borrar
 * (test abortado, crash del worker, etc.). No sustituye al afterEach de cada test.
 */
import {
  purgarPacientesE2E,
  borrarDocumentosTest,
  borrarMiscTest,
  closePool,
} from './fixtures/database';

async function globalTeardown() {
  try {
    await borrarMiscTest();

    const docs = await borrarDocumentosTest();
    if (docs > 0) console.log(`🧹 globalTeardown: borrados ${docs} documento(s) admin ZZ_E2E`);

    const n = await purgarPacientesE2E();
    console.log(
      n > 0
        ? `🧹 globalTeardown: purgados ${n} paciente(s) ZZ_E2E huérfanos`
        : '🧹 globalTeardown: sin pacientes ZZ_E2E huérfanos'
    );
  } finally {
    await closePool();
  }
}

export default globalTeardown;
