import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir } from "node:fs/promises";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { zhCN } from "../src/i18n/locales/zh-CN.js";
import { en } from "../src/i18n/locales/en.js";
import { ja } from "../src/i18n/locales/ja.js";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const executablePath =
  process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const EXPECTED_COPY = {
  "zh-CN": {
    language: "简体中文",
    homeTitle: "影创工坊｜AI 出片工作台",
    heroHeading: "专为自媒体小白打造的AI 出片工作台",
    notFoundHeading: "页面未找到",
    notFoundTitle: "页面未找到｜影创工坊",
    routeHeadings: { "/dashboard": "工作台概览", "/dashboard/create": "创建新的 AI 视频", "/dashboard/projects": "我的项目" },
    dashboardTitle: "快速开始",
    createTitle: "选择创作类型",
    projectsTitle: "管理全部创作任务与生成结果",
    accountActions: "账户快捷操作",
    editor: { heading: "短剧解说多轨编辑器", saveDraft: "保存草稿" },
    routeToasts: { "/dashboard": "充值功能建设中", "/dashboard/create": "参数设置功能建设中", "/dashboard/projects": "霸总短剧解说 01：导出功能建设中" },
    workflow: { resultHeading: "霸总短剧解说 01 · 项目结果", resultAction: "导出视频", resultStatus: "生成完成", resultLog: "视频导出完成", resultMedia: "霸总短剧解说 01 成片", resultBreadcrumb: "我的项目", createdAt: "创建时间", createdDate: "2024年5月30日 14:30", resultToast: "分享链接已准备（原型）", settingsHeading: "短剧解说设置参数", settingsAction: "使用当前设置，开始 AI 分析", settingsMedia: "短剧画面预览", exportStep: "导出", settingsToast: "重命名功能建设中", analysisHeading: "短剧解说 AI 分析", analysisAction: "下一步：编辑片段 →", analysisTitle: "正在理解剧情并提取高光", analysisDone: "已完成", analysisLog: "正在定位剧情冲突与爽点", analysisMedia: "全屏播放 EP01", resultTitle: "霸总短剧解说 01｜影创工坊", settingsTitle: "短剧解说设置｜影创工坊", analysisPageTitle: "AI 分析｜影创工坊" },
  },
  en: {
    language: "English",
    homeTitle: "影创工坊 | AI Video Workspace",
    heroHeading: "Built for first-time creatorsAI Video Workspace",
    notFoundHeading: "Page not found",
    notFoundTitle: "Page not found | 影创工坊",
    routeHeadings: { "/dashboard": "Workspace overview", "/dashboard/create": "Create a new AI video", "/dashboard/projects": "My projects" },
    dashboardTitle: "Quick start",
    createTitle: "Choose creation type",
    projectsTitle: "Manage every creation task and result",
    accountActions: "Account quick actions",
    editor: { heading: "Multitrack narration editor", saveDraft: "Save draft" },
    routeToasts: { "/dashboard": "Top-up is coming soon", "/dashboard/create": "Parameter settings are coming soon", "/dashboard/projects": "霸总短剧解说 01: Export is coming soon" },
    workflow: { resultHeading: "霸总短剧解说 01 · Project result", resultAction: "Export video", resultStatus: "Generated", resultLog: "Video export completed", resultMedia: "Final video for 霸总短剧解说 01", resultBreadcrumb: "My projects", createdAt: "Created", createdDate: "May 30, 2024, 2:30 PM", resultToast: "Share link is ready (prototype)", settingsHeading: "Short-drama narration settings", settingsAction: "Start AI analysis with current settings", settingsMedia: "Short-drama scene preview", exportStep: "Export", settingsToast: "Renaming is coming soon", analysisHeading: "Short-drama narration AI analysis", analysisAction: "Next: Edit clips →", analysisTitle: "Understanding the story and extracting highlights", analysisDone: "Complete", analysisLog: "Locating story conflicts and payoffs", analysisMedia: "Play EP01 fullscreen", resultTitle: "霸总短剧解说 01 | 影创工坊", settingsTitle: "Narration settings | 影创工坊", analysisPageTitle: "AI analysis | 影创工坊" },
  },
  ja: {
    language: "日本語",
    homeTitle: "影创工坊｜AI 動画制作ワークスペース",
    heroHeading: "動画制作初心者のためのAI 動画制作ワークスペース",
    notFoundHeading: "ページが見つかりません",
    notFoundTitle: "ページが見つかりません｜影创工坊",
    routeHeadings: { "/dashboard": "ワークスペース概要", "/dashboard/create": "新しい AI 動画を作成", "/dashboard/projects": "マイプロジェクト" },
    dashboardTitle: "クイックスタート",
    createTitle: "制作タイプを選択",
    projectsTitle: "すべての制作タスクと生成結果を管理",
    accountActions: "アカウントのクイック操作",
    editor: { heading: "マルチトラック解説エディター", saveDraft: "下書きを保存" },
    routeToasts: { "/dashboard": "チャージ機能は準備中です", "/dashboard/create": "パラメータ設定は準備中です", "/dashboard/projects": "霸总短剧解说 01：書き出しは準備中です" },
    workflow: { resultHeading: "霸总短剧解说 01 · プロジェクト結果", resultAction: "動画を書き出す", resultStatus: "生成完了", resultLog: "動画の書き出しが完了", resultMedia: "霸总短剧解说 01 の完成動画", resultBreadcrumb: "マイプロジェクト", createdAt: "作成日時", createdDate: "2024/05/30 14:30", resultToast: "共有リンクを準備しました（プロトタイプ）", settingsHeading: "ショートドラマ解説の設定", settingsAction: "現在の設定で AI 分析を開始", settingsMedia: "ショートドラマ画面プレビュー", exportStep: "書き出し", settingsToast: "名前変更機能は準備中です", analysisHeading: "ショートドラマ解説 AI 分析", analysisAction: "次へ：クリップ編集 →", analysisTitle: "ストーリーを理解してハイライトを抽出中", analysisDone: "完了", analysisLog: "ストーリーの対立と見せ場を特定中", analysisMedia: "EP01 を全画面再生", resultTitle: "霸总短剧解说 01｜影创工坊", settingsTitle: "ショートドラマ解説設定｜影创工坊", analysisPageTitle: "AI 分析｜影创工坊" },
  },
};

