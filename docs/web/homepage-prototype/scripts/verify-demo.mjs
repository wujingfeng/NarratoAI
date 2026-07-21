#!/usr/bin/env node

import { readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173/";
const executablePath = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const failures = [];

function check(condition, message, details = "") {
  if (!condition) failures.push(`${message}${details ? ` — ${details}` : ""}`);
}

function assertCleanSource(label, source) {
  const forbidden = [
    ["data:image", /data:image/i],
    ["base64", /base64/i],
    ["canvas", /(?:<canvas\b|CanvasTexture|TextureLoader|VideoTexture)/i],
    ["background-image: url(", /background-image\s*:\s*url\s*\(/i],
  ];

  for (const [token, pattern] of forbidden) {
    check(!pattern.test(source), `${label} 不得使用贴图重建标记 ${token}`);
  }
}

const componentSource = await readFile(path.join(projectRoot, "src/components/DemoSection.jsx"), "utf8");
const cssSource = await readFile(path.join(projectRoot, "src/styles/demo-workbenches.css"), "utf8");
assertCleanSource("DemoSection.jsx", componentSource);
assertCleanSource("demo-workbenches.css", cssSource);

const browser = await chromium.launch({ executablePath, headless: true });
const browserErrors = [];

async function configurePage(page, label) {
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(`pageerror: ${error.message}`));
  page.on("response", (response) => {
    if (response.status() >= 400) pageErrors.push(`response: ${response.status()} ${response.url()}`);
  });
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().startsWith("Failed to load resource:")) {
      pageErrors.push(`console: ${message.text()}`);
    }
  });
  const response = await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  check(Boolean(response?.ok()), `${label} 页面必须可访问`, response ? `${response.status()}` : "no response");
  await page.evaluate(() => document.fonts?.ready);
  await page.locator("#tool-demo-panel").waitFor({ state: "visible" });
  return pageErrors;
}

async function inspectTool(page, id, expectedCount) {
  await page.locator(`#tool-tab-${id}`).click();
  await page.waitForFunction((toolId) => document.querySelector("#tool-demo-panel")?.dataset.toolLayout === toolId, id);

  return page.locator("#tool-demo-panel").evaluate((panel, expected) => {
    const root = panel.firstElementChild;
    const box = panel.getBoundingClientRect();
    return {
      layout: panel.dataset.toolLayout,
      rootClass: root?.className || "",
      stepCount: panel.querySelectorAll("[data-flow-step]").length,
      hasNarration: Boolean(panel.querySelector(".narration-studio")),
      hasTranslation: Boolean(panel.querySelector(".translation-localizer")),
      hasRemix: Boolean(panel.querySelector(".remix-console")),
      hasBilingual: Boolean(panel.querySelector(".bilingual-subtitles")),
      hasVoiceMapping: Boolean(panel.querySelector(".voice-mapping")),
      hasClipPool: Boolean(panel.querySelector(".clip-pool")),
      hasTimeline: Boolean(panel.querySelector(".remix-timeline")),
      hasBeatControls: Boolean(panel.querySelector(".beat-controls")),
      hasNarrationScript: Boolean(panel.querySelector(".narration-script")),
      panelWidth: box.width,
      expected,
    };
  }, expectedCount);
}

