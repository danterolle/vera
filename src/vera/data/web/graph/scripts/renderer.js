const NS = "http://www.w3.org/2000/svg";
const ICONS = {
  Input: "IN", Control: "CTL", Context: "CTX", Reasoning: "AI",
  Guardrail: "CHK", Persistence: "DB", Output: "OUT", Workflow: "WF"
};
const EDGE_LABELS = {
  CAG_ONLY: "CAG", CAG_RAG: "RAG", CAG_RAG_TOOL: "RAG + APIs",
  STREAM: "STREAM", FULL: "FULL"
};

function element(name, attributes = {}) {
  const node = document.createElementNS(NS, name);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
  return node;
}

function text(parent, value, attributes = {}) {
  const node = element("text", attributes);
  node.textContent = value;
  parent.append(node);
}

function addDefinitions(svg) {
  const defs = element("defs");
  defs.innerHTML = `
    <pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse">
      <path d="M28 0H0V28" fill="none" stroke="#172234" stroke-width=".7"/>
    </pattern>
    <linearGradient id="active-edge" gradientUnits="userSpaceOnUse"
      x1="0" y1="0" x2="1200" y2="880">
      <stop offset="0" stop-color="#5aaeff"/><stop offset="1" stop-color="#43e0ae"/>
    </linearGradient>
    <filter id="shadow" x="-30%" y="-30%" width="160%" height="180%">
      <feDropShadow dx="0" dy="7" stdDeviation="7" flood-color="#000" flood-opacity=".4"/>
    </filter>
    <filter id="active-shadow" x="-40%" y="-40%" width="180%" height="190%">
      <feDropShadow dx="0" dy="8" stdDeviation="9" flood-color="#43e0ae" flood-opacity=".22"/>
    </filter>
    <filter id="glow"><feGaussianBlur stdDeviation="2" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
      markerWidth="5" markerHeight="5" orient="auto-start-reverse">
      <path d="M0 0L10 5 0 10Z" fill="context-stroke"/>
    </marker>`;
  svg.append(defs);
}

function addBackground(scene) {
  scene.append(element("rect", {
    width: "1200", height: "880", fill: "url(#grid)", class: "graph-grid"
  }));
  const stages = [
    [22, 16, 1156, 252, "INGESTION & ROUTING", 40, 38, false],
    [22, 288, 1156, 128, "ADAPTIVE CONTEXT", 40, 281, false],
    [466, 436, 268, 422, "REASONING & ASSURANCE", 482, 708, true]
  ];
  stages.forEach(([x, y, width, height, label, labelX, labelY, vertical]) => {
    scene.append(element("rect", { x, y, width, height, rx: "18", class: "stage" }));
    const position = vertical
      ? { x: "0", y: "0", transform: `translate(${labelX} ${labelY}) rotate(-90)` }
      : { x: labelX, y: labelY };
    text(scene, label, { ...position, class: "stage-label" });
  });
}

function edgePath(source, target) {
  if (source.y >= target.y) {
    return `M${source.x + 92} ${source.y}C${source.x + 260} ${source.y} ` +
      `${target.x + 260} ${target.y} ${target.x + 92} ${target.y}`;
  }
  const middle = (source.y + target.y) / 2;
  return `M${source.x} ${source.y + 32}C${source.x} ${middle} ` +
    `${target.x} ${middle} ${target.x} ${target.y - 32}`;
}

function drawEdge(scene, edge, nodes) {
  const source = nodes.get(edge.source);
  const target = nodes.get(edge.target);
  if (!source || !target) return;
  const path = element("path", {
    d: edgePath(source, target),
    class: `edge${edge.active ? " active" : ""}`,
    "data-source": edge.source,
    "data-target": edge.target
  });
  scene.append(path);
  if (edge.label && edge.source === "route") {
    const label = EDGE_LABELS[edge.label] || edge.label.replaceAll("_", " ");
    const width = Math.max(52, label.length * 5.5 + 18);
    const y = target.y - 48;
    scene.append(element("rect", {
      x: target.x - width / 2, y: y - 11, width, height: "20",
      rx: "10", class: `edge-label-bg${edge.active ? " active" : ""}`
    }));
    text(scene, label, {
      x: target.x, y: y + 3, class: `edge-label${edge.active ? " active" : ""}`
    });
  }
}

function drawNode(scene, node, onSelect) {
  const width = 184;
  const height = 64;
  const group = element("g", {
    class: `node ${node.category.toLowerCase()}${node.active ? " active" : ""}`,
    transform: `translate(${node.x - width / 2} ${node.y - height / 2})`,
    tabindex: "0", role: "button", "data-node-id": node.id,
    "aria-label": `${node.label}, ${node.category}`
  });
  const tooltip = element("title");
  tooltip.textContent = node.description;
  group.append(tooltip);
  group.append(element("rect", { width, height, rx: "12", class: "surface" }));
  group.append(element("rect", { width: "4", height: "34", y: "15", rx: "2", class: "accent" }));
  group.append(element("rect", {
    x: "14", y: "14", width: "36", height: "36", rx: "9", class: "icon-box"
  }));
  text(group, ICONS[node.category] || "WF", { x: "32", y: "36", class: "icon" });
  text(group, node.label, { x: "61", y: "29", class: "title" });
  text(group, node.category.toUpperCase(), { x: "61", y: "44", class: "category" });
  group.append(element("circle", { cx: "169", cy: "14", r: "4", class: "state-dot" }));
  if (node.executions > 1) {
    group.append(element("circle", { cx: "169", cy: "50", r: "10", class: "badge" }));
    text(group, String(node.executions), { x: "169", y: "53", class: "badge-text" });
  }
  group.addEventListener("click", event => {
    event.stopPropagation();
    onSelect(node, group);
  });
  group.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(node, group);
    }
  });
  scene.append(group);
  return group;
}

export function renderGraph(svg, data, onSelect) {
  svg.replaceChildren();
  addDefinitions(svg);
  const scene = element("g", { id: "graph-scene" });
  addBackground(scene);
  const nodes = new Map(data.nodes.map(node => [node.id, node]));
  data.edges.forEach(edge => drawEdge(scene, edge, nodes));
  const groups = new Map(
    data.nodes.map(node => [node.id, drawNode(scene, node, onSelect)])
  );
  svg.append(scene);
  return { groups };
}

export function iconFor(category) {
  return ICONS[category] || "WF";
}
