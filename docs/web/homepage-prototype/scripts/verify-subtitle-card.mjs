import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173";
const executablePath = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const projectId = "prj_subtitle_card";
const layouts = {
  ast_clip_1: { status: "confirmed", region: { x: 0, y: 0.72, width: 1, height: 0.1 } },
  ast_clip_2: { status: "detected", region: { x: 0, y: 0.66, width: 1, height: 0.12 }, detected_confidence: 0.91 },
};
const mediaUrl = `${baseUrl}/media/project-result/overlord-narration-result-85s.mp4`;
const failures = [];
const browser = await chromium.launch({ executablePath, headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

page.setDefaultTimeout(12000);
page.on("pageerror", (error) => failures.push(`pageerror: ${error.message}`));
page.on("console", (message) => {
  if (message.type() === "error") failures.push(`console.error: ${message.text()}`);
});
await page.addInitScript(({ id, cachedLayouts }) => {
  localStorage.setItem("narrato.api.token", "token-subtitle-card");
  localStorage.setItem("narrato.locale", "zh-CN");
  sessionStorage.setItem(`narrato:subtitle-region-layouts:${id}`, JSON.stringify(cachedLayouts));
}, { id: projectId, cachedLayouts: layouts });

await page.route("**/api/v1/**", async (route) => {
  const request = route.request();
  const apiPath = new URL(request.url()).pathname.replace(/^\/api\/v1/, "");
  let data;
  if (apiPath === "/users/me") {
    data = { id: "usr_subtitle_card", email: "subtitle@example.test", credit_balance: 1280 };
  } else if (apiPath === "/products/short-drama-narration/config") {
    data = {
      narration_styles: [{ id: "悬疑/犯罪", name: "悬疑/犯罪", eyebrow: "悬念推进", description: "突出剧情冲突", tags: ["悬疑"], is_custom: false }],
      original_sound_ratios: [0, 30, 70, 90],
      video_ratios: [{ id: "9:16", name: "9:16" }],
      voices: [{ id: "voice_real", name: "沉稳男声", provider_code: "fake", languages: ["zh-CN"], gender: "male", styles: [], sample_url: null }],
      subtitle_styles: [{ id: "经典白色", name: "经典白色" }],
    };
  } else if (apiPath === `/projects/${projectId}/cost-estimate`) {
    data = { credits: 40, total_seconds: 170, estimated_output_seconds: 28, credits_per_minute: 20 };
  } else if (apiPath === `/projects/${projectId}/narration/settings`) {
    data = {
      background_music: null,
      narration_style: "悬疑/犯罪",
      original_sound_ratio: 30,
      video_ratio: "9:16",
      voice_id: "voice_real",
      subtitle_style: "经典白色",
      execution_mode: "manual",
      source_subtitle_layouts: layouts,
      narration_subtitle_position: { y: 0.84, font_scale: 0.9 },
    };
  } else if (apiPath === `/projects/${projectId}/stage`) {
    data = {
      project_id: projectId,
      project_title: "双视频字幕设置",
      project_status: "ready",
      current_stage: "settings",
      execution_mode: "manual",
      workflow_state: null,
      failure_code: null,
      updated_at: "2026-08-05T08:00:00Z",
      stages: ["created", "settings", "analysis", "edit", "generate", "export"],
      analysis_tasks: [],
      video_assets: [
        { id: "ast_clip_1", filename: "片段一.mp4", cdn_url: `${mediaUrl}?clip=1`, duration_seconds: 85 },
        { id: "ast_clip_2", filename: "片段二.mp4", cdn_url: `${mediaUrl}?clip=2`, duration_seconds: 85 },
      ],
    };
  } else {
    failures.push(`unexpected API request: ${request.method()} ${apiPath}`);
    data = {};
  }
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ code: "OK", message: "ok", data, request_id: "req_subtitle_card" }),
  });
});

