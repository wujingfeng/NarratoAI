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

await test("debounced editor saves can be cancelled before a render locks the draft", async () => {
  const { createDebouncedEditorSaver } = await import("../src/features/projects/projectApi.js");
  const saves = [];
  const save = createDebouncedEditorSaver("prj_1", async (path, options) => saves.push([path, options]), 5);
  assert.equal(typeof save.cancel, "function");
  save({ title: "待渲染草稿" });
  save.cancel();
  await new Promise((resolve) => setTimeout(resolve, 15));
  assert.deepEqual(saves, []);
});

await test("registers one protected lightweight project editor route", async () => {
  const app = await readFile(new URL("App.jsx", sourceRoot), "utf8");
  assert.match(app, /ProjectEditorPage/);
  assert.match(
    app,
    /<Route\s+path="\/projects\/:projectId\/editor"\s+element=\{<RequireAuth><ProjectEditorPage\s*\/><\/RequireAuth>\}\s*\/>/,
  );
});

await test("editor only saves content changes through its debounced saver and locks immediately while rendering", async () => {
  const page = await readFile(new URL("pages/ProjectEditorPage.jsx", sourceRoot), "utf8");
  assert.match(page, /createDebouncedEditorSaver/);
  assert.match(page, /submitRender/);
  assert.match(page, /saverRef\.current\(next\)/);
  assert.match(page, /saverRef\.current\?\.cancel\?\.\(\)/);
  assert.match(page, /setSubmitting\(true\)/);
  assert.match(page, /readOnly=\{readOnly \|\| submitting\}/);
  assert.doesNotMatch(page, /timeline|<video|<canvas/i);
});

if (process.exitCode) process.exit(process.exitCode);
