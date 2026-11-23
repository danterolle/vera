# Local models

VERA talks to a model server running in a separate process. The examples below use
an OpenAI-compatible API on `127.0.0.1:1234`, while VERA listens on port `8000`.
Model files are not included in Git. Run only one model server on a given port.

## LM Studio / Bionic

Load **Qwen3.5-4B Q4_K_M** from
[lmstudio-community](https://huggingface.co/lmstudio-community/Qwen3.5-4B-GGUF).
Enable GPU offload, select an 8,192-token context and disable thinking where supported.
After starting the local API, read its model ID:

```bash
curl -fsS http://127.0.0.1:1234/v1/models
```

Use the returned identifier in VERA. It may differ from both the display name and
the GGUF filename.

## Apple silicon

Use a recent Metal-enabled
[`llama-server`](https://github.com/ggml-org/llama.cpp/tree/master/tools/server)
with MTP support. Download `Qwen3.5-4B-Q6_K.gguf` from
[unsloth/Qwen3.5-4B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.5-4B-MTP-GGUF)
into `.vera/models/qwen3.5-4b-mtp/`, then start it with:

```bash
llama-server -m .vera/models/qwen3.5-4b-mtp/Qwen3.5-4B-Q6_K.gguf \
  --spec-type draft-mtp --spec-draft-n-max 4 \
  -ngl 99 -fa on --ctx-size 8192 --parallel 1 \
  --reasoning off --reasoning-budget 0 \
  --host 127.0.0.1 --port 1234 --alias vera-qwen3.5-4b-mtp
```

This file includes the MTP head, so no separate draft model is needed. If your server
does not recognize these flags, update it. Performance will depend on the hardware.

## Test a fine-tuned adapter

The experimental step-400 LoRA was trained on `Qwen/Qwen3.5-4B` revision `851bf6e8`.
Keep it separate from the base under the ignored `.vera/finetuning/adapter-step400/`.
Using the matching llama.cpp revision, `8642541b2`, convert it once with:

```bash
uv run python convert_lora_to_gguf.py .vera/finetuning/adapter-step400 \
  --outfile .vera/finetuning/adapter-step400/vera-step400-lora-f16.gguf \
  --outtype f16
```

The command assumes that llama.cpp's conversion script and its dependencies are
available in your conversion environment. Then serve the base and adapter together:

```bash
llama-server -m .vera/models/qwen3.5-4b-mtp/Qwen3.5-4B-Q6_K.gguf \
  --lora .vera/finetuning/adapter-step400/vera-step400-lora-f16.gguf \
  -ngl 99 -fa on --ctx-size 8192 --parallel 1 \
  --reasoning off --reasoning-budget 0 \
  --host 127.0.0.1 --port 1234 --alias vera-qwen3.5-4b-step400
```

You can inspect the loaded adapters and set their scale through the API. A scale of
`0` selects the base behavior; `1` applies the adapter fully:

```bash
curl -fsS http://127.0.0.1:1234/lora-adapters
curl -fsS -X POST http://127.0.0.1:1234/lora-adapters \
  -H 'Content-Type: application/json' -d '[{"id":0,"scale":1}]'
```

Set `VERA_LLM_MODEL=vera-qwen3.5-4b-step400` in the connection profile below. Applying
a LoRA to a quantized GGUF is numerically different from merging it before
quantization, so evaluate the artifact you actually serve, not just its source adapter.

## Serve the merged v4 artifact

The local v4 artifact already contains the adapter merged into the pinned base before
quantization. It needs no `--lora` flag. The file is
`.vera/models/vera-v4-676-merged-Q6_K.gguf`, approximately 3.2 GB, with SHA-256
`872292b16661ab123e51f588d857592c0eab0d1d74aae0615d1310e954ec21a6`.

```bash
llama-server -m .vera/models/vera-v4-676-merged-Q6_K.gguf \
  -ngl 99 -fa on --ctx-size 8192 --parallel 1 \
  --reasoning off --reasoning-budget 0 \
  --host 127.0.0.1 --port 1234 --alias vera-v4-676-merged
```

Use `VERA_LLM_MODEL=vera-v4-676-merged` in VERA. The artifact remains experimental:
the [v4 results](finetuning-v4-results.md) do not authorize deployment, and acceptance
of the current runtime still needs fresh independent answers and human review.

## Linux / NVIDIA helper

`bash scripts/start-local-model.sh` reuses LM Studio's CUDA runtime to serve
`vera-qwen3.5-4b`. It expects Linux/systemd and the installed paths used by the script.
For another installation, override `VERA_LOCAL_MODEL_FILE`, `VERA_LOCAL_BACKEND` and
`VERA_LOCAL_CUDA_VENDOR`. Stop the helper with
`systemctl --user stop vera-qwen.scope`.

## Connect VERA

Put the model ID from `/v1/models` into `.env`. This example is a local profile,
not a list of global defaults; consult [`Settings`](../src/vera/config.py) and
`.env.example` for those.

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

Set `VERA_LLM_API_KEY` if authentication is required. The step-400 profile previously
used a 600-second timeout; choose a supported timeout for the server you run. Restart
VERA after editing `.env`. The `vera serve` command does not start the model server.

## Enable bounded ReAct

ReAct is optional and requires an external provider; the deterministic provider
cannot choose model actions. With the local connection above, enable it by setting:

```dotenv
VERA_REACT_ENABLED=true
VERA_MAX_REACT_STEPS=3
```

Use the exact API model ID rather than assuming the example alias. ReAct requests one
JSON action at a time: search the local corpus, look up an exact CVE already identified
in the request, or finish. It cannot run arbitrary commands, open arbitrary URLs or
perform general web search. With three steps, the automatic budget is six model calls,
including action decisions and answer generation.

Chat response details show the action trace. The complete result is also available
at `/v1/runs/{run_id}` or through `vera analyze --json`. Inspect `trace`,
`metadata.react_steps` and `metadata.react_observations` for actions, short operational
reasons, outcomes and new evidence IDs. This is an audit summary, not private
chain-of-thought. Enabling ReAct does not establish that a model chooses useful actions.

## Verify and stop

Ask a question in `/chat` and inspect `metadata.model`, `metadata.provider_fallback`,
warnings and citations. `/health` confirms configuration only; `/ready` checks basic
inference with a synthetic request. HTTP `202` means a
draft is waiting for review, not necessarily that inference failed.

With both servers running, the bounded local check is:

```bash
uv run --extra knowledge-graph python scripts/check-local-model.py
```

It writes `.vera/local-model-checks.json`, counts pending reviews as failed autonomous
answers and exits nonzero for them. It never approves a review or establishes general
accuracy. For the historical four-case offline base/adapter comparison, use:

```bash
uv sync --extra knowledge-graph
uv run --extra knowledge-graph --with huggingface_hub \
  python scripts/reproduce_step400.py
```

This downloads pinned artifacts, verifies their hashes, starts a temporary loopback
server, compares LoRA scales 0 and 1, then stops the server. It uses bundled snapshots
and temporary databases with ReAct and live sources disabled. No `.env`, local corpus
or existing database is needed. A server built from llama.cpp `8642541b2` must already
be installed; native builds depend on the OS and GPU.

To probe 30 cybersecurity questions, six unrelated requests and four social messages:

```bash
uv run --extra knowledge-graph --with huggingface_hub \
  python scripts/scope_probe.py --output .vera/finetuning/scope-probe.json
```

The probe uses the same pinned artifacts and temporary server, but distinguishes
correct rejection from in-domain over-refusal. Add `--backend sentence-transformers`
and `--extra embeddings` to compare retrieval backends. It writes only a JSON report.
Stop manual servers with Ctrl+C and unload GUI models through LM Studio/Bionic.
To run without a model server, select `VERA_LLM_PROVIDER=deterministic`.
