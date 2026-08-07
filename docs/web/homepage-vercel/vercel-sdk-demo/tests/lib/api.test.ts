import { describe, it, expect, vi, afterEach } from "vitest";
import { getJSON, postJSON, subscribeSSE } from "../../src/lib/api";

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

describe("api.getJSON", () => {
  afterEach(() => vi.restoreAllMocks());

  it("成功时返回 JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ items: [1, 2, 3] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    const r = await getJSON<{ items: number[] }>("/api/test");
    expect(r.items).toEqual([1, 2, 3]);
  });

  it("失败时抛出错误", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 500 })));
    await expect(getJSON("/api/x")).rejects.toThrow(/500/);
  });
});

describe("api.subscribeSSE", () => {
  afterEach(() => vi.restoreAllMocks());

  it("注册监听器后 unsubscribe 关闭 EventSource", () => {
    const addSpy = vi.fn();
    const removeSpy = vi.fn();
    const closeSpy = vi.fn();
    class FakeES {
      addEventListener = addSpy;
      removeEventListener = removeSpy;
      close = closeSpy;
    }
    vi.stubGlobal("EventSource", FakeES);
    const unsub = subscribeSSE("/api/x", () => {});
    expect(addSpy).toHaveBeenCalled();
    unsub();
    expect(removeSpy).toHaveBeenCalled();
    expect(closeSpy).toHaveBeenCalled();
  });
});

