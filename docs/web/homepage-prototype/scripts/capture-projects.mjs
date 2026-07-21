import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173";
const outputDir = new URL("../artifacts/projects-page/", import.meta.url);
await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true });
try {
  for (const [name, viewport, fullPage] of [["projects-desktop-1487", { width: 1487, height: 1058 }, false], ["projects-mobile-390", { width: 390, height: 844 }, true]]) {
    const page = await browser.newPage({ viewport });
    await page.goto(`${baseUrl}/dashboard/projects`, { waitUntil: "networkidle" });
    await page.locator('[data-page="projects"]').waitFor();
    await page.screenshot({ path: new URL(`${name}.png`, outputDir).pathname, fullPage });
    await page.close();
  }
} finally { await browser.close(); }
console.log(`Projects screenshots captured in ${outputDir.pathname}`);
