# Kaggle pilot and dataset

The standalone [notebook](../finetuning/kaggle.ipynb) targets structured cybersecurity
answer generation with **Qwen/Qwen3.5-4B**.
A five-update FP32 compatibility pilot and a full v4 epoch completed on two Kaggle T4
GPUs. The full epoch peaked at 9.89 and 10.15 GiB of PyTorch-allocated VRAM. This
establishes execution compatibility and full-epoch fit for v4, not quality improvement.
It does not train ReAct decisions, tool use or retrieval policy.

## Dataset

The retained v1 dataset is incompatible with the current chat prompt and remains
local-only. The **v4 dataset** replaces it for the next experiment: it is rebuilt
against the current `SYSTEM_PROMPT` and `generation_prompt`, and it closes the gaps that
the step-400 adapter exposed. Dataset card:
[domain dataset v4](domain-dataset-v4.md).

`vera-domain-v4.zip` and `.vera/datasets/vera-domain-v4/` are local, ignored artifacts.
They contain **5,406 training, 686 validation and 720 test** conversations (6,812 total),
plus 160 controlled event replays. Targets combine pinned public MITRE ATT&CK and CISA KEV
records, 122 repository-bundled official documents and synthetic analyst scenarios. They
are not expert SOC decisions. Upstream revisions, hashes and license notices are preserved
in the archive.

| Gap in v1/v3 data | v4 coverage |
| --- | --- |
| Prompt drift | both messages come from the current runtime prompts; the manifest records `sha256(SYSTEM_PROMPT)` |
| One-sided scope | in-domain, unavailable-but-in-domain, social, clarification and `out_of_scope` families |
| Social handled as security | `social_conversation` and `clarification` targets carry no claims and set `out_of_scope=false` |
| Alerts only 0/1 | train alert counts `{0: 5316, 1: 40, 2: 30, 3: 20}`; validation and test cover 0-3 |
| No multi-turn | 320 training follow-up conversations with resolved question, subject and search query |
| No language variants | Italian, Spanish, German and French questions answered in the configured English |
| Entity/title drift | targets quote evidence verbatim and name the entity each record concerns |

The reviewed package was signed off on 2026-11-11 (`accept` 80/80) and an authorized
derivative now sets `human_reviewed` and `training_authorized` to true. Deployment is
still not authorized, and the GPU launch remains a separate explicit step.

| Artifact | SHA-256 |
| --- | --- |
| Reviewed manifest | `485bd329a5c3409929b17f7618b3cd95e0a35bcbccc8a29a7dd863437823d98d` |
| Authorized manifest | `04d18fbb7db8b35571bff755f43ad3eadadbc3c30d01d3f54426bfbcf27feb10` |
| Authorized package | `6a3b5aa90252cecabc0560f2376929c8b4d0f7b38f85f580e98af011a1c0cd24` |
| Authorized dataset archive | `f0e288f4bf78be8a351f3a7f403a7fe0c870c6137af44c2b1b7f0bf611997142` |
| Authorized Kaggle bundle | `f13248e11a6a5d0f99ac905fd8ee50d89de98f2f0884a41c2cb1b1928fa8ce48` |

The authorized derivative preserves the reviewed data shards byte-for-byte and adds
`AUTHORIZATION.md` with the reviewed hashes and reviewer. The token receipt is rebound
to the authorized manifest: maximum 2,462 tokens, no truncation, assistant-only loss
boundary verified.

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
The v4 epoch is verified on T4 x2; memory fit and cost for other workloads remain
unverified.

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

### v4 training result (2026-11-12)

The authorized v4 dataset completed **one full epoch**: 676 optimizer updates over
5,406 examples with accumulation 8 and `max_length` 2,560. It ran in two Kaggle
sessions: the first saved `checkpoint-000350` and was stopped by its wall-clock budget
at step 387; the second resumed from that checkpoint for the remaining 326 updates.
The resumed segment took **35,093 s (9.75 h)** of training. The first subprocess ran
11.4 h before its budget expired, so the epoch cost about 21 h of T4 x2 time across
the two sessions, including the 37 updates discarded at the first timeout.

