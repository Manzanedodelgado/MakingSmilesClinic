"use client";
/**
 * Modal.tsx — Pantallas emergentes con la estética de la referencia Gesden One
 * (modal "Alertas del paciente"), con el VERDE sustituido por TURQUESA y el ROJO
 * por MAGENTA.
 *
 * Es el componente base de TODOS los modales de la aplicación: los tokens viven en
 * `modal-styles.ts` (fuente única de verdad) y aquí sólo se compone la estructura.
 */
import React from "react";
import { X, Plus, Check, type LucideIcon } from "lucide-react";
import {
  MODAL_PANEL,
  MODAL_TITLE,
  MODAL_SUBTITLE,
  MODAL_CLOSE,
  MODAL_TABS,
  MODAL_TAB_ACTIVE,
  MODAL_TAB_INACTIVE,
  MODAL_BODY,
  MODAL_FOOTER,
  PILL_PRIMARY,
  PILL_MAGENTA,
  PILL_OUTLINE,
  PILL_DISABLED,
} from "./modal-styles";

export type ModalSize = "sm" | "md" | "lg" | "xl" | "full";

const SIZE: Record<ModalSize, string> = {
  sm: "max-w-[400px]",
  md: "max-w-[560px]",
  lg: "max-w-[780px]",
  xl: "max-w-[1040px]",
  full: "max-w-[1220px]",
};

/* ──────────────────────────────────────────────────────────────────────────
   Modal
   ────────────────────────────────────────────────────────────────────────── */

interface ModalProps {
  open?: boolean;
  onClose: () => void;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  size?: ModalSize;
  /** Cerrar pulsando fuera del panel. Por defecto sí. */
  closeOnBackdrop?: boolean;
  /** Contenido del pie (acciones). */
  footer?: React.ReactNode;
  /** Clase extra del panel. */
  className?: string;
  /**
   * Clase extra del cuerpo. NO se aplica automáticamente: el cuerpo lo aporta
   * <ModalBody> (padding + scroll). Se mantiene sólo para compatibilidad.
   */
  bodyClassName?: string;
  /** Z-index del overlay (para modales apilados). */
  zIndex?: number;
  children?: React.ReactNode;
}

export function Modal({
  open = true,
  onClose,
  title,
  subtitle,
  size = "md",
  closeOnBackdrop = true,
  footer,
  className = "",
  bodyClassName = "",
  zIndex = 50,
  children,
}: ModalProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 flex items-center justify-center p-4"
      style={{ background: "rgba(1, 30, 66, .48)", zIndex }}
      onClick={closeOnBackdrop ? onClose : undefined}
    >
      <div
        role="dialog"
        aria-modal="true"
        className={`${MODAL_PANEL} w-full ${SIZE[size]} max-h-[92vh] ${className}`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Cabecera: título azul + cierre circular */}
        <div className="flex items-start justify-between gap-4 px-5 pt-4 pb-3 shrink-0">
          <div className="min-w-0">
            <h2 className={MODAL_TITLE}>{title}</h2>
            {subtitle ? <p className={MODAL_SUBTITLE}>{subtitle}</p> : null}
          </div>
          <button type="button" onClick={onClose} aria-label="Cerrar" className={MODAL_CLOSE}>
            <X className="w-4 h-4" strokeWidth={2.5} />
          </button>
        </div>

        {children}

        {footer ? <div className={MODAL_FOOTER}>{footer}</div> : null}
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
   ModalTabs — pestañas con la activa en azul sólido y subrayado continuo
   ────────────────────────────────────────────────────────────────────────── */

export interface ModalTab {
  id: string;
  label: string;
}

interface ModalTabsProps {
  tabs: ModalTab[];
  activeTab: string;
  onChange: (id: string) => void;
  className?: string;
}

export function ModalTabs({ tabs, activeTab, onChange, className = "" }: ModalTabsProps) {
  return (
    <div className={`${MODAL_TABS} ${className}`} role="tablist">
      {tabs.map((t) => {
        const active = t.id === activeTab;
        return (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(t.id)}
            className={active ? MODAL_TAB_ACTIVE : MODAL_TAB_INACTIVE}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
   ModalSection — barra de sección a todo el ancho con "⊕" (referencia)
   ────────────────────────────────────────────────────────────────────────── */

export type ModalSectionTone = "blue" | "teal" | "magenta";

const SECTION_BG: Record<ModalSectionTone, string> = {
  blue: "bg-[#21A2E5]",
  teal: "bg-[#20BEAB]",
  magenta: "bg-[#C026D3]",
};

interface ModalSectionProps {
  title?: React.ReactNode;
  tone?: ModalSectionTone;
  /** Icono a la izquierda de la barra. Por defecto el "⊕" de la referencia. */
  icon?: LucideIcon | null;
  /** Contenido a la derecha de la barra. */
  action?: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
}

export function ModalSection({
  title,
  tone = "blue",
  icon: Icon = Plus,
  action,
  className = "",
  children,
}: ModalSectionProps) {
  return (
    <div className={`border border-[#BFE4F7] rounded-lg overflow-hidden ${className}`}>
      <div className={`flex items-center gap-2 px-3 py-1.5 text-white ${SECTION_BG[tone]}`}>
        {Icon ? (
          <span className="w-[18px] h-[18px] rounded-full border border-white/80 grid place-items-center shrink-0">
            <Icon className="w-3 h-3" strokeWidth={2.5} />
          </span>
        ) : null}
        {title ? <span className="text-[13px] font-semibold">{title}</span> : null}
        {action ? <span className="ml-auto flex items-center gap-2">{action}</span> : null}
      </div>
      {children ? <div className="p-4 bg-white">{children}</div> : null}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
   ModalBody / ModalFooter — recortes del cuerpo y del pie
   ────────────────────────────────────────────────────────────────────────── */

export function ModalBody({ className = "", children }: { className?: string; children: React.ReactNode }) {
  return <div className={`${MODAL_BODY} ${className}`}>{children}</div>;
}

export function ModalFooter({ className = "", children }: { className?: string; children: React.ReactNode }) {
  return <div className={`${MODAL_FOOTER} ${className}`}>{children}</div>;
}

/* ──────────────────────────────────────────────────────────────────────────
   ModalButton — botones en pastilla de la referencia
   ────────────────────────────────────────────────────────────────────────── */

export type ModalButtonVariant = "primary" | "magenta" | "outline" | "disabled";

const VARIANT: Record<ModalButtonVariant, string> = {
  primary: PILL_PRIMARY,
  magenta: PILL_MAGENTA,
  outline: PILL_OUTLINE,
  disabled: PILL_DISABLED,
};

interface ModalButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ModalButtonVariant;
  icon?: LucideIcon;
}

export function ModalButton({
  variant = "primary",
  icon: Icon,
  children,
  className = "",
  ...rest
}: ModalButtonProps) {
  return (
    <button type="button" className={`${VARIANT[variant]} ${className}`} {...rest}>
      {Icon ? <Icon className="w-4 h-4" strokeWidth={2.5} /> : null}
      {children}
    </button>
  );
}

/** Icono "✓" para el botón de guardar (como en la referencia). */
export const ModalCheckIcon = Check;
