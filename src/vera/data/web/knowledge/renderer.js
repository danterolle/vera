import {positions} from "/assets/knowledge-layout.js";
const NS = "http://www.w3.org/2000/svg";
export function element(tag, attributes = {}, text = "") {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  node.textContent = text;
  return node;
}
export function readable(label) {
  return label.replace(/^(?:CVE-\d{4}-\d+|CWE-\d+|CAPEC-\d+|TA?\d{4}(?:\.\d+)?|[MGS]\d{4})\s*-\s*/, "");
}
function activate(group, callback) {
  group.addEventListener("click", event => {event.stopPropagation(); callback();});
  group.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === " ") {event.preventDefault(); callback();}
  });
}
export function renderGraph(svg, data, inspect) {
  svg.replaceChildren();
  const width = Math.max(1200, Math.ceil(Math.sqrt(data.nodes.length)) * 340);
  const height = Math.max(800, Math.ceil(Math.sqrt(data.nodes.length)) * 230);
  const map = positions(data, width, height);
  const defs = element("defs"), marker = element("marker", {
    id: "knowledge-arrow", viewBox: "0 0 10 10", refX: "9", refY: "5",
    markerWidth: "6", markerHeight: "6", orient: "auto-start-reverse"
  });
  marker.append(element("path", {d: "M0 0L10 5 0 10Z", fill: "#7d91ab"}));
  defs.append(marker); svg.append(defs);
  for (const edge of data.edges) {
    const a = map.get(edge.source), b = map.get(edge.target);
    if (!a || !b) continue;
    const dx = b.x - a.x, dy = b.y - a.y;
    const factor = Math.min(140 / Math.max(1, Math.abs(dx)), 48 / Math.max(1, Math.abs(dy)));
    const x1 = a.x + dx * factor, y1 = a.y + dy * factor;
    const x2 = b.x - dx * factor, y2 = b.y - dy * factor;
    const group = element("g", {class: "edge-group", tabindex: "0", role: "button",
      "aria-pressed": "false", "data-source-id": edge.source, "data-target-id": edge.target,
      "aria-label": `${readable(a.label)} ${edge.label} ${readable(b.label)}`});
    const d = `M${x1} ${y1}L${x2} ${y2}`;
    group.append(element("path", {d, class: "edge-hit"}), element("path", {
      d, class: "edge", "marker-end": "url(#knowledge-arrow)"
    }));
    const x = (x1 + x2) / 2, y = (y1 + y2) / 2, size = edge.label.length * 9 + 20;
    group.append(element("rect", {x: x - size / 2, y: y - 12, width: size,
      height: 24, rx: 7, class: "edge-caption"}));
    group.append(element("text", {x, y: y + 4, class: "edge-label", "text-anchor": "middle"}, edge.label));
    activate(group, () => inspect({...edge, kind: "relationship", label: `${readable(a.label)} → ${readable(b.label)}`}, group));
    svg.append(group);
  }
  for (const node of map.values()) {
    const group = element("g", {transform: `translate(${node.x - 140},${node.y - 48})`,
      class: `node ${node.kind}${data.selected_ids.includes(node.id) ? " seed" : ""}`,
      tabindex: "0", role: "button", "aria-pressed": "false",
      "aria-label": `${node.label}, ${node.kind}`, "data-node-id": node.id});
    group.append(element("title", {}, node.label));
    group.append(element("rect", {width: 280, height: 96, rx: 13}));
    const words = readable(node.label).split(" ");
    const lines = [""];
    for (const word of words) {
      if (lines.at(-1).length + word.length > 26 && lines.length < 2) lines.push("");
      lines[lines.length - 1] += `${word} `;
    }
    lines.forEach((line, index) => group.append(element("text", {
      x: 14, y: 27 + index * 22, class: "node-name"
    }, line.trim().length > 27 ? `${line.trim().slice(0, 26)}…` : line.trim())));
    const code = node.id.startsWith("attack:") ? node.id.split(":").at(-1) :
      node.kind === "source" || node.kind === "assertion" ? "" : node.id;
    group.append(element("text", {x: 14, y: 82, class: "node-kind"}, `${node.kind} ${code}`.slice(0, 33)));
    activate(group, () => inspect(node, group)); svg.append(group);
  }
  return {x: 0, y: 0, width, height};
}
