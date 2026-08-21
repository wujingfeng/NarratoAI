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

await test("loads only the Artifact payload returned by the completion-gated API", async () => {
  const { getProjectResult } = await import("../src/features/projects/projectApi.js");
  const calls = [];
  const result = await getProjectResult("prj_completed", async (path, options) => {
    calls.push([path, options]);
    return {
      project_id: "prj_completed",
      artifacts: [{ id: "art_video", kind: "video", cdn_url: "https://cdn.example.test/video.mp4" }],
    };
  });

  assert.deepEqual(calls, [["/projects/prj_completed/result", undefined]]);
  assert.deepEqual(result, {
    id: "prj_completed",
    artifacts: [{ id: "art_video", kind: "video", cdn_url: "https://cdn.example.test/video.mp4" }],
  });
  assert.equal("status" in result, false, "the browser must not invent a completed status");
});

await test("registers one protected history result route", async () => {
  const app = await readFile(new URL("App.jsx", sourceRoot), "utf8");
  assert.match(app, /ProjectResultPage/);
  assert.match(
    app,
    /<Route\s+path="\/projects\/:projectId\/result"\s+element=\{<RequireAuth><ProjectResultPage\s*\/><\/RequireAuth>\}\s*\/>/,
  );
  assert.doesNotMatch(app, /overlord\/result/, "fixed demo result routes must not survive");
});

await test("history and automatic completion use the same real result implementation", async () => {
  const wrapper = await readFile(new URL("pages/ProjectResultPage.jsx", sourceRoot), "utf8");
  const page = await readFile(new URL("pages/NarrationStagePage.jsx", sourceRoot), "utf8");
  assert.match(wrapper, /NarrationStagePage/);
  assert.match(wrapper, /stage="export"/);
  assert.match(page, /useParams/);
  assert.match(page, /routeParams\.projectId/);
  assert.match(page, /getProjectStage\(projectId\)/);
  assert.match(page, /getProjectResult\(projectId\)/);
  assert.match(page, /artifact\.cdn_url/);
});

if (process.exitCode) process.exit(process.exitCode);
