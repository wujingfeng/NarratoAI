import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173";
const executablePath =
  process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
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

try {
  await page.goto(`${baseUrl}/dashboard`, { waitUntil: "domcontentloaded" });
  if ((await page.locator("h1").textContent()) !== "工作台概览") {
    throw new Error("/dashboard 应渲染工作台概览而不是官网");
  }
  await page.goto(`${baseUrl}/missing-route`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "页面未找到" }).waitFor();
  if (failures.length > 0) throw new Error(`路由访问存在浏览器错误:\n${failures.join("\n")}`);
} finally {
  await browser.close();
}

console.log("路由骨架验收通过");
