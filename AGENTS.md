# AGENTS.md — VERA Machine Entry Point

> **VERA (Vulnerability Evidence and Reasoning Agent)**
> A deterministic-first cybersecurity analysis workflow built with LangGraph, Kuzu Graph, and strict evidentiary verification.

---

## Agent Navigation Hub

Comprehensive architectural specifications, engineering guidelines, operational toolbooks, and agent skills are organized in the [`agents/`](./agents/) directory:

- 📖 **Main Agent System Guide**: [`agents/AGENTS.md`](./agents/AGENTS.md)
- 🏗️ **LangGraph Architecture & State**: [`agents/architecture.md`](./agents/architecture.md)
- 🛡️ **Safety Boundaries & Anti-Patterns**: [`agents/guidelines.md`](./agents/guidelines.md)
- ⚙️ **CLI Tooling & `.env` Reference**: [`agents/tooling-and-commands.md`](./agents/tooling-and-commands.md)
- 📚 **Threat Taxonomy & Claim Contracts**: [`agents/domain-ontology.md`](./agents/domain-ontology.md)

---

## Quick Reference Commands

Always use **`uv`** for dependency management and execution:

```bash
# Sync environment with dev and knowledge-graph extras
uv sync --extra dev --extra knowledge-graph

# Run code linters
uv run ruff check .

# Build and verify Kuzu Knowledge Graph (Kuzu 0.11.3)
uv run --extra knowledge-graph vera kg-build
uv run --extra knowledge-graph vera kg-status

# Run benchmark evaluation scenarios (synthetic)
uv run vera evaluate

# Start local server (Chat at /chat, KG at /knowledge-graph, OpenAPI at /docs)
uv run --extra knowledge-graph vera serve --open-browser
```

---

## Agent Skills Available (`agents/skills/`)

- [`vera-workflow-dev`](./agents/skills/vera-workflow-dev/SKILL.md): LangGraph state transitions, node development, ReAct loop, and human review policies.
- [`vera-kg-operations`](./agents/skills/vera-kg-operations/SKILL.md): Kuzu graph operations, table migrations, projection replay, entity resolution, and neighborhood queries.
- [`vera-testing-and-eval`](./agents/skills/vera-testing-and-eval/SKILL.md): Running benchmark evaluations, validating claim grounding rates, and adding synthetic scenarios.
- [`vera-model-setup`](./agents/skills/vera-model-setup/SKILL.md): Configuring local model servers (Qwen 3.5 4B, LM Studio, Bionic, llama-server) on port 1234.

---

## Core Invariants

1. **Evidentiary Grounding**: Factual claims (`supported_fact`) require verbatim quotations from available non-memory evidence with >=55% token overlap.
2. **Untrusted Evidence**: External CVE/NVD descriptions and packet headers are marked untrusted to prevent prompt injection.
3. **No Shell Invocations**: PCAP extraction uses `PcapExtractor` with fixed `tshark` argument lists. Never invoke shell subprocesses.
4. **Loopback Protection**: `vera serve` only binds to loopback (`127.0.0.1` / `::1`) to safeguard human review actions.
