# Chat and API

After starting VERA with the [README](../README.md) instructions, open `/chat`.
Both `/` and the older `/graph` address redirect there. The generated API reference
is at `/docs`, while `/v1/graph` exposes the workflow for diagnostics.

## Conversations

Each conversation has a `session_id`. The browser keeps messages and report references,
while SQLite stores completed reports and pending reviews. Clearing browser storage
therefore leaves server history intact. Use the refresh button to retrieve reviews
that are still held on the server.

The API accepts up to six `user` or `assistant` messages in `conversation`, with a
limit of 2,000 characters per message and 6,000 overall. The UI clips each context
message to 1,000 characters and leaves out unpublished, rejected or superseded drafts.
This history helps VERA understand follow-ups, but cannot support factual claims.

```bash
curl -fsS http://127.0.0.1:8000/v1/analyze \
  -H 'Content-Type: application/json' \
  -d '{"query":"Explain PowerShell.","session_id":"example","origin":"chat"}'
```

`POST /v1/analyze` returns HTTP `200` for a published report and `202` for an
unpublished `ReviewRecord`. Expand the response details to see claims, quotations,
source availability, warnings, route and model. Neither the selected route nor a
successful `/health` response proves that inference or a live lookup succeeded.

| Route | Selected resources |
| --- | --- |
| `CAG_ONLY` | Curated knowledge |
| `CAG_RAG` | Curated knowledge, corpus and optional graph retrieval |
| `CAG_RAG_TOOL` | Retrieval plus CVE APIs or bounded web research |
| `STREAM` | Curated knowledge and supplied event statistics |
| `FULL` | Stream processing combined with retrieval and optional lookups |

The chat accepts text rather than event files. To run the detectors, supply structured
`events` through the API or use the CLI's `--events` or `--pcap` option. Describing
traffic in prose does not invoke them.

## Human review

A draft can be held because of high or critical alerts, failed citations, unsupported
claims, provider fallback or missing required evidence. Automatic retries and repairs
do not erase citation failures. Model-written cybersecurity summaries also need review
unless they are entirely extractive: checking citations cannot establish whether the
remaining prose is correct or useful.

This is a deliberately conservative boundary, not a claim of semantic verification.
Until approved, a draft stays outside completed history, memory and graph projection.

The review card offers **Approva e salva**, **Chiedi una modifica** and **Rifiuta**.
Give feedback when rejecting or requesting a revision. A revision requires an external
model, gathers evidence again and pauses for another decision; a draft can be revised
at most twice. Approval publishes it, but is not an independent verification of its
statements.

```bash
uv run --extra knowledge-graph vera reviews
uv run --extra knowledge-graph vera review <run_id> --interactive
```

CLI `analyze --json` leaves a held draft pending and exits with code `2`.
Non-interactive review also supports `--approve`, `--reject "reason"`,
`--revise "feedback"` and `--retry` for an interrupted decision.

API clients can list or read drafts with `GET /v1/reviews` and
`GET /v1/reviews/<run_id>`, then submit a decision to
`POST /v1/reviews/<run_id>/decisions`. Include `action`, the current `version`, a new
UUID `decision_id` and any required feedback. If an action is interrupted, retry
with the same UUID and payload. Stale or competing decisions return `409`; a missing
checkpoint returns `503` rather than publishing silently. Published reports are
available at `/v1/runs/<run_id>`.

The provider, model and validation contract are recorded with the draft. A checkpoint
that lacks provenance or uses an older validation contract cannot be approved. Reject
it, request a revision if available, or run the analysis again. A legacy approval
interrupted before publication cannot be retried; an already published result remains
available in history.

Review-enabled serving is loopback-only. Do not expose it through a proxy or port
forward: these are local decisions, not authenticated analyst identities.

For model acceptance, `scripts/review-pack.py` generates fresh runtime answers and
renders the full summaries, claims, quotations and evidence without clipping them.
Each CSV verdict needs a reviewer and date; sign-off is bound to the immutable case
hash. Fallbacks and mismatched validation-contract versions block readiness for
authorization, even if a person accepts their content. At least 40 accepted cases
from one identified model are necessary, not sufficient; the pack never authorizes
production. Use a new output directory after runtime or model changes.

## Online research

To allow online research, set `VERA_LIVE_SOURCES=true` and
`VERA_WEB_SEARCH_ENABLED=true`, then restart VERA. An optional
`VERA_WEB_SEARCH_API_KEY` enables [Brave Search](https://brave.com/search/api/);
without a key, discovery uses DuckDuckGo and exact MITRE ATT&CK catalog lookups.

Explicit online requests, current-information questions and missing local subject
coverage can trigger research. Providers receive the resolved research query, not
raw packets or the full conversation.

Search results are used to locate allowlisted HTTPS pages, not as evidence themselves:
snippets and Instant Answer abstracts cannot support a claim. VERA retrieves at most
two pages, limits responses to 2 MiB and follows no redirects. These requests share
the run's budget, and general pages still need a relevance assessment. Failed lookups
and missing records remain unavailable.

Inspect `lookup_method`, `provenance`, retrieval time, HTTP requests and
`metrics.tool_calls`. Cached graph records are not fresh lookups.
