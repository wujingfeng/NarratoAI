import type { Message } from "@ai-sdk/react";
import { ToolCallCard } from "./ToolCallCard";
import { ScriptSegmentCard } from "./ScriptSegmentCard";
import type { ScriptSegment } from "../../features/project/types";

type Props = { message: Message };

export function ChatMessage({ message }: Props) {
  const isUser = message.role === "user";
  return (
    <div className={`chat-msg chat-msg--${message.role}`}>
      <div className="chat-msg__avatar">{isUser ? "你" : "AI"}</div>
      <div className="chat-msg__body">
        {message.content && <p className="chat-msg__text">{message.content}</p>}
        {message.toolInvocations?.map((inv) => {
          const result = "result" in inv ? inv.result : undefined;
          if (
            inv.state === "result" &&
            result &&
            Array.isArray((result as { segments?: unknown[] }).segments)
          ) {
            return (
              <ScriptSegmentCard
                key={inv.toolCallId}
                segments={(result as { segments: ScriptSegment[] }).segments}
              />
            );
          }
          return (
            <ToolCallCard
              key={inv.toolCallId}
              toolName={inv.toolName ?? "?"}
              state={inv.state}
              result={result}
            />
          );
        })}
      </div>
    </div>
  );
}
