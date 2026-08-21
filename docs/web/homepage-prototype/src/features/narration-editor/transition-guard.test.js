import test from "node:test";
import assert from "node:assert/strict";
import { createTransitionGuard } from "./transition-guard.js";

test("keeps save, mode switch, and generation mutually exclusive across an async wait", async () => {
  const changes = [];
  const guard = createTransitionGuard((active) => changes.push(active));
  let release;
  const delayedSave = new Promise((resolve) => { release = resolve; });

  assert.equal(guard.begin("save"), true);
  assert.equal(guard.busy, true);
  assert.equal(guard.begin("switch"), false);
  assert.equal(guard.begin("generate"), false);

  release();
  await delayedSave;
  assert.equal(guard.end("save"), true);
  assert.equal(guard.begin("generate"), true);
  assert.equal(guard.end("switch"), false);
  assert.equal(guard.end("generate"), true);
  assert.deepEqual(changes, ["save", "", "generate", ""]);
});
