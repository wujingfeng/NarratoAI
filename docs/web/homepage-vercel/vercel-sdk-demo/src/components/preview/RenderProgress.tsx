import { useProjectStore } from "../../features/project/store";

const STAGE_LABEL: Record<string, string> = {
  idle: "未开始",
  tts: "配音合成",
  subtitle: "字幕烧录",
  mixing: "音视频混流",
  encoding: "编码输出",
  done: "完成",
  failed: "失败",
};

export function RenderProgress() {
  const stage = useProjectStore((s) => s.render.stage);
  const progress = useProjectStore((s) => s.render.progress);
  const pct = Math.round(progress * 100);
  return (
    <div className="render-progress">
      <div className="render-progress__stage">
        {STAGE_LABEL[stage] ?? stage}
      </div>
      <div className="render-progress__bar">
        <div
          className="render-progress__fill"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="render-progress__pct">{pct}%</div>
    </div>
  );
}
