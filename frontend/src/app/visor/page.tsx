"use client";
/**
 * /visor — emergente de presentación (segundo monitor / escritorio extendido).
 * Muestra una imagen/RX a pantalla completa sobre negro. La abre el botón "Lanzar"
 * del panel Multimedia con window.open posicionado en la pantalla externa.
 * Lee ?src= (URL absoluta del proxy, lleva la cookie same-origin) y ?name=.
 */
import { useEffect, useState } from "react";

export default function VisorPage() {
  const [src, setSrc] = useState("");
  const [name, setName] = useState("");
  const [paciente, setPaciente] = useState("");
  const [icono, setIcono] = useState("");
  const [fs, setFs] = useState(false);

  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    setSrc(p.get("src") || "");
    setName(p.get("name") || "");
    setPaciente(p.get("paciente") || "");
    setIcono(p.get("icono") || "");
    document.title = p.get("paciente") || "Visor";

    // Pantalla completa: el navegador exige activación de usuario, que una ventana recién
    // abierta no tiene. Se reintenta en cuanto haya cualquier señal (foco, visible, primer
    // puntero/tecla) y como último recurso, al clic. Con permiso "gestión de ventanas" Chrome
    // lo concede solo; si no, el primer clic en la pantalla del paciente lo activa.
    const tryFs = () => {
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen?.().then(() => setFs(true)).catch(() => {});
      }
    };
    tryFs();
    const onFs = () => setFs(!!document.fullscreenElement);
    window.addEventListener("focus", tryFs);
    document.addEventListener("visibilitychange", tryFs);
    window.addEventListener("pointerdown", tryFs);
    window.addEventListener("keydown", tryFs);
    document.addEventListener("fullscreenchange", onFs);
    return () => {
      window.removeEventListener("focus", tryFs);
      document.removeEventListener("visibilitychange", tryFs);
      window.removeEventListener("pointerdown", tryFs);
      window.removeEventListener("keydown", tryFs);
      document.removeEventListener("fullscreenchange", onFs);
    };
  }, []);

  const pantallaCompleta = () => {
    if (!document.fullscreenElement) document.documentElement.requestFullscreen?.().catch(() => {});
  };

  return (
    <div
      onClick={pantallaCompleta}
      style={{
        position: "fixed", inset: 0, background: "#fff", display: "flex",
        alignItems: "center", justifyContent: "center", overflow: "hidden",
        cursor: fs ? "default" : "zoom-in",
      }}
    >
      {src ? (
        <img src={src} alt={name} draggable={false}
          style={{ maxWidth: "100vw", maxHeight: "100vh", objectFit: "contain", userSelect: "none" }} />
      ) : (
        <span style={{ color: "#777", fontFamily: "sans-serif" }}>Sin imagen</span>
      )}

      {/* Abajo-izquierda: nombre del paciente · Abajo-derecha: icono del centro */}
      {paciente && (
        <div style={{
          position: "absolute", bottom: 22, left: 28, color: "#1a1a1a", fontSize: 20,
          fontWeight: 600, fontFamily: "sans-serif", pointerEvents: "none",
        }}>{paciente}</div>
      )}
      {icono && (
        <img src={icono} alt="" style={{
          position: "absolute", bottom: 18, right: 28, height: 64, maxWidth: 240,
          objectFit: "contain", pointerEvents: "none",
        }} />
      )}
      {!fs && (
        <div style={{
          position: "absolute", bottom: 6, left: 0, right: 0, textAlign: "center",
          color: "rgba(0,0,0,.4)", fontSize: 11, fontFamily: "sans-serif", pointerEvents: "none",
        }}>haz clic para pantalla completa</div>
      )}

      <button onClick={(e) => { e.stopPropagation(); window.close(); }} title="Cerrar (o Esc)"
        style={{
          position: "absolute", top: 12, right: 12, width: 42, height: 42, borderRadius: "50%",
          border: "none", background: "rgba(0,0,0,.08)", color: "#333", fontSize: 20, cursor: "pointer",
        }}>✕</button>
    </div>
  );
}
