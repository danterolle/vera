# Architecture

VERA is one stateful LangGraph workflow with specialized deterministic layers. It is not a
collection of autonomous agents.

```mermaid
flowchart LR
    I[Validated input] --> N[Normalize and detect]
    N --> R[Hybrid router]
    R --> C[CAG]
    R --> G[CAG and RAG]
    R --> T[CAG, RAG, tools]
    R --> S[Stream]
    R --> F[Full pipeline]
    C --> A[Generate]
    G --> A
    T --> A
    S --> A
    F --> A
    A --> V[Validate claims]
    V -->|one bounded retry| A
    V --> X[Reflect]
    X --> P[Persist and return]
```

## Domain boundaries

- `domain`: validated request, evidence, claim, incident, and result contracts.
- `routing`: deterministic intent rules and optional LLM ambiguity resolution.
- `retrieval`: curated knowledge, hybrid retrieval, feed normalization, and sync storage.
- `sources`: read-only exact CVE clients with explicit unavailable results.
- `stream`: normalized event parsing, restricted PCAP extraction, rules, and statistics.
- `providers`: deterministic, OpenAI-compatible, Ollama, Unsloth, and Gemini generation.
- `reasoning`: citation validation, bounded repair, and structured reflection.
- `memory`: SQLite execution history plus semantic and episodic memories.
- `workflow`: LangGraph state transitions and dependency wiring.
- `interfaces`: Typer CLI and FastAPI HTTP API.

## Project layout

```text
src/vera/
├── domain/          Typed requests, evidence, reports, and graph contracts
├── workflow/        LangGraph topology, nodes, acquisition, and orchestration
├── retrieval/       Hybrid ranking, embeddings, corpus store, and feed sync
├── sources/         Read-only CVE.org, NVD, KEV, EPSS, and OSV adapters
├── stream/          Event parsing, PCAP extraction, detection, and statistics
├── providers/       Deterministic and external language-model providers
├── reasoning/       Claim validation and reflection
├── memory/          SQLite persistence and semantic or episodic recall
├── interfaces/      FastAPI and Typer entry points
└── data/
    ├── knowledge/   Stable CAG documents
    ├── corpus/      Bundled RAG documents
    ├── evaluation/  Controlled benchmark scenarios
    ├── samples/     Safe synthetic event streams
    └── web/graph/   Workflow explorer HTML, styles, and scripts

tests/
├── unit/            Isolated domain behavior
├── integration/     Workflow, API, UI, persistence, and evaluation
└── architecture/    Repository-wide structural constraints
```

## Routing contract

Events are normalized before routing. The meta-controller produces a typed `ResourcePlan`
containing independent CAG, RAG, tool, and stream flags plus extracted CVE and ATT&CK IDs.
`Route` remains a derived label for compatibility. Mixed requests can activate stream,
retrieval, and exact APIs together. Conceptual requests use CAG-only only when curated
knowledge actually covers the topic.

## Safety boundaries

- Live tools only issue fixed read-only HTTP requests.
- PCAP extraction uses an argument list and never invokes a shell.
- Raw packet bytes are never sent to a model.
- Input count, PCAP size, model calls, tool calls, and HTTP timeouts are bounded.
- Evidence content is marked as untrusted data in model prompts.
- Unknown citation IDs cannot support a factual claim.
- Supported facts require a verbatim quotation from available non-memory evidence.
- Grounding checks meaningful term coverage, identifiers, numbers, and negation.
- Memory can support context but cannot establish an authoritative fact.
- Missing live information is represented as unavailable evidence.

## Workflow observability

`VeraOrchestrator.get_topology()` reads nodes, conditional edges, and Mermaid output from the
compiled LangGraph object. `/v1/graph` exposes that typed representation. `/graph` renders it
with local HTML, CSS, and JavaScript under a restrictive content security policy; no diagram
or execution data is sent to an external rendering service. A persisted run activates only
its selected acquisition branch and records repeated generation and validation nodes.

## Retrieval

Bundled JSON documents and optional synchronized JSONL feeds share the same evidence schema.
The ranker combines normalized BM25 (`0.7`) with normalized embedding similarity (`0.3`).
Exact identifiers such as CVE, CWE, CAPEC, and ATT&CK IDs remain searchable as single tokens.
Hash embeddings provide a deterministic baseline; Sentence Transformers remain optional.

Corpus synchronization is explicit. The synchronizer downloads only allowlisted official
ATT&CK STIX and CISA KEV URLs, validates payload shape, normalizes source metadata, enforces
byte and document limits, and stages replacements before publishing local feed files.
Exact live sources execute concurrently. Provenance-aware deduplication preserves retrieval
order while preferring live API records over synchronized feeds and bundled snapshots.

## Claim grounding

Claims retain evidence IDs and add structured citations containing verbatim supporting
quotations. Validation checks registry integrity, quotation presence, meaningful term coverage,
identifiers, numeric values, and negation. Invalid claims receive one bounded retry when
available; otherwise they become explicit system inferences. Reflection and source coverage
are calculated from the grounded result rather than citation presence alone.

This deterministic layer rejects unrelated citations and simple contradictions. It remains a
conservative lexical check, not a complete natural-language inference model.

## Detection windows

Port scanning, authentication failures, and SYN bursts use configurable sliding windows.
Alerts expose observed count, threshold, first and last timestamps, duration, and confidence.
HTTP payload signatures remain event-local.

## Persistence

SQLite stores runs, evidence, reflection reports, and two memories per completed execution.
Semantic memory contains supported findings; episodic memory contains the request, route, and
outcome. Retrieval uses the configured local embedder and can be scoped by `session_id`.
