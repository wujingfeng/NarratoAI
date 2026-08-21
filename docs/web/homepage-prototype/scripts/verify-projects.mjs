import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const targets = ["src/pages/ProjectsPage.jsx", "src/components/projects", "src/features/projects/projectDeletion.js", "src/styles/projects.css", "src/data/projectsData.js"];
const forbidden = [["reference image", /06-projects-desktop\.png/i], ["data image", /data:image/i], ["base64", /base64/i], ["canvas", /<canvas\b|CanvasRenderingContext2D|drawImage\s*\(/i], ["CSS url background", /background-image\s*:\s*url\s*\(/i], ["SVG bitmap", /<image\b|xlink:href\s*=|href\s*=\s*["']data:image/i]];

async function files(target) {
  const absolute = path.join(root, target);
  const entries = await readdir(absolute, { withFileTypes: true }).catch(() => null);
  if (!entries) return [absolute];
  return (await Promise.all(entries.map((entry) => entry.isDirectory() ? files(path.join(target, entry.name)) : [path.join(root, target, entry.name)]))).flat();
}

const violations = [];
for (const target of targets) {
  for (const file of await files(target)) {
    const source = await readFile(file, "utf8");
    for (const [label, regex] of forbidden) if (regex.test(source)) violations.push(`${path.relative(root, file)}: ${label}`);
  }
}
if (violations.length) throw new Error(`Projects page anti-paste scan failed:\n${violations.join("\n")}`);
console.log("Projects page anti-paste scan passed");
if (process.env.PROJECTS_SCAN_ONLY === "1") process.exit(0);

const createdAt = "2026-08-05T08:00:00Z";
const firstVideoUrl = `${baseUrl}/media/project-result/overlord-narration-result-85s.mp4`;
const projects = [
  { id: "project-created", status: "draft", current_stage: "created", title: "待上传项目.mp4" },
  { id: "project-settings", status: "ready", current_stage: "settings", title: "待设置项目.mp4" },
  { id: "project-completed", status: "completed", current_stage: "export", title: "已完成项目.mp4" },
  { id: "project-failed", status: "failed", current_stage: "generate", title: "失败项目.mp4" },
  ...Array.from({ length: 6 }, (_, index) => ({ id: `project-running-${index + 1}`, status: "analyzing", current_stage: "analysis", title: `处理中项目 ${index + 1}.mp4` })),
  { id: "project-last-page", status: "completed", current_stage: "export", title: "末页项目.mp4" },
].map((project, index) => ({
  ...project,
  product: "short_drama_narration",
  duration_seconds: 60 + index,
  thumbnail_url: project.id === "project-created" ? firstVideoUrl : null,
  credits: index + 1,
  created_at: createdAt,
}));

const executablePath = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await chromium.launch({ executablePath, headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const failures = [];
const deletedIds = new Set();
const deletionRequests = [];
const stageRequests = [];
const retryDraftRequests = [];
const costEstimateRequests = [];
let failProjectOnce = true;
let failNextProjectList = false;

page.setDefaultTimeout(10000);
page.on("pageerror", (error) => failures.push(`pageerror: ${error.message}`));
page.on("console", (message) => {
  if (message.type() === "error" && !/status of (409 \(Conflict\)|503 \(Service Unavailable\))/.test(message.text())) failures.push(`console.error: ${message.text()}`);
});
await page.addInitScript(() => {
  localStorage.setItem("narrato.api.token", "token-projects-verify");
  localStorage.setItem("narrato.locale", "zh-CN");
});
await page.route("**/oss-verify", async (route) => route.fulfill({ status: 204, body: "" }));

await page.route("**/api/v1/**", async (route) => {
  const request = route.request();
  const url = new URL(request.url());
  const apiPath = url.pathname.replace(/^\/api\/v1/, "");
  if (apiPath === "/users/me") {
    await fulfill(route, { id: "usr_projects", email: "projects@example.test", credit_balance: 1280 });
    return;
  }
  if (apiPath === "/projects" && request.method() === "GET") {
    if (failNextProjectList) {
      failNextProjectList = false;
      await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ code: "INTERNAL_SERVER_ERROR", message: "Project list unavailable", data: null, request_id: "req_projects_list_failed" }) });
      return;
    }
    const pageNumber = Number(url.searchParams.get("page") || 1);
    const pageSize = Number(url.searchParams.get("page_size") || 10);
    const visible = projects.filter((project) => !deletedIds.has(project.id));
    const start = (pageNumber - 1) * pageSize;
    await fulfill(route, { items: visible.slice(start, start + pageSize), page: pageNumber, page_size: pageSize, total: visible.length });
    return;
  }
  if (apiPath === "/projects/project-created/retry-draft" && request.method() === "POST") {
    retryDraftRequests.push("project-created");
    await fulfill(route, { project_id: "project-retry", status: "draft" }, 201);
    return;
  }
  const stageMatch = apiPath.match(/^\/projects\/([^/]+)\/stage$/);
  if (stageMatch && request.method() === "GET") {
    const projectId = decodeURIComponent(stageMatch[1]);
    stageRequests.push(projectId);
    const project = projects.find((item) => item.id === projectId);
    await new Promise((resolve) => setTimeout(resolve, 120));
    await fulfill(route, {
      project_id: projectId,
      project_title: project?.title || projectId,
      project_status: projectId === "project-created" ? "ready" : projectId === "project-retry" ? "draft" : project?.status,
      // 列表快照仍为 created，实时接口返回 settings，用于验证按钮没有依赖陈旧列表阶段。
      current_stage: projectId === "project-created" ? "settings" : projectId === "project-retry" ? "created" : project?.current_stage,
      execution_mode: "manual",
      workflow_state: null,
      failure_code: null,
      updated_at: createdAt,
      stages: [],
      analysis_tasks: [],
      video_assets: ["project-created", "project-retry"].includes(projectId) ? [{ id: projectId === "project-created" ? "asset-created" : "asset-retry", filename: "待上传项目.mp4", cdn_url: "", duration_seconds: 60 }] : [],
    });
    return;
  }
  if (apiPath === "/products/short-drama-narration/config" && request.method() === "GET") {
    await fulfill(route, {
      narration_styles: [{ id: "悬疑/犯罪", name: "悬疑/犯罪", eyebrow: "悬念推进", description: "突出剧情冲突", tags: ["悬疑"], is_custom: false }],
      original_sound_ratios: [0, 30, 70, 90],
      video_ratios: [{ id: "9:16", name: "9:16" }],
      voices: [{ id: "voice_real", name: "沉稳男声", provider_code: "fake", languages: ["zh-CN"], gender: "male", styles: [], sample_url: null }],
      subtitle_styles: [{ id: "经典白色", name: "经典白色" }],
    });
    return;
  }
  const costEstimateMatch = apiPath.match(/^\/projects\/([^/]+)\/cost-estimate$/);
  if (costEstimateMatch && request.method() === "POST") {
    const projectId = costEstimateMatch[1];
    costEstimateRequests.push(projectId);
    if (!["project-created", "project-retry"].includes(projectId)) failures.push(`unexpected cost estimate project: ${projectId}`);
    await fulfill(route, { total_seconds: 60, estimated_output_seconds: 30, credits: 60 });
    return;
  }
  if (apiPath === "/projects/project-retry/uploads/policy" && request.method() === "POST") {
    await fulfill(route, { url: `${baseUrl}/oss-verify`, fields: {}, key: "narrato/project-retry/retry-subtitle.srt", max_size_bytes: 5 * 1024 * 1024 });
    return;
  }
  if (apiPath === "/projects/project-retry/uploads/complete" && request.method() === "POST") {
    await fulfill(route, { id: "asset-retry-subtitle", status: "ready", filename: "retry-subtitle.srt", cdn_url: "", duration_seconds: null });
    return;
  }
  if (apiPath === "/projects/project-created/narration/settings" && request.method() === "GET") {
    await fulfill(route, { execution_mode: "manual", source_subtitle_layouts: {} });
    return;
  }
  const deletionMatch = apiPath.match(/^\/projects\/([^/]+)\/deletion-requests$/);
  if (deletionMatch && request.method() === "POST") {
    const projectId = deletionMatch[1];
    deletionRequests.push(projectId);
    await new Promise((resolve) => setTimeout(resolve, 120));
    if (projectId === "project-failed" && failProjectOnce) {
      failProjectOnce = false;
      await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ code: "PROJECT_NOT_TERMINAL", message: "Project state changed", data: null, request_id: "req_delete_failed" }) });
      return;
    }
    deletedIds.add(projectId);
    await fulfill(route, { job_id: `job-${projectId}`, project_id: projectId, status: "pending" }, 202);
    return;
  }
  failures.push(`unexpected API request: ${request.method()} ${apiPath}`);
  await fulfill(route, {});
});

