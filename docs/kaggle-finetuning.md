# Kaggle pilot and dataset

The standalone [notebook](../finetuning/kaggle.ipynb) targets structured cybersecurity
answer generation with **Qwen/Qwen3.5-4B**.
A five-update FP32 pilot completed on two Kaggle T4 GPUs, peaking at 9.91 and 10.15 GiB
of PyTorch-allocated VRAM. This establishes initial execution compatibility, not
quality improvement or full-epoch reliability. It does not train social replies,
intent interpretation, source assessment or ReAct decisions.

## Dataset

The retained v1 dataset is incompatible with the current chat prompt and remains
local-only. The **v4 candidate** replaces it for the next experiment: it is rebuilt
against the current `SYSTEM_PROMPT` and `generation_prompt`, and it closes the gaps that
the step-400 adapter exposed. Dataset card:
[domain dataset v4](domain-dataset-v4.md).

`vera-domain-v4.zip` and `.vera/datasets/vera-domain-v4/` are local, ignored artifacts.
They contain **4,863 training, 622 validation and 655 test** conversations (6,140 total),
plus 130 controlled event replays. Targets combine pinned public MITRE ATT&CK and CISA KEV
records, 122 repository-bundled official documents and synthetic analyst scenarios. They
are not expert SOC decisions. Upstream revisions, hashes and license notices are preserved
in the archive.

| Gap in v1/v3 data | v4 coverage |
| --- | --- |
| Prompt drift | both messages come from the current runtime prompts; the manifest records `sha256(SYSTEM_PROMPT)` |
| One-sided scope | in-domain, unavailable-but-in-domain, social, clarification and `out_of_scope` families |
| Social handled as security | `social_conversation` and `clarification` targets carry no claims and set `out_of_scope=false` |
| Alerts only 0/1 | train alert counts `{0: 4773, 1: 40, 2: 30, 3: 20}`; validation and test cover 0-3 |
| No multi-turn | follow-up conversations with resolved question, subject and search query |
| No language variants | Italian, Spanish, German and French questions answered in the configured English |
| Entity/title drift | targets quote evidence verbatim and name the entity each record concerns |

Both `human_reviewed` and `training_authorized` remain false; the archive is a candidate,
not an approved corpus.

User-facing prose follows `Settings.response_language` (`VERA_RESPONSE_LANGUAGE`,
default `English`) rather than the input message language. This value is supplied to
generation and conversation prompts; evidence quotations remain verbatim in their
source language.

## Token budget

The v4 preflight passes at **`max_length=2560`** with `truncation: false` and a verified
assistant-only loss boundary. A 2,048-token budget would drop 80 `stream_triage` rows and
still truncate 48 at 2,304, because three-alert replays need up to **2,462 tokens**
(question prefix plus multi-alert evidence). 2,560 is the smallest tested budget that
keeps alert counts 2 and 3, so it is the justified choice. The targets themselves are much
shorter: the largest is **543 tokens**. Preflight writes `token-budget.json` bound to the
dataset's `manifest.json` SHA-256; packaging refuses a receipt that does not match.

## Training approach

Two T4 GPUs have separate memory. This recipe uses one process with **FP32 LoRA
and model sharding**, not DDP, BF16, FP16 or 4-bit QLoRA.
T4 lacks native BF16 training; Qwen3.5 has documented FP16 gradient stability issues,
and its model-specific guide discourages 4-bit QLoRA.
Full-epoch cost and memory fit for other workloads remain unverified.

The [model setup](../finetuning/vera_finetuning/model.py) pins the base revision
and uses eager attention, gradient checkpointing, LoRA rank 8 and alpha 16.
The pilot performs five updates including the longest input and largest target.
A full experiment performs `--epochs` passes (default 1) with accumulation 8; each
epoch is reshuffled deterministically, and a resume continues from the saved epoch and
data cursor. Neither recipe is optimized. For an intermediate experiment, `--max-steps`
stops a full-mode run after a bounded absolute number of updates, `--validation-every`
records validation loss during training and `--validation-examples` controls the fixed
validation sample. These runs write `metrics.jsonl` so the curve survives outside the
notebook log.

## Prepare and run

Build and audit the v4 candidate without loading weights, then package it:

```bash
uv run python finetuning/vera_domain/cli.py
uv run python finetuning/prepare.py \
  --dataset .vera/datasets/vera-domain-v4.zip --max-length 2560 \
  --output .vera/finetuning/vera-kaggle-training-v4.zip
```

