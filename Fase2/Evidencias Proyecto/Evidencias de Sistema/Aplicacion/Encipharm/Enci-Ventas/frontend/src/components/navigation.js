import { hasIntelAccess, hasMinimumRole } from "../auth/roles";

export const NAV_SECTIONS = [
  {
    title: "Principal",
    items: [
      { label: "Dashboard", path: "/dashboard", icon: "dashboard" },
      { label: "Pipeline & Funnels", path: "/oportunidades", icon: "pipeline" },
      { label: "Proyecciones", path: "/proyecciones", icon: "chart" },
    ],
  },
  {
    title: "Gestion",
    items: [
      { label: "Equipo de Ventas", path: "/equipo", icon: "team" },
      { label: "Clientes", path: "/clientes", icon: "team" },
      { label: "Nuevo cliente", path: "/crear", icon: "spark" },
      { label: "Interacciones", path: "/interacciones", icon: "pipeline" },
      { label: "Calendario", path: "/calendario", icon: "calendar" },
      { label: "Propuestas", path: "/propuestas", icon: "chart" },
      { label: "Enci Chat", path: "/asistente", icon: "spark" },
      { label: "Inteligencia de Mercado", path: "/inteligencia", icon: "shield" },
      { label: "Análisis de Competencia", path: "/competencia", icon: "analysis" },
    ],
  },
  {
    title: "Sistema",
    items: [
      { label: "Configuración", path: "/configuracion", icon: "settings" },
    ],
  },
];

const INTEL_PATHS = ["/inteligencia", "/competencia"];

export function visibleNavSections(user) {
  return NAV_SECTIONS
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => {
        if (item.path === "/equipo") return hasMinimumRole(user?.rol, "supervisor");
        if (INTEL_PATHS.includes(item.path)) return hasIntelAccess(user);
        return true;
      }),
    }))
    .filter((section) => section.items.length > 0);
}
