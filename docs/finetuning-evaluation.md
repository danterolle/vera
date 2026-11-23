# Evaluating and reviewing a fine-tuned model

Evaluation needs to separate three things: what the model emitted, what the runtime
normalized or repaired, and what a person judged correct. None is a substitute for
the others. The [v4 results](finetuning-v4-results.md) show why valid JSON and exact
quotations can coexist with an answer about the wrong entity.

## Score the generated answers

The notebook can run `evaluate.py` after training to generate paired base/adapter
answers on a deterministic, task-balanced validation sample. Download `answers.jsonl`
and score it against the matching dataset, captured contract and selection:

```bash
uv run python finetuning/score.py \
  --dataset /path/to/reviewed-dataset.zip \
  --contract /path/to/runtime-contract.json \
  --answers /path/to/answers.jsonl \
  --selection /path/to/selection.json \
  --output /path/to/new-scores.json
```

The scorer uses `GeneratedAnswer` and the runtime validator. It reports raw-contract
validity, normalization changes, scope, status recall and precision, exact status
agreement, citations, quote fidelity, summary-review requirements and fallback counts.
Repaired metrics are separate, so repair cannot be mistaken for model learning.
Invalid answers remain in the status-metric denominators.

Duplicate answers and unpaired samples are rejected. Supplying `--selection` also
checks completeness against the chosen IDs. Reports are immutable and never authorize
production. Citation rates remain conditional on schema-valid answers; read them
alongside the raw validity rates.

## Select an independent pack

`prepare_eval_pack.py` selects a deterministic number of examples per task. By
default, targets must be absent from training and unique within the selected pack,
in addition to source/group/entity separation. The explicit
`--require-independent-targets` flag keeps that behavior.

Exact JSON novelty is necessary but does not prove independent authorship, semantic
diversity or factual accuracy. The v3 candidate cannot supply independent targets
for every task because some families have only one target. The
[golden-set procedure](../finetuning/golden/README.md) instead calls for at least
50 reviewed cases covering the current 18 tasks.

For historical template-based packs, `--allow-template-targets` is an exploratory
override, not an acceptance shortcut. The following recreates the old 220-row
validation selection using today's explicit override:

```bash
uv run python finetuning/prepare_eval_pack.py \
  --dataset .vera/finetuning/v3-english-20261102b/aligned/vera-domain-v3-english-candidate.zip \
  --contract .vera/finetuning/v3-english-20261102b/bundle/runtime-contract.json \
  --previous-answers .vera/finetuning/kaggle-preview-20261028-103035/resume-results/vera-eval-resume-20261029-104525/answers.jsonl \
  --previous-dataset .vera/finetuning/v2-eval-20261101/aligned/vera-domain-v2-candidate.zip \
  --previous-contract .vera/finetuning/v2-eval-20261101/bundle/runtime-contract.json \
  --exclude-loss-sample 24 --per-task 20 --seed 20261102 \
  --max-new-tokens 768 --allow-template-targets \
  --output .vera/finetuning/v3-english-20261102b/evaluation-pack-20-per-task-recreated
```

The historical selection had 40 training-target overlaps and 38 duplicate rows.
Its 110-row counterpart had 20 and 18. Those were validation slices with unchanged
targets, not independent tests or permission to train. Use a fresh directory, since
the packer never overwrites a selection.

## Reserve the held-out test

Use the test split only after model selection. Test packs reject prior-answer and
loss-sample exclusions, which are validation-only options. For provenance, the old
220-row test selection can be expressed as:

```bash
uv run python finetuning/prepare_eval_pack.py \
  --dataset .vera/finetuning/v3-english-20261102b/aligned/vera-domain-v3-english-candidate.zip \
  --contract .vera/finetuning/v3-english-20261102b/bundle/runtime-contract.json \
  --split test --per-task 20 --seed 20261107 \
  --max-new-tokens 768 --allow-template-targets \
  --output .vera/finetuning/v3-english-20261102b/evaluation-pack-test-recreated
```

That split has already been consumed. Recreating a selection is not permission to
reuse its answers for tuning. The [held-out report](finetuning-step400-heldout.md)
records the 86/220 versus 219/220 strict result and its template limitations.

