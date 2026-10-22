# Qwen3.5 fine-tuning on Kaggle

Training runs **only on Kaggle**. Local commands below prepare synthetic data, run ordinary
code checks, and build an upload archive. They do not load model weights or train adapters.
Training dependencies are isolated in `training/kaggle/requirements.txt`, not VERA's runtime.

## Prepare the private upload

From the repository root:

```bash
uv run vera-prepare-kaggle
```

The upload ZIP is visible at `vera-sft-v1.zip` in the repository root. A copy and its unpacked
contents are kept in `.vera/finetuning/`, which Finder normally hides.
Existing outputs are never overwritten; use `--output .vera/finetuning/vera-sft-v2` for a
new bundle. Optional `--train-size`, `--validation-size`, `--test-size`, and `--seed` flags
control generation; each split needs at least 20 examples.

The archive contains the following:

| Path | Purpose |
| --- | --- |
| `data/train/*.jsonl` | 2,000 synthetic training conversations |
| `data/validation/*.jsonl` | 200 model-selection conversations |
| `data/test/*.jsonl` | 300 final held-out conversations |
| `data/sources.jsonl` | Source URLs, original IDs, content hashes and version metadata |
| `data/manifest.json` | Split groups, checksums, task counts and limitations |
| `wheels/*.whl` | Installable VERA code and bundled public resources |
| `requirements-kaggle.txt` | Pinned core training packages and Unsloth source revisions |
| `vera-qwen35.ipynb` | Notebook to import into Kaggle |
| `bundle.json` | Checksums for the complete upload |
| `quality-report.json` | Exhaustive automated target, provenance, split and coverage audit |

No `.env`, `.vera` databases, local model weights, real logs or existing HITL decisions are
read. The wheel includes VERA's public package, not the local checkout or its Git history.
The notebook checks the automated audit without requiring a manual-review declaration.
This is not expert or legal approval. The repository's software license does not replace
upstream data licenses. Keep the Dataset and notebook private; public
redistribution and commercial use require a separate source-license review.

## Data contract and limitations

Each row has `messages`, an ID, task, source groups and provenance. The system/user messages
use VERA's actual `SYSTEM_PROMPT` and `generation_prompt`; the assistant target is
`GeneratedAnswer` JSON, not a rendered report or `AnalysisResult`.
Targets pass the existing claim validator and additional exact-quotation checks.

Half the examples teach grounded quoting. The remainder cover unavailable sources,
irrelevant records, memory-only context, cautious inference, simulated traffic, scope,
untrusted instructions and synthetic revision feedback. All targets are explicitly
`synthetic_template`, with **no human-review approval implied**.
This bootstrap dataset teaches the application contract, not general cybersecurity expertise.
2,500 augmented examples are not 2,500 independently annotated security cases.
The automated audit checks every row, including exact origin of factual source content.
Each split contains simulated traffic both above and below its detection threshold.

Source records are grouped before augmentation by shared URLs, identifiers and exact
content. Parent/subtechnique IDs share a group. Source groups never cross splits;
distractors come from the same split. Relationship-only ATT&CK and OWASP mapping records
are excluded rather than treated as independently grounded graph conclusions.
Stream families are separately held out: port scanning for training, authentication for
validation and SYN bursts for testing. Stream technique IDs can occur in document examples;
this is not a claim that every semantic concept is unseen during training.
Scope topics are also separated. Exact semantic duplicates ignore randomized evidence IDs.
Nothing changes VERA's graph traversal, detector thresholds, tools or HITL policy.

## Kaggle execution

1. Create a **private Dataset** from the ZIP, preserving its extracted directories.
2. Import `training/kaggle/vera-qwen35.ipynb` into a **private notebook**, attach that Dataset,
   enable Internet and select **GPU T4 x2**.
3. Run the location cell: it verifies all bundle hashes and the matching automated audit.
4. Run location and installation. Restart the kernel, rerun location, then configuration.
   Installation uses CUDA 12.6 wheels and must be compatible with Kaggle's installed driver.
5. Leave `GPU_COUNT = 1`. Run preflight, baseline, 40-update smoke training and smoke
   evaluation. Preflight rejects overlong examples instead of truncating evidence or JSON.
6. Inspect the raw validation answers, rates, finite gradients, changed adapter weights,
   memory and measured time. Only then set `RUN_FULL_TRAINING = True`, rerun configuration,
   and execute the full-training and full-validation cells.
