import localFont from "next/font/local";

// Roboto AUTO-HOSPEDADA (src/app/fonts): es la tipografía de GesdenOne. En la captura de referencia el título
// «Horario del recurso» mide 121 px a 14 px de cuerpo; con Inter ocupa 126 px. Solo se aplica a esta ruta.
const roboto = localFont({ src: "../../../../fonts/roboto-latin-variable.woff2", weight: "100 900", display: "swap" });

// display: contents → no crea caja (no rompe el flex/alto de la página) pero la fuente se hereda.
export default function AgendaLayout({ children }: { children: React.ReactNode }) {
  return <div className={`${roboto.className} contents`}>{children}</div>;
}
