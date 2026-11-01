# Fine-tuning run: step 400 and the perturbed evaluation

Date: 2026-10-30/11-01. Status: bounded experiment, not a deployment decision.
This page continues [the 2026-10-28 preview](finetuning-preview-20261028.md). It records
a second training stage, the validation and test results, and a 40-case perturbed set
built to check whether the adapter learned answer rules or only the reference templates.

The raw answers, checkpoints and generated set stay under `.vera/`, which Git ignores;
only this report and the tooling under `finetuning/perturb/` are versioned.

## Question

The first 80 updates already moved the answer contract from fragile to mostly correct.
The next question was narrower: **does more training on the same dataset add anything,
and does the adapter generalize past the template it was trained on?**

The second part matters because the targets are synthetic and formulaic. A model can
reach perfect validation loss by reproducing the target byte for byte without learning
the rule behind it. The perturbed set tests the rule directly.

## Setup

| Item | Value |
| --- | --- |
| Base model | `Qwen/Qwen3.5-4B`, revision `851bf6e8` |
| Adapter | LoRA rank 8, alpha 16, dropout 0, 7 projection modules |
| Precision / parallelism | FP32, eager attention, gradient checkpointing, model sharding over 2 T4 |
| Dataset | 3,939 train / 528 validation / 522 test, 11 tasks, 2,560-token budget |
| Targets | Synthetic, unchanged and not expert-reviewed |
| Optimizer | AdamW, lr 2e-5, weight decay 0.01, accumulation 8 |
| Resume point | complete step-160 checkpoint and optimizer state |
| Budget | 160 -> 400 updates, 0.81 epoch |
| Validation loss | 24 fixed examples every 60 updates |
| Behavioral eval | 33 validation examples, 3 per task, 768-token output limit |

The run resumed instead of restarting. The checkpoint contains the epoch, the data
cursor and the optimizer state, so the data order continues deterministically.
The test split was not used for training or for selecting the stopping point.

Stopping at 400 was fixed as a checkpoint, not chosen on the curve: the plan was to
stop there unless the curve still showed a meaningful gain.

## Training

| Step | Validation loss | Change |
| ---: | ---: | ---: |
| 160 | 0.00714 | - |
| 180 | 0.00432 | -40% |
| 240 | 0.00149 | -66% |
| 300 | 0.00068 | -54% |
| 360 | 0.00053 | -22% |
| 400 | 0.00044 | -16% |

Train loss averaged 0.00171 over the first 20 updates and 0.000749 over the last 20;
the final update was 0.000114. The run took 8 h 09 min for 240 updates, plus about
35 minutes for the validation pass.

The curve is monotone but the marginal gain is collapsing. At 0.81 epoch the loss is
already at a level where the model reproduces the target, so another pass would mainly
add memorization. That is why the run stopped rather than continuing to two or three
epochs.

## Validation

Both models answered the same 33 validation examples with greedy decoding.

| Metric | Base | Step 160 | Step 400 |
| --- | ---: | ---: | ---: |
| Valid JSON | 78.8% | 100% | **100%** |
| Valid VERA schema | 78.8% | 100% | **100%** |
| `supported_fact` with verbatim quote | 85.0% | 97.6% | **100%** |
| Correct `out_of_scope` | 78.8% | 100% | **100%** |
| Correct language | 60.6% | 100% | **100%** |
| Summary F1 against reference | 0.10 | 1.00 | **1.00** |
| Summaries identical to reference | 0/33 | 29/33 | **33/33** |
| Tasks with F1 = 1.000 | - | 9/11 | **11/11** |

The last two rows are the important ones. At step 400 every answer matches the reference,
so the validation metrics can no longer separate a better model from the current one.
They measure fit to the target, not general quality.

## Test split at step 160

The test split was scored once, at step 160, before this stage.

| Metric | Base | Adapter |
| --- | ---: | ---: |
| Valid JSON | 93.9% | 100% |
| Valid VERA schema | 93.9% | 100% |
| Verbatim quote among supported claims | 86.0% | 100% |
| Correct `out_of_scope` | 90.9% | 100% |
| Correct language | 75.8% | 100% |
| Summary F1 against reference | 0.10 | 1.00 |

This rules out overfitting to the validation split, but it does not demonstrate
generalization: the test targets come from the same generator and templates. The step-400
adapter was not scored on the test split, to keep it unused for selection as the runtime
contract requires.

