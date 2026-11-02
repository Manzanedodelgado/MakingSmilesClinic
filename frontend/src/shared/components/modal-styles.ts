/**
 * modal-styles.ts — Fuente única de verdad para las PANTALLAS EMERGENTES (modales).
 *
 * Estética de referencia: modal "Alertas del paciente" de Gesden One
 * (Uploads/nuevas funciones y estetica/Captura de pantalla 2026-10-15 a las 7.13.37.png):
 *   · panel blanco, título azul, botón de cierre circular azul claro
 *   · pestañas con la activa en azul sólido y subrayado azul continuo
 *   · barras de sección a todo el ancho en color, con "⊕" a la izquierda
 *   · pie de la tarjeta en verde muy claro con los botones en pastilla
 *
 * SUSTITUCIÓN DE COLOR pedida expresamente: se cambia el ROJO y el VERDE de la
 * referencia por MAGENTA y TURQUESA. Los azules, grises y blancos se mantienen.
 *   · verde  #588426 → turquesa #20BEAB
 *   · rojo   #D31E1C → magenta  #C026D3
 */

/* ── Azules (idénticos a la referencia) ─────────────────────────────── */
export const MS_BLUE = "#21A2E5"; // azul de tabs activas, barras y subrayados
export const MS_BLUE_DEEP = "#073D8D"; // badges y textos secundarios
export const MS_BLUE_SOFT = "#E7F6FD"; // fondo del botón de cierre
export const MS_BLUE_LINE = "#BFE4F7"; // bordes y separadores
export const MS_BLUE_TAB = "#5FB9DE"; // texto de pestañas inactivas

/* ── Turquesa (sustituye al verde de la referencia) ─────────────────── */
export const MS_TEAL = "#20BEAB"; // barras de sección, iconos
export const MS_TEAL_SOFT = "#E6F7F4"; // pie de tarjeta, fondos suaves
export const MS_TEAL_TEXT = "#0F8C7D"; // texto sobre turquesa suave

/* ── Magenta (sustituye al rojo de la referencia) ───────────────────── */
export const MS_MAGENTA = "#C026D3"; // botones de cerrar/cancelar
export const MS_MAGENTA_DARK = "#A21CAF"; // hover
export const MS_MAGENTA_SOFT = "#FBEAFD"; // fondos de aviso/validación

/* ── Neutros ────────────────────────────────────────────────────────── */
export const MS_GREY_DISABLED = "#D1D1D1"; // botón deshabilitado (gris de la referencia)
export const MS_TEXT = "#333333";
export const MS_TEXT_MUTED = "#5F7690";
export const MS_OVERLAY = "rgba(1, 30, 66, 0.48)";

/* ── Clases reutilizables ───────────────────────────────────────────── */

/** Panel blanco del modal: borde azul claro + sombra profunda. */
export const MODAL_PANEL =
  "bg-white rounded-xl border border-[#BFE4F7] shadow-[0_18px_48px_rgba(1,59,130,.28)] flex flex-col overflow-hidden";

/** Título principal del modal, en azul de marca. */
export const MODAL_TITLE = "text-[19px] leading-tight font-bold text-[#21A2E5]";

/** Subtítulo bajo el título. */
export const MODAL_SUBTITLE = "text-[12px] text-[#5F7690] mt-0.5";

/** Botón circular de cierre (equivalente al ⊗ de la referencia). */
export const MODAL_CLOSE =
  "shrink-0 w-7 h-7 rounded-full grid place-items-center bg-[#FFFFFF] text-[#21A2E5] hover:bg-[#21A2E5] hover:text-white transition-colors cursor-pointer";

/** Contenedor de pestañas: subrayado azul continuo de borde a borde. */
export const MODAL_TABS = "flex items-end gap-1 px-5 border-b-2 border-[#21A2E5] bg-white shrink-0";

/** Pestaña activa: azul sólido, texto blanco. */
export const MODAL_TAB_ACTIVE =
  "px-4 py-2 rounded-t-md text-[13px] font-semibold text-white bg-[#21A2E5] transition-colors cursor-pointer";

/** Pestaña inactiva: texto azul claro sobre blanco. */
export const MODAL_TAB_INACTIVE =
  "px-4 py-2 rounded-t-md text-[13px] font-medium text-[#5FB9DE] hover:text-[#21A2E5] hover:bg-[#E6EDFF] transition-colors cursor-pointer";

/** Cuerpo del modal. */
export const MODAL_BODY = "px-5 py-4 overflow-y-auto flex-1 min-h-0";

/** Pie de la tarjeta: turquesa muy claro (verde claro de la referencia). */
export const MODAL_FOOTER =
  "px-5 py-3 flex items-center justify-end gap-3 bg-[#FFFFFF] border-t border-[#BFE4F7] shrink-0";

/** Pastilla base (botones redondos de la referencia). */
export const PILL =
  "inline-flex items-center justify-center gap-1.5 rounded-full px-4 py-1.5 text-[13px] font-semibold transition-colors cursor-pointer disabled:cursor-not-allowed";

/** Guardar / aceptar: turquesa de marca con texto navy. */
export const PILL_PRIMARY =
  `${PILL} bg-[#2DD9C3] text-[#1500A0] hover:bg-[#20BEAB] disabled:bg-[#D1D1D1] disabled:text-white`;

/** Cerrar / cancelar: magenta (sustituye al rojo de la referencia). */
export const PILL_MAGENTA =
  `${PILL} bg-[#C026D3] text-white hover:bg-[#A21CAF] disabled:bg-[#D1D1D1] disabled:text-white`;

/** Botón deshabilitado tal cual aparece en la referencia. */
export const PILL_DISABLED = `${PILL} bg-[#D1D1D1] text-white cursor-not-allowed`;

/** Botón secundario: blanco con borde azul claro. */
export const PILL_OUTLINE =
  `${PILL} bg-white border border-[#BFE4F7] text-[#073D8D] hover:bg-[#E6EDFF]`;

/** Campo de texto del modal: borde azul claro, foco azul. */
export const MODAL_INPUT =
  "w-full px-2.5 py-1.5 text-[13px] text-[#333333] bg-white border border-[#BFE4F7] rounded-md outline-none focus:border-[#21A2E5] focus:ring-2 focus:ring-[#21A2E5]/20 transition-all";
