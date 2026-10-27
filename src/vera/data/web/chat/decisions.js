import { loadRecord, readApi, receive, records, validateRecord } from "/assets/chat-records.js";
import { entry } from "/assets/chat-store.js";

export function createDecisions(context) {
  const { state, runtime, persist, render, notice, analyze } = context;

  async function refreshMessage(message) {
    if (runtime.busy) return;
    try { await loadRecord(message); }
    catch (error) { message.error = `Non riesco ad aggiornare la risposta: ${error.message}`; }
    persist(); render();
  }

  async function decide(message, action) {
    const record = records.get(message.id);
    const chat = state.conversations.find(item => item.entries.includes(message));
    if (runtime.busy || !record || !chat) return;
    const retry = action === "retry";
    let decision = retry ? message.pendingDecision || record.retry_decision : null;
    if (!retry) {
      if (record.status !== "pending" || !["approve", "reject", "revise"].includes(action)) return;
      if (action === "revise" && !record.can_revise) return;
      const feedback = (message.feedback || "").trim();
      if (action !== "approve" && !feedback) {
        message.error = "Scrivi un'indicazione prima di inviare la decisione."; render(); return;
      }
      decision = {
        action, version: record.version, decision_id: crypto.randomUUID(), feedback: feedback || null
      };
    }
    if (!decision) return;
    message.pendingDecision = decision; message.error = null; runtime.busy = message.id;
    persist(); render();
    try {
      const response = await fetch(`/v1/reviews/${encodeURIComponent(message.runId)}/decisions`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(decision)
      });
      const result = validateRecord(await readApi(response));
      if (response.status !== (decision.action === "revise" ? 202 : 200)) {
        throw new Error("Stato della decisione inatteso. Aggiorna la richiesta prima di riprovare.");
      }
      message.pendingDecision = null; message.feedbackAction = null; message.feedback = "";
      if (decision.action === "revise") {
        message.live = false;
        message.updatedAt = Date.now();
        const feedback = entry("user", decision.feedback); feedback.kind = "feedback";
        const next = entry("assistant"); receive(next, result);
        chat.entries.push(feedback, next);
      } else {
        receive(message, result);
        if (decision.action === "reject") {
          message.content = "Ho rifiutato la bozza: non è stata pubblicata. Puoi continuare la conversazione.";
        }
      }
      chat.updated = Date.now();
    } catch (error) {
      message.error = `Non ho ricevuto conferma della decisione: ${error.message}`;
      if ([409, 422, 404, 403].includes(error.status)) message.pendingDecision = null;
      if (error.status === 409 || error.status === 503) {
        try {
          await loadRecord(message);
          message.error = `${error.message}. Ho aggiornato lo stato della bozza.`;
        } catch { /* Preserve the exact decision for an idempotent retry. */ }
      }
    } finally {
      runtime.busy = null; persist(); render({ bottom: chat.id === state.active });
      const input = document.querySelector("#message-input");
      if (!input.disabled) input.focus();
    }
  }

  return {
    decide,
    refresh: refreshMessage,
    intent(message, action) {
      if (runtime.busy) return;
      message.feedbackAction = action; message.error = null; persist(); render();
      if (action) document.getElementById(`feedback-${message.id}`)?.focus();
    },
    feedback(message, value) { message.feedback = value; message.updatedAt = Date.now(); persist(); },
    retry(message) {
      const chat = state.conversations.find(item => item.entries.includes(message));
      const user = chat?.entries.find(item => item.id === message.replyTo);
      if (user) analyze(chat, user, message);
      else {
        message.error = "La domanda originale non è disponibile. Invia un nuovo messaggio."; render();
      }
    },
    async copy(message) {
      try {
        await navigator.clipboard.writeText(records.get(message.id)?.answer || message.content);
        notice("Risposta copiata.");
      } catch {
        notice("Il browser non consente la copia automatica. Puoi selezionare il testo del messaggio.");
      }
    }
  };
}
