# VERA Architecture Specification

> **Target Audience**: AI Agents and Engineers contributing to VERA's workflow, data model, or reasoning pipelines.

---

## 1. System Topology & LangGraph Pipeline

VERA is structured as a deterministic state machine managed by LangGraph. It compiles into a single directed execution graph with conditional branching:

```mermaid
flowchart TD
    START([START]) --> Init[initialize\nExtract alerts, memory, stats]
    Init --> Route[route\nInterpret intent & build ResourcePlan]
    
    Route -->|CAG_ONLY| CAG[cag\nCurated knowledge only]
    Route -->|CAG_RAG| RAG[rag\nCAG + Local Corpus + Kuzu KG]
    Route -->|CAG_RAG_TOOL| Tools[tools\nCAG + RAG + Read-only CVE APIs]
    Route -->|STREAM| Stream[stream\nCAG + Event statistics & rules]
    Route -->|FULL| Full[full\nAll sources combined]
    
    CAG --> ReactCheck{ReAct Enabled?}
    RAG --> ReactCheck
    Tools --> ReactCheck
    Stream --> ReactCheck
    Full --> ReactCheck
    
    ReactCheck -->|Yes| ReActDecide[react_decide\nBounded step budget]
    ReActDecide -->|Action: local_corpus or cve_lookup| ReActExec[react_execute\nExecute read-only action]
    ReActExec --> ReActDecide
    ReActDecide -->|Action: finish| Gen[generate\nDraft response & extract claims]
    ReactCheck -->|No| Gen
    
    Gen --> Val[validate\nGrounding, quotation & ID checks]
    Val -->|retry_generation is True (max 1 retry)| Gen
    Val -->|Validated or exhausted| Refl[reflection\nCompleteness & score metrics]
    
    Refl --> ReviewAssess[review_assess\nDeterministic check for held review]
    ReviewAssess -->|review_required is True| ReviewWait[review_wait\nCheckpoint state & pause]
    ReviewAssess -->|review_required is False| Finalize[finalize\nPersist report & memory]
    
    ReviewWait -->|approve| Finalize
    ReviewWait -->|reject| END([END: Unpublished])
    ReviewWait -->|revise (max 2)| Revise[revise\nFeedback loop]
    Revise -->|retry generate| Val
    Revise -->|error| ReviewAssess
    
    Finalize --> END
```

---

## 2. GraphState: Typed Execution Context

All nodes read and mutate a centralized typed state dictionary defined in `src/vera/domain/state.py`:

```python
class GraphState(TypedDict, total=False):
    request: AnalysisRequest         # User query, session_id, conversation context, events
    request_received_at: str         # ISO-8601 UTC timestamp
    started_at: float                # High-precision start timestamp (perf_counter)
    active_ms: float                 # Cumulative execution latency excluding human pauses
    route: Route                     # Derived route enum (CAG_ONLY, CAG_RAG, etc.)
    route_reason: str                # Human-readable routing rationale
    resource_plan: ResourcePlan      # Intent, extracted CVEs/ATT&CK IDs, subqueries
    alerts: list[Alert]              # Deterministic detection alerts from stream
    statistics: EventStatistics      # Volume, protocols, source IPs, port frequencies
    incident: IncidentContext        # Consolidated incident telemetry
    memory: list[MemorySnippet]      # Recalled semantic snippets and past user context
    evidence: list[Evidence]         # Master registry of all retrieved evidence items
    draft: DraftResponse             # LLM output text + structured Claim candidates
    generation_attempts: int         # Count of generation cycles (max 2: initial + 1 repair)
    retry_generation: bool           # Flag triggering repair loop
    validation_errors: list[str]     # Exact errors reported during citation verification
    reflection: Reflection           # Completeness score, grounded counts, gaps
    review_required: bool            # True if draft fails safety/evidence threshold
    review_reasons: list[str]        # Specific triggers holding the draft
    review_record: ReviewRecord      # Held review object for API/UI persistence
    review_action: str               # "approve", "reject", or "revise"
    revision_count: int              # Bounded counter (<= 2)
    revision_feedback: str | None    # Human reviewer input
    revision_error: str | None       # Error if revision generation fails
    react_action: ReActDecision      # Current ReAct action (decision + reason)
    react_steps: int                 # Current step in the ReAct budget
    react_observations: list[dict]   # Logged tool execution history
    model_calls: int                 # Running count of model inferences
    tool_calls: int                  # Running count of external/tool queries
    provider_fallback: bool          # True if external LLM failed and deterministic fallback was used
    trace: list[str]                 # Execution audit breadcrumbs
    warnings: list[str]              # Non-fatal operational notices
    result: AnalysisResult           # Published final report
```

