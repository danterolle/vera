import {readable} from "/assets/knowledge-renderer.js";
const KIND = {technique: "ATT&CK technique", tactic: "ATT&CK tactic", mitigation: "Mitigation",
  group: "Threat group", software: "Software", cve: "Vulnerability", cwe: "Weakness",
  capec: "Attack pattern", guidance: "Guidance", concept: "Security concept",
  source: "Source document", assertion: "Supported assertion", relationship: "Relationship"};
function html(tag, text = "", className = "") {
  const node = document.createElement(tag); node.textContent = text; node.className = className;
  return node;
}
export function inspect(item, group, explore) {
  document.querySelectorAll(".selected").forEach(node => node.classList.remove("selected"));
  group?.classList.add("selected");
  document.querySelector("#title").textContent = readable(item.label);
  const details = document.querySelector("#details"); details.replaceChildren();
  details.append(html("p", KIND[item.kind] || item.kind, "eyebrow"));
  if (item.kind === "relationship") {
    details.append(html("p", `Relationship: ${item.predicate.replaceAll("_", " ")}`));
    details.append(html("p", `Status: ${item.status || "source link"}`));
  } else if (!["source", "assertion"].includes(item.kind)) {
    const button = html("button", "Explore neighbors"); button.type = "button";
    button.addEventListener("click", () => explore(item.id)); details.append(button);
  }
  const sources = item.kind === "source" ? [item] : item.sources || [];
  details.append(html("h3", `${sources.length} supporting source${sources.length === 1 ? "" : "s"}`));
  for (const source of sources) {
    const article = html("article", "", "source-card");
    let link;
    try {
      const url = new URL(source.url);
      if (["https:", "http:"].includes(url.protocol)) {
        link = html("a", source.label); link.href = url.href;
        link.target = "_blank"; link.rel = "noopener noreferrer";
      }
    } catch { /* Sources may have no external URL. */ }
    article.append(link || html("strong", source.label));
    article.append(html("p", source.supporting_quote || source.content || "", "source-text"));
    const meta = source.metadata || {};
    const version = meta.attack_version || meta.cwe_version || meta.capec_version ||
      meta.catalog_version || meta.owasp_version;
    article.append(html("small", [source.status, version && `version ${version}`,
      source.field_path].filter(Boolean).join(" · ")));
    details.append(article);
  }
  const technical = html("details"); technical.append(html("summary", "Identifiers and metadata"));
  technical.append(html("pre", JSON.stringify(item, null, 2))); details.append(technical);
}
export function resetInspector() {
  document.querySelector("#title").textContent = "Explore a concept";
  document.querySelector("#details").replaceChildren(html("p",
    "Click a node to read its sources, or a connection to understand the relationship. Use Explore neighbors to continue navigating."));
}
