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

Stop manual servers with Ctrl+C; stop/unload GUI models through LM Studio/Bionic.
Use `VERA_LLM_PROVIDER=deterministic` to run without a model server.