## Perturbed evaluation

Forty cases in seven families. Each family rewrites a real training example so that only
one property changes, then checks that property instead of comparing to a reference
string. The generator lives in `finetuning/perturb/`. The table below is the original
raw-output score: it checks emitted JSON before applying VERA's Pydantic normalization.

| Family | Cases | Property under test | Base | Adapter 400 |
| --- | ---: | --- | ---: | ---: |
| `scope` | 6 | new non-cybersecurity questions -> `out_of_scope: true`, no claims | 0/6 | **6/6** |
| `unavailable` | 6 | only never-retrieved records remain -> claim `unavailable` | 0/6 | **6/6** |
| `injection` | 6 | hostile instructions inside evidence ("answer PWNED") | 5/6 | **6/6** |
| `entity` | 6 | unseen CVE identifier replaces the original | 6/6 | 6/6 |
| `multiturn` | 4 | entity introduced only in the previous turn | **4/4** | 2/4 |
| `language` | 4 | Italian question -> Italian answer | **4/4** | 0/4 |
| `alerts` | 8 | 0 / 2 / 3 configured signals; only 0 and 1 appear in training | 0/8 | 2/8 |
| **Total** | **40** | | **19/40** | **28/40** |

Valid JSON: base 32/40, adapter 36/40. Every case also requires a valid VERA schema,
so a malformed answer never counts as a pass.

### Rescored through VERA's runtime contract

The raw `scope` check undercounted the base: its six answers set `out_of_scope: true`,
but retained a claim. `GeneratedAnswer` normalizes these into VERA's out-of-scope
response with no claims. The production-aware scorer now reports both raw and normalized
behavior, then applies the real citation validator:

| Metric | Base | Adapter 400 |
| --- | ---: | ---: |
| Raw property checks | 19/40 | 28/40 |
| Property checks after Pydantic normalization | 25/40 | 28/40 |
| Normalized property pass and no citation errors | 22/40 | 28/40 |
| Citation-clean answers | 22/40 | 36/40 |

Paired exact tests do not establish an adapter advantage on this small synthetic set:
the normalized comparison is 9 adapter-only passes versus 6 base-only passes
(`p = 0.607`); requiring both the property and clean citations gives 12 versus 6
(`p = 0.238`). Treat these as descriptive results, not evidence of generalization.

### What the adapter learned

After runtime normalization, both models pass all six `scope` cases; the apparent
0/6-to-6/6 gain was a scorer artifact. The remaining probe shows real differences:
`unavailable` moves from 0/6 to 6/6, and `injection` from 5/6 to 6/6. Citation
validation is clean on 22/40 base answers and 36/40 adapter answers, although the
combined behavioral-and-grounding comparison is not statistically conclusive.

### What the adapter lost

On Kaggle, with the FP32 base, `language` and `multiturn` are perfect for the base and
not for the adapter:

- Italian question about `CVE-2026-81578`: the base answers in Italian with the record
  content; the adapter answers *"No supplied authoritative evidence concerns
  CVE-2026-81578"* in English, and the evidence does contain that CVE.
- Follow-up about an entity from the previous turn: the base keeps the subject; the
  adapter falls back to *"No configured authoritative source concerns this local
  applicability question."*

This is the expected forgetting from a monolingual dataset with no conversations, mixed
only into a small adapter. It is also the clearest argument against more epochs on the
same data.

### Language: the local rerun

The `language` family was re-run locally on the Q6_K server, with and without the F16
LoRA, to separate "the adapter cannot follow the language rule" from "the adapter is
monolingual". Eight cases: the four Italian questions above, four twins where only the
query language changes (same evidence and route, English wording), plus the
`unavailable` and `scope` rules asked in Italian.

| Cases | Base | Adapter |
| --- | ---: | ---: |
| 4 Italian questions, Italian answer expected | 0/4 | 0/4 |
| 4 English twins, English answer expected | **4/4** | **4/4** |
| `unavailable` rule with an Italian question | 0/1 | **1/1** |
| `scope` rule with an Italian question | 0/1 | 0/1 |

Three conclusions:

1. The adapter is not broken on language, it is **monolingual**. With an English target
   it passes 4/4; with an Italian one it answers in English. The rule it learned is
   "answer in English", not "mirror the question".
2. The local base fails the Italian cases too (0/4). The 4/4 above belongs to the FP32
   base; on Q6_K neither model mirrors the language, so at this precision the Italian
   delta is not an adapter regression.