const ROUTE_MATRIX = [
  { path: "/", titleKey: "home", heading: (resource) => `${resource.home.hero.headingPrefix}${resource.home.hero.headingAccent}`, headingSelector: ".hero-copy h1" },
  { path: "/dashboard", titleKey: "dashboard", heading: (resource) => resource.dashboard.routeHeading },
  { path: "/dashboard/create", titleKey: "create", heading: (resource) => resource.create.routeHeading },
  { path: "/dashboard/projects", titleKey: "projects", heading: (resource) => resource.projects.routeHeading },
  { path: "/dashboard/projects/overlord/result", titleKey: "projectResult", heading: (resource) => resource.projectResult.routeHeading.replace("{title}", "霸总短剧解说 01") },
  { path: "/dashboard/narration/settings", titleKey: "narrationSettings", heading: (resource) => resource.narration.routeHeading },
  { path: "/dashboard/narration/analysis", titleKey: "narrationAnalysis", heading: (resource) => resource.analysis.routeHeading },
  { path: "/dashboard/narration/editor", titleKey: "narrationEditor", heading: (resource) => resource.editor.routeHeading },
  { path: "/missing-route", titleKey: "notFound", heading: (resource) => resource.errors.notFound.heading },
];
const VIEWPORT_MATRIX = [
  { name: "desktop", width: 1487, height: 1058 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "mobile", width: 390, height: 844 },
];
const RESOURCES = { "zh-CN": zhCN, en, ja };

for (const [locale, resources] of Object.entries({ "zh-CN": zhCN, en, ja })) {
  assert.equal(resources.home.capabilities.kicker, "ALL-IN-ONE WORKSPACE", `${locale} capability kicker must come from resources`);
  assert.equal(resources.home.demo.kicker, "CASE DEMO", `${locale} demo kicker must come from resources`);
}

