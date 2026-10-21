import { readApi } from "/assets/graph-analysis-report.js";

export async function sendReviewDecision(runId, decision) {
  const response = await fetch(`/v1/reviews/${encodeURIComponent(runId)}/decisions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(decision)
  });
  const result = await readApi(response);
  if (response.status !== (decision.action === "revise" ? 202 : 200)) {
    throw new Error(`Unexpected decision response (HTTP ${response.status}).`);
  }
  return result;
}
