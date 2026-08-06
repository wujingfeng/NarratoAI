import { Hono } from "hono";
import { streamSSE } from "hono/streaming";
import { memoryStore } from "../store/memoryStore";
import { jobRunner } from "../store/jobRunner";

export const renderRoute = new Hono();

renderRoute.post("/start", async (c) => {
  const body = (await c.req.json()) as { projectId: string };
  if (!body.projectId) return c.json({ error: "projectId required" }, 400);
  const renderId = `render-${Date.now()}`;
  memoryStore.setRender(renderId, {
    renderId,
    projectId: body.projectId,
    stage: "tts",
    progress: 0,
  });
  return c.json({ renderId });
});

renderRoute.get("/:id/status", (c) => {
  const id = c.req.param("id");
  const existing = memoryStore.getRender(id);
  if (!existing) return c.json({ error: "render not found" }, 404);

  return streamSSE(c, async (stream) => {
    if (existing.stage === "done") {
      const url = existing.artifactUrl ?? `/api/export/jianying?renderId=${id}`;
      await stream.writeSSE({
        event: "done",
        data: JSON.stringify({ progress: 1, artifactUrl: url }),
      });
      await stream.close();
      return;
    }

    await jobRunner.run(
      id,
      "render",
      { projectId: existing.projectId },
      async (e) => {
        memoryStore.setRender(id, {
          projectId: existing.projectId,
          stage: e.stage,
          progress: e.progress,
        });
        if (e.stage === "done") {
          const artifactUrl = `/api/export/jianying?renderId=${id}`;
          memoryStore.setRender(id, {
            projectId: existing.projectId,
            stage: "done",
            progress: 1,
            artifactUrl,
          });
        }
        const payload =
          e.stage === "done"
            ? { progress: 1, artifactUrl: `/api/export/jianying?renderId=${id}` }
            : { progress: e.progress };
        await stream.writeSSE({ event: e.stage, data: JSON.stringify(payload) });
      },
    );
    await stream.close();
  });
});
