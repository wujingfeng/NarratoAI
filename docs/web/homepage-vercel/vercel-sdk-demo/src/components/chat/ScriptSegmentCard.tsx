import { useState } from "react";
import type { ScriptSegment } from "../../features/project/types";
import { useProjectStore } from "../../features/project/store";

type Props = { segments: ScriptSegment[] };

export function ScriptSegmentCard({ segments }: Props) {
  const update = useProjectStore((s) => s.updateSegmentText);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  return (
    <div className="script-card">
      <div className="script-card__title">解说脚本（{segments.length} 段）</div>
      {segments.map((seg) => (
        <div key={seg.id} className="script-card__row">
          <span className="script-card__idx">{seg.id}</span>
          {editing === seg.id ? (
            <>
              <input
                className="script-card__input"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              />
              <button
                type="button"
                onClick={() => {
                  update(seg.id, draft);
                  setEditing(null);
                }}
              >
                保存
              </button>
              <button type="button" onClick={() => setEditing(null)}>
                取消
              </button>
            </>
          ) : (
            <>
              <span className="script-card__text">{seg.text}</span>
              <button
                type="button"
                onClick={() => {
                  setEditing(seg.id);
                  setDraft(seg.text);
                }}
              >
                改
              </button>
            </>
          )}
        </div>
      ))}
    </div>
  );
}
