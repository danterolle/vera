# VERA Engineering & Agentic Guidelines

> **Target Audience**: AI Agents and Developers writing or refactoring code in the VERA repository.

---

## 1. Code Style & Tooling Invariants

- **Python Version**: Strictly Python 3.11+ (tested on Python 3.12).
- **Package Management**: **`uv`** is the mandatory toolchain. Never run `pip install` or direct `python -m venv`.
- **Linter & Formatter**:
  - Code must pass `uv run ruff check .` with zero errors.
  - Formatted to 100 character line limit (`line-length = 100`, target version `py311`).
  - Active ruff rule groups: `E` (pycodestyle errors), `F` (Pyflakes), `I` (isort), `UP` (pyupgrade), `B` (flake8-bugbear), `SIM` (flake8-simplify).
- **Pydantic v2 Conventions**:
  - All domain contracts under `src/vera/domain/` must declare:
    ```python
    model_config = ConfigDict(extra="forbid", frozen=True)
    ```
  - Direct attribute mutation is prohibited on frozen models. Use `model.model_copy(update={...})`.
  - Validate models via `Model.model_validate(data)` rather than `Model(**data)`.

---

## 2. Safety & Security Boundaries

These guardrails are fundamental to VERA's mission as an evidence-based security engine:

### 1. Read-Only External Interactions
- Live API adapters (`src/vera/sources/`) MUST only perform read-only `GET` queries to authoritative catalogs (CVE.org, NVD, KEV, EPSS, OSV, Brave Search).
- Never implement `POST`, `PUT`, or state-modifying requests against external APIs.
- External queries must have strict timeouts (`VERA_HTTP_TIMEOUT_SECONDS`, default 10s) and handle network failures gracefully by returning `EvidenceStatus.UNAVAILABLE`.

### 2. PCAP Ingestion Safety
- Packet extraction (`src/vera/stream/pcap.py`) must invoke `tshark` using a direct argument list (`subprocess.run(["tshark", "-r", ...], ...)`).
- **NEVER** use `shell=True` or interpolate user-supplied filenames into shell strings.
- Raw packet payload bytes must never be transmitted to an LLM. Only aggregated metadata (protocols, ports, timestamp deltas, packet counts) are forwarded.

### 3. Evidentiary Asymmetry & Untrusted Evidence
- All retrieved evidence and event payloads are treated as **untrusted data**.
- In LLM prompts (`src/vera/providers/prompts.py`), evidence snippets are clearly encapsulated inside isolation boundaries to prevent prompt injection from attacker-controlled CVE descriptions or HTTP headers.
- **Memory Invariant**: Recalled conversational memory (`MemorySnippet`) can provide conversational context, but CANNOT be used as supporting evidence for a `supported_fact` claim. Only authoritative source records (CAG, RAG, Tool) can establish facts.

### 4. Local Loopback Protection
- `vera serve` is hardcoded to enforce loopback binding (`127.0.0.1` or `::1`).
- Non-loopback bindings or remote proxy headers are rejected at startup and runtime to prevent unauthorized execution of human review decisions.

---

## 3. Strict Architectural Anti-Patterns

When generating or editing code, **DO NOT**:

| Anti-Pattern | Why It Breaks the System | Correct Pattern |
| :--- | :--- | :--- |
| **Bypassing `validate_and_repair`** | Claims would reach the user without lexical quote verification or identifier validation. | Always route generation output through `WorkflowNodes.validate`. |
| **Direct SQLite mutation outside stores** | Corrupts review snapshots and breaks atomic state recovery in LangGraph. | Use `ReviewStore`, `MemoryStore`, or LangGraph checkpointers. |
| **Unbounded ReAct execution** | Risk of infinite model loops and quota exhaustion. | Always decrement `react_steps` against `settings.max_react_steps`. |
| **Auto-approving held drafts** | Destroys the conditional human-in-the-loop safety guarantee. | Return `ReviewRecord` with HTTP 202 and await explicit human decision. |
| **Silent Fallback masking** | Conceals model provider outages from the user. | Set `metadata.provider_fallback=True` and attach explicit warning. |
| **Arbitrary web navigation** | VERA is not an open web crawler. | Restrict lookups to configured CVE endpoints or bounded Brave search queries. |

---

## 4. Error Handling Hierarchy

All custom exceptions inherit from `VeraError` (`src/vera/errors.py`):

```text
VeraError
├── ConfigurationError      # Misconfigured provider, model ID, or missing required dependency
├── ModelUnavailableError   # LLM server offline, endpoint timeout, or invalid JSON schema
├── SourceUnavailableError  # Upstream catalog (NVD, CVE.org) HTTP 429/500 or timeout
├── ValidationError         # Input validation or schema constraint failure
└── ReviewUnavailable       # Attempted invalid transition on pending review (e.g. stale version)
```

- When external sources fail, do not crash the workflow. Convert the failure into an `Evidence` object with `status = EvidenceStatus.UNAVAILABLE` and continue execution.
