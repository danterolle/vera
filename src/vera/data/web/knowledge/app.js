import {renderGraph} from "/assets/knowledge-renderer.js";
import {inspect, resetInspector} from "/assets/knowledge-inspector.js";
import {GraphViewport} from "/assets/graph-viewport.js";
const svg = document.querySelector("#graph"), statusLine = document.querySelector("#status");
const input = document.querySelector("#entity"), suggestions = document.querySelector("#suggestions");
const feedback = document.querySelector("#search-feedback"), empty = document.querySelector("#empty");
const viewTitle = document.querySelector("#view-title");
const viewport = new GraphViewport(svg, value => {
  document.querySelector("#zoom-level").textContent = `${value}%`;
});
let controller, searchController, timer, activeIndex = -1, currentIdentifier = input.value.trim();

function selectItem(item, group, scroll = true) {
  inspect(item, group, load);
  document.querySelectorAll("#concept-list button").forEach(button => {
    button.setAttribute("aria-pressed", String(item.kind !== "relationship" &&
      button.dataset.nodeId === item.id));
  });
  if (scroll && window.innerWidth <= 1000) {
    document.querySelector("#inspector").scrollIntoView({behavior: "smooth", block: "start"});
  }
}

function closeSuggestions() {
  clearTimeout(timer);
  searchController?.abort();
  searchController = undefined;
  suggestions.replaceChildren();
  suggestions.hidden = true;
  feedback.textContent = "";
  feedback.classList.remove("visually-hidden");
  input.setAttribute("aria-expanded", "false");
  input.removeAttribute("aria-activedescendant");
  activeIndex = -1;
}

function selectSuggestion(index) {
  const options = [...suggestions.querySelectorAll("[role=option]")];
  if (!options.length) return;
  activeIndex = (index + options.length) % options.length;
  options.forEach((option, position) => {
    option.setAttribute("aria-selected", String(position === activeIndex));
  });
  input.setAttribute("aria-activedescendant", options[activeIndex].id);
  options[activeIndex].scrollIntoView({block: "nearest"});
}

async function load(identifier = input.value.trim()) {
  closeSuggestions();
  currentIdentifier = identifier;
  input.value = identifier;
  controller?.abort(); controller = new AbortController();
  const request = controller;
  const params = new URLSearchParams({limit: document.querySelector("#limit").value,
    provenance: document.querySelector("#provenance").checked});
  if (identifier) params.set("id", identifier);
  statusLine.textContent = "Reading local knowledge graph…";
  svg.setAttribute("aria-busy", "true");
  try {
    const response = await fetch(`/v1/knowledge-graph?${params}`, {signal: request.signal});
    const data = await response.json();
    if (!response.ok) throw new Error(
      typeof data.detail === "string" ? data.detail : "Graph request failed");
    if (request !== controller) return;
    resetInspector();
    viewport.base = renderGraph(svg, data, (item, group) => selectItem(item, group));
    viewport.fit();
    const list = document.querySelector("#concept-list");
    list.replaceChildren();
    document.querySelector(".concept-browser summary").textContent =
      `Browse ${data.nodes.length} nodes in this view`;
    for (const node of data.nodes) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary";
      button.dataset.nodeId = node.id;
      button.setAttribute("aria-pressed", "false");
      button.textContent = `${node.label} · ${node.kind}`;
      button.addEventListener("click", () => {
        const group = [...svg.querySelectorAll(".node")].find(element =>
          element.dataset.nodeId === node.id);
        selectItem(node, group);
      });
      list.append(button);
    }
    const seed = data.nodes.find(node => data.selected_ids.includes(node.id));
    if (seed && data.selected_ids.length === 1 && window.innerWidth <= 650) viewport.zoom(2.4);
    if (!data.status.available) {
      viewTitle.textContent = "Graph unavailable";
      statusLine.textContent = data.status.error || "Knowledge graph is unavailable.";
      empty.textContent = "Build the local graph with vera kg-build, then reload this page.";
    } else {
      viewTitle.textContent = !identifier ? "Overview" : seed
        ? data.selected_ids.length === 1 ? `Exploring ${seed.label}`
          : `${data.selected_ids.length} matching concepts`
        : `No match for “${identifier}”`;
      statusLine.textContent = `${data.nodes.length} nodes · ${data.edges.length} connections` +
        (data.truncated ? " · Partial view: refine search or increase the limit." : "");
      empty.textContent = identifier
        ? "No matching concepts. Try another name or identifier, or show the overview."
        : "No relationships yet. Build the local graph with vera kg-build.";
      if (seed) {
        const group = [...svg.querySelectorAll(".node")].find(node => node.dataset.nodeId === seed.id);
        selectItem(seed, group, false);
      }
    }
    empty.hidden = data.nodes.length > 0;
  } catch (error) {
    if (request === controller && error.name !== "AbortError") {
      svg.replaceChildren();
      document.querySelector("#concept-list").replaceChildren();
      resetInspector();
      viewTitle.textContent = "Unable to load graph";
      statusLine.textContent = error.message;
      empty.textContent = "Check the connection and try exploring again.";
      empty.hidden = false;
    }
  } finally {
    if (request === controller) svg.setAttribute("aria-busy", "false");
  }
}