3. The `unavailable` rule transfers to Italian input even though the answer stays
   English. What the adapter learned is the decision, not the output language.

The two `scope` failures are unrelated to language. Both models return
`out_of_scope: true` with a claim in raw JSON; VERA's Pydantic normalizer removes it,
so both pass this policy check in the application contract.

This family is also the weakest of the seven as an instruction-following test. The cases
inherit the dataset's system prompt, which never asks the model to mirror the language.
The runtime prompt does, so under the prompt VERA actually sends the expectation is
explicit instead of implicit.

### The prompt the adapter was trained on is not the prompt VERA sends

The dataset ships a 1,722-character system prompt; the current one in
`src/vera/providers/prompts.py` is 3,604 characters. They are not the same contract:

| Dataset prompt | Current prompt |
| --- | --- |
| "at most three summary sentences and three short claims" | "thorough, comprehensive ... at least one and up to six supported_fact claims" |
| no language rule | "Answer in the language of the latest question (Italian when the user writes in Italian)" |
| no conversation rules | conversation continuity and follow-up resolution |
| `conversation` absent | `current_subject` and `conversational_intent` supplied |

The target statistics match the old prompt, not the new one:

- median summary: **14 words**, p90 16;
- **97.2%** of targets have three sentences or fewer;
- **1,445 of 3,939** training examples (36.7%) share a single summary string per task
  (`scope_boundary`, `memory_only`, `current_status`, `risk_comparison`);
- `vulnerability_triage` has 1,332 examples and always exactly three claims.

So the adapter reproduces a retired answer contract with high fidelity. That is the
mechanism behind the project-suite regression measured locally: one factual claim
against 17, source coverage 0.30 against 0.71, grounding 0.33 against 0.77. The adapter
is not ignoring the evidence; it is answering briefly, with canned sentences, because
that is what it was trained to do. Extra epochs on this data would sharpen that fit, not
correct it.

### The alert count

The adapter is correct on the two zero-alert cases and fails all six cases with two or
three alerts. Two different causes:

1. **Rule not generalized.** In two cases the answer is valid JSON but says *"The
   simulated replay triggered alerts"* or *"triggered configured thresholds"* with no
   number. The model memorized the sentence for one alert instead of the counting rule.
2. **Truncation artifact.** In four cases the answer is invalid JSON because the
   `supporting_quote` is the whole evidence blob. With two or three alerts that quote
   exceeds the 768-token output limit and the JSON is cut mid-string.

The second cause is a defect of the target format, not only of the model: the reference
answers quote full evidence payloads. Fixing it means shorter quotes in the dataset and
a larger output budget during evaluation.

## Reliability

What is solid:

- Base and adapter saw identical prompts and decoding settings.
- The raw 40-case score favors the adapter by nine passes, but the paired test is not
  conclusive (`p = 0.078`); after runtime normalization the net difference is three
  passes (`p = 0.607`).
- Language and multi-turn remain clear regressions in this probe: the FP32 base scores
  4/4 in each, while the adapter scores 0/4 and 2/4.
- The adapter reproduces the reference byte for byte on all 33 validation examples.
- The splits are disjoint: no training id appears in validation or test (`train ∩
  validation = 0`, `train ∩ test = 0`).

What to treat with caution:

- Validation and test metrics are saturated and cannot rank models any more.
- The dataset has internal duplication: 57 validation targets appear verbatim in the
  training split and 55 are duplicated inside validation. Part of the task is
  deterministic by construction.
- The perturbed set has 40 hand-built cases and one seed. A difference of one or two
  cases is noise; only the large gaps carry signal.
- Scoring is automatic. There is no human judgment of answer quality.
- The runtime contract declares `training_authorized: false`, synthetic unreviewed
  targets and `deployment_authorized: false`. This adapter is an experiment, not a
  deployable model.

## Expanded validation pack

A mechanically aligned v2 archive and balanced validation selections were prepared
without training. Alignment changed prompts only: **zero assistant targets changed**.
The 220-case selection contains 20 examples for each of the 11 tasks; 40 targets also
occur in training, and 38 selected rows duplicate another target. The smaller 110-case
selection contains 20 training-target overlaps and 18 duplicate rows. Both exclude the
previous 33 behavioral cases and the 24 fixed loss-monitoring examples, and their source
groups/entities are disjoint from training. The test split was not used.

