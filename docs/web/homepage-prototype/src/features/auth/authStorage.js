const TOKEN_STORAGE_KEY = "narrato.api.token";

export function readToken() {
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function writeToken(token) {
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearToken() {
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}
