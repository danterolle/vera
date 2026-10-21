# Conditional human review

VERA does not pause every analysis. After validation and reflection, high/critical detection
alerts, unsupported or ungrounded claims, missing usable evidence (including a CVE with no
available record for that identifier), and out-of-scope decisions that conflict with a
cybersecurity request require human review. Supported offline CVE snapshots are not held
merely because live APIs are disabled; genuinely unrelated questions also finish normally.
Review triggers are deterministic checks, not a second model's opinion.

`POST /v1/analyze` still returns `200` and an `AnalysisResult` for ordinary analyses. A held
analysis returns `202` and a `ReviewRecord` containing `status: "pending"`, `run_id`,
`version`, reasons, the **unpublished** draft, evidence, incident context, reflection,
warnings, and revision history. The draft does not appear in `/v1/runs`, run history,
semantic memory, or knowledge-graph projection. The server does not retain an open request,
model call, or worker while the reviewer decides. `/graph` lists pending reviews separately
from recorded executions and shows the evidence and available actions.

## Decide locally

Run `vera serve` on a loopback address and open `/graph`. Examine the draft and its cited
quotes, evidence availability, alerts, and gaps. Approve to persist the report; reject
with a reason to close the review without a saved run; or request revision with specific
feedback. A revision invokes the configured external model once, then validates, reflects,
and **pauses again**, even if the new draft is well supported. At most two revision cycles
are allowed per run. The deterministic provider does not use feedback and rejects automatic
revision explicitly; approval and rejection remain available. A failed revision keeps the
previous draft pending and exposes the model error instead of silently substituting output.

The same operations are available through the local API. `GET /v1/reviews` returns every
open review, including ones needing an action retry:

```bash
curl -fsS http://127.0.0.1:8000/v1/reviews
curl -fsS http://127.0.0.1:8000/v1/reviews/<run_id>
curl -i http://127.0.0.1:8000/v1/reviews/<run_id>/decisions \
  -H 'Content-Type: application/json' \
  -d '{"action":"approve","version":0,"decision_id":"941612b5-7c77-4c32-a1ed-cdbe196de969"}'
```

For `reject` or `revise`, include nonblank `"feedback"` (up to 4,000 characters). Supply
a new UUID `decision_id` for each new action and the current review `version`. Repeating
an identical decision ID and payload returns its stored result; a stale version or competing
action returns `409`. Invalid input returns `422`, inaccessible reviews `404`, and a missing
or damaged checkpoint `503`. A successful revision returns `202` with a new version; an
approval returns `200` with the saved `AnalysisResult`, and rejection returns `200` with
`status: "rejected"`. Refresh `/v1/reviews/<run_id>` to inspect the latest state.

Review decisions are local-only, not authenticated user identities: VERA refuses a
non-loopback `vera serve` bind and rejects non-loopback clients/hosts or mismatched browser
Origin. Do not expose the server through a proxy or port forward.

The CLI provides the same local review gate without a running server. `vera analyze` offers
an inline approve/reject/revise prompt when standard input is a terminal; `--no-interactive`
or `--json` leaves the draft pending and exits with code `2`. Inspect or decide later:

```bash
vera reviews
vera review <run_id> --json
vera review <run_id> --interactive
vera review <run_id> --approve
vera review <run_id> --reject "Not reliable"
vera review <run_id> --revise "Use the cited evidence"
vera review <run_id> --retry
```

Decisions operate directly on the local SQLite database. A revision still requires an
external model provider; the deterministic provider permits approval and rejection only.
`--retry` repeats an interrupted decision after an error. The CLI never presents a pending
draft as a saved report.

## Persistence and recovery

LangGraph persists the state in the same SQLite database as the review ledger and finished
reports, using the run ID as its thread ID. A conditional `interrupt()` waits after
reflection and before finalization; `Command(resume=...)` continues the saved graph. The
ledger records a versioned, compare-and-set decision and idempotency key. If a process
stops between checkpoint and ledger writes, the next server startup reconciles interrupted
checkpoints, saved reports, and accepted decisions. An interrupted decision is shown as an
error with its original action and decision ID for explicit retry; missing checkpoints fail
closed. Completed/rejected checkpoint threads are pruned, while their decision records
remain queryable. Use one VERA server process per database.

Startup retains unregistered, nonterminal checkpoints because another instance may still
be writing them. It prunes only terminal saved runs; interrupted drafts are reindexed.

Measured analysis latency excludes human wait and survives a restart. Existing autonomous
model-call limits apply to the initial analysis; a human-requested revision permits one
additional generation call per cycle (two total), counted in the final metrics. The
offline synthetic evaluation disables review internally to measure its original routing
and grounding benchmarks; live API/CLI analyses cannot bypass the review gate.
