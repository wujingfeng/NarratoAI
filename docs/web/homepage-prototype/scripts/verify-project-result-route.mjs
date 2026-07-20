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

await test("loads the completed project result through the existing API contract", async () => {
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
    status: "completed",
    artifacts: [{ id: "art_video", kind: "video", cdn_url: "https://cdn.example.test/video.mp4" }],
  });
});

await test("registers one protected project result route", async () => {
  const app = await readFile(new URL("App.jsx", sourceRoot), "utf8");
  assert.match(app, /ProjectResultPage/);
  assert.match(
    app,
    /<Route\s+path="\/projects\/:projectId\/result"\s+element=\{<RequireAuth><ProjectResultPage\s*\/\><\/RequireAuth>\}\s*\/\>/,
  );
});

await test("result page loads from its route parameter and never exposes exports before a completed result", async () => {
  const page = await readFile(new URL("pages/ProjectResultPage.jsx", sourceRoot), "utf8");
  assert.match(page, /useParams/);
  assert.match(page, /getProjectResult\(projectId\)/);
  assert.match(page, /if \(!project\) return/);
  assert.match(page, /<ProjectResultDetails project=\{project\}/);
});

if (process.exitCode) process.exit(process.exitCode);
