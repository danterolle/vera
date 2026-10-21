import { readApi, renderReport } from "/assets/graph-analysis-report.js";

const $ = selector => document.querySelector(selector);
const resultPanel = $("#analysis-result");
const status = $("#analysis-status");

function setStatus(message, tone = "info") {
  status.textContent = message;
  status.dataset.tone = tone;
}

export function initializeAnalysis(onSaved, onPending) {
  const form = $("#analysis-form");
  const input = $("#analysis-query");
  const submit = $("#analysis-submit");
  let requestNumber = 0;

  async function showSaved(report, message, current) {
    renderReport(report);
    try {
      await onSaved(report.run_id);
      if (current === requestNumber) setStatus(message, "success");
    } catch (error) {
      if (current === requestNumber) {
        setStatus(`Analysis saved, but the diagram could not refresh: ${error.message}`, "error");
      }
    }
  }

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
      const result = await readApi(response);
      if (current !== requestNumber) return;
      if (response.status === 202) {
        onPending(result);
        setStatus("Awaiting human review. The draft is not a saved report.");
      } else if (response.status === 200) {
        await showSaved(result, "Analysis complete.", current);
      } else {
        throw new Error(`Unexpected analysis response (HTTP ${response.status}).`);
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
    async showApproved(report) {
      const current = ++requestNumber;
      resultPanel.hidden = true;
      await showSaved(report, "Review approved. Analysis saved.", current);
    },
    async showRun(runId) {
      const current = ++requestNumber;
      resultPanel.hidden = true;
      setStatus("Loading report…");
      try {
        const report = await readApi(await fetch(`/v1/runs/${encodeURIComponent(runId)}`));
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
