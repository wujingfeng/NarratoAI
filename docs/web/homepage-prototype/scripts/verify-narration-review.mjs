import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const artifactDirectory = path.join(projectRoot, "artifacts", "narration-review");
const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173";
const executablePath = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const projectId = "prj_review_verify";
const assetOneUrl = `${baseUrl}/media/narration-editor/%E5%8F%A4%E5%A2%93%E8%BF%B7%E5%AE%AB%E9%9C%87%E5%85%A8%E7%90%831.mp4`;
const assetTwoUrl = `${baseUrl}/media/narration-editor/%E5%8F%A4%E5%A2%93%E8%BF%B7%E5%AE%AB%E9%9C%87%E5%85%A8%E7%90%832.mp4`;

let currentStage = "edit";
let renderSubmissions = 0;
const saves = [];
let delayedSave = null;
let delayedRender = null;

function createBarrier(assign) {
  let markStarted;
  let release;
  const started = new Promise((resolve) => { markStarted = resolve; });
  const released = new Promise((resolve) => { release = resolve; });
  assign({ markStarted, released });
  return { started, release };
}
let draftContent = {
  version: 1,
  clips: [
    { id: "video-1", track_id: "video", start: 0, duration: 4, source_start: 1, asset_id: "asset-1", asset_url: assetOneUrl, region_id: "region-1" },
    { id: "script-1", track_id: "script", start: 0, duration: 4, text: "第一段解说", picture: "人物走进大厅", original_sound: false, region_id: "region-1" },
    { id: "video-2", track_id: "video", start: 4, duration: 5, source_start: 8, asset_id: "asset-2", asset_url: assetTwoUrl, region_id: "region-2" },
    { id: "script-2", track_id: "script", start: 4, duration: 5, text: "第二段解说", picture: "镜头切换到远景", original_sound: true, region_id: "region-2" },
    { id: "bgm-1", track_id: "bgm", start: 0, duration: 9, source_start: 0, asset_id: "bgm-1", asset_url: `${baseUrl}/media/narration-editor/0e5bf3db017e0e593c4eef4144d7c68a.mp3`, region_id: "bgm-region" },
  ],
  subtitles: [
    { start: 0, end: 4, text: "第一段人工字幕", region_id: "region-1" },
    { start: 4, end: 9, text: "第二段人工字幕", region_id: "region-2" },
  ],
  settings: { voice_role: "voice-1", volume: 100, rate: 1, subtitle_style: "classic", video_ratio: "9:16" },
};

await mkdir(artifactDirectory, { recursive: true });
const browser = await chromium.launch({ executablePath, headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const failures = [];
page.setDefaultTimeout(15_000);
page.on("pageerror", (error) => failures.push(`pageerror: ${error.message}`));
page.on("console", (message) => {
  if (message.type() === "error" && !/Failed to load resource/.test(message.text())) failures.push(`console.error: ${message.text()}`);
});

await page.addInitScript(() => {
  localStorage.setItem("narrato.api.token", "token-review-verify");
  localStorage.setItem("narrato.locale", "zh-CN");
});

await page.route("**/api/v1/**", async (route) => {
  const request = route.request();
  const apiPath = new URL(request.url()).pathname.replace(/^\/api\/v1/, "");
  let data;
  if (apiPath === "/users/me") {
    data = { id: "user-review", email: "review@example.test", credit_balance: 1000 };
  } else if (apiPath === `/projects/${projectId}/stage`) {
    data = {
      project_id: projectId,
      project_title: "人工核对验收项目",
      current_stage: currentStage,
      project_status: currentStage === "edit" ? "waiting_for_edit" : "rendering",
      video_assets: [
        { id: "asset-1", filename: "第一集.mp4", cdn_url: assetOneUrl, duration_seconds: 120 },
        { id: "asset-2", filename: "第二集.mp4", cdn_url: assetTwoUrl, duration_seconds: 180 },
      ],
    };
  } else if (apiPath === `/projects/${projectId}/editor` && request.method() === "GET") {
    data = { draft_id: "draft-review", content: draftContent, locked: false };
  } else if (apiPath === `/projects/${projectId}/editor/save` && request.method() === "POST") {
    if (delayedSave) {
      const barrier = delayedSave;
      delayedSave = null;
      barrier.markStarted();
      await barrier.released;
    }
    draftContent = request.postDataJSON().content;
    saves.push(structuredClone(draftContent));
    data = { draft_id: "draft-review" };
  } else if (apiPath === `/projects/${projectId}/render/submit` && request.method() === "POST") {
    if (delayedRender) {
      const barrier = delayedRender;
      delayedRender = null;
      barrier.markStarted();
      await barrier.released;
    }
    renderSubmissions += 1;
    currentStage = "render";
    data = { accepted: true };
  } else {
    failures.push(`unexpected API request: ${request.method()} ${apiPath}`);
    data = {};
  }
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ code: "OK", message: "ok", data, request_id: "req-review" }),
  });
});

const assertNoPageOverflow = async (width) => {
  await page.setViewportSize({ width, height: width <= 768 ? 1000 : 900 });
  await page.waitForTimeout(80);
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  assert.ok(dimensions.scrollWidth <= dimensions.clientWidth + 1, `${width}px viewport has horizontal overflow: ${JSON.stringify(dimensions)}`);
  await page.screenshot({ path: path.join(artifactDirectory, `review-${width}.png`), fullPage: true });
};

const waitForSaveAfter = async (count) => {
  const deadline = Date.now() + 3_000;
  while (saves.length <= count && Date.now() < deadline) await page.waitForTimeout(20);
  assert.ok(saves.length > count, `expected a save after request ${count}`);
};

