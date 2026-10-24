import { renderMessages } from "/assets/chat-render.js";
import { conversation, entry, history, readState, remember, saveState } from "/assets/chat-store.js";

const $ = selector => document.querySelector(selector);
const state = readState();
const records = new Map();
const OPEN = new Set(["pending", "processing", "error"]);
let busy = null;
let refreshing = false;
const serverSessions = new Set();

function activeChat() {
  return state.conversations.find(chat => chat.id === state.active);
}

function notice(message = "") {
  $("#app-notice").textContent = message;
  $("#app-notice").hidden = !message;
}

function persist() {
  if (!saveState(state)) notice("Il browser non può salvare la cronologia. La chat resta disponibile finché questa pagina è aperta.");
}

function isOpen(message) {
  return message.live !== false && message.kind === "review" && OPEN.has(message.reviewStatus);
}

function closeSidebar() {
  $("#sidebar").classList.remove("open");
  $("#sidebar-backdrop").hidden = true;
  $("#sidebar-toggle").setAttribute("aria-expanded", "false");
}

function scrollEnd() {
  requestAnimationFrame(() => {
    const area = $("#scroll-area");
    area.scrollTop = area.scrollHeight;
  });
}

function resizeInput() {
  const input = $("#message-input");
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
}

function updateComposer() {
  const chat = activeChat();
  const waiting = chat.entries.some(isOpen);
  const input = $("#message-input");
  if (input.value !== (chat.draft || "")) input.value = chat.draft || "";
  input.disabled = Boolean(busy);
  $("#send-message").disabled = input.disabled || !input.value.trim();
  $("#composer").setAttribute("aria-busy", String(Boolean(busy)));
  $("#composer-hint").textContent = busy ? "VERA sta completando una richiesta…"
    : waiting ? "Puoi rispondere qui o scegliere un'azione sotto la bozza."
      : "Invio per inviare · Maiusc + Invio per andare a capo";
  resizeInput();
}

function renderSidebar() {
  const list = $("#conversations"); list.replaceChildren();
  let pending = 0;
  const chats = state.conversations.filter(chat => !chat.external && chat.entries.length);
  if (!chats.length) {
    const empty = document.createElement("p"); empty.className = "history-empty";
    empty.textContent = "Le tue conversazioni appariranno qui."; list.append(empty);
  }
  for (const chat of [...chats].sort((left, right) => right.updated - left.updated)) {
    const button = document.createElement("button"); button.type = "button";
    button.className = `conversation-link${chat.id === state.active ? " active" : ""}`;
    button.setAttribute("aria-current", chat.id === state.active ? "page" : "false");
    const title = document.createElement("span"); title.className = "conversation-title";
    title.textContent = chat.title; button.append(title);
    const open = chat.entries.filter(isOpen).length;
    pending += open;
    if (open) {
      const badge = document.createElement("span"); badge.className = "conversation-state";
      badge.textContent = "In attesa della tua verifica"; button.append(badge);
    } else if (chat.entries.some(message => message.id === busy)) {
      const badge = document.createElement("span"); badge.className = "conversation-state";
      badge.textContent = "Analisi in corso…"; button.append(badge);
    }
    button.addEventListener("click", () => selectChat(chat.id)); list.append(button);
  }
  $("#review-count").hidden = pending === 0;
  $("#review-count").textContent = `${pending} da rivedere`;
  $("#refresh-reviews").disabled = Boolean(busy) || refreshing;
}

function render({ bottom = false } = {}) {
  const chat = activeChat();
  $("#chat-title").textContent = chat.entries.length ? chat.title : "Nuova chat";
  $("#welcome").hidden = chat.entries.length > 0;
  renderMessages($("#messages"), chat, records, callbacks, busy);
  renderSidebar(); updateComposer();
  if (bottom) scrollEnd();
}