7. After selecting an adapter, optionally enable `RUN_FINAL_TEST` for the same 300 held-out
   examples on both models. Do not select more hyperparameters against the test results.
8. Download the complete results ZIP before ending the session. It includes the adapter,
   retained checkpoints and smoke provenance. Save the notebook without automatically
   rerunning all cells. Export to merged weights or GGUF is optional and disabled by default.

The notebook uses separate subprocesses so model memory is released between stages.
Do not use Run All blindly, rerun completed output cells, or keep an idle GPU session running.
Only the main training process writes shared reports, adapters and checkpoint recipes.

## T4 precision, memory and two GPUs

The recipe pins `Qwen/Qwen3.5-4B` revision
`851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`, uses language-only rank-8 LoRA,
alpha 16, learning rate `5e-5`, batch 1, gradient checkpointing and no 4-bit training.
Only assistant target tokens contribute to the loss. Default context is 2,048 tokens;
data-loader workers are zero and dataset preparation uses one process.

T4 has no native BF16. Qwen3.5's generic FP16 path can overflow, so the loader must activate
its float32 safeguards; training does not force FP16 autocast.
The advertised BF16 memory estimate is not a T4 guarantee.
Dependency installation, CUDA kernels, peak memory and real training speed still need the
Kaggle smoke run; CPU tests do not establish CUDA compatibility.
The Linux/Python 3.11 dependency lock is generated from `requirements.txt` and `pyproject.toml`;
each run also saves the actual `pip freeze` environment. The notebook installs the lock.

If the one-GPU smoke run succeeds, optionally change `GPU_COUNT = 2`, rerun configuration,
and run a **new** smoke/evaluation pair before full DDP training.
One GPU uses accumulation 8; two GPUs use accumulation 4 per process, keeping effective
batch 8. DDP replicates the model and does not combine memory into a 32 GB device.
If useful contexts do not fit one card, stop: DDP is not a memory fix. Do not disable
precision guards or silently switch to QLoRA. Sharding/offload needs a separate experiment.

Treat the 30 weekly hours as a ceiling, not a training target. Reserve at most two hours
for initial compatibility, eight for a first training run, six for a motivated alternative,
four for evaluation/export and ten for recovery. These are spending caps, not runtime
predictions. With 2,000 examples and effective batch 8, one epoch is about 250 updates.
Estimate elapsed time after compilation, adding evaluation and checkpoint overhead.

## Checkpoints, evaluation and deployment

Smoke runs save every ten updates; full runs save every fifty and retain two checkpoints.
Checkpoints contain optimizer/scheduler/RNG state and a recipe fingerprint, not just LoRA.
The download cell can also archive full-run checkpoints after a training subprocess fails,
even if no final adapter was saved. Run it before ending the interactive session.
After interruption, attach previously saved Kaggle outputs or the extracted results ZIP
as a private Dataset. Set `SMOKE_REPORT_OVERRIDE` to `provenance/smoke-report.json` and
`RESUME_CHECKPOINT` to the original complete checkpoint directory in configuration.
Resume requires the same dataset hash, model revision, GPU count and training recipe.
A model-only adapter is not accepted as a resumable Trainer checkpoint.
Checkpoint files are trusted executable model artifacts; only resume your own outputs.

Raw evaluation checks JSON, exact quotation grounding, expected claim statuses, relevant
factual source selection and scope, without repair or provider fallback. It preserves raw
answers and identifies output truncation. The small validation subset is stratified by task.
These checks do not fully validate prose summaries or exercise HITL. After deployment,
keep VERA's application-level review rules and compare matched local runs; missing evidence
can correctly result in HTTP 202, not an autonomous report.

The adapter pins its original base revision. Optional export uses that same base and can
require substantial RAM/disk or llama.cpp compilation. GGUF quantization after LoRA is
different from QLoRA training. MTP preservation is not verified. Compare the exported GGUF
again against the original local profile before changing `VERA_LLM_MODEL`.

References: [Qwen model](https://huggingface.co/Qwen/Qwen3.5-4B),
[Unsloth Qwen3.5](https://unsloth.ai/docs/models/qwen3.5/fine-tune),
[Unsloth DDP](https://unsloth.ai/docs/basics/multi-gpu-training-with-unsloth/ddp).
