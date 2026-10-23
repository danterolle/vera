import { initializeAnalysis } from "/assets/graph-analysis.js";
import { GraphPanels, routeLabel } from "/assets/graph-panels.js";
import { initializeReview } from "/assets/graph-review.js";
import { renderGraph } from "/assets/graph-renderer.js";
import { GraphViewport } from "/assets/graph-viewport.js";

const svg = document.querySelector("#graph");
const runSelect = document.querySelector("#run");
const routeButtons = [...document.querySelectorAll("[data-route]")];
const focusButton = document.querySelector("#focus-path");
const panels = new GraphPanels(routeButtons);
const viewport = new GraphViewport(svg, value => {
  document.querySelector("#zoom-level").textContent = `${value}%`;
}, { x: 0, y: 0, width: 1200, height: 980 });
const ROUTE_NODES = {
  CAG_ONLY: "cag", CAG_RAG: "rag", CAG_RAG_TOOL: "tools", STREAM: "stream", FULL: "full"
};
let topology;
let corpus;
let loadVersion = 0;
const analysis = initializeAnalysis(runId => {
  review.clear();
  return load(runId);
}, record => review.receive(record));
const review = initializeReview({
  onSelect() {
    analysis.clear();
    if (runSelect.value) {
      runSelect.value = "";
      if (topology && corpus) draw(pathPreview(topology, ""), "overview");
      load().catch(showError);
    }
  },
  onApproved: report => analysis.showApproved(report)
});

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
    "validate", "reflection", "review_assess", "finalize", "__end__"
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
            edge.source === (react ? "react_decide" : branch))
    })),
    execution: null
  };
}

function draw(data, mode) {
  panels.reset();
  const rendered = renderGraph(svg, data, (node, group) => {
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
  const version = ++loadVersion;
  showLoading();
  const query = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  try {
    const [graphResponse, corpusResponse] = await Promise.all([
      fetch(`/v1/graph${query}`), fetch("/v1/corpus")
    ]);
    if (!graphResponse.ok || !corpusResponse.ok) throw new Error("Runtime data unavailable");
    const [nextTopology, nextCorpus] = await Promise.all([
      graphResponse.json(), corpusResponse.json()
    ]);
    if (version !== loadVersion) return;
    topology = nextTopology;
    corpus = nextCorpus;
    fillRuns(topology.recent_runs, topology.selected_run_id);
    document.querySelector("#mermaid").textContent = topology.mermaid;
    draw(topology, runId ? "run" : "overview");
    hideLoading();
  } catch (error) {
    if (version === loadVersion) throw error;
  }
}

function fillRuns(runs, selected) {
  runSelect.replaceChildren(new Option("No run selected", ""));
  runs.forEach(run => {
    const stamp = new Date(run.created_at).toLocaleString();
    runSelect.add(new Option(`${routeLabel(run.route)} · ${stamp} · ${run.run_id.slice(0, 8)}`, run.run_id));
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
  loadVersion += 1;
  hideLoading();
  runSelect.value = "";
  analysis.clear();
  draw(pathPreview(topology, route), route ? "preview" : "overview");
}
routeButtons.forEach(button => button.addEventListener("click", () => selectRoute(button.dataset.route)));
runSelect.addEventListener("change", () => {
  review.clear();
  const runId = runSelect.value;
  if (runId) analysis.showRun(runId);
  else analysis.clear();
  load(runId).catch(showError);
});
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
