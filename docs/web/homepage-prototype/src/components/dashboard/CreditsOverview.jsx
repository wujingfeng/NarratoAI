import { ArrowUpRight, Coins } from "@phosphor-icons/react";

export function CreditsOverview({ credits, onUnavailable }) {
  return (
    <section className="credits-overview" aria-labelledby="credits-title">
      <div className="dashboard-section-heading"><p>账户资源</p><h2 id="credits-title">创作点</h2></div>
      <span className="credits-overview__icon" aria-hidden="true"><Coins /></span>
      <p>当前余额</p>
      <strong>{credits.balance.toLocaleString("en-US")}</strong>
      <p>本月已使用 {credits.monthlyUsed} 创作点</p>
      <button type="button" onClick={() => onUnavailable("充值创作点功能建设中")}>充值创作点<ArrowUpRight aria-hidden="true" /></button>
    </section>
  );
}
