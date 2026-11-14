# Presentation

The presentation uses a vendored copy of reveal.js and exports to PDF through Chrome.
Each export reflects the repository at that point in time, so regenerate
`../VERA-presentation.pdf` whenever the slides change.

From the repository root, open the deck and install the export dependencies:

```bash
cd presentation
open index.html
npm ci
npm run export
node scripts/check-overflow.mjs
```

The export writes `../VERA-presentation.pdf` and detects Chrome automatically.
To use a different executable, set `CHROME_PATH` or pass `--chrome` from the
`presentation` directory:

```bash
node scripts/export-pdf.mjs --out ../other.pdf --chrome /path/to/chrome
```

The charts in `images/finetuning-v3/` come from retained scores, pack reports and
training reports. Run the following commands from the repository root, not from
the presentation directory:

```bash
uv run --extra analysis python finetuning/plot_pack.py \
  --scores .vera/finetuning/v3-english-20261102b/scores-kaggle-110.json \
  --pack-report .vera/finetuning/v3-english-20261102b/evaluation-pack-10-per-task/report.json \
  --output presentation/images/finetuning-v3
uv run --extra analysis python finetuning/plot_validation.py \
  --scores .vera/finetuning/v3-english-20261102b/scores-kaggle-110.json \
  --output presentation/images/finetuning-v3
uv run --extra analysis python finetuning/plot_perturbed.py \
  --training .vera/finetuning/v3-english-20261102b/scores-perturbed-english-only.json \
  --held-out .vera/finetuning/v3-english-20261102b/scores-perturbed-test-english-only.json \
  --output presentation/images/finetuning-v3
uv run --extra analysis python finetuning/plot_training.py \
  --report .vera/finetuning/kaggle-preview-20261028-103035/results/vera-full-20261028-103453/report.json \
  --report .vera/finetuning/kaggle-preview-20261028-103035/resume-results/vera-full-resume-20261029-104525/report.json \
  --extra-history .vera/finetuning/step400-validation-history.json \
  --metrics .vera/finetuning/kaggle-preview-20261028-103035/results/vera-full-20261028-103453/metrics.jsonl \
  --metrics .vera/finetuning/kaggle-preview-20261028-103035/resume-results/vera-full-resume-20261029-104525/metrics.jsonl \
  --output presentation/images/finetuning-v3
```

The stage-2 points in `step400-validation-history.json` were transcribed from the
[step-400 report](../docs/finetuning-run-20261101.md), because that run's log was
not retained as JSON. These charts describe historical experiments, not acceptance
of the current runtime.

Libron's [font license](fonts/LICENSE-Libron.txt) is included alongside the vendored
reveal.js files.
