import { isOpen, loadRecord, OPEN, readApi, receive, records, validateRecord } from "/assets/chat-records.js";
import { conversation, entry } from "/assets/chat-store.js";

export function createHistory(context) {
  const { state, runtime, activeChat, persist, render, closeSidebar, notice } = context;

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
    document.querySelector("#message-input").focus();
  }

  async function refreshReviews() {
    if (runtime.refreshing || runtime.busy) return;
    runtime.refreshing = true;
    document.querySelector("#refresh-reviews").disabled = true;
    try {
      const reviews = await readApi(await fetch("/v1/reviews"));
      if (runtime.busy) return;
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
          if (!record.session_id ||
              (!runtime.serverSessions.has(record.session_id) && record.metadata?.origin !== "chat")) continue;
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
    finally {
      runtime.refreshing = false;
      document.querySelector("#refresh-reviews").disabled = false;
    }
  }

  async function restoreSessions() {
    try {
      const sessions = await readApi(await fetch("/v1/conversations"));
      if (!Array.isArray(sessions) || runtime.busy) return;
      for (const session of sessions) {
        runtime.serverSessions.add(session.id);
        let chat = state.conversations.find(item => item.id === session.id);
        if (!chat) {
          chat = conversation(); chat.id = session.id; chat.title = session.title;
          chat.updated = 0; state.conversations.push(chat);
        }
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
      const owners = new Map(sessions.flatMap(session =>
        session.turns.map(turn => [turn.run_id, session.id])));
      for (const chat of state.conversations) {
        const replies = chat.entries.filter(message => message.runId);
        if (replies.length && chat.entries.length <= 2 && replies.every(message =>
          owners.has(message.runId) && owners.get(message.runId) !== chat.id)) chat.external = true;
      }
      if (activeChat()?.external) newChat();
      persist(); render(); await hydrate(activeChat());
    } catch (error) {
      notice(`Cronologia locale disponibile; sincronizzazione non riuscita: ${error.message}`);
    }
  }

  return { hydrate, selectChat, newChat, refreshReviews, restoreSessions };
}
