import { CollapsibleCard } from "../shared/CollapsibleCard";
import { EmptyState } from "../shared/EmptyState";
import { useProjectStore } from "../../features/project/store";

export function ScriptSegmentsCard() {
  const segments = useProjectStore((s) => s.script.segments);
  return (
    <CollapsibleCard
      title="解说脚本"
      badge={segments.length > 0 ? `${segments.length} 段` : undefined}
    >
      {segments.length === 0 ? (
        <EmptyState icon="📝" text="先生成脚本" />
      ) : (
        <ul className="insp-seg-list">
          {segments.map((seg) => (
            <li key={seg.id} className="insp-seg-list__row">
              <div className="insp-seg-list__head">
                <span>{seg.id}</span>
                <span>
                  {seg.start}–{seg.end}s · {seg.tone}
                </span>
              </div>
              <p>{seg.text}</p>
            </li>
          ))}
        </ul>
      )}
    </CollapsibleCard>
  );
}
