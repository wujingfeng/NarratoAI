import { mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { chromium } from "playwright";
import { screens } from "./screens.mjs";

const baseUrl = process.env.VISUAL_BASE_URL ?? "http://127.0.0.1:5173";
const outDir = resolve("visual-qa/actual");
const only = process.env.SCREEN ? new Set(process.env.SCREEN.split(",").map((item) => item.trim())) : null;
const browserCandidates = [
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
  "/Users/wujingfeng/Library/Caches/ms-playwright/chromium_headless_shell-1223/chrome-headless-shell-mac-arm64/chrome-headless-shell",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
].filter(Boolean);
const executablePath = browserCandidates.find((path) => existsSync(path));

await mkdir(outDir, { recursive: true });

const browser = await chromium.launch(executablePath ? { executablePath } : undefined);
const page = await browser.newPage({ deviceScaleFactor: 1 });

for (const screen of screens) {
  if (only && !only.has(screen.id)) continue;
  await page.setViewportSize({ width: screen.width + 380, height: screen.height + 120 });
  await page.goto(`${baseUrl}/?screen=${screen.id}`, { waitUntil: "networkidle" });
  const stage = page.locator(".screen-stage");
  await stage.screenshot({ path: resolve(outDir, `${screen.id}.png`) });
  console.log(`captured ${screen.id} ${screen.width}x${screen.height}`);
}

await browser.close();
