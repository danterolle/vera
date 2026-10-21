import { routeLabel } from "/assets/graph-panels.js";

const $ = selector => document.querySelector(selector);
const resultPanel = $("#analysis-result");
const status = $("#analysis-status");

function setStatus(message, tone = "info") {
  status.textContent = message;
  status.dataset.tone = tone;
}

function addText(parent, tag, content, className = "") {
  const element = document.createElement(tag);
  element.textContent = content;
  if (className) element.className = className;
  parent.append(element);
  return element;
}

function assessment(answer) {
  const text = answer.startsWith("## Assessment\n")
    ? answer.slice("## Assessment\n".length) : answer;
  return text.split("\n\n## ")[0].trim();
}

function renderClaims(claims, evidenceById) {
  const list = $("#analysis-claims");
  list.replaceChildren();
  if (!claims.length) {
    addText(list, "li", "No findings for this request.", "analysis-empty");
    return;
  }
  claims.forEach(claim => {
    const item = document.createElement("li");
    addText(item, "span", claim.status.replaceAll("_", " "), `claim-status ${claim.status}`);
    addText(item, "p", claim.text);
    claim.citations.forEach(citation => {
      if (citation.supporting_quote !== claim.text) {
        addText(item, "blockquote", citation.supporting_quote);
      }
    });
    const titles = claim.evidence_ids.map(id => evidenceById.get(id)?.title || `Missing: ${id}`);
    if (titles.length) addText(item, "small", `Evidence: ${titles.join(", ")}`);
    list.append(item);
  });
}

function renderSources(claims, evidenceById) {
  const list = $("#analysis-sources");
  list.replaceChildren();
  const ids = new Set(claims.flatMap(claim => claim.evidence_ids));
  if (!ids.size) {
    addText(list, "li", "No evidence cited in the final findings.", "analysis-empty");
    return;
  }
  ids.forEach(id => {
    const source = evidenceById.get(id);
    const item = document.createElement("li");
    const title = source?.title || `Missing evidence: ${id}`;
    let url;
    try {
      if (source?.url) url = new URL(source.url);
    } catch {
      url = null;
    }
    if (url && ["https:", "http:"].includes(url.protocol)) {
      const link = addText(item, "a", title);
      link.href = url.href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    } else {
      addText(item, "span", title);
    }
    addText(item, "small", `${source?.source || "unknown"} · ${source?.status || "missing"}`);
    list.append(item);
  });
}

function renderIncident(incident) {
  const panel = $("#analysis-incident");
  panel.hidden = !incident;
  if (!incident) return;
  $("#analysis-incident-summary").textContent = incident.summary;
  const actions = $("#analysis-actions");
  actions.replaceChildren();
  incident.recommended_actions.forEach(action => addText(actions, "li", action));
}

function renderReport(report) {
  if (typeof report.run_id !== "string" || typeof report.answer !== "string" ||
      !Array.isArray(report.claims) || !Array.isArray(report.evidence)) {
    throw new Error("The server returned an incomplete analysis report.");
  }
  const evidenceById = new Map(report.evidence.map(source => [source.id, source]));
  $("#analysis-route").textContent = routeLabel(report.route);
  const provider = report.metadata.provider_fallback
    ? "Deterministic fallback" : report.metadata.model || "Deterministic provider";
  $("#analysis-provider").textContent = provider;
  $("#analysis-provider").classList.toggle("fallback", Boolean(report.metadata.provider_fallback));
  $("#analysis-latency").textContent = `${(report.metrics.latency_ms / 1000).toFixed(1)} s`;
  $("#analysis-assessment").textContent = assessment(report.answer);
  renderIncident(report.incident);
  renderClaims(report.claims, evidenceById);
  renderSources(report.claims, evidenceById);
  const warnings = [
    ...(report.metadata.provider_fallback ? ["The model failed; a deterministic answer was used."] : []),
    ...report.warnings,
    ...(report.reflection.validation_failures
      ? [`${report.reflection.validation_failures} claim validation issue(s); review the full report.`]
      : [])
  ];
  const warning = $("#analysis-warning");
  warning.hidden = !warnings.length;
  warning.textContent = warnings.join(" ");
  $("#analysis-run-link").href = `/v1/runs/${encodeURIComponent(report.run_id)}`;
  resultPanel.hidden = false;
}

async function readReport(response) {
  const body = await response.json();
  if (response.ok) return body;
  const detail = body.detail;
  const message = typeof detail === "string" ? detail
    : Array.isArray(detail) ? detail.map(item => item.msg).join("; ")
      : `HTTP ${response.status}`;
  throw new Error(message || `HTTP ${response.status}`);
}

export function initializeAnalysis(onSaved) {
  const form = $("#analysis-form");
  const input = $("#analysis-query");
  const submit = $("#analysis-submit");
  let requestNumber = 0;

  form.addEventListener("submit", async event => {
    event.preventDefault();
    const query = input.value.trim();
    if (!query) {
      setStatus("Enter a question before running an analysis.", "error");
      return;
    }
    const current = ++requestNumber;
    submit.disabled = true;
    input.disabled = true;
    form.setAttribute("aria-busy", "true");
    resultPanel.hidden = true;
    setStatus("Analyzing…");
    try {
      const response = await fetch("/v1/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query })
      });
      const report = await readReport(response);
      if (current !== requestNumber) return;
      renderReport(report);
      try {
        await onSaved(report.run_id);
        if (current === requestNumber) {
          setStatus("Analysis complete.", "success");
        }
      } catch (error) {
        if (current === requestNumber) {
          setStatus(`Analysis saved, but the diagram could not refresh: ${error.message}`, "error");
        }
      }
    } catch (error) {
      if (current === requestNumber) setStatus(`Analysis failed: ${error.message}`, "error");
    } finally {
      submit.disabled = false;
      input.disabled = false;
      form.removeAttribute("aria-busy");
    }
  });

  return {
    async showRun(runId) {
      const current = ++requestNumber;
      resultPanel.hidden = true;
      setStatus("Loading report…");
      try {
        const report = await readReport(await fetch(`/v1/runs/${encodeURIComponent(runId)}`));
        if (current !== requestNumber) return;
        renderReport(report);
        setStatus("Saved analysis.", "success");
      } catch (error) {
        if (current === requestNumber) setStatus(`Could not load the saved report: ${error.message}`, "error");
      }
    },
    clear() {
      requestNumber += 1;
      resultPanel.hidden = true;
      setStatus("");
    }
  };
}
