import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDirectory, "..");
const outputDirectory = path.join(projectRoot, "artifacts", "screenshots");
const targetUrl = "http://127.0.0.1:4177";

const viewports = [
  { name: "desktop-1487x1058", width: 1487, height: 1058 },
  { name: "tablet-landscape-1024x768", width: 1024, height: 768 },
  { name: "tablet-portrait-768x1024", width: 768, height: 1024 },
  { name: "mobile-390x844", width: 390, height: 844 },
];

let chromium;
try {
  ({ chromium } = await import("playwright"));
} catch {
  console.error("Capture requires the Playwright package and an installed Chromium browser.");
  console.error("Install it in this isolated prototype before running npm run capture.");
  process.exit(1);
}

await mkdir(outputDirectory, { recursive: true });
const browser = await chromium.launch({ headless: true });
const diagnostics = [];

try {
  for (const viewport of viewports) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      deviceScaleFactor: 1,
      reducedMotion: "reduce",
    });
    const page = await context.newPage();
    const events = [];

    page.on("console", (message) => {
      if (message.type() === "error" || message.type() === "warning") {
        events.push({ type: `console:${message.type()}`, text: message.text() });
      }
    });
    page.on("pageerror", (error) => events.push({ type: "pageerror", text: error.message }));
    page.on("requestfailed", (request) => {
      events.push({
        type: "requestfailed",
        text: `${request.method()} ${request.url()} — ${request.failure()?.errorText ?? "unknown error"}`,
      });
    });

    try {
      const response = await page.goto(targetUrl, { waitUntil: "networkidle", timeout: 20_000 });
      if (!response?.ok()) events.push({ type: "http", text: `Navigation returned ${response?.status() ?? "no response"}` });
      await page.screenshot({
        path: path.join(outputDirectory, `${viewport.name}.png`),
        fullPage: true,
        animations: "disabled",
      });
    } catch (error) {
      events.push({ type: "capture", text: error.message });
    }

    diagnostics.push({ viewport, events });
    await context.close();
  }
} finally {
  await browser.close();
}

const reportPath = path.join(outputDirectory, "diagnostics.json");
await writeFile(reportPath, `${JSON.stringify({ targetUrl, diagnostics }, null, 2)}\n`);

const errors = diagnostics.flatMap(({ viewport, events }) => events.map((event) => ({ viewport: viewport.name, ...event })));
console.log(`Captured ${viewports.length} responsive viewports in ${outputDirectory}`);
console.log(`Diagnostics written to ${reportPath}`);

if (errors.length > 0) {
  errors.forEach((event) => console.error(`[${event.viewport}] ${event.type}: ${event.text}`));
  process.exitCode = 1;
} else {
  console.log("Browser diagnostics are clean: no console warnings/errors, page errors, or failed requests.");
}
