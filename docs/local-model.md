# Local Qwen3.5 with NVIDIA

The interactive profile uses **Qwen3.5-4B, GGUF Q4_K_M**, downloaded from
`lmstudio-community/Qwen3.5-4B-GGUF` into `.vera/models`. Its adjacent metadata JSON
records the pinned revision, file size, and verified SHA-256.
The NVIDIA GPU on this PC has about 6 GB VRAM; the earlier Qwen3.8-27B used CPU/RAM
offload and substantial swap. The smaller model is intended to fit entirely on the GPU.

## Model files and Bionic

Model files are not included in Git. On another computer, download the GGUF from the
repository above, or obtain it through Bionic/LM Studio's model search. The standard
library location is:

```text
~/.lmstudio/models/lmstudio-community/Qwen3.5-4B-GGUF/Qwen3.5-4B-Q4_K_M.gguf
```

On the development workstation, this library entry was imported as a hard link to the
file in `.vera/models`: both paths work without duplicating the model's disk usage.
That local import is not reproduced by cloning the repository.
To use a model already in Bionic's library with the script, run in the same terminal:

```bash
export VERA_LOCAL_MODEL_FILE="$HOME/.lmstudio/models/lmstudio-community/Qwen3.5-4B-GGUF/Qwen3.5-4B-Q4_K_M.gguf"
```

The script additionally requires Linux/systemd, an NVIDIA GPU, and the installed LM Studio
CUDA runtime and vendor libraries. Its default paths include a runtime version specific to
the development workstation; adjust the overrides below if your installed paths differ.
For serving directly through the Bionic GUI instead, follow
[README option A](../README.md#option-a-bionic--lm-studio). Use the actual model ID returned
by `/v1/models` in `.env`; `vera-qwen3.5-4b` is the alias assigned by the script.

## Start and stop

From the project directory, in one terminal:

```bash
bash scripts/start-local-model.sh
```

The script reuses LM Studio's installed CUDA 12 `llama-server` and vendor libraries,
without starting the Bionic GUI. No new driver or container is installed.
The LM Studio/Bionic application itself is still available for managing models;
its CLI discovery stopped working after the application's automatic update.

The model listens only on `127.0.0.1:1234`, with all layers requested on CUDA0,
8,192 context tokens, thinking disabled, one inference slot, small batches, and two CPU
threads. A transient user systemd scope additionally caps CPU at 200% (two logical cores),
RAM at 8 GiB, and swap at 1 GiB. These settings apply to this process, not the whole PC.
The runtime path can be overridden with `VERA_LOCAL_BACKEND` and `VERA_LOCAL_CUDA_VENDOR`;
the GGUF path with `VERA_LOCAL_MODEL_FILE`.

In a second terminal:

```bash
uv run --extra knowledge-graph vera serve
```

To stop the model immediately:

```bash
systemctl --user stop vera-qwen.scope
```

Stop VERA with Ctrl+C in its terminal. The model is not started automatically by VERA.

## Local configuration

```dotenv
VERA_LLM_PROVIDER=openai
VERA_LLM_MODEL=vera-qwen3.5-4b
VERA_LLM_BASE_URL=http://127.0.0.1:1234/v1
VERA_LLM_RESPONSE_FORMAT=json_schema
VERA_LLM_TIMEOUT_SECONDS=120
VERA_LLM_MAX_OUTPUT_TOKENS=1024
VERA_KG_ENABLED=true
VERA_KG_MAX_RESULTS=6
VERA_RETRIEVAL_K=3
VERA_MEMORY_K=1
VERA_REACT_ENABLED=false
VERA_LIVE_SOURCES=false
```

`openai` names the protocol adapter; the endpoint is on this PC. The profile uses
JSON Schema for routing, answer generation, and ReAct decisions. Model timeout is
independent of the short HTTP timeout used for vulnerability sources. Output token limits
produce an explicit failure rather than silently accepting truncated JSON.
Live sources are disabled for repeatable local checks; enable them separately for current
CVE lookups. Restart VERA after changing `.env`.

## Manual verification

Open `/docs`, select **POST /v1/analyze**, then **Try it out** and **Execute**:

```json
{"query":"Explain PowerShell. Give a brief answer with one sourced claim."}
```

Or run without requiring the VERA API server:

```bash
uv run --extra knowledge-graph vera analyze "Explain PowerShell" --offline --json
```

Check `metadata.model`, `metadata.provider_fallback`, `metadata.out_of_scope`, `warnings`, and
`metadata.knowledge_graph.cited_evidence_ids`. A nonempty cited list proves graph evidence
was used in the answer; availability and model-call counts alone do not.
`/health` reports configuration, not proof of a successful generation.
Try a known technique/weakness, an unknown CVE, and an unrelated question: missing details
must remain unavailable and unrelated questions must stay outside VERA's cybersecurity scope.

Run the four local checks sequentially against the running server. These checks expect
the script profile's exact model alias `vera-qwen3.5-4b`; for other API identifiers, use
the manual request and inspect the returned metadata as described above:

```bash
uv run --extra knowledge-graph python scripts/check-local-model.py
```

The report is `.vera/local-model-checks.json`; each result is also saved in normal run history.
These checks exercise selected cases, not a general guarantee of model accuracy.
The generation context includes source titles. Verified claim text repeats its source quote
to avoid introducing identifiers absent from that quote. When the model declares a question
out of scope, the application enforces a refusal without claims or citations.

The local check on 2026-10-13 took about 9 s for PowerShell, 9 s for CWE-89, 21 s for
missing CVE data, and 4 s for an unrelated question. The missing-data test needed a claim
status correction by the validator; all final checks passed without deterministic fallback.
The measured model scope peaked around 100% CPU (one logical core), 3.4 GiB RAM,
and zero swap; total NVIDIA usage peaked around 3 GiB with 99% utilization.
Resource measurements are stored in `.vera/local-model-resources.json`.

In `/graph`, refresh and select the saved execution to inspect its route and metrics.
The complete answer is in the API/CLI result or `/v1/runs/<run_id>`.
`/knowledge-graph` explores domain knowledge independently of model inference.

Sources: [model quantization](https://huggingface.co/lmstudio-community/Qwen3.5-4B-GGUF),
[llama.cpp server](https://github.com/ggml-org/llama.cpp/tree/master/tools/server).
