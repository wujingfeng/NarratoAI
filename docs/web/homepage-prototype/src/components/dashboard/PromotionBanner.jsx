import { ArrowRight } from "@phosphor-icons/react";

export function PromotionBanner({ promotion, onUnavailable }) {
  return (
    <article className="promotion-banner" data-dashboard-banner aria-label={promotion.title}>
      <span className="promotion-banner__crystal" aria-hidden="true" />
      <span className="promotion-banner__orbit" aria-hidden="true" />
      <span className="promotion-banner__beam" aria-hidden="true" />
      <div className="promotion-banner__content">
        <p className="promotion-banner__eyebrow">{promotion.eyebrow}</p>
        <h2 className="promotion-banner__title">{promotion.title}</h2>
      </div>
      <button className="promotion-banner__action" type="button" onClick={() => onUnavailable(promotion.unavailableMessage)}>
        {promotion.action} <ArrowRight aria-hidden="true" />
      </button>
      <span className="promotion-banner__indicator" aria-hidden="true" />
    </article>
  );
}
