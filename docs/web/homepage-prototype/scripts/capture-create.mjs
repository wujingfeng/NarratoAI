import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173";
const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outputDir = path.join(projectRoot, "artifacts/create-page");
const executablePath =
  process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ executablePath, headless: true });

try {
  const desktop = await browser.newPage({ viewport: { width: 1487, height: 1058 }, deviceScaleFactor: 1 });
  await desktop.goto(`${baseUrl}/dashboard/create`, { waitUntil: "networkidle" });
  await desktop.getByRole("heading", { name: "创建新的 AI 视频" }).waitFor();
  await desktop.screenshot({ path: path.join(outputDir, "create-desktop-1487.png"), fullPage: false });
  await desktop.close();

  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  await mobile.goto(`${baseUrl}/dashboard/create`, { waitUntil: "networkidle" });
  await mobile.getByRole("heading", { name: "创建新的 AI 视频" }).waitFor();
  await mobile.screenshot({ path: path.join(outputDir, "create-mobile-390.png"), fullPage: true });
  await mobile.close();
} finally {
  await browser.close();
}

console.log(`新建创作页面截图已保存：${outputDir}`);
