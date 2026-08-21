import test from "node:test";
import assert from "node:assert/strict";
import {
  deletableProjectIds,
  isProjectDeletable,
  reconcileProjectSelection,
  toggleAllDeletableProjects,
  toggleProjectSelection,
} from "./projectDeletion.js";

test("deletion eligibility follows the current project status or pre-analysis stage", () => {
  for (const status of ["completed", "failed"]) {
    assert.equal(isProjectDeletable({ status, current_stage: "export" }), true, status);
  }
  for (const current_stage of ["created", "settings"]) {
    assert.equal(isProjectDeletable({ status: "draft", current_stage }), true, current_stage);
    assert.equal(isProjectDeletable({ status: "ready", current_stage }), true, current_stage);
  }
  for (const status of ["deleting", "deleted"]) {
    assert.equal(isProjectDeletable({ status, current_stage: "created" }), false, status);
  }
  for (const [status, current_stage] of [["queued", "analysis"], ["analyzing", "analysis"], ["rendering", "generate"]]) {
    assert.equal(isProjectDeletable({ status, current_stage }), false, `${status}/${current_stage}`);
  }
});

test("current-page selection only includes deletable projects and removes stale choices", () => {
  const projects = [
    { id: "draft", status: "draft", current_stage: "settings" },
    { id: "complete", status: "completed", current_stage: "export" },
    { id: "running", status: "analyzing", current_stage: "analysis" },
  ];
  assert.deepEqual(deletableProjectIds(projects), ["draft", "complete"]);

  const selected = toggleAllDeletableProjects(new Set(), projects, true);
  assert.deepEqual([...selected], ["draft", "complete"]);
  assert.deepEqual([...toggleProjectSelection(selected, "draft", false)], ["complete"]);
  assert.deepEqual([...reconcileProjectSelection(new Set(["complete", "stale"]), projects)], ["complete"]);
  assert.deepEqual([...toggleAllDeletableProjects(selected, projects, false)], []);
});
