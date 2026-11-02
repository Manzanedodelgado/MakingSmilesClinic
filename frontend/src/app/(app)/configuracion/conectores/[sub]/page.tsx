import { Placeholder } from "../../_components/Placeholder";
import { CanalesIA } from "../../_components/CanalesIA";
import { ConectorMail, ConectorDrive, ConectorRadiografias, ConectorServidor } from "../../_components/ConectoresEditores";

// Config → Conectores: la clínica hacia fuera. Todo sobre `integraciones` (credenciales nunca en .env).
// WhatsApp = editor ÚNICO del integración whatsapp (incluye Evolution: credenciales + estado + QR).
// Servidor = la máquina que aloja la app (no el PACS). Radiografías = Orthanc.
export default async function ConectoresSubPage({ params }: { params: Promise<{ sub: string }> }) {
  const { sub } = await params;
  if (sub === "whatsapp") return <CanalesIA solo="whatsapp" />;
  if (sub === "voicebot") return <CanalesIA solo="voicebot" />;
  if (sub === "mail") return <ConectorMail />;
  if (sub === "drive") return <ConectorDrive />;
  if (sub === "radiografias") return <ConectorRadiografias />;
  if (sub === "servidor") return <ConectorServidor />;
  return <Placeholder titulo={sub} />;
}
