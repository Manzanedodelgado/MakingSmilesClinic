"use client";
/**
 * Botón de envío "pintado": brochazo navy con textura (filtro SVG) + texto en fuente de
 * pincel (Dancing Script) con las letras en los colores del logo (primera letra mayúscula
 * más grande). Reutilizable por las pantallas de acceso (login lo replica inline).
 * Requiere las clases .lg-submit / .lg-submit::before / .lg-acc en el CSS de la página.
 */
const PAINT = ["#6EC5E9", "#C026D3", "#7C3AED", "#20BEAB"];

export function PaintedSubmit({ text, loadingText, loading }: { text: string; loadingText: string; loading: boolean }) {
  return (
    <>
      {/* Filtro "brochazo": bordes pintados + vetas + grano sobre el fondo navy */}
      <svg width="0" height="0" aria-hidden style={{ position: "absolute" }}>
        <filter id="lg-brush" x="-20%" y="-90%" width="140%" height="280%">
          <feTurbulence type="fractalNoise" baseFrequency="0.016 0.1" numOctaves={2} seed={7} result="rough" />
          <feDisplacementMap in="SourceGraphic" in2="rough" scale={11} xChannelSelector="R" yChannelSelector="G" result="disp" />
          <feTurbulence type="fractalNoise" baseFrequency="0.006 0.42" numOctaves={2} seed={9} result="streak" />
          <feColorMatrix in="streak" type="matrix" values="0 0 0 0 0.30  0 0 0 0 0.44  0 0 0 0 0.70  0 0 0 0.17 0" result="streakC" />
          <feComposite in="streakC" in2="disp" operator="in" result="streakClip" />
          <feTurbulence type="fractalNoise" baseFrequency="0.5 0.5" numOctaves={3} seed={4} result="grain" />
          <feColorMatrix in="grain" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.30 0" result="grainA" />
          <feComposite in="grainA" in2="disp" operator="in" result="grainClip" />
          <feMerge>
            <feMergeNode in="disp" />
            <feMergeNode in="streakClip" />
            <feMergeNode in="grainClip" />
          </feMerge>
        </filter>
      </svg>
      <button type="submit" className="lg-submit" disabled={loading}>
        {loading ? loadingText : (
          <span className="lg-acc">
            {[...text].map((ch, i) => (
              <span key={i} style={{ color: PAINT[i % PAINT.length], ...(i === 0 ? { fontSize: "1.4em" } : {}) }}>{ch}</span>
            ))}
          </span>
        )}
      </button>
    </>
  );
}
