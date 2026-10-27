# Chat and API

Start VERA as described in the [README](../README.md), then open `/chat`.
The root `/` and legacy `/graph` URL redirect there. `/docs` is the generated API
reference; `/v1/graph` remains available for workflow diagnostics.

## Conversations

Each chat has a `session_id`. The browser retains messages and report references;
SQLite retains completed reports and pending reviews. Clearing browser storage does
not delete server history. The refresh button retrieves server-side reviews.

The API accepts up to six `conversation` messages: `user` or `assistant`, at most
2,000 characters each and 6,000 total. The UI clips each context message to 1,000
characters and excludes unpublished, rejected and superseded drafts.
History can resolve follow-ups but cannot support factual claims.

```bash
curl -fsS http://127.0.0.1:8000/v1/analyze \
  -H 'Content-Type: application/json' \
  -d '{"query":"Explain PowerShell.","session_id":"example","origin":"chat"}'
```

For `POST /v1/analyze`, HTTP `200` is a published report; `202` is an unpublished
`ReviewRecord`. Expand response details to inspect claims, quotations, source
availability, warnings, route and model. A selected route or `/health` response
does not prove that inference or a live lookup succeeded.

| Route | Selected resources |
| --- | --- |
| `CAG_ONLY` | Curated knowledge |
| `CAG_RAG` | Curated knowledge, corpus and optional graph retrieval |
| `CAG_RAG_TOOL` | Retrieval plus CVE APIs or bounded web research |
| `STREAM` | Curated knowledge and supplied event statistics |
| `FULL` | Stream processing combined with retrieval and optional lookups |

The chat accepts text. Supply structured `events` through the API, or use CLI
`--events` / `--pcap`; describing traffic in prose does not invoke detectors.

## Human review

High/critical alerts, failed citation validation, unsupported claims and missing
required evidence can hold a report. Drafts remain outside completed history,
memory and graph projection until approved.

The review card offers **Approva e salva**, **Chiedi una modifica** and **Rifiuta**.
Rejection and revision require feedback. Revision needs an external model, reacquires
evidence and pauses for another decision; at most two revisions are allowed.
Approval publishes a draft, but does not independently verify its statements.

```bash
uv run --extra knowledge-graph vera reviews
uv run --extra knowledge-graph vera review <run_id> --interactive
```

CLI `analyze --json` leaves a held draft pending and exits with code `2`.
Non-interactive review also supports `--approve`, `--reject "reason"`,
`--revise "feedback"` and `--retry` for an interrupted decision.

API clients use `GET /v1/reviews`, `GET /v1/reviews/<run_id>` and
`POST /v1/reviews/<run_id>/decisions`. Supply `action`, the current `version`, a new
UUID `decision_id`, and feedback when required. Retry an interrupted action with
the same UUID and payload; stale or competing decisions return `409`.
A missing checkpoint returns `503` rather than silently publishing a report.
Completed reports are available at `/v1/runs/<run_id>`.

Review-enabled serving is loopback-only. Do not expose it through a proxy or port
forward: these are local decisions, not authenticated analyst identities.

## Online research

Set `VERA_LIVE_SOURCES=true` and `VERA_WEB_SEARCH_ENABLED=true` to allow research.
An optional `VERA_WEB_SEARCH_API_KEY` enables [Brave Search](https://brave.com/search/api/).
Keyless discovery uses DuckDuckGo and exact MITRE ATT&CK catalog lookups.
Restart VERA after changing `.env`.

Explicit online requests, current-information questions and missing local subject
coverage can trigger research. Providers receive the resolved research query, not
raw packets or the full conversation.

Search results locate allowlisted HTTPS pages; snippets and Instant Answer abstracts
are not evidence. VERA retrieves at most two pages, limits responses to 2 MiB, does not
follow redirects and shares the run's request budget. General pages require relevance
assessment. Failures and missing records remain unavailable.

Inspect `lookup_method`, `provenance`, retrieval time, HTTP requests and
`metrics.tool_calls`. Cached graph records are not fresh lookups.
