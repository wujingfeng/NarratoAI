import { apiRequest } from "../../services/httpClient.js";

/** 浏览器直传的单文件上限；服务端策略同样会再次校验。 */
export const MAX_UPLOAD_SIZE_BYTES = 300 * 1024 * 1024;

function declaration(file, assetType) {
  if (file.size > MAX_UPLOAD_SIZE_BYTES) throw new Error("单个文件不能超过 300 MiB");
  return {
    asset_type: assetType,
    filename: file.name,
    size_bytes: file.size,
    content_type: file.type || "application/octet-stream",
  };
}

/** 申请受限 OSS policy，POST 成功后立即向 API 确认，启动异步校验。 */
export async function uploadAsset(projectId, file, assetType, dependencies = {}) {
  const request = dependencies.request || apiRequest;
  const postToOss = dependencies.postToOss || ((url, form) => fetch(url, { method: "POST", body: form }));
  const payload = declaration(file, assetType);
  const policy = await request(`/projects/${projectId}/uploads/policy`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (file.size > policy.max_size_bytes) throw new Error("文件超过本次上传策略允许的大小");

  const form = new FormData();
  Object.entries(policy.fields).forEach(([key, value]) => form.append(key, value));
  form.append("key", policy.key);
  form.append("file", file);
  const ossResponse = await postToOss(policy.url, form);
  if (!ossResponse.ok) throw new Error(`OSS upload failed: ${ossResponse.status || "unknown"}`);

  return request(`/projects/${projectId}/uploads/complete`, {
    method: "POST",
    body: JSON.stringify({ ...payload, object_key: policy.key }),
  });
}
