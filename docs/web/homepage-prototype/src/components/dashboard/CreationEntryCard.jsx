import { ArrowUpRight } from "@phosphor-icons/react";

export function CreationEntryCard({ action, onUnavailable }) {
  const Icon = action.icon;
  return (
    <article className="creation-entry-card">
      <span className="creation-entry-card__icon" aria-hidden="true"><Icon /></span>
      <div>
        <p>从一个想法开始</p>
        <h2>创建你的下一支爆款视频</h2>
      </div>
      <button type="button" onClick={() => onUnavailable(action.unavailableMessage)}>
        {action.label}<ArrowUpRight aria-hidden="true" />
      </button>
    </article>
  );
}
