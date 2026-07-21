import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173";
const executablePath =
  process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const outputDir = new URL("../artifacts/screenshots/", import.meta.url);
const issues = [];

await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ executablePath, headless: true });

async function capture(name, viewport, fullPage) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1 });
  page.on("console", (message) => {
    if (message.type() === "error") {
      const location = message.location().url;
      issues.push(`[${name}] console${location ? ` (${location})` : ""}: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => issues.push(`[${name}] pageerror: ${error.message}`));
  page.on("requestfailed", (request) => issues.push(`[${name}] requestfailed: ${request.url()}`));
  page.on("response", (response) => {
    if (response.status() >= 400) issues.push(`[${name}] response ${response.status()}: ${response.url()}`);
  });

  try {
    await page.goto(`${baseUrl}/dashboard`, { waitUntil: "networkidle" });
    await page.locator('[data-page="dashboard"]').waitFor();
    await page.evaluate(() => document.fonts.ready);
    await page.waitForFunction(() => [...document.querySelectorAll(".case-masonry img")]
      .every((image) => image.complete && image.naturalWidth > 0));
    await page.screenshot({
      path: new URL(`${name}.png`, outputDir).pathname,
      fullPage,
    });
  } finally {
    await page.close();
  }
}

try {
  await capture("dashboard-desktop-1487", { width: 1487, height: 1058 }, false);
  await capture("dashboard-mobile-390", { width: 390, height: 844 }, false);
  await capture("dashboard-mobile-390-full", { width: 390, height: 844 }, true);
  await capture("dashboard-tablet-768", { width: 768, height: 1024 }, true);
  await capture("dashboard-wide-1920", { width: 1920, height: 1080 }, false);
} finally {
  await browser.close();
}

if (issues.length > 0) {
  console.error(issues.join("\n"));
  process.exitCode = 1;
} else {
  console.log(`Dashboard screenshots captured in ${outputDir.pathname}`);
}
