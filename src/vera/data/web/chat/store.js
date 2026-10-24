const KEY = "vera.chat.v1";

export function conversation() {
  return { id: crypto.randomUUID(), title: "Nuova chat", entries: [], updated: Date.now() };
}

export function entry(role, content = "") {
  return { id: crypto.randomUUID(), role, content, created: Date.now(), updatedAt: Date.now(),
    kind: role === "user" ? "question" : "loading" };
}

export function readState() {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY));
    if (saved?.version === 1 && Array.isArray(saved.conversations)) {
      const conversations = saved.conversations.filter(item => typeof item.id === "string" &&
        typeof item.title === "string" && Array.isArray(item.entries));
      for (const chat of conversations) {
        chat.entries = chat.entries.filter(item => typeof item.id === "string" &&
          ["user", "assistant"].includes(item.role));
        for (const message of chat.entries) {
          if (message.kind === "loading") {
            message.kind = "error";
            message.error = "La pagina è stata chiusa durante la richiesta. Puoi riprovare; le bozze già ricevute dal server sono recuperate nella cronologia.";
          }
        }
      }
      if (conversations.length) return {
        version: 1, conversations,
        active: conversations.some(chat => chat.id === saved.active) ? saved.active : conversations[0].id
      };
    }
  } catch { /* Private browsing or unavailable storage must not prevent chatting. */ }
  const chat = conversation();
  return { version: 1, active: chat.id, conversations: [chat] };
}

export function saveState(state) {
  try {
    const stored = JSON.parse(localStorage.getItem(KEY));
    if (stored?.version === 1 && Array.isArray(stored.conversations)) {
      const merged = new Map(stored.conversations.map(chat => [chat.id, chat]));
      for (const chat of state.conversations) {
        const previous = merged.get(chat.id);
        if (!previous) { merged.set(chat.id, chat); continue; }
        const messages = new Map(previous.entries.map(message => [message.id, message]));
        for (const message of chat.entries) {
          const old = messages.get(message.id);
          if (!old || (message.updatedAt || 0) >= (old.updatedAt || 0)) messages.set(message.id, message);
        }
        const entries = [...messages.values()];
        entries.sort((a, b) => (a.created || 0) - (b.created || 0));
        Object.assign(chat, (previous.updated > chat.updated ? previous : {}), { entries,
          external: chat.external || previous.external });
        merged.set(chat.id, chat);
      }
      state.conversations = [...merged.values()];
    }
    localStorage.setItem(KEY, JSON.stringify(state));
    return true;
  } catch {
    return false;
  }
}

export function summary(report) {
  const answer = report.answer || "";
  const assessment = answer.startsWith("## Assessment\n")
    ? answer.slice("## Assessment\n".length) : answer;
  return assessment.split(/\n\n## (?:Incident|Findings|Sources)\b/)[0].trim();
}

export function remember(message, record) {
  message.runId = record.run_id;
  message.kind = typeof record.answer === "string" ? "result" : "review";
  message.content = message.kind === "result" ? summary(record) : record.draft.summary;
  message.context = message.kind === "result"
    ? [message.content, ...record.claims.map(claim => claim.text)].join("\n").slice(0, 2000) : null;
  message.version = record.version;
  message.reviewStatus = record.status;
  message.error = null;
  message.live = true;
  message.updatedAt = Date.now();
  message.sessionId = record.session_id || record.metadata?.session_id;
}

export function history(chat, beforeId) {
  const messages = [];
  for (const message of chat.entries) {
    if (message.id === beforeId) break;
    if (message.role === "user" || message.kind === "result" || message.kind === "review" && message.live !== false) {
      const content = String(message.context || message.content || "").trim().slice(0, 1000);
      if (content) messages.push({ role: message.role, content });
    }
  }
  return messages.slice(-6);
}
