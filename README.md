# VERA

VERA is a teaching prototype for evidence-based cybersecurity analysis. It combines curated
knowledge, local retrieval, a Kuzu Knowledge Graph, restricted live lookups, event-stream
rules, claim validation, reflection, and persistent memory. LangGraph runs the workflow.
An alert is a signal to investigate; it does not establish that a compromise occurred.

## 1. Install

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), and a terminal in the cloned
project directory. For model-generated answers, install LM Studio/Bionic or another
supported local model server. `tshark` is additionally required only for PCAP input.

```bash
uv sync --extra dev --extra knowledge-graph
cp -n .env.example .env
```

The copy preserves an existing `.env`. Edit its values in step 3. The default provider in
`.env.example` is `deterministic`: selecting Qwen requires the configuration below.
The default hash embedding backend needs no additional model download.

Git includes the graph schema, import code, and bundled source documents. `.env`, `.venv/`,
and `.vera/` are local and ignored: each colleague must obtain the model and build the graph.
Requests, memory, downloaded corpus updates, and generated database files are not shared by Git.

## 2. Start Qwen 3.5

The suggested local profile on the tested NVIDIA machine is **Qwen3.5-4B, GGUF Q4_K_M**
from [lmstudio-community/Qwen3.5-4B-GGUF](https://huggingface.co/lmstudio-community/Qwen3.5-4B-GGUF).
This is the profile tested with VERA on an NVIDIA GPU with about 6 GB VRAM. Prefer this
small profile to a 27B model on that hardware; performance depends on the machine.
On Apple silicon, the selected profile is **Qwen3.5-4B MTP Q6_K** from
[unsloth/Qwen3.5-4B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.5-4B-MTP-GGUF).
It uses the MTP draft head in `llama-server` and was about 70% faster at decoding than
the same Q6_K target without MTP, with no quality change in the local checks. See
[Apple silicon: Qwen3.5-4B MTP Q6_K](docs/local-model.md#apple-silicon-qwen35-4b-mtp-q6_k).

Choose **one** model-server option. Both use port **1234**; VERA uses port **8000**.

### Option A: Bionic / LM Studio

1. Download `Qwen3.5-4B-Q4_K_M.gguf` through Bionic's model search, or select it in your
   existing library. A fresh clone does not contain the model.
2. Load Qwen3.5-4B. For the tested NVIDIA profile, use GPU offload, an 8,192-token context,
   and disable thinking if the runtime exposes that setting.
3. In **Developer**, start the local API server on `127.0.0.1:1234`.
4. List the [models visible to the server](https://lmstudio.ai/docs/developer/openai-compat/models):

```bash
curl -fsS http://127.0.0.1:1234/v1/models
```

Copy Qwen's exact `data[].id` into `VERA_LLM_MODEL` in step 3. The displayed model name,
file name, and API identifier may differ. The server must remain running while using VERA.
See the official [local API server instructions](https://lmstudio.ai/docs/developer/core/server).

### Option B: existing Linux/NVIDIA script

```bash
bash scripts/start-local-model.sh
```

This uses LM Studio's installed CUDA runtime directly, without its GUI, and serves the
model as **`vera-qwen3.5-4b`**. It requires Linux/systemd, the GGUF at
`.vera/models/Qwen3.5-4B-Q4_K_M.gguf`, and the installed runtime paths used by the script.
If the model is only in Bionic's library, set `VERA_LOCAL_MODEL_FILE` to its absolute path.
Other machines may also need `VERA_LOCAL_BACKEND` and `VERA_LOCAL_CUDA_VENDOR` overrides.
The script limits CPU to two logical cores, RAM to 8 GiB, and swap to 1 GiB; it requests all
model layers on CUDA0. See [runtime paths, measurements, and checks](docs/local-model.md).

## 3. Connect VERA to the model

Update these values in `.env`, replacing the model ID with the one from step 2:

```dotenv
VERA_LLM_PROVIDER=openai
VERA_LLM_MODEL=REPLACE_WITH_QWEN_ID_FROM_V1_MODELS
VERA_LLM_BASE_URL=http://127.0.0.1:1234/v1
VERA_LLM_RESPONSE_FORMAT=json_schema
VERA_LLM_TIMEOUT_SECONDS=120
VERA_LLM_MAX_OUTPUT_TOKENS=1024
VERA_KG_ENABLED=true
VERA_KG_PATH=.vera/knowledge.kuzu
VERA_KG_MAX_RESULTS=6
VERA_RETRIEVAL_K=3
VERA_MEMORY_K=1
VERA_REACT_ENABLED=false
VERA_LIVE_SOURCES=false
```

For **option B**, the model ID is `vera-qwen3.5-4b`. `openai` selects the compatible API
protocol; requests go to the local endpoint above. If Bionic requires authentication, set
`VERA_LLM_API_KEY` as well. Restart VERA whenever you change `.env`.
Live sources are disabled here for repeatable local tests; local Qwen and Kuzu still work.
Set `VERA_LIVE_SOURCES=true` separately when you want authoritative online CVE lookups.

## 4. Build the graph and start VERA

In another terminal, from the project directory:

```bash
uv run --extra knowledge-graph vera kg-build
uv run --extra knowledge-graph vera kg-status
uv run --extra knowledge-graph vera serve --open-browser
```

`kg-build` reconstructs the initial graph from the bundled corpus; no Kuzu server or Qwen
inference is needed for this step. Repeating the import does not duplicate unchanged records.
The model server and VERA are separate processes; `vera serve` does not start Qwen.

| Address | Purpose |
| --- | --- |
| <http://127.0.0.1:8000/docs> | Submit requests with POST `/v1/analyze`, **Try it out**, **Execute** |
| <http://127.0.0.1:8000/graph> | Ask a question, preview routes, or inspect saved executions |
| <http://127.0.0.1:8000/knowledge-graph> | Explore domain entities, relationships, and sources |
| <http://127.0.0.1:8000/health> | Inspect configured provider, model, and graph enablement |

The `/graph` question form shows completed reports or unpublished pending reviews; see
[Human review](docs/human-review.md). Previews do not run. Use API for events, CLI for PCAP.

## 5. Ask questions and verify the connection

```bash
curl -fsS http://127.0.0.1:8000/v1/analyze \
  -H 'Content-Type: application/json' \
  -d '{"query":"Explain PowerShell. Give a brief answer with one sourced claim."}'
```

In Swagger, the same request body is:

```json
{"query":"Explain PowerShell. Give a brief answer with one sourced claim."}
```

Check `metadata.model` against your Qwen ID and `metadata.provider_fallback=false` to verify
the model answered. Nonempty `metadata.knowledge_graph.cited_evidence_ids` shows graph
evidence was cited. `/health` alone confirms configuration, not successful model inference.
Refresh `/graph` and select the saved run to inspect its route. Read the complete answer in
`answer`, or retrieve it later through GET `/v1/runs/<run_id>` or `vera history`.

The CLI also uses `.env` and the running model server; it does not require `vera serve`:

```bash
uv run --extra knowledge-graph vera analyze "Explain PowerShell" --offline --json
uv run --extra knowledge-graph vera analyze "Analyze this traffic" \
  --events src/vera/data/samples/benign-web.jsonl --simulated --offline --json
uv run --extra knowledge-graph vera analyze "Analyze this traffic" \
  --events src/vera/data/samples/port-scan.jsonl --simulated --offline --json
```

The event examples select `STREAM` without alerts and `FULL` with `NET-PORT-SCAN`, respectively.
Use structured `events` in API requests, `--events` for JSON/JSONL, or `--pcap capture.pcap`
with `tshark` installed. Pasting raw log text into `query` does not invoke stream detectors.
`--simulated` labels synthetic data; omit it for real events. `--offline` disables live source
lookups, while local model calls and graph retrieval remain available where selected.

For either server, run the four sequential model/graph/scope checks using `VERA_LLM_MODEL`:

```bash
uv run --extra knowledge-graph python scripts/check-local-model.py
```

## Stop and troubleshoot

- Stop VERA with **Ctrl+C** in its terminal. For option A, stop/unload the model in Bionic.
- For option B, stop Qwen with `systemctl --user stop vera-qwen.scope`.
- If port 1234 is occupied, stop the other model server before switching options.
- On model fallback, inspect `warnings`, verify `/v1/models`, and check the ID/base URL.
- If Kuzu is locked, disconnect Kuzu Explorer before running imports or analyses.
- To run without an LLM, set `VERA_LLM_PROVIDER=deterministic` and restart VERA.

## Routes and evidence

The resource plan selects the route from the request and the available evidence; the branch
table is in [Workflow Explorer](docs/workflow-explorer.md#reading-the-workflow). Claims
distinguish `supported_fact` (quoted available evidence), `system_inference`, `unavailable`,
and `simulated`; memory is not authoritative factual support.

## Development and documentation

```bash
uv run --extra dev --extra knowledge-graph ruff check .
uv run --extra dev --extra knowledge-graph pytest
VERA_LLM_PROVIDER=deterministic uv run --extra knowledge-graph vera evaluate --json
uv run --extra knowledge-graph vera corpus-sync
uv run --extra knowledge-graph vera kg-build
```

Corpus synchronization is explicit and downloads official ATT&CK/CISA data; it is not
required for the bundled graph. Rebuild after synchronization to import the updated sources.
Other provider adapters are Ollama and Gemini; settings are defined in `.env.example` and
[`Settings`](src/vera/config.py). Optional Sentence Transformers use the `embeddings` extra
and `VERA_EMBEDDING_BACKEND=sentence-transformers` instead of the default hash backend.

See [Knowledge Graph](docs/knowledge-graph.md), [Workflow Explorer](docs/workflow-explorer.md),
[local models](docs/local-model.md), [architecture](docs/architecture.md), and
[data provenance](docs/data-provenance.md) for details and limits.

[Kaggle fine-tuning](docs/fine-tuning.md) covers offline data preparation and Kaggle-only LoRA.
