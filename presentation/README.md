# Presentation

Vendored reveal.js deck and Chrome-based PDF export. The deck tracks the repository at
the time of export; regenerate `../VERA-presentation.pdf` after changing slides.

From the repository root:

```bash
cd presentation
open index.html
npm ci
npm run export
node scripts/check-overflow.mjs
```

Export writes `../VERA-presentation.pdf`. Chrome is detected automatically;
use `--chrome /path/to/chrome` or `CHROME_PATH` to select another executable:

```bash
node scripts/export-pdf.mjs --out ../other.pdf --chrome /path/to/chrome
```

Charts under `images/finetuning-v3/` are generated from the retained scores, pack reports
and training reports:

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

The stage-2 points in `step400-validation-history.json` are transcribed from
`docs/finetuning-run-20261101.md`; the run log was not retained as JSON.

Libron's [font license](fonts/LICENSE-Libron.txt) is included. Reveal.js remains vendored.
