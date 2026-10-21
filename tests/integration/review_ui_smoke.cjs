const { readFileSync } = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const { webcrypto } = require("node:crypto");

const elements = new Map();
function element(id) {
  if (!elements.has(id)) {
    elements.set(id, {
      hidden: true, disabled: false, value: "", textContent: "", dataset: {}, listeners: {},
      children: [], addEventListener(name, fn) { this.listeners[name] = fn; },
      setAttribute() {}, removeAttribute() {}, focus() {},
      replaceChildren(...children) { this.children = children; },
      append(...children) { this.children.push(...children); },
      add(child) { this.children.push(child); },
      querySelectorAll() { return [{ disabled: false }, { disabled: false }, { disabled: false }]; }
    });
  }
  return elements.get(id);
}

const record = { run_id: "draft", status: "pending", can_revise: true, version: 1, route: "CAG_RAG",
  query: "Question", draft: { summary: "Draft", claims: [] }, reasons: ["Check quote"],
  evidence: [], reflection: { completeness_score: .5, gaps: [] }, warnings: [],
  feedback_history: [], revision_count: 0 };
const report = { run_id: "draft", answer: "Final", claims: [], evidence: [] };
let latest = record;
const decisionReplies = [];
const calls = [];
let delayedDecision;
async function fetch(url, options = {}) {
  calls.push({ url, options });
  if (url === "/v1/analyze") return { ok: true, status: 202, body: record };
  if (url === "/v1/reviews") return { ok: true, status: 200, body: [latest] };
  if (url.endsWith("/decisions")) return delayedDecision || decisionReplies.shift();
  if (url === "/v1/runs/saved") return { ok: true, status: 200, body: report };
  if (url.startsWith("/v1/reviews/")) return { ok: true, status: 200, body: latest };
  throw new Error(`Unexpected request: ${url}`);
}
async function readApi(response) {
  if (response.ok) return response.body;
  const error = new Error(response.body.detail);
  error.status = response.status;
  throw error;
}
const document = {
  querySelector(selector) { return element(selector.startsWith("#") ? selector.slice(1) : selector); },
  createElement(tag) {
    return { tag, children: [], textContent: "",
      append(...children) { this.children.push(...children); },
      replaceChildren(...children) { this.children = children; } };
  }
};
function evaluate(file, symbol, bindings) {
  const source = readFileSync(`src/vera/data/web/graph/scripts/${file}.js`, "utf8")
    .replace(/^import .*;\s*$/gm, "").replaceAll("export function ", "function ")
    .replaceAll("export async function ", "async function ");
  const context = vm.createContext({ document, fetch, readApi, crypto: webcrypto, URL,
    Option: function(label, value) { return { label, value }; }, ...bindings });
  vm.runInContext(`${source}\nglobalThis.entry = ${symbol};`, context);
  return context.entry;
}
const renderReview = evaluate("review-render", "renderReview", { routeLabel: route => route });
const sendReviewDecision = evaluate("review-request", "sendReviewDecision", {});
const initializeAnalysis = evaluate("analysis", "initializeAnalysis", {
  renderReport(value) { element("analysis-result").hidden = false; }
});
const initializeReview = evaluate("review", "initializeReview", {
  renderReview, sendReviewDecision, routeLabel: route => route
});
const decisionCalls = () => calls.filter(call => call.url.endsWith("/decisions"));
const lastDecision = () => JSON.parse(decisionCalls().at(-1).options.body);
const submit = action => element("review-form").listeners.submit({
  preventDefault() {}, submitter: { value: action }
});