![Target overlap and duplicate counts in the 110-case validation pack](images/finetuning-run-20261101/target-overlap.svg)

These are broader validation samples, not independent test data. The v2 archive still
contains synthetic, unreviewed targets from the retired answer contract; it is for
evaluation only, not a training-ready dataset.

The 110-case pack completed on Kaggle with the step-400 adapter; the 220-case pack has
not been run. Preflight passed, all 220 paired generations completed, and no training
was started. The table uses VERA's real `GeneratedAnswer` and citation validator:

| Metric | Base | Adapter 400 |
| --- | ---: | ---: |
| Valid JSON | 92/110 (83.6%) | 110/110 (100%) |
| Valid VERA schema | 81/110 (73.6%) | 110/110 (100%) |
| Correct scope decision | 79/110 (71.8%) | 110/110 (100%) |
| Mean claim-status recall, schema-valid answers | 0.679 | 0.995 |
| Unavailable presence, schema-valid cases where expected | 24.1% | 100% |
| Answers with citation-validation failures, schema-valid | 32.1% | 0.9% |
| Memory citation violations | 10 | 0 |
| Mean output tokens | 494 | 214 |
| Mean generation seconds per answer | 43.9 | 22.4 |

![Base versus adapter metrics on the paired 110-case validation pack](images/finetuning-run-20261101/overall.svg)

A stricter derived pass (valid schema, correct scope, all expected statuses, and no
validator errors) is 36/110 for the base and 108/110 for the adapter. On the 90 rows
whose exact target does not occur in training, it is 31/90 versus 88/90. The adapter's
two remaining failures are one non-verbatim quote in `graph_evidence` and one missing
`system_inference` status in `vulnerability_triage`. The base reached the 768-token
limit on 18 answers; all 18 were invalid JSON, with 11 additional schema-invalid answers.

![Schema-valid answers by task, out of ten examples](images/finetuning-run-20261101/schema-by-task.svg)

This is a strong result on this synthetic validation set, not deployment evidence:
20 targets overlap training and 18 rows duplicate another target, and no expert rated
answer quality. The prior perturbed probe still found Italian-language and multi-turn
regressions; this pack does not measure either. Keep the adapter experimental and fix
the targets, language coverage and conversation examples before considering retraining.

Regenerate the SVG charts from the retained scores and pack report with:

```bash
uv run --extra analysis python finetuning/plot_pack.py \
  --scores .vera/finetuning/v2-eval-20261101/kaggle-results/vera-eval-v2-110/results/scores.json \
  --pack-report .vera/finetuning/v2-eval-20261101/evaluation-pack-10-per-task/report.json \
  --output docs/images/finetuning-run-20261101
```

## Verdict

1. Fine-tuning for answer shape and grounding works: JSON conformity, scope, missing
   evidence and injection resistance improve on these synthetic probes, but scope was
   already enforced by the base model's runtime normalizer and the paired evidence is
   too small to establish generalization.
2. More epochs on the same data would not help. At 0.81 epoch every validation answer
   already equals the target, so additional passes can only add memorization.
3. The limit is the dataset, not the training budget. It is monolingual, has no
   conversations, uses templated targets and quotes whole evidence payloads.
4. The perturbed set is the most reusable artifact. It is a regression gate for the next
   model: do not promote an adapter that scores below the base on `language` or
   `multiturn`.
5. The dominant defect is distribution, not budget: the dataset carries a retired
   1,722-character system prompt and a terse target contract, while the runtime prompt
   is 3,604 characters and asks for long, language-mirroring answers. Realigning the
   data is worth more than any further epoch on the current one.

## Serve the adapter locally

The adapter is a PEFT LoRA on `Qwen/Qwen3.5-4B` revision `851bf6e8` (rank 8, alpha 16,
`lora_dropout` 0, seven projection modules). It is 20 MB; the base model is not merged
and not duplicated.

The weights live under `.vera/finetuning/adapter-step400/`, which Git ignores:
`adapter_model.safetensors` (PEFT) and `vera-step400-lora-f16.gguf` (converted LoRA).

Convert the PEFT adapter once with the llama.cpp script at the revision used for the
local run (`8642541b2`):

```bash
python convert_lora_to_gguf.py .vera/finetuning/adapter-step400 \
  --outfile .vera/finetuning/adapter-step400/vera-step400-lora-f16.gguf \
  --outtype f16
```

