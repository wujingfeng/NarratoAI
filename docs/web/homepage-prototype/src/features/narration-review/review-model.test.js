import test from "node:test";
import assert from "node:assert/strict";
import { createEditorDraft, readEditorDraft } from "../narration-editor/editor-data.js";
import {
  createReviewModel,
  deleteReviewRow,
  formatTimecode,
  insertReviewRow,
  materializeReviewModel,
  moveReviewRow,
  parseTimecode,
  updateReviewRow,
  validateReviewModel,
} from "./review-model.js";

const assets = [
  { id: "asset-a", filename: "a.mp4", cdnUrl: "https://cdn.test/a.mp4", durationSeconds: 30 },
  { id: "asset-b", filename: "b.mp4", cdnUrl: "https://cdn.test/b.mp4", durationSeconds: 20 },
];

const saved = {
  clips: [
    { id: "video-1", trackId: "video", start: 0, duration: 2, sourceStart: 5, assetId: "asset-a", assetUrl: assets[0].cdnUrl, regionId: "region-1" },
    { id: "script-1", trackId: "script", start: 0, duration: 2, text: "第一段", picture: "近景", originalSound: false, regionId: "region-1" },
    { id: "voice-1", trackId: "voice", start: 0, duration: 2, sourceStart: 0, assetId: "voice-a", assetUrl: "https://cdn.test/voice.mp3", regionId: "region-1" },
    { id: "video-2", trackId: "video", start: 2, duration: 3, sourceStart: 2, assetId: "asset-b", assetUrl: assets[1].cdnUrl, regionId: "region-2" },
    { id: "script-2", trackId: "script", start: 2, duration: 3, text: "第二段", picture: "远景", originalSound: true, regionId: "region-2" },
    { id: "bgm", trackId: "bgm", start: 0, duration: 5, sourceStart: 0, assetId: "music", assetUrl: "https://cdn.test/bgm.mp3", regionId: "bgm-music" },
  ],
  cues: [{ start: 0, end: 2, text: "第一段" }, { start: 2, end: 5, text: "第二段" }],
  settings: { voiceRole: "voice", volume: 90, rate: 1, subtitleStyle: "classic", videoRatio: "9:16", backgroundMusic: null },
};

test("parses and formats editable source timecodes", () => {
  assert.equal(formatTimecode(135.2), "00:02:15.200");
  assert.equal(parseTimecode("00:02:15.200"), 135.2);
  assert.equal(parseTimecode("02:15.2"), 135.2);
  assert.equal(parseTimecode("135.2"), 135.2);
  assert.equal(Number.isNaN(parseTimecode("00:72:00")), true);
});

test("reorders rows and synchronizes all related tracks, subtitles, and BGM", () => {
  const model = moveReviewRow(createReviewModel(saved), "region-2", -1);
  const result = materializeReviewModel(model);
  const regionTwo = result.clips.filter((clip) => clip.regionId === "region-2");
  const regionOne = result.clips.filter((clip) => clip.regionId === "region-1");
  assert.equal(regionTwo.every((clip) => clip.start === 0 && clip.duration === 3), true);
  assert.equal(regionOne.every((clip) => clip.start === 3 && clip.duration === 2), true);
  assert.deepEqual(result.cues, [
    { start: 0, end: 3, text: "第二段", regionId: "region-2" },
    { start: 3, end: 5, text: "第一段", regionId: "region-1" },
  ]);
  assert.equal(result.clips.find((clip) => clip.trackId === "bgm").duration, 5);
  assert.deepEqual(result.clips.filter((clip) => clip.trackId === "video").map((clip) => clip.id), ["video-2", "video-1"]);
});

test("preserves custom subtitles independently from narration while reordering rows", () => {
  const customized = {
    ...saved,
    cues: [
      { start: 0, end: 2, text: "第一段人工字幕" },
      { start: 2, end: 5, text: "第二段人工字幕" },
    ],
  };
  let model = moveReviewRow(createReviewModel(customized), "region-2", -1);
  model = updateReviewRow(model, "region-1", { text: "第一段修改后的解说" }, assets);

  const result = materializeReviewModel(model);

  assert.deepEqual(result.cues, [
    { start: 0, end: 3, text: "第二段人工字幕", regionId: "region-2" },
    { start: 3, end: 5, text: "第一段人工字幕", regionId: "region-1" },
  ]);
  assert.deepEqual(
    result.clips.filter((clip) => clip.trackId === "script").map((clip) => clip.text),
    ["第二段", "第一段修改后的解说"],
  );
});

