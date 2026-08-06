import { Hono } from "hono";
import { BlobReader, BlobWriter, ZipWriter } from "@zip.js/zip.js";
import { memoryStore } from "../store/memoryStore";

export const exportRoute = new Hono();

exportRoute.post("/jianying", async (c) => {
  const body = (await c.req.json().catch(() => ({}))) as {
    projectId?: string;
    renderId?: string;
  };
  const project = body.projectId ? memoryStore.getProject(body.projectId) : undefined;
  const render = body.renderId ? memoryStore.getRender(body.renderId) : undefined;

  const manifest = {
    project: project ?? null,
    render: render ?? null,
    exportedAt: new Date().toISOString(),
    note: "mock 导出，仅用于演示",
  };
  const draftContent = {
    timeline: [
      { type: "video", source: "episode-1.mp4", start: 0, end: 60 },
      { type: "narration", start: 0, end: 60, text: "[mock] 这里是解说文本" },
      {
        type: "voiceover",
        start: 0,
        end: 60,
        voiceId: project?.selectedVoiceId ?? "morgan",
      },
    ],
  };

  const writer = new ZipWriter(new BlobWriter("application/zip"));
  await writer.add(
    "manifest.json",
    new BlobReader(new Blob([JSON.stringify(manifest, null, 2)])),
  );
  await writer.add(
    "draft_content.json",
    new BlobReader(new Blob([JSON.stringify(draftContent, null, 2)])),
  );
  await writer.add(
    "README.txt",
    new BlobReader(
      new Blob(["这是 mock 剪映草稿，仅用于演示 vercel-sdk-demo。\n"]),
    ),
  );
  const blob = await writer.close();

  return new Response(blob.stream(), {
    headers: {
      "Content-Type": "application/zip",
      "Content-Disposition": `attachment; filename="narrato-mock-${Date.now()}.zip"`,
    },
  });
});
