export const STAGE_LABELS = {
  nuevo: "Prospecto",
  contactado: "Calificacion",
  cotizacion: "Propuesto",
  negociacion: "Negociacion",
  ganado: "Cierre",
  perdido: "Perdido",
};

export const STAGES = ["nuevo", "contactado", "cotizacion", "negociacion", "ganado"];

export function money(value) {
  return `$${Number(value || 0).toLocaleString("es-CL")}`;
}

export function compactMoney(value) {
  const amount = Number(value || 0);
  if (amount >= 1000000) return `$${(amount / 1000000).toFixed(1)}M`;
  if (amount >= 1000) return `$${(amount / 1000).toFixed(0)}K`;
  return money(amount);
}

export function initials(text = "") {
  return String(text || "EV")
    .split(/[\s.@_-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "EV";
}

function isOpaqueIdentifier(value = "") {
  const text = String(value || "").trim();
  return (
    text.length >= 20
    && /[a-z]/.test(text)
    && /[A-Z]/.test(text)
    && /\d/.test(text)
    && !text.includes("@")
    && !/\s/.test(text)
  );
}

function readableNameFromEmail(email = "") {
  const localPart = String(email || "").split("@")[0] || "";
  const parts = localPart
    .replace(/[._-]+/g, " ")
    .split(/\s+/)
    .filter(Boolean);

  if (!parts.length || isOpaqueIdentifier(parts.join(""))) {
    return "";
  }

  return parts
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function resolveSellerIdentity(uid, user) {
  const name = String(user?.nombre || "").trim();
  const email = String(user?.email || "").trim();
  const readableEmailName = readableNameFromEmail(email);

  if (name && !isOpaqueIdentifier(name)) {
    return { email: email || uid, name };
  }

  if (readableEmailName) {
    return { email: email || uid, name: readableEmailName };
  }

  return {
    email: email && !isOpaqueIdentifier(email) ? email : "Ficha de usuario pendiente",
    name: "Vendedor sin ficha",
  };
}

export function weightedValue(item) {
  return Number(item?.valorEstimado || 0) * (Number(item?.probabilidad || 0) / 100);
}

/** Datos reales de una oportunidad y sus propuestas (sin estimaciones de presion competitiva). */
export function buildOpportunityProfile({ oportunidad, propuestas = [] }) {
  const opportunityProposals = propuestas.filter((item) => item.oportunidadId === oportunidad?.id);
  return {
    accepted: opportunityProposals.filter((item) => item.estado === "aceptada").length,
    proposalCount: opportunityProposals.length,
    probability: Math.max(0, Math.min(Number(oportunidad?.probabilidad || 0), 100)),
    rejected: opportunityProposals.filter((item) => item.estado === "rechazada").length,
    weighted: weightedValue(oportunidad),
  };
}

export function buildSellerRows({ oportunidades = [], propuestas = [], users = [] }) {
  const usersById = new Map(users.map((user) => [user.uid, user]));
  const sellerIds = new Set([
    ...oportunidades.map((item) => item.vendedorUid).filter(Boolean),
    ...propuestas.map((item) => item.vendedorUid).filter(Boolean),
    ...users.map((user) => user.uid),
  ]);

  return [...sellerIds].map((uid) => {
    const user = usersById.get(uid);
    const sellerIdentity = resolveSellerIdentity(uid, user);
    const sellerOpportunities = oportunidades.filter((item) => item.vendedorUid === uid);
    const sellerProposals = propuestas.filter((item) => item.vendedorUid === uid);
    const accepted = sellerProposals.filter((item) => item.estado === "aceptada");
    const projected = sellerOpportunities.reduce((sum, item) => sum + weightedValue(item), 0);
    const realized = accepted.reduce((sum, item) => sum + Number(item.montoTotal || 0), 0);
    const stageCounts = Object.fromEntries(
      STAGES.map((stage) => [stage, sellerOpportunities.filter((item) => item.etapa === stage).length]),
    );
    const stageValues = Object.fromEntries(
      STAGES.map((stage) => [
        stage,
        sellerOpportunities
          .filter((item) => item.etapa === stage)
          .reduce((sum, item) => sum + Number(item.valorEstimado || 0), 0),
      ]),
    );
    const winRate = sellerProposals.length
      ? Math.round((accepted.length / sellerProposals.length) * 100)
      : 0;

    return {
      uid,
      name: sellerIdentity.name,
      email: sellerIdentity.email,
      active: user?.activo !== false,
      role: user?.rol || "vendedor",
      zone: user?.zona || "Zona centro",
      projected,
      realized,
      pipeline: sellerOpportunities.reduce((sum, item) => sum + Number(item.valorEstimado || 0), 0),
      stageCounts,
      stageValues,
      total: sellerOpportunities.length,
      winRate,
      accepted,
      negotiating: sellerOpportunities.filter((item) => item.etapa === "negociacion"),
    };
  }).sort((a, b) => b.pipeline - a.pipeline);
}

export function matchText(item, query, fields) {
  const term = query.trim().toLowerCase();
  if (!term) return true;
  return fields.some((field) => String(item[field] || "").toLowerCase().includes(term));
}
