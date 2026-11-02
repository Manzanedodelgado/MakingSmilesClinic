import type { MetadataRoute } from "next";

// Manifest de la app instalable (Chrome/Edge "Instalar"). Su icono es SIEMPRE el favicon configurado
// en Config > Apariencia: se genera en cada petición, así que si el favicon cambia, el icono cambia con él.
export const dynamic = "force-dynamic";

// El manifest exige declarar el tamaño real del icono → se lee de la cabecera de la imagen (PNG/JPEG).
function dimensiones(buf: Uint8Array): string | null {
  if (buf.length > 24 && buf[0] === 0x89 && buf[1] === 0x50 && buf[2] === 0x4e && buf[3] === 0x47) {
    const v = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
    return `${v.getUint32(16)}x${v.getUint32(20)}`;
  }
  if (buf.length > 4 && buf[0] === 0xff && buf[1] === 0xd8) {
    let i = 2;
    while (i + 9 < buf.length) {
      if (buf[i] !== 0xff) return null;
      const m = buf[i + 1];
      if (m === 0xff) { i++; continue; }
      // SOF0..SOF15 (salvo DHT/JPG/DAC) llevan alto y ancho
      if (m >= 0xc0 && m <= 0xcf && m !== 0xc4 && m !== 0xc8 && m !== 0xcc) {
        const alto = (buf[i + 5] << 8) | buf[i + 6];
        const ancho = (buf[i + 7] << 8) | buf[i + 8];
        return `${ancho}x${alto}`;
      }
      i += 2 + ((buf[i + 2] << 8) | buf[i + 3]);
    }
  }
  return null;
}

async function iconoFavicon(): Promise<MetadataRoute.Manifest["icons"] | null> {
  try {
    // Corre en SERVIDOR → backend por origen absoluto (igual que generateMetadata en layout.tsx).
    const ORIGEN = process.env.BACKEND_ORIGIN ?? "http://localhost:8000";
    const res = await fetch(`${ORIGEN}/auth/apariencia`, { cache: "no-store" });
    if (!res.ok) return null;
    const { favicon_url } = await res.json();
    if (!favicon_url) return null;
    const img = await fetch(`${ORIGEN}/auth/apariencia/imagen/favicon`, { cache: "no-store" });
    if (!img.ok) return null;
    const sizes = dimensiones(new Uint8Array(await img.arrayBuffer()));
    // ?v= cambia con cada favicon subido (nombre de fichero único) → ningún navegador sirve el viejo de caché.
    const v = encodeURIComponent(String(favicon_url).split("/").pop() ?? "");
    return [{
      src: `/api/auth/apariencia/imagen/favicon?v=${v}`,
      sizes: sizes ?? "any",
      type: img.headers.get("content-type") ?? undefined,
      purpose: "any",
    }];
  } catch {
    return null;
  }
}

export default async function manifest(): Promise<MetadataRoute.Manifest> {
  return {
    name: "Making Smiles Studio",
    short_name: "Making Smiles",
    lang: "es",
    start_url: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#1500A0",
    // Sin favicon configurado → icono de marca de public/ (el que había antes).
    icons: (await iconoFavicon()) ?? [{ src: "/icono-marca.png", sizes: "256x256", type: "image/png", purpose: "any" }],
  };
}
