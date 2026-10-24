const ROUTES = {
  CAG_ONLY: {
    label: "CAG",
    description: "Curated cybersecurity knowledge and memory, without corpus or graph retrieval."
  },
  CAG_RAG: {
    label: "CAG + RAG",
    description: "Curated knowledge plus local corpus retrieval and, when enabled, Kuzu evidence."
  },
  CAG_RAG_TOOL: {
    label: "CAG + RAG + API",
    description: "Curated knowledge and retrieval, plus exact CVE API lookups when live sources are enabled."
  },
  STREAM: {
    label: "CAG + Stream",
    description: "Curated knowledge plus statistics from supplied events, without corpus or graph retrieval."
  },
  FULL: {
    label: "CAG + RAG + Stream",
    description: "Events combined with curated knowledge and retrieval; CVE API lookups run when needed and enabled."
  }
};

export function routeLabel(route) {
  return ROUTES[route]?.label || "Explore";
}

export function routeDescription(route) {
  return ROUTES[route]?.description || "";
}
