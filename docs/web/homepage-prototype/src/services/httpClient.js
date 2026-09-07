import { clearToken, readToken } from "../features/auth/authStorage.js";

export const API_BASE_URL = import.meta.env?.VITE_NARRATO_API_BASE_URL || "/api/v1";

const ERROR_MESSAGES = {
  NETWORK_UNAVAILABLE: "网络连接失败，请检查网络后重试。",
  OSS_UPLOAD_UNAVAILABLE: "文件上传服务暂时不可用，请稍后重试。",
  OSS_UPLOAD_REJECTED: "文件上传失败，请重新上传或稍后重试。",
  MEDIA_PROBE_UNAVAILABLE: "媒体校验服务暂时不可用，请稍后重试。",
  MEDIA_PROBE_REJECTED: "媒体文件未通过校验，请检查文件格式后重新上传。",
  OSS_UNAVAILABLE: "上传文件校验服务暂时不可用，请稍后重试。",
  UPLOAD_OBJECT_REJECTED: "上传的文件无效或不完整，请重新上传。",
  UPLOAD_DECLARATION_REJECTED: "上传文件信息无效，请重新选择文件。",
  UPLOAD_CONTENT_TYPE_REJECTED: "文件类型与所选素材类型不一致，请重新选择文件。",
  UPLOAD_LIMIT_EXCEEDED: "上传数量已达到上限。",
  PROJECT_NOT_FOUND: "项目不存在或已被删除。",
  ASSET_NOT_FOUND: "素材不存在或已被删除。",
  AUTHENTICATION_REQUIRED: "登录已失效，请重新登录。",
  UNAUTHORIZED: "登录已失效，请重新登录。",
  FORBIDDEN: "您没有执行此操作的权限。",
  EMAIL_ALREADY_REGISTERED: "该邮箱已注册。",
  VALIDATION_ERROR: "提交的信息不符合要求，请检查后重试。",
  REQUEST_VALIDATION_ERROR: "提交的信息不符合要求，请检查后重试。",
  JIANYING_SNAPSHOT_NOT_FOUND: "剪映导出快照不完整，请重新生成视频后再试。",
  JIANYING_MANIFEST_INVALID: "剪映草稿数据无效，请重新生成视频后再试。",
  INTERNAL_SERVER_ERROR: "服务暂时异常，请稍后重试。",
};

function requestIdSuffix(requestId) {
  return requestId ? `（请求编号：${requestId}）` : "";
}

function fallbackMessage(status) {
  if (status === 401) return "登录已失效，请重新登录。";
  if (status === 403) return "您没有执行此操作的权限。";
  if (status === 404) return "请求的内容不存在或已被删除。";
  if (status === 408 || status === 504) return "请求超时，请检查网络后重试。";
  if (status === 429) return "操作过于频繁，请稍后重试。";
  if (status >= 500) return "服务暂时不可用，请稍后重试。";
  return "请求失败，请检查填写内容后重试。";
}

function readableMessage({ status, code, requestId }) {
  return `${ERROR_MESSAGES[code] || fallbackMessage(status)}${requestIdSuffix(requestId)}`;
}

export class ApiError extends Error {
  constructor(status, code, message, data, requestId = null) {
    super(readableMessage({ status, code, requestId }));
    this.name = "ApiError";
    this.status = status;
    this.code = code || "REQUEST_FAILED";
    this.data = data;
    this.requestId = requestId;
    this.serverMessage = message || null;
    this.retryable = status === 0 || status === 408 || status === 429 || status >= 500;
  }
}

async function readPayload(response) {
  const text = await response.text();
  if (!text) return {};
  try {
    const payload = JSON.parse(text);
    return payload && typeof payload === "object" ? payload : {};
  } catch {
    return {};
  }
}

export async function apiRequest(path, options = {}) {
  const token = readToken();
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw new ApiError(0, "NETWORK_UNAVAILABLE", "Network request failed", null);
  }
  const payload = await readPayload(response);
  const requestId = payload.request_id || response.headers.get("X-Request-ID") || null;

  if (response.status === 401) {
    clearToken();
    window.dispatchEvent(new CustomEvent("auth:expired"));
  }
  if (!response.ok) {
    throw new ApiError(response.status, payload.code, payload.message, payload.data, requestId);
  }
  return payload.data;
}
