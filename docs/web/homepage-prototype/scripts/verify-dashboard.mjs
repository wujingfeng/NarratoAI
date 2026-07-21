import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173";
const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const scanTargets = ["src/pages/DashboardPage.jsx", "src/components/dashboard", "src/data/dashboardData.js", "src/styles/dashboard.css", "public"];
const forbidden = [["dashboard reference image", /04-dashboard-desktop(?:\.png)?/i], ["mobile reference image", /28-dashboard-mobile(?:\.png)?/i], ["data image", /data:image/i], ["base64", /base64/i], ["canvas", /<canvas\b|CanvasRenderingContext2D|drawImage\s*\(/i], ["CSS url background", /background-image\s*:\s*url\s*\(/i], ["SVG bitmap", /<image\b|xlink:href\s*=|href\s*=\s*["']data:image/i]];
const sourceExtensions = new Set([".js", ".jsx", ".mjs", ".css", ".html", ".svg", ".json", ".txt"]);

async function filesIn(target) {
  const stat = await readdir(target, { withFileTypes: true });
  return (await Promise.all(stat.map(async (entry) => {
    const entryPath = path.join(target, entry.name);
    return entry.isDirectory() ? filesIn(entryPath) : [entryPath];
  }))).flat();
}

const violations = [];
for (const target of scanTargets) {
  const absolute = path.join(projectRoot, target);
  let files = [];
  try { files = await filesIn(absolute); } catch (error) { if (error.code === "ENOTDIR") files = [absolute]; else throw error; }
  for (const file of files) {
    if (!sourceExtensions.has(path.extname(file).toLowerCase())) continue;
    const source = await readFile(file, "utf8");
    for (const [label, matcher] of forbidden) if (matcher.test(source)) violations.push(`${path.relative(projectRoot, file)}: ${label}`);
  }
}
if (violations.length) throw new Error(`Dashboard anti-paste scan failed:\n${violations.join("\n")}`);
console.log("Dashboard anti-paste scan passed");
if (process.env.DASHBOARD_SCAN_ONLY === "1") process.exit(0);

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true });
const failures = [];
const viewports = [{ width: 375, height: 844 }, { width: 768, height: 1024 }, { width: 1024, height: 900 }, { width: 1440, height: 1000 }];

try {
  for (const viewport of viewports) {
    const page = await browser.newPage({ viewport });
    page.on("pageerror", (error) => failures.push(`${viewport.width}: pageerror ${error.message}`));
    page.on("console", (message) => { if (message.type() === "error") failures.push(`${viewport.width}: console ${message.text()}`); });
    await page.addInitScript(() => localStorage.setItem("narrato.locale", "zh-CN"));
    await page.goto(`${baseUrl}/dashboard`, { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "工作台概览" }).waitFor();
    const metrics = await page.evaluate(() => {
      const visible = (element) => {
        const rect = element?.getBoundingClientRect();
        const style = element && getComputedStyle(element);
        return Boolean(rect && style && style.display !== "none" && rect.width > 0 && rect.height > 0);
      };
      const tools = [...document.querySelectorAll(".featured-tools__card")].map((item) => item.getBoundingClientRect());
      const cases = [...document.querySelectorAll(".case-masonry__card")].map((item) => item.getBoundingClientRect());
      const videos = [...document.querySelectorAll(".case-masonry video")];
      const marketingRect = document.querySelector(".dashboard-marketing")?.getBoundingClientRect();
      const creationRect = document.querySelector(".creation-studio")?.getBoundingClientRect();
      return {
        pageWidth: document.documentElement.scrollWidth, viewportWidth: innerWidth,
        sidebar: visible(document.querySelector(".dashboard-sidebar")),
        mobileNav: visible(document.querySelector(".dashboard-mobile-nav")),
        header: visible(document.querySelector(".dashboard-header")),
        marketing: visible(document.querySelector(".dashboard-marketing .promotion-banner")),
        creationCards: document.querySelectorAll(".creation-studio__card").length,
        toolCards: tools.length, tools,
        marketingBottom: marketingRect?.bottom ?? 0,
        creationTop: creationRect?.top ?? 0,
        cases: cases.length, caseWidths: cases.map((item) => item.width),
        caseColumns: [...new Set(cases.map((item) => Math.round(item.left)))],
        videoContracts: videos.map((video) => ({ autoplay: video.autoplay, muted: video.muted, loop: video.loop, playsInline: video.playsInline, preload: video.preload })),
      };
    });
    const assert = (condition, message) => { if (!condition) throw new Error(`${viewport.width}px: ${message}`); };
    assert(metrics.pageWidth <= metrics.viewportWidth + 1, "page must not overflow horizontally");
    assert(metrics.header && metrics.marketing, "header and marketing panel must be visible");
    assert(metrics.creationCards === 3, "exactly three creation entry cards must render");
    assert(metrics.toolCards === 3, "featured tools must render exactly AI image, AI video, AI voice");
    assert(metrics.cases === 6, "six real case cards must render");
    if (viewport.width <= 699) assert(metrics.caseColumns.length === 2, "mobile masonry must keep two visible columns");
    assert(metrics.videoContracts.length === 6 && metrics.videoContracts.every((video) => video.autoplay && video.muted && video.loop && video.playsInline && video.preload === "auto"), "case videos must autoplay muted, loop, play inline, and preload automatically");
    if (viewport.width > 1024) {
      assert(metrics.sidebar && !metrics.mobileNav, "desktop must retain sidebar and hide mobile nav");
      assert(metrics.tools.every((item, index) => index === 0 || item.left >= metrics.tools[index - 1].right), "desktop tool cards must not overlap");
      assert(Math.max(...metrics.caseWidths) - Math.min(...metrics.caseWidths) < 2, "each masonry column must keep a uniform media width");
    } else assert(!metrics.sidebar && metrics.mobileNav, "tablet and mobile must use mobile navigation");
    if (viewport.width <= 820) assert(metrics.creationTop >= metrics.marketingBottom, "narrow layout must stack marketing above creation cards");

    const hiddenVideoMetrics = await page.locator(".case-masonry video").evaluateAll((videos) => {
      videos.forEach((video) => { video.hidden = true; });
      return [...document.querySelectorAll(".case-masonry__card")].map((card) => {
        const style = getComputedStyle(card);
        const rect = card.getBoundingClientRect();
        return {
          visible: style.display !== "none" && rect.width > 0 && rect.height > 0,
          caption: !card.querySelector(".case-masonry__caption"),
          play: !card.querySelector(".case-masonry__play"),
        };
      });
    });
    assert(hiddenVideoMetrics.length === 6 && hiddenVideoMetrics.every((item) => item.visible && item.caption && item.play), "hidden case videos must leave usable cards without a text description or overlay icon");
    await page.close();
  }
  const failurePage = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await failurePage.addInitScript(() => localStorage.setItem("narrato.locale", "zh-CN"));
  await failurePage.route("**/161528_a755036523c0e80a332e95ba206d7ff8.mp4", (route) => route.fulfill({ status: 404, contentType: "video/mp4", body: "" }));
  await failurePage.goto(`${baseUrl}/dashboard`, { waitUntil: "networkidle" });
  await failurePage.locator(".case-video__fallback").waitFor();
  const failedImageCard = await failurePage.locator(".case-masonry__card").first().evaluate((card) => ({
    fallback: Boolean(card.querySelector(".case-video__fallback")),
    caption: !card.querySelector(".case-masonry__caption"),
    play: !card.querySelector(".case-masonry__play"),
  }));
  if (!failedImageCard.fallback || !failedImageCard.caption || !failedImageCard.play) throw new Error("failed case video must retain fallback without a text description or overlay icon");
  await failurePage.close();
  if (failures.length) throw new Error(failures.join("\n"));
  console.log("Dashboard responsive verification passed (375, 768, 1024, 1440)");
} finally { await browser.close(); }
