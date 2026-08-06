import { describe, it, expect } from "vitest";
import { allTools, toolNames } from "../../src/features/agent/tools";

describe("Agent 工具集", () => {
  it("导出 11 个工具", () => {
    expect(Object.keys(allTools).length).toBe(11);
  });

  it("包含全部预期工具名", () => {
    const expected = [
      "upload_video",
      "analyze_plot",
      "set_narration_style",
      "set_target_duration",
      "generate_script",
      "edit_script_segment",
      "regenerate_segment",
      "list_voices",
      "select_voice",
      "start_render",
      "track_render_status",
    ];
    for (const name of expected) {
      expect(toolNames).toContain(name);
    }
  });

  it("每个工具都有 description 和 parameters", () => {
    for (const [name, t] of Object.entries(allTools)) {
      expect(t.description, `${name} 缺 description`).toBeTruthy();
      expect(t.parameters, `${name} 缺 parameters`).toBeDefined();
    }
  });
});
