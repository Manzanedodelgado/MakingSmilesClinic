import type { ElementType, ReactNode } from "react";

/** "PACIENTES" / "pacientes" → "Pacientes" (los títulos llegan en mayúsculas desde varias pantallas). */
const titulo = (t: string) => (t === t.toUpperCase() ? t.charAt(0) + t.slice(1).toLowerCase() : t);

/**
 * PageHeader — barra de título de área (formato .37, verbatim de Config/Agenda):
 * barra navy blue #000080 de 42 px con icono + título en blanco (estética GesdenOne medida en
 * Uploads/Agenda) y franja azul de 10 px que queda por debajo del contenido.
 *
 *  - `icon`     icono Lucide a la izquierda del título.
 *  - `title`    texto del área (en tipo frase).
 *  - `children` contenido extra tras el título (selectores, etc.).
 *  - `right`    contenido alineado a la derecha de la barra.
 *  - `px`       padding horizontal de la barra (por defecto px-4; Config usa px-5).
 */
export function PageHeader({
  icon: Icon,
  title,
  children,
  right,
  px = "px-4",
}: {
  icon?: ElementType;
  title: string;
  children?: ReactNode;
  right?: ReactNode;
  px?: string;
}) {
  return (
    <>
      <div className={`bg-[#000080] h-[39px] ${px} flex items-center gap-2.5 shrink-0 text-white`}>
        {Icon && <Icon className="w-5 h-5 text-white shrink-0" />}
        <span className="text-[20px] font-normal tracking-tight whitespace-nowrap">{titulo(title)}</span>
        {children}
        {right && (
          <>
            <div className="flex-1" />
            {right}
          </>
        )}
      </div>
      {/* Rasgo GesdenOne: la franja azul sigue 10 px POR DEBAJO del contenido. Margen negativo:
          no ocupa altura (Filiación debe seguir cabiendo sin scroll a 1920×950) y lo que viene
          detrás se pinta encima, así los paneles blancos quedan "flotando" sobre la franja. */}
      <div aria-hidden className="h-[10px] -mb-[10px] bg-[#000080] shrink-0" />
    </>
  );
}
