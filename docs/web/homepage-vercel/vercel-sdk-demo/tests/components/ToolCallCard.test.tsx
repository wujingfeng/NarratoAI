import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ToolCallCard } from "../../src/components/chat/ToolCallCard";

describe("ToolCallCard", () => {
  it("默认折叠，点击 head 展开", () => {
    render(
      <ToolCallCard
        toolName="analyze_plot"
        state="result"
        result={{ ok: true, scenes: [] }}
      />,
    );
    expect(screen.queryByText(/ok/i)).toBeNull();
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText(/"ok":\s*true/)).toBeTruthy();
  });

  it("错误时显示 error 样式", () => {
    const { container } = render(
      <ToolCallCard toolName="x" state="result" result={{ ok: false }} />,
    );
    expect(container.querySelector(".tool-card--error")).toBeTruthy();
  });
});
