import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { InspectorPanel } from "../../src/components/inspector/InspectorPanel";
import { useProjectStore } from "../../src/features/project/store";

describe("InspectorPanel", () => {
  beforeEach(() => useProjectStore.getState().reset());

  it("渲染所有 5 个折叠卡片标题", () => {
    render(<InspectorPanel />);
    expect(screen.getByText("项目信息")).toBeTruthy();
    expect(screen.getByText("剧情分析")).toBeTruthy();
    expect(screen.getByText("解说脚本")).toBeTruthy();
    expect(screen.getByText("音色选择")).toBeTruthy();
    expect(screen.getByText("渲染状态")).toBeTruthy();
  });

  it("填充 plotAnalysis 后场景数 badge 出现", () => {
    useProjectStore.getState().setPlotAnalysis({
      scenes: [
        { start: 0, end: 10, summary: "s1", keyCharacters: [] },
        { start: 10, end: 20, summary: "s2", keyCharacters: [] },
      ],
    });
    render(<InspectorPanel />);
    expect(screen.getByText("2 段")).toBeTruthy();
  });
});
