import { ArrowRight, X } from "@phosphor-icons/react";

export function PromotionBanner({ onClose, onUnavailable }) {
  return (
    <section className="promotion-banner" data-dashboard-banner aria-label="促销信息">
      <span className="promotion-banner__crystal" aria-hidden="true" />
      <span className="promotion-banner__orbit" aria-hidden="true" />
      <span className="promotion-banner__beam" aria-hidden="true" />
      <div className="promotion-banner__content">
        <p>限时创作加速计划</p>
        <h2>本周升级，额外获得 20% 创作点</h2>
      </div>
      <button type="button" onClick={() => onUnavailable("优惠活动功能建设中")}>
        立即查看 <ArrowRight aria-hidden="true" />
      </button>
      <button type="button" aria-label="关闭促销信息" onClick={onClose}>
        <X aria-hidden="true" />
      </button>
      <span className="promotion-banner__indicator" aria-hidden="true" />
    </section>
  );
}
