import { describe, it, expect, beforeEach } from "vitest";
import { memoryStore } from "../../server/store/memoryStore";

describe("memoryStore", () => {
  beforeEach(() => memoryStore.clear());

  it("set 后能 get 出来", () => {
    memoryStore.setProject("p1", { id: "p1", title: "测试项目", style: "悬疑" });
    expect(memoryStore.getProject("p1")?.title).toBe("测试项目");
  });

  it("appendMessage 按顺序累加", () => {
    memoryStore.appendMessage("p1", { role: "user", content: "你好" });
    memoryStore.appendMessage("p1", {
      role: "assistant",
      content: "你好！有什么可以帮你？",
    });
    const msgs = memoryStore.getMessages("p1");
    expect(msgs).toHaveLength(2);
    expect(msgs[0]?.content).toBe("你好");
    expect(msgs[1]?.content).toBe("你好！有什么可以帮你？");
  });

  it("不存在的项目返回 undefined", () => {
    expect(memoryStore.getProject("nonexistent")).toBeUndefined();
  });

  it("setProject 不传 title 沿用已有 title", () => {
    memoryStore.setProject("p1", { id: "p1", title: "原始" });
    memoryStore.setProject("p1", { id: "p1", style: "悬疑" });
    const p = memoryStore.getProject("p1");
    expect(p?.title).toBe("原始");
    expect(p?.style).toBe("悬疑");
  });

  it("setProject 更新字段不会丢旧字段", () => {
    memoryStore.setProject("p1", {
      id: "p1",
      title: "x",
      style: "悬疑",
      targetDurationSec: 60,
      audience: "通用",
      selectedVoiceId: "morgan",
    });
    memoryStore.setProject("p1", { id: "p1", title: "y" });
    const p = memoryStore.getProject("p1");
    expect(p?.title).toBe("y");
    expect(p?.style).toBe("悬疑");
    expect(p?.targetDurationSec).toBe(60);
    expect(p?.audience).toBe("通用");
    expect(p?.selectedVoiceId).toBe("morgan");
  });

  it("setRender 创建新条目", () => {
    const r = memoryStore.setRender("r1", { projectId: "p1", stage: "tts", progress: 0 });
    expect(r.renderId).toBe("r1");
    expect(memoryStore.getRender("r1")?.stage).toBe("tts");
  });

  it("setRender 合并已有 finishedAt / artifactUrl", () => {
    memoryStore.setRender("r1", {
      projectId: "p1",
      stage: "done",
      progress: 1,
      finishedAt: 100,
      artifactUrl: "/api/x",
    });
    memoryStore.setRender("r1", { projectId: "p1", stage: "encoding", progress: 0.95 });
    const r = memoryStore.getRender("r1");
    expect(r?.stage).toBe("encoding");
    expect(r?.finishedAt).toBe(100);
    expect(r?.artifactUrl).toBe("/api/x");
  });

  it("getRender 不存在返回 undefined", () => {
    expect(memoryStore.getRender("nope")).toBeUndefined();
  });
});