try {
  await page.goto(`${baseUrl}/dashboard/projects`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "我的项目", level: 2 }).waitFor();
  await page.waitForFunction(() => document.querySelectorAll(".projects-table tbody tr").length === 10);
  assert.equal(await page.locator(".projects-table tbody tr .project-actions__retry").count(), 10, "当前页每条项目记录都必须提供重新生成");
  const firstProjectPreview = page.locator(".projects-table tbody tr", { hasText: "待上传项目" }).locator(".dashboard-thumbnail video");
  await firstProjectPreview.waitFor();
  assert.equal(await firstProjectPreview.getAttribute("src"), firstVideoUrl, "项目列表缩略位必须使用首个上传视频的真实地址");

  const continueButton = page.getByRole("button", { name: "继续编辑" });
  await continueButton.click();
  await page.locator('.project-actions__continue[aria-busy="true"]').waitFor();
  await page.waitForURL(`${baseUrl}/dashboard/narration/settings?projectId=project-created`);
  await page.getByRole("heading", { name: "待上传项目.mp4", level: 2 }).waitFor();
  assert.equal(stageRequests[0], "project-created", "继续编辑必须先读取服务端当前阶段");
  assert.equal(await page.locator('[data-page="narration-settings"]').count(), 1, "继续编辑必须进入服务端返回的真实阶段页面");

  await page.goto(`${baseUrl}/dashboard/projects`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "我的项目", level: 2 }).waitFor();
  await page.waitForFunction(() => document.querySelectorAll(".projects-table tbody tr").length === 10);

  const completedRow = page.locator(".projects-table tbody tr", { hasText: "已完成项目" });
  await completedRow.getByRole("button", { name: /重新生成/ }).click();
  await page.waitForURL(`${baseUrl}/dashboard/narration/settings?retrySourceProjectId=project-completed`);
  await page.goto(`${baseUrl}/dashboard/projects`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "我的项目", level: 2 }).waitFor();
  await page.waitForFunction(() => document.querySelectorAll(".projects-table tbody tr").length === 10);

  costEstimateRequests.length = 0;
  const retrySourceRow = page.locator(".projects-table tbody tr", { hasText: "待上传项目" });
  await retrySourceRow.getByRole("button", { name: /重新生成/ }).click();
  await page.waitForURL(`${baseUrl}/dashboard/narration/settings?retrySourceProjectId=project-created`);
  const retryVideoRow = page.locator("[data-video-row]").first();
  await retryVideoRow.locator('input[type="file"][accept*=".srt"]').setInputFiles({
    name: "retry-subtitle.srt",
    mimeType: "application/x-subrip",
    buffer: Buffer.from("1\n00:00:00,000 --> 00:00:01,000\n重试字幕"),
  });
  await retryVideoRow.getByText("retry-subtitle.srt", { exact: true }).waitFor();
  await retryVideoRow.locator(".create-video-row__status--success").waitFor();
  await page.waitForFunction(() => document.querySelector(".create-summary__credits")?.textContent?.includes("60"));
  assert.deepEqual(retryDraftRequests, ["project-created"], "首次上传字幕必须先且仅创建一次新草稿");
  assert.deepEqual(costEstimateRequests, ["project-retry"], "字幕首次上传后的报价只能针对新草稿，不能访问源项目");

  await page.goto(`${baseUrl}/dashboard/projects`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "我的项目", level: 2 }).waitFor();
  await page.waitForFunction(() => document.querySelectorAll(".projects-table tbody tr").length === 10);

  const selectAll = page.getByRole("checkbox", { name: "选择当前页全部可删除项目" });
  await selectAll.check();
  assert.equal(await page.locator(".projects-table tbody .project-selection-checkbox:checked").count(), 4, "全选只能选中当前页可删除项目");
  assert.equal(await page.locator(".projects-table tbody .project-selection-checkbox:disabled").count(), 6, "处理中的项目必须禁用选择");
  await selectAll.uncheck();

  for (const width of [375, 768]) {
    await page.setViewportSize({ width, height: 1000 });
    const mobileSelectAll = page.getByRole("button", { name: "选择当前页全部可删除项目" });
    assert.equal(await mobileSelectAll.isVisible(), true, `${width}px 必须提供移动端全选入口`);
    await mobileSelectAll.click();
    assert.equal(await page.locator(".projects-table tbody .project-selection-checkbox:checked").count(), 4, `${width}px 移动端全选必须只选择可删除项目`);
    await page.getByRole("button", { name: "取消全选" }).click();
    assert.equal(await page.locator(".projects-table tbody .project-selection-checkbox:checked").count(), 0, `${width}px 移动端必须支持取消全选`);
    assert.equal(await page.locator(".project-mobile-field-label").count(), 30, `${width}px 卡片字段必须保留可访问标签`);
  }
  await page.setViewportSize({ width: 1440, height: 1000 });

  await page.getByRole("button", { name: "下一页" }).click();
  await page.waitForFunction(() => document.querySelectorAll(".projects-table tbody tr").length === 1);
  assert.match(await page.locator(".projects-bulk-toolbar strong").textContent(), /0/, "翻页后必须清空选择");
  await page.getByLabel("选择项目 末页项目").check();
  await page.getByRole("button", { name: "批量删除（1）" }).click();
  await page.getByRole("dialog", { name: "确认批量删除项目？" }).waitFor();
  await page.getByRole("button", { name: "删除 1 个项目" }).click();
  await page.getByRole("button", { name: "正在删除…" }).waitFor();
  await page.waitForFunction(() => document.querySelector(".project-pagination button.is-active")?.textContent?.trim() === "1");
  await page.waitForFunction(() => document.querySelectorAll(".projects-table tbody tr").length === 10);
  await page.waitForFunction(() => document.activeElement?.id === "projects-title");
  assert.ok(deletionRequests.includes("project-last-page"), "末页删除必须调用单项目删除接口");

  await page.getByRole("checkbox", { name: "选择当前页全部可删除项目" }).check();
  await page.getByRole("button", { name: "批量删除（4）" }).click();
  await page.getByRole("button", { name: "删除 4 个项目" }).click();
  await page.getByRole("button", { name: "正在删除…" }).waitFor();
  await page.getByText("已提交 3 个项目，另有 1 个删除失败").waitFor();
  await page.waitForFunction(() => document.querySelectorAll(".projects-table tbody tr").length === 7);
  assert.equal(await page.locator(".projects-table tbody .project-selection-checkbox:checked").count(), 1, "部分失败后只保留失败项目选择");

  await page.getByRole("button", { name: "批量删除（1）" }).click();
  await page.getByRole("button", { name: "删除 1 个项目" }).click();
  await page.getByText("已提交 1 个项目的删除请求").waitFor();
  await page.waitForFunction(() => document.querySelectorAll(".projects-table tbody tr").length === 6);

  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    const metrics = await page.evaluate(() => ({
      documentOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      bodyOverflow: document.body.scrollWidth - document.body.clientWidth,
      rowDisplay: getComputedStyle(document.querySelector(".projects-table tbody tr")).display,
      checkbox: document.querySelector(".projects-table tbody .project-selection-checkbox")?.getBoundingClientRect().toJSON(),
    }));
    assert.ok(metrics.documentOverflow <= 1 && metrics.bodyOverflow <= 1, `${width}px 页面不应横向溢出：${JSON.stringify(metrics)}`);
    assert.equal(metrics.rowDisplay, width <= 820 ? "grid" : "table-row", `${width}px 应使用对应的响应式表格布局`);
    assert.ok(metrics.checkbox && metrics.checkbox.x >= 0 && metrics.checkbox.x + metrics.checkbox.width <= width + 1, `${width}px 选择框必须可见`);
  }

  await page.setViewportSize({ width: 1440, height: 1000 });
  failNextProjectList = true;
  await page.getByPlaceholder("搜索项目名称").fill("force-list-error");
  const loadError = page.getByRole("alert");
  await loadError.waitFor();
  assert.match(await loadError.textContent(), /req_projects_list_failed/, "列表错误应保留请求编号");
  assert.equal(await page.locator(".projects-table").count(), 0, "列表错误时不得继续显示旧表格");
  assert.equal(await page.locator(".projects-empty").count(), 0, "列表错误时不得同时显示空态");
  await page.getByPlaceholder("搜索项目名称").fill("");
  await page.waitForFunction(() => document.querySelectorAll(".projects-table tbody tr").length === 6);

  assert.equal(deletionRequests.filter((id) => id === "project-failed").length, 2, "失败项目应支持保留选择后重试");
  assert.equal(failures.length, 0, failures.join("\n"));
  console.log("Projects all-status regeneration, first retry subtitle upload, continue flow, batch deletion, mobile select-all, error state, focus recovery, and 375/768/1024/1440 responsive checks passed");
} finally {
  await browser.close();
}

async function fulfill(route, data, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify({ code: "OK", message: "ok", data, request_id: "req_projects_verify" }) });
}