async function readApi(response) {
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

function validateRecord(record) {
  if (typeof record?.run_id !== "string" || !Array.isArray(record.evidence) ||
      (typeof record.answer !== "string" && typeof record.draft?.summary !== "string")) {
    throw new Error("Il server ha restituito una risposta incompleta.");
  }
  return record;
}

function receive(message, record) {
  validateRecord(record);
  remember(message, record); records.set(message.id, record);
  if (message.pendingDecision && (typeof record.answer === "string" ||
      record.version > message.pendingDecision.version || record.status === "rejected")) {
    message.pendingDecision = null;
  }
}

async function loadRecord(message) {
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

async function hydrate(chat) {
  const messages = chat.entries.filter(message => message.runId && message.live !== false);
  await Promise.allSettled(messages.map(async message => {
    if (records.has(message.id)) return;
    try { await loadRecord(message); }
    catch (error) { message.error = `Impossible recuperare il messaggio: ${error.message}`; }
  }));
  persist();
  if (chat.id === state.active) render({ bottom: true });
}

function selectChat(id) {
  state.active = id; persist(); render({ bottom: true }); closeSidebar();
  hydrate(activeChat());
}

function newChat() {
  let chat = state.conversations.find(item => item.entries.length === 0 && !item.draft?.trim());
  if (!chat) { chat = conversation(); state.conversations.push(chat); }
  chat.updated = Date.now(); state.active = chat.id; persist(); render(); closeSidebar();
  $("#message-input").focus();
}

async function refreshReviews() {
  if (refreshing || busy) return;
  refreshing = true; $("#refresh-reviews").disabled = true;
  try {
    const reviews = await readApi(await fetch("/v1/reviews"));
    if (busy) return;
    if (!Array.isArray(reviews)) throw new Error("L'elenco delle richieste non è valido.");
    const existing = new Map();
    for (const chat of state.conversations) {
      for (const message of chat.entries) {
        if (message.runId && message.live !== false) existing.set(message.runId, message);
      }
    }
    for (const record of reviews) {
      validateRecord(record);
      if (!OPEN.has(record.status)) continue;
      for (const oldChat of state.conversations) {
        if (oldChat.id !== record.session_id && oldChat.entries.length <= 2 &&
            oldChat.entries.some(item => item.runId === record.run_id)) oldChat.external = true;
      }
      let message = existing.get(record.run_id);
      const owner = state.conversations.find(chat => chat.entries.includes(message));
      if (owner && record.session_id && owner.id !== record.session_id && owner.entries.length <= 2) {
        owner.external = true;
        message = null;
      }
      if (!message) {
        if (!record.session_id || (!serverSessions.has(record.session_id) && record.metadata?.origin !== "chat")) continue;
        let chat = state.conversations.find(item => item.id === record.session_id);
        if (!chat) {
          chat = conversation(); chat.id = record.session_id; chat.title = record.query;
          state.conversations.push(chat);
        }
        message = entry("assistant");
        chat.entries.push(entry("user", record.query), message);
      }
      receive(message, record);
    }
    const openIds = new Set(reviews.map(record => record.run_id));
    await Promise.allSettled([...existing.values()].filter(message => isOpen(message) &&
      !openIds.has(message.runId)).map(async message => {
      try { await loadRecord(message); }
      catch (error) { message.error = error.message; }
    }));
    if (activeChat()?.external) newChat();
    persist(); render();
  } catch (error) { notice(`Non riesco ad aggiornare le richieste da rivedere: ${error.message}`); }
  finally { refreshing = false; $("#refresh-reviews").disabled = false; }
}

async function analyze(chat, user, assistant) {
  if (busy) return;
  busy = assistant.id; assistant.kind = "loading"; assistant.error = null;
  persist(); render({ bottom: true });
  try {
    const response = await fetch("/v1/analyze", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: user.content, session_id: chat.id, origin: "chat", conversation: history(chat, user.id) })
    });
    const record = await readApi(response);
    if (![200, 202].includes(response.status)) throw new Error("Stato della risposta inatteso.");
    receive(assistant, record);
  } catch (error) {
    assistant.kind = "error";
    assistant.error = `Non riesco a completare la richiesta: ${error.message}. Puoi riprovare.`;
  } finally {
    busy = null; chat.updated = Date.now(); persist(); render({ bottom: chat.id === state.active });
    if (!$("#message-input").disabled) $("#message-input").focus();
  }
}

async function refreshMessage(message) {
  if (busy) return;
  try { await loadRecord(message); }
  catch (error) { message.error = `Non riesco ad aggiornare la risposta: ${error.message}`; }
  persist(); render();
}

async function decide(message, action) {
  const record = records.get(message.id);
  const chat = state.conversations.find(item => item.entries.includes(message));
  if (busy || !record || !chat) return;
  const retry = action === "retry";
  let decision = retry ? message.pendingDecision || record.retry_decision : null;
  if (!retry) {
    if (record.status !== "pending" || !["approve", "reject", "revise"].includes(action)) return;
    if (action === "revise" && !record.can_revise) return;
    const feedback = (message.feedback || "").trim();
    if (action !== "approve" && !feedback) {
      message.error = "Scrivi un'indicazione prima di inviare la decisione."; render(); return;
    }
    decision = { action, version: record.version, decision_id: crypto.randomUUID(), feedback: feedback || null };
  }
  if (!decision) return;
  message.pendingDecision = decision; message.error = null; busy = message.id;
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
    if (error.status === 409 || error.status === 422 || error.status === 404 || error.status === 403) {
      message.pendingDecision = null;
    }
    if (error.status === 409 || error.status === 503) {
      try { await loadRecord(message); message.error = `${error.message}. Ho aggiornato lo stato della bozza.`; }
      catch { /* Retain the exact decision so an interrupted action can be retried safely. */ }
    }
  } finally {
    busy = null; persist(); render({ bottom: chat.id === state.active });
    if (!$("#message-input").disabled) $("#message-input").focus();
  }
}

