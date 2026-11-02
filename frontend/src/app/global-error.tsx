"use client";
/**
 * Red de seguridad para el hueco de "cliente desactualizado tras un despliegue".
 *
 * Por qué existe: `deploy-web.sh` no tira el servidor ni un instante (verificado: 0
 * fallos en 60 peticiones/100ms durante un reinicio completo), PERO si alguien ya tenía
 * la web abierta en el navegador EXACTAMENTE cuando se publicó el build nuevo, su pestaña
 * se queda con JS del build viejo. Al interactuar (navegar, un formulario…) Next.js intenta
 * resolver una referencia de servidor (Server Reference / RSC) del build anterior contra el
 * servidor nuevo y explota con "The Server Reference ID did not match the expected format"
 * — visto en vivo en logs/web-prod.log justo tras un despliegue real. El servidor está bien;
 * es la pestaña la que quedó obsoleta. La única cura real es recargar esa pestaña una vez.
 */
import { useEffect } from "react";

function esErrorDeBuildObsoleto(error: Error & { digest?: string }): boolean {
  const msg = `${error?.message ?? ""} ${error?.digest ?? ""}`;
  return (
    msg.includes("Server Reference ID") ||
    msg.includes("Failed to find Server Action") ||
    msg.includes("ChunkLoadError") ||
    msg.includes("Loading chunk")
  );
}

export default function GlobalError({ error }: { error: Error & { digest?: string } }) {
  useEffect(() => {
    if (esErrorDeBuildObsoleto(error)) {
      // Una sola recarga automática: la pestaña vuelve a pedir el HTML/JS del build actual.
      window.location.reload();
    }
  }, [error]);

  return (
    <html lang="es">
      <body style={{ margin: 0, display: "grid", placeItems: "center", height: "100vh", fontFamily: "system-ui" }}>
        <div style={{ textAlign: "center", color: "#1500A0" }}>
          <p>Actualizando la página…</p>
        </div>
      </body>
    </html>
  );
}
