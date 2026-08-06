import { describe, it, expect } from "vitest";
import { jobRunner } from "../../server/store/jobRunner";

describe("jobRunner", () => {
  // render 场景含 5 阶段约 10s；其他场景更短。
  const LONG_TIMEOUT = 30_000;

  it(
    "推完所有阶段后完成",
    async () => {
      const events: Array<{ stage: string; progress: number }> = [];
      const result = await jobRunner.run(
        "render-test-1",
        "render",
        { projectId: "p1" },
        (e) => events.push({ stage: e.stage, progress: e.progress }),
      );
      expect(events.length).toBeGreaterThanOrEqual(4);
      expect(events.at(-1)?.stage).toBe("done");
      expect(events.at(-1)?.progress).toBe(1);
      expect(result.jobId).toBe("render-test-1");
    },
    LONG_TIMEOUT,
  );

  it(
    "订阅 SSE 期间能收到全部进度",
    async () => {
      const received: string[] = [];
      const unsub = jobRunner.subscribe("render-test-2", (e) => received.push(e.stage));
      await jobRunner.run("render-test-2", "render", { projectId: "p1" });
      unsub();
      expect(received.at(-1)).toBe("done");
    },
    LONG_TIMEOUT,
  );

  it("支持取消", async () => {
    const controller = new AbortController();
    const promise = jobRunner.run("render-test-3", "render", { projectId: "p1" }, undefined, {
      signal: controller.signal,
    });
    setTimeout(() => controller.abort(), 100);
    await expect(promise).rejects.toThrow();
  });
});