try {
  await page.goto(`${baseUrl}/dashboard/narration/settings?projectId=${projectId}`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "字幕与遮罩设置" }).waitFor();
  const dialog = page.getByRole("dialog", { name: "未探测到可确认的原字幕位置" });
  assert.equal(await dialog.count(), 0, "进入设置页时不得用旧探测弹窗阻塞操作");

  const cards = page.locator(".narration-preview__video-card");
  const selectedStage = page.locator(".narration-preview__selected-stage");
  const selectedVideo = selectedStage.locator("video");
  assert.equal(await cards.count(), 2, "视频列表必须展示全部片段");
  assert.equal(await page.locator(".narration-preview__frame").count(), 0, "不得保留独立视频预览区域");
  await selectedStage.locator(".narration-preview__content-layer").waitFor();
  assert.equal(await selectedStage.locator(".narration-source-mask").count(), 1, "上方当前视频必须展示原字幕遮罩");
  assert.equal(await selectedStage.locator(".narration-preview__caption").count(), 1, "上方当前视频必须展示解说字幕");
  assert.equal(await cards.locator(".narration-preview__content-layer").count(), 0, "下方缩略图不得承载编辑层");
  const fontScaleSlider = page.locator('.narration-preview__caption-controls input[type="range"]');
  assert.equal(await fontScaleSlider.inputValue(), "0.9", "默认解说字幕大小必须以当前 90% 为基准");
  assert.equal(await page.locator(".narration-preview__caption-controls output").textContent(), "90%", "字号基准值必须明确显示为 90%");

  const subtitleControls = page.locator("#narration-source-subtitle-controls");
  const confirmPositionButton = subtitleControls.getByRole("button", { name: "确认位置" });
  const noSubtitleButton = subtitleControls.getByRole("button", { name: "无字幕" });
  assert.equal(await confirmPositionButton.count(), 1, "确认位置按钮必须始终存在");
  assert.equal(await noSubtitleButton.count(), 1, "无字幕按钮必须始终存在");
  assert.equal(await confirmPositionButton.getAttribute("aria-pressed"), "true", "已确认片段应标记确认位置为当前选择");
  await noSubtitleButton.click();
  await page.waitForFunction(() => Array.from(document.querySelectorAll("#narration-source-subtitle-controls button")).some((node) => node.textContent.includes("无字幕") && node.getAttribute("aria-pressed") === "true"));
  assert.equal(await noSubtitleButton.getAttribute("aria-pressed"), "true", "必须允许从已确认切换为无字幕");
  assert.equal(await selectedStage.locator(".narration-source-mask").count(), 0, "切换为无字幕后应隐藏原字幕遮罩");
  assert.equal(await confirmPositionButton.count(), 1, "切换为无字幕后确认位置按钮仍须存在");
  await confirmPositionButton.click();
  await selectedStage.locator(".narration-source-mask").waitFor();
  assert.equal(await confirmPositionButton.getAttribute("aria-pressed"), "true", "必须允许从无字幕切回确认位置");
  assert.equal(await noSubtitleButton.count(), 1, "切回确认位置后无字幕按钮仍须存在");

  const firstWidth = (await cards.nth(0).boundingBox())?.width || 0;
  const secondWidth = (await cards.nth(1).boundingBox())?.width || 0;
  const stageBox = await selectedStage.boundingBox();
  const railBox = await page.locator(".narration-preview__video-rail").boundingBox();
  const firstBox = await cards.nth(0).boundingBox();
  const lastBox = await cards.nth(-1).boundingBox();
  assert.ok(Math.abs(firstWidth - secondWidth) <= 1, "下方视频缩略图必须保持等宽");
  assert.ok((stageBox?.width || 0) > firstWidth, "上方当前视频应明显大于下方缩略图");
  assert.ok((stageBox?.y || 0) < (railBox?.y || 0), "当前视频必须位于缩略图列表上方");
  const leftGap = (firstBox?.x || 0) - (railBox?.x || 0);
  const rightGap = ((railBox?.x || 0) + (railBox?.width || 0)) - ((lastBox?.x || 0) + (lastBox?.width || 0));
  assert.ok(Math.abs(leftGap - rightGap) <= 2, `视频片段列表必须居中：left=${leftGap}, right=${rightGap}`);
  assert.equal(await selectedVideo.evaluate((node) => getComputedStyle(node).objectFit), "contain");
  await selectedVideo.evaluate((node) => { node.dataset.verifyInstance = "stable"; });

  await cards.nth(1).locator(".narration-preview__video-thumbnail").click();
  await page.waitForFunction(() => document.querySelectorAll(".narration-preview__video-card")[1]?.classList.contains("is-selected"));
  await page.waitForFunction(() => document.querySelector(".narration-preview__selected-stage video")?.getAttribute("src")?.includes("clip=2"));
  await selectedStage.locator(".narration-source-mask").waitFor();
  assert.equal(await selectedVideo.getAttribute("data-verify-instance"), "stable", "切换片段不得重建上方视频元素");
  assert.equal(await cards.nth(0).getAttribute("aria-current"), null, "切换后旧缩略图必须取消选中");
  assert.equal(await cards.nth(1).getAttribute("aria-current"), "true", "切换后新缩略图必须高亮");

  const mask = selectedStage.locator(".narration-source-mask");
  await mask.scrollIntoViewIfNeeded();
  await page.waitForTimeout(250);
  const beforeTop = await mask.evaluate((node) => Number.parseFloat(node.style.top));
  const maskBox = await mask.boundingBox();
  assert.ok(maskBox, "原字幕遮罩必须可见");
  await page.mouse.move(maskBox.x + maskBox.width / 2, maskBox.y + maskBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(maskBox.x + maskBox.width / 2, maskBox.y + maskBox.height / 2 + 18, { steps: 5 });
  await page.mouse.up();
  await page.waitForFunction((top) => Number.parseFloat(document.querySelector(".narration-preview__selected-stage .narration-source-mask")?.style.top || "0") > top, beforeTop);
  assert.equal(await selectedVideo.getAttribute("data-verify-instance"), "stable", "拖动遮罩不得重建上方视频元素");

  const playButton = page.getByRole("button", { name: "播放所选视频" });
  await playButton.click();
  await page.getByRole("button", { name: "暂停所选视频" }).waitFor();
  await page.getByRole("button", { name: "暂停所选视频" }).click();
  await page.getByRole("button", { name: "播放所选视频" }).waitFor();

  const startAnalysisButton = page.locator(".narration-actions button");
  await startAnalysisButton.click();
  const confirmationDialog = page.getByRole("dialog", { name: "还有 1 个视频未确认字幕处理方式" });
  await confirmationDialog.waitFor();
  assert.equal(await page.getByText("请先确认每个视频的原字幕位置，或选择“无字幕”。", { exact: true }).count(), 0, "字幕确认错误不得显示在背景音乐区域");
  assert.equal(await confirmationDialog.getByRole("button", { name: "去确认" }).count(), 1);
  assert.equal(await confirmationDialog.getByRole("button", { name: "一键确认" }).count(), 1);
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    const dialogMetrics = await confirmationDialog.locator(":scope > div").evaluate((node) => {
      const bounds = node.getBoundingClientRect();
      return {
        left: bounds.left,
        right: bounds.right,
        width: bounds.width,
        documentOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      };
    });
    assert.ok(dialogMetrics.left >= 0 && dialogMetrics.right <= width + 1 && dialogMetrics.documentOverflow <= 1, `${width}px 确认弹窗不得横向溢出：${JSON.stringify(dialogMetrics)}`);
    if (process.env.CAPTURE_DIR && width === 375) {
      await mkdir(process.env.CAPTURE_DIR, { recursive: true });
      await page.screenshot({ path: path.join(process.env.CAPTURE_DIR, "subtitle-confirmation-dialog-375.png"), fullPage: true });
    }
  }
  if (process.env.CAPTURE_DIR) {
    await mkdir(process.env.CAPTURE_DIR, { recursive: true });
    await page.screenshot({ path: path.join(process.env.CAPTURE_DIR, "subtitle-confirmation-dialog-1440.png"), fullPage: true });
  }
  await confirmationDialog.getByRole("button", { name: "去确认" }).click();
  await confirmationDialog.waitFor({ state: "hidden" });
  assert.equal(await confirmPositionButton.evaluate((node) => document.activeElement === node), true, "去确认后应聚焦当前片段的确认按钮");

  await startAnalysisButton.click();
  await confirmationDialog.waitFor();
  await confirmationDialog.getByRole("button", { name: "一键确认" }).click();
  await confirmationDialog.waitFor({ state: "hidden" });
  assert.equal(await confirmPositionButton.getAttribute("aria-pressed"), "true", "一键确认应确认全部待处理片段");
  assert.equal(await selectedStage.locator(".narration-source-mask").count(), 1, "一键确认后应保留当前遮罩位置");
  await noSubtitleButton.click();
  assert.equal(await noSubtitleButton.getAttribute("aria-pressed"), "true", "一键确认后仍必须允许切换为无字幕");
  assert.equal(await confirmPositionButton.count(), 1);
  await confirmPositionButton.click();
  await selectedStage.locator(".narration-source-mask").waitFor();
  assert.equal(await confirmPositionButton.getAttribute("aria-pressed"), "true", "切换后仍可再次确认字幕位置");

  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.waitForTimeout(250);
    const metrics = await page.evaluate(() => {
      const card = document.querySelector(".narration-preview__video-card.is-selected");
      const media = document.querySelector(".narration-preview__selected-stage");
      const rail = document.querySelector(".narration-preview__video-rail");
      const maskNode = media?.querySelector(".narration-source-mask");
      return {
        documentOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        bodyOverflow: document.body.scrollWidth - document.body.clientWidth,
        cardWidth: card?.getBoundingClientRect().width || 0,
        mediaWidth: media?.getBoundingClientRect().width || 0,
        maskWidth: maskNode?.getBoundingClientRect().width || 0,
        mediaTop: media?.getBoundingClientRect().top || 0,
        railTop: rail?.getBoundingClientRect().top || 0,
      };
    });
    assert.ok(metrics.documentOverflow <= 1 && metrics.bodyOverflow <= 1, `${width}px 页面不得横向溢出：${JSON.stringify(metrics)}`);
    assert.ok(metrics.cardWidth > 0 && metrics.maskWidth > 0 && metrics.maskWidth <= metrics.mediaWidth + 1, `${width}px 遮罩必须位于上方当前视频内：${JSON.stringify(metrics)}`);
    assert.ok(metrics.mediaTop < metrics.railTop, `${width}px 必须保持当前视频在上、缩略图列表在下：${JSON.stringify(metrics)}`);
  }

  if (process.env.CAPTURE_DIR) {
    await mkdir(process.env.CAPTURE_DIR, { recursive: true });
    await page.screenshot({ path: path.join(process.env.CAPTURE_DIR, "subtitle-card-1440.png"), fullPage: true });
    await page.setViewportSize({ width: 375, height: 1000 });
    await page.screenshot({ path: path.join(process.env.CAPTURE_DIR, "subtitle-card-375.png"), fullPage: true });
  }
  assert.deepEqual(failures, []);
  console.log("PASS subtitle preview, confirmation dialog, bulk confirmation, decision switching, playback, drag stability, and responsive layout");
} finally {
  await browser.close();
}
