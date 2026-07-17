import { clearToken, readToken } from "../features/auth/authStorage.js";

const API_BASE_URL = import.meta.env?.VITE_NARRATO_API_BASE_URL || "/api/v1";

export class ApiError extends Error {
  constructor(status, code, message, data) {
    super(message || "请求失败");
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.data = data;
  }
}

export async function apiRequest(path, options = {}) {
  const token = readToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  const payload = await response.json();

  if (response.status === 401) {
    clearToken();
    window.dispatchEvent(new CustomEvent("auth:expired"));
  }
  if (!response.ok) {
    throw new ApiError(response.status, payload.code, payload.message, payload.data);
  }
  return payload.data;
}
