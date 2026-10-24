# AGENTS.md — VERA Agentic System Guide

> **VERA (Vulnerability Evidence and Reasoning Agent)**
> A deterministic-first cybersecurity analysis workflow built with LangGraph, Kuzu Graph, and strict evidentiary verification.

---

## 1. Executive Summary & Mental Model

- **What VERA is**: A deterministic, stateful LangGraph workflow designed for evidence-based cybersecurity reasoning. It combines Curated Knowledge (CAG), Local Retrieval (RAG), an embedded Kuzu Knowledge Graph (KG), restricted read-only authoritative APIs (CVE.org, NVD, CISA KEV, FIRST EPSS, OSV), event stream detection, citation validation, lexical grounding, and conditional human-in-the-loop review.
- **What VERA is NOT**: It is **not** an unbounded swarm of autonomous sub-agents with shell access. It does not blindly trust model outputs; every factual claim must be backed by non-memory evidence quotes. An alert or correlation is a signal to investigate, never proof of compromise.
- **Core Invariant**: Evidence content is marked as untrusted data. Models are restricted to structured extraction and drafting. Unknown citation IDs or missing verbatim quotes fail validation deterministically.

---

## 2. Fast Operational Cheat Sheet

Always use **`uv`** for execution. Do not use plain `python` or `pip`.

```bash
# Environment sync (always include extras if working with dev/KG)
uv sync --extra dev --extra knowledge-graph

# Run code linters & syntax checks
uv run ruff check .

# Knowledge Graph lifecycle (Kuzu 0.11.3 embedded)
uv run --extra knowledge-graph vera kg-build
uv run --extra knowledge-graph vera kg-status

# Run benchmark evaluation scenarios (offline, synthetic)
uv run vera evaluate

# Execute deterministic / local analysis via CLI
uv run --extra knowledge-graph vera analyze "Explain PowerShell" --offline --json

# Start local server (Chat & Knowledge Graph Viewport)
# NOTE: Server strictly enforces loopback (127.0.0.1) for local review security
uv run --extra knowledge-graph vera serve --open-browser
```

---

## 3. Directory & Context Map (Progressive Disclosure)

When working on specific subsystems, load the dedicated reference files in `agents/` to maintain a lean context window:

| Topic | Deep-Dive Reference File | Purpose |
| :--- | :--- | :--- |
| **System Architecture** | [`architecture.md`](./architecture.md) | LangGraph topology, `GraphState`, node contracts, ReAct loop, checkpoints, SQLite stores |
| **Rules & Guardrails** | [`guidelines.md`](./guidelines.md) | Safety invariants, anti-patterns, typing standards, Pydantic immutability, review policies |
| **Tooling & Commands** | [`tooling-and-commands.md`](./tooling-and-commands.md) | Full CLI reference, `.env` config options, model server profiles (Qwen 3.5 4B), ports |
| **Domain Ontology** | [`domain-ontology.md`](./domain-ontology.md) | Threat intelligence taxonomy (CVE, CWE, CAPEC, ATT&CK, EPSS, KEV), claim statuses, detection rules |

---

## 4. Specialized Agent Skills

The `agents/skills/` directory contains procedural runbooks formatted according to the open Agent Skills standard (`SKILL.md` with YAML frontmatter):

- [`vera-workflow-dev`](./skills/vera-workflow-dev/SKILL.md): Modifying or adding LangGraph nodes, managing state transitions, tuning the ReAct loop, and adjusting review checkpoints.
- [`vera-kg-operations`](./skills/vera-kg-operations/SKILL.md): Kuzu graph operations, table migrations, projection replay, entity resolution, and neighborhood queries.
- [`vera-testing-and-eval`](./skills/vera-testing-and-eval/SKILL.md): Running regression evaluations, validating grounding rates, and adding synthetic benchmark scenarios.
- [`vera-model-setup`](./skills/vera-model-setup/SKILL.md): Configuring local model servers (LM Studio, Bionic, llama-server) on port 1234, JSON schema responses, and debugging timeout fallbacks.

---

## 5. Non-Obvious Technical Constraints

1. **Local Ports**:
   - VERA Web & API: `http://127.0.0.1:8000` (strictly loopback; rejects external hosts).
   - Local LLM Server: `http://127.0.0.1:1234/v1` (OpenAI-compatible protocol, default model `vera-qwen3.5-4b`).
2. **Kuzu Dependency**:
   - Pinned strictly to `kuzu==0.11.3`. Do not upgrade Kuzu without validating schema migrations in `src/vera/knowledge_graph/schema.py`.
3. **Pydantic Immutability**:
   - Domain models (`ResourcePlan`, `AnalysisRequest`, `Evidence`, `Claim`, `AnalysisResult`) use `frozen=True` and `extra="forbid"`. Update state using `model_copy(update={...})`.
4. **Human Review Gate**:
   - When claims lack verified support, detection alerts are High/Critical, or required CVE evidence is unavailable, VERA returns HTTP `202` (`ReviewRecord`) rather than `200` (`AnalysisResult`). The draft is held unpersisted until approved, revised, or rejected.
5. **No Shell Invocations in Core Flow**:
   - PCAP parsing uses `PcapExtractor` with fixed `tshark` argument arrays. Never use `subprocess.run(..., shell=True)`.
