import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const sourceRoot = new URL("../src/", import.meta.url);

async function test(name, run) {
  try {
    await run();
    console.log(`PASS ${name}`);
  } catch (error) {
    console.error(`FAIL ${name}: ${error.message}`);
    process.exitCode = 1;
  }
}

await test("rejects files larger than 300 MiB before requesting OSS policy", async () => {
  const { uploadAsset, MAX_UPLOAD_SIZE_BYTES } = await import("../src/features/uploads/ossPostUpload.js");
  assert.equal(MAX_UPLOAD_SIZE_BYTES, 300 * 1024 * 1024);
  let calls = 0;
  await assert.rejects(
    () => uploadAsset("prj_1", { name: "too-large.mp4", size: 300 * 1024 * 1024 + 1, type: "video/mp4" }, "video", {
      request: async () => { calls += 1; },
    }),
    /300 MiB/,
  );
  assert.equal(calls, 0);
});

await test("posts to OSS then immediately completes the uploaded asset", async () => {
  const { uploadAsset } = await import("../src/features/uploads/ossPostUpload.js");
  const calls = [];
  const file = new File(["video"], "episode.mp4", { type: "video/mp4" });
  const result = await uploadAsset("prj_1", file, "video", {
    request: async (path, options) => {
      calls.push([path, options]);
      if (path.endsWith("/policy")) return { url: "https://oss.test/upload", key: "objects/episode.mp4", fields: { policy: "signed" } };
      return { id: "asset_1", status: "validating" };
    },
    postToOss: async (url, form) => {
      calls.push([url, form.get("key"), form.get("file").name]);
      return { ok: true };
    },
  });
  assert.equal(result.id, "asset_1");
  assert.deepEqual(calls.map(([path]) => path), [
    "/projects/prj_1/uploads/policy",
    "https://oss.test/upload",
    "/projects/prj_1/uploads/complete",
  ]);
  assert.deepEqual(JSON.parse(calls[2][1].body), {
    asset_type: "video", filename: "episode.mp4", size_bytes: file.size,
    content_type: "video/mp4", object_key: "objects/episode.mp4",
  });
});

await test("project start remains disabled until every asset is ready and uses API fee", async () => {
  const { canStartProject, estimateProjectCost, startProject } = await import("../src/features/projects/projectApi.js");
  assert.equal(canStartProject([{ status: "ready" }, { status: "validating" }]), false);
  assert.equal(canStartProject([{ status: "ready" }]), true);
  const calls = [];
  const request = async (path, options) => {
    calls.push([path, options]);
    return path.endsWith("cost-estimate") ? { credits: 40 } : { job_id: "job_1" };
  };
  assert.deepEqual(await estimateProjectCost("prj_1", request), { credits: 40 });
  assert.deepEqual(await startProject("prj_1", [{ status: "ready" }], request), { job_id: "job_1" });
  await assert.rejects(() => startProject("prj_1", [{ status: "invalid" }], request), /ready/);
  assert.deepEqual(calls.map(([path]) => path), ["/projects/prj_1/cost-estimate", "/projects/prj_1/start"]);
});

await test("SSE reader accepts split frames and forwards Last-Event-ID", async () => {
  const { createSseParser, readJobEvents } = await import("../src/features/jobs/readJobEvents.js");
  const events = [];
  const parse = createSseParser((event) => events.push(event));
  parse("id: 3\ndata: {\"status\":\"analyzing\"}\n");
  parse("\ndata: {\"status\":\"waiting_for_edit\"}\n\n");
  assert.deepEqual(events, [{ status: "analyzing" }, { status: "waiting_for_edit" }]);
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  globalThis.window = { localStorage: { getItem: () => "token_1" } };
  let request;
  globalThis.fetch = async (url, options) => {
    request = [url, options];
    return new Response("data: {\"status\":\"queued\"}\n\n");
  };
  try {
    await readJobEvents("job_1", "9", (event) => events.push(event));
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
  }
  assert.match(request[0], /\/jobs\/job_1\/events$/);
  assert.equal(request[1].headers["Last-Event-ID"], "9");
  assert.deepEqual(events.at(-1), { status: "queued" });
});

await test("editor save is debounced and render submission makes it read-only", async () => {
  const { createDebouncedEditorSaver, submitRender } = await import("../src/features/projects/projectApi.js");
  const saves = [];
  const save = createDebouncedEditorSaver("prj_1", async (path, options) => saves.push([path, options]), 5);
  save({ tracks: [1] });
  save({ tracks: [2] });
  await new Promise((resolve) => setTimeout(resolve, 15));
  assert.equal(saves.length, 1);
  assert.deepEqual(JSON.parse(saves[0][1].body), { content: { tracks: [2] } });
  let locked = false;
  await submitRender("prj_1", async () => ({ accepted: true }), () => { locked = true; });
  assert.equal(locked, true);
});

await test("Create page delegates uploads and blocks start while assets are not ready", async () => {
  const source = await readFile(new URL("pages/CreatePage.jsx", sourceRoot), "utf8");
  assert.match(source, /uploadAsset/);
  assert.match(source, /canStartProject/);
  assert.match(source, /estimateProjectCost/);
  assert.match(source, /startProject/);
});

if (process.exitCode) process.exit(process.exitCode);
