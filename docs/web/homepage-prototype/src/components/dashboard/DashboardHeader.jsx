import { UserCircle } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { BrandMark } from "../BrandMark.jsx";
import { LanguageSwitcher } from "../i18n/LanguageSwitcher.jsx";
import { useI18n } from "../../i18n/useI18n.js";

export function DashboardHeader({ credits, onUnavailable }) {
  const { formatNumber, t } = useI18n();
  const balance = Number.isFinite(credits?.balance) ? formatNumber(credits.balance) : "—";
  return (
    <header className="dashboard-header">
      <Link className="dashboard-header--mobile" to="/" aria-label={t("dashboard.header.home")}>
        <BrandMark />
      </Link>
      <div className="dashboard-account-cluster" role="group" aria-label={t("dashboard.header.accountActions")}>
        <div className="dashboard-account">
          <LanguageSwitcher compact />
          <button
            className="dashboard-account__balance"
            type="button"
            aria-label={t("dashboard.header.viewBalance", { balance })}
            onClick={() => onUnavailable(t("dashboard.unavailable.creditDetails"))}
          >
            <span>{t("dashboard.credits.title")}</span>
            <strong>{balance}</strong>
          </button>
          <button className="dashboard-account__recharge" type="button" onClick={() => onUnavailable(t("dashboard.unavailable.recharge"))}>
            {t("dashboard.header.recharge")}
          </button>
        </div>
        <button
          className="dashboard-account__avatar"
          type="button"
          aria-label={t("dashboard.nav.account")}
          onClick={() => onUnavailable(t("dashboard.unavailable.account"))}
        >
          <UserCircle aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}
