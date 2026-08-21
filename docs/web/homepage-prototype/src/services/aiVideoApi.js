import { apiRequest } from "./httpClient.js";
import { normalizeModels } from "../features/ai-video/modelCapabilities.js";

const ROOT = "/products/ai-video";
const startOfDayIso = (day) => day ? new Date(`${day}T00:00:00.000Z`).toISOString() : "";
const nextDayIso = (day) => {
  if (!day) return "";
  const value = new Date(`${day}T00:00:00.000Z`);
  value.setUTCDate(value.getUTCDate() + 1);
  return value.toISOString();
};

export async function listAiVideoModels(request = apiRequest) {
  const payload = await request(`${ROOT}/models`);
  return { items: normalizeModels(payload?.items || payload), defaultModelId: payload?.default_model_id || payload?.defaultModelId || null };
}

/** 仅在用户选中模型后加载玩法规则、能力参数和计费展示信息。 */
export async function getAiVideoModelGenParam(modelId, request = apiRequest) {
  return request(`${ROOT}/models/${encodeURIComponent(modelId)}/gen-params`);
}

// 与产品侧约定的 modelGenParam 命名保持一致。
export const modelGenParam = getAiVideoModelGenParam;

export async function createAiVideoDraft(request = apiRequest) {
  return request(`${ROOT}/drafts`, {
    method: "POST",
  });
}

export function quoteAiVideoTask({ modelId, playModeId, resolution, durationSeconds }, request = apiRequest) {
  return request(`${ROOT}/quote`, { method: "POST", body: JSON.stringify({ model_id: modelId, play_mode_id: playModeId || undefined, resolution: resolution || undefined, duration_seconds: durationSeconds || undefined }) });
}

export function listAiVideoTasks(filters = {}, request = apiRequest) {
  const params = new URLSearchParams();
  if (filters.type && filters.type !== "all") params.set("type", filters.type);
  if (filters.startDate) params.set("created_from", startOfDayIso(filters.startDate));
  // 服务端以 < created_to 处理；传次日 00:00 的排他上界，不遗漏结束当天的任务。
  if (filters.endDate) params.set("created_to", nextDayIso(filters.endDate));
  if (filters.view) params.set("view", filters.view === "grid" ? "gallery" : "list");
  if (filters.page) params.set("page", String(filters.page));
  if (filters.pageSize) params.set("page_size", String(filters.pageSize));
  return request(`${ROOT}/tasks${params.size ? `?${params}` : ""}`);
}

export function submitAiVideoTask(payload, request = apiRequest) {
  return request(`${ROOT}/tasks`, {
    method: "POST",
    headers: { "X-Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify(payload),
  });
}

export function retryAiVideoTask(taskId, request = apiRequest) {
  return request(`${ROOT}/tasks/${encodeURIComponent(taskId)}/retry`, { method: "POST" });
}

export function getAiVideoAsset(assetId, request = apiRequest) {
  return request(`/assets/${encodeURIComponent(assetId)}`);
}

function imageContentType(file) {
  const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  return { ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp" }[extension] || file.type;
}

/** AI 视频草稿仍沿用项目受控 OSS policy；projectId 由 draft 接口返回。 */
export async function uploadAiVideoImage(projectId, file, request = apiRequest, postToOss = (url, form) => fetch(url, { method: "POST", body: form })) {
  const contentType = imageContentType(file);
  if (!contentType?.startsWith("image/")) throw new Error("仅支持 JPG、PNG 或 WebP 图片");
  const declaration = { asset_type: "image", filename: file.name, size_bytes: file.size, content_type: contentType };
  const policy = await request(`/projects/${projectId}/uploads/policy`, { method: "POST", body: JSON.stringify(declaration) });
  const form = new FormData();
  Object.entries(policy.fields || {}).forEach(([key, value]) => form.append(key, value));
  form.append("key", policy.key); form.append("file", file);
  const uploaded = await postToOss(policy.url, form);
  if (!uploaded.ok) throw new Error("图片上传失败");
  return request(`/projects/${projectId}/uploads/complete`, { method: "POST", body: JSON.stringify({ ...declaration, object_key: policy.key }) });
}
