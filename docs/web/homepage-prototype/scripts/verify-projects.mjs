import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const targets = ["src/pages/ProjectsPage.jsx", "src/components/projects", "src/styles/projects.css", "src/data/projectsData.js"];
const forbidden = [["reference image", /06-projects-desktop\.png/i], ["data image", /data:image/i], ["base64", /base64/i], ["canvas", /<canvas\b|CanvasRenderingContext2D|drawImage\s*\(/i], ["CSS url background", /background-image\s*:\s*url\s*\(/i], ["SVG bitmap", /<image\b|xlink:href\s*=|href\s*=\s*["']data:image/i]];

async function files(target) { const absolute = path.join(root, target); const stats = await readdir(absolute, { withFileTypes: true }).catch(() => null); if (!stats) return [absolute]; return (await Promise.all(stats.map((entry) => entry.isDirectory() ? files(path.join(target, entry.name)) : [path.join(root, target, entry.name)]))).flat(); }
const violations = [];
for (const target of targets) for (const file of await files(target)) { const source = await readFile(file, "utf8"); for (const [label, regex] of forbidden) if (regex.test(source)) violations.push(`${path.relative(root, file)}: ${label}`); }
if (violations.length) throw new Error(`Projects page anti-paste scan failed:\n${violations.join("\n")}`);
console.log("Projects page anti-paste scan passed");
if (process.env.PROJECTS_SCAN_ONLY === "1") process.exit(0);

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1487, height: 1058 } });
await page.addInitScript(() => localStorage.setItem("narrato.locale", "zh-CN"));
const failures = [];
page.on("pageerror", (error) => failures.push(error.message));
page.on("console", (message) => { if (message.type() === "error") failures.push(message.text()); });
try {
  await page.goto(`${baseUrl}/dashboard/projects`, { waitUntil: "networkidle" });
  await page.locator('[data-route-heading="true"]').waitFor();
  const metrics = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: innerWidth, selected: document.querySelector(".dashboard-sidebar a[aria-current='page']")?.textContent, rows: document.querySelectorAll(".projects-table tbody tr").length, account: document.querySelectorAll(".dashboard-account button").length }));
  if (metrics.width > metrics.viewport + 1) throw new Error("Desktop horizontal overflow");
  if (metrics.selected !== "我的项目") throw new Error("Projects nav not active");
  if (metrics.rows !== 6 || metrics.account !== 3) throw new Error("Project table or shared header missing");
  await page.getByRole("tab", { name: "短剧解说" }).click();
  if (await page.locator(".projects-table tbody tr").count() !== 2) throw new Error("Category filter failed");
  await page.getByPlaceholder("搜索项目名称").fill("悬疑");
  if (await page.locator(".projects-table tbody tr").count() !== 1) throw new Error("Search filter failed");
  await page.setViewportSize({ width: 390, height: 844 });
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)) throw new Error("Mobile horizontal overflow");
  console.log("Projects interaction and responsive checks passed");
} finally { await browser.close(); }
if (failures.length) throw new Error(`Browser errors:\n${failures.join("\n")}`);
