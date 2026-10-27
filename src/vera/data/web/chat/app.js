import { createDecisions } from "/assets/chat-decisions.js";
import { createHistory } from "/assets/chat-history.js";
import { isOpen, readApi, receive, records } from "/assets/chat-records.js";
import { renderMessages } from "/assets/chat-render.js";
import { entry, history, readState, saveState } from "/assets/chat-store.js";

const $ = selector => document.querySelector(selector);
const state = readState();
const runtime = { busy: null, refreshing: false, serverSessions: new Set() };
const context = { state, runtime, activeChat, persist, render, notice, closeSidebar, analyze };
const callbacks = createDecisions(context);
const chatHistory = createHistory(context);

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
  input.disabled = Boolean(runtime.busy);
  $("#send-message").disabled = input.disabled || !input.value.trim();
  $("#composer").setAttribute("aria-busy", String(Boolean(runtime.busy)));
  $("#composer-hint").textContent = runtime.busy ? "VERA sta completando una richiesta…"
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
    } else if (chat.entries.some(message => message.id === runtime.busy)) {
      const badge = document.createElement("span"); badge.className = "conversation-state";
      badge.textContent = "Analisi in corso…"; button.append(badge);
    }
    button.addEventListener("click", () => chatHistory.selectChat(chat.id)); list.append(button);
  }
  $("#review-count").hidden = pending === 0;
  $("#review-count").textContent = `${pending} da rivedere`;
  $("#refresh-reviews").disabled = Boolean(runtime.busy) || runtime.refreshing;
}

function render({ bottom = false } = {}) {
  const chat = activeChat();
  $("#chat-title").textContent = chat.entries.length ? chat.title : "Nuova chat";
  $("#welcome").hidden = chat.entries.length > 0;
  renderMessages($("#messages"), chat, records, callbacks, runtime.busy);
  renderSidebar(); updateComposer();
  if (bottom) scrollEnd();
}

async function analyze(chat, user, assistant) {
  if (runtime.busy) return;
  runtime.busy = assistant.id; assistant.kind = "loading"; assistant.error = null;
  persist(); render({ bottom: true });
  try {
    const response = await fetch("/v1/analyze", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: user.content, session_id: chat.id, origin: "chat", conversation: history(chat, user.id)
      })
    });
    const record = await readApi(response);
    if (![200, 202].includes(response.status)) throw new Error("Stato della risposta inatteso.");
    receive(assistant, record);
  } catch (error) {
    assistant.kind = "error";
    assistant.error = `Non riesco a completare la richiesta: ${error.message}. Puoi riprovare.`;
  } finally {
    runtime.busy = null; chat.updated = Date.now(); persist(); render({ bottom: chat.id === state.active });
    if (!$("#message-input").disabled) $("#message-input").focus();
  }
}

$("#composer").addEventListener("submit", event => {
  event.preventDefault();
  const chat = activeChat();
  const query = $("#message-input").value.trim();
  if (!query || runtime.busy) return;
  const pending = [...chat.entries].reverse().find(message =>
    isOpen(message) && records.get(message.id)?.can_revise);
  if (pending) {
    pending.feedback = query; chat.draft = "";
    callbacks.decide(pending, "revise"); return;
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
$("#new-chat").addEventListener("click", chatHistory.newChat);
$("#review-count").addEventListener("click", () => {
  const pending = [...state.conversations].sort((left, right) => right.updated - left.updated)
    .find(chat => chat.entries.some(isOpen));
  if (pending) chatHistory.selectChat(pending.id);
});
$("#refresh-reviews").addEventListener("click", chatHistory.refreshReviews);
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
chatHistory.hydrate(activeChat());
chatHistory.restoreSessions().then(chatHistory.refreshReviews);
fetch("/health").then(readApi).then(health => {
  $("#model-label").textContent = health.model || "Risposte deterministiche";
}).catch(() => { $("#model-label").textContent = "Connessione al servizio non disponibile"; });
