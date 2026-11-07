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

Charts under `images/finetuning-v3/` are generated from the retained v3 scores and pack
report:

```bash
uv run --extra analysis python finetuning/plot_pack.py \
  --scores .vera/finetuning/v3-english-20261102b/scores-kaggle-110.json \
  --pack-report .vera/finetuning/v3-english-20261102b/evaluation-pack-10-per-task/report.json \
  --output presentation/images/finetuning-v3
```

Libron's [font license](fonts/LICENSE-Libron.txt) is included. Reveal.js remains vendored.
