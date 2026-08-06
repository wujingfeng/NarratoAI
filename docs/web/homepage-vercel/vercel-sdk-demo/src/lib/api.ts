export async function postJSON<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return (await res.json()) as T;
}

export async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return (await res.json()) as T;
}

const KNOWN_EVENTS = [
  "queued",
  "uploading",
  "asr",
  "summarizing",
  "drafting",
  "refining",
  "tts",
  "subtitle",
  "mixing",
  "encoding",
  "done",
  "result",
];

/**
 * 订阅 SSE 流。返回 unsubscribe 函数。
 */
export function subscribeSSE(
  url: string,
  onEvent: (event: string, data: unknown) => void,
): () => void {
  const es = new EventSource(url);
  const handle = (e: MessageEvent) => {
    try {
      onEvent(e.type, JSON.parse(e.data));
    } catch {
      onEvent(e.type, e.data);
    }
  };
  for (const name of KNOWN_EVENTS) {
    es.addEventListener(name, handle as EventListener);
  }
  return () => {
    for (const name of KNOWN_EVENTS) es.removeEventListener(name, handle as EventListener);
    es.close();
  };
}
