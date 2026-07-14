import { ArrowUpRight, Coins } from "@phosphor-icons/react";

export function CreditsOverview({ credits, onUnavailable }) {
  return (
    <section className="credits-overview" aria-labelledby="credits-title">
      <div className="dashboard-section-heading credits-overview__heading"><p>账户资源</p><h2 id="credits-title">创作点</h2></div>
      <span className="credits-overview__icon" aria-hidden="true"><Coins /></span>
      <span className="credits-ring" aria-hidden="true" />
      <p className="credits-overview__balance-label">当前余额</p>
      <strong className="credits-overview__balance-value">{credits.balance.toLocaleString("en-US")}</strong>
      <p className="credits-overview__usage"><span aria-hidden="true" />本月已使用 {credits.monthlyUsed} 创作点</p>
      <button className="credits-overview__action" type="button" onClick={() => onUnavailable("充值创作点功能建设中")}>充值创作点<ArrowUpRight aria-hidden="true" /></button>
    </section>
  );
}
