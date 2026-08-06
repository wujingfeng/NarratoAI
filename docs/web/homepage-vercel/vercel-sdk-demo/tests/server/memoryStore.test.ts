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
});
