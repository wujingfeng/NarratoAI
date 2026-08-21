import assert from "node:assert/strict";
import test from "node:test";
import { selectMostReliableSubtitleDetection } from "./subtitleRegionConsensus.js";

const detection = (y, confidence, height = 0.03) => ({
  region: { x: 0, y, width: 1, height },
  confidence,
});

test("出现次数最多的字幕位置优先于单帧高置信画面文字", () => {
  const result = selectMostReliableSubtitleDetection([
    detection(0.72, 0.62),
    detection(0.721, 0.65),
    detection(0.719, 0.6),
    detection(0.72, 0.64),
    detection(0.55, 0.95),
  ]);

  assert.equal(result.occurrenceCount, 4);
  assert.equal(result.candidateClusters, 2);
  assert.equal(result.region.y, 0.72);
  assert.equal(result.confidence, 0.6275);
});

test("出现次数相同时以平均置信度决定最终位置", () => {
  const result = selectMostReliableSubtitleDetection([
    detection(0.68, 0.6),
    detection(0.681, 0.62),
    detection(0.8, 0.72),
    detection(0.801, 0.74),
  ]);

  assert.equal(result.occurrenceCount, 2);
  assert.equal(result.region.y, 0.8005);
  assert.equal(result.confidence, 0.73);
});
