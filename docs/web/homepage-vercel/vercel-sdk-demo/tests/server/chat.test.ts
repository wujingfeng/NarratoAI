import { describe, it, expect } from "vitest";
import { app } from "../../server/app";

describe("chat 路由", () => {
  it("无 API key 时返回 401", async () => {
    const oldKey = process.env["OPENAI_API_KEY"];
    delete process.env["OPENAI_API_KEY"];
    try {
      const res = await app.request("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: [{ role: "user", content: "hi" }] }),
      });
      expect(res.status).toBe(401);
      const json = (await res.json()) as { error: string };
      expect(json.error).toContain("OPENAI_API_KEY");
    } finally {
      if (oldKey) process.env["OPENAI_API_KEY"] = oldKey;
    }
  });
});
