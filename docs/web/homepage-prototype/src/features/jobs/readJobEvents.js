import { readToken } from "../auth/authStorage.js";

const API_BASE_URL = import.meta.env?.VITE_NARRATO_API_BASE_URL || "/api/v1";

/** 将可能拆分在任意网络 chunk 中的 SSE data 帧逐个解析。 */
export function createSseParser(onEvent) {
  let buffer = "";
  return (chunk) => {
    buffer += chunk.replaceAll("\r\n", "\n");
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const data = frame.split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (data) onEvent(JSON.parse(data));
    }
  };
}

/** 使用 fetch 而非 EventSource，以便发送 Bearer token 和断线续接 event id。 */
export async function readJobEvents(jobId, lastEventId, onEvent, signal) {
  const token = readToken();
  const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/events`, {
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}) },
    signal,
  });
  if (!response.ok || !response.body) throw new Error(`SSE ${response.status}`);
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const parse = createSseParser(onEvent);
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    parse(value);
  }
}
