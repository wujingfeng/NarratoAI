import assert from "node:assert/strict";
import test from "node:test";
import { resolveSourceSubtitleRegion } from "./subtitleRegionSelection.js";

const fallback = { x: .08, y: .78, width: .84, height: .12 };
const detected = { x: 0, y: .7345, width: 1, height: .03125 };

test("设置页使用当前视频缓存的检测框，而不是通用默认框", () => {
  assert.deepEqual(
    resolveSourceSubtitleRegion(null, { asset_1: { status: "detected", region: detected } }, "asset_1", fallback),
    detected,
  );
});

test("已有服务端保存的用户框选优先于上传页缓存", () => {
  const saved = { x: 0, y: .81, width: 1, height: .04 };
  assert.deepEqual(
    resolveSourceSubtitleRegion(saved, { asset_1: { status: "detected", region: detected } }, "asset_1", fallback),
    saved,
  );
});

test("损坏的检测框不会覆盖默认框", () => {
  assert.deepEqual(
    resolveSourceSubtitleRegion(null, { asset_1: { status: "detected", region: { x: 0, y: .9, width: 1, height: .2 } } }, "asset_1", fallback),
    fallback,
  );
});
