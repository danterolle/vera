import {readable} from "/assets/knowledge-renderer.js";
const KIND = {technique: "ATT&CK technique", tactic: "ATT&CK tactic", mitigation: "Mitigation",
  group: "Threat group", software: "Software", cve: "Vulnerability", cwe: "Weakness",
  capec: "Attack pattern", guidance: "Guidance", concept: "Security concept",
  source: "Source document", assertion: "Supported assertion", relationship: "Relationship"};
function html(tag, text = "", className = "") {
  const node = document.createElement(tag); node.textContent = text; node.className = className;
  return node;
}
function fact(label, value) {
  const row = html("div");
  row.append(html("dt", label), html("dd", String(value)));
  return row;
}
function highlight(item, selected) {
  const graph = document.querySelector("#graph");
  const neighbors = new Set(item.kind === "relationship"
    ? [item.source, item.target] : [item.id]);
  if (item.kind !== "relationship") {
    graph.querySelectorAll(".edge-group").forEach(edge => {
      if (edge.dataset.sourceId === item.id) neighbors.add(edge.dataset.targetId);
      if (edge.dataset.targetId === item.id) neighbors.add(edge.dataset.sourceId);
    });
  }
  graph.querySelectorAll(".node, .edge-group").forEach(group => {
    const edge = group.classList.contains("edge-group");
    const related = edge
      ? item.kind === "relationship"
        ? neighbors.has(group.dataset.sourceId) && neighbors.has(group.dataset.targetId)
        : group.dataset.sourceId === item.id || group.dataset.targetId === item.id
      : neighbors.has(group.dataset.nodeId);
    group.classList.toggle("selected", group === selected);
    group.classList.toggle("related", related && group !== selected);
    group.classList.toggle("dimmed", Boolean(selected) && !related && group !== selected);
    group.setAttribute("aria-pressed", String(group === selected));
  });
}
export function inspect(item, group, explore) {
  highlight(item, group);
  document.querySelector("#title").textContent = readable(item.label);
  const details = document.querySelector("#details"); details.replaceChildren();
  details.append(html("p", KIND[item.kind] || item.kind, "eyebrow"));
  const facts = html("dl", "", "facts");
  if (item.kind === "relationship") {
    facts.append(fact("Connection", item.predicate.replaceAll("_", " ").toLowerCase()));
  } else {
    facts.append(fact("Identifier", item.id));
    if (item.aliases?.length) facts.append(fact("Also known as", item.aliases.join(", ")));
  }
  if (item.status) facts.append(fact("Evidence status", item.status.replaceAll("_", " ")));
  details.append(facts);
  if (!["relationship", "source", "assertion"].includes(item.kind)) {
    const button = html("button", "Explore neighbors"); button.type = "button";
    button.addEventListener("click", () => explore(item.id));
    details.append(button);
  }
  const sources = item.kind === "source" ? [item] : item.sources || [];
  details.append(html("h3", `${sources.length} source${sources.length === 1 ? "" : "s"} in this view`));
  if (!sources.length) details.append(html("p",
    item.kind === "relationship" ? "No source excerpt is available for this connection."
      : "Select a connection to see the sources supporting its mapping.", "muted-text"));
  for (const source of sources) {
    const article = html("article", "", "source-card");
    let link;
    try {
      const url = new URL(source.url);
      if (["https:", "http:"].includes(url.protocol)) {
        link = html("a", source.label || "Open source"); link.href = url.href;
        link.target = "_blank"; link.rel = "noopener noreferrer";
      }
    } catch {}
    article.append(link || html("strong", source.label || "Source record"));
    article.append(html("p", source.supporting_quote ? "Supporting excerpt" : "Source excerpt",
      "source-caption"));
    article.append(html("p", source.supporting_quote || source.content ||
      "No excerpt available.", "source-text"));
    const meta = source.metadata || {};
    const version = meta.attack_version || meta.cwe_version || meta.capec_version ||
      meta.catalog_version || meta.owasp_version;
    article.append(html("small", [source.status?.replaceAll("_", " "), version && `version ${version}`,
      source.field_path].filter(Boolean).join(" · ")));
    details.append(article);
  }
  const technical = html("details"); technical.append(html("summary", "Identifiers and metadata"));
  technical.append(html("pre", JSON.stringify(item, null, 2))); details.append(technical);
}
export function resetInspector() {
  document.querySelector("#title").textContent = "Inspector";
  document.querySelector("#details").replaceChildren(html("p",
    "Select a node or connection to inspect sources.", "muted-text"));
}
