#!/usr/bin/env node
/**
 * Export the reveal.js deck to PDF using headless Chrome.
 *
 * Usage:
 *   node scripts/export-pdf.mjs [--out ../VERA-presentation.pdf] [--chrome <path>]
 *
 * The script relies on reveal.js' built-in print mode (`?print-pdf`), which renders
 * every slide at the deck size and paginates them with CSS page breaks.
 */
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const here = path.dirname(fileURLToPath(import.meta.url));
const deckDir = path.resolve(here, "..");

const args = process.argv.slice(2);
const argValue = (flag, fallback) => {
  const index = args.indexOf(flag);
  return index !== -1 && args[index + 1] ? args[index + 1] : fallback;
};

const outFile = path.resolve(deckDir, argValue("--out", "../VERA-presentation.pdf"));
const deckFile = path.resolve(deckDir, "index.html");

const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  argValue("--chrome", null),
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
].filter(Boolean);

const chromePath = CHROME_CANDIDATES.find((candidate) => existsSync(candidate));
if (!chromePath) {
  console.error("Could not find a Chrome/Chromium binary. Pass --chrome <path> or set CHROME_PATH.");
  process.exit(1);
}

const browser = await puppeteer.launch({
  executablePath: chromePath,
  headless: true,
  args: ["--no-sandbox", "--font-render-hinting=none", "--disable-lcd-text"],
});

try {
  const page = await browser.newPage();
  const url = `file://${deckFile}?print-pdf&print-pdf-page-size=1210,681`;

  await page.setViewport({ width: 1210, height: 681, deviceScaleFactor: 2 });
  await page.goto(url, { waitUntil: "networkidle0" });

  // Wait for reveal.js and the webfonts to be ready.
  await page.waitForFunction(() => window.Reveal && window.Reveal.isReady(), { timeout: 30000 });
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  });

  const total = await page.evaluate(() => window.Reveal.getTotalSlides());
  console.log(`Deck loaded: ${total} slides`);

  await page.pdf({
    path: outFile,
    printBackground: true,
    preferCSSPageSize: true,
    timeout: 120000,
  });

  console.log(`PDF written to ${outFile}`);
} finally {
  await browser.close();
}
