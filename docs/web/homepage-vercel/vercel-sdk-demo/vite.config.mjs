import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

function honoMockServer() {
  return {
    name: "hono-mock-server",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        if (!req.url?.startsWith("/api/")) return next();
        try {
          const { app } = await import("./server/app.ts");
          const url = `http://${req.headers.host ?? "localhost"}${req.url}`;
          const headers = new Headers();
          for (const [k, v] of Object.entries(req.headers)) {
            if (Array.isArray(v)) v.forEach((vv) => headers.append(k, vv));
            else if (v != null) headers.set(k, String(v));
          }
          const method = req.method ?? "GET";
          let body;
          if (method !== "GET" && method !== "HEAD") {
            const chunks = [];
            for await (const chunk of req) chunks.push(chunk);
            body = Buffer.concat(chunks);
            if (!headers.has("content-type"))
              headers.set("content-type", "application/octet-stream");
          }
          const webReq = new Request(url, {
            method,
            headers,
            ...(body !== undefined ? { body } : {}),
          });
          const webRes = await app.request(webReq);
          res.statusCode = webRes.status;
          webRes.headers.forEach((v, k) => res.setHeader(k, v));
          if (webRes.body) {
            const reader = webRes.body.getReader();
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              res.write(Buffer.from(value));
            }
          }
          res.end();
        } catch (err) {
          next(err);
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), honoMockServer()],
  server: { port: 5173, strictPort: true },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: [
        "src/**/*.{ts,tsx}",
        "server/**/*.ts",
      ],
      exclude: [
        "src/main.tsx",
        "src/**/*.d.ts",
        "tests/**",
        "**/*.test.{ts,tsx}",
      ],
    },
  },
});