Generation is data-only: it calls no external model, loads no weights, refuses to
overwrite an existing directory or archive, and verifies source hashes. `prepare.py`
validates archive hashes, the actual runtime prompts and grounded targets, refuses any
example that exceeds the declared token budget, and writes the data-free code bundle.
It never trains, modifies the dataset, uploads data or overwrites an existing bundle.
Use `--max-length 2560` for this candidate; lower budgets either fail or require dropping
multi-alert rows, which is not permitted.

1. Import the notebook into Kaggle. Attach a private dataset containing `vera-domain-v4.zip`
   and its code bundle; these exact filenames are required. Do not upload credentials,
   databases or company telemetry.
2. Select **GPU T4 x2**, enable Internet and run preflight. Every example must fit the
   declared token budget without truncation, with a verified assistant-only loss boundary.
3. Read the warnings, set `ACKNOWLEDGE_CANDIDATE_DATA = True` and run the five-update pilot.
   Non-finite loss or gradients stop execution. Retain any OOM/kernel traceback;
   do not silently truncate examples or switch to unstable reduced precision.
4. Inspect the report, memory peaks and duration before explicitly enabling
   `RUN_FULL_TRAINING`. For a bounded preview set `MAX_STEPS` (for example 50),
   keep `VALIDATION_EVERY` enabled and set `RUN_BEHAVIORAL_EVAL = True` to generate
   base/adapter answers on a stratified validation sample. Save notebook outputs
   with Kaggle **Save Version**.

The notebook installs dependencies in a separate environment and runs training in
subprocesses. It avoids `ensurepip` and targets the environment with the image's existing pip.
Dependencies, code and base-model caches stay in a temporary runtime, outside saved outputs.
ZIPs and Kaggle-extracted directories are supported; package and per-file hashes verify
extracted contents. Subprocesses share `RUN_TIME_LIMIT_SECONDS` (1,800 by default).
Downloads are public packages and the pinned model/tokenizer;
no tracking service or automatic publishing is configured.

## Outputs and acceptance

Outputs include `report.json`, `metrics.jsonl`, an `adapter/` directory and complete
checkpoints. `metrics.jsonl` appends train, validation and end events, including updates
written before a timeout. Reports record package versions, hashes, losses, validation
history, duration and memory peaks.
Fixed validation losses are a numerical smoke check, not a quality benchmark.
The test split is checked for integrity/token length, never used for training or selection.

For behavioral evidence, the notebook can run `evaluate.py` after training. It generates
base and adapter answers on a deterministic stratified sample of the validation split and
writes `answers.jsonl`. Download that file and run the local scorer, which uses VERA's
production `GeneratedAnswer` and `validate_and_repair` contract:

```bash
uv run python finetuning/score.py --dataset /path/to/vera-domain-v4.zip \
  --contract /path/to/runtime-contract.json \
  --answers /path/to/answers.jsonl --output /path/to/scores.json
```

The score report compares JSON validity, schema validity, `out_of_scope` decisions,
claim-status behavior (unavailable and simulated cases), citation failures, exact
quote use and memory-citation violations by task. This measures behavior on supplied
evidence, not latent cybersecurity knowledge. Use the test split only after selecting
a configuration. A completed preview with its charts and residual failures is recorded
in [the 2026-10-28 experiment report](finetuning-preview-20261028.md).
The resumed run to step 400, together with the 40-case perturbed evaluation that tests
generalization beyond the training templates, is recorded in
[the 2026-11-01 run report](finetuning-run-20261101.md).

For a larger validation comparison that excludes earlier behavioral cases and the
fixed loss-monitoring sample, prepare a deterministic, task-balanced pack:

```bash
uv run python finetuning/prepare_eval_pack.py \
  --dataset .vera/finetuning/v3-english-20261102b/aligned/vera-domain-v3-english-candidate.zip \
  --contract .vera/finetuning/v3-english-20261102b/bundle/runtime-contract.json \
  --previous-answers .vera/finetuning/kaggle-preview-20261028-103035/resume-results/vera-eval-resume-20261029-104525/answers.jsonl \
  --previous-dataset .vera/finetuning/v2-eval-20261101/aligned/vera-domain-v2-candidate.zip \
  --previous-contract .vera/finetuning/v2-eval-20261101/bundle/runtime-contract.json \
  --exclude-loss-sample 24 \
  --per-task 20 \
  --seed 20261102 \
  --max-new-tokens 768 \
  --output .vera/finetuning/v3-english-20261102b/evaluation-pack-20-per-task
```

