import test from "node:test";
import assert from "node:assert/strict";
import { createDebouncedEditorSaver, createProject, requestProjectDeletion } from "./projectApi.js";

test("creation page narration type maps to the Business API product key", async () => {
  const calls = [];
  const request = async (...args) => {
    calls.push(args);
    return { id: "project-1", status: "draft" };
  };

  await createProject("narration", request);

  assert.deepEqual(calls, [["/projects", {
    method: "POST",
    body: JSON.stringify({ product: "short-drama-narration" }),
  }]]);
});

test("project deletion uses the existing per-project deletion request boundary", async () => {
  const calls = [];
  const request = async (...args) => {
    calls.push(args);
    return { job_id: "job-1", project_id: "project-1", status: "pending" };
  };

  const result = await requestProjectDeletion("project-1", request);

  assert.deepEqual(calls, [["/projects/project-1/deletion-requests", { method: "POST" }]]);
  assert.deepEqual(result, { job_id: "job-1", project_id: "project-1", status: "pending" });
});

test("debounced editor saver exposes flush failure without an internal unhandled rejection and can retry", async () => {
  const failure = new Error("save failed");
  const contents = [];
  let attempts = 0;
  const request = async (_path, options) => {
    attempts += 1;
    contents.push(JSON.parse(options.body).content);
    if (attempts === 1) throw failure;
    return { draft_id: "draft-1" };
  };
  const saver = createDebouncedEditorSaver("project-1", request, 0);

  const firstWaiter = saver({ version: 1, value: "first" });
  const handledFirstWaiter = firstWaiter.catch((error) => error);
  assert.equal(await handledFirstWaiter, failure);
  // The timer-triggered internal run is fire-and-forget; only the public waiter
  // is caught above. A rejected internal promise would surface here.
  await new Promise((resolve) => setTimeout(resolve, 0));
  await assert.rejects(saver.flush(), failure);

  const retryWaiter = saver({ version: 1, value: "retry" });
  await saver.flush();
  assert.deepEqual(await retryWaiter, { draft_id: "draft-1" });
  assert.equal(attempts, 2);
  assert.deepEqual(contents.map((content) => content.value), ["first", "retry"]);
});
