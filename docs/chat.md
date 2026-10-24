# Chat

Start `vera serve` and open **http://127.0.0.1:8000/chat**. The root `/` and old `/graph`
bookmarks redirect to the chat. The workflow map is no longer a page in the application.

## Conversations

Use **Nuova chat** for a separate conversation. Write in **Messaggio a VERA** and send with
Enter or the arrow button; Shift+Enter inserts a newline. Sending clears the composer.
The sidebar restores conversations on this browser. Completed reports stay in SQLite;
the browser stores messages, report references, and draft feedback. Clearing browser storage
does not delete server reports. An unavailable browser store leaves the current chat usable
and displays a notice that history cannot be retained.

Each conversation has its own `session_id`. The API additionally accepts an optional
`conversation` list of up to six messages, with `role` equal to `user` or `assistant` and
`content` up to 2,000 characters per message, 6,000 characters total. The chat sends the last
six user messages and completed response summaries with their claims, clipped to 1,000 characters each.
Pending drafts are excluded as assistant context. History can resolve references but cannot
support factual claims; retrieval still needs relevant current evidence. The router receives
the latest question, so an old CVE or ATT&CK term does not silently change the next route.

## Answers and sources

A `200` response becomes an assistant message. Expand **Fonti e dettagli della risposta**
for grounded claims, quotations, source records, evidence gaps, model, route, and a link to
the full report. A deterministic fallback is explicitly labeled. The UI waits for the full
analysis response; it does not simulate streamed model output.

## Human review inside the chat

A `202` response is displayed as an unpublished draft with **Serve una tua conferma**.
Read the reasons and expand **Esamina affermazioni, fonti e motivazioni** before deciding.

- **Approva e salva** publishes the report in place of the draft.
- **Chiedi una modifica** opens a feedback field. The revised draft appears as a new assistant
  message and still needs a decision; previous draft summaries remain in the conversation.
- **Rifiuta** requires a reason and closes the draft without publishing it.

While a draft is pending, decide on its card before continuing that conversation. A new
chat remains available. Existing server reviews are imported into the sidebar; use its
refresh button to retrieve reviews created elsewhere. Revision limits and availability
come from the server. Interrupted decisions retain their UUID and exact payload for retry;
version conflicts refresh the record. No draft is automatically approved.

## Routes and evidence

| Displayed route | API identifier | Context |
| --- | --- | --- |
| CAG | `CAG_ONLY` | Curated knowledge and memory |
| CAG + RAG | `CAG_RAG` | CAG, local corpus, optional Kuzu retrieval |
| CAG + RAG + API | `CAG_RAG_TOOL` | CAG, RAG, CVE APIs or bounded online research when enabled |
| CAG + Stream | `STREAM` | Curated knowledge and supplied event statistics |
| CAG + RAG + Stream | `FULL` | Events, CAG, retrieval, and CVE APIs when needed and enabled |

`/chat` accepts text questions. Structured events remain available through `/v1/analyze`;
PCAP extraction uses the CLI and `tshark`. Text describing traffic does not run detectors.
`/knowledge-graph` remains the independent domain-data viewer; `/v1/graph` remains available
for workflow diagnostics. An alert or graph connection is not proof of compromise.

## Online research

With `VERA_LIVE_SOURCES=true` and `VERA_WEB_SEARCH_ENABLED=true` (the default), definitions
without a record about the actual subject escalate from local retrieval to online research.
A mention inside another entity's relationship is insufficient. For example, a Cobalt Strike
record mentioning PowerSploit does not define PowerSploit. `Cerca su internet PowerSploit`
forces a fresh lookup; a standalone `Cerca su internet` uses the last substantive user question.
The same instruction in review feedback reacquires sources before revising the draft.

The built-in, keyless lookup searches the **live MITRE ATT&CK software, enterprise-technique,
and group catalogs for exact names/aliases or IDs**. It is not an unrestricted search engine.
For general search, configure `VERA_WEB_SEARCH_API_KEY` with a Brave Search API key.
Search results locate pages on a fixed list of primary-source hosts; VERA downloads at most
two such pages and cites their text, never a search snippet. The built-in catalogs are tried
first. A missing exact match, missing key, network failure, disabled access, or exhausted tool
budget is reported as unavailable. A typo such as `powersplot` is not silently corrected.

Research performs only bounded HTTPS GET requests, with per-request timeouts, a 2 MiB page
limit, no redirects, and the run's shared tool-call budget. It does not execute downloaded
code, install tools, or collect traffic. General search sends the resolved research query to
Brave; conversation history and supplied traffic events are not included in the search payload.

Expand the source details to inspect `lookup_method`, `provenance: live_api`, retrieval time,
and actual HTTP URLs/statuses. The route indicates selected resources; check `metrics.tool_calls`
to establish whether a call actually happened. Subsequent questions may use a source saved in
Kuzu; explicit online requests refresh it. `CAG + RAG + API` does not by itself prove a live call.
Approving an unsupported draft saves it; approval does not verify its statements.
