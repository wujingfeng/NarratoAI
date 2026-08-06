import { CollapsibleCard } from "../shared/CollapsibleCard";
import { useProjectStore } from "../../features/project/store";

export function RenderStatusCard() {
  const renderId = useProjectStore((s) => s.render.renderId);
  const stage = useProjectStore((s) => s.render.stage);
  const progress = useProjectStore((s) => s.render.progress);
  const pct = Math.round(progress * 100);
  const badge =
    stage === "done"
      ? "完成"
      : stage === "failed"
        ? "失败"
        : stage === "idle"
          ? "未开始"
          : `${pct}%`;
  return (
    <CollapsibleCard title="渲染状态" badge={badge}>
      <div className="kv">
        <span>renderId</span>
        <b>{renderId ?? "—"}</b>
      </div>
      <div className="kv">
        <span>阶段</span>
        <b>{stage}</b>
      </div>
      <div className="kv">
        <span>进度</span>
        <b>{pct}%</b>
      </div>
    </CollapsibleCard>
  );
}
