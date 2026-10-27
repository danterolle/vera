# Architecture

VERA is one stateful LangGraph workflow, not a swarm of autonomous agents.
The [graph definition](../src/vera/workflow/graph.py) is the source of truth:
normalize events and detect signals, interpret the question, acquire evidence,
generate, validate, reflect, then publish or wait for human review.

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

`ResourcePlan` selects CAG, RAG, tools and stream processing independently; its route
is derived from those flags. Original explicit identifiers survive model rewriting.
Conversation history can resolve references but is not factual evidence.

Retrieval combines BM25 and embedding similarity, followed by provenance, freshness
and diversity heuristics. Hash embeddings are the default; Sentence Transformers
are optional. Ranking is not an independent accuracy check.

## Evidence and limits

| Claim status | Meaning |
| --- | --- |
| `supported_fact` | Quoted available evidence from a source other than memory |
| `system_inference` | A conclusion that is not established as an authoritative fact |
| `simulated` | A finding tied to explicitly simulated evidence |
| `unavailable` | Missing evidence or an unavailable lookup |

Validation checks evidence IDs, quotations, term coverage, identifiers, numbers and
negation. The external-provider analysis schema allows up to six claims.
Failed claims retain their errors and require review; unrelated quotations must not
be substituted to make a draft appear grounded.

Grounding is lexical, not complete semantic verification. It does not validate every
statement in the prose summary. Model quality and source relevance still need review.

Exact live clients cover CVE.org, NVD, CISA KEV, FIRST EPSS and OSV. Local sources
include focused ATT&CK, CWE, CAPEC, OWASP, NIST and FIRST material. Bundled records
are snapshots, not current intelligence. Explicit `vera corpus-sync` refreshes
ATT&CK and KEV feeds; rebuild Kuzu afterwards.

CVSS is severity, EPSS is exploitation probability, and KEV records known exploitation.
None proves compromise or asset-specific risk. Asset inventory and affected-version
matching are not implemented.

Stream rules detect distinct-port scans, repeated HTTP 401/403 responses, SYN bursts,
and selected traversal, command-injection and JNDI markers. Windows and thresholds
are defined in [Settings](../src/vera/config.py). These are teaching rules, not a
production intrusion-detection system. PCAP processing requires `tshark` and sends
normalized fields rather than raw packets to the model.

## Budgets and persistence

Model/tool calls, timeouts and input sizes are bounded by `Settings`. Optional ReAct
can choose local corpus searches and exact CVE lookups, not arbitrary URLs or commands.
The initial model-call budget defaults to four; ReAct resolves its budget separately.

SQLite stores completed runs, memories, review decisions and LangGraph checkpoints.
Pending drafts are durable but unpublished until approved. Human revisions are
bounded separately; see [review operations](chat.md#human-review).
Use one API worker per database and close Python orchestrators with a context manager.

Kuzu is optional and separate from LangGraph. Traversal supplies evidence candidates;
graph associations do not bypass citation checks. Failed run projection is queued in
SQLite for retry. See [graph operations](knowledge-graph.md).

`/v1/graph` exposes workflow topology; `/knowledge-graph` exposes domain data.
The default SQLite design targets local use, not concurrent SOC-scale ingestion.
