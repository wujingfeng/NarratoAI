import { Hono } from "hono";
import { streamText } from "ai";
import { createOpenAICompatible } from "@ai-sdk/openai-compatible";
import { SERVER_SYSTEM_PROMPT } from "../llm/agentPrompt";

export const chatRoute = new Hono();

chatRoute.post("/", async (c) => {
  const apiKey = process.env["OPENAI_API_KEY"];
  if (!apiKey || apiKey === "sk-your-key-here") {
    return c.json(
      { error: "OPENAI_API_KEY 未配置，请在 .env 中设置后再启动" },
      401,
    );
  }

  const body = (await c.req.json()) as {
    messages: Array<{ role: string; content: string }>;
    projectId?: string;
  };

  const baseURL = process.env["OPENAI_BASE_URL"] ?? "https://api.openai.com/v1";
  const modelName = process.env["OPENAI_MODEL"] ?? "gpt-4o-mini";

  const openai = createOpenAICompatible({
    name: "custom",
    baseURL,
    headers: { Authorization: `Bearer ${apiKey}` },
  });

  try {
    const result = streamText({
      model: openai(modelName),
      system: SERVER_SYSTEM_PROMPT,
      messages: body.messages as Array<{
        role: "user" | "assistant" | "system";
        content: string;
      }>,
    });
    return result.toDataStreamResponse();
  } catch (err) {
    const msg = err instanceof Error ? err.message : "LLM 调用失败";
    return c.json({ error: msg }, 500);
  }
});
