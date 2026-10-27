import { text } from "/assets/chat-elements.js";
import { routeLabel } from "/assets/routes.js";

const CLAIMS = {
  supported_fact: "Fatto documentato", system_inference: "Inferenza",
  unavailable: "Informazione non disponibile", simulated: "Dato simulato"
};
const STATUSES = { available: "Disponibile", unavailable: "Non disponibile", simulated: "Simulata" };

function evidence(parent, record, all) {
  const cited = new Set((record.claims || record.draft?.claims || []).flatMap(claim => claim.evidence_ids));
  const sources = record.evidence.filter(source => all || cited.has(source.id));
  if (!sources.length) text(parent, "p", "Nessuna fonte citata.");
  for (const source of sources) {
    const item = document.createElement("article");
    item.className = "source-item";
    let url;
    try { url = new URL(source.url); } catch { /* Local sources have no URL. */ }
    if (url && ["https:", "http:"].includes(url.protocol)) {
      const link = text(item, "a", source.title);
      link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer";
    } else text(item, "strong", source.title);
    text(item, "small", `${source.source} · ${STATUSES[source.status] || source.status}`);
    if (source.metadata?.kg_record_key) {
      text(item, "small", "Fonte salvata nel Knowledge Graph; nessuna nuova chiamata implicita");
      if (source.metadata?.lookup_method) text(item, "small",
        `Ultimo recupero online: ${new Date(source.retrieved_at).toLocaleString("it-IT")}`);
    } else if (source.metadata?.lookup_method) {
      text(item, "small", `${source.status === "unavailable" ? "Ricerca senza fonte utilizzabile" : "Recuperata online"} · ${new Date(source.retrieved_at).toLocaleString("it-IT")}`);
      for (const request of source.metadata.http_requests || []) {
        text(item, "small", `HTTP GET ${request.url} · ${request.status_code ?? "errore di connessione"}`);
      }
    } else if (source.metadata?.snapshot) {
      text(item, "small", "Fonte locale / copia nel Knowledge Graph");
    }
    text(item, "blockquote", source.content);
    parent.append(item);
  }
}

export function details(parent, record, review = false) {
  const panel = document.createElement("details");
  panel.className = "message-details";
  text(panel, "summary", review ? "Esamina affermazioni, fonti e motivazioni" : "Fonti e dettagli della risposta");
  const body = document.createElement("div"); body.className = "details-body";
  text(body, "h4", "Affermazioni");
  const claims = record.claims || record.draft?.claims || [];
  if (!claims.length) text(body, "p", "Nessuna affermazione.");
  for (const claim of claims) {
    text(body, "span", CLAIMS[claim.status] || claim.status, `claim-label ${claim.status}`);
    text(body, "p", claim.text);
    for (const citation of claim.citations) text(body, "blockquote", citation.supporting_quote);
  }
  text(body, "h4", review ? "Evidenze disponibili" : "Fonti citate");
  evidence(body, record, review);
  if (record.incident) {
    text(body, "h4", "Segnali rilevati");
    const list = document.createElement("ul");
    record.incident.alerts.forEach(alert => text(list, "li", `${alert.severity} · ${alert.title}: ${alert.description}`));
    body.append(list);
    text(body, "p", "Gli alert richiedono una verifica e non dimostrano una compromissione.");
  }
  if (record.reflection?.gaps?.length) {
    text(body, "h4", "Limiti delle evidenze");
    const list = document.createElement("ul");
    record.reflection.gaps.forEach(gap => text(list, "li", gap));
    body.append(list);
  }
  text(body, "h4", "Informazioni sulla risposta");
  text(body, "p", `Percorso: ${routeLabel(record.route)}`);
  if (record.metadata?.provider) {
    text(body, "p", `Modello: ${record.metadata.model || record.metadata.provider}`);
    const graph = record.metadata.knowledge_graph;
    if (graph) text(body, "p", `Fonti del Knowledge Graph citate: ${graph.cited_evidence_ids?.length || 0}`);
    if (record.metrics) text(body, "p", `Chiamate al modello: ${record.metrics.model_calls} · Chiamate ai tool/API: ${record.metrics.tool_calls}`);
    const learned = record.metadata.knowledge_learning?.validated_entity_ids || [];
    if (learned.length) text(body, "p", `Nuove conoscenze convalidate: ${learned.length} · ${learned.join(", ")}`);
  }
  if (typeof record.answer === "string") {
    const link = text(body, "a", "Apri report completo");
    link.href = `/v1/runs/${encodeURIComponent(record.run_id)}`;
    link.target = "_blank"; link.rel = "noopener";
  } else text(body, "p", `Versione ${record.version + 1} · Revisioni ${record.revision_count}/2 · Bozza non pubblicata`);
  for (const warning of record.warnings || []) text(body, "p", warning, "message-warning");
  panel.append(body); parent.append(panel);
}
