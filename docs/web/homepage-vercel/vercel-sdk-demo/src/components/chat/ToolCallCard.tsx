import { useState } from "react";

type Props = {
  toolName: string;
  state: "call" | "partial-call" | "result";
  result?: unknown;
};

const LABEL: Record<string, string> = {
  upload_video: "上传视频",
  analyze_plot: "分析剧情",
  set_narration_style: "设置解说风格",
  set_target_duration: "设置目标时长",
  generate_script: "生成脚本",
  edit_script_segment: "修改段落",
  regenerate_segment: "重新生成段落",
  list_voices: "查询音色",
  select_voice: "选定音色",
  start_render: "开始渲染",
  track_render_status: "查询渲染状态",
};

export function ToolCallCard({ toolName, state, result }: Props) {
  const [open, setOpen] = useState(false);
  const label = LABEL[toolName] ?? toolName;
  const isError =
    state === "result" &&
    result &&
    typeof result === "object" &&
    "ok" in result &&
    (result as { ok: boolean }).ok === false;
  return (
    <div className={`tool-card ${isError ? "tool-card--error" : ""}`}>
      <button
        type="button"
        className="tool-card__head"
        onClick={() => setOpen((o) => !o)}
      >
        <span className="tool-card__dot" />
        <span className="tool-card__name">{label}</span>
        <span className="tool-card__state">
          {state === "result" ? "完成" : "执行中…"}
        </span>
      </button>
      {open && (
        <pre className="tool-card__body">
          {JSON.stringify(result ?? null, null, 2)}
        </pre>
      )}
    </div>
  );
}
