import { remember } from "/assets/chat-store.js";

export const records = new Map();
export const OPEN = new Set(["pending", "processing", "error"]);

export function isOpen(message) {
  return message.live !== false && message.kind === "review" && OPEN.has(message.reviewStatus);
}

export async function readApi(response) {
  let body;
  try { body = await response.json(); }
  catch { throw new Error("Il server ha restituito una risposta non leggibile."); }
  if (!response.ok) {
    const detail = body?.detail;
    const message = typeof detail === "string" ? detail : Array.isArray(detail)
      ? detail.map(item => item.msg).join("; ") : `Il server ha risposto con errore ${response.status}.`;
    const error = new Error(message); error.status = response.status; throw error;
  }
  return body;
}

export function validateRecord(record) {
  if (typeof record?.run_id !== "string" || !Array.isArray(record.evidence) ||
      (typeof record.answer !== "string" && typeof record.draft?.summary !== "string")) {
    throw new Error("Il server ha restituito una risposta incompleta.");
  }
  return record;
}

export function receive(message, record) {
  validateRecord(record);
  remember(message, record); records.set(message.id, record);
  if (message.pendingDecision && (typeof record.answer === "string" ||
      record.version > message.pendingDecision.version || record.status === "rejected")) {
    message.pendingDecision = null;
  }
}

export async function loadRecord(message) {
  let record;
  if (message.kind === "result") {
    record = await readApi(await fetch(`/v1/runs/${encodeURIComponent(message.runId)}`));
  } else {
    record = await readApi(await fetch(`/v1/reviews/${encodeURIComponent(message.runId)}`));
    if (record.status === "approved") {
      record = await readApi(await fetch(`/v1/runs/${encodeURIComponent(message.runId)}`));
    }
  }
  receive(message, record);
}