async function suggest() {
  searchController?.abort(); searchController = new AbortController();
  const request = searchController, q = input.value.trim();
  suggestions.replaceChildren();
  suggestions.hidden = true;
  input.setAttribute("aria-expanded", "false");
  if (q.length < 2) return;
  try {
    const response = await fetch(`/v1/knowledge-graph/search?${new URLSearchParams({q})}`,
      {signal: request.signal});
    if (!response.ok) throw new Error("Search unavailable");
    const matches = await response.json();
    if (request !== searchController || input.value.trim() !== q) return;
    feedback.textContent = matches.length
      ? `${matches.length} matching concept${matches.length === 1 ? "" : "s"}. Use arrow keys to choose.`
      : "No suggestions · Enter to search";
    feedback.classList.toggle("visually-hidden", matches.length > 0);
    matches.forEach((match, index) => {
      const button = document.createElement("button"); button.type = "button";
      button.id = `suggestion-${index}`;
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", "false");
      button.setAttribute("aria-label", `${match.label}, ${match.kind}, ${match.id}`);
      button.tabIndex = -1;
      const label = document.createElement("span"), meta = document.createElement("span");
      label.textContent = match.label;
      meta.textContent = `${match.kind} · ${match.id}`;
      button.append(label, meta);
      button.addEventListener("click", () => load(match.id)); suggestions.append(button);
    });
    suggestions.hidden = !matches.length;
    input.setAttribute("aria-expanded", String(matches.length > 0));
  } catch (error) {
    if (request === searchController && error.name !== "AbortError") {
      feedback.classList.remove("visually-hidden");
      feedback.textContent = "Suggestions unavailable · Enter to search";
    }
  }
}
input.addEventListener("input", () => {
  closeSuggestions();
  timer = setTimeout(suggest, 180);
});
input.addEventListener("keydown", event => {
  if (event.key === "Escape") {
    closeSuggestions();
    event.preventDefault();
  } else if (!suggestions.hidden && ["ArrowDown", "ArrowUp"].includes(event.key)) {
    selectSuggestion(activeIndex < 0
      ? (event.key === "ArrowDown" ? 0 : suggestions.children.length - 1)
      : activeIndex + (event.key === "ArrowDown" ? 1 : -1));
    event.preventDefault();
  } else if (event.key === "Enter" && activeIndex >= 0 && !suggestions.hidden) {
    suggestions.querySelectorAll("[role=option]")[activeIndex].click();
    event.preventDefault();
  }
});
document.addEventListener("pointerdown", event => {
  if (!event.target.closest(".search-box")) closeSuggestions();
});
document.querySelector("#filters").addEventListener("submit", event => {
  event.preventDefault(); load();
});
document.querySelector("#overview").addEventListener("click", () => load(""));
document.querySelector("#provenance").addEventListener("change", () => load(currentIdentifier));
document.querySelector("#limit").addEventListener("change", () => load(currentIdentifier));
document.querySelector("#zoom-in").addEventListener("click", () => viewport.zoom(1.2));
document.querySelector("#zoom-out").addEventListener("click", () => viewport.zoom(.84));
document.querySelector("#fit-graph").addEventListener("click", () => viewport.fit());
document.querySelector("#back-to-graph").addEventListener("click", () => {
  const target = svg.querySelector(".selected") || svg;
  target.focus();
  svg.scrollIntoView({behavior: "smooth", block: "center"});
});
load();
