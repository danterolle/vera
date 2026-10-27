import { details } from "/assets/chat-details.js";
import { button, prose, text } from "/assets/chat-elements.js";

export function reviewReason(reason) {
  return reason
    .replace(/(\d+) high or critical detection alert\(s\) require review\./,
      "$1 alert di gravità alta o critica richiedono una verifica.")
    .replace(/(\d+) claim\(s\) lack verified support\./,
      "$1 affermazioni non hanno un supporto verificato.")
    .replace("The draft contains no findings to assess.", "Mancano risultati valutabili.")
    .replace("No usable non-memory evidence supports the analysis.", "Non sono disponibili evidenze utilizzabili a supporto.")
    .replace(/No available evidence concerns (.+)\./, "Non sono disponibili evidenze relative a $1.")
    .replace("The draft has no supported or observed findings.", "La bozza contiene solo inferenze o informazioni indisponibili.")
    .replace("A cybersecurity request was classified as out of scope.", "Una domanda di cybersecurity è stata classificata fuori ambito.")
    .replace("A revised draft requires a human decision.", "La bozza aggiornata attende la tua decisione.");
}

function reviewCard(parent, message, record, callbacks, busy) {
  const card = document.createElement("section"); card.className = "review-card";
  const pending = record.status === "pending";
  text(card, "h3", pending ? "Serve una tua conferma" : record.status === "rejected"
    ? "Bozza rifiutata" : "La richiesta richiede attenzione");
  text(card, "p", pending
    ? "Questa risposta è una bozza. Puoi chiedere nuove fonti o una correzione. Approvare la salva, ma non verifica le affermazioni prive di fonti."
    : record.status === "rejected" ? "La bozza non è stata pubblicata."
      : "La decisione non è ancora conclusa. Puoi aggiornare lo stato della richiesta.");
  if (record.reasons?.length) {
    const list = document.createElement("ul");
    record.reasons.forEach(reason => text(list, "li", reviewReason(reason)));
    card.append(list);
  }
  if (record.error) text(card, "p", record.error, "message-error");
  if (message.error) text(card, "p", message.error, "message-error");
  const retry = message.pendingDecision || (record.status === "error" && record.retry_decision);
  const actions = document.createElement("div"); actions.className = "review-actions";
  if (busy === message.id) text(actions, "span", "Sto elaborando la decisione…", "archived-label");
  else if (retry) {
    button(actions, "Riprova la stessa decisione", () => callbacks.decide(message, "retry"), "action-button primary");
    button(actions, "Aggiorna stato", () => callbacks.refresh(message));
  } else if (pending) {
    button(actions, "Approva e salva", () => callbacks.decide(message, "approve"), "action-button primary");
    if (record.can_revise) button(actions, "Chiedi una modifica", () => callbacks.intent(message, "revise"));
    button(actions, "Rifiuta", () => callbacks.intent(message, "reject"));
  } else if (record.status !== "rejected") button(actions, "Aggiorna stato", () => callbacks.refresh(message));
  actions.querySelectorAll("button").forEach(element => { element.disabled = Boolean(busy); });
  card.append(actions);
  if (pending && message.feedbackAction && !retry && busy !== message.id) {
    const form = document.createElement("form"); form.className = "feedback-form";
    const id = `feedback-${message.id}`;
    const label = text(form, "label", message.feedbackAction === "revise"
      ? "Che cosa vuoi modificare?" : "Perché vuoi rifiutare questa bozza?");
    label.htmlFor = id;
    const input = document.createElement("textarea"); input.id = id;
    input.maxLength = 4000; input.required = true; input.value = message.feedback || "";
    input.placeholder = message.feedbackAction === "revise"
      ? "Per esempio: cerca su internet fonti sul soggetto richiesto e correggi la risposta." : "Scrivi una breve motivazione…";
    input.addEventListener("input", () => callbacks.feedback(message, input.value));
    form.append(input);
    const buttons = document.createElement("div"); buttons.className = "feedback-buttons";
    const submit = text(buttons, "button", message.feedbackAction === "revise" ? "Invia indicazioni" : "Rifiuta bozza", "action-button primary");
    submit.type = "submit"; submit.disabled = Boolean(busy);
    button(buttons, "Annulla", () => callbacks.intent(message, null));
    form.append(buttons);
    form.addEventListener("submit", event => {
      event.preventDefault();
      callbacks.decide(message, message.feedbackAction);
    });
    card.append(form);
  }
  parent.append(card);
}

export function renderMessages(container, chat, records, callbacks, busy) {
  container.replaceChildren();
  for (const message of chat.entries) {
    const article = document.createElement("article");
    article.className = `message ${message.role}`; article.dataset.entryId = message.id;
    if (message.role === "user") {
      text(article, "div", message.content, "user-content");
    } else {
      const heading = document.createElement("div"); heading.className = "assistant-heading";
      text(heading, "span", "V", "assistant-avatar"); text(heading, "span", "VERA"); article.append(heading);
      const body = document.createElement("div"); body.className = "assistant-content";
      const record = records.get(message.id);
      if (message.kind === "loading") {
        const thinking = document.createElement("div"); thinking.className = "thinking"; thinking.role = "status";
        for (let index = 0; index < 3; index++) thinking.append(document.createElement("span"));
        text(thinking, "em", "Sto analizzando le evidenze…"); body.append(thinking);
      } else if (message.kind === "error") {
        text(body, "p", message.error || "Non riesco a completare la richiesta.", "message-error");
        const retry = button(body, "Riprova", () => callbacks.retry(message)); retry.disabled = Boolean(busy);
      } else {
        prose(body, message.content);
        if (message.live === false) text(body, "p", "Bozza precedente · sostituita dalla revisione successiva", "archived-label");
        else if (record) {
          if (message.kind === "review") {
            details(body, record, true);
            reviewCard(body, message, record, callbacks, busy);
          } else {
            if (record.metadata.provider_fallback) text(body, "p",
              "Il modello non ha risposto: questa è una risposta di riserva generata dal sistema.", "message-warning");
            if (!record.metadata.intent || record.metadata.intent === "cybersecurity") details(body, record);
            const meta = document.createElement("div"); meta.className = "message-meta";
            text(meta, "span", record.metadata.provider_fallback ? "Risposta di riserva" : record.metadata.model || "VERA");
            button(meta, "Copia risposta", () => callbacks.copy(message), "text-button"); body.append(meta);
          }
        } else if (message.runId) {
          text(body, "p", message.error || "Recupero la risposta salvata…", "archived-label");
          if (message.error) button(body, "Ricarica", () => callbacks.refresh(message));
        }
      }
      article.append(body);
    }
    container.append(article);
  }
}