async function verifyDesktopInteractions() {
  const page = await browser.newPage({ viewport: { width: 1487, height: 1058 } });
  await page.addInitScript(() => localStorage.setItem("narrato.locale", "zh-CN"));
  const pageErrors = await configurePage(page, "1487px");
  const results = {};

  results.narration = await inspectTool(page, "narration", 5);
  check(results.narration.layout === "narration", "短剧解说必须发布 narration 根布局");
  check(results.narration.hasNarration, "短剧解说必须使用 .narration-studio");
  check(results.narration.stepCount === 5, "短剧解说必须具有 5 个流程步骤", String(results.narration.stepCount));
  check(results.narration.hasNarrationScript, "短剧解说必须具有专属文案编辑区");

  results.translation = await inspectTool(page, "translation", 4);
  check(results.translation.layout === "translation", "视频翻译必须发布 translation 根布局");
  check(results.translation.hasTranslation, "视频翻译必须使用 .translation-localizer");
  check(results.translation.stepCount === 4, "视频翻译必须具有 4 个流程步骤", String(results.translation.stepCount));
  check(results.translation.hasBilingual && results.translation.hasVoiceMapping, "视频翻译必须具有双语字幕和角色声线映射");

  results.remix = await inspectTool(page, "remix", 3);
  check(results.remix.layout === "remix", "短剧混剪必须发布 remix 根布局");
  check(results.remix.hasRemix, "短剧混剪必须使用 .remix-console");
  check(results.remix.stepCount === 3, "短剧混剪必须具有 3 个流程步骤", String(results.remix.stepCount));
  check(results.remix.hasClipPool && results.remix.hasTimeline && results.remix.hasBeatControls, "短剧混剪必须具有片段池、时间线和节拍控制");
  check(!results.remix.hasNarrationScript && !results.remix.hasBilingual, "短剧混剪不得包含解说词或双语字幕编辑语义");

  check(new Set(Object.values(results).map((result) => result.rootClass)).size === 3, "三类工作台根 class 签名必须互不相同");

  await page.locator("#tool-tab-narration").focus();
  await page.keyboard.press("ArrowRight");
  check(await page.locator("#tool-tab-translation").getAttribute("aria-selected") === "true", "Tab 必须支持 ArrowRight 键盘切换");
  check(await page.evaluate(() => document.activeElement?.id) === "tool-tab-translation", "键盘切换后焦点必须跟随活动 Tab");
  await page.keyboard.press("End");
  check(await page.locator("#tool-tab-remix").getAttribute("aria-selected") === "true", "Tab 必须支持 End 键切换到末项");
  await page.keyboard.press("Home");
  check(await page.locator("#tool-tab-narration").getAttribute("aria-selected") === "true", "Tab 必须支持 Home 键切换到首项");

  const modalTrigger = page.locator(".case-card__image").first();
  await modalTrigger.click();
  const dialog = page.locator(".video-modal[role='dialog']");
  check(await dialog.isVisible(), "案例卡必须打开真实视频弹层");
  check(await page.locator("body").evaluate((body) => body.classList.contains("modal-locked")), "弹层打开时页面滚动必须锁定");
  check((await page.evaluate(() => document.activeElement?.getAttribute("aria-label"))) === "关闭案例", "弹层打开后焦点必须进入关闭按钮");
  await page.keyboard.press("Escape");
  await dialog.waitFor({ state: "detached" });
  await page.waitForFunction(() => document.activeElement?.classList.contains("case-card__image"));
  check(await modalTrigger.evaluate((node) => document.activeElement === node), "Escape 关闭弹层后必须归还触发器焦点");

  browserErrors.push(...pageErrors.map((error) => `1487px ${error}`));
  await page.close();
}

async function verifyViewport(width, height) {
  const page = await browser.newPage({ viewport: { width, height } });
  await page.addInitScript(() => localStorage.setItem("narrato.locale", "zh-CN"));
  const pageErrors = await configurePage(page, `${width}px`);

  for (const [id, count] of [["narration", 5], ["translation", 4], ["remix", 3]]) {
    const result = await inspectTool(page, id, count);
    const overflow = await page.evaluate(() => ({
      pageWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
    }));
    check(overflow.pageWidth <= overflow.viewportWidth + 1, `${width}px ${id} 页面不得横向溢出`, `${overflow.pageWidth}px > ${overflow.viewportWidth}px`);
    check(result.panelWidth > 0, `${width}px ${id} 工作台必须可见`);
  }

  if (width === 390) {
    await page.locator("#tool-tab-narration").click();
    const narrationScroll = await page.locator(".narration-studio__pipeline ol").evaluate((node) => ({ client: node.clientWidth, scroll: node.scrollWidth, overflow: getComputedStyle(node).overflowX }));
    check(narrationScroll.scroll > narrationScroll.client && ["auto", "scroll"].includes(narrationScroll.overflow), "390px 解说流程必须只在内部横向滚动");

    await page.locator("#tool-tab-translation").click();
    const translationScroll = await page.locator(".translation-localizer__flow").evaluate((node) => ({ client: node.clientWidth, scroll: node.scrollWidth, overflow: getComputedStyle(node).overflowX }));
    check(translationScroll.scroll > translationScroll.client && ["auto", "scroll"].includes(translationScroll.overflow), "390px 翻译流程必须只在内部横向滚动");

    await page.locator("#tool-tab-remix").click();
    const remixScroll = await page.locator(".remix-timeline").evaluate((node) => ({ client: node.clientWidth, scroll: node.scrollWidth, overflow: getComputedStyle(node).overflowX }));
    check(remixScroll.scroll > remixScroll.client && ["auto", "scroll"].includes(remixScroll.overflow), "390px 混剪时间线必须只在内部横向滚动");
    const finalOverflow = await page.evaluate(() => ({ page: document.documentElement.scrollWidth, viewport: innerWidth }));
    check(finalOverflow.page <= finalOverflow.viewport + 1, "390px 内部滚动不得扩展页面宽度", `${finalOverflow.page}px > ${finalOverflow.viewport}px`);
  }

  browserErrors.push(...pageErrors.map((error) => `${width}px ${error}`));
  await page.close();
}

try {
  await verifyDesktopInteractions();
  await verifyViewport(1024, 820);
  await verifyViewport(390, 844);
} finally {
  await browser.close();
}

for (const error of browserErrors) check(false, `浏览器不得出现错误：${error}`);

if (failures.length) {
  console.error("Demo 验收失败：");
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exit(1);
}

console.log("Demo 验收通过：三类根节点、5/4/3 步流程、专属 UI、Tab 键盘、案例弹层及响应式内部滚动均符合要求。");
