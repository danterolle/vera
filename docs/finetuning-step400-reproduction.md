# Reproducing the historical step-400 evaluations

These commands document the English-only v3 evaluation of the existing step-400
adapter. They do not train it, authorize v3 training or qualify the current
`vera-evidence-v2` runtime. Use fresh output paths: retained selections and scores
must not be overwritten.

## Prepare the English-only probe

The 2026-11-01 answers used the older language-mirroring prompt. To rebuild the later
probe, extract the training shard from the aligned candidate. Its Italian questions
deliberately expect English answers:

```bash
uv run python - <<'PY'
from pathlib import Path
from zipfile import ZipFile

archive = Path(".vera/finetuning/v3-english-20261102b/aligned/vera-domain-v3-english-candidate.zip")
destination = Path(".vera/finetuning/v3-english-20261102b/extracted/train/part-000.jsonl")
destination.parent.mkdir(parents=True, exist_ok=True)
with ZipFile(archive) as source:
    destination.write_bytes(source.read("train/part-000.jsonl"))
PY
uv run python -m finetuning.perturb.build \
  --dataset .vera/finetuning/v3-english-20261102b/extracted/train \
  --output .vera/finetuning/v3-english-20261102b/perturbed-english-only.jsonl \
  --seed 20261102
```

The generated set is ignored by Git. Answers from 2026-11-06 remain at
`.vera/finetuning/v3-english-20261102b/perturbed-answers-english-only.jsonl`.
Score those answers against the matching set, candidate and captured contract:

```bash
PYTHONPATH=finetuning uv run python -m perturb.score \
  --answers .vera/finetuning/v3-english-20261102b/perturbed-answers-english-only.jsonl \
  --set .vera/finetuning/v3-english-20261102b/perturbed-english-only.jsonl \
  --dataset .vera/finetuning/v3-english-20261102b/aligned/vera-domain-v3-english-candidate.zip \
  --contract .vera/finetuning/v3-english-20261102b/bundle/runtime-contract.json \
  --output .vera/finetuning/v3-english-20261102b/scores-perturbed-english-only.json
```

## Prepare the held-out probe

Extract `test/part-000.jsonl` into the corresponding `extracted/test` directory,
then use the held-out seed and answer file:

```bash
uv run python -m finetuning.perturb.build \
  --dataset .vera/finetuning/v3-english-20261102b/extracted/test \
  --output .vera/finetuning/v3-english-20261102b/perturbed-test-english-only.jsonl \
  --seed 20261107
PYTHONPATH=finetuning uv run python -m perturb.score \
  --answers .vera/finetuning/v3-english-20261102b/perturbed-test-answers-english-only.jsonl \
  --set .vera/finetuning/v3-english-20261102b/perturbed-test-english-only.jsonl \
  --dataset .vera/finetuning/v3-english-20261102b/aligned/vera-domain-v3-english-candidate.zip \
  --contract .vera/finetuning/v3-english-20261102b/bundle/runtime-contract.json \
  --output .vera/finetuning/v3-english-20261102b/scores-perturbed-test-english-only.json
```

The held-out split has already been used. These are provenance instructions, not a
recommendation to reuse it for tuning or model selection.

## Packs and charts

The 110-case Kaggle run used `finetuning/kaggle_eval.py`, followed by local
`finetuning/score.py` scoring against the same candidate and contract. Answers and
metadata are under `.vera/finetuning/v3-english-20261102b/kaggle-results/`.
The [evaluation guide](finetuning-evaluation.md) explains pack selection and why
recreating these template-based selections now needs an explicit exploratory override.

To regenerate the earlier v2 charts:

```bash
uv run --extra analysis python finetuning/plot_pack.py \
  --scores .vera/finetuning/v2-eval-20261101/kaggle-results/vera-eval-v2-110/results/scores.json \
  --pack-report .vera/finetuning/v2-eval-20261101/evaluation-pack-10-per-task/report.json \
  --output docs/images/finetuning-run-20261101
```

The v3 charts use `plot_training.py`, `plot_validation.py` and `plot_perturbed.py`.
Their complete commands are in the [presentation README](../presentation/README.md).

## Retained artifacts

Everything below is local and Git-ignored under `.vera/finetuning/`. The original
language-mirroring run retained `perturbed.jsonl`, its 80 paired answers in
`perturbed-answers.jsonl`, and `scores-perturbed.json`.

The training outputs retain step-160 and step-400 reports, metrics, validation/test
answers and complete checkpoints. English-only candidates, probes, 110/220-case packs,
the 220-case test pack, local results and Kaggle scores live under
`v3-english-20261102b/`. Earlier inference-only outputs live under
`v2-eval-20261101/kaggle-results/vera-eval-v2-110/`.

The private Kaggle resources used for these runs were:

| Role | Resource |
| --- | --- |
| Training from 160 to 400 | `danterolle/vera-stage4-train-20261030` |
| Earlier test evaluation | `danterolle/vera-stage3-test-eval-20261030` |
| Original perturbed runner | `danterolle/vera-perturbed-runner-20261101` |
| v2 validation kernel | `danterolle/vera-v2-eval-110-base-vs-adapter` |
| English-only validation kernel | `danterolle/vera-english-only-evaluation-110` |
| v2 evaluation inputs | `danterolle/vera-eval-v2-110-inputs-20261101` |
| English-only inputs | `danterolle/vera-english-eval-inputs-20261102` |
| Step-160 checkpoint | `danterolle/vera-checkpoint-160-20261030` |
| Step-400 checkpoint | `danterolle/vera-checkpoint-400-20261101` |
| Original perturbed dataset | `danterolle/vera-perturbed-eval-20261101` |

The checkpoint datasets include adapter, optimizer state and data cursor, which
allowed a resumed run with `--epochs 2`. Their existence does not authorize that run.
