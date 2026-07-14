import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173";
const outputDir = new URL("../artifacts/screenshots/", import.meta.url);
const issues = [];

await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch();

async function capture(name, viewport) {
  const page = await browser.newPage({ viewportSize: viewport, deviceScaleFactor: 1 });
  page.on("console", (message) => {
    if (message.type() === "error") issues.push(`[${name}] console: ${message.text()}`);
  });
  page.on("pageerror", (error) => issues.push(`[${name}] pageerror: ${error.message}`));
  page.on("requestfailed", (request) => issues.push(`[${name}] requestfailed: ${request.url()} ${request.failure()?.errorText || ""}`));
  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await page.screenshot({ path: new URL(`home-${name}.png`, outputDir).pathname, fullPage: true });
  await page.close();
}

try {
  await capture("desktop-1487", { width: 1487, height: 1058 });
  await capture("mobile-390", { width: 390, height: 844 });
} finally {
  await browser.close();
}

if (issues.length) {
  console.error(issues.join("\n"));
  process.exitCode = 1;
} else {
  console.log("Captured desktop and mobile screenshots with no console, page, or request errors.");
}
