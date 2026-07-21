import { access, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
for (const file of [
  "src/pages/NarrationAnalysisPage.jsx",
  "src/components/narration/NarrationAnalysisBoard.jsx",
  "src/components/narration/NarrationFullscreenPlayer.jsx",
  "src/data/narrationAnalysisData.js",
  "src/styles/narration-analysis.css",
]) {
  await access(path.join(root, file));
}
const sources = await Promise.all([
  "src/pages/NarrationAnalysisPage.jsx",
  "src/components/narration/NarrationAnalysisBoard.jsx",
  "src/components/narration/NarrationFullscreenPlayer.jsx",
  "src/styles/narration-analysis.css",
].map((file) => readFile(path.join(root, file), "utf8")));
const forbidden = [/08-narration-analysis-desktop\.png/i, /data:image/i, /base64/i, /background-image\s*:\s*url\s*\(/i, /<canvas\b/i];
if (forbidden.some((pattern) => sources.some((source) => pattern.test(source)))) throw new Error("分析页包含不允许的贴图实现");
const pageSource = sources[0];
if (!pageSource.includes('from "animejs"') || !pageSource.includes("analysisProgress")) {
  throw new Error("分析页必须由 Anime.js 驱动进度条与百分比动画");
}
if (!pageSource.includes("logs={analysisLogs}")) {
  throw new Error("分析页必须向任务日志组件传递 analysisLogs");
}
const boardSource = sources[1];
if (!boardSource.includes("analysis-orbit__progress") || !pageSource.includes("createTimeline")) {
  throw new Error("方案 A 必须包含 Anime.js 驱动的 SVG 能量进度环");
}
if (!boardSource.includes("animationRefs.ring") || !pageSource.includes("ring: ringRef")) {
  throw new Error("66% 停留态必须直接驱动 SVG 进度环呼吸");
}
if (!boardSource.includes("analysis-total__glow") || boardSource.includes("可离开此页面，进度会自动保存")) {
  throw new Error("停留态必须包含同步进度条扫光，并移除离开页面提示");
}
if (!pageSource.includes("barGlowPosition") || !boardSource.includes("left: `${barGlowPosition}%`")) {
  throw new Error("进度条扫光必须覆盖完整已完成区间");
}
if (!pageSource.includes("barGlowOpacity") || !boardSource.includes("opacity: barGlowOpacity")) {
  throw new Error("进度条扫光必须由 Anime.js 同步驱动透明度");
}
if (!pageSource.includes("ANALYSIS_PROGRESS = 100") || pageSource.includes('<button type="button" disabled>下一步：编辑片段')) {
  throw new Error("分析完成态必须默认 100%，并启用下一步按钮");
}
console.log("Narration analysis structure and anti-paste scan passed");
if (process.env.ANALYSIS_SCAN_ONLY === "1") process.exit(0);

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1487, height: 1058 } });
await page.addInitScript(() => localStorage.setItem("narrato.locale", "zh-CN"));
const failures = [];
page.on("pageerror", (error) => failures.push(error.message));
try {
  await page.goto(`${process.env.BASE_URL || "http://127.0.0.1:4174"}/dashboard/narration/analysis`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "短剧解说 AI 分析" }).waitFor();
  if ((await page.locator(".dashboard-sidebar a[aria-current='page']").textContent()) !== "短剧解说") throw new Error("共享侧栏未正确复用或高亮");
  const videos = page.locator(".analysis-video");
  await videos.nth(1).click();
  if (await videos.nth(0).locator(".analysis-video__expand").count()) throw new Error("未选中视频仍显示放大按钮");
  const selected = videos.nth(1);
  await selected.getByRole("button", { name: /全屏播放 EP02/ }).click();
  await page.getByRole("dialog", { name: "EP02 全屏播放" }).waitFor();
  await page.getByRole("button", { name: "播放下一个视频" }).click();
  if ((await page.getByRole("dialog").getByText("EP03").count()) < 1) throw new Error("全屏播放器未切换到下一个视频");
  await page.keyboard.press("Escape");
  await page.getByRole("dialog").waitFor({ state: "hidden" });
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)) throw new Error("桌面页面出现水平溢出");
  console.log("Narration analysis route and video interactions passed");
} finally { await browser.close(); }
if (failures.length) throw new Error(`Browser errors:\n${failures.join("\n")}`);
