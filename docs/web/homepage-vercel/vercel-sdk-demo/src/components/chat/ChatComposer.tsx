import { useState } from "react";
import { demoStageHints } from "../../features/agent/prompts";

type Props = {
  onSend: (text: string, file?: File) => void;
  disabled?: boolean;
};

const STAGE_HINTS = [
  ...demoStageHints.upload,
  ...demoStageHints.script,
  ...demoStageHints.voice,
  ...demoStageHints.render,
];

export function ChatComposer({ onSend, disabled }: Props) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const handleSend = () => {
    if (!text.trim() && !file) return;
    onSend(text, file ?? undefined);
    setText("");
    setFile(null);
  };

  return (
    <div className="composer">
      <div className="composer__hints">
        {STAGE_HINTS.map((h) => (
          <button
            key={h}
            type="button"
            className="composer__chip"
            onClick={() => onSend(h)}
          >
            {h}
          </button>
        ))}
      </div>
      <div className="composer__row">
        <input
          type="file"
          accept="video/mp4"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <input
          className="composer__input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="告诉 Narrato 你想做什么…"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
        />
        <button
          type="button"
          onClick={handleSend}
          disabled={disabled || (!text.trim() && !file)}
        >
          发送
        </button>
      </div>
      {file && <div className="composer__file">已选：{file.name}</div>}
    </div>
  );
}
