import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173";
const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const executablePath =
  process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const authoredTargets = [
  "src/pages/CreatePage.jsx",
  "src/components/create",
  "src/styles/create.css",
  "src/data/createData.js",
];
const forbidden = [
  ["参考图文件名", /05-new-creation-desktop\.png/i],
  ["data image", /data:image/i],
  ["base64", /base64/i],
  ["canvas", /<canvas\b|CanvasRenderingContext2D|drawImage\s*\(/i],
  ["CSS url 背景", /background-image\s*:\s*url\s*\(/i],
  ["SVG 内嵌位图", /<image\b|xlink:href\s*=|href\s*=\s*["']data:image/i],
];

async function collectFiles(target) {
  const entries = await readdir(target, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const entryPath = path.join(target, entry.name);
    if (entry.isDirectory()) files.push(...(await collectFiles(entryPath)));
    else if (entry.isFile()) files.push(entryPath);
  }
  return files;
}

async function verifyAuthoredSources() {
  const files = [];
  for (const target of authoredTargets) {
    const absoluteTarget = path.join(projectRoot, target);
    try {
      files.push(...(await collectFiles(absoluteTarget)));
    } catch (error) {
      if (error.code === "ENOTDIR") files.push(absoluteTarget);
      else if (error.code !== "ENOENT") throw error;
    }
  }

  const violations = [];
  for (const file of files) {
    const source = await readFile(file, "utf8");
    for (const [label, pattern] of forbidden) {
      const match = source.match(pattern);
      if (match) violations.push(`${path.relative(projectRoot, file)}: ${label} (${match[0]})`);
    }
  }
  if (violations.length) throw new Error(`Create page 反贴图扫描失败:\n${violations.join("\n")}`);
  console.log(`Create page 反贴图扫描通过（${files.length} files）`);
  const createSource = await readFile(path.join(projectRoot, "src/pages/CreatePage.jsx"), "utf8");
  check(createSource.includes("URL.createObjectURL"), "创建页必须使用 URL.createObjectURL 读取本地媒体");
  check(createSource.includes("loadedmetadata"), "创建页必须监听 loadedmetadata");
  check(createSource.includes("URL.revokeObjectURL"), "创建页必须释放 object URL");
  check(createSource.includes('durationLabel: "--:--"'), "真实文件初始时长必须保持 --:--");
}

function check(condition, message) {
  if (!condition) throw new Error(message);
}

await verifyAuthoredSources();
if (process.env.CREATE_SCAN_ONLY === "1") process.exit(0);

const browser = await chromium.launch({ executablePath, headless: true });
const page = await browser.newPage({ viewport: { width: 1487, height: 1058 } });
await page.addInitScript(() => localStorage.setItem("narrato.locale", "zh-CN"));
page.setDefaultTimeout(8000);
const failures = [];
const apiRequests = [];

page.on("console", (message) => {
  if (message.type() === "error") failures.push(`console.error: ${message.text()}`);
});
page.on("pageerror", (error) => failures.push(`pageerror: ${error.message}`));
page.on("requestfailed", (request) => {
  failures.push(`requestfailed: ${request.method()} ${request.url()} ${request.failure()?.errorText}`);
});
page.on("request", (request) => {
  if (["xhr", "fetch"].includes(request.resourceType())) apiRequests.push(request.url());
});

try {
  await page.goto(`${baseUrl}/dashboard/create`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "创建新的 AI 视频" }).waitFor();
  const routeHeadingOutline = await page.locator("[data-route-heading]").evaluate((element) =>
    getComputedStyle(element).outlineStyle,
  );
  check(routeHeadingOutline === "none", "程序化聚焦的可见页面标题不得出现浏览器默认描边");

  const desktopMetrics = await page.evaluate(() => {
    const rect = (selector) => document.querySelector(selector).getBoundingClientRect();
    const typeCards = [...document.querySelectorAll(".create-type-card")].map((element) => element.getBoundingClientRect());
    const sidebar = rect(".dashboard-sidebar");
    const main = rect(".create-main");
    const dropzone = rect(".create-video-dropzone");
    const summary = rect(".create-summary");
    return {
      pageWidth: document.documentElement.scrollWidth,
      viewportWidth: innerWidth,
      sidebar: { left: sidebar.left, right: sidebar.right, width: sidebar.width },
      mainLeft: main.left,
      typeTops: typeCards.map(({ top }) => top),
      dropzone: { left: dropzone.left, right: dropzone.right, width: dropzone.width },
      summary: { left: summary.left, right: summary.right, width: summary.width },
      mobileNavDisplay: getComputedStyle(document.querySelector(".dashboard-mobile-nav")).display,
    };
  });
  check(desktopMetrics.pageWidth <= desktopMetrics.viewportWidth + 1, "桌面不得横向溢出");
  check(desktopMetrics.sidebar.width >= 220 && desktopMetrics.sidebar.width <= 280, "桌面复用工作台侧栏宽度");
  check(desktopMetrics.mainLeft >= desktopMetrics.sidebar.right, "创建页主体不得压入侧栏");
  check(Math.max(...desktopMetrics.typeTops) - Math.min(...desktopMetrics.typeTops) <= 2, "三个类型卡片必须位于同一行");
  check(desktopMetrics.dropzone.width > desktopMetrics.summary.width * 2, "素材区必须明显宽于创作小结");
  check(desktopMetrics.summary.left > desktopMetrics.dropzone.right, "创作小结必须位于素材区右侧");
  check(desktopMetrics.mobileNavDisplay === "none", "桌面必须隐藏移动底栏");

  const typeButtons = page.locator("[data-creation-type]");
  check((await typeButtons.count()) === 3, "创建类型必须精确包含 3 个按钮");
  check(
    (await page.locator('[data-creation-type="narration"]').getAttribute("aria-pressed")) === "true",
    "短剧解说必须默认选中",
  );
  await page.locator('[data-creation-type="remix"]').click();
  check(
    (await page.locator('[data-creation-type="remix"]').getAttribute("aria-pressed")) === "true",
    "短剧混剪点击后必须选中",
  );
  await page.locator('[data-creation-type="narration"]').click();

  const videoInput = page.locator('input[type="file"][accept*="video"]');
  await videoInput.setInputFiles([
    { name: "夜景片段.mp4", mimeType: "video/mp4", buffer: Buffer.from("video-a") },
    { name: "对白片段.mov", mimeType: "video/quicktime", buffer: Buffer.from("video-b") },
  ]);
  check((await page.locator("[data-video-row]").count()) === 5, "选择两个视频后必须追加到 3 个演示视频之后");
  check((await page.locator(".create-summary__credits").textContent()).trim().startsWith("107"), "追加两个待识别视频后预计消耗必须更新");
  await videoInput.setInputFiles({ name: "超限片段.mp4", mimeType: "video/mp4", buffer: Buffer.from("overflow") });
  await page.getByRole("status").filter({ hasText: "短剧解说最多上传 5 个视频" }).waitFor();
  check((await page.locator("[data-video-row]").count()) === 5, "短剧解说第 6 个视频必须被拒绝");
  await page.locator("[data-video-row]").nth(3).getByRole("button", { name: /删除/ }).click();
  check((await page.locator("[data-video-row]").count()) === 4, "删除后视频行数必须减少");
  check((await page.locator("[data-video-index]").last().textContent()) === "04", "删除后序号必须重新排列");
  check((await page.locator(".create-summary__credits").textContent()).trim().startsWith("97"), "删除待识别视频后预计消耗必须回落");

  await page.locator('[data-creation-type="translation"]').click();
  check(
    (await page.locator('[data-creation-type="translation"]').getAttribute("aria-pressed")) === "true",
    "素材超限时仍必须允许切换到视频翻译",
  );
  await page.getByRole("button", { name: "下一步：设置参数" }).click();
  await page.getByRole("status").filter({ hasText: "视频翻译当前有 4 个视频，最多支持 1 个" }).waitFor();

  while ((await page.locator("[data-video-row]").count()) > 1) {
    await page.locator("[data-video-row]").last().getByRole("button", { name: /删除/ }).click();
  }
  await page.locator('[data-creation-type="translation"]').click();
  check(
    (await page.locator('[data-creation-type="translation"]').getAttribute("aria-pressed")) === "true",
    "仅剩一个视频后必须允许切换到视频翻译",
  );
  await page.getByRole("button", { name: "下一步：设置参数" }).click();
  await page.getByRole("status").filter({ hasText: "参数设置功能建设中" }).waitFor();
  await videoInput.setInputFiles({ name: "翻译超限.mp4", mimeType: "video/mp4", buffer: Buffer.from("translation-overflow") });
  await page.getByRole("status").filter({ hasText: "视频翻译最多上传 1 个视频" }).waitFor();
  check((await page.locator("[data-video-row]").count()) === 1, "视频翻译第 2 个视频必须被拒绝");

  await page.locator('[data-creation-type="remix"]').click();
  const remixFiles = Array.from({ length: 9 }, (_, index) => ({
    name: `混剪片段-${index + 1}.mp4`,
    mimeType: "video/mp4",
    buffer: Buffer.from(`remix-${index + 1}`),
  }));
  await videoInput.setInputFiles(remixFiles);
  check((await page.locator("[data-video-row]").count()) === 10, "短剧混剪必须允许上传至 10 个视频");
  await videoInput.setInputFiles({ name: "混剪超限.mp4", mimeType: "video/mp4", buffer: Buffer.from("remix-overflow") });
  await page.getByRole("status").filter({ hasText: "短剧混剪最多上传 10 个视频" }).waitFor();
  check((await page.locator("[data-video-row]").count()) === 10, "短剧混剪第 11 个视频必须被拒绝");

  check((await page.locator(".create-subtitle-section").count()) === 0, "独立字幕上传区域必须移除");
  const firstVideoRow = page.locator("[data-video-row]").first();
  await firstVideoRow.locator('input[type="file"][accept*=".srt"]').setInputFiles({
    name: "自定义字幕.srt",
    mimeType: "application/x-subrip",
    buffer: Buffer.from("1\n00:00:00,000 --> 00:00:01,000\n字幕"),
  });
  await firstVideoRow.getByText("自定义字幕.srt", { exact: true }).waitFor();
  check(
    (await page.getByText("点击上传字幕，或AI 智能识别", { exact: true }).count()) >= 1,
    "未上传字幕的视频必须显示新的上传提示文案",
  );

  await page.getByRole("button", { name: "下一步：设置参数" }).click();
  await page.getByRole("status").filter({ hasText: "参数设置功能建设中" }).waitFor();
  check(page.url() === `${baseUrl}/dashboard/create`, "下一步不得改变路由");
  check(apiRequests.length === 0, `本地交互不得发起 API 请求：${apiRequests.join(", ")}`);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${baseUrl}/dashboard/create`, { waitUntil: "networkidle" });
  const mobileMetrics = await page.evaluate(() => {
    const cards = [...document.querySelectorAll(".create-type-card")].map((element) => element.getBoundingClientRect());
    const summary = document.querySelector(".create-summary").getBoundingClientRect();
    const form = document.querySelector(".create-form").getBoundingClientRect();
    return {
      pageWidth: document.documentElement.scrollWidth,
      viewportWidth: innerWidth,
      sidebarDisplay: getComputedStyle(document.querySelector(".dashboard-sidebar")).display,
      mobileNavDisplay: getComputedStyle(document.querySelector(".dashboard-mobile-nav")).display,
      cardTops: cards.map(({ top }) => top),
      formBottom: form.bottom,
      summaryTop: summary.top,
    };
  });
  check(mobileMetrics.pageWidth <= mobileMetrics.viewportWidth + 1, "移动端不得横向溢出");
  check(mobileMetrics.sidebarDisplay === "none", "移动端必须隐藏桌面侧栏");
  check(mobileMetrics.mobileNavDisplay !== "none", "移动端必须显示底部导航");
  check(new Set(mobileMetrics.cardTops.map(Math.round)).size === 3, "移动端三个类型卡片必须纵向排列");
  check(mobileMetrics.summaryTop >= mobileMetrics.formBottom, "移动端创作小结必须位于表单下方");
  check(failures.length === 0, `页面存在浏览器错误：\n${failures.join("\n")}`);
} finally {
  await browser.close();
}

console.log("新建创作页面交互验收通过");
