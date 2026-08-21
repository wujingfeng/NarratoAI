import { apiRequest } from "./httpClient.js";

export function login(credentials) {
  return apiRequest("/auth/login", {
    method: "POST",
    body: JSON.stringify(credentials),
  });
}

export function sendRegistrationCode(email) {
  return apiRequest("/auth/register-code/send", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export function registerAccount({ email, password, verificationCode }) {
  return apiRequest("/auth/register", {
    method: "POST",
    body: JSON.stringify({
      email,
      password,
      verification_code: verificationCode,
    }),
  });
}

export function sendPasswordResetCode(email) {
  return apiRequest("/auth/password-code/send", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export function resetPassword({ email, password, verificationCode }) {
  return apiRequest("/auth/password/reset", {
    method: "POST",
    body: JSON.stringify({
      email,
      new_password: password,
      verification_code: verificationCode,
    }),
  });
}

export function logout() {
  return apiRequest("/auth/logout", { method: "POST" });
}

export function getCurrentUser() {
  return apiRequest("/users/me");
}
