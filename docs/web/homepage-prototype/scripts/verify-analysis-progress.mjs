import assert from "node:assert/strict";

const { calculateAnalysisProgress, ANALYSIS_STAGE_FILL_DURATION_MS } = await import("../src/features/projects/analysisProgress.js");

const start = 1_000;
const activeStageOne = { completedCount: 0, activeIndex: 0, failed: false, startedAt: start, totalStages: 4 };
assert.equal(calculateAnalysisProgress({ ...activeStageOne, now: start }), 0);
assert.equal(calculateAnalysisProgress({ ...activeStageOne, now: start + ANALYSIS_STAGE_FILL_DURATION_MS }), 24.99);

const stageTwo = { completedCount: 1, activeIndex: 1, failed: false, startedAt: start, totalStages: 4 };
assert.equal(calculateAnalysisProgress({ ...stageTwo, now: start + ANALYSIS_STAGE_FILL_DURATION_MS }), 49.99);

const stageThree = { completedCount: 2, activeIndex: 2, failed: false, startedAt: start, totalStages: 4 };
assert.equal(calculateAnalysisProgress({ ...stageThree, now: start + ANALYSIS_STAGE_FILL_DURATION_MS }), 74.99);

const stageFour = { completedCount: 3, activeIndex: 3, failed: false, startedAt: start, totalStages: 4 };
assert.equal(calculateAnalysisProgress({ ...stageFour, now: start + ANALYSIS_STAGE_FILL_DURATION_MS }), 99.99);
assert.equal(calculateAnalysisProgress({ ...stageFour, completedCount: 4, activeIndex: null, now: start }), 100);
assert.equal(calculateAnalysisProgress({ ...stageFour, failed: true, now: start + 5000 }), 75);

const scriptStage = { completedCount: 4, activeIndex: 4, failed: false, startedAt: start, totalStages: 5 };
assert.equal(calculateAnalysisProgress({ ...scriptStage, now: start }), 80);
assert.equal(calculateAnalysisProgress({ ...scriptStage, now: start + ANALYSIS_STAGE_FILL_DURATION_MS }), 99.99);
assert.equal(calculateAnalysisProgress({ ...scriptStage, completedCount: 5, activeIndex: null, now: start }), 100);

console.log("verify-analysis-progress: passed");
