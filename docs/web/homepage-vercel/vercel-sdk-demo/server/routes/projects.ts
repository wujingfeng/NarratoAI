import { Hono } from "hono";
import { memoryStore } from "../store/memoryStore";

export const projectsRoute = new Hono();

projectsRoute.post("/", async (c) => {
  const body = (await c.req.json().catch(() => ({}))) as { title?: string };
  const id = `proj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const project = memoryStore.setProject(id, { id, title: body.title ?? "未命名项目" });
  return c.json(project);
});

projectsRoute.get("/:id", (c) => {
  const id = c.req.param("id");
  const project = memoryStore.getProject(id);
  if (!project) return c.json({ error: "Project not found" }, 404);
  return c.json(project);
});
