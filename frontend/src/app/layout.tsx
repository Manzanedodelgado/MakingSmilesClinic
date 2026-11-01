import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "MakingSmiles Clinic",
  description: "Plataforma de gestión para la clínica dental MakingSmiles.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es">
      <body>
        <header>
          <p>MakingSmiles Clinic</p>
        </header>
        {children}
      </body>
    </html>
  );
}