const callbacks = {
  decide,
  refresh: refreshMessage,
  intent(message, action) {
    if (busy) return;
    message.feedbackAction = action; message.error = null; persist(); render();
    if (action) document.getElementById(`feedback-${message.id}`)?.focus();
  },
  feedback(message, value) { message.feedback = value; message.updatedAt = Date.now(); persist(); },
  retry(message) {
    const chat = state.conversations.find(item => item.entries.includes(message));
    const user = chat?.entries.find(item => item.id === message.replyTo);
    if (user) analyze(chat, user, message);
    else { message.error = "La domanda originale non è disponibile. Invia un nuovo messaggio."; render(); }
  },
  async copy(message) {
    try {
      await navigator.clipboard.writeText(records.get(message.id)?.answer || message.content);
      notice("Risposta copiata.");
    } catch { notice("Il browser non consente la copia automatica. Puoi selezionare il testo del messaggio."); }
  }
};

$("#composer").addEventListener("submit", event => {
  event.preventDefault();
  const chat = activeChat();
  const query = $("#message-input").value.trim();
  if (!query || busy) return;
  const pending = [...chat.entries].reverse().find(message => isOpen(message) && records.get(message.id)?.can_revise);
  if (pending) {
    pending.feedback = query; chat.draft = "";
    decide(pending, "revise"); return;
  }
  const user = entry("user", query), assistant = entry("assistant"); assistant.replyTo = user.id;
  if (!chat.entries.length) chat.title = query;
  chat.entries.push(user, assistant); chat.draft = ""; chat.updated = Date.now();
  notice(); analyze(chat, user, assistant);
});
$("#message-input").addEventListener("input", event => {
  activeChat().draft = event.target.value; persist(); updateComposer();
});
$("#message-input").addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    if (!$("#send-message").disabled) $("#composer").requestSubmit();
  }
});
$("#new-chat").addEventListener("click", newChat);
$("#review-count").addEventListener("click", () => {
  const pending = [...state.conversations].sort((left, right) => right.updated - left.updated)
    .find(chat => chat.entries.some(isOpen));
  if (pending) selectChat(pending.id);
});
$("#refresh-reviews").addEventListener("click", refreshReviews);
$("#sidebar-toggle").addEventListener("click", () => {
  const open = $("#sidebar").classList.toggle("open");
  $("#sidebar-backdrop").hidden = !open;
  $("#sidebar-toggle").setAttribute("aria-expanded", String(open));
});
$("#sidebar-backdrop").addEventListener("click", closeSidebar);
document.addEventListener("keydown", event => { if (event.key === "Escape") closeSidebar(); });
document.querySelectorAll("[data-prompt]").forEach(button => {
  button.addEventListener("click", () => {
    activeChat().draft = button.dataset.prompt; persist(); updateComposer(); $("#message-input").focus();
  });
});

render(); persist();
hydrate(activeChat());
restoreSessions().then(refreshReviews);
fetch("/health").then(readApi).then(health => {
  $("#model-label").textContent = health.model || "Risposte deterministiche";
}).catch(() => { $("#model-label").textContent = "Connessione al servizio non disponibile"; });

async function restoreSessions() {
  try {
    const sessions = await readApi(await fetch("/v1/conversations"));
    if (!Array.isArray(sessions) || busy) return;
    for (const session of sessions) {
      serverSessions.add(session.id);
      let chat = state.conversations.find(item => item.id === session.id);
      if (!chat) { chat = conversation(); chat.id = session.id; chat.title = session.title;
        chat.updated = 0; state.conversations.push(chat); }
      for (const turn of session.turns) {
        if (chat.entries.some(message => message.runId === turn.run_id)) continue;
        const user = entry("user", turn.query), assistant = entry("assistant", turn.summary);
        const timestamp = Date.parse(turn.created_at) || chat.updated || Date.now();
        user.id = `user-${turn.run_id}`; user.created = timestamp;
        assistant.id = `assistant-${turn.run_id}`; assistant.created = timestamp + 1;
        assistant.runId = turn.run_id; assistant.kind = turn.kind; assistant.live = true;
        assistant.reviewStatus = turn.status; assistant.version = turn.version;
        assistant.replyTo = user.id;
        chat.entries.push(user, assistant); chat.updated = Math.max(chat.updated, timestamp);
      }
      chat.entries.sort((a, b) => (a.created || 0) - (b.created || 0));
    }
    const owners = new Map(sessions.flatMap(session => session.turns.map(turn => [turn.run_id, session.id])));
    for (const chat of state.conversations) {
      const replies = chat.entries.filter(message => message.runId);
      if (replies.length && chat.entries.length <= 2 && replies.every(message =>
        owners.has(message.runId) && owners.get(message.runId) !== chat.id)) chat.external = true;
    }
    if (activeChat()?.external) newChat();
    persist(); render(); await hydrate(activeChat());
  } catch (error) { notice(`Cronologia locale disponibile; sincronizzazione non riuscita: ${error.message}`); }
}