try {
  await page.goto(`${baseUrl}/dashboard/narration/review?projectId=${projectId}`, { waitUntil: "domcontentloaded" });
  await page.getByTestId("narration-review").waitFor();
  assert.equal(await page.title(), "解说核对｜影创工坊");
  assert.equal(await page.locator(".review-row").count(), 2);
  assert.equal(await page.getByTestId("review-picture-1").inputValue(), "人物走进大厅");
  assert.equal(await page.getByTestId("review-original-2").isChecked(), true);

  for (const width of [1440, 1024, 768, 375]) await assertNoPageOverflow(width);
  await page.setViewportSize({ width: 1440, height: 1000 });

  await page.getByTestId("review-script-1").fill("第一段人工修订");
  await page.getByTestId("review-original-1").check({ force: true });
  await page.getByRole("button", { name: "下移第 1 行" }).click();
  assert.equal(await page.getByTestId("review-script-1").inputValue(), "第二段解说");

  await page.getByRole("button", { name: "在第 1 行后插入新行" }).click();
  assert.equal(await page.locator(".review-row").count(), 3);
  assert.equal(await page.getByTestId("review-generate").isDisabled(), true);
  await page.getByTestId("review-script-2").fill("插入片段的解说");
  await page.getByTestId("review-end-2").fill("00:99:00.000");
  await page.getByText("请输入 HH:MM:SS.mmm 格式的时间码", { exact: true }).waitFor();
  assert.equal(await page.getByTestId("review-save").isDisabled(), true);
  await page.getByTestId("review-end-2").fill("00:00:16.000");
  await page.getByTestId("review-end-2").blur();
  await page.getByTestId("review-generate").waitFor();
  assert.equal(await page.getByTestId("review-generate").isDisabled(), false);

  await page.waitForTimeout(700);
  const savesBeforeExplicit = saves.length;
  const saveBarrier = createBarrier((barrier) => { delayedSave = barrier; });
  await page.getByTestId("review-save").click();
  await saveBarrier.started;
  assert.equal(await page.getByTestId("review-editor-mode").isDisabled(), true);
  assert.equal(await page.getByTestId("review-generate").isDisabled(), true);
  assert.equal(await page.getByTestId("review-script-1").isDisabled(), true);
  assert.equal(renderSubmissions, 0);
  saveBarrier.release();
  await waitForSaveAfter(savesBeforeExplicit);
  const savedVideos = saves.at(-1).clips.filter((clip) => clip.track_id === "video");
  const savedScripts = saves.at(-1).clips.filter((clip) => clip.track_id === "script");
  assert.deepEqual(savedVideos.map((clip) => clip.start), [0, 5, 8]);
  assert.deepEqual(savedScripts.map((clip) => clip.start), [0, 5, 8]);
  assert.deepEqual(saves.at(-1).subtitles.map((cue) => cue.start), [0, 5, 8]);
  assert.deepEqual(saves.at(-1).subtitles.map((cue) => cue.text), [
    "第二段人工字幕",
    "插入片段的解说",
    "第一段人工字幕",
  ]);
  assert.deepEqual(saves.at(-1).subtitles.map((cue) => cue.region_id), [
    "region-2",
    savedScripts.find((clip) => clip.text === "插入片段的解说").region_id,
    "region-1",
  ]);
  assert.equal(savedScripts.find((clip) => clip.text === "第一段人工修订").original_sound, true);
  assert.equal(saves.at(-1).clips.find((clip) => clip.track_id === "bgm").duration, 12);

  await page.getByTestId("review-editor-mode").click();
  await page.waitForURL(`${baseUrl}/dashboard/narration/editor?projectId=${projectId}`);
  await page.getByTestId("narration-editor").waitFor();
  await page.getByLabel("编辑当前片段文案").fill("切换前立即保存的文案");
  const savesBeforeSwitch = saves.length;
  const switchBarrier = createBarrier((barrier) => { delayedSave = barrier; });
  await page.getByTestId("editor-review-mode").click();
  await switchBarrier.started;
  assert.equal(await page.getByTestId("editor-generate").isDisabled(), true);
  assert.equal(await page.getByTestId("editor-save").isDisabled(), true);
  assert.equal(await page.getByTestId("editor-review-mode").isDisabled(), true);
  switchBarrier.release();
  await page.waitForURL(`${baseUrl}/dashboard/narration/review?projectId=${projectId}`);
  await page.getByTestId("narration-review").waitFor();
  assert.ok(saves.length > savesBeforeSwitch, "editor mode switch must flush its 600ms queued save");
  assert.equal(await page.getByTestId("review-script-1").inputValue(), "切换前立即保存的文案");

  await page.getByTestId("review-picture-1").fill("生成前立即修改画面");
  const savesBeforeGenerate = saves.length;
  const renderBarrier = createBarrier((barrier) => { delayedRender = barrier; });
  await page.getByTestId("review-generate").click();
  await renderBarrier.started;
  assert.equal(await page.getByTestId("review-editor-mode").isDisabled(), true);
  assert.equal(await page.getByTestId("review-save").isDisabled(), true);
  assert.equal(await page.getByTestId("review-generate").isDisabled(), true);
  renderBarrier.release();
  await page.waitForURL(`${baseUrl}/dashboard/narration/generate?projectId=${projectId}`);
  assert.equal(renderSubmissions, 1);
  assert.ok(saves.length > savesBeforeGenerate, "generation must flush the queued draft before render submit");
  assert.equal(saves.at(-1).clips.find((clip) => clip.track_id === "script").picture, "生成前立即修改画面");
  assert.deepEqual(failures, []);
} finally {
  await browser.close();
}

console.log("PASS narration review route, row operations, responsive layout, and save barriers");
