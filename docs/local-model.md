# Local model servers

VERA reaches any OpenAI-compatible local server on port 1234. Two profiles are tested:
**Qwen3.5-4B, GGUF Q4_K_M** on NVIDIA through LM Studio's CUDA runtime, and
**Qwen3.5-4B MTP, GGUF Q6_K** on Apple silicon through `llama-server` with the MTP draft
head. Model files are not included in Git.

## Model files and Bionic

The interactive profile uses **Qwen3.5-4B, GGUF Q4_K_M**, downloaded from
`lmstudio-community/Qwen3.5-4B-GGUF` into `.vera/models`. Its adjacent metadata JSON
records the pinned revision, file size, and verified SHA-256.
The NVIDIA GPU on this PC has about 6 GB VRAM; the earlier Qwen3.8-27B used CPU/RAM
offload and substantial swap. The smaller model is intended to fit entirely on the GPU.

On another computer, download the GGUF from the repository above, or obtain it through
Bionic/LM Studio's model search. The standard library location is:

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

## NVIDIA profile: start and stop

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

`openai` names the protocol adapter; the endpoint is on this PC. The profile uses
JSON Schema for routing, answer generation, and ReAct decisions. Model timeout is
independent of the short HTTP timeout used for vulnerability sources. Output token limits
produce an explicit failure rather than silently accepting truncated JSON.
Live sources are disabled for repeatable local checks; enable them separately for current
CVE lookups. Restart VERA after changing `.env`.

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

The Apple silicon profile uses the same values with `vera-qwen3.5-4b-mtp` as the model ID,
`VERA_LLM_TIMEOUT_SECONDS=300`, `VERA_LLM_MAX_OUTPUT_TOKENS=4096`, and `VERA_MEMORY_K=0`.

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

Run the four local checks sequentially against the running server. The script verifies
the model ID configured in `VERA_LLM_MODEL`; it also works with other local model servers:

```bash
uv run --extra knowledge-graph python scripts/check-local-model.py
```

The report is `.vera/local-model-checks.json`. Completed HTTP 200 results enter run history;
HTTP 202 responses are unpublished reviews. The checker reports the pending `run_id`,
`status`, and `reasons`, counts it as a failed autonomous answer, and exits nonzero.
It never decides a review; use `/chat` or [Human review](human-review.md).
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

In `/chat`, expand the response's sources and details to inspect its route and model.
The complete structured result remains available at `/v1/runs/<run_id>`.
`/knowledge-graph` explores domain knowledge independently of model inference.

## Apple silicon: Qwen3.5-4B MTP Q6_K

On an Apple M2 with 16 GiB unified memory, use a recent Metal-enabled `llama-server`
that supports MTP. The selected profile is **Qwen3.5-4B MTP, GGUF Q6_K** from
[`unsloth/Qwen3.5-4B-MTP-GGUF`](https://huggingface.co/unsloth/Qwen3.5-4B-MTP-GGUF).
The file is 3.4 GB and includes the MTP head, so no separate `-md` draft model is needed.
Start at 8,192 context tokens and one slot; larger contexts leave less room for macOS.

```bash
hf download unsloth/Qwen3.5-4B-MTP-GGUF Qwen3.5-4B-Q6_K.gguf \
  --local-dir .vera/models/qwen3.5-4b-mtp
llama-server -m .vera/models/qwen3.5-4b-mtp/Qwen3.5-4B-Q6_K.gguf \
  --spec-type draft-mtp --spec-draft-n-max 4 \
  -ngl 99 -fa on --ctx-size 8192 --parallel 1 \
  --reasoning off --reasoning-budget 0 \
  --host 127.0.0.1 --port 1234 --alias vera-qwen3.5-4b-mtp
```

MTP is a server-side decoding optimization, not a VERA setting. The log should contain
`creating MTP draft context`; if the flag is unknown, update `llama-server`.
`--spec-draft-n-max 4` was fastest on this M2. In 128-token completions with the same
prompt, the Q6_K target alone produced 21.3 tok/s, while MTP at draft limits 2/3/4/6/8
produced 32.2/34.1/36.2/33.4/25.6 tok/s. At four, 93 of 135 draft tokens were accepted
(69%), decoding was 70% faster, and warmed VERA total latency fell 42%, from 44.2 s to
25.8 s:

| Check | Q6_K alone | MTP, n-max 4 |
| --- | ---: | ---: |
| PowerShell | 13.6 s | 7.4 s |
| CWE-89 | 12.7 s | 6.9 s |
| Missing CVE | 9.7 s | 5.8 s |
| Out of scope | 8.2 s | 5.6 s |
| Total | 44.2 s | 25.8 s |

Both setups passed 3/4 in two consecutive runs, with the same cases and graph citations.
The fourth check remains an unpublished HTTP 202 review: the unknown CVE has no evidence,
so autonomous publication cannot pass while the missing-data review rule exists; 3/4 is
the maximum. MTP adds a draft head rather than a separate model; the checks showed no
quality loss. Disabling extended reasoning reduced latency in these tests. Do not use the
CUDA-specific `scripts/start-local-model.sh` for this profile.

Earlier Apple silicon candidates were removed. LFM2.5-8B-A1B Q6_K passed only 2/4, and its
official DSpark draft at three tokens improved warmed VERA checks by only 3.7%; nine draft
tokens were 23.8% slower. Qwen3.5-9B passed 3/4 but was substantially slower. There is no
official DSpark GGUF for Qwen3.5-4B; MTP is its supported speculative path. The only model
kept under `.vera/models` is `.vera/models/qwen3.5-4b-mtp/Qwen3.5-4B-Q6_K.gguf`.

Sources: [model quantization](https://huggingface.co/lmstudio-community/Qwen3.5-4B-GGUF),
[Qwen3.5-4B MTP GGUF](https://huggingface.co/unsloth/Qwen3.5-4B-MTP-GGUF),
[llama.cpp server](https://github.com/ggml-org/llama.cpp/tree/master/tools/server).
