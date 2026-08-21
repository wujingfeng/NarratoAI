import test from "node:test";
import assert from "node:assert/strict";
import { estimateTranslationCost, exceedsPreviewLimit, normalizeOriginalSoundMode } from "./translationApi.js";
test("试听文案按中日韩字符和其他语种单词限制 100", () => {
  assert.equal(exceedsPreviewLimit("中".repeat(100), "ja"), false);
  assert.equal(exceedsPreviewLimit("中".repeat(101), "ja"), true);
  assert.equal(exceedsPreviewLimit(Array(101).fill("word").join(" "), "en"), true);
});

test("原声音频旧值收敛到替换人声或仅译文配音", () => {
  assert.equal(normalizeOriginalSoundMode("keep"), "voice_replacement");
  assert.equal(normalizeOriginalSoundMode("preserve"), "voice_replacement");
  assert.equal(normalizeOriginalSoundMode("mute"), "translated_voice_only");
  assert.equal(normalizeOriginalSoundMode(undefined), "translated_voice_only");
});

test("报价请求把当前音频模式交给服务端计算", async () => {
  let observed;
  await estimateTranslationCost("project-1", "translated_voice_only", async (path, options) => {
    observed = { path, options };
    return {};
  });
  assert.equal(observed.path, "/projects/project-1/video-translation/cost-estimate");
  assert.equal(observed.options.method, "POST");
  assert.deepEqual(JSON.parse(observed.options.body), {
    original_sound_mode: "translated_voice_only",
  });
});
