import { useEffect, useRef } from "react";
import { ChatMessage } from "./ChatMessage";
import { ChatComposer } from "./ChatComposer";
import { useWorkbench } from "../../features/agent/useWorkbench";
import { useProjectStore } from "../../features/project/store";

type Props = { projectId: string };

export function ChatPanel({ projectId }: Props) {
  const banner = useProjectStore((s) => s.banner);
  const clearBanner = useProjectStore((s) => s.clearBanner);
  const { messages, status, append } = useWorkbench(projectId);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <section className="chat-panel">
      {banner && (
        <div className={`chat-banner chat-banner--${banner.kind}`}>
          <span>{banner.text}</span>
          <button type="button" onClick={clearBanner}>
            ×
          </button>
        </div>
      )}
      <div className="chat-panel__list">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>👋 你好，我是 Narrato。</p>
            <p>告诉我你想做什么，例如"帮我分析这 3 集短剧"。</p>
          </div>
        )}
        {messages.map((m) => (
          <ChatMessage key={m.id} message={m} />
        ))}
        <div ref={bottomRef} />
      </div>
      <ChatComposer
        onSend={(text, file) => {
          if (file)
            void append({
              role: "user",
              content: `${text}（已上传 ${file.name}）`,
            });
          else void append({ role: "user", content: text });
        }}
        disabled={status !== "ready"}
      />
    </section>
  );
}
