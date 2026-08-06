import { CollapsibleCard } from "../shared/CollapsibleCard";
import { EmptyState } from "../shared/EmptyState";
import { useProjectStore } from "../../features/project/store";

export function VoiceSelectionCard() {
  const candidates = useProjectStore((s) => s.voice.candidates);
  const selected = useProjectStore((s) => s.voice.selected);
  const sel = candidates.find((v) => v.id === selected);
  return (
    <CollapsibleCard
      title="音色选择"
      badge={sel ? sel.name : undefined}
    >
      {candidates.length === 0 ? (
        <EmptyState icon="🎙️" text="尚未查询音色" />
      ) : (
        <ul className="voice-list">
          {candidates.map((v) => (
            <li
              key={v.id}
              className={`voice-list__row ${
                v.id === selected ? "voice-list__row--sel" : ""
              }`}
            >
              <div>
                <b>{v.name}</b>
                <span className="voice-list__meta">
                  {v.gender} · {v.age} · {v.tone}
                </span>
              </div>
              {v.id === selected && (
                <span className="voice-list__check">✓</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </CollapsibleCard>
  );
}
