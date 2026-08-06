import { describe, it, expect, beforeEach } from "vitest";
import { useProjectStore } from "../../src/features/project/store";

describe("useProjectStore", () => {
  beforeEach(() => {
    useProjectStore.getState().reset();
  });

  it("setStyle 更新项目风格", () => {
    useProjectStore.getState().setStyle("搞笑");
    expect(useProjectStore.getState().project.style).toBe("搞笑");
  });

  it("setTargetDuration 更新目标时长", () => {
    useProjectStore.getState().setTargetDuration(90);
    expect(useProjectStore.getState().project.targetDurationSec).toBe(90);
  });

  it("appendScene 累加场景", () => {
    useProjectStore
      .getState()
      .appendScene({ start: 0, end: 10, summary: "s1", keyCharacters: [] });
    useProjectStore
      .getState()
      .appendScene({ start: 10, end: 20, summary: "s2", keyCharacters: [] });
    expect(useProjectStore.getState().plotAnalysis.scenes).toHaveLength(2);
  });

  it("updateSegmentText 改写某段文案", () => {
    useProjectStore.getState().setScriptSegments([
      { id: "a", start: 0, end: 5, text: "old", tone: "紧张" },
    ]);
    useProjectStore.getState().updateSegmentText("a", "new");
    expect(useProjectStore.getState().script.segments[0]?.text).toBe("new");
  });

  it("setBanner 设置后能被 clearBanner 清空", () => {
    useProjectStore.getState().setBanner("error", "出错");
    expect(useProjectStore.getState().banner?.text).toBe("出错");
    useProjectStore.getState().clearBanner();
    expect(useProjectStore.getState().banner).toBeNull();
  });
});
