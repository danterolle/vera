# VERA Tooling, CLI Reference & Operational Manual

> **Target Audience**: AI Agents running commands, building artifacts, or diagnosing environments in the VERA workspace.

---

## 1. CLI Commands Reference (`vera`)

The command line interface is implemented using Typer in `src/vera/interfaces/cli.py`. Always execute via `uv run` to ensure project virtual environment and extras are activated.

### 1. Analysis & Evaluation
```bash
# Basic offline analysis with JSON output
uv run --extra knowledge-graph vera analyze "Explain PowerShell T1059.001" --offline --json

# Analyze real or synthetic event logs
uv run vera analyze "Investigate suspicious auth spikes" \
  --events src/vera/data/samples/brute_force.jsonl \
  --simulated

# Analyze PCAP traffic replay (requires tshark installed)
uv run vera analyze "Inspect traffic replay" \
  --pcap /path/to/capture.pcap \
  --offline

# Run controlled benchmark evaluation (all synthetic test scenarios)
uv run vera evaluate --json

# Inspect previous execution runs
uv run vera history --limit 10
```

### 2. Knowledge Graph Operations (Kuzu 0.11.3)
```bash
# Incrementally build/rebuild graph from curated knowledge & corpus
uv run --extra knowledge-graph vera kg-build

# Check graph health and node counts without mutating database
uv run --extra knowledge-graph vera kg-status

# Export neighborhood of an entity as bounded JSON
uv run --extra knowledge-graph vera kg-export --id "PowerShell" --limit 50 --output powershell-graph.json
```

### 3. Corpus Management & Threat Feeds
```bash
# Check status of local bundled corpus and synchronized documents
uv run vera corpus-status

# Synchronize upstream threat intelligence feeds (CISA KEV, ATT&CK STIX)
uv run vera corpus-sync --feed all
uv run vera corpus-sync --feed attack
uv run vera corpus-sync --feed kev
```

### 4. Human Review Operations
```bash
# List all pending or open human reviews
uv run vera reviews

# Interactive terminal decision
uv run vera review <run_id> --interactive

# Direct non-interactive decisions
uv run vera review <run_id> --approve
uv run vera review <run_id> --reject "Citations do not match evidence text."
uv run vera review <run_id> --revise "Include the specific CVE identifiers mentioned."
uv run vera review <run_id> --retry
```

### 5. Web & API Server
```bash
# Start local server (Chat UI at /chat, Knowledge Graph at /knowledge-graph, OpenAPI at /docs)
uv run --extra knowledge-graph vera serve --open-browser --port 8000
```

---

## 2. Environment Variables Configuration (`.env`)

Settings are managed via Pydantic Settings in `src/vera/config.py`:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `VERA_LLM_PROVIDER` | `deterministic` | Provider: `openai`, `gemini`, `ollama`, or `deterministic` |
| `VERA_LLM_MODEL` | `vera-qwen3.5-4b` | Exact model ID exposed by the server endpoint |
| `VERA_LLM_BASE_URL` | `http://127.0.0.1:1234/v1` | URL of the local or remote OpenAI-compatible server |
| `VERA_LLM_RESPONSE_FORMAT` | `json_schema` | Structured output mode (`json_schema` or `none`) |
| `VERA_LLM_TIMEOUT_SECONDS`| `120` | Timeout for model generation |
| `VERA_LLM_MAX_OUTPUT_TOKENS`| `1024` | Maximum token budget per generation step |
| `VERA_KG_ENABLED` | `false` | Enable Kuzu Knowledge Graph integration |
| `VERA_KG_PATH` | `.vera/knowledge.kuzu` | Filesystem path for Kuzu database files |
| `VERA_KG_MAX_RESULTS` | `6` | Maximum entity neighborhood results retrieved per query |
| `VERA_RETRIEVAL_K` | `3` | Number of local corpus RAG documents to retrieve |
| `VERA_MEMORY_K` | `1` | Number of previous session memory snippets to recall |
| `VERA_REACT_ENABLED` | `false` | Enable optional bounded ReAct decision loop |
| `VERA_MAX_REACT_STEPS` | `3` | Maximum autonomous ReAct decision steps |
| `VERA_LIVE_SOURCES` | `false` | Allow outbound read-only HTTP lookups to CVE/NVD |
| `VERA_WEB_SEARCH_API_KEY` | `""` | Optional Brave Search API key for live web context |
| `VERA_DB_PATH` | `.vera/database.sqlite`| SQLite storage path for history, reviews, checkpoints |

---

## 3. Local Model Deployment (Qwen 3.5 4B)

VERA is optimized for **Qwen 3.5 4B (GGUF Q4_K_M)** on machines with ~6GB VRAM.

### Option A: LM Studio / Bionic GUI
1. Search and download `Qwen3.5-4B-Q4_K_M.gguf`.
2. Configure GPU offload to maximize VRAM usage; set context window to `8192` tokens.
3. Disable thinking mode if exposed.
4. Start local API server on `127.0.0.1:1234`.
5. Verify model ID with `curl -fsS http://127.0.0.1:1234/v1/models` and copy ID into `VERA_LLM_MODEL`.

### Option B: Linux Headless Script (`scripts/start-local-model.sh`)
```bash
bash scripts/start-local-model.sh
```
- Uses LM Studio's installed CUDA runtime directly without GUI.
- Exposes model ID **`vera-qwen3.5-4b`** on `http://127.0.0.1:1234`.
- Enforces cgroups resource limits: CPU capped at 2 logical cores, RAM at 8 GiB, swap at 1 GiB.

---

## 4. Diagnostics & Troubleshooting Runbook

### Issue: "Review checkpoint is missing" (HTTP 503)
- **Cause**: SQLite database corrupted or review thread pruned while pending.
- **Resolution**: Run `vera reviews` to list state. If error persists, re-run analysis to generate a fresh checkpoint.

### Issue: "Unsupported Kuzu schema version"
- **Cause**: Kuzu database at `.vera/knowledge.kuzu` was created with a previous schema.
- **Resolution**: Run `uv run --extra knowledge-graph vera kg-build` to execute automatic migrations.

### Issue: Model timeout / fallback triggered
- **Cause**: Local model server at `127.0.0.1:1234` is unresponsive, busy, or context exceeds GPU memory.
- **Resolution**:
  1. Test endpoint reachability: `curl -m 3 http://127.0.0.1:1234/v1/models`
  2. Inspect VERA response `metadata.provider_fallback`. If `true`, output was generated by the deterministic fallback engine.
  3. Increase `VERA_LLM_TIMEOUT_SECONDS` if decoding is slow on CPU.