For inference-only Kaggle comparisons, `finetuning/kaggle_eval.py` runs preflight
and base/adapter generation on a private T4 x2 kernel. Its uploaded bundle includes
dataset, inference and evaluation modules, but no training entrypoint. Answers and
preflight outputs go under `/kaggle/working`; dependencies and model caches stay
under `/kaggle/temp`.

## Prepare an independent local model study

Use the [golden case format](../finetuning/golden/README.md) with at least 50 newly
reviewed cases across all 18 tasks. Before seeing any model output, have a second
person confirm each case's sources, expected findings and forbidden assertions, then
record their name and ISO date with `"reviewed": true`. Keep the reviewed source file
private. Neither the historical seven draft cases nor the old v1 questions qualify.

Freeze the case file with the exact ID from the local server's `/v1/models` and the
SHA-256 of the actual file being served. For example, use the following after setting
`MODEL_ID` and `MODEL_FILE` to the values for the chosen merged model:

```bash
EVAL_DIR=.vera/reviews/independent-v1
MODEL_SHA="$(shasum -a 256 "$MODEL_FILE" | cut -d ' ' -f 1)"
uv run python scripts/review-pack.py prepare \
  --cases "$EVAL_DIR/cases-reviewed.jsonl" \
  --model "$MODEL_ID" --artifact-sha256 "$MODEL_SHA" \
  --output "$EVAL_DIR/study"
```

Before generation, start a separate loopback VERA instance on port `8001` as
described in the [local model guide](local-model.md#connect-vera), using a fresh
`VERA_DB_PATH` and `VERA_CORPUS_DIR`. For these offline cases, disable live sources,
web search and memory recall; build a separate graph if measuring graph retrieval.
Record the Git revision, model server version and active settings with the study. Do not
change the model file, adapter scale, profile or runtime while generating or resuming:
the digest is operator-verified, not something the model API can attest.

```bash
uv run python scripts/review-pack.py generate \
  --study "$EVAL_DIR/study" --url http://127.0.0.1:8001 \
  --output "$EVAL_DIR/answers.jsonl"
uv run python scripts/review-pack.py build \
  --study "$EVAL_DIR/study" --answers "$EVAL_DIR/answers.jsonl" \
  --output "$EVAL_DIR/pack"
```

This path checks that every frozen case has one matching answer from the declared
model and validation contract; fallbacks remain visible and block readiness. Case
expectations and reviewer names are not sent in the analysis request. Complete
`record` and `summarize` as below. Score raw model output separately; runtime reports
include normalization and repair. HTTP `202` is not autonomous success. Initial
analysis does not exercise restart, decision retries, or the revision endpoint:
exercise them separately for the target profile, along with any enabled graph or
live-source integrations.

## Review fresh runtime answers

The runtime pack tests the artifact actually being served. It does not train,
tune or choose a model, and it cannot replace an independently authored golden set.
Use a new answer file and pack directory after runtime or model changes:

```bash
uv run python scripts/review-pack.py generate \
  --queries .vera/reviews/v1/queries.jsonl \
  --output .vera/reviews/v2/answers.jsonl
uv run python scripts/review-pack.py build \
  --answers .vera/reviews/v2/answers.jsonl \
  --output .vera/reviews/v2/pack
uv run python scripts/review-pack.py record \
  --pack .vera/reviews/v2/pack --reviewer "Reviewer name"
uv run python scripts/review-pack.py summarize --pack .vera/reviews/v2/pack
```

The query file supplies case IDs, tasks, expected scope and questions. It can also
include conversation, events and a simulated flag. Reusing the old question list
does not make it an independently authored golden set.

Each case exposes the full summary, claims, quotations, evidence, reflection,
warnings and runtime provenance without clipping them. A person records `accept`,
`fix` or `reject` in `review.csv`, with notes required for fixes or rejection.
Every verdict needs a reviewer and date.

After review, the person completes `signoff.json` with reviewer, ISO date and
`human_review_complete=true`, keeping the exact `pack_sha256`. The summary requires
one verdict per unique case, all cases accepted, required notes and a matching hash.
At least 40 accepted cases from one identified model are needed for runtime-pack
readiness. Fallbacks and mismatched validation-contract versions block it even
when their text is accepted.

This readiness is necessary, not sufficient, for authorization. The tool always
leaves `production_authorized=false`. Reviewing a pack also does not approve any
pending API review; those decisions retain their own local version/idempotency checks.
The [chat guide](chat.md#human-review) explains that separate workflow.
