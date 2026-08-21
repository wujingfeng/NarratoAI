import assert from "node:assert/strict";
import test from "node:test";
import { mergeAdjacentSubtitleLines } from "./subtitleRegionBand.js";

test("相邻的两行字幕合并为同一个遮罩带", () => {
  const first = { x: .15, y: .67, width: .7, height: .018 };
  const second = { x: .19, y: .702, width: .62, height: .02 };
  assert.deepEqual(
    mergeAdjacentSubtitleLines([first, second], first),
    { ...first, y: .67, height: .052 },
  );
});

test("远离字幕行的画面文字不会扩大遮罩", () => {
  const subtitle = { x: .12, y: .72, width: .76, height: .02 };
  const sceneText = { x: .2, y: .51, width: .5, height: .04 };
  assert.deepEqual(mergeAdjacentSubtitleLines([subtitle, sceneText], subtitle), subtitle);
});