| Metric | Value |
| --- | --- |
| Optimizer updates | 676 / 676 |
| Training examples | 5,406 |
| Peak allocated VRAM | 9.89 / 10.15 GiB |
| Validation loss | 0.0177 (350) → 0.0084 (600) → 0.0146 (676) |
| Final training loss | 0.0023 |
| Truncation / warnings | none |

The final adapter (`adapter/adapter_model.safetensors`, 41 MB) has SHA-256
`927d384c922e8523000ce8b9445de03e6650dde17098f548e07f4e1065151b4b`. It is a local
artifact and is not committed.

Validation loss is saturated and training loss is near zero: the epoch fits the
generation templates and does not demonstrate general capability. The test split was
not used for selection and deployment remains unauthorized. A behavioral evaluation
on validation (scope, unavailable evidence, citations and exact quotes) is the next
gate; loss alone is not evidence of quality.

### v4 behavioral result (2026-11-12)

The final adapter was evaluated once on a fixed validation pack: 54 examples,
3 per task across 18 tasks, seed 20261102, `max_new_tokens` 768, selection SHA-256
`54eee0b8d9b7984739af79abf7663c7dc8921d206dcbd787902ba0611259fc7f`. The pack
excludes the 24 validation parent IDs used for loss monitoring, and the test split was
not used. Each example was generated with the base model and with the adapter, so the
108 answers are paired. Generation took 3,147 s (52.5 min); the kernel took 1 h 34 min
including dependency install and model load.

| Metric | Base | Adapter |
| --- | ---: | ---: |
| Valid JSON | 90.7% | 98.1% |
| Valid schema | 88.9% | 98.1% |
| Correct scope | 87.0% | 98.1% |
| Mean status recall | 0.719 | 0.981 |
| `unavailable` present (12 expected) | 8/12 | 11/12 |
| Citation failures (schema-valid rows) | 8.3% | 0% |
| Exact-quote claims | 98.0% | 100% |
| Memory-citation violations | 0 | 0 |
| Mean output tokens | 399 | 190 |
| Mean seconds per answer | 36.6 | 21.7 |

The adapter's only schema failure was a `social_conversation` reply written as prose
instead of JSON. That target was seen in training, so the failure is not explained by
unseen-task difficulty. The `unavailable` miss used `system_inference` for "No local
record of DNS tunnelling was established"; the text states absence, but the status is
wrong. Base failed schema on 6/54 examples, including all three `stream_triage` cases,
and had citation failures in `current_status` and `graph_evidence`.

Caveats: 12/54 targets were seen in training, 5 rows duplicate another target within
the pack, and the targets are synthetic. On the 42 rows whose targets were unseen, the
adapter still produced valid schema and scope in 42/42 with status recall 0.976 (base
85.7%, 85.7%, 0.653). That is evidence of contract retention on this pack, not
generalization: validation loss is saturated and the split is template-adjacent.
Deployment remains unauthorized.

### v4 held-out test result (2026-11-13)

After the adapter was frozen, the held-out test split was used once: 54 examples,
3 per task, seed 20261113, selection SHA-256
`da626b6a67829cb36c649cfa376d07fea3343b023af5a27203831b8480f0612c`. The pack
shares 12/54 targets with training and contains 5 duplicate rows, so it is a held-out-row
test, not an independently authored target set. Generation took 2,904 s (48.4 min);
the kernel took 53 min including install and model load.

| Metric | Base | Adapter |
| --- | ---: | ---: |
| Valid JSON | 92.6% | 100% |
| Valid schema | 83.3% (45/54) | 100% |
| Correct scope | 81.5% | 100% |
| Mean status recall | 0.667 | 0.963 |
| `unavailable` present (12 expected) | 6/12 | 10/12 |
| Citation failures (schema-valid rows) | 13.3% | 0% |
| Exact-quote claims | 88.1% | 100% |
| Memory-citation violations | 0 | 0 |
| Mean output tokens | 386 | 183 |
| Mean seconds per answer | 34.7 | 19.1 |

