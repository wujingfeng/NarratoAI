import assert from "node:assert/strict";
import test from "node:test";
import { getAssistantThread, mergeAssistantMessages, mergeAssistantRunSnapshot, mergeAssistantRunStepSnapshot, normalizeAssistantMessages, streamAssistantChatMessage, streamAssistantRun } from "./assistantApi.js";

test("聊天消息始终按创建时间展示", () => {
  const messages = normalizeAssistantMessages([
    { id: "third", role: "assistant", content: "第三条", created_at: "2026-08-24T10:00:03Z" },
    { id: "first", role: "user", content: "第一条", created_at: "2026-08-24T10:00:01Z" },
    { id: "second", role: "assistant", content: "第二条", created_at: "2026-08-24T10:00:02Z" },
  ]);

  assert.deepEqual(messages.map((message) => message.id), ["first", "second", "third"]);
});

test("重试回复按新的创建时间追加且不复制用户输入", () => {
  const current = normalizeAssistantMessages([
    { id: "source", role: "user", content: "分析图片", created_at: "2026-08-24T10:00:01Z" },
    { id: "old-reply", role: "assistant", content: "旧回复", created_at: "2026-08-24T10:00:02Z" },
    { id: "later-source", role: "user", content: "后续输入", created_at: "2026-08-24T10:00:03Z" },
    { id: "later-reply", role: "assistant", content: "后续回复", created_at: "2026-08-24T10:00:04Z" },
  ]);
  const merged = mergeAssistantMessages(
    current,
    normalizeAssistantMessages([
      { id: "retry-reply", role: "assistant", content: "重试回复", created_at: "2026-08-24T10:00:05Z" },
    ]),
  );

  assert.deepEqual(merged.map((message) => message.id), [
    "source",
    "old-reply",
    "later-source",
    "later-reply",
    "retry-reply",
  ]);
  assert.equal(merged.filter((message) => message.role === "user").length, 2);
});


test("聊天记录请求默认加载最近 100 条，并携带向前翻页游标", async () => {
  let path = "";
  await getAssistantThread("thread-1", {}, async (value) => { path = value; return {}; });
  assert.equal(path, "/assistant/threads/thread-1?limit=100");
  await getAssistantThread("thread-1", { limit: 10, before: "message-10" }, async (value) => { path = value; return {}; });
  assert.equal(path, "/assistant/threads/thread-1?limit=10&before=message-10");
});


test("聊天流在 SSE 首帧前确认已创建，供输入区立即清空", async () => {
  const originalWindow = globalThis.window;
  const originalFetch = globalThis.fetch;
  const events = [];
  globalThis.window = { localStorage: { getItem: () => null } };
  globalThis.fetch = async () => new Response(
    'event: message_created\ndata: {"message":{},"assistant_message":{}}\n\nevent: completed\ndata: {"content":"完成"}\n\n',
    { status: 200, headers: { "Content-Type": "text/event-stream" } },
  );
  try {
    await streamAssistantChatMessage("thread-1", { mode: "chat", content: "你好" }, {
      onAccepted: () => events.push("accepted"),
      onMessageCreated: () => events.push("message_created"),
      onCompleted: () => events.push("completed"),
    });
    assert.deepEqual(events, ["accepted", "message_created", "completed"]);
  } finally {
    globalThis.window = originalWindow;
    globalThis.fetch = originalFetch;
  }
});


test("Agent Run 流式步骤以可恢复草稿合并，并由正式结果替换", () => {
  const run = { id: "run-1", status: "running", steps: [{ id: "plot_structure", status: "running", outputs: [] }] };
  const streamed = mergeAssistantRunStepSnapshot(run, {
    run_id: "run-1",
    step_id: "plot_structure",
    phase: "analysis",
    status_label: "正在理解剧情结构…",
    event_id: "core:2",
    content: "剧情结构草稿",
  });
  assert.equal(streamed.steps[0].stream_label, "正在理解剧情结构…");
  assert.deepEqual(streamed.steps[0].outputs, [
    { type: "markdown", content: "剧情结构草稿", draft: true },
  ]);

  const formal = mergeAssistantRunSnapshot(streamed, {
    id: "run-1",
    status: "running",
    steps: [{ id: "plot_structure", status: "completed", outputs: [{ type: "markdown", content: "正式剧情结构" }] }],
  });
  assert.deepEqual(formal.steps[0].outputs, [{ type: "markdown", content: "正式剧情结构" }]);
});


test("Agent Run SSE 分发运行快照、步骤增量与完成事件", async () => {
  const originalWindow = globalThis.window;
  const originalFetch = globalThis.fetch;
  const events = [];
  globalThis.window = { localStorage: { getItem: () => null } };
  globalThis.fetch = async () => new Response(
    'event: run_snapshot\ndata: {"run":{"id":"run-1"}}\n\nevent: step_snapshot\ndata: {"run_id":"run-1","step_id":"plot_structure"}\n\nevent: completed\ndata: {"run":{"id":"run-1","status":"completed"}}\n\n',
    { status: 200, headers: { "Content-Type": "text/event-stream" } },
  );
  try {
    await streamAssistantRun("run-1", {
      onRunSnapshot: () => events.push("run"),
      onStepSnapshot: () => events.push("step"),
      onCompleted: () => events.push("completed"),
    });
    assert.deepEqual(events, ["run", "step", "completed"]);
  } finally {
    globalThis.window = originalWindow;
    globalThis.fetch = originalFetch;
  }
});
