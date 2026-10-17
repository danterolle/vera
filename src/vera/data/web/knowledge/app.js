import {renderGraph} from "/assets/knowledge-renderer.js";
import {inspect, resetInspector} from "/assets/knowledge-inspector.js";
import {GraphViewport} from "/assets/graph-viewport.js";
const svg = document.querySelector("#graph"), statusLine = document.querySelector("#status");
const input = document.querySelector("#entity"), suggestions = document.querySelector("#suggestions");
const viewport = new GraphViewport(svg, value => {
  document.querySelector("#zoom-level").textContent = `${value}%`;
});
let controller, searchController, timer;
async function load(identifier = input.value.trim()) {
  input.value = identifier;
  suggestions.replaceChildren(); controller?.abort(); controller = new AbortController();
  const request = controller;
  const params = new URLSearchParams({limit: document.querySelector("#limit").value,
    provenance: document.querySelector("#provenance").checked});
  if (identifier) params.set("id", identifier);
  statusLine.textContent = "Reading local knowledge graph…";
  try {
    const response = await fetch(`/v1/knowledge-graph?${params}`, {signal: request.signal});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Graph request failed");
    if (request !== controller) return;
    resetInspector();
    viewport.base = renderGraph(svg, data, (item, group) => {
      inspect(item, group, load);
      if (window.innerWidth <= 1000) {
        document.querySelector("aside").scrollIntoView({behavior: "smooth", block: "nearest"});
      }
    });
    viewport.fit();
    document.querySelector("#empty").hidden = data.nodes.length > 0;
    statusLine.textContent = data.status.available
      ? `${data.nodes.length} visible nodes · ${data.edges.length} connections · ${data.status.counts.Entity} entities in database${data.truncated ? " · partial view: narrow your search or increase the limit" : ""}`
      : data.status.error;
    const seed = data.nodes.find(node => data.selected_ids.includes(node.id));
    if (seed) inspect(seed, svg.querySelector(".seed"), load);
  } catch (error) {
    if (error.name !== "AbortError") {
      svg.replaceChildren(); resetInspector(); statusLine.textContent = error.message;
    }
  }
}
async function suggest() {
  searchController?.abort(); searchController = new AbortController();
  const request = searchController, q = input.value.trim();
  suggestions.replaceChildren();
  if (q.length < 2) return;
  try {
    const response = await fetch(`/v1/knowledge-graph/search?${new URLSearchParams({q})}`,
      {signal: request.signal});
    if (!response.ok) return;
    const matches = await response.json();
    if (request !== searchController || input.value.trim() !== q) return;
    for (const match of matches) {
      const button = document.createElement("button"); button.type = "button";
      button.textContent = `${match.label} · ${match.kind}`;
      button.addEventListener("click", () => load(match.id)); suggestions.append(button);
    }
  } catch (error) { if (error.name !== "AbortError") statusLine.textContent = "Search unavailable"; }
}
input.addEventListener("input", () => {clearTimeout(timer); timer = setTimeout(suggest, 180);});
document.querySelector("#filters").addEventListener("submit", event => {
  event.preventDefault(); clearTimeout(timer); searchController?.abort(); load();
});
document.querySelector("#overview").addEventListener("click", () => load(""));
document.querySelector("#provenance").addEventListener("change", () => load());
document.querySelector("#zoom-in").addEventListener("click", () => viewport.zoom(1.2));
document.querySelector("#zoom-out").addEventListener("click", () => viewport.zoom(.84));
document.querySelector("#fit-graph").addEventListener("click", () => viewport.fit());
load();