On the 42 rows whose targets were unseen, the adapter produced valid schema and scope
in 42/42 with status recall 0.952. The aggregate hides the blocker: `unavailable_concept`
is only **1/3**. In two cases the supplied record concerns a different entity (Overwrite
Process Arguments for "supply chain attack"; Stripped Payloads for "firmware implant"),
and the adapter cites it as `supported_fact` instead of returning `unavailable`. One
answer even says the record is a different entity and still cites it. The base also fails
these cases, but its answer is schema-invalid in one; the adapter makes the same
grounding error schema-valid, so it can pass format checks while asserting the wrong
record.

The test split has now been used once for the final evaluation and must not be reused
for tuning. This result does not meet the production gate: format and scope improve, but
abstention on unrelated evidence is a core safety rule. Deployment remains unauthorized;
the next step is a runtime relevance/abstention guard (or targeted data), followed by a
fresh independent review, not another epoch on the same templates.

### v4 runtime guard and merged artifact (2026-11-13)

The held-out test exposed a runtime rule, not only a data gap: off-topic evidence was
accepted as `supported_fact`. A runtime guard now checks the evidence set after
generation. If no supplied knowledge record names the question subject, claims that cite
a knowledge record are degraded to `unavailable` during repair. Memory, stream and
simulated rows are ignored, and fallback records never qualify; identifiers match
exactly, while a concept matches only when all its meaningful tokens occur in one name or
alias. The guard runs in `validate_and_repair`, the validation node and the local scorer.
On all 1,406 gold targets from validation and test (1,737 `supported_fact` claims) it
degraded nothing; the run is recorded in `guard-regression-v4.json` (SHA-256
`dd46677ec6eb6165f533dd6ef493f21233da9e7a0d21030dec076f9905c78586`).

Guarded scoring reuses the same answers, so the test split was not run again:

| Metric | Adapter | Adapter + guard |
| --- | ---: | ---: |
| Valid schema | 54/54 | 54/54 |
| Correct scope | 100% | 100% |
| Mean status recall | 0.963 | 1.000 |
| `unavailable` present (12 expected) | 10/12 | 12/12 |
| Relevance failures | 2/54 | 0/54 |
| Citation failures | 0% | 0% |

On validation the guard never intervened: schema 53/54 (one invalid JSON), status recall
0.981, `unavailable` 11/12, `unavailable_concept` 2/3. The guard closes the measured
failure on test; it does not add capability that the validation pack still lacks.

For serving, the adapter was merged into the pinned base (PEFT on
`Qwen3_5ForCausalLM`, bf16), converted to GGUF BF16 (SHA-256
`053007ea347f71bd132c55f2d086a260c25a59829da78018506dc68c4dd49f03`) and quantized to
Q6_K (3.2 GB, SHA-256
`872292b16661ab123e51f588d857592c0eab0d1d74aae0615d1310e954ec21a6`). The served
artifact is the merged Q6_K file, without `--lora`. `scripts/check-local-model.py`
passed 4/4 checks on it, recorded in `local-model-checks-v4-merged-guarded.json`
(SHA-256 `e41448722c8a3efd6a1ff942905bdc0601e56b51efac004a0cde9e21dd5d3de6`). That
check covers four cases, not the production gate.

Deployment remains unauthorized. The next gate is a real human review of an independent
40-answer pack generated by the merged runtime: one verdict per case, signoff bound to
the pack hash, then explicit authorization. The held-out test split stays consumed and is
not reused for tuning or selection.

## Prepare and run

Build and audit the v4 dataset without loading weights, then package it:

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
Use `--max-length 2560` for this dataset; lower budgets either fail or require dropping
multi-alert rows, which is not permitted. Before training, run the human review pack
described in the [dataset card](domain-dataset-v4.md#human-review); a green audit alone
does not authorize training.

1. Import the notebook into Kaggle. Attach a private dataset containing
   `vera-domain-v4.zip` and `vera-kaggle-training.zip`; these exact filenames are
   required. Upload the authorized archive as `vera-domain-v4.zip` and the authorized
   bundle as `vera-kaggle-training.zip`. Do not upload credentials, databases or
   company telemetry.
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
