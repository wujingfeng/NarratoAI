// @vitest-environment node
import { describe, it, expect, beforeEach } from "vitest";
import { app } from "../../server/app";
import { memoryStore } from "../../server/store/memoryStore";

describe("POST /api/upload", () => {
  beforeEach(() => {
    memoryStore.clear();
  });

  it("缺少 projectId 返回 400", async () => {
    const form = new FormData();
    form.append("file", new File([new Uint8Array([1, 2, 3])], "test.mp4"));
    const res = await app.request("/api/upload", {
      method: "POST",
      body: form,
    });
    expect(res.status).toBe(400);
  });

  it("缺少 file 返回 400", async () => {
    const form = new FormData();
    form.append("projectId", "proj-1");
    const res = await app.request("/api/upload", {
      method: "POST",
      body: form,
    });
    expect(res.status).toBe(400);
  });

  it("完整上传返回 videoId / duration / thumbnail", async () => {
    const form = new FormData();
    form.append("projectId", "proj-upload-1");
    form.append("file", new File([new Uint8Array([1, 2, 3])], "episode-1.mp4"));
    const res = await app.request("/api/upload", {
      method: "POST",
      body: form,
    });
    expect(res.status).toBe(200);
    const json = (await res.json()) as {
      videoId: string;
      durationSec: number;
      thumbnailUrl: string;
    };
    expect(json.videoId).toBeTruthy();
    expect(json.durationSec).toBe(120);
    expect(json.thumbnailUrl).toMatch(/^\/media\/episode-\d\.mp4$/);
  });
});

describe("POST /api/analyze", () => {
  it("缺少 projectId 返回 400", async () => {
    const res = await app.request("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(res.status).toBe(400);
  });

  it("完整 analyze 返回 SSE 流", async () => {
    const res = await app.request("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ projectId: "proj-analyze-1" }),
    });
    expect(res.status).toBe(200);
    const text = await res.text();
    expect(text).toContain("event:");
    expect(text).toContain("result");
  });
});

describe("POST /api/script/*", () => {
  it("/generate 缺少 projectId 返回 400", async () => {
    const res = await app.request("/api/script/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ style: "悬疑", targetSec: 60 }),
    });
    expect(res.status).toBe(400);
  });

  it("/generate 返回 SSE 流含 result", async () => {
    const res = await app.request("/api/script/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        projectId: "proj-script-1",
        style: "悬疑",
        targetSec: 60,
      }),
    });
    expect(res.status).toBe(200);
    const text = await res.text();
    expect(text).toContain("result");
  }, 15000);

  it("/edit 缺少字段返回 400", async () => {
    const res = await app.request("/api/script/edit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ projectId: "p" }),
    });
    expect(res.status).toBe(400);
  });

  it("/regenerate 不带 hint 走默认分支", async () => {
    const res = await app.request("/api/script/regenerate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        projectId: "proj-reg-1",
        segmentId: "seg-1",
      }),
    });
    expect(res.status).toBe(200);
    const json = (await res.json()) as { segment: { text: string } };
    expect(json.segment.text).toContain("[重新生成]");
  });

  it("/regenerate 带 hint 走扩展分支", async () => {
    const res = await app.request("/api/script/regenerate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        projectId: "proj-reg-2",
        segmentId: "seg-2",
        hint: "更紧张",
      }),
    });
    expect(res.status).toBe(200);
    const json = (await res.json()) as { segment: { text: string } };
    expect(json.segment.text).toContain("更紧张");
  });

  it("/regenerate 缺少字段返回 400", async () => {
    const res = await app.request("/api/script/regenerate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ projectId: "p" }),
    });
    expect(res.status).toBe(400);
  });
});

describe("GET /api/voices", () => {
  it("language=en 仅返回 ronin", async () => {
    const res = await app.request("/api/voices?language=en");
    const json = (await res.json()) as Array<{ id: string }>;
    expect(json.length).toBe(1);
    expect(json[0]?.id).toBe("ronin");
  });

  it("无 language 返回完整列表", async () => {
    const res = await app.request("/api/voices");
    const json = (await res.json()) as Array<{ id: string }>;
    expect(json.length).toBeGreaterThan(1);
  });
});

describe("POST /api/render/start + GET /api/render/:id/status", () => {
  it("start 缺少 projectId 返回 400", async () => {
    const res = await app.request("/api/render/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(res.status).toBe(400);
  });

  it("start 成功返回 renderId 并写入 store", async () => {
    const res = await app.request("/api/render/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ projectId: "proj-render-1" }),
    });
    expect(res.status).toBe(200);
    const json = (await res.json()) as { renderId: string };
    expect(json.renderId).toBeTruthy();
    const stored = memoryStore.getRender(json.renderId);
    expect(stored).toBeDefined();
    expect(stored?.stage).toBe("tts");
  });

  it("status 找不到 render 返回 404", async () => {
    const res = await app.request("/api/render/unknown-id/status");
    expect(res.status).toBe(404);
  });
});

describe("POST /api/export/jianying", () => {
  it("返回 application/zip 流", async () => {
    const res = await app.request("/api/export/jianying", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ projectId: "proj-exp-1" }),
    });
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("application/zip");
    const buf = new Uint8Array(await res.arrayBuffer());
    // ZIP 头 magic "PK\x03\x04"
    expect(buf[0]).toBe(0x50);
    expect(buf[1]).toBe(0x4b);
  });
});

describe("GET /api/projects/:id", () => {
  it("找不到返回 404", async () => {
    const res = await app.request("/api/projects/nonexistent");
    expect(res.status).toBe(404);
  });

  it("找到时返回 project", async () => {
    const create = await app.request("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "demo" }),
    });
    const { id } = (await create.json()) as { id: string };
    const res = await app.request(`/api/projects/${id}`);
    expect(res.status).toBe(200);
    const json = (await res.json()) as { id: string; title: string };
    expect(json.id).toBe(id);
    expect(json.title).toBe("demo");
  });
});
