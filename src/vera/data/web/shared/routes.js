const ROUTES = {
  CAG_ONLY: "CAG",
  CAG_RAG: "CAG + RAG",
  CAG_RAG_TOOL: "CAG + RAG + API",
  STREAM: "CAG + Stream",
  FULL: "CAG + RAG + Stream"
};

export function routeLabel(route) {
  return Object.hasOwn(ROUTES, route) ? ROUTES[route] : "Explore";
}
