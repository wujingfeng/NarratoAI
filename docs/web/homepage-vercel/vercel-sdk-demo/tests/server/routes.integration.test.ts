import { describe, it, expect } from "vitest";
import { app } from "../../server/app";

describe("REST 路由集成", () => {
  it("POST /api/projects 创建并返回", async () => {
    const res = await app.request("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "古墓系列" }),
    });
    expect(res.status).toBe(200);
    const json = (await res.json()) as { id: string; title: string };
    expect(json.title).toBe("古墓系列");
    expect(json.id).toBeTruthy();
  });

  it("GET /api/voices 返回 8 个候选", async () => {
    const res = await app.request("/api/voices");
    const json = (await res.json()) as Array<{ id: string }>;
    expect(json.length).toBe(8);
    expect(json[0]?.id).toBe("morgan");
  });

  it("POST /api/script/edit 修改段落", async () => {
    const create = await app.request("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "t" }),
    });
    const { id } = (await create.json()) as { id: string };
    const res = await app.request("/api/script/edit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        projectId: id,
        segmentId: "seg-1",
        newText: "新文案",
      }),
    });
    expect(res.status).toBe(200);
    const json = (await res.json()) as { segment: { text: string } };
    expect(json.segment.text).toBe("新文案");
  });
});