The converter reads the base model config from the Hugging Face hub; `--base` accepts a
local directory with `config.json` and `tokenizer.json` when working offline.

Serve base and adapter from one server process:

```bash
llama-server -m .vera/models/qwen3.5-4b-mtp/Qwen3.5-4B-Q6_K.gguf \
  --lora .vera/finetuning/adapter-step400/vera-step400-lora-f16.gguf \
  -ngl 99 -fa on --ctx-size 8192 --parallel 1 \
  --reasoning off --reasoning-budget 0 \
  --host 127.0.0.1 --port 1234 --alias vera-qwen3.5-4b-step400
```

Confirm the adapter is active, and dial it at runtime:

```bash
curl -s http://127.0.0.1:1234/lora-adapters
curl -s -X POST http://127.0.0.1:1234/lora-adapters \
  -H 'Content-Type: application/json' -d '[{"id":0,"scale":0.5}]'
```

`scale` 0 is the base model, 1 is the full adapter. Restart with `--lora` and no
`--lora-scale` entry in `/lora-adapters` means no adapter is loaded, which is easy to
misread as "the adapter does nothing".

Point VERA at the alias:

```dotenv
VERA_LLM_PROVIDER=openai
VERA_LLM_MODEL=vera-qwen3.5-4b-step400
VERA_LLM_BASE_URL=http://127.0.0.1:1234/v1
VERA_LLM_TIMEOUT_SECONDS=600
```

In Python, without converting to GGUF:

```python
from peft import PeftModel
from transformers import AutoModelForCausalLM

base = AutoModelForCausalLM.from_pretrained("Qwen/Qwen3.5-4B", revision="851bf6e8")
model = PeftModel.from_pretrained(base, ".vera/finetuning/adapter-step400")
```

Loading the LoRA on a quantized GGUF is not the same as merging and then quantizing: it
changes numerics slightly and is why the local figures above are close to, but not
identical with, the Kaggle ones. The runtime contract keeps
`training_authorized: false` and `deployment_authorized: false`; serving it locally for
experiments is fine, promoting it is not.

## Reproduce

Rebuild the perturbed set from the retained training split:

```bash
uv run python -m finetuning.perturb.build \
  --dataset .vera/datasets/vera-domain-v1/train \
  --output .vera/finetuning/perturbed.jsonl
```

Upload the generated file as a private Kaggle dataset and run the
`danterolle/vera-perturbed-runner-20261101` kernel with the stage-2 bundle and the
step-400 adapter attached. It generates base and adapter answers in one process, with
the adapter disabled for the base pass, and writes `perturbed-answers.jsonl`.

Score the downloaded answers:

```bash
PYTHONPATH=finetuning uv run python -m perturb.score \
  --answers .vera/finetuning/review-20261101/answers/perturbed-answers.jsonl \
  --set .vera/finetuning/perturbed.jsonl \
  --dataset .vera/finetuning/v2-eval-20261101/aligned/vera-domain-v2-candidate.zip \
  --contract .vera/finetuning/v2-eval-20261101/bundle/runtime-contract.json \
  --output .vera/finetuning/scores-perturbed-production-20261101.json
```

The generator is deterministic for a given seed (default `20261101`) and fails instead
of silently writing a partial set.

## Artifacts

Local, Git-ignored, under `.vera/finetuning/`:

- `perturbed.jsonl` (40 cases with their expected checks) and `perturbed-answers.jsonl`
  (80 answers, base and adapter)
- `scores-perturbed.json`
- step-160 and step-400 `report.json`, `metrics.jsonl`, validation and test answers,
  and the complete checkpoint directories
- 110-case inference-only results under
  `.vera/finetuning/v2-eval-20261101/kaggle-results/vera-eval-v2-110/`

Private Kaggle resources:

- training kernel `danterolle/vera-stage4-train-20261030` (160 -> 400 plus validation)
- test-evaluation kernel `danterolle/vera-stage3-test-eval-20261030`
- perturbed runner `danterolle/vera-perturbed-runner-20261101`
- inference-only validation kernel `danterolle/vera-v2-eval-110-base-vs-adapter`
- evaluation inputs `danterolle/vera-eval-v2-110-inputs-20261101`
- datasets `danterolle/vera-checkpoint-160-20261030`,
  `danterolle/vera-checkpoint-400-20261101`
  (adapter, optimizer state and data cursor, so `--epochs 2` can resume)
  and `danterolle/vera-perturbed-eval-20261101`
