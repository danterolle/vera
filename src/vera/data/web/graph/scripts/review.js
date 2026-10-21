import { readApi } from "/assets/graph-analysis-report.js";
import { routeLabel } from "/assets/graph-panels.js";
import { renderReview } from "/assets/graph-review-render.js";
import { sendReviewDecision } from "/assets/graph-review-request.js";

const $ = selector => document.querySelector(selector);
const OPEN = new Set(["pending", "processing", "error"]);

export function initializeReview({ onSelect, onApproved }) {
  const list = $("#review-list");
  const feedback = $("#review-feedback");
  const form = $("#review-form");
  const refreshButton = $("#review-refresh");
  const reviews = new Map();
  let active = null;
  let selectionVersion = 0;
  let refreshVersion = 0;
  let refreshPending = 0;
  let busy = false;
  let retry = null;
  function status(message, tone = "info") {
    $("#review-status").textContent = message;
    $("#review-status").dataset.tone = tone;
  }
  function fillList() {
    list.replaceChildren(new Option("Select an open review", ""));
    for (const record of reviews.values()) {
      const label = `${record.status} · ${routeLabel(record.route)} · ${record.query.slice(0, 60)} · ${record.run_id.slice(0, 8)} (v${record.version})`;
      list.add(new Option(label, record.run_id));
    }
    list.value = active && reviews.has(active.run_id) ? active.run_id : "";
  }
  function show(record, { keepFeedback = false } = {}) {
    renderReview(record);
    active = record;
    if (OPEN.has(record.status)) reviews.set(record.run_id, record);
    else reviews.delete(record.run_id);
    fillList();
    if (!keepFeedback) feedback.value = "";
  }
  function close() {
    ++selectionVersion;
    active = null;
    retry = null;
    $("#review-draft").hidden = true;
    feedback.value = "";
    fillList();
    status("");
  }
  function setBusy(value) {
    busy = value;
    list.disabled = value;
    refreshButton.disabled = value || refreshPending > 0;
    form.querySelectorAll("button").forEach(button => { button.disabled = value; });
    form.setAttribute("aria-busy", String(value));
  }
  async function refresh() {
    const current = ++refreshVersion;
    ++refreshPending;
    refreshButton.disabled = true;
    try {
      const records = await readApi(await fetch("/v1/reviews"));
      if (current !== refreshVersion) return;
      if (!Array.isArray(records)) throw new Error("The server returned an invalid review list.");
      reviews.clear();
      for (const record of records) {
        if (OPEN.has(record.status) && typeof record.run_id === "string") {
          reviews.set(record.run_id, record);
        }
      }
      if (active && OPEN.has(active.status)) {
        const next = reviews.get(active.run_id);
        if (next) show(next, { keepFeedback: true });
        else close();
      } else {
        fillList();
      }
      status(`${reviews.size} open review${reviews.size === 1 ? "" : "s"}.`);
    } catch (error) {
      if (current === refreshVersion) status(`Could not refresh pending reviews: ${error.message}`, "error");
    } finally {
      --refreshPending;
      refreshButton.disabled = busy || refreshPending > 0;
    }
  }
  async function select(runId) {
    const current = ++selectionVersion;
    if (!runId) {
      close();
      return;
    }
    onSelect();
    $("#review-draft").hidden = true;
    status("Loading unpublished draft…");
    try {
      const record = await readApi(await fetch(`/v1/reviews/${encodeURIComponent(runId)}`));
      if (current !== selectionVersion) return;
      show(record);
      status(record.status === "pending" ? "Pending human review; not a saved report."
        : `Review status: ${record.status}.`);
    } catch (error) {
      if (current === selectionVersion) status(`Could not load draft: ${error.message}`, "error");
    }
  }
  async function reconcile(runId) {
    try {
      const latest = await readApi(await fetch(`/v1/reviews/${encodeURIComponent(runId)}`));
      if (active?.run_id === runId) show(latest, { keepFeedback: true });
    } catch (error) {
      if (error.status === 404) close();
      else throw error;
    }
    await refresh();
  }

  form.addEventListener("submit", async event => {
    event.preventDefault();
    const requested = event.submitter?.value;
    const previous = requested === "retry" && active?.status === "error"
      ? active.retry_decision : null;
    if (busy || (active?.status !== "pending" && !previous)) return;
    const action = previous?.action || requested;
    if (!["approve", "reject", "revise"].includes(action)) return;
    if (!previous && action === "revise" && active.can_revise !== true) {
      status("Revision is unavailable for this draft.", "error");
      return;
    }
    const comment = previous ? previous.feedback : feedback.value.trim();
    if (!previous && action !== "approve" && !comment) {
      status("Feedback is required to reject or request a revision.", "error");
      feedback.focus();
      return;
    }
    const runId = active.run_id;
    const current = selectionVersion;
    let decision = previous;
    if (!decision) {
      const { version } = active;
      const key = JSON.stringify([runId, version, action, comment]);
      if (retry?.key !== key) retry = { key, id: crypto.randomUUID() };
      decision = { action, version, decision_id: retry.id, feedback: comment || null };
    }
    setBusy(true);
    status(`${previous ? "Retrying previous" : "Submitting"} ${action} decision…`);
    try {
      const result = await sendReviewDecision(runId, decision);
      if (current !== selectionVersion) {
        if (OPEN.has(result.status)) reviews.set(runId, result);
        else reviews.delete(runId);
        fillList();
        return;
      }
      retry = null;
      if (action === "approve") {
        reviews.delete(runId);
        fillList();
        const approval = onApproved(result), afterDispatch = selectionVersion;
        await approval;
        if (afterDispatch !== selectionVersion) return;
        close();
        status("Approved and published. The saved report is selected above.", "success");
      } else {
        show(result);
        status(action === "reject" ? "Rejected. Draft was not published."
          : "Revision requested. Draft remains pending and unpublished.", "success");
      }
    } catch (error) {
      if (current !== selectionVersion) return;
      if (error.status === 409) {
        retry = null;
        try {
          await reconcile(runId);
          status(`Conflict: ${error.message}. Review the refreshed version before retrying.`, "error");
        } catch (reloadError) {
          status(`Conflict: ${error.message}. Refresh failed: ${reloadError.message}`, "error");
        }
      } else {
        const message = `Could not ${action} draft: ${error.message}${error.status === 503
          ? ". Retry the unchanged decision when the service is available." : ""}`;
        if (error.status === 404) await refresh();
        status(message, "error");
      }
    } finally {
      setBusy(false);
    }
  });
  list.addEventListener("change", () => select(list.value));
  refreshButton.addEventListener("click", refresh);
  refresh();
  return {
    receive(record) {
      ++refreshVersion;
      ++selectionVersion;
      onSelect();
      show(record);
      status("Pending human review; this draft is unpublished.", "info");
    },
    clear: close
  };
}
