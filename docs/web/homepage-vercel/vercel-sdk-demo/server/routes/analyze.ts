import { Hono } from "hono";
import { streamSSE } from "hono/streaming";
import { jobRunner } from "../store/jobRunner";
import sampleAnalysis from "../fixtures/sampleAnalysis.json" with { type: "json" };

export const analyzeRoute = new Hono();

analyzeRoute.post("/", async (c) => {
  const body = (await c.req.json()) as { projectId: string };
  if (!body.projectId) return c.json({ error: "projectId required" }, 400);

  return streamSSE(c, async (stream) => {
    const jobId = `analyze-${Date.now()}`;
    await jobRunner.run(
      jobId,
      "analyze_plot",
      { projectId: body.projectId },
      async (e) => {
        await stream.writeSSE({
          event: e.stage,
          data: JSON.stringify({ progress: e.progress }),
        });
      },
    );
    await stream.writeSSE({ event: "result", data: JSON.stringify(sampleAnalysis) });
    await stream.close();
  });
});
