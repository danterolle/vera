import { GraphPanels, routeLabel } from "/assets/graph-panels.js";
import { renderGraph } from "/assets/graph-renderer.js";
import { GraphViewport } from "/assets/graph-viewport.js";

const svg = document.querySelector("#graph");
const runSelect = document.querySelector("#run");
const routeButtons = [...document.querySelectorAll("[data-route]")];
const focusButton = document.querySelector("#focus-path");
const panels = new GraphPanels(routeButtons);
const viewport = new GraphViewport(svg, value => {
  document.querySelector("#zoom-level").textContent = `${value}%`;
});
const ROUTE_NODES = {
  CAG_ONLY: "cag", CAG_RAG: "rag", CAG_RAG_TOOL: "tools", STREAM: "stream", FULL: "full"
};
let topology;
let corpus;
let rendered;

function pathPreview(data, route) {
  if (!route) {
    return {
      ...data,
      nodes: data.nodes.map(node => ({ ...node, active: false, executions: 0 })),
      edges: data.edges.map(edge => ({ ...edge, active: false })),
      execution: null
    };
  }
  const branch = ROUTE_NODES[route];
  const react = data.nodes.some(node => node.id === "react_decide");
  const active = new Set([
    "__start__", "initialize", "route", branch, "generate",
    "validate", "reflection", "finalize", "__end__"
  ]);
  if (react) active.add("react_decide");
  return {
    ...data,
    nodes: data.nodes.map(node => ({
      ...node, active: active.has(node.id), executions: active.has(node.id) ? 1 : 0
    })),
    edges: data.edges.map(edge => ({
      ...edge,
      active: edge.source === "validate" && edge.target === "generate"
        ? false
        : active.has(edge.source) && active.has(edge.target) &&
          (edge.source !== "route" || edge.target === branch) &&
          (edge.target !== "generate" ||
            edge.source === (react ? "react_decide" : branch) ||
            edge.source === "validate")
    })),
    execution: null
  };
}

function draw(data, mode) {
  panels.reset();
  rendered = renderGraph(svg, data, (node, group) => {
    const route = Object.keys(ROUTE_NODES).find(key => ROUTE_NODES[key] === node.id);
    if (route && mode !== "run") selectRoute(route);
    else panels.inspect(node, group, mode);
    if (window.innerWidth <= 1120) {
      document.querySelector(".inspector").scrollIntoView({behavior: "smooth", block: "nearest"});
    }
  });
  const branch = data.nodes.find(node => node.active && Object.values(ROUTE_NODES).includes(node.id));
  if (branch) panels.inspect(branch, rendered.groups.get(branch.id), mode);
  const hasPath = data.nodes.some(node => node.active);
  focusButton.disabled = !hasPath;
  if (!hasPath && focusButton.getAttribute("aria-pressed") === "true") toggleFocus();
  panels.update(data, mode, corpus, ROUTE_NODES);
}

function toggleFocus() {
  const enabled = focusButton.getAttribute("aria-pressed") !== "true";
  focusButton.setAttribute("aria-pressed", String(enabled));
  focusButton.textContent = enabled ? "Show all" : "Focus path";
  svg.classList.toggle("focus-path", enabled);
}

async function load(runId = "") {
  showLoading();
  const query = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  const [graphResponse, corpusResponse] = await Promise.all([
    fetch(`/v1/graph${query}`), fetch("/v1/corpus")
  ]);
  if (!graphResponse.ok || !corpusResponse.ok) throw new Error("Runtime data unavailable");
  [topology, corpus] = await Promise.all([graphResponse.json(), corpusResponse.json()]);
  fillRuns(topology.recent_runs, topology.selected_run_id);
  document.querySelector("#mermaid").textContent = topology.mermaid;
  draw(topology, runId ? "run" : "overview");
  hideLoading();
}

function fillRuns(runs, selected) {
  runSelect.replaceChildren(new Option("No run selected", ""));
  runs.forEach(run => {
    const stamp = new Date(run.created_at).toLocaleString();
    runSelect.add(new Option(`${routeLabel(run.route)} · ${stamp}`, run.run_id));
  });
  runSelect.value = selected || "";
}

function showLoading() {
  const state = document.querySelector("#canvas-state");
  state.classList.remove("hidden", "error");
  state.querySelector("strong").textContent = "Loading workflow";
  state.querySelector("p").textContent = "Reading the compiled LangGraph topology.";
  state.querySelector("button").hidden = true;
}

function hideLoading() {
  document.querySelector("#canvas-state").classList.add("hidden");
}

function showError(error) {
  const state = document.querySelector("#canvas-state");
  state.classList.add("error");
  state.querySelector("strong").textContent = "Unable to load workflow";
  state.querySelector("p").textContent = error.message;
  state.querySelector("button").hidden = false;
}

function selectRoute(route) {
  if (!topology) return;
  runSelect.value = "";
  draw(pathPreview(topology, route), route ? "preview" : "overview");
}
routeButtons.forEach(button => button.addEventListener("click", () => selectRoute(button.dataset.route)));
runSelect.addEventListener("change", () => load(runSelect.value).catch(showError));
focusButton.addEventListener("click", toggleFocus);
document.querySelector("#zoom-in").addEventListener("click", () => viewport.zoom(1.2));
document.querySelector("#zoom-out").addEventListener("click", () => viewport.zoom(0.84));
document.querySelector("#fit-graph").addEventListener("click", () => viewport.fit());
document.querySelector("#reset-selection").addEventListener("click", () => panels.reset());
svg.addEventListener("click", event => {
  if (!event.target.closest(".node")) panels.reset();
});
document.querySelector("#retry-load").addEventListener("click", () => load().catch(showError));

load().catch(showError);
