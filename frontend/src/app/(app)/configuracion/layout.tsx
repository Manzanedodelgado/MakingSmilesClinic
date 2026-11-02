"use client";
import { Building2, ShieldCheck, Settings, Plug, Zap, GitBranch, Bot } from "lucide-react";
/**
 * Sub-shell de Configuración — vive DENTRO del shell común `(app)/layout.tsx`
 * (que aporta header + rail). Aquí solo la barra "Configuración" del .37
 * (sólido #1500A0 + 2 líneas) y las pestañas de área (Clínica/Admin/IA's).
 */
import { usePathname, useRouter } from "next/navigation";
import { API_BASE } from "@/shared/lib/api";
import { AreaTabs } from "@/shared/components";
import { usePermisos } from "@/shared/hooks/usePermisos";

const TABS = {
  clinica: { label: "Clínica", icon: Building2, subs: [
    { id: "centro", label: "Centro" }, { id: "agenda", label: "Agenda" },
    { id: "personal", label: "Personal" }, { id: "colaboradores", label: "Colaboradores" },
  ] },
  agentes: { label: "Agentes IA", icon: Bot, subs: [
    { id: "rueda", label: "Agentes IA" },
  ] },
  admin: { label: "Admin", icon: ShieldCheck, subs: [
    { id: "diseno", label: "Diseño" },
    { id: "documentos", label: "Documentos" },
    { id: "tablas", label: "Tablas" },
  ] },
  conectores: { label: "Conectores", icon: Plug, subs: [
    { id: "whatsapp", label: "WhatsApp" },
    { id: "voicebot", label: "Voicebot" },
    { id: "mail", label: "Mail" },
    { id: "drive", label: "Drive" },
    { id: "radiografias", label: "Radiografías" },
    { id: "servidor", label: "Servidor" },
  ] },
  automatizaciones: { label: "Automatizaciones", icon: Zap, subs: [
    { id: "reglas", label: "Reglas" },
    { id: "editor", label: "Editor" },
    { id: "plantillas", label: "Plantillas" },
  ] },
  flujos: { label: "Flujos", icon: GitBranch, subs: [
    { id: "flujos", label: "Flujos" },
    { id: "editor", label: "Editor" },
  ] },
} as const;
type TabId = keyof typeof TABS;

export default function ConfiguracionLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  const { has, loading } = usePermisos();

  const seg = pathname.split("/").filter(Boolean); // ["configuracion", tab, sub]
  const tab = ((seg[1] as TabId) in TABS ? seg[1] : "clinica") as TabId;
  // Secciones que su perfil permite (agentes no se subdivide: basta la pestaña).
  const subsOk = tab === "agentes" ? TABS[tab].subs : TABS[tab].subs.filter((s) => has(`config.tab.${tab}.${s.id}`));
  const sub = seg[2] && subsOk.some((s) => s.id === seg[2]) ? seg[2] : (subsOk[0]?.id ?? TABS[tab].subs[0].id);
  const tabDef = TABS[tab];

  const go = (t: TabId, s?: string) => router.push(`/configuracion/${t}/${s ?? TABS[t].subs[0].id}`);

  return (
    <div className="flex-1 min-w-0 flex flex-col min-h-0">
      {/* Barra de configuración eliminada: el título "Configuración" lo pinta la barra común del layout. */}
      <AreaTabs tabs={subsOk.map((s) => ({ id: s.id, label: s.label }))} activeTab={sub} onChange={(s) => go(tab, s)} />
      <main className="flex-1 min-h-0 overflow-y-auto bg-[#FFFFFF] px-5 pb-5 pt-5">
        {!loading && subsOk.length === 0 ? <p className="text-[12px] italic text-[#94a3b8]">Tu perfil no tiene acceso a ninguna sección de esta pestaña.</p>
          : !loading && seg[2] && !subsOk.some((s) => s.id === seg[2]) ? <p className="text-[12px] italic text-[#94a3b8]">Tu perfil no tiene acceso a esta sección.</p>
          : children}
      </main>
      <span data-api-base={API_BASE} hidden />
    </div>
  );
}
