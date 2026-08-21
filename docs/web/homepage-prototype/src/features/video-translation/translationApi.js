import { apiRequest } from "../../services/httpClient.js";

const base = (projectId) => `/projects/${projectId}/video-translation`;

export function normalizeOriginalSoundMode(value) {
  if (["voice_replacement", "keep", "preserve"].includes(value)) return "voice_replacement";
  if (["translated_voice_only", "mute"].includes(value)) return "translated_voice_only";
  return "translated_voice_only";
}

export function createTranslationProject(request = apiRequest) {
  return request("/projects", { method: "POST", body: JSON.stringify({ product: "video-translation" }) });
}
export function getTranslationConfig(request = apiRequest) { return request("/products/video-translation/config"); }
export function getTranslationSettings(projectId, request = apiRequest) { return request(`${base(projectId)}/settings`); }
export function estimateTranslationCost(projectId, originalSoundMode, request = apiRequest) {
  if (typeof originalSoundMode === "function") { request = originalSoundMode; originalSoundMode = undefined; }
  return request(`${base(projectId)}/cost-estimate`, {
    method: "POST",
    body: JSON.stringify(originalSoundMode ? { original_sound_mode: normalizeOriginalSoundMode(originalSoundMode) } : {}),
  });
}
export function saveTranslationSettings(projectId, settings, request = apiRequest) {
  return request(`${base(projectId)}/settings`, {
    method: "PUT",
    body: JSON.stringify({
      ...settings,
      original_sound_mode: normalizeOriginalSoundMode(settings?.original_sound_mode),
    }),
  });
}
export function startTranslation(projectId, settings, request = apiRequest) {
  return request(`${base(projectId)}/start`, { method: "POST" });
}
export function getTranslationStage(projectId, request = apiRequest) { return request(`${base(projectId)}/stage`); }
export function getTranslationSegments(projectId, request = apiRequest) { return request(`${base(projectId)}/segments`); }
export function saveTranslationSegment(projectId, segmentId, patch, request = apiRequest) {
  return request(`${base(projectId)}/segments/${segmentId}`, { method: "PATCH", body: JSON.stringify(patch) });
}
export function applyTranslationVoice(projectId, voiceId, { overwriteCustom = false } = {}, request = apiRequest) {
  return request(`${base(projectId)}/segments/voice`, { method: "POST", body: JSON.stringify({ voice_id: voiceId, overwrite_custom: overwriteCustom }) });
}
export function previewTranslationSegment(projectId, segmentId, request = apiRequest) {
  const idempotencyKey = globalThis.crypto?.randomUUID?.() || `preview-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return request(`${base(projectId)}/segments/${segmentId}/preview`, { method: "POST", headers: { "X-Idempotency-Key": idempotencyKey } });
}
export function reconcileTranslationPreview(projectId, segmentId, coreTaskId, request = apiRequest) {
  return request(`${base(projectId)}/segments/${segmentId}/preview/${coreTaskId}/reconcile`, { method: "POST" });
}
export async function waitForTranslationPreview(projectId, segmentId, initial, request = apiRequest, delay = 1200) {
  let result = initial;
  while (result?.status === "pending") {
    await new Promise((resolve) => globalThis.setTimeout(resolve, delay));
    result = await reconcileTranslationPreview(projectId, segmentId, result.core_task_id, request);
  }
  return result;
}
export function renderTranslation(projectId, request = apiRequest) { return request(`${base(projectId)}/render`, { method: "POST" }); }
export function getTranslationResult(projectId, request = apiRequest) { return request(`${base(projectId)}/result`); }

export function retryTranslationFromUpload(projectId, request = apiRequest) {
  return request(`${base(projectId)}/retry-draft`, { method: "POST" });
}

export function restartTranslationFromSubtitle(projectId, request = apiRequest) {
  return request(`${base(projectId)}/retry`, {
    method: "POST",
    body: JSON.stringify({ restart_from: "subtitle_translation" }),
  });
}

export function retryTranslationFromNode(projectId, nodeName, request = apiRequest) {
  return request(`${base(projectId)}/retry`, {
    method: "POST",
    body: JSON.stringify({ restart_from: nodeName }),
  });
}

export function exceedsPreviewLimit(text, language) {
  const value = String(text || "").trim();
  const cjk = ["ja", "ko"].includes(language) || /[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]/.test(value);
  return cjk ? Array.from(value.replace(/\s/g, "")).length > 100 : value.split(/\s+/).filter(Boolean).length > 100;
}
