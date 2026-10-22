#!/usr/bin/env node
/**
 * Report slides whose content overflows the printable frame.
 *
 * The deck is loaded in reveal.js print mode (`?print-pdf`), which is exactly how
 * the PDF is produced, so the measurements match the exported pages.
 *
 * Usage: node scripts/check-overflow.mjs
 */
import { createRequire } from "node:module";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const deckFile = path.resolve(here, "..", "index.html");

const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
].filter(Boolean);

const chromePath = CHROME_CANDIDATES.find((candidate) => existsSync(candidate));
const puppeteer = require("puppeteer-core");

const browser = await puppeteer.launch({
  executablePath: chromePath,
  headless: true,
  args: ["--no-sandbox", "--font-render-hinting=none"],
});

try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1210, height: 681, deviceScaleFactor: 1 });
  await page.goto(`file://${deckFile}?print-pdf`, { waitUntil: "networkidle0" });
  await page.waitForFunction(() => window.Reveal && window.Reveal.isReady(), { timeout: 30000 });
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise((resolve) => setTimeout(resolve, 500));
  });

  const report = await page.evaluate(() => {
    const pages = [...document.querySelectorAll(".reveal .slides .pdf-page")];
    return pages.map((pdfPage, index) => {
      const section = pdfPage.querySelector("section");
      const pageRect = pdfPage.getBoundingClientRect();
      const style = getComputedStyle(section);
      const padTop = parseFloat(style.paddingTop);
      const padBottom = parseFloat(style.paddingBottom);
      const padLeft = parseFloat(style.paddingLeft);
      const padRight = parseFloat(style.paddingRight);

      let bottom = 0;
      let right = 0;
      let widest = 0;
      for (const child of section.children) {
        if (child.classList.contains("deck-footer")) continue;
        const rect = child.getBoundingClientRect();
        bottom = Math.max(bottom, rect.bottom);
        right = Math.max(right, rect.right);
        widest = Math.max(widest, rect.width);
      }

      const contentBottom = pageRect.top + pageRect.height - padBottom;
      const contentRight = pageRect.left + pageRect.width - padRight;

      return {
        index: index + 1,
        title: (section.querySelector("h1, h2")?.textContent || "(untitled)").trim().slice(0, 52),
        overflowBottom: Math.round(bottom - contentBottom),
        overflowRight: Math.round(right - contentRight),
        scrollOverflow: Math.round(section.scrollHeight - pageRect.height),
        pageHeight: Math.round(pageRect.height),
      };
    });
  });

  let bad = 0;
  for (const row of report) {
    const flags = [];
    if (row.overflowBottom > 1) flags.push(`bottom +${row.overflowBottom}px`);
    if (row.overflowRight > 1) flags.push(`right +${row.overflowRight}px`);
    if (row.scrollOverflow > 1) flags.push(`scroll +${row.scrollOverflow}px`);
    if (flags.length) {
      bad += 1;
      console.log(
        `slide ${String(row.index).padStart(2)}  ${row.title.padEnd(54)} ${flags.join(", ")}`,
      );
    }
  }
  console.log(
    bad === 0
      ? `OK: all ${report.length} slides fit the ${report[0]?.pageHeight ?? 681}px frame`
      : `${bad} slide(s) need adjustment`,
  );
} finally {
  await browser.close();
}
