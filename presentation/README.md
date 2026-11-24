# Presentation

The [26-slide deck](../VERA-presentation.pdf) explains VERA's architecture,
evidence path and human review before comparing retrieval, fine-tuning and local
inference. The [technical report](../docs/technical-report.md) provides the
experiment protocols and separates measured results from open questions.

## Edit and export

Edit `index.html` for the main deck and `scripts/exam-slides.js` for the graph
comparison, review trace, runtime budgets, model experiments and failure analysis.
`scripts/deck.js` initializes the vendored reveal.js and numbers the
slides. The light palette and Libron typography live in `css/theme.css`.
`css/signal.css` styles the cover and workflow panels, `css/data.css` styles the
tables and charts, and `images/vera-mark.svg` contains the centered wordmark.

From the repository root, install the export dependencies, open the deck and
regenerate the PDF:

```bash
cd presentation
npm ci
open index.html
node scripts/check-overflow.mjs
npm run export
```

The export overwrites `../VERA-presentation.pdf` and detects Chrome automatically.
Regenerate it whenever the HTML, slide scripts, styles or figures change.
To use a different executable, set `CHROME_PATH` or pass `--chrome` from the
`presentation` directory:

```bash
node scripts/export-pdf.mjs --out ../other.pdf --chrome /path/to/chrome
```

## Reproduce the figures

| Figure | Source |
| --- | --- |
| Per-analysis resource budgets | [Runtime settings](../src/vera/config.py) and [workflow limits](../docs/architecture.md#budgets-and-persistence) |
| Graph on/off and synthetic review trace | [Paired retrieval probe](../docs/technical-report.md#paired-retrieval-probe) |
| Step-400 checkpoints, held-out results, 220-case comparison and retrieval audit | [Checkpoint comparison](../docs/finetuning-run-20261101.md#validation), [held-out report](../docs/finetuning-step400-heldout.md) and [scope audit](../docs/finetuning-adapter-assessment.md#scope-probe-refusal-in-both-directions-2026-11-09) |
| V4 dataset split, alert counts, training resume and validation loss | [Dataset counts](../docs/domain-dataset-v4.md#size) and the [training record](../docs/finetuning-v4-results.md#the-completed-epoch). The three loss measurements are plotted in `images/v4-validation-loss.svg`. |
| V4 schema, scope, tokens and generation time | [Historical paired test](../docs/finetuning-v4-results.md#paired-validation-and-test-samples). The [relevance guard rescore](../docs/finetuning-v4-results.md#the-historical-runtime-guard) reused those answers. |
| Local request latency and targeted rerun | [Local comparison and failure analysis](../docs/technical-report.md#results-and-failures) |

Run the graph probe from the repository root. It prints per-query JSON and uses
temporary databases, so it leaves the existing VERA stores untouched:

```bash
uv run --extra knowledge-graph python presentation/scripts/measure-graph.py
```

When refreshing the deck's recorded values, update the matching table and chart
labels as well as the report. The graph probe measures retrieval and provenance.
The historical comparison reports generation time. The local probe times full requests.

The historical charts in `images/finetuning-v3/` are used by the deck or the
fine-tuning documentation. To rebuild them from the retained local reports, run
the following commands from the repository root:

```bash
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
not retained as JSON. The charts document historical experiments.

Libron's [font license](fonts/LICENSE-Libron.txt) is included alongside the vendored
reveal.js files.
