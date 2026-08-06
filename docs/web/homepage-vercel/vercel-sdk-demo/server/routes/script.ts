import { Hono } from "hono";
import { streamSSE } from "hono/streaming";
import { jobRunner } from "../store/jobRunner";
import sampleScript from "../fixtures/sampleScript.json" with { type: "json" };

export const scriptRoute = new Hono();

scriptRoute.post("/generate", async (c) => {
  const body = (await c.req.json()) as {
    projectId: string;
    style: string;
    targetSec: number;
  };
  if (!body.projectId) return c.json({ error: "projectId required" }, 400);

  return streamSSE(c, async (stream) => {
    const jobId = `script-${Date.now()}`;
    await jobRunner.run(
      jobId,
      "generate_script",
      { projectId: body.projectId, style: body.style, targetSec: body.targetSec },
      async (e) => {
        await stream.writeSSE({
          event: e.stage,
          data: JSON.stringify({ progress: e.progress }),
        });
      },
    );
    await stream.writeSSE({ event: "result", data: JSON.stringify(sampleScript) });
    await stream.close();
  });
});

scriptRoute.post("/edit", async (c) => {
  const body = (await c.req.json()) as {
    projectId: string;
    segmentId: string;
    newText: string;
  };
  if (!body.projectId || !body.segmentId)
    return c.json({ error: "missing fields" }, 400);
  return c.json({
    segment: { id: body.segmentId, start: 0, end: 12, text: body.newText, tone: "紧张" },
  });
});

scriptRoute.post("/regenerate", async (c) => {
  const body = (await c.req.json()) as {
    projectId: string;
    segmentId: string;
    hint?: string;
  };
  if (!body.projectId || !body.segmentId)
    return c.json({ error: "missing fields" }, 400);
  const newText = body.hint
    ? `[重新生成] 根据提示「${body.hint}」扩展后的版本：深夜，墓门开，林夏只觉背后发凉。`
    : "[重新生成] 重新写一版这一段。";
  return c.json({
    segment: { id: body.segmentId, start: 0, end: 12, text: newText, tone: "悬疑" },
  });
});
