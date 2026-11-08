# Local models

VERA connects to a separate OpenAI-compatible model server. The examples use
`127.0.0.1:1234`; VERA itself uses port `8000`. Models are not included in Git.
Start only one server on a given port.

## LM Studio / Bionic

Load **Qwen3.5-4B Q4_K_M** from
[lmstudio-community](https://huggingface.co/lmstudio-community/Qwen3.5-4B-GGUF).
Use GPU offload, an 8,192-token context and disabled thinking where supported.
Start the local API server and obtain its exact model ID:

```bash
curl -fsS http://127.0.0.1:1234/v1/models
```

The display name, GGUF filename and API ID may differ.

## Apple silicon

Use a recent Metal-enabled
[`llama-server`](https://github.com/ggml-org/llama.cpp/tree/master/tools/server)
with MTP support. Download `Qwen3.5-4B-Q6_K.gguf` from
[unsloth/Qwen3.5-4B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.5-4B-MTP-GGUF)
into `.vera/models/qwen3.5-4b-mtp/`, then run:

```bash
llama-server -m .vera/models/qwen3.5-4b-mtp/Qwen3.5-4B-Q6_K.gguf \
  --spec-type draft-mtp --spec-draft-n-max 4 \
  -ngl 99 -fa on --ctx-size 8192 --parallel 1 \
  --reasoning off --reasoning-budget 0 \
  --host 127.0.0.1 --port 1234 --alias vera-qwen3.5-4b-mtp
```

The MTP head is included in this file; no separate draft model is needed.
If the flags are unknown, update `llama-server`. Performance depends on hardware.

## Test a fine-tuned adapter

The step-400 LoRA uses `Qwen/Qwen3.5-4B` revision `851bf6e8`; the adapter is separate
from the base model and stays under the ignored `.vera/finetuning/adapter-step400/`.
Convert it once with the matching llama.cpp revision (`8642541b2`):

```bash
python convert_lora_to_gguf.py .vera/finetuning/adapter-step400 \
  --outfile .vera/finetuning/adapter-step400/vera-step400-lora-f16.gguf \
  --outtype f16
```

Serve the base and adapter in one process:

```bash
llama-server -m .vera/models/qwen3.5-4b-mtp/Qwen3.5-4B-Q6_K.gguf \
  --lora .vera/finetuning/adapter-step400/vera-step400-lora-f16.gguf \
  -ngl 99 -fa on --ctx-size 8192 --parallel 1 \
  --reasoning off --reasoning-budget 0 \
  --host 127.0.0.1 --port 1234 --alias vera-qwen3.5-4b-step400
```

Inspect and set the adapter scale (`0` for base, `1` for full adapter):

```bash
curl -fsS http://127.0.0.1:1234/lora-adapters
curl -fsS -X POST http://127.0.0.1:1234/lora-adapters \
  -H 'Content-Type: application/json' -d '[{"id":0,"scale":1}]'
```

Point VERA at the alias:

```dotenv
VERA_LLM_PROVIDER=openai
VERA_LLM_MODEL=vera-qwen3.5-4b-step400
VERA_LLM_BASE_URL=http://127.0.0.1:1234/v1
VERA_LLM_TIMEOUT_SECONDS=600
```

Revalidate the served model: applying a LoRA to a quantized GGUF differs numerically
from merging the adapter before quantization. The adapter is experimental, not a
replacement model.

## Linux / NVIDIA helper

`bash scripts/start-local-model.sh` reuses LM Studio's CUDA runtime and serves
`vera-qwen3.5-4b`. It requires Linux/systemd and the installed runtime paths used
by the script. Override `VERA_LOCAL_MODEL_FILE`, `VERA_LOCAL_BACKEND` and
`VERA_LOCAL_CUDA_VENDOR` for another installation.
Stop this helper with `systemctl --user stop vera-qwen.scope`.

## Connect VERA

Set `.env` using the ID from `/v1/models`. This example uses the Apple alias:

```dotenv
VERA_LLM_PROVIDER=openai
VERA_LLM_MODEL=vera-qwen3.5-4b-mtp
VERA_LLM_BASE_URL=http://127.0.0.1:1234/v1
VERA_LLM_RESPONSE_FORMAT=json_schema
VERA_LLM_TIMEOUT_SECONDS=300
VERA_LLM_MAX_OUTPUT_TOKENS=4096
VERA_KG_ENABLED=true
VERA_KG_MAX_RESULTS=6
VERA_RETRIEVAL_K=3
VERA_MEMORY_K=0
VERA_REACT_ENABLED=false
VERA_LIVE_SOURCES=false
```

These are a local profile, not global defaults; see
[`Settings`](../src/vera/config.py) and `.env.example`.
Set `VERA_LLM_API_KEY` if the server requires authentication.
Restart VERA after changes. `vera serve` does not start the model.

## Enable bounded ReAct

ReAct is opt-in and requires an external provider; the deterministic provider cannot
make model action decisions. With the local OpenAI-compatible server above, enable it
in `.env`:

```dotenv
VERA_LLM_PROVIDER=openai
VERA_LLM_MODEL=vera-qwen3.5-4b-mtp
VERA_LLM_BASE_URL=http://127.0.0.1:1234/v1
VERA_LLM_RESPONSE_FORMAT=json_schema
VERA_REACT_ENABLED=true
VERA_MAX_REACT_STEPS=3
```

Use the exact model ID returned by `/v1/models` instead of the example alias. ReAct
asks the model for one JSON action at a time; it can search the local corpus, look up
an exact CVE already identified in the request, or finish. It does not expose
arbitrary commands, URLs or general web search. With the default three steps, VERA
budgets up to six model calls, including action decisions and answer generation.

The response details in chat show the ReAct action trace when present. The complete
result is also available from `/v1/runs/{run_id}` or `vera analyze --json`; inspect
`trace`, `metadata.react_steps` and `metadata.react_observations`. The trace includes
each action and its short operational reason; observations include whether it
completed, was skipped or rejected, and the new evidence IDs. This is an audit
summary, not the model's private chain-of-thought. The model must still return valid
action JSON, and enabling ReAct does not establish that a particular model or adapter
makes useful decisions; verify actual responses and warnings before relying on it.

## Verify and stop

Ask a question through `/chat` and inspect `metadata.model`,
`metadata.provider_fallback`, warnings and citations.
`/health` only confirms configuration. A pending HTTP `202` review is not an inference error.

With both servers running, `scripts/check-local-model.py` checks selected cases:

```bash
uv run --extra knowledge-graph python scripts/check-local-model.py
```

It saves `.vera/local-model-checks.json`, counts pending reviews as failed autonomous
answers and exits nonzero for them. It never approves a review and does not establish
general model accuracy.

For an automated, offline base/adapter comparison, run:

```bash
uv sync --extra knowledge-graph
uv run --extra knowledge-graph --with huggingface_hub \
  python scripts/reproduce_step400.py
```

The script downloads the pinned base GGUF and public adapter GGUF, verifies their
SHA-256 digests, starts a temporary loopback model server, runs the four-case A/B check
at LoRA scales 0 and 1, then stops the server. It uses repository-bundled snapshots,
disables ReAct/live sources, and writes to temporary databases; it does not require
`.env`, `.vera/corpus` or existing runtime databases. A `llama-server` binary built
from llama.cpp commit `8642541b2` is required because native builds vary by OS/GPU.
The check is a smoke test, not a general quality benchmark.

Stop manual servers with Ctrl+C; stop/unload GUI models through LM Studio/Bionic.
Use `VERA_LLM_PROVIDER=deterministic` to run without a model server.
