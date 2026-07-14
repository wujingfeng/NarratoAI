import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173";
const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const executablePath =
  process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const homePageSource = await readFile(path.join(projectRoot, "src/pages/HomePage.jsx"), "utf8");
const retiredWorkspaceToast = ["正式工作台接入后", "继续"].join("");
if (homePageSource.includes(retiredWorkspaceToast)) {
  throw new Error("HomePage.jsx 不得保留旧工作台 Toast 文案");
}

const browser = await chromium.launch({ executablePath, headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const failures = [];

await page.route("**/favicon.ico", (route) => route.fulfill({ status: 204 }));

page.on("console", (message) => {
  if (message.type() === "error") {
    const location = message.location().url;
    failures.push(`console.error${location ? ` (${location})` : ""}: ${message.text()}`);
  }
});
page.on("pageerror", (error) => failures.push(`pageerror: ${error.message}`));
page.on("requestfailed", (request) => {
  failures.push(`requestfailed: ${request.method()} ${request.url()} ${request.failure()?.errorText}`);
});
page.on("response", (response) => {
  if (response.status() >= 400) failures.push(`response ${response.status()}: ${response.url()}`);
});

async function expectDashboardAfterClick(locator, label) {
  await locator.click();
  await page.waitForURL(`${baseUrl}/dashboard`);
  if ((await page.locator("h1").textContent()) !== "工作台概览") {
    throw new Error(`${label} 未进入工作台`);
  }
  await page.goBack();
  await page.waitForURL(`${baseUrl}/`);
}

async function expectRouteState({ pathname, title, heading }) {
  await page.waitForURL(`${baseUrl}${pathname}`);
  await page.waitForFunction((expectedTitle) => document.title === expectedTitle, title);
  const routeHeading = page.locator("[data-route-heading]");
  await routeHeading.filter({ hasText: heading }).waitFor();
  await page.waitForFunction(() => document.activeElement === document.querySelector("[data-route-heading]"));
}

async function expectHomeRouteState() {
  await expectRouteState({
    pathname: "/",
    title: "影创工坊｜AI 出片工作台",
    heading: "专为自媒体小白打造的AI 出片工作台",
  });
}

async function verifyRouteHistoryAndNotFound() {
  await page.goto(`${baseUrl}/dashboard`, { waitUntil: "domcontentloaded" });
  await expectRouteState({
    pathname: "/dashboard",
    title: "工作台概览｜影创工坊",
    heading: "工作台概览",
  });

  await page.reload({ waitUntil: "domcontentloaded" });
  await expectRouteState({
    pathname: "/dashboard",
    title: "工作台概览｜影创工坊",
    heading: "工作台概览",
  });

  await page.getByRole("link", { name: "影创工坊" }).click();
  await expectHomeRouteState();

  await page.goBack();
  await expectRouteState({
    pathname: "/dashboard",
    title: "工作台概览｜影创工坊",
    heading: "工作台概览",
  });

  await page.goForward();
  await expectHomeRouteState();

  await page.goto(`${baseUrl}/missing-route`, { waitUntil: "domcontentloaded" });
  await expectRouteState({
    pathname: "/missing-route",
    title: "页面未找到｜影创工坊",
    heading: "页面未找到",
  });

  await page.getByRole("link", { name: "返回官网" }).click();
  await expectHomeRouteState();
  await page.goBack();
  await expectRouteState({
    pathname: "/missing-route",
    title: "页面未找到｜影创工坊",
    heading: "页面未找到",
  });
  await page.getByRole("link", { name: "前往工作台" }).click();
  await expectRouteState({
    pathname: "/dashboard",
    title: "工作台概览｜影创工坊",
    heading: "工作台概览",
  });
}

async function verifyCreationEntries() {
  await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
  const startButtons = page.getByRole("button", { name: /^开始创作/ });
  const startButtonCount = await startButtons.count();
  if (startButtonCount !== 2) {
    throw new Error(`开始创作入口应为 2 个，实际为 ${startButtonCount} 个`);
  }
  await expectDashboardAfterClick(
    startButtons.first(),
    "Hero 开始创作",
  );

  for (const toolId of ["narration", "translation", "remix"]) {
    await page.locator(`#tool-tab-${toolId}`).click();
    const templates = page.getByRole("button", { name: /使用相同模板创作/ });
    const templateCount = await templates.count();
    if (templateCount !== 3) {
      throw new Error(`${toolId} 模板入口应为 3 个，实际为 ${templateCount} 个`);
    }
    for (let index = 0; index < templateCount; index += 1) {
      await expectDashboardAfterClick(templates.nth(index), `${toolId} 模板 ${index + 1}`);
      await page.locator(`#tool-tab-${toolId}`).click();
    }
  }

  const tryButtons = page.getByRole("button", { name: /立即体验/ });
  const tryButtonCount = await tryButtons.count();
  if (tryButtonCount !== 3) {
    throw new Error(`能力入口应为 3 个，实际为 ${tryButtonCount} 个`);
  }
  for (let index = 0; index < tryButtonCount; index += 1) {
    await expectDashboardAfterClick(tryButtons.nth(index), `能力入口 ${index + 1}`);
  }

  await expectDashboardAfterClick(
    startButtons.last(),
    "底部开始创作",
  );
}

async function verifyPreservedWebsiteBehaviors() {
  await page.getByRole("button", { name: "查看案例", exact: true }).first().click();
  await page.locator("#demo").waitFor({ state: "visible" });
  await page.waitForFunction(() => window.scrollY > 0);
  if (new URL(page.url()).pathname !== "/") throw new Error("Hero 查看案例不应离开官网");

  await page.locator("#tool-tab-translation").click();
  if ((await page.locator("#tool-tab-translation").getAttribute("aria-selected")) !== "true") {
    throw new Error("Demo Tab 无法切换");
  }

  await page.getByRole("button", { name: /^播放案例：/ }).first().click();
  await page.getByRole("dialog").waitFor({ state: "visible" });
  await page.getByRole("button", { name: "关闭案例", exact: true }).click();

  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.getByRole("status").getByText("登录流程待接入", { exact: true }).waitFor();
  await page.getByRole("button", { name: "关闭提示" }).click();

  await page.getByRole("button", { name: "价格", exact: true }).first().click();
  await page.getByRole("status").getByText("价格页待接入", { exact: true }).waitFor();
}

try {
  await verifyCreationEntries();
  await verifyPreservedWebsiteBehaviors();
  await verifyRouteHistoryAndNotFound();
  if (failures.length > 0) throw new Error(`路由访问存在浏览器错误:\n${failures.join("\n")}`);
} finally {
  await browser.close();
}

console.log("路由骨架验收通过");