---

## 3. The 5 Routing Channels (`ResourcePlan`)

The Meta-Controller in `src/vera/routing/router.py` parses the user's intent and extracts technical identifiers (CVEs, ATT&CK techniques, CWEs).

1. **`CAG_ONLY`** (`cag`):
   - Curated Knowledge documents (NIST 800-61r2, OWASP Top 10, FIRST CSIRT principles).
   - Activated for foundational concepts when verified to be inside curated data.
2. **`CAG_RAG`** (`rag`):
   - Curated Knowledge + Local Corpus (ATT&CK techniques, software, groups, CWEs) + Kuzu Knowledge Graph semantic retrieval.
3. **`CAG_RAG_TOOL`** (`tools`):
   - CAG + RAG + live read-only vulnerability APIs (CVE.org, NVD, CISA KEV, EPSS, OSV, optional Brave web search).
   - Triggered when exact CVE IDs or live threat research are requested.
4. **`STREAM`** (`stream`):
   - CAG + Event stream telemetry (normalized JSON/JSONL or PCAP extraction).
   - Evaluates port scan, brute force, syn burst, and injection pattern rules.
5. **`FULL`** (`full`):
   - Composite pipeline activating Stream detection, Knowledge Graph, Retrieval, and CVE lookups simultaneously.

---

## 4. Evidentiary Verification & Grounding Pipeline

Model reasoning is subjected to strict deterministic validation in `src/vera/reasoning/`:

1. **Quotation Verification (`grounding.py`)**:
   - Every `supported_fact` claim MUST include a verbatim quote from cited evidence.
   - The quote must exist verbatim in the evidence text.
   - Token lexical overlap between the claim text and the supporting quote must meet or exceed **55%** (`minimum_coverage = 0.55`).
   - All identifiers (CVEs, CWEs, techniques) and numeric facts (CVSS scores, EPSS percentiles, port counts) in the claim must be present in the supporting quote.
2. **Repair Loop (`validation.py`)**:
   - If validation fails on the first pass, `retry_generation` is set to `True`.
   - The validation errors are passed directly into the correction prompt.
   - Exactly **one** bounded correction attempt is allowed. If the corrected output still fails validation, claims are downgraded to `system_inference` or `unavailable`, and human review is triggered.
3. **Reflection (`reflection.py`)**:
   - Computes completeness metrics, verified citation coverage, and identifies evidence gaps.

---

## 5. Human-in-the-Loop Review System

Implemented in `src/vera/workflow/review.py` and `src/vera/workflow/review_service.py`:

- **Deterministic Review Triggers**:
  - Detection alerts with severity `HIGH` or `CRITICAL`.
  - Unsupported claims (`reflection.unsupported_claims > 0`).
  - Genuinely out-of-scope classification for cybersecurity queries.
  - Zero usable non-memory evidence, or missing evidence for an explicitly queried CVE.
  - Draft contains no findings.
- **Workflow Pausing & Checkpointing**:
  - The workflow executes up to `review_wait` and yields control.
  - State is saved in SQLite using LangGraph's `SqliteSaver`.
  - The API emits HTTP `202 Accepted` returning a `ReviewRecord`.
  - The draft remains unpublished: it is **not** written to run history, semantic memory, or the Knowledge Graph.
- **Decision Invariants**:
  - `approve`: Finalizes and persists the report (`AnalysisResult`).
  - `reject`: Closes the run permanently without publishing.
  - `revise`: Takes feedback (up to 4,000 chars), executes one focused re-generation, and enters review again (maximum 2 revision cycles).

---

## 6. Knowledge Graph (Kuzu 0.11.3)

Located in `src/vera/knowledge_graph/`:

- **Storage**: Embedded Kuzu database stored at `.vera/knowledge.kuzu` (no external daemon).
- **Core Node Tables**:
  - `Entity`: Threat entities (id, kind, name, aliases). Kinds: `Technique`, `Tactic`, `Mitigation`, `Software`, `Group`, `Vulnerability`, `Weakness`, `Guidance`.
  - `SourceRecord`: Provenance document snapshots (record_key, evidence_id, source, url, title, content).
  - `Assertion`: Semantic relationships (predicate, status).
  - `Run`, `Alert`, `Event`: Operational run telemetry.
- **Projection**:
  - When an analysis run completes successfully, a background projection job writes the run's entities, citations, and alerts into Kuzu.
  - Replay of pending projection jobs occurs automatically during `vera kg-build`.
