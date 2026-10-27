# Presentation

Vendored reveal.js deck and Chrome-based PDF export. The slides and PDF are a historical
snapshot; references to the removed test suite are not current implementation claims.

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

Libron's [font license](fonts/LICENSE-Libron.txt) is included. Reveal.js remains vendored.
