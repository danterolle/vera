import { iconFor } from "/assets/graph-renderer.js";

const ROUTE_COPY = {
  "": "Inspect the complete topology or preview one adaptive path.",
  CAG_ONLY: "Stable curated knowledge only. No retrieval and no live API calls.",
  CAG_RAG: "Curated knowledge plus hybrid retrieval from the local corpus.",
  CAG_RAG_TOOL: "Local context enriched with exact authoritative vulnerability APIs.",
  STREAM: "Deterministic analysis of normalized events without triggered alerts.",
  FULL: "Incident detections correlated with retrieval and authoritative lookups."
};
const ROUTE_LABELS = {
  CAG_ONLY: "CAG only",
  CAG_RAG: "CAG + RAG",
  CAG_RAG_TOOL: "RAG + APIs",
  STREAM: "Stream",
  FULL: "Full analysis"
};

export function routeLabel(route) {
  return ROUTE_LABELS[route] || "Explore";
}

export class GraphPanels {
  constructor(routeButtons) {
    this.routeButtons = routeButtons;
    this.selectedElement = null;
  }

  inspect(node, group, mode) {
    this.selectedElement?.classList.remove("selected");
    this.selectedElement = group;
    group.classList.add("selected");
    document.querySelector("#node-icon").textContent = iconFor(node.category);
    document.querySelector("#node-category").textContent = node.category;
    document.querySelector("#node-title").textContent = node.label;
    document.querySelector("#node-description").textContent = node.description;
    document.querySelector("#node-input").textContent = node.input_contract;
    document.querySelector("#node-output").textContent = node.output_contract;
    document.querySelector("#node-id").textContent = node.id;
    const state = mode === "overview" ? "Available in topology" :
      node.active && mode === "preview" ? "Included in preview" :
        node.active ? "Executed" : "Outside selected path";
    document.querySelector("#node-state").textContent = state;
    document.querySelector("#node-executions").textContent = mode === "run"
      ? String(node.executions) : "—";
  }

  reset() {
    this.selectedElement?.classList.remove("selected");
    this.selectedElement = null;
    document.querySelector("#node-icon").textContent = "—";
    document.querySelector("#node-category").textContent = "Node inspector";
    document.querySelector("#node-title").textContent = "Select a node";
    document.querySelector("#node-description").textContent =
      "Select a card in the graph to inspect its role and state contract.";
    document.querySelector("#node-input").textContent = "—";
    document.querySelector("#node-output").textContent = "—";
    document.querySelector("#node-id").textContent = "—";
    document.querySelector("#node-state").textContent = "Not selected";
    document.querySelector("#node-executions").textContent = "—";
  }

  update(data, mode, corpus, routeNodes) {
    const execution = data.execution;
    const active = data.nodes.filter(node => node.active).length;
    const contextNode = data.nodes.find(node => node.active && node.category === "Context");
    const route = execution?.route || Object.keys(routeNodes).find(
      key => routeNodes[key] === contextNode?.id
    );
    document.querySelector("#metric-route").textContent = routeLabel(route);
    document.querySelector("#metric-route-meta").textContent =
      mode === "run" ? "Recorded execution" :
        mode === "preview" ? "Route preview" : "Five adaptive paths";
    document.querySelector("#metric-latency").textContent =
      execution ? `${execution.latency_ms.toFixed(1)} ms` : "—";
    document.querySelector("#metric-latency-meta").textContent = execution
      ? `${execution.model_calls} model · ${execution.tool_calls} tool calls`
      : "Select a recorded run";
    document.querySelector("#metric-evidence").textContent = execution
      ? String(execution.evidence_documents)
      : new Intl.NumberFormat().format(corpus.total_documents);
    document.querySelector("#metric-evidence-meta").textContent = execution
      ? `${execution.source_count} evidence sources` : "Documents in local corpus";
    document.querySelector("#metric-quality").textContent =
      execution ? `${Math.round(execution.completeness * 100)}%` : "—";
    document.querySelector("#metric-quality-meta").textContent = execution
      ? `${execution.warning_count} warnings` : "No run selected";
    document.querySelector("#summary").textContent =
      mode === "run" ? `${active} nodes executed` :
        mode === "preview" ? `${active} nodes in preview` : "Topology overview";
    document.querySelector(".trace-state").classList.toggle("idle", !active);
    this.selectRoute(route || "");
  }

  selectRoute(route) {
    this.routeButtons.forEach(button => {
      const selected = button.dataset.route === route;
      button.classList.toggle("selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
    document.querySelector("#route-description").textContent =
      ROUTE_COPY[route] || ROUTE_COPY[""];
  }
}