test("uses cue region identity when a video moved without moving its old cue", () => {
  const independentlyMoved = structuredClone(saved);
  independentlyMoved.clips.find((clip) => clip.id === "video-1").start = 8;
  independentlyMoved.cues = [
    { start: 0, end: 2, text: "第一段稳定字幕", regionId: "region-1" },
    { start: 2, end: 5, text: "第二段稳定字幕", regionId: "region-2" },
  ];

  const result = materializeReviewModel(createReviewModel(independentlyMoved));

  assert.deepEqual(result.clips.filter((clip) => clip.trackId === "video").map((clip) => clip.id), ["video-2", "video-1"]);
  assert.deepEqual(result.cues, [
    { start: 0, end: 3, text: "第二段稳定字幕", regionId: "region-2" },
    { start: 3, end: 5, text: "第一段稳定字幕", regionId: "region-1" },
  ]);
});

test("never falls back to a mismatched or duplicate non-legacy cue region", () => {
  const mismatched = structuredClone(saved);
  mismatched.cues = [
    { start: 0, end: 2, text: "第一段有效字幕", regionId: "region-1" },
    { start: 2, end: 5, text: "脏 region 字幕", regionId: "unknown-region" },
    { start: 9, end: 12, text: "第二段旧版字幕" },
  ];
  const mismatchedResult = materializeReviewModel(createReviewModel(mismatched));
  assert.deepEqual(mismatchedResult.cues.map((cue) => cue.text), [
    "第一段有效字幕",
    "第二段旧版字幕",
  ]);

  const duplicate = structuredClone(saved);
  duplicate.cues = [
    { start: 0, end: 2, text: "第一段有效字幕", regionId: "region-1" },
    { start: 2, end: 5, text: "重复 region 字幕", regionId: "region-1" },
  ];
  const duplicateResult = materializeReviewModel(createReviewModel(duplicate));
  assert.deepEqual(duplicateResult.cues.map((cue) => cue.text), [
    "第一段有效字幕",
    "第二段",
  ]);
});

test("time and copy edits update paired clips and subtitle timing", () => {
  let model = createReviewModel(saved);
  model = updateReviewRow(model, "region-1", { sourceStart: 10, sourceEnd: 14, text: "修改后", picture: "新画面", originalSound: true }, assets);
  const result = materializeReviewModel(model);
  const video = result.clips.find((clip) => clip.id === "video-1");
  const script = result.clips.find((clip) => clip.id === "script-1");
  const next = result.clips.find((clip) => clip.id === "video-2");
  assert.deepEqual({ start: video.start, duration: video.duration, sourceStart: video.sourceStart }, { start: 0, duration: 4, sourceStart: 10 });
  assert.deepEqual({ text: script.text, picture: script.picture, originalSound: script.originalSound }, { text: "修改后", picture: "新画面", originalSound: true });
  assert.equal(next.start, 4);
  assert.deepEqual(result.cues[0], { start: 0, end: 4, text: "修改后", regionId: "region-1" });
  assert.equal(result.clips.find((clip) => clip.trackId === "bgm").duration, 7);
});

