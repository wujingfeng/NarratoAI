import assert from "node:assert/strict";
import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173";
const executablePath =
  process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const projectId = "prj_video_order";
const browser = await chromium.launch({ executablePath, headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const failures = [];
const orderPayloads = [];

page.setDefaultTimeout(10000);
page.on("console", (message) => {
  if (message.type() === "error") failures.push(`console.error: ${message.text()}`);
});
page.on("pageerror", (error) => failures.push(`pageerror: ${error.message}`));
await page.addInitScript(() => {
  localStorage.setItem("narrato.api.token", "token-video-order");
  localStorage.setItem("narrato.locale", "zh-CN");
});

await page.route("**/mock-oss", (route) => route.fulfill({ status: 204, body: "" }));
await page.route("**/api/v1/**", async (route) => {
  const request = route.request();
  const path = new URL(request.url()).pathname.replace(/^\/api\/v1/, "");
  let data;

  if (path === "/users/me") {
    data = { id: "usr_video_order", email: "order@example.test", credit_balance: 1280 };
  } else if (path === "/products/short-drama-narration/config") {
    data = {
      narration_styles: [{ id: "悬疑/犯罪", name: "悬疑/犯罪", eyebrow: "悬念推进", description: "突出剧情冲突", tags: ["悬疑"], is_custom: false }],
      video_ratios: [{ id: "9:16", name: "9:16" }],
      voices: [{ id: "voice_real", name: "沉稳男声", provider_code: "fake", languages: ["zh-CN"], gender: "male", styles: [], sample_url: null }],
      subtitle_styles: [{ id: "经典白色", name: "经典白色" }],
    };
  } else if (path === "/projects") {
    data = { id: projectId };
  } else if (path === `/projects/${projectId}/uploads/policy`) {
    const body = request.postDataJSON();
    data = {
      url: `${baseUrl}/mock-oss`,
      key: `narrato/api/verify/${body.filename}`,
      fields: {},
      max_size_bytes: 300 * 1024 * 1024,
    };
  } else if (path === `/projects/${projectId}/uploads/complete`) {
    const body = request.postDataJSON();
    const stem = body.filename.replace(/\..+$/, "");
    data = { id: `ast_${stem}`, status: "ready", cdn_url: `${baseUrl}/${body.filename}` };
  } else if (path === `/projects/${projectId}/assets/order`) {
    const body = request.postDataJSON();
    orderPayloads.push(body.asset_ids);
    data = { asset_ids: body.asset_ids };
  } else if (path === `/projects/${projectId}/cost-estimate`) {
    data = { credits: 20, total_seconds: 0, estimated_output_seconds: 0, credits_per_minute: 20 };
  } else if (path === `/projects/${projectId}/stage`) {
    data = {
      project_id: projectId,
      project_title: "02.mp4",
      project_status: "ready",
      current_stage: "settings",
      execution_mode: "manual",
      workflow_state: null,
      failure_code: null,
      updated_at: "2026-08-04T04:00:00Z",
      stages: ["created", "settings", "analysis", "edit", "generate", "export"],
      analysis_tasks: [],
      video_assets: [
        { id: "ast_02", filename: "02.mp4", cdn_url: "", duration_seconds: 0 },
        { id: "ast_01", filename: "01.mp4", cdn_url: "", duration_seconds: 0 },
      ],
    };
  } else if (path === `/projects/${projectId}/narration/settings`) {
    data = { background_music: null, execution_mode: "manual" };
  } else {
    failures.push(`unexpected API request: ${request.method()} ${path}`);
    data = {};
  }

  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ code: "OK", message: "ok", data, request_id: "req_video_order" }),
  });
});

try {
  await page.goto(`${baseUrl}/dashboard/narration/settings`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "短剧解说设置参数" }).waitFor();
  await page.getByLabel("选择视频文件").setInputFiles([
    { name: "01.mp4", mimeType: "video/mp4", buffer: Buffer.from("first") },
    { name: "02.mp4", mimeType: "video/mp4", buffer: Buffer.from("second") },
  ]);

  const rows = page.locator("[data-video-row]");
  await rows.nth(1).waitFor();
  await page.waitForFunction(() => document.querySelectorAll("[data-video-row]").length === 2);
  await page.waitForTimeout(100);
  assert.deepEqual(orderPayloads.at(-1), ["ast_01", "ast_02"], "上传完成后必须同步可见顺序");

  const firstHandle = page.getByRole("button", { name: "调整 01.mp4 的顺序" });
  const secondHandle = page.getByRole("button", { name: "调整 02.mp4 的顺序" });
  const firstBox = await firstHandle.boundingBox();
  const secondBox = await secondHandle.boundingBox();
  assert.ok(firstBox && secondBox, "拖拽手柄必须可见");
  await page.mouse.move(firstBox.x + firstBox.width / 2, firstBox.y + firstBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(secondBox.x + secondBox.width / 2, secondBox.y + secondBox.height / 2, { steps: 8 });
  await page.mouse.up();
  await page.waitForFunction(() => document.querySelector("[data-video-row] strong")?.textContent === "02.mp4");
  await page.waitForTimeout(100);
  assert.deepEqual(orderPayloads.at(-1), ["ast_02", "ast_01"], "键盘拖动后的顺序必须持久化");

  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    const overflow = await page.evaluate(() => ({
      document: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      body: document.body.scrollWidth - document.body.clientWidth,
    }));
    assert.ok(overflow.document <= 1 && overflow.body <= 1, `${width}px 页面不应横向溢出：${JSON.stringify(overflow)}`);
  }

  const nextButton = page.getByRole("button", { name: "下一步：设置参数" });
  await nextButton.waitFor();
  await page.waitForFunction(() => !document.querySelector(".create-summary__next")?.disabled);
  await nextButton.click();
  await page.waitForURL(`${baseUrl}/dashboard/narration/settings?projectId=${projectId}`);
  assert.deepEqual(orderPayloads.at(-1), ["ast_02", "ast_01"], "进入设置页前必须再次确认最终顺序");
  assert.deepEqual(failures, []);
} finally {
  await browser.close();
}

console.log("PASS persisted and responsive video source ordering");
