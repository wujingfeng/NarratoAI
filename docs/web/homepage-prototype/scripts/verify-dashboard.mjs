import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173";
const executablePath =
  process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await chromium.launch({ executablePath, headless: true });
const page = await browser.newPage({ viewport: { width: 1487, height: 1058 } });
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

function check(condition, message) {
  if (!condition) throw new Error(message);
}

async function expectToast(trigger, message) {
  await trigger.click();
  await page.getByRole("status").filter({ hasText: message }).waitFor();
  check(page.url() === `${baseUrl}/dashboard`, `${message} 不得改变路由`);
}

try {
  await page.goto(`${baseUrl}/dashboard`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "工作台概览" }).waitFor();
  check(await page.getByRole("navigation", { name: "工作台主导航" }).count() === 1, "桌面主导航存在");
  check(await page.getByRole("link", { name: "影创工坊" }).getAttribute("href") === "/", "品牌链接返回官网");
  check(await page.locator("[data-project-status]").count() === 3, "最近项目覆盖三态");
  check(await page.getByText("1,280", { exact: true }).count() >= 1, "余额为 1,280");
  check(await page.getByText(/本月.*240.*创作点/).count() >= 1, "月耗为 240");
  check(await page.locator("progress[value='66'][max='100']").count() === 1, "处理中进度有原生语义");

  const before = page.url();
  await page.getByRole("button", { name: /新建创作/ }).first().click();
  await page.getByRole("status").filter({ hasText: "新建创作功能建设中" }).waitFor();
  check(page.url() === before, "未实现功能不得改路由");

  await expectToast(page.getByRole("button", { name: "视频翻译" }).first(), "视频翻译功能建设中");
  await expectToast(page.getByRole("button", { name: "短剧解说" }).first(), "短剧解说功能建设中");
  await page.getByRole("button", { name: "关闭提示" }).click();
  check(await page.getByRole("status").count() === 0, "关闭提示后 Toast 移除 DOM");

  await page.getByRole("button", { name: "关闭促销信息" }).click();
  check(await page.locator("[data-dashboard-banner]").count() === 0, "Banner 关闭后移除 DOM");

  await page.getByRole("link", { name: "影创工坊" }).click();
  await page.waitForURL(`${baseUrl}/`);
  await page.goBack();
  await page.waitForURL(`${baseUrl}/dashboard`);
  await page.getByRole("heading", { name: "工作台概览" }).waitFor();

  if (failures.length > 0) throw new Error(`工作台访问存在浏览器错误:\n${failures.join("\n")}`);
} finally {
  await browser.close();
}

console.log("工作台结构与交互验收通过");