const task5ResourceRoots = ["projectResult", "narration", "analysis"];
const task5EqualContentBoundaries = new Set(["narration.ratios.landscape", "narration.ratios.square"]);
const readResourceLeaves = (value, prefix = "", leaves = new Map()) => {
  for (const [key, child] of Object.entries(value)) {
    const resourcePath = prefix ? `${prefix}.${key}` : key;
    if (typeof child === "string") leaves.set(resourcePath, child);
    else readResourceLeaves(child, resourcePath, leaves);
  }
  return leaves;
};
const zhTask5Leaves = readResourceLeaves(Object.fromEntries(task5ResourceRoots.map((root) => [root, zhCN[root]])));
for (const [locale, resources] of Object.entries({ en, ja })) {
  const localizedLeaves = readResourceLeaves(Object.fromEntries(task5ResourceRoots.map((root) => [root, resources[root]])));
  for (const [key, zhValue] of zhTask5Leaves) {
    assert.equal(typeof localizedLeaves.get(key), "string", `${locale} must define Task 5 resource ${key}`);
    if (!task5EqualContentBoundaries.has(key)) assert.notEqual(localizedLeaves.get(key), zhValue, `${locale} Task 5 resource ${key} must not silently remain Chinese`);
  }
}

const editorEqualContentBoundaries = new Set(["editor.content.projectName", "editor.content.defaultCaption"]);
for (const [locale, resources] of Object.entries({ "zh-CN": zhCN, en, ja })) {
  assert.equal(typeof resources.editor, "object", `${locale} must define Task 6 editor resources`);
}
const zhEditorLeaves = readResourceLeaves({ editor: zhCN.editor });
for (const [locale, resources] of Object.entries({ en, ja })) {
  const localizedLeaves = readResourceLeaves({ editor: resources.editor });
  for (const [key, zhValue] of zhEditorLeaves) {
    assert.equal(typeof localizedLeaves.get(key), "string", `${locale} must define Task 6 resource ${key}`);
    if (!editorEqualContentBoundaries.has(key)) assert.notEqual(localizedLeaves.get(key), zhValue, `${locale} Task 6 resource ${key} must not silently remain Chinese`);
  }
}

async function findAvailablePort() {
  return await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close((error) => (error ? reject(error) : resolve(port)));
    });
  });
}

