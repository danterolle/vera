# Isolated Kaggle validation for Qwen3.5

This package currently validates installation, data formatting and an optional baseline.
It is **not a ready domain fine-tuning dataset**. The default notebook never starts training
or downloads Qwen model weights. Real CUDA checks run only on Kaggle; local verification
does not establish T4 compatibility, model memory fit or training stability.

## Data suitability

The default bundle has 2,000 training, 200 validation and 300 test conversations.
Each JSONL shard has up to 200 complete system/user/assistant exchanges, not one sentence.
The targets follow VERA's short JSON answer contract.

However, the 1,300 factual claims in the training split contain only **86 distinct texts**.
Template variations are useful for testing quotation, JSON, unavailable information,
memory boundaries and simulation handling; they are not independent expert annotations.
The manifest explicitly marks the data `purpose: "contract_bootstrap"`.
Full training is rejected on that purpose before GPU libraries are imported.
Domain SFT needs a separate, substantially more diverse dataset and independent evaluation.
Changing a metadata label is not a substitute for collecting suitable examples.

The automated audit checks every target, original factual source, duplicate, split and
claim-status coverage. Each split contains simulated traffic with and without alerts.
This is not expert or legal approval. The software license does not replace source terms.
Keep uploads private; upstream data provenance is retained in `data/sources.jsonl`.
No local runtime databases, real logs, credentials or genuine HITL decisions are read.

## Build the private package

From the repository root:

```bash
uv run vera-prepare-kaggle
```

The visible upload is `vera-sft-v3.zip`. An identical copy and unpacked contents are kept in
`.vera/finetuning/vera-sft-v3/`. Existing outputs are not overwritten; use
`--output .vera/finetuning/vera-sft-v4` for another build.
Optional `--train-size`, `--validation-size`, `--test-size` and `--seed` control generation.
Every split needs at least 20 examples. Increasing row counts does not create new expertise.

| Included path | Purpose |
| --- | --- |
| `data/*/*.jsonl` | Synthetic contract conversations |
| `data/sources.jsonl` | Original source IDs, URLs, versions and content hashes |
| `data/manifest.json` | Purpose, split groups and shard checksums |
| `quality-report.json` | Automated audit, diversity counts and explicit limitations |
| `wheels/*.whl` | VERA package, without local secrets or model weights |
| `requirements-kaggle.txt` | Linux/Python 3.11 dependency lock |
| `bootstrap.py` | Isolated installer and dependency checks |
| `vera-qwen35.ipynb` | Notebook with safe defaults |
| `bundle.json` | Upload checksums and workflow version |

## Notebook flow

Attach only the v3 bundle to a private Kaggle notebook, enable Internet and select T4 x2.
Import `training/kaggle/vera-qwen35.ipynb`. No kernel restart is required.
By default, Run All executes only:

1. Bundle, workflow-version and data-audit verification.
2. Installation in `/kaggle/working/vera-finetuning/runtime`.
3. A runtime check: real imports, loader/trainer APIs, NumPy and small CUDA arithmetic.
4. Tokenizer-only validation of every record, including exact assistant loss masks.
5. Packaging of available diagnostics and provenance, even without a trained adapter.

The installer uses an actual virtual environment with global and user packages excluded.
It never installs training packages into Kaggle's notebook-kernel Python.
`pip check` must pass before the isolated runtime is marked ready.
All subprocesses, including DDP, use that runtime's Python with `-I`.
Python path/home overrides are removed. The base notebook environment is not repaired,
upgraded or downgraded by the installer.

If any stage fails, do not continue to later compute stages. The download cell can still
collect available diagnostics. Existing reports are preserved rather than silently reused
or overwritten; use a fresh work directory for an independent repeated validation.

### Optional model baseline

Only after the runtime and data checks pass, set `RUN_BASELINE = True` and execute the
baseline cell. It downloads the pinned Qwen3.5-4B weights and evaluates nine stratified cases.
No claim repair or deterministic provider fallback is used.
Raw answers and truncation are retained. This checks the application contract, not the
whole of cybersecurity reasoning, summary accuracy or HITL behavior.

### Optional training compatibility probe

`RUN_SMOKE = False` by default. After a baseline, explicitly enabling it performs only five
optimizer updates, followed by a small adapter evaluation. This is a numerical and memory
compatibility experiment, not domain fine-tuning or evidence of improved quality.
Finite gradients and actual adapter updates are checked; non-finite values stop execution.
Keep full training, final model testing and export disabled for the bundled bootstrap.

The separate CLI also rejects full training on the bootstrap, even if a smoke report passes.
An appropriate domain dataset, independent evaluation and a matching successful smoke run
are prerequisites for any future full-training use.

## T4 limitations and quota

The model is `Qwen/Qwen3.5-4B`, pinned to revision
`851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`. The optional LoRA probe uses rank 8,
alpha 16, learning rate `5e-5`, batch 1, gradient checkpointing and no 4-bit training.
The context limit is 2,048 tokens; overlong examples fail instead of being truncated.

T4 has no native BF16. Qwen3.5's generic FP16 path can overflow, so the pinned loader must
activate its float32 safeguards. No forced FP16 override or automatic QLoRA fallback exists.
The advertised BF16 memory estimate is not a T4 guarantee.
Runtime checks do not load the full model or exercise gated-delta training kernels;
their report explicitly leaves `model_load_verified` and `training_verified` false.

Start with `GPU_COUNT = 1`, even though Kaggle supplies two T4 cards.
DDP replicates the model; it does not combine them into a single 32 GB memory device.
One process uses accumulation 8; two use accumulation 4 to preserve effective batch 8.
Every different GPU count/context/recipe needs its own compatibility probe.
Treat 30 weekly hours as a ceiling, not a training target. Do not leave an idle GPU session
running, run repeated hyperparameter searches on the bootstrap or infer timing from JIT startup.

## Persistence and older notebooks

Download the results ZIP before ending a session. It includes diagnostics, provenance and
any completed adapter/checkpoints, but never the installed runtime or model caches.
A diagnostics ZIP without an adapter is explicitly identified as such.
Interrupted smoke runs can still preserve complete checkpoints through the download cell.
Only your own complete Trainer checkpoints are safe resume inputs.

If an old global installer changed Kaggle's preinstalled packages, a kernel restart alone
does not undo those pip changes. If the kernel still works, the legacy recovery cell
`training/kaggle/recover.py` can use a separate environment without reuploading its Dataset.
If the notebook was deleted or the kernel itself is broken, use a clean session and the v3
workflow only after its actual T4 validation has been confirmed.

References: [Qwen model](https://huggingface.co/Qwen/Qwen3.5-4B),
[Unsloth Qwen3.5](https://unsloth.ai/docs/models/qwen3.5/fine-tune),
[Unsloth DDP](https://unsloth.ai/docs/basics/multi-gpu-training-with-unsloth/ddp).
