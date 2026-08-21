import assert from "node:assert/strict";
import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173";
const executablePath =
  process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const projectId = "prj_auto_verify";
const browser = await chromium.launch({ executablePath, headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const failures = [];
const visitedPaths = [];
let startedAt = 0;
let startPayload = null;

page.setDefaultTimeout(10000);
page.on("console", (message) => {
  if (message.type() === "error") failures.push(`console.error: ${message.text()}`);
});
page.on("pageerror", (error) => failures.push(`pageerror: ${error.message}`));
page.on("framenavigated", (frame) => {
  if (frame === page.mainFrame()) visitedPaths.push(new URL(frame.url()).pathname);
});

await page.addInitScript(() => {
  localStorage.setItem("narrato.api.token", "token-auto-verify");
  localStorage.setItem("narrato.locale", "zh-CN");
});

await page.route("**/source.mp4", (route) => route.fulfill({ status: 200, contentType: "video/mp4", body: "" }));
await page.route("**/final.mp4", (route) => route.fulfill({ status: 200, contentType: "video/mp4", body: "" }));
await page.route("**/api/v1/**", async (route) => {
  const request = route.request();
  const url = new URL(request.url());
  const path = url.pathname.replace(/^\/api\/v1/, "");
  let data;

  if (path === "/users/me") {
    data = { id: "usr_auto_verify", email: "auto@example.test", credit_balance: 1280 };
  } else if (path === "/products/short-drama-narration/config") {
    data = {
      narration_styles: [{ id: "悬疑/犯罪", name: "悬疑/犯罪", eyebrow: "悬念推进", description: "突出剧情冲突", tags: ["悬疑"], is_custom: false }],
      original_sound_ratios: [0, 10, 20, 30, 40, 50, 60, 70, 80, 90],
      video_ratios: [{ id: "9:16", name: "9:16" }],
      voices: [{ id: "voice_real", name: "沉稳男声", provider_code: "fake", languages: ["zh-CN"], gender: "male", styles: [], sample_url: null }],
      subtitle_styles: [{ id: "经典白色", name: "经典白色" }],
    };
  } else if (path === `/projects/${projectId}/cost-estimate`) {
    data = { credits: 20, total_seconds: 60, estimated_output_seconds: 10, credits_per_minute: 20 };
  } else if (path === `/projects/${projectId}/narration/settings/start-analysis`) {
    startPayload = request.postDataJSON();
    startedAt = Date.now();
    data = { workflow_id: "wfl_auto_verify" };
  } else if (path === `/projects/${projectId}/narration/settings`) {
    data = {
      background_music: null,
      narration_style: "悬疑/犯罪",
      original_sound_ratio: 30,
      video_ratio: "9:16",
      voice_id: "voice_real",
      subtitle_style: "经典白色",
      custom_style: null,
      requirements: null,
      execution_mode: "manual",
    };
  } else if (path === `/projects/${projectId}/stage`) {
    const elapsed = startedAt ? Date.now() - startedAt : 0;
    const current = !startedAt ? "settings" : elapsed < 1200 ? "analysis" : elapsed < 4200 ? "render" : "export";
    data = {
      project_id: projectId,
      project_title: "自动模式验收.mp4",
      project_status: current === "export" ? "completed" : current === "render" ? "rendering" : "analyzing",
      current_stage: current,
      execution_mode: startedAt ? "auto" : "manual",
      workflow_state: current === "export" ? "completed" : "running",
      failure_code: null,
      updated_at: "2026-08-04T04:00:00Z",
      stages: ["created", "settings", "analysis", "edit", "generate", "export"],
      analysis_tasks: ["subtitle_recognition", "plot_structure", "conflict_highlights", "highlight_scoring", "script_generation"].map((id) => ({
        id,
        name: id,
        state: current === "analysis" ? "running" : "completed",
        updated_at: "2026-08-04T04:00:00Z",
        error_code: null,
      })),
      video_assets: [{ id: "ast_video", filename: "自动模式验收.mp4", cdn_url: `${baseUrl}/source.mp4`, duration_seconds: 60 }],
    };
  } else if (path === `/projects/${projectId}/result`) {
    data = {
      project_id: projectId,
      artifacts: [
        { id: "art_video", kind: "video", cdn_url: `${baseUrl}/final.mp4` },
        { id: "art_subtitle", kind: "subtitle", cdn_url: `${baseUrl}/final.srt` },
        { id: "art_voice", kind: "voice", cdn_url: `${baseUrl}/final.wav` },
        { id: "art_timeline", kind: "timeline", cdn_url: `${baseUrl}/timeline.json` },
      ],
    };
  } else {
    failures.push(`unexpected API request: ${request.method()} ${path}`);
    data = {};
  }

  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ code: "OK", message: "ok", data, request_id: "req_auto_verify" }),
  });
});

try {
  await page.goto(`${baseUrl}/dashboard/narration/settings?projectId=${projectId}`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "短剧解说设置参数" }).waitFor();
  await page.waitForFunction(() => document.title === "短剧解说设置｜影创工坊");

  const originalSoundRatio = page.getByRole("group", { name: "原片占比" });
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.waitForFunction(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
    );
    const bounds = await originalSoundRatio.boundingBox();
    assert.ok(bounds, `${width}px 下原片占比控件必须可见`);
    assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= width + 1, `${width}px 下原片占比控件不得横向溢出`);
  }

  await originalSoundRatio.getByRole("combobox").selectOption("70");
  await page.getByText("自动模式", { exact: true }).click();
  const startButton = page.getByRole("button", { name: "使用当前设置，全自动生成" });
  await startButton.waitFor();
  await startButton.click();

  await page.waitForURL(`${baseUrl}/dashboard/narration/analysis?projectId=${projectId}`);
  await page.waitForFunction(() => document.title === "AI 分析｜影创工坊");
  await page.getByText("自动模式已启动，分析完成后将继续生成", { exact: true }).waitFor();
  assert.equal(startPayload?.execution_mode, "auto", "启动请求必须冻结 auto 模式");
  assert.equal(startPayload?.original_sound_ratio, 70, "启动请求必须冻结用户选择的原片占比");

  await page.waitForURL(`${baseUrl}/dashboard/narration/generate?projectId=${projectId}`, { timeout: 7000 });
  await page.waitForFunction(() => document.title === "生成视频｜影创工坊");
  await page.getByText("自动模式", { exact: true }).waitFor();

  await page.waitForURL(`${baseUrl}/dashboard/narration/export?projectId=${projectId}`, { timeout: 8000 });
  await page.waitForFunction(() => document.title === "导出完成｜影创工坊");
  await page.getByRole("heading", { name: "导出完成" }).waitFor();
  assert.equal(await page.getByRole("list", { name: "已登记产物" }).getByRole("listitem").count(), 4);
  assert.equal(await page.getByRole("link", { name: "下载" }).count(), 4);
  assert.equal(visitedPaths.includes("/dashboard/narration/editor"), false, "自动模式不得进入人工编辑页");
  assert.deepEqual(failures, []);
} finally {
  await browser.close();
}

console.log("PASS auto mode settings -> analysis -> render -> export flow");
