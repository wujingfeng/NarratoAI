import { Hono } from "hono";
import { projectsRoute } from "./routes/projects";
import { uploadRoute } from "./routes/upload";
import { analyzeRoute } from "./routes/analyze";
import { scriptRoute } from "./routes/script";
import { voicesRoute } from "./routes/voices";
import { renderRoute } from "./routes/render";
import { exportRoute } from "./routes/export";
import { chatRoute } from "./routes/chat";

export const app = new Hono()
  .route("/api/projects", projectsRoute)
  .route("/api/upload", uploadRoute)
  .route("/api/analyze", analyzeRoute)
  .route("/api/script", scriptRoute)
  .route("/api/voices", voicesRoute)
  .route("/api/render", renderRoute)
  .route("/api/export", exportRoute)
  .route("/api/chat", chatRoute);
