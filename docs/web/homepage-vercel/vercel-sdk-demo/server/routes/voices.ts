import { Hono } from "hono";
import voiceList from "../fixtures/voiceList.json" with { type: "json" };

export const voicesRoute = new Hono();

voicesRoute.get("/", (c) => {
  const language = c.req.query("language");
  if (language === "en") {
    return c.json(voiceList.filter((v) => v.id === "ronin"));
  }
  return c.json(voiceList);
});
