import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import type { Message } from "@ai-sdk/react";
import { ChatMessage } from "../../src/components/chat/ChatMessage";

const baseMsg = (overrides: Partial<Message> = {}): Message => ({
  id: "m1",
  role: "assistant",
  content: "你好",
  toolInvocations: [],
  ...overrides,
} as unknown as Message);

describe("ChatMessage", () => {
  it("用户消息显示'你' avatar", () => {
    const { container } = render(<ChatMessage message={baseMsg({ role: "user", content: "hi" })} />);
    expect(container.textContent).toContain("你");
    expect(container.textContent).toContain("hi");
  });

  it("AI 消息显示'AI' avatar", () => {
    const { container } = render(<ChatMessage message={baseMsg({ role: "assistant", content: "ok" })} />);
    expect(container.textContent).toContain("AI");
  });

  it("无 content 时不渲染文本节点", () => {
    const { container } = render(<ChatMessage message={baseMsg({ content: "" })} />);
    expect(container.querySelector(".chat-msg__text")).toBeNull();
  });

  it("带 toolInvocations 时渲染 ToolCallCard", () => {
    const { container } = render(
      <ChatMessage
        message={baseMsg({
          toolInvocations: [
            {
              toolCallId: "t1",
              toolName: "set_narration_style",
              state: "result",
              args: { style: "悬疑" },
              result: { ok: true, style: "悬疑" },
            },
          ],
        })}
      />,
    );
    expect(container.textContent).toContain("设置解说风格");
  });

  it("toolInvocation.result.segments 走 ScriptSegmentCard 分支", () => {
    const { container } = render(
      <ChatMessage
        message={baseMsg({
          toolInvocations: [
            {
              toolCallId: "t2",
              toolName: "generate_script",
              state: "result",
              args: {},
              result: {
                segments: [
                  { id: "seg-1", start: 0, end: 12, text: "生成的文案", tone: "悬疑" },
                ],
              },
            },
          ],
        })}
      />,
    );
    expect(container.textContent).toContain("生成的文案");
  });
});
