import assert from "node:assert/strict";
import test from "node:test";
import { subtitleLineRegion } from "./subtitleRegionGeometry.js";

test("字幕框在检测行高的上下各增加 8% 容错空间", () => {
  assert.deepEqual(
    subtitleLineRegion({ y: 0.78, height: 0.026 }),
    { x: 0, y: 0.77792, width: 1, height: 0.03016 },
  );
});

test("极细的检测结果仍保留可操作的最小有效高度", () => {
  assert.deepEqual(
    subtitleLineRegion({ y: 0.995, height: 0.002 }),
    { x: 0, y: 0.99, width: 1, height: 0.01 },
  );
});
