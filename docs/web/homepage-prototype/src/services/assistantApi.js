import { API_BASE_URL, ApiError, apiRequest } from "./httpClient.js";
import { readToken } from "../features/auth/authStorage.js";

const ROOT = "/assistant";

export function listAssistantThreads(request = apiRequest) {
  return request(`${ROOT}/threads`);
}

export function listAssistantChatModels(request = apiRequest) {
  return request(`${ROOT}/chat-models`);
}

export function createAssistantThread(payload = {}, request = apiRequest) {
  return request(`${ROOT}/threads`, { method: "POST", body: JSON.stringify(payload) });
}

export function updateAssistantThreadTitle(threadId, title, request = apiRequest) {
  return request(`${ROOT}/threads/${encodeURIComponent(threadId)}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

export function deleteAssistantThread(threadId, request = apiRequest) {
  return request(`${ROOT}/threads/${encodeURIComponent(threadId)}`, {
    method: "DELETE",
  });
}

// Load a complete recent Agent timeline on first entry. The API still caps this
// page at 100 and returns a cursor for older conversation history.
export function getAssistantThread(threadId, { limit = 100, before } = {}, request = apiRequest) {
  const query = new URLSearchParams({ limit: String(limit) });
  if (before) query.set("before", before);
  return request(`${ROOT}/threads/${encodeURIComponent(threadId)}?${query.toString()}`);
}

export function createAssistantDraft(threadId, mode, request = apiRequest) {
  return request(`${ROOT}/threads/${encodeURIComponent(threadId)}/drafts`, {
    method: "POST",
    body: JSON.stringify({ mode }),
  });
}

export function sendAssistantMessage(threadId, payload, request = apiRequest) {
  return request(`${ROOT}/threads/${encodeURIComponent(threadId)}/messages`, {
    method: "POST",
    headers: { "X-Idempotency-Key": globalThis.crypto?.randomUUID?.() || `assistant-${Date.now()}` },
    body: JSON.stringify(payload),
  });
}

export async function streamAssistantChatMessage(threadId, payload, { signal, onAccepted, onMessageCreated, onDelta, onCompleted } = {}) {
  const token = readToken();
  const response = await fetch(`${API_BASE_URL}${ROOT}/threads/${encodeURIComponent(threadId)}/messages/stream`, {
    method: "POST",
    signal,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      "X-Idempotency-Key": globalThis.crypto?.randomUUID?.() || `assistant-stream-${Date.now()}`,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorPayload = await response.json().catch(() => ({}));
    throw new ApiError(response.status, errorPayload.code, errorPayload.message, errorPayload.data, errorPayload.request_id || null);
  }
  // A 200 SSE response is opened only after the server persisted the user turn,
  // assistant placeholder, and underlying LLM task. Do not wait for the first
  // stream frame before allowing the composer to clear its accepted input.
  onAccepted?.();
  return consumeAssistantStream(response, { onMessageCreated, onDelta, onCompleted });
}

export async function resumeAssistantChatStream(threadId, assistantMessageId, { signal, onMessageCreated, onDelta, onCompleted } = {}) {
  const token = readToken();
  const response = await fetch(`${API_BASE_URL}${ROOT}/threads/${encodeURIComponent(threadId)}/messages/${encodeURIComponent(assistantMessageId)}/stream`, {
    method: "GET",
    signal,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    const errorPayload = await response.json().catch(() => ({}));
    throw new ApiError(response.status, errorPayload.code, errorPayload.message, errorPayload.data, errorPayload.request_id || null);
  }
  return consumeAssistantStream(response, { onMessageCreated, onDelta, onCompleted });
}

export async function streamAssistantChatRetry(threadId, assistantMessageId, { signal, onMessageCreated, onDelta, onCompleted } = {}) {
  const token = readToken();
  const response = await fetch(`${API_BASE_URL}${ROOT}/threads/${encodeURIComponent(threadId)}/messages/${encodeURIComponent(assistantMessageId)}/retry/stream`, {
    method: "POST",
    signal,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      "X-Idempotency-Key": globalThis.crypto?.randomUUID?.() || `assistant-retry-${Date.now()}`,
    },
  });
  if (!response.ok) {
    const errorPayload = await response.json().catch(() => ({}));
    throw new ApiError(response.status, errorPayload.code, errorPayload.message, errorPayload.data, errorPayload.request_id || null);
  }
  return consumeAssistantStream(response, { onMessageCreated, onDelta, onCompleted });
}

async function consumeAssistantStream(response, { onMessageCreated, onDelta, onCompleted }) {
  if (!response.body) throw new Error("Assistant stream is unavailable");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;
  const handleEvent = (frame) => {
    const lines = frame.replaceAll("\r", "").split("\n");
    const event = lines.find((line) => line.startsWith("event:"))?.slice(6).trim() || "message";
    const serialized = lines.filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trim()).join("\n");
    if (!serialized) return;
    const data = JSON.parse(serialized);
    if (event === "message_created") onMessageCreated?.(data);
    else if (event === "delta") onDelta?.(data);
    else if (event === "completed") { completed = true; onCompleted?.(data); }
    else if (event === "error") throw new Error(data.message || "Assistant stream failed");
  };

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    buffer = buffer.replaceAll("\r\n", "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      handleEvent(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }
  if (buffer.trim()) handleEvent(buffer);
  if (!completed) throw new Error("Assistant stream ended before completion");
}

export function getAssistantRuns(threadId, request = apiRequest) {
  return request(`${ROOT}/threads/${encodeURIComponent(threadId)}/runs`);
}

export function getAssistantRun(runId, request = apiRequest) {
  return request(`${ROOT}/runs/${encodeURIComponent(runId)}`);
}

export async function streamAssistantRun(runId, { signal, onRunSnapshot, onStepSnapshot, onCompleted } = {}) {
  const token = readToken();
  const response = await fetch(`${API_BASE_URL}${ROOT}/runs/${encodeURIComponent(runId)}/stream`, {
    method: "GET",
    signal,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    const errorPayload = await response.json().catch(() => ({}));
    throw new ApiError(response.status, errorPayload.code, errorPayload.message, errorPayload.data, errorPayload.request_id || null);
  }
  if (!response.body) throw new Error("Agent Run stream is unavailable");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;
  const handleEvent = (frame) => {
    const lines = frame.replaceAll("\r", "").split("\n");
    const event = lines.find((line) => line.startsWith("event:"))?.slice(6).trim() || "message";
    const serialized = lines.filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trim()).join("\n");
    if (!serialized) return;
    const data = JSON.parse(serialized);
    if (event === "run_snapshot") onRunSnapshot?.(data.run);
    else if (event === "step_snapshot") onStepSnapshot?.(data);
    else if (event === "completed") { completed = true; onCompleted?.(data.run); }
    else if (event === "error") throw new Error(data.message || "Agent Run stream failed");
  };
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    buffer = buffer.replaceAll("\r\n", "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      handleEvent(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }
  if (buffer.trim()) handleEvent(buffer);
  if (!completed) throw new Error("Agent Run stream ended before completion");
}

export function mergeAssistantRunStepSnapshot(run, snapshot) {
  if (!run || !snapshot || String(run.id || run.run_id || "") !== String(snapshot.run_id || "")) return run;
  const steps = Array.isArray(run.steps) ? run.steps.map((step) => ({ ...step, outputs: Array.isArray(step.outputs) ? [...step.outputs] : [] })) : [];
  const index = steps.findIndex((step) => step.id === snapshot.step_id);
  if (index < 0) return run;
  const step = steps[index];
  const content = typeof snapshot.content === "string" ? snapshot.content : "";
  const formalOutputs = step.outputs.filter((output) => !output?.draft);
  steps[index] = {
    ...step,
    status: snapshot.completed ? step.status : "running",
    stream_phase: snapshot.phase || null,
    stream_label: snapshot.status_label || null,
    stream_event_id: snapshot.event_id || null,
    outputs: content ? [...formalOutputs, { type: "markdown", content, draft: true }] : formalOutputs,
  };
  return { ...run, steps };
}

export function mergeAssistantRunSnapshot(current, incoming) {
  if (!current || !incoming) return incoming || current;
  const currentSteps = new Map((current.steps || []).map((step) => [step.id, step]));
  const steps = (incoming.steps || []).map((step) => {
    if (Array.isArray(step.outputs) && step.outputs.length) return step;
    const previous = currentSteps.get(step.id);
    const draftOutputs = (previous?.outputs || []).filter((output) => output?.draft);
    const hasStreamState = draftOutputs.length || previous?.stream_label;
    return hasStreamState && ["queued", "running", "processing", "analyzing"].includes(String(step.status || "").toLowerCase())
      ? { ...step, outputs: draftOutputs, stream_phase: previous.stream_phase, stream_label: previous.stream_label, stream_event_id: previous.stream_event_id }
      : step;
  });
  return { ...current, ...incoming, steps };
}

export function normalizeAssistantThreadList(payload) {
  return Array.isArray(payload) ? payload : payload?.items || payload?.threads || [];
}

export function normalizeAssistantMessages(payload) {
  const source = Array.isArray(payload) ? payload : payload?.messages || payload?.items || [];
  return source
    .filter(Boolean)
    .map((message, index) => ({
      ...message,
      id: String(message.id || message.message_id || `message-${index}`),
      role: message.role === "assistant" ? "assistant" : "user",
      content: Array.isArray(message.content) ? message.content : [{ type: "text", text: String(message.content || message.text || "") }],
    }))
    .map((message, index) => ({ message, index, createdAt: Date.parse(message.created_at || "") }))
    .sort((left, right) => {
      const leftTime = Number.isFinite(left.createdAt) ? left.createdAt : Number.MAX_SAFE_INTEGER;
      const rightTime = Number.isFinite(right.createdAt) ? right.createdAt : Number.MAX_SAFE_INTEGER;
      return leftTime - rightTime || left.index - right.index;
    })
    .map(({ message }) => message);
}

export function mergeAssistantMessages(current, incoming) {
  const next = [...current];
  const positions = new Map(next.map((message, index) => [message.id, index]));
  incoming.forEach((message) => {
    const position = positions.get(message.id);
    if (position === undefined) {
      positions.set(message.id, next.length);
      next.push(message);
    } else {
      next[position] = message;
    }
  });
  return normalizeAssistantMessages(next);
}

export function normalizeAssistantRuns(payload) {
  return Array.isArray(payload) ? payload : payload?.items || payload?.runs || [];
}
