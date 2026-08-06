import { CollapsibleCard } from "../shared/CollapsibleCard";
import { useProjectStore } from "../../features/project/store";

export function ProjectInfoCard() {
  const project = useProjectStore((s) => s.project);
  const videos = useProjectStore((s) => s.videos);
  return (
    <CollapsibleCard
      title="项目信息"
      badge={videos.length > 0 ? `${videos.length} 个视频` : undefined}
    >
      <div className="kv">
        <span>标题</span>
        <b>{project.title}</b>
      </div>
      <div className="kv">
        <span>风格</span>
        <b>{project.style}</b>
      </div>
      <div className="kv">
        <span>目标时长</span>
        <b>{project.targetDurationSec} 秒</b>
      </div>
      <div className="kv">
        <span>目标观众</span>
        <b>{project.audience}</b>
      </div>
    </CollapsibleCard>
  );
}
