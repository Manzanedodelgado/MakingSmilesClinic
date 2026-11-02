import type { ReactNode } from "react";
import { fichaTema as T } from "./fichaTema";

/** Cabecera clara de 34 px, igual en todos los paneles de la ficha. */
export function FichaCabecera({ titulo, accion }: { titulo: ReactNode; accion?: ReactNode }) {
  return (
    <div data-ficha-cab className="shrink-0 flex items-center justify-between gap-2 px-3"
      style={{ height: T.cabAlto, background: T.cabFondo, color: T.cabTexto }}>
      <h2 className="text-[14px] font-normal truncate">{titulo}</h2>
      {accion ? <div className="flex items-center gap-2 shrink-0">{accion}</div> : null}
    </div>
  );
}

/** Cabecera + cuerpo con scroll. El marco (borde, sombra, esquinas) lo pone el ClinicalCard de FichaLibre. */
export function FichaPanel({ titulo, accion, children, className = "" }: {
  titulo: ReactNode; accion?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <div className={`flex flex-col flex-1 min-h-0 min-w-0 ${className}`}>
      <FichaCabecera titulo={titulo} accion={accion} />
      <div className="flex-1 min-h-0 overflow-auto flex flex-col">{children}</div>
    </div>
  );
}

/** Estado vacío de un panel: texto de oficio, no un «Sin datos» genérico. */
export function FichaVacio({ texto }: { texto: string }) {
  return <p className="px-4 py-5 text-center text-[12px] italic" style={{ color: T.textoSuave }}>{texto}</p>;
}
