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
string. The generator lives in `finetuning/perturb/`.

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

### What the adapter learned

`scope`, `unavailable` and `injection` move from 0/6 to 6/6. The base answered
out-of-scope questions as security questions, treated missing records as facts and
followed one injection note; the adapter refuses, labels the claims and ignores the
instructions. These are behaviors the base did not have, not phrasing differences.

### What the adapter lost

On `language` and `multiturn` the base is perfect and the adapter is not:

- Italian question about `CVE-2026-81578`: the base answers in Italian with the record
  content; the adapter answers *"No supplied authoritative evidence concerns
  CVE-2026-81578"* in English, and the evidence does contain that CVE.
- Follow-up about an entity from the previous turn: the base keeps the subject; the
  adapter falls back to *"No configured authoritative source concerns this local
  applicability question."*

This is the expected forgetting from a monolingual dataset with no conversations, mixed
only into a small adapter. It is also the clearest argument against more epochs on the
same data.

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
- The gaps are large and coherent: 6/6 against 0/6, 4/4 against 0/4.
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

## Verdict

1. Fine-tuning for answer shape and grounding works: JSON conformity, scope, missing
   evidence and injection resistance improve sharply and reproducibly.
2. More epochs on the same data would not help. At 0.81 epoch every validation answer
   already equals the target, so additional passes can only add memorization.
3. The limit is the dataset, not the training budget. It is monolingual, has no
   conversations, uses templated targets and quotes whole evidence payloads.
4. The perturbed set is the most reusable artifact. It is a regression gate for the next
   model: do not promote an adapter that scores below the base on `language` or
   `multiturn`.

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
uv run python -m finetuning.perturb.score \
  --answers .vera/finetuning/perturbed-answers.jsonl \
  --set .vera/finetuning/perturbed.jsonl \
  --output .vera/finetuning/scores-perturbed.json
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

Private Kaggle resources:

- training kernel `danterolle/vera-stage4-train-20261030` (160 -> 400 plus validation)
- test-evaluation kernel `danterolle/vera-stage3-test-eval-20261030`
- perturbed runner `danterolle/vera-perturbed-runner-20261101`
- datasets `danterolle/vera-checkpoint-160-20261030`,
  `danterolle/vera-checkpoint-400-20261101`
  (adapter, optimizer state and data cursor, so `--epochs 2` can resume)
  and `danterolle/vera-perturbed-eval-20261101`
