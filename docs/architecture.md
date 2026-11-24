# Architecture

VERA runs as a single stateful LangGraph workflow rather than a group of autonomous
agents. It normalizes events, detects signals, interprets the question and gathers
evidence before generating a draft. Validation and reflection then decide whether
the draft can be published or needs human review. The
[graph definition](../src/vera/workflow/graph.py) is the reference for this sequence.

## Domains

| Package under `src/vera/` | Responsibility |
| --- | --- |
| `domain` | Requests, evidence, claims, resource plans and reports |
| `workflow` | LangGraph nodes, acquisition, review and finalization |
| `routing`, `retrieval` | Resource selection, curated knowledge and hybrid ranking |
| `sources` | Bounded live CVE lookups and web research |
| `stream` | Event parsing, PCAP extraction, detection rules and statistics |
| `providers` | Deterministic, OpenAI-compatible, Ollama and Gemini adapters |
| `reasoning` | Citation checks, repair, reflection and review triggers |
| `memory` | SQLite history, memories and pending-review persistence |
| `knowledge_graph` | Kuzu import, traversal and run projection |
| `interfaces`, `data/web` | CLI, HTTP API and browser UI |

`ResourcePlan` selects CAG, RAG, tools and stream processing independently, then
derives the route from those choices. Identifiers supplied explicitly by the user
remain authoritative even if a model rewrites the question. Conversation history
helps resolve references, but it never becomes factual evidence.
The external model assesses the purpose of the message and whether it needs
subject-matter help, then VERA derives its intent from that structured assessment.
Explicit technical identifiers, supplied events, and definitions with a
matching local record still require an evidence path. Without a conversation model,
the deterministic provider selects facts from on-topic evidence without inferring
conversational intent.

Retrieval combines BM25 with embedding similarity, then considers provenance,
freshness and diversity. It uses hash embeddings by default, with Sentence
Transformers available as an option. A high ranking is a selection signal, not
an independent check that the source or answer is correct.

## Evidence and limits

| Claim status | Meaning |
| --- | --- |
| `supported_fact` | Quoted available evidence from a source other than memory |
| `system_inference` | A conclusion that is not established as an authoritative fact |
| `simulated` | A finding tied to explicitly simulated evidence |
| `unavailable` | Missing evidence or an unavailable lookup |

For each claim, validation checks evidence IDs, exact quotations, term coverage,
identifiers, numbers and negation. A `supported_fact` must reproduce its supporting
quotation exactly, and every cited knowledge record must concern a subject of the
question. A relevant document elsewhere in the context does not justify an unrelated
citation. An explicitly named relationship can supplement the subject's own record,
but cannot replace it; identifiers produced by stream detectors are also subjects.

External providers can return up to six claims. When validation fails, VERA keeps
the error through automatic retries and repairs and sends the draft for review.
Repairing an off-topic claim replaces the assertion with a statement of what the
evidence does not establish, rather than disguising the original assertion as a fact.

These checks are lexical, not a complete semantic verifier. For that reason,
non-extractive cybersecurity summaries from an external provider require human review
even when their citations pass. Only prose made entirely from validated factual claim
text counts as extractive. This deliberately increases the review workload. Provider
fallbacks also require review and do not count as successful model answers.

Reports identify these rules as `vera-evidence-v2`. Scores collected under earlier
runtime behavior do not establish acceptance of this contract.

Live clients support exact lookups through CVE.org, NVD, CISA KEV, FIRST EPSS and OSV.
The local corpus contains selected ATT&CK, CWE, CAPEC, OWASP, NIST and FIRST material.
Bundled records are snapshots, not current intelligence. To refresh the ATT&CK and
KEV feeds, run `vera corpus-sync` explicitly, then rebuild Kuzu.

CVSS is severity, EPSS is exploitation probability, and KEV records known exploitation.
None proves compromise or asset-specific risk. Asset inventory and affected-version
matching are not implemented.

Stream rules detect distinct-port scans, repeated HTTP 401/403 responses, SYN bursts,
and selected traversal, command-injection and JNDI markers. Windows and thresholds
are defined in [Settings](../src/vera/config.py). These are teaching rules, not a
production intrusion-detection system. PCAP processing requires `tshark` and sends
normalized fields rather than raw packets to the model.

## Budgets and persistence

`Settings` bounds model calls, tool calls, timeouts and input sizes. Optional ReAct
lets an external model choose local corpus searches or exact CVE lookups, but never
arbitrary URLs or commands. It is disabled by default. Its audit trace records the
action, a short operational reason, the outcome and new evidence IDs; it does not
expose private chain-of-thought. The initial workflow allows four model calls by
default, while ReAct resolves its budget separately.

User-facing prose follows `VERA_RESPONSE_LANGUAGE`, which defaults to English,
regardless of the query language. Evidence quotations keep their source language.

SQLite stores completed runs, memories, review decisions and LangGraph checkpoints.
Completed evidence and reflections live in `runs.result_json`. Older databases may
still have separate `evidence` and `reflections` tables; VERA preserves their rows but
no longer updates them. Use the runs API to read current reports.
Pending drafts survive restarts but remain unpublished until approved. Human
revisions have a separate limit, described in the [review guide](chat.md#human-review).
Use one API worker per database and close Python orchestrators with a context manager.

Kuzu is optional and separate from LangGraph. Traversal supplies evidence candidates;
graph associations do not bypass citation checks. Failed run projection is queued in
SQLite for retry. See [graph operations](knowledge-graph.md).

`/v1/graph` exposes workflow topology; `/knowledge-graph` exposes domain data.
The default SQLite design targets local use, not concurrent SOC-scale ingestion.