The 220-case selection (20 per task) reports exact-target overlap and duplicates:
40 targets are seen in training and 38 rows duplicate a target within the pack. The
smaller 110-case selection has 20 overlaps and 18 duplicates; it was run on Kaggle with
the v3 English-only candidate on 2026-11-07. The base produced 97/110 schema-valid
answers and 43 strict passes; the adapter produced 110/110 and 109 strict passes (89/90
on rows whose exact target is unseen). The adapter's only failure is a non-verbatim quote
in `graph_evidence`. Results and caveats are in
[the fine-tuning report](finetuning-run-20261101.md#english-only-evaluation-2026-11-0607).
Both selections are validation slices, not independent tests; they do not change targets,
authorize training or use the held-out test split. Prompt alignment preserves all targets,
so this candidate is not ready for training until labels are reviewed and corrected. Use a
fresh output directory because the packer never overwrites an existing selection.

The same packer can select from the held-out test split. Test packs do not reuse
validation-only exclusions, so prior-answer and loss-sample flags are rejected:

```bash
uv run python finetuning/prepare_eval_pack.py \
  --dataset .vera/finetuning/v3-english-20261102b/aligned/vera-domain-v3-english-candidate.zip \
  --contract .vera/finetuning/v3-english-20261102b/bundle/runtime-contract.json \
  --split test \
  --per-task 20 \
  --seed 20261107 \
  --max-new-tokens 768 \
  --output .vera/finetuning/v3-english-20261102b/evaluation-pack-test-20-per-task
```

The 220-case test selection has no ID overlap with the validation pack. Targets are still
shared with training in `memory_only` (20) and `scope_boundary` (20), because those tasks
have a single target in the dataset; 38 rows duplicate another target within the pack.
That remains a template limitation, not a split problem. The selection was run locally
on 2026-11-08: the base reached 86/220 strict passes, the adapter 219/220, and its only
failure was a non-verbatim supporting quote. Template reproduction persists on this split
(209/220 exact target summaries, 169/180 on unseen targets). Results are in
[the fine-tuning report](finetuning-run-20261101.md#test-split-pack-220-cases).
A consolidated view of purpose, evidence, serving and limits is in
[the adapter assessment](finetuning-adapter-assessment.md).

For a future independent pack, pass `--require-independent-targets` to
`prepare_eval_pack.py`. It excludes canonical answer JSON already present in training
and duplicate answer targets within the selected pack, in addition to the existing
source/group/entity leakage checks. The current v3 candidate cannot satisfy this option
for all tasks; new, independently authored and reviewed targets are required. Exact
JSON novelty does not by itself establish semantic diversity or factual accuracy.

For inference-only comparison, `finetuning/kaggle_eval.py` runs preflight followed by
base/adapter generation on a private Kaggle T4 x2 kernel. Its uploaded code bundle contains
only dataset, inference and evaluation modules; it does not include the training entrypoint.
The script writes answers and preflight output under `/kaggle/working`, while dependencies
and model caches stay under `/kaggle/temp`.

A full run checkpoints every 50 updates and at completion. To resume, preserve a complete
`checkpoint-*`, set `FULL_RESUME` and choose a new `FULL_OUTPUT`.
Data, prompt, model revision, mode and accumulation must match.

Compare base and adapted models with identical validation contexts and decoding settings.
Check JSON, citations, relevance, missing-data behavior, scope and actual VERA review outcomes.
Use the held-out test only after selection; decreasing loss is not deployment approval.

The output is a LoRA adapter, not a replacement MTP GGUF. Merge it with the same pinned
Hugging Face base, convert with a compatible llama.cpp version, then revalidate the
served artifact. Conversion and deployment are separate, manual steps.

## References

- [Qwen3.5 text-only architecture and loading](https://huggingface.co/docs/transformers/main/en/model_doc/qwen3_5)
- [Model checkpoint](https://huggingface.co/Qwen/Qwen3.5-4B)
- [Model-specific training caveats](https://unsloth.ai/docs/models/qwen3.5/fine-tune)
- [FP32 architecture guard](https://github.com/unslothai/unsloth/blob/main/unsloth/models/loader.py)