(async () => {
  const saved = [];
  let review;
  let releaseApproval;
  const analysis = initializeAnalysis(async runId => {
    review.clear();
    saved.push(runId);
    if (runId === "late-approval") await new Promise(resolve => { releaseApproval = resolve; });
  },
    value => review.receive(value));
  review = initializeReview({ onSelect: () => analysis.clear(),
    onApproved: value => analysis.showApproved(value) });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls[0].url, "/v1/reviews");
  element("analysis-query").value = "Question";
  await element("analysis-form").listeners.submit({ preventDefault() {} });
  assert.equal(saved.length, 0);
  assert.equal(element("analysis-result").hidden, true);
  assert.equal(element("review-draft").hidden, false);
  assert.equal(element("review-retry").hidden, true);
  assert.equal(element("review-revise").hidden, false);
  assert.match(element("analysis-status").textContent, /not a saved report/);
  await submit("revise");
  assert.match(element("review-status").textContent, /Feedback is required/);
  assert.equal(decisionCalls().length, 0);
  element("review-feedback").value = "Add a source";
  decisionReplies.push({ ok: true, status: 202, body: { ...record, version: 2 } });
  await submit("revise");
  assert.equal(lastDecision().version, 1);
  assert.equal(lastDecision().feedback, "Add a source");
  assert.match(lastDecision().decision_id, /^[\w-]{36}$/);
  assert.match(element("review-context").textContent, /Version 2/);
  latest = { ...record, version: 3 };
  element("review-feedback").value = "Still missing a source";
  decisionReplies.push({ ok: false, status: 409, body: { detail: "Stale version" } });
  await submit("revise");
  assert.match(element("review-context").textContent, /Version 3/);
  assert.equal(element("review-feedback").value, "Still missing a source");
  assert.match(element("review-status").textContent, /Conflict/);
  decisionReplies.push({ ok: false, status: 503, body: { detail: "Unavailable" } });
  await submit("approve");
  const retryId = lastDecision().decision_id;
  assert.match(element("review-status").textContent, /Retry the unchanged decision/);
  decisionReplies.push({ ok: true, status: 200, body: report });
  await submit("approve");
  assert.equal(lastDecision().version, 3);
  assert.equal(lastDecision().decision_id, retryId);
  assert.deepEqual(saved, ["draft"]);
  assert.equal(element("analysis-result").hidden, false);
  assert.equal(element("review-draft").hidden, true);
  review.receive({ ...record, run_id: "rejected" });
  element("review-feedback").value = "Insufficient evidence";
  decisionReplies.push({ ok: true, status: 200,
    body: { ...record, run_id: "rejected", status: "rejected" } });
  await submit("reject");
  assert.deepEqual(saved, ["draft"]);
  assert.equal(element("review-form").hidden, true);
  assert.match(element("review-status").textContent, /not published/);
  const prior = { action: "approve", version: 4, decision_id: webcrypto.randomUUID(),
    feedback: "Original feedback" };
  latest = { ...record, run_id: "recovery", status: "error", version: 4,
    error: "Interrupted by restart", retry_decision: prior };
  await element("review-refresh").listeners.click();
  element("review-list").value = "recovery";
  await element("review-list").listeners.change();
  assert.equal(element("review-form").hidden, false);
  assert.equal(element("review-retry").hidden, false);
  assert.equal(element(".review-actions").hidden, true);
  const before = decisionCalls().length;
  await submit("approve");
  assert.equal(decisionCalls().length, before);
  decisionReplies.push({ ok: true, status: 200, body: { ...report, run_id: "recovery" } });
  await submit("retry");
  assert.deepEqual(lastDecision(), prior);
  assert.deepEqual(saved, ["draft", "recovery"]);
  latest = { ...record, run_id: "unrecoverable", status: "error",
    error: "No decision available", retry_decision: null };
  await element("review-refresh").listeners.click();
  element("review-list").value = "unrecoverable";
  await element("review-list").listeners.change();
  assert.equal(element("review-form").hidden, true);
  assert.equal(element("review-retry").hidden, true);
  const unchanged = decisionCalls().length;
  await submit("retry");
  assert.equal(decisionCalls().length, unchanged);
  review.receive({ ...record, run_id: "limit-reached", can_revise: false, revision_count: 2 });
  assert.equal(element("review-revise").hidden, true);
  await submit("revise");
  assert.equal(decisionCalls().length, unchanged);
  assert.match(element("review-status").textContent, /Revision is unavailable/);
  const runHandler = readFileSync("src/vera/data/web/graph/scripts/app.js", "utf8")
    .match(/runSelect.addEventListener\("change", \(\) => \{[\s\S]*?\n\}\);/)[0];
  vm.runInNewContext(runHandler, { runSelect: element("run"), review, analysis,
    load: async () => {}, showError() {} });
  review.receive({ ...record, run_id: "race" });
  element("review-feedback").value = "Fix the citation";
  let releaseDecision;
  delayedDecision = new Promise(resolve => { releaseDecision = resolve; });
  const pending = submit("revise");
  assert.equal(element("review-list").disabled, true);
  element("run").value = "saved";
  element("run").listeners.change();
  assert.equal(element("review-draft").hidden, true);
  releaseDecision({ ok: true, status: 202, body: { ...record, run_id: "race", version: 2 } });
  await pending;
  assert.equal(element("review-draft").hidden, true);
  assert.equal(element("run").value, "saved");
  assert.equal(element("review-list").disabled, false);
  assert.match(element("review-list").children.find(option => option.value === "race").label, /v2/);
  review.receive({ ...record, run_id: "late-approval" });
  delayedDecision = null;
  decisionReplies.push({ ok: true, status: 200, body: { ...report, run_id: "late-approval" } });
  const approving = submit("approve");
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(typeof releaseApproval, "function");
  assert.equal(element("review-list").disabled, true);
  element("run").value = "saved";
  element("run").listeners.change();
  releaseApproval();
  await approving;
  assert.equal(element("run").value, "saved");
  assert.equal(element("review-list").children.some(option => option.value === "late-approval"), false);
  assert.equal(element("review-status").textContent, "");
})().catch(error => { console.error(error); process.exitCode = 1; });
