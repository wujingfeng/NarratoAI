import { Hono } from "hono";
import { memoryStore } from "../store/memoryStore";

export const uploadRoute = new Hono();

uploadRoute.post("/", async (c) => {
  const body = (await c.req.parseBody()) as Record<string, string | File>;
  const projectId = typeof body["projectId"] === "string" ? body["projectId"] : "";
  const file = body["file"];
  if (!projectId) return c.json({ error: "projectId required" }, 400);
  if (!(file instanceof File)) return c.json({ error: "file required" }, 400);

  const videoId = `vid-${Date.now()}`;
  const durationSec = 120;
  const idx = ((Date.now() % 3) + 1) as 1 | 2 | 3;
  const thumbnailUrl = `/media/episode-${idx}.mp4`;

  memoryStore.setProject(projectId, {
    id: projectId,
    title: file.name.replace(/\.[^.]+$/, ""),
  });
  return c.json({ videoId, durationSec, thumbnailUrl });
});
