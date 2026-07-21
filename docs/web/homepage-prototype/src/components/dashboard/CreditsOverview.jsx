import { ArrowUpRight, Coins } from "@phosphor-icons/react";
import { useI18n } from "../../i18n/useI18n.js";

export function CreditsOverview({ credits, onUnavailable }) {
  const { formatNumber, t } = useI18n();
  return (
    <section className="credits-overview" aria-labelledby="credits-title">
      <div className="dashboard-section-heading credits-overview__heading"><p>{t("dashboard.credits.resource")}</p><h2 id="credits-title">{t("dashboard.credits.title")}</h2></div>
      <span className="credits-overview__icon" aria-hidden="true"><Coins /></span>
      <span className="credits-ring" aria-hidden="true" />
      <p className="credits-overview__balance-label">{t("dashboard.credits.balance")}</p>
      <strong className="credits-overview__balance-value">{formatNumber(credits.balance)}</strong>
      <p className="credits-overview__usage"><span aria-hidden="true" />{t("dashboard.credits.monthlyUsed", { count: formatNumber(credits.monthlyUsed) })}</p>
      <button className="credits-overview__action" type="button" aria-label={t("dashboard.credits.recharge")} onClick={() => onUnavailable(t("dashboard.unavailable.rechargeCredits"))}>{t("dashboard.credits.recharge")}<ArrowUpRight aria-hidden="true" /></button>
    </section>
  );
}
