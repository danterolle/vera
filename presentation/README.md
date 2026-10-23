# VERA presentation

A reveal.js deck describing the VERA project, plus a headless-Chrome PDF export.

The deck and PDF retain a historical project snapshot, including references to the
automated test suite that has since been removed.

## Files

```text
presentation/
├── index.html              the 21-slide deck (English)
├── css/theme.css           custom theme, @font-face for Libron, print overrides
├── fonts/                  Libron woff2 files (OFL 1.1) + license
├── vendor/reveal.js/       vendored reveal.js 5 dist (MIT)
├── scripts/export-pdf.mjs  renders the deck to PDF with headless Chrome
├── scripts/check-overflow.mjs  verifies every slide fits the printable frame
└── package.json            dev dependency: puppeteer-core
```

## View it

```bash
open index.html            # no build step, everything is vendored
```

Arrow keys navigate, `?` opens the reveal.js help, `s` opens the speaker notes view.

## Export to PDF

```bash
npm install
npm run export                                     # writes ../VERA-presentation.pdf
node scripts/export-pdf.mjs --out ../other.pdf     # custom output path
node scripts/export-pdf.mjs --chrome /path/to/chrome
```

The script finds Chrome automatically on macOS, Linux and Windows; override it with
`--chrome <path>` or the `CHROME_PATH` environment variable. It uses reveal.js' own
print mode (`?print-pdf`), so the exported pages are pixel-identical to the slides on
screen.

## Check the layout

```bash
node scripts/check-overflow.mjs
```

It loads the deck in print mode and reports any slide whose content exceeds the
1210×681 frame, so text clipped by the PDF page boundary is caught before export.

## Typography

Libron by Nico Verbruggen (derived from Readerly / Newsreader), licensed under the
SIL Open Font License 1.1 — see `fonts/LICENSE-Libron.txt`. The woff2 files come from
the official [release archive](https://github.com/nicoverbruggen/libron/releases).
