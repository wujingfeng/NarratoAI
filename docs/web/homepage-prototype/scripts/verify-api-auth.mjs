import assert from "node:assert/strict";

const listeners = new Map();
const storage = new Map();
let requestedRoute = "/dashboard";
let capturedRequest;

globalThis.window = {
  addEventListener(type, listener) {
    listeners.set(type, listener);
  },
  dispatchEvent(event) {
    listeners.get(event.type)?.(event);
    return true;
  },
};
globalThis.CustomEvent = class CustomEvent {
  constructor(type, options = {}) {
    this.type = type;
    this.detail = options.detail;
  }
};
globalThis.localStorage = {
  getItem: (key) => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: (key) => storage.delete(key),
};
globalThis.window.localStorage = globalThis.localStorage;
globalThis.fetch = async (url, options) => {
  capturedRequest = { url, options };
  return new Response(JSON.stringify({ code: "AUTHENTICATION_REQUIRED", message: "Session expired", data: null }), {
    status: 401,
    headers: { "Content-Type": "application/json" },
  });
};

window.addEventListener("auth:expired", () => {
  requestedRoute = "/login";
});

const { readToken, writeToken } = await import("../src/features/auth/authStorage.js");
const { ApiError, apiRequest } = await import("../src/services/httpClient.js");
const { resetPassword, sendPasswordResetCode } = await import("../src/services/narratoApi.js");

writeToken("session-token");
await assert.rejects(() => apiRequest("/users/me"), (error) => error instanceof ApiError && error.status === 401);

assert.equal(capturedRequest.options.headers.Authorization, "Bearer session-token");
assert.equal(readToken(), null, "401 必须清理本地 Token");
assert.equal(requestedRoute, "/login", "401 必须回到登录页");

globalThis.fetch = async () => new Response(JSON.stringify({
  code: "MEDIA_PROBE_UNAVAILABLE",
  message: "Media validation is unavailable",
  data: null,
  request_id: "req_media_probe_123",
}), {
  status: 503,
  headers: { "Content-Type": "application/json" },
});

await assert.rejects(() => apiRequest("/projects/prj_1/uploads/complete"), (error) => (
  error instanceof ApiError
  && error.code === "MEDIA_PROBE_UNAVAILABLE"
  && error.requestId === "req_media_probe_123"
  && error.message === "媒体校验服务暂时不可用，请稍后重试。（请求编号：req_media_probe_123）"
));

globalThis.fetch = async () => { throw new TypeError("Failed to fetch"); };
await assert.rejects(() => apiRequest("/projects"), (error) => (
  error instanceof ApiError
  && error.code === "NETWORK_UNAVAILABLE"
  && error.message === "网络连接失败，请检查网络后重试。"
));

globalThis.fetch = async (url, options) => {
  capturedRequest = { url, options };
  return new Response(JSON.stringify({ code: "OK", message: "OK", data: { accepted: true } }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
};

await sendPasswordResetCode("user@example.com");
assert.equal(capturedRequest.url, "/api/v1/auth/password-code/send");
assert.deepEqual(JSON.parse(capturedRequest.options.body), { email: "user@example.com" });

await resetPassword({ email: "user@example.com", password: "Abcdef12", verificationCode: "123456" });
assert.equal(capturedRequest.url, "/api/v1/auth/password/reset");
assert.deepEqual(JSON.parse(capturedRequest.options.body), {
  email: "user@example.com",
  new_password: "Abcdef12",
  verification_code: "123456",
});

console.log("verify-api-auth: passed");
