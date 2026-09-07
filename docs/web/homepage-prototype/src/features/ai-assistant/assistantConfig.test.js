import assert from "node:assert/strict";
import test from "node:test";
import { assistantRunAnchorMessageId, assistantRunStatusLabel, attachmentRequirement, isAssistantRunActive, validateAssistantSubmission } from "./assistantConfig.js";

test("视频生成固定选项缺失时不可提交", () => {
  assert.match(validateAssistantSubmission({ mode: "video_generation", prompt: "海边广告片", attachments: [], generation: { generationMode: "text_to_video" } }), /完成视频生成模式/);
});

test("短剧解说和视频翻译要求已就绪视频", () => {
  assert.deepEqual(attachmentRequirement("short_drama_narration"), { min: 1, type: "video" });
  assert.match(validateAssistantSubmission({ mode: "video_translation", prompt: "翻译", targetLanguage: "en", attachments: [] }), /上传一个视频/);
});

test("视频翻译将用户目标语种作为固定前置条件", () => {
  assert.match(validateAssistantSubmission({ mode: "video_translation", prompt: "自然女声", targetLanguage: "", attachments: [{ status: "ready", kind: "video" }] }), /目标翻译语种/);
});

test("普通聊天仅接受可由聊天草稿处理的图片附件", async () => {
  const { CONVERSATION_MODES } = await import("./assistantConfig.js");
  assert.match(CONVERSATION_MODES.chat.accepted, /image\/png/);
  assert.doesNotMatch(CONVERSATION_MODES.chat.accepted, /pdf|doc/);
  assert.equal(CONVERSATION_MODES.chat.attachmentHint, "可选图片");
});

test("短剧工作流渲染排队状态持续轮询并展示准确文案", () => {
  const run = { mode: "short_drama_narration", status: "render_queued" };
  assert.equal(isAssistantRunActive(run.status), true);
  assert.equal(assistantRunStatusLabel(run, run.status), "等待视频渲染");
});

test("参数任务提交中的内部状态仍持续订阅和轮询", () => {
  assert.equal(isAssistantRunActive("submitting"), true);
  assert.equal(isAssistantRunActive("future_intermediate_state"), true);
  assert.equal(assistantRunStatusLabel({ mode: "short_drama_narration" }, "submitting"), "正在创建任务");
});

test("工作流终态停止轮询", () => {
  assert.equal(isAssistantRunActive("completed"), false);
  assert.equal(isAssistantRunActive("succeeded_with_partial_output"), false);
  assert.equal(isAssistantRunActive("failed"), false);
  assert.equal(isAssistantRunActive("cancelled"), false);
});

test("Agent 执行结果显示在首句 assistant 响应之后", () => {
  assert.equal(assistantRunAnchorMessageId({
    message_id: "user-message",
    assistant_message_id: "first-response",
  }), "first-response");
  assert.equal(assistantRunAnchorMessageId({ message_id: "legacy-user-message" }), "legacy-user-message");
});
