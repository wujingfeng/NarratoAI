import { apiRequest } from "../../services/httpClient.js";

export const canStartProject = (assets) => assets.length > 0 && assets.every((asset) => asset.status === "ready");

export function createProject(request = apiRequest) {
  return request("/projects", { method: "POST", body: JSON.stringify({ product: "short-drama-narration" }) });
}

export function estimateProjectCost(projectId, request = apiRequest) {
  return request(`/projects/${projectId}/cost-estimate`, { method: "POST" });
}

export function getAsset(assetId, request = apiRequest) {
  return request(`/assets/${assetId}`);
}

export async function startProject(projectId, assets, request = apiRequest) {
  if (!canStartProject(assets)) throw new Error("所有素材必须校验为 ready 后才能开始");
  return request(`/projects/${projectId}/start`, { method: "POST" });
}

/** 仅对内容编辑结果防抖；指针移动、播放头和本地选中不应调用这个函数。 */
export function createDebouncedEditorSaver(projectId, request = apiRequest, delay = 600) {
  let timer;
  return (content) => new Promise((resolve, reject) => {
    globalThis.clearTimeout(timer);
    timer = globalThis.setTimeout(() => request(`/projects/${projectId}/editor/save`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }).then(resolve, reject), delay);
  });
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
