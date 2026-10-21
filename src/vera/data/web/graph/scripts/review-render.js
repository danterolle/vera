import { routeLabel } from "/assets/graph-panels.js";

const $ = selector => document.querySelector(selector);

function text(parent, tag, value, className = "") {
  const element = document.createElement(tag);
  element.textContent = String(value ?? "");
  if (className) element.className = className;
  parent.append(element);
  return element;
}

function section(parent, title, items, empty) {
  const container = document.createElement("section");
  text(container, "h4", title);
  if (items.length) {
    const list = document.createElement("ul");
    items.forEach(item => list.append(item));
    container.append(list);
  } else {
    text(container, "p", empty);
  }
  parent.append(container);
  return container;
}

function item(value) {
  const entry = document.createElement("li");
  entry.textContent = String(value ?? "");
  return entry;
}

function safeLink(parent, title, address) {
  let url;
  try {
    url = new URL(address);
  } catch {
    url = null;
  }
  if (url && ["https:", "http:"].includes(url.protocol)) {
    const link = text(parent, "a", title);
    link.href = url.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  } else {
    text(parent, "strong", title);
  }
}

function renderClaims(parent, record, evidence) {
  const claims = record.draft.claims;
  const entries = claims.map(claim => {
    const entry = document.createElement("li");
    text(entry, "strong", `${claim.status.replaceAll("_", " ")} · ${claim.text}`);
    for (const id of claim.evidence_ids) {
      const source = evidence.get(id);
      text(entry, "small", `Evidence: ${source?.title || id} · ${source?.status || "missing"}`);
    }
    for (const citation of claim.citations) {
      const source = evidence.get(citation.evidence_id);
      text(entry, "small", `Cited: ${source?.title || citation.evidence_id} · ${source?.status || "missing"}`);
      text(entry, "blockquote", citation.supporting_quote);
    }
    return entry;
  });
  section(parent, "Draft claims and cited quotes", entries, "No claims in this draft.");
}

function renderEvidence(parent, sources) {
  const entries = sources.map(source => {
    const entry = document.createElement("li");
    safeLink(entry, source.title, source.url);
    text(entry, "small", `${source.source} · ${source.status} · ${source.id}`);
    text(entry, "blockquote", source.content);
    return entry;
  });
  section(parent, "Evidence and availability", entries, "No evidence in this draft.");
}

function renderIncident(parent, incident) {
  if (!incident) return;
  const area = document.createElement("section");
  text(area, "h4", "Incident context");
  text(area, "p", `${incident.severity} · ${incident.title} · ${incident.summary}`);
  const entries = incident.alerts.map(alert =>
    item(`${alert.severity} · ${alert.title}${alert.description ? ` — ${alert.description}` : ""}`)
  );
  if (entries.length) {
    const list = document.createElement("ul");
    list.append(...entries);
    area.append(list);
  } else {
    text(area, "p", "No alerts.");
  }
  parent.append(area);
}

export function renderReview(record) {
  if (typeof record?.run_id !== "string" || typeof record.version !== "number" ||
      !record.draft || !Array.isArray(record.draft.claims) ||
      !Array.isArray(record.evidence) || !Array.isArray(record.reasons)) {
    throw new Error("The server returned an incomplete review draft.");
  }
  $("#review-state").textContent = record.status === "pending"
    ? "Pending · unpublished draft" : record.status === "approved"
      ? "Approved · report published" : `${record.status} · unpublished draft`;
  $("#review-context").textContent =
    `Run ${record.run_id} · Version ${record.version} · ${routeLabel(record.route)} · ${record.query}`;
  const details = $("#review-details");
  details.replaceChildren();
  section(details, "Why review is required", record.reasons.map(item), "No reason supplied.");
  const overview = document.createElement("section");
  text(overview, "h4", "Draft summary");
  text(overview, "p", record.draft.summary);
  details.append(overview);
  const evidence = new Map(record.evidence.map(source => [source.id, source]));
  renderClaims(details, record, evidence);
  renderEvidence(details, record.evidence);
  renderIncident(details, record.incident);
  const score = record.reflection?.completeness_score;
  const reflection = section(details, "Evidence gaps", (record.reflection?.gaps || []).map(item),
    "No gaps reported.");
  if (typeof score === "number") {
    text(reflection, "p", `Completeness (evidence coverage, not accuracy): ${Math.round(score * 100)}%`);
  }
  section(details, "Warnings", (record.warnings || []).map(item), "No warnings.");
  const history = section(details, "Reviewer history",
    (record.feedback_history || []).map(item), "No prior reviewer feedback.");
  text(history, "p", `Revision count: ${record.revision_count ?? 0}`);
  if (record.error) text(details, "p", `Review error: ${record.error}`, "review-error");
  const retry = record.status === "error" ? record.retry_decision : null;
  if (retry) {
    text(details, "p", `Retry available: ${retry.action} from version ${retry.version}. ` +
      `Feedback: ${retry.feedback || "none"}.`, "review-retry-context");
  }
  $("#review-retry").hidden = !retry;
  $("#review-revise").hidden = record.status !== "pending" || record.can_revise !== true;
  $(".review-actions").hidden = record.status !== "pending";
  $("#review-feedback").hidden = record.status !== "pending";
  $("#review-form label").hidden = record.status !== "pending";
  $("#review-form").hidden = record.status !== "pending" && !retry;
  $("#review-draft").hidden = false;
}
