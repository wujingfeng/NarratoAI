import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("../../src/features/agent/useWorkbench", () => ({
  useWorkbench: () => ({
    messages: [
      { id: "1", role: "user", content: "你好", toolInvocations: [] },
      { id: "2", role: "assistant", content: "你好！", toolInvocations: [] },
    ],
    input: "",
    handleInputChange: vi.fn(),
    handleSubmit: vi.fn(),
    status: "ready",
    append: vi.fn(),
  }),
}));

import { ChatPanel } from "../../src/components/chat/ChatPanel";

describe("ChatPanel", () => {
  it("渲染用户与 AI 消息", () => {
    render(<ChatPanel projectId="p1" />);
    expect(screen.getByText("你好")).toBeTruthy();
    expect(screen.getByText("你好！")).toBeTruthy();
  });
});
