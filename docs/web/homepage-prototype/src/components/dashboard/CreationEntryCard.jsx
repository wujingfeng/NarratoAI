import { ArrowUpRight } from "@phosphor-icons/react";
import { Link } from "react-router-dom";

export function CreationEntryCard({ action, onUnavailable }) {
  const Icon = action.icon;
  return (
    <article className="creation-entry-card">
      <span className="creation-entry-card__icon" aria-hidden="true"><Icon /></span>
      <div>
        <p className="creation-entry-card__eyebrow">开始一次新的 AI 创作</p>
        <h2>新建创作</h2>
        <p className="creation-entry-card__description">上传素材，跟随引导完成专业出片</p>
      </div>
      {action.to ? (
        <Link to={action.to}>{action.label}<ArrowUpRight aria-hidden="true" /></Link>
      ) : (
        <button type="button" onClick={() => onUnavailable(action.unavailableMessage)}>
          {action.label}<ArrowUpRight aria-hidden="true" />
        </button>
      )}
    </article>
  );
}