test("delete and insert keep valid paired rows without deleting unrelated BGM", () => {
  let model = deleteReviewRow(createReviewModel(saved), "region-1");
  let result = materializeReviewModel(model);
  assert.equal(result.clips.some((clip) => clip.regionId === "region-1"), false);
  assert.equal(result.clips.find((clip) => clip.id === "video-2").start, 0);
  assert.equal(result.clips.find((clip) => clip.trackId === "bgm").duration, 3);
  assert.deepEqual(result.cues, [{ start: 0, end: 3, text: "第二段", regionId: "region-2" }]);

  let counter = 0;
  model = insertReviewRow(model, "region-2", assets, { idFactory: () => `new-${++counter}` });
  result = materializeReviewModel(model);
  assert.equal(model.rows.length, 2);
  assert.equal(result.clips.filter((clip) => clip.trackId === "video").length, 2);
  assert.equal(result.clips.filter((clip) => clip.trackId === "script").length, 2);
  assert.equal(model.rows[1].assetId, "asset-b");
  assert.equal(model.rows[1].sourceStart, 5);
  assert.equal(model.rows[1].sourceEnd, 8);
  assert.deepEqual(result.cues[1], { start: 3, end: 6, text: "", regionId: model.rows[1].regionId });
  const validation = validateReviewModel(model, assets);
  assert.equal(validation.isValid, false);
  assert.equal(validation.safeToSave, true);
  assert.equal(validation.rowErrors[model.rows[1].id].text, "emptyScript");
});

test("asset changes reset and clamp the source interval", () => {
  const tinyAssets = [...assets, { id: "asset-c", filename: "c.mp4", cdnUrl: "https://cdn.test/c.mp4", durationSeconds: 1 }];
  const model = updateReviewRow(createReviewModel(saved), "region-1", { assetId: "asset-c" }, tinyAssets);
  assert.deepEqual({
    assetId: model.rows[0].assetId,
    assetUrl: model.rows[0].assetUrl,
    sourceStart: model.rows[0].sourceStart,
    sourceEnd: model.rows[0].sourceEnd,
  }, {
    assetId: "asset-c",
    assetUrl: "https://cdn.test/c.mp4",
    sourceStart: 0,
    sourceEnd: 1,
  });
});

test("editor serialization preserves review metadata and defaults old drafts", () => {
  const cues = saved.cues.map((cue, index) => ({ ...cue, regionId: `region-${index + 1}` }));
  const draft = createEditorDraft({
    clips: saved.clips,
    cues,
    ...saved.settings,
  });
  const script = draft.clips.find((clip) => clip.id === "script-2");
  assert.equal(script.picture, "远景");
  assert.equal(script.original_sound, true);
  assert.equal(draft.subtitles[1].region_id, "region-2");
  const hydrated = readEditorDraft(draft);
  assert.equal(hydrated.clips.find((clip) => clip.id === "script-2").originalSound, true);
  assert.equal(hydrated.cues[1].regionId, "region-2");

  const legacy = structuredClone(draft);
  legacy.clips.filter((clip) => clip.track_id === "script").forEach((clip) => {
    delete clip.picture;
    delete clip.original_sound;
  });
  const legacyScript = readEditorDraft(legacy).clips.find((clip) => clip.trackId === "script");
  assert.equal(legacyScript.picture, "");
  assert.equal(legacyScript.originalSound, false);
});

test("editor draft roundtrips alignment anchors and drops them after text edit", () => {
  const clips = saved.clips.map((clip) => clip.trackId === "script" ? {
    ...clip,
    text: "证据终于出现",
    eventId: "asset-a:event-1",
    visualAnchor: 2.4,
    narrationAnchorText: "证据",
    matchConfidence: 0.92,
    visualLead: 0.15,
    narrationStartOffset: 1.1,
  } : clip);
  const draft = createEditorDraft({ clips, cues: saved.cues, ...saved.settings });
  const hydrated = readEditorDraft(draft);
  const script = hydrated.clips.find((clip) => clip.trackId === "script");
  assert.equal(script.eventId, "asset-a:event-1");
  assert.equal(script.visualAnchor, 2.4);
  assert.equal(script.narrationAnchorText, "证据");
  assert.equal(script.matchConfidence, 0.92);
  assert.equal(script.visualLead, 0.15);
  assert.equal(script.narrationStartOffset, 1.1);

  script.text = "用户已经改写文案";
  const edited = createEditorDraft({
    clips: hydrated.clips,
    cues: hydrated.cues,
    ...hydrated.settings,
  });
  const editedScript = edited.clips.find((clip) => clip.track_id === "script");
  assert.equal("event_id" in editedScript, false);
  assert.equal("visual_anchor" in editedScript, false);
  assert.equal("narration_start_offset" in editedScript, false);
});
