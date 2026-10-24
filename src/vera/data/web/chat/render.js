import { routeLabel } from "/assets/routes.js";

const CLAIMS = {
  supported_fact: "Fatto documentato", system_inference: "Inferenza",
  unavailable: "Informazione non disponibile", simulated: "Dato simulato"
};
const STATUSES = { available: "Disponibile", unavailable: "Non disponibile", simulated: "Simulata" };

function text(parent, tag, value, className = "") {
  const element = document.createElement(tag);
  element.textContent = String(value ?? "");
  if (className) element.className = className;
  parent.append(element);
  return element;
}

function button(parent, label, callback, className = "action-button") {
  const element = text(parent, "button", label, className);
  element.type = "button";
  element.addEventListener("click", callback);
  return element;
}

function prose(parent, content) {
  const area = document.createElement("div");
  area.className = "prose";
  String(content || "").split(/\n\s*\n/).filter(Boolean).forEach(paragraph => {
    text(area, "p", paragraph);
  });
  parent.append(area);
}

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

function evidence(parent, record, all) {
  const cited = new Set((record.claims || record.draft?.claims || []).flatMap(claim => claim.evidence_ids));
  const sources = record.evidence.filter(source => all || cited.has(source.id));
  if (!sources.length) text(parent, "p", "Nessuna fonte citata.");
  for (const source of sources) {
    const item = document.createElement("article");
    item.className = "source-item";
    let url;
    try { url = new URL(source.url); } catch { /* Local sources have no URL. */ }
    if (url && ["https:", "http:"].includes(url.protocol)) {
      const link = text(item, "a", source.title);
      link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer";
    } else text(item, "strong", source.title);
    text(item, "small", `${source.source} · ${STATUSES[source.status] || source.status}`);
    if (source.metadata?.kg_record_key) {
      text(item, "small", "Fonte salvata nel Knowledge Graph; nessuna nuova chiamata implicita");
      if (source.metadata?.lookup_method) text(item, "small",
        `Ultimo recupero online: ${new Date(source.retrieved_at).toLocaleString("it-IT")}`);
    } else if (source.metadata?.lookup_method) {
      text(item, "small", `${source.status === "unavailable" ? "Ricerca senza fonte utilizzabile" : "Recuperata online"} · ${new Date(source.retrieved_at).toLocaleString("it-IT")}`);
      for (const request of source.metadata.http_requests || []) {
        text(item, "small", `HTTP GET ${request.url} · ${request.status_code ?? "errore di connessione"}`);
      }
    } else if (source.metadata?.snapshot) {
      text(item, "small", "Fonte locale / copia nel Knowledge Graph");
    }
    text(item, "blockquote", source.content);
    parent.append(item);
  }
}

function details(parent, record, review = false) {
  const panel = document.createElement("details");
  panel.className = "message-details";
  text(panel, "summary", review ? "Esamina affermazioni, fonti e motivazioni" : "Fonti e dettagli della risposta");
  const body = document.createElement("div"); body.className = "details-body";
  text(body, "h4", "Affermazioni");
  const claims = record.claims || record.draft?.claims || [];
  if (!claims.length) text(body, "p", "Nessuna affermazione.");
  for (const claim of claims) {
    text(body, "span", CLAIMS[claim.status] || claim.status, `claim-label ${claim.status}`);
    text(body, "p", claim.text);
    for (const citation of claim.citations) text(body, "blockquote", citation.supporting_quote);
  }
  text(body, "h4", review ? "Evidenze disponibili" : "Fonti citate");
  evidence(body, record, review);
  if (record.incident) {
    text(body, "h4", "Segnali rilevati");
    const list = document.createElement("ul");
    record.incident.alerts.forEach(alert => text(list, "li", `${alert.severity} · ${alert.title}: ${alert.description}`));
    body.append(list);
    text(body, "p", "Gli alert richiedono una verifica e non dimostrano una compromissione.");
  }
  if (record.reflection?.gaps?.length) {
    text(body, "h4", "Limiti delle evidenze");
    const list = document.createElement("ul");
    record.reflection.gaps.forEach(gap => text(list, "li", gap));
    body.append(list);
  }
  text(body, "h4", "Informazioni sulla risposta");
  text(body, "p", `Percorso: ${routeLabel(record.route)}`);
  if (record.metadata?.provider) {
    text(body, "p", `Modello: ${record.metadata.model || record.metadata.provider}`);
    const graph = record.metadata.knowledge_graph;
    if (graph) text(body, "p", `Fonti del Knowledge Graph citate: ${graph.cited_evidence_ids?.length || 0}`);
    if (record.metrics) text(body, "p", `Chiamate al modello: ${record.metrics.model_calls} · Chiamate ai tool/API: ${record.metrics.tool_calls}`);
    const learned = record.metadata.knowledge_learning?.validated_entity_ids || [];
    if (learned.length) text(body, "p", `Nuove conoscenze convalidate: ${learned.length} · ${learned.join(", ")}`);
  }
  if (typeof record.answer === "string") {
    const link = text(body, "a", "Apri report completo");
    link.href = `/v1/runs/${encodeURIComponent(record.run_id)}`;
    link.target = "_blank"; link.rel = "noopener";
  } else text(body, "p", `Versione ${record.version + 1} · Revisioni ${record.revision_count}/2 · Bozza non pubblicata`);
  for (const warning of record.warnings || []) text(body, "p", warning, "message-warning");
  panel.append(body); parent.append(panel);
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
