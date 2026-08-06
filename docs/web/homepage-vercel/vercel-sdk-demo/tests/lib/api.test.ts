import { describe, it, expect, vi, afterEach } from "vitest";
import { postJSON } from "../../src/lib/api";

describe("api.postJSON", () => {
  afterEach(() => vi.restoreAllMocks());

  it("成功时返回 JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    const r = await postJSON<{ ok: boolean }>("/api/test", {});
    expect(r.ok).toBe(true);
  });

  it("失败时抛出带状态码的错误", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("bad", { status: 400 })));
    await expect(postJSON("/api/test", {})).rejects.toThrow(/400/);
  });
});
