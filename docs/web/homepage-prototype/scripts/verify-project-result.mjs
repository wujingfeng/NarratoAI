import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const targets = [
  "src/pages/ProjectResultPage.jsx",
  "src/components/projects/ProjectResultPlayer.jsx",
  "src/components/projects/ProjectResultDetails.jsx",
  "src/data/projectResultData.js",
  "src/styles/project-result.css",
];
const forbidden = [
  ["reference image", /13-project-result-desktop\.png/i],
  ["data image", /data:image/i],
  ["base64", /base64/i],
  ["canvas", /<canvas\b|CanvasRenderingContext2D|drawImage\s*\(/i],
  ["CSS url background", /background-image\s*:\s*url\s*\(/i],
  ["SVG bitmap", /<image\b|xlink:href\s*=|href\s*=\s*["']data:image/i],
];

function vttTimestampToSeconds(timestamp) {
  const [hours, minutes, seconds] = timestamp.split(":");
  return Number(hours) * 3600 + Number(minutes) * 60 + Number(seconds);
}

async function files(target) {
  const absolute = path.join(root, target);
  const entries = await readdir(absolute, { withFileTypes: true }).catch(() => null);
  if (!entries) return [absolute];
  return (await Promise.all(entries.map((entry) => entry.isDirectory()
    ? files(path.join(target, entry.name))
    : [path.join(root, target, entry.name)]))).flat();
}

const violations = [];
for (const target of targets) {
  for (const file of await files(target)) {
    const source = await readFile(file, "utf8");
    for (const [label, regex] of forbidden) {
      if (regex.test(source)) violations.push(`${path.relative(root, file)}: ${label}`);
    }
  }
}
if (violations.length) throw new Error(`Project result anti-paste scan failed:\n${violations.join("\n")}`);
console.log("Project result anti-paste scan passed");
if (process.env.PROJECT_RESULT_SCAN_ONLY === "1") process.exit(0);

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true,
});
const page = await browser.newPage({ viewport: { width: 1487, height: 1058 } });
await page.addInitScript(() => localStorage.setItem("narrato.locale", "zh-CN"));
const browserErrors = [];
page.on("pageerror", (error) => browserErrors.push(error.message));
page.on("console", (message) => { if (message.type() === "error") browserErrors.push(message.text()); });

try {
  await page.goto(`${baseUrl}/dashboard/projects`, { waitUntil: "networkidle" });
  const firstProject = page.locator(".projects-table tbody tr").first();
  const resultLink = firstProject.getByRole("link", { name: "查看结果" });
  await resultLink.click();
  await page.waitForURL(`${baseUrl}/dashboard/projects/overlord/result`);
  await page.locator('[data-page="project-result"]').waitFor();

  await page.goto(`${baseUrl}/dashboard/projects/overlord/result`, { waitUntil: "networkidle" });
  await page.locator('[data-page="project-result"]').waitFor();
  await page.reload({ waitUntil: "networkidle" });
  await page.locator('[data-page="project-result"]').waitFor();

  const metrics = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    viewport: innerWidth,
    headings: document.querySelectorAll('[data-route-heading="true"]').length,
    selected: document.querySelector(".dashboard-sidebar a[aria-current='page']")?.textContent,
    accountButtons: document.querySelectorAll(".dashboard-account button").length,
    sharedShell: Boolean(document.querySelector(".dashboard-sidebar") && document.querySelector(".dashboard-mobile-nav")),
    video: document.querySelectorAll(".project-result-player video").length,
    steps: document.querySelectorAll(".project-result-steps li").length,
    logs: document.querySelectorAll(".project-result-log li").length,
    costItems: document.querySelectorAll(".project-result-cost__item").length,
  }));
  if (metrics.width > metrics.viewport + 1) throw new Error("Desktop horizontal overflow");
  if (metrics.headings !== 1) throw new Error("Result route must have exactly one route heading");
  if (metrics.selected !== "我的项目") throw new Error("Projects nav not active on result route");
  if (!metrics.sharedShell || metrics.accountButtons !== 3) throw new Error("Shared dashboard chrome missing");
  if (metrics.video !== 1 || metrics.steps !== 5 || metrics.logs !== 5 || metrics.costItems !== 4) throw new Error("Result content structure incomplete");

  const video = page.locator(".project-result-player video");
  await page.waitForFunction(() => Number.isFinite(document.querySelector(".project-result-player video")?.duration));
  const mediaDuration = await video.evaluate((element) => element.duration);
  if (Math.abs(mediaDuration - 85) > 0.15) throw new Error(`Result video metadata must be 85 seconds, got ${mediaDuration}`);
  const progressControl = page.locator(".project-result-player__progress input");
  await progressControl.fill("100");
  await page.waitForFunction(() => document.querySelector(".project-result-player video").currentTime > 84.8);
  const seekMetrics = await page.evaluate(() => ({
    currentTime: document.querySelector(".project-result-player video").currentTime,
    duration: document.querySelector(".project-result-player video").duration,
    renderedProgress: Number.parseFloat(document.querySelector(".project-result-player__progress input").style.getPropertyValue("--progress")),
  }));
  if (seekMetrics.currentTime > seekMetrics.duration + 0.01 || seekMetrics.renderedProgress > 100) throw new Error(`Video progress exceeded 100%: ${JSON.stringify(seekMetrics)}`);
  await video.evaluate((element) => { element.currentTime = 0; });
  await page.waitForFunction(() => document.querySelector(".project-result-player video").currentTime < 0.1);

  const assets = await page.evaluate(() => ({
    video: document.querySelector(".project-result-player video")?.currentSrc,
    subtitle: document.querySelector('a[download][data-subtitle-download]')?.href,
  }));
  for (const [kind, url] of Object.entries(assets)) {
    if (!url) throw new Error(`${kind} asset URL missing`);
    const response = await page.request.get(url);
    if (!response.ok()) throw new Error(`${kind} asset returned ${response.status()}`);
    const contentType = response.headers()["content-type"] || "";
    const expectedType = kind === "video" ? /^video\/mp4(?:;|$)/i : /^(application\/(x-subrip|octet-stream)|text\/(plain|vtt))(?:;|$)/i;
    if (!expectedType.test(contentType)) throw new Error(`${kind} MIME type is not reasonable: ${contentType}`);
    if (kind === "subtitle") {
      const vtt = await response.text();
      const cueEnds = [...vtt.matchAll(/-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})/g)].map((match) => vttTimestampToSeconds(match[1]));
      if (cueEnds.length === 0) throw new Error("Subtitle contains no parseable VTT cues");
      const overflow = cueEnds.filter((end) => end > mediaDuration + 0.001);
      if (overflow.length) throw new Error(`Subtitle cues exceed video duration ${mediaDuration}: ${overflow.join(", ")}`);
    }
  }

  const playButton = page.getByRole("button", { name: "播放视频" });
  await playButton.click();
  await page.waitForFunction(() => !document.querySelector(".project-result-player video").paused);
  await page.waitForFunction(() => document.querySelector(".project-result-player video").currentTime > 0.05);
  await page.getByRole("button", { name: "暂停视频" }).click();
  await page.waitForFunction(() => document.querySelector(".project-result-player video").paused);
  await page.getByRole("button", { name: "静音" }).click();
  if (!(await video.evaluate((element) => element.muted))) throw new Error("Mute control failed");
  await video.evaluate((element) => {
    window.__projectResultFullscreenRequested = false;
    element.requestFullscreen = async () => { window.__projectResultFullscreenRequested = true; };
  });
  await page.getByRole("button", { name: "全屏播放" }).click();
  if (!(await page.evaluate(() => window.__projectResultFullscreenRequested))) throw new Error("Fullscreen control did not invoke requestFullscreen");
  await page.getByRole("button", { name: "分享项目" }).click();
  await page.getByRole("status").getByText("分享链接已准备（原型）").waitFor();

  for (const name of ["导出视频", "下载字幕"]) {
    const link = page.getByRole("link", { name }).first();
    if ((await link.getAttribute("download")) === null) throw new Error(`${name} is not a download link`);
  }

  await page.setViewportSize({ width: 390, height: 844 });
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)) throw new Error("Mobile horizontal overflow");
  if (!(await page.locator(".dashboard-mobile-nav").isVisible())) throw new Error("Mobile navigation missing");
  if (browserErrors.length) throw new Error(`Browser errors:\n${browserErrors.join("\n")}`);
  console.log("Project result route, interaction and responsive checks passed");
} finally {
  await browser.close();
}
