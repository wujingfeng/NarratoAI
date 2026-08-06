import { CollapsibleCard } from "../shared/CollapsibleCard";
import { EmptyState } from "../shared/EmptyState";
import { useProjectStore } from "../../features/project/store";

export function PlotAnalysisCard() {
  const scenes = useProjectStore((s) => s.plotAnalysis.scenes);
  return (
    <CollapsibleCard
      title="剧情分析"
      badge={scenes.length > 0 ? `${scenes.length} 段` : undefined}
    >
      {scenes.length === 0 ? (
        <EmptyState icon="🎬" text="上传视频后开始分析" />
      ) : (
        <ul className="scene-list">
          {scenes.map((s, i) => (
            <li key={`${s.start}-${i}`} className="scene-list__row">
              <div className="scene-list__time">
                {s.start}–{s.end}s
              </div>
              <div className="scene-list__summary">{s.summary}</div>
              {s.keyCharacters.length > 0 && (
                <div className="scene-list__chars">
                  人物：{s.keyCharacters.join("、")}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </CollapsibleCard>
  );
}
