import { apiRequest } from "../../services/httpClient.js";

export const canStartProject = (assets) => assets.length > 0 && assets.every((asset) => asset.status === "ready");
const PROJECT_PRODUCT_BY_CREATION_TYPE = {
  narration: "short-drama-narration",
  translation: "video-translation",
};

export function createProject(product = "short-drama-narration", request = apiRequest) {
  // 兼容既有 createProject(fakeRequest) 测试/调用方，并将创建页内部类型
  // 映射为 Business API 接受的产品 key。
  if (typeof product === "function") { request = product; product = "short-drama-narration"; }
  return request("/projects", { method: "POST", body: JSON.stringify({ product: PROJECT_PRODUCT_BY_CREATION_TYPE[product] || product }) });
}

/** 任意可见项目都可复用当前用户已校验的源视频和字幕，返回新的可编辑草稿。 */
export function createRetryDraft(projectId, request = apiRequest) {
  return request(`/projects/${projectId}/retry-draft`, { method: "POST" });
}

/** 重新生成必须回到原项目所属功能的素材入口，不能统一落到“新建创作”。 */
const RETRY_UPLOAD_PATH_BY_PRODUCT = {
  short_drama_narration: (projectId) => `/dashboard/narration/settings?retrySourceProjectId=${encodeURIComponent(projectId)}`,
  video_translation: (projectId) => `/dashboard/video-translation/upload?retrySourceProjectId=${encodeURIComponent(projectId)}`,
};

export function retryUploadPath(product, projectId) {
  return RETRY_UPLOAD_PATH_BY_PRODUCT[product]?.(projectId) || null;
}

export function listProjects({ page = 1, pageSize = 10, query, status, product, signal } = {}, request = apiRequest) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (query?.trim()) params.set("query", query.trim());
  if (status && status !== "all") params.set("status", status);
  if (product && product !== "all") params.set("product", product);
  return request(`/projects?${params.toString()}`, { signal });
}

/** 删除仍由服务端逐项目登记，页面批量操作只负责并发调用这个幂等边界。 */
export function requestProjectDeletion(projectId, request = apiRequest) {
  return request(`/projects/${projectId}/deletion-requests`, { method: "POST" });
}

/** 设置页只读取 Business API，避免把产品枚举散落在前端。 */
export function getNarrationConfig(request = apiRequest) {
  return request("/products/short-drama-narration/config");
}

export function estimateProjectCost(projectId, request = apiRequest) {
  return request(`/projects/${projectId}/cost-estimate`, { method: "POST" });
}

/** 短剧解说设置（包括背景音乐引用和混音音量）由项目保存，刷新页面后可恢复。 */
export function getNarrationSettings(projectId, request = apiRequest) {
  return request(`/projects/${projectId}/narration/settings`);
}

export function saveNarrationSettings(projectId, settings, request = apiRequest) {
  return request(`/projects/${projectId}/narration/settings`, {
    method: "PATCH",
    body: JSON.stringify(settings),
  });
}

/**
 * 任务阶段是服务端状态机的投影。前端只用它决定可见页面和只读态，不能自行推进。
 * `start-analysis` 在同一事务内保存完整参数快照并创建 AI 分析工作流。
 */
export function getProjectStage(projectId, request = apiRequest) {
  return request(`/projects/${projectId}/stage`);
}

/** 编辑器草稿是服务端的唯一持久化来源；提交渲染后仍可读取，但会标记为 locked。 */
export function getEditorDraft(projectId, request = apiRequest) {
  return request(`/projects/${projectId}/editor`);
}

export function saveSettingsAndStartAnalysis(projectId, settings, request = apiRequest) {
  return request(`/projects/${projectId}/narration/settings/start-analysis`, {
    method: "POST",
    body: JSON.stringify(settings),
  });
}

export function advanceProjectStage(projectId, targetStage, request = apiRequest) {
  return request(`/projects/${projectId}/stage/advance`, {
    method: "POST",
    body: JSON.stringify({ target_stage: targetStage }),
  });
}

export function getAsset(assetId, request = apiRequest) {
  return request(`/assets/${assetId}`);
}

export function removeProjectAsset(projectId, assetId, request = apiRequest) {
  return request(`/projects/${projectId}/assets/${assetId}/remove`, { method: "POST" });
}

/** 视频源顺序会被分析、脚本生成和最终渲染共同消费，必须先由服务端持久化。 */
export function reorderProjectVideoAssets(projectId, assetIds, request = apiRequest) {
  return request(`/projects/${projectId}/assets/order`, {
    method: "POST",
    body: JSON.stringify({ asset_ids: assetIds }),
  });
}

/** Result endpoint is deliberately completion-gated by the API. */
export async function getProjectResult(projectId, request = apiRequest) {
  const result = await request(`/projects/${projectId}/result`);
  return {
    id: result.project_id,
    artifacts: result.artifacts,
  };
}

export async function startProject(projectId, assets, request = apiRequest) {
  if (!canStartProject(assets)) throw new Error("所有素材必须校验为 ready 后才能开始");
  return request(`/projects/${projectId}/start`, { method: "POST" });
}

/** 仅对内容编辑结果防抖；指针移动、播放头和本地选中不应调用这个函数。 */
export function createDebouncedEditorSaver(projectId, request = apiRequest, delay = 600) {
  let timer;
  let pendingContent;
  let waiters = [];
  let saving = false;
  let inFlight = null;
  let lastError;
  const run = () => {
    if (saving) return inFlight;
    if (!pendingContent) return Promise.resolve();
    saving = true;
    const content = pendingContent;
    const currentWaiters = waiters;
    pendingContent = undefined;
    waiters = [];
    lastError = undefined;
    inFlight = Promise.resolve().then(() => request(`/projects/${projectId}/editor/save`, {
        method: "POST",
        body: JSON.stringify({ content }),
      })).then((result) => {
        currentWaiters.forEach(({ resolve }) => resolve(result));
        return result;
      }, (error) => {
        lastError = error;
        currentWaiters.forEach(({ reject }) => reject(error));
        return undefined;
      }).finally(() => {
        saving = false;
        inFlight = null;
        if (pendingContent) run();
      });
    return inFlight;
  };
  const save = (content) => new Promise((resolve, reject) => {
    pendingContent = content;
    waiters.push({ resolve, reject });
    globalThis.clearTimeout(timer);
    timer = globalThis.setTimeout(run, delay);
  });
  save.flush = async () => {
    globalThis.clearTimeout(timer);
    while (pendingContent || inFlight) await run();
    if (lastError) {
      const error = lastError;
      lastError = undefined;
      throw error;
    }
  };
  // Rendering freezes the draft. A queued write must not race that transition.
  save.cancel = () => {
    globalThis.clearTimeout(timer);
    pendingContent = undefined;
    waiters.forEach(({ resolve }) => resolve(undefined));
    waiters = [];
    lastError = undefined;
  };
  return save;
}

/** 提交渲染后立即通知 UI 锁定，避免并发保存写入可变草稿。 */
export async function submitRender(projectId, request = apiRequest, lockEditor = () => {}) {
  const result = await request(`/projects/${projectId}/render/submit`, {
    method: "POST",
    headers: { "X-Idempotency-Key": crypto.randomUUID() },
  });
  lockEditor();
  return result;
}
