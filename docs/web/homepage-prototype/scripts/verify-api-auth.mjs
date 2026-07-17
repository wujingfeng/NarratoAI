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

writeToken("session-token");
await assert.rejects(() => apiRequest("/users/me"), (error) => error instanceof ApiError && error.status === 401);

assert.equal(capturedRequest.options.headers.Authorization, "Bearer session-token");
assert.equal(readToken(), null, "401 必须清理本地 Token");
assert.equal(requestedRoute, "/login", "401 必须回到登录页");

console.log("verify-api-auth: passed");