async function waitForPreview(url, preview, getOutput) {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    if (preview.exitCode !== null) {
      throw new Error(`Vite preview exited early (${preview.exitCode}).\n${getOutput()}`);
    }
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for Vite preview at ${url}.\n${getOutput()}`);
}

async function stopPreview(preview) {
  if (preview.exitCode !== null) return;
  try {
    process.kill(-preview.pid, "SIGTERM");
  } catch {
    preview.kill("SIGTERM");
  }
  await Promise.race([
    new Promise((resolve) => preview.once("exit", resolve)),
    new Promise((resolve) => setTimeout(resolve, 2_000)),
  ]);
  if (preview.exitCode === null) {
    try {
      process.kill(-preview.pid, "SIGKILL");
    } catch {
      preview.kill("SIGKILL");
    }
  }
}

const port = Number(process.env.I18N_PREVIEW_PORT) || await findAvailablePort();
const baseUrl = `http://127.0.0.1:${port}`;
const viteBin = path.join(projectRoot, "node_modules", "vite", "bin", "vite.js");
const preview = spawn(process.execPath, [viteBin, "preview", "--host", "127.0.0.1", "--port", String(port), "--strictPort"], {
  cwd: projectRoot,
  detached: true,
  stdio: ["ignore", "pipe", "pipe"],
});
let previewOutput = "";
preview.stdout.on("data", (chunk) => { previewOutput += chunk; });
preview.stderr.on("data", (chunk) => { previewOutput += chunk; });

let browser;
try {
  await waitForPreview(baseUrl, preview, () => previewOutput);
  browser = await chromium.launch({ executablePath, headless: true });
  const context = await browser.newContext({ locale: "en-US", viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  page.setDefaultTimeout(15_000);
  const browserErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => browserErrors.push(`pageerror: ${error.message}`));

  const selectLocale = async (locale) => {
    const expected = EXPECTED_COPY[locale];
    await page.getByTestId("language-switcher-trigger").click();
    const option = page.getByRole("menuitem", { name: expected.language });
    await option.waitFor({ state: "visible" });
    await option.evaluate((node) => node.click());
    await page.locator("html").evaluate((node, expectedLocale) => {
      if (node.lang !== expectedLocale) throw new Error(`Expected html lang ${expectedLocale}, received ${node.lang}`);
    }, locale);
  };

  const assertHomeCopy = async (locale) => {
    const expected = EXPECTED_COPY[locale];
    assert.equal(await page.title(), expected.homeTitle);
    assert.equal((await page.locator(".brand-mark__text").first().textContent()).trim(), "影创工坊");
    assert.equal((await page.locator(".hero-copy h1").textContent()).replace(/\s+/g, " ").trim(), expected.heroHeading);
  };

  await page.goto(`${baseUrl}/`);
  await page.getByTestId("language-switcher-trigger").waitFor();
  assert.equal(await page.locator("html").getAttribute("lang"), "en");
  await assertHomeCopy("en");
  assert.equal(await page.getByTestId("language-switcher-trigger").getAttribute("aria-haspopup"), "menu");
  await page.evaluate(() => window.scrollTo(0, 640));
  const scrollBeforeLocaleSwitch = await page.evaluate(() => window.scrollY);
  const triggerBeforeLocaleSwitch = page.getByTestId("language-switcher-trigger");
  await triggerBeforeLocaleSwitch.focus();
  assert.equal(await triggerBeforeLocaleSwitch.evaluate((node) => node === document.activeElement), true);
  await selectLocale("ja");
  assert.equal(new URL(page.url()).pathname, "/");
  assert.equal(await page.locator("html").getAttribute("lang"), "ja");
  assert.equal(await page.evaluate(() => localStorage.getItem("narrato.locale")), "ja");
  assert.equal(await page.evaluate(() => window.scrollY), scrollBeforeLocaleSwitch);
  assert.equal(await triggerBeforeLocaleSwitch.evaluate((node) => node === document.activeElement), true);
  await assertHomeCopy("ja");

  for (const locale of ["zh-CN", "en", "ja"]) {
    await page.goto(`${baseUrl}/`);
    await selectLocale(locale);
    await assertHomeCopy(locale);
    await page.goto(`${baseUrl}/missing-route`);
    await page.getByRole("heading", { level: 1 }).waitFor();
    assert.equal((await page.getByRole("heading", { level: 1 }).textContent()).trim(), EXPECTED_COPY[locale].notFoundHeading);
    assert.equal(await page.title(), EXPECTED_COPY[locale].notFoundTitle);
  }

  for (const locale of ["zh-CN", "en", "ja"]) {
    const expected = EXPECTED_COPY[locale].workflow;
    await page.goto(`${baseUrl}/dashboard/projects/overlord/result`);
    await selectLocale(locale);
    assert.equal((await page.locator("[data-route-heading]").textContent()).trim(), expected.resultHeading);
    assert.equal(await page.title(), expected.resultTitle);
    await page.getByText(expected.resultStatus, { exact: true }).waitFor();
    await page.getByText(expected.resultLog, { exact: true }).waitFor();
    await page.getByLabel(expected.resultMedia).waitFor();
    await page.locator(".project-result-breadcrumb").getByText(expected.resultBreadcrumb, { exact: true }).waitFor();
    await page.locator(".project-result-summary dt").getByText(expected.createdAt, { exact: true }).waitFor();
    await page.locator(".project-result-summary dd").getByText(expected.createdDate, { exact: true }).waitFor();
    await page.getByRole("link", { name: expected.resultAction, exact: true }).first().waitFor();
    await page.getByRole("button", { name: /分享项目|Share project|プロジェクトを共有/ }).click();
    assert.equal((await page.locator(".dashboard-toast > span").innerText()).trim(), expected.resultToast);
    for (const literal of ["霸总短剧解说 01", "1080 × 1920", "01:25"]) await page.getByText(literal, { exact: false }).first().waitFor();

    await page.goto(`${baseUrl}/dashboard/narration/settings`);
    await selectLocale(locale);
    assert.equal((await page.locator("[data-route-heading]").textContent()).trim(), expected.settingsHeading);
    assert.equal(await page.title(), expected.settingsTitle);
    await page.getByRole("link", { name: expected.settingsAction }).waitFor();
    await page.getByLabel(expected.settingsMedia).waitFor();
    await page.locator(".narration-stepper").getByText(expected.exportStep, { exact: true }).waitFor();
    await page.locator(".narration-topbar button").click();
    assert.equal((await page.locator(".dashboard-toast > span").innerText()).trim(), expected.settingsToast);
    await page.getByText("霸总短剧解说 01", { exact: true }).waitFor();
    await page.getByText("01:25", { exact: true }).waitFor();

    await page.goto(`${baseUrl}/dashboard/narration/analysis`);
    await selectLocale(locale);
    assert.equal((await page.locator("[data-route-heading]").textContent()).trim(), expected.analysisHeading);
    assert.equal(await page.title(), expected.analysisPageTitle);
    await page.getByRole("heading", { name: expected.analysisTitle }).waitFor();
    await page.getByText(expected.analysisLog, { exact: true }).waitFor();
    assert.equal(await page.locator(".analysis-stage small").filter({ hasText: expected.analysisDone }).count(), 2);
    await page.getByRole("button", { name: expected.analysisMedia, exact: true }).waitFor();
    await page.getByRole("button", { name: expected.analysisAction }).waitFor();
    for (const literal of ["EP01", "EP02", "EP03", "EP04", "08:42", "03:21"]) await page.getByText(literal, { exact: true }).first().waitFor();
  }

  await page.goto(`${baseUrl}/`);
  await selectLocale("ja");

  const trigger = page.getByTestId("language-switcher-trigger");
  await trigger.focus();
  await trigger.press("Enter");
  const japaneseMenuItem = page.getByRole("menuitem", { name: "日本語" });
  await japaneseMenuItem.waitFor();
  await japaneseMenuItem.press("ArrowDown");
  assert.equal(await page.getByRole("menuitem", { name: "简体中文" }).evaluate((node) => node === document.activeElement), true);
  await page.keyboard.press("Escape");
  await page.getByRole("menu").waitFor({ state: "detached" });
  assert.equal(await trigger.evaluate((node) => node === document.activeElement), true);

  await trigger.click();
  await page.getByRole("menu").waitFor();
  await page.locator(".hero-section").click({ position: { x: 20, y: 300 } });
  await page.getByRole("menu").waitFor({ state: "detached" });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator(".menu-button").click();
  const inlineSwitcher = page.locator(".language-switcher--inline");
  await inlineSwitcher.waitFor();
  for (const language of ["简体中文", "English", "日本語"]) {
    await inlineSwitcher.getByRole("button", { name: language, exact: true }).waitFor();
  }

  for (const locale of ["zh-CN", "en", "ja"]) {
    const expected = EXPECTED_COPY[locale];
    for (const route of ["/dashboard", "/dashboard/create", "/dashboard/projects"]) {
      await page.setViewportSize({ width: 1487, height: 900 });
      await page.goto(`${baseUrl}${route}`);
      await page.getByTestId("language-switcher-trigger").waitFor();
      await selectLocale(locale);
      assert.equal((await page.locator("[data-route-heading]").textContent()).trim(), expected.routeHeadings[route]);
      if (route === "/dashboard") await page.getByRole("heading", { name: expected.dashboardTitle }).waitFor();
      if (route === "/dashboard/create") await page.getByRole("heading", { name: expected.createTitle }).waitFor();
      if (route === "/dashboard/projects") await page.getByText(expected.projectsTitle, { exact: true }).waitFor();
      if (route === "/dashboard/projects") assert.equal((await page.locator(".project-date").first().textContent()).trim(), expected.workflow.createdDate);

      const action = route === "/dashboard"
        ? page.locator(".dashboard-account__recharge")
        : route === "/dashboard/create"
          ? page.locator(".create-summary__next")
          : page.locator(".project-actions__export").first();
      await action.click();
      await page.locator(".dashboard-toast").waitFor();
      assert.equal((await page.locator(".dashboard-toast > span").innerText()).trim(), expected.routeToasts[route], `${locale} ${route} should show localized feedback`);

      if (route === "/dashboard") {
        assert.equal(await page.getByRole("group", { name: expected.accountActions }).count(), 1, `${locale} account actions should expose group semantics`);
        assert.equal(await page.locator(".dashboard-account > .language-switcher + .dashboard-account__balance").count(), 1, `${locale} switcher should immediately precede balance`);
        const accountTargetHeights = await page.locator(".dashboard-account__balance, .dashboard-account__recharge").evaluateAll((elements) => elements.map((element) => element.getBoundingClientRect().height));
        assert.equal(accountTargetHeights.every((height) => height >= 44), true, `${locale} desktop account targets should be at least 44px high`);
      }

      for (const width of [1487, 768, 390]) {
        await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true, `${locale} ${route} must not overflow at ${width}px`);
      }
    }
  }

  await page.setViewportSize({ width: 1487, height: 900 });
  await page.goto(`${baseUrl}/dashboard/narration/editor`);
  await selectLocale("zh-CN");
  const editorVideo = page.getByTestId("preview-video");
  await editorVideo.waitFor();
  await page.locator(".editor-clip-list > button").nth(1).click();
  const scriptTextarea = page.locator(".inspector-copy textarea");
  const editedScript = "保留原始项目内容的编辑状态";
  await scriptTextarea.fill(editedScript);
  const zoom = page.getByLabel("时间轴缩放");
  await zoom.evaluate((node) => {
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    setValue.call(node, "60");
    node.dispatchEvent(new Event("input", { bubbles: true }));
    node.dispatchEvent(new Event("change", { bubbles: true }));
  });
  const editorBefore = await page.evaluate(() => {
    const video = document.querySelector('[data-testid="preview-video"]');
    video.currentTime = 1.25;
    window.__i18nEditorVideo = video;
    return {
      path: location.pathname,
      currentTime: video.currentTime,
      selection: [...document.querySelectorAll(".timeline-clip.is-selected")].map((node) => node.dataset.clipId).sort(),
      zoom: document.querySelector('[aria-label="时间轴缩放"]').value,
      script: document.querySelector(".inspector-copy textarea").value,
      project: document.querySelector(".editor-topbar > strong").textContent.trim(),
      cue: document.querySelector('[data-testid="subtitle"]').textContent.trim(),
    };
  });
  await selectLocale("ja");
  const editorAfter = await page.evaluate(() => {
    const video = document.querySelector('[data-testid="preview-video"]');
    return {
      sameVideo: video === window.__i18nEditorVideo,
      path: location.pathname,
      currentTime: video.currentTime,
      selection: [...document.querySelectorAll(".timeline-clip.is-selected")].map((node) => node.dataset.clipId).sort(),
      zoom: document.querySelector('[aria-label="タイムラインのズーム"]').value,
      script: document.querySelector(".inspector-copy textarea").value,
      project: document.querySelector(".editor-topbar > strong").textContent.trim(),
      cue: document.querySelector('[data-testid="subtitle"]').textContent.trim(),
    };
  });
  assert.equal(editorAfter.sameVideo, true, "locale switching must preserve the preview video DOM node");
  assert.equal(editorAfter.path, editorBefore.path);
  assert.ok(Math.abs(editorAfter.currentTime - editorBefore.currentTime) <= 0.25, "locale switching must preserve media time");
  assert.deepEqual(editorAfter.selection, editorBefore.selection);
  assert.equal(editorAfter.zoom, editorBefore.zoom);
  assert.equal(editorAfter.script, editedScript);
  assert.equal(editorAfter.project, editorBefore.project);
  assert.equal(editorAfter.cue, editorBefore.cue);
  assert.equal((await page.locator("[data-route-heading]").textContent()).trim(), EXPECTED_COPY.ja.editor.heading);
  await page.getByRole("button", { name: EXPECTED_COPY.ja.editor.saveDraft, exact: true }).waitFor();
  await page.getByLabel(ja.editor.script.input).waitFor();
  await page.getByLabel(ja.editor.preview.progress).waitFor();
  await page.getByLabel(ja.editor.timeline.zoom).waitFor();
  for (const label of [ja.editor.preview.start, ja.editor.preview.play, ja.editor.preview.forwardOne, ja.editor.preview.end, ja.editor.preview.volume, ja.editor.preview.fullscreen]) {
    await page.getByRole("button", { name: label, exact: true }).waitFor();
  }
  await page.getByLabel(ja.editor.preview.speed, { exact: true }).waitFor();
  assert.deepEqual(
    await page.locator(".timeline-row > label").evaluateAll((labels) => labels.map((label) => label.lastChild.textContent.trim())),
    Object.values(ja.editor.timeline.tracks),
  );
  assert.ok(await page.getByRole("button", { name: ja.editor.timeline.trimStart, exact: true }).count() > 0);
  assert.ok(await page.getByRole("button", { name: ja.editor.timeline.trimEnd, exact: true }).count() > 0);
  for (const preset of Object.values(ja.editor.presets)) await page.locator(".inspector-settings").getByText(preset, { exact: true }).waitFor();
  for (const action of [ja.editor.settings.editVoiceRole, ja.editor.settings.editSubtitleStyle, ja.editor.settings.editBackgroundMusic]) {
    await page.getByRole("button", { name: action, exact: true }).waitFor();
  }
  await page.getByRole("button", { name: ja.editor.tabs.subtitle, exact: true }).click();
  await page.locator(".subtitle-editor textarea").first().waitFor();
  await page.getByLabel(ja.editor.subtitle.cue.replace("{time}", "00:00"), { exact: true }).waitFor();
  await page.getByRole("button", { name: ja.editor.tabs.bgm, exact: true }).click();
  await page.getByText(ja.editor.bgm.currentFile.replace("{file}", "0e5bf3db017e0e593c4eef4144d7c68a.mp3"), { exact: true }).waitFor();
  await page.getByText(ja.editor.bgm.reselect, { exact: true }).waitFor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true, "editor must not create page-level horizontal overflow");
  await page.setViewportSize({ width: 1024, height: 900 });
  const compactSwitcherBox = await page.getByTestId("language-switcher-trigger").boundingBox();
  assert.ok(compactSwitcherBox && compactSwitcherBox.x >= 0 && compactSwitcherBox.x + compactSwitcherBox.width <= 1024, "compact editor switcher must remain reachable at narrow desktop widths");
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true, "narrow editor must not create page-level horizontal overflow");

  await page.setViewportSize({ width: 1487, height: 900 });
  await page.goto(`${baseUrl}/dashboard/projects`);
  await selectLocale("en");
  const projectSearch = page.locator(".project-search input");
  await projectSearch.fill("霸总短剧解说 01");
  await page.getByText("霸总短剧解说 01", { exact: true }).waitFor();
  await selectLocale("ja");
  assert.equal(await projectSearch.inputValue(), "霸总短剧解说 01");
  await page.getByText("霸总短剧解说 01", { exact: true }).waitFor();

  const screenshotDirectory = path.join(projectRoot, "artifacts", "i18n");
  await mkdir(screenshotDirectory, { recursive: true });
  for (const locale of ["zh-CN", "en", "ja"]) {
    const resource = RESOURCES[locale];
    for (const viewport of VIEWPORT_MATRIX) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      for (const route of ROUTE_MATRIX) {
        await page.evaluate(([storageKey, value]) => localStorage.setItem(storageKey, value), ["narrato.locale", locale]);
        const errorStart = browserErrors.length;
        const response = await page.goto(`${baseUrl}${route.path}`, { waitUntil: "domcontentloaded" });
        assert.ok(response?.ok(), `${locale} ${route.path} ${viewport.name} must return a successful document response`);
        const heading = page.locator(route.headingSelector ?? "[data-route-heading]");
        await heading.waitFor();
        assert.equal(await page.locator("html").getAttribute("lang"), locale, `${locale} ${route.path} ${viewport.name} must set html[lang]`);
        assert.equal(await page.title(), resource.titles[route.titleKey], `${locale} ${route.path} ${viewport.name} must set the localized title`);
        assert.equal((await heading.textContent()).replace(/\s+/g, " ").trim(), route.heading(resource), `${locale} ${route.path} ${viewport.name} must render the localized route heading`);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true, `${locale} ${route.path} must not overflow at ${viewport.width}×${viewport.height}`);
        await page.waitForTimeout(30);
        assert.deepEqual(browserErrors.slice(errorStart), [], `${locale} ${route.path} ${viewport.name} must not emit browser errors`);

        if ((locale === "en" || locale === "ja") && route.path === "/") {
          await page.screenshot({ path: path.join(screenshotDirectory, `${locale}-${viewport.name}.png`), fullPage: true });
        }
      }
    }
  }

  await context.close();
  console.log(`i18n verification passed: ${ROUTE_MATRIX.length} routes × ${Object.keys(RESOURCES).length} locales × ${VIEWPORT_MATRIX.length} viewports`);
} finally {
  await browser?.close();
  await stopPreview(preview);
}
