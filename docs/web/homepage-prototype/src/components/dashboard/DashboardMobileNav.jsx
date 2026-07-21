import { NavLink } from "react-router-dom";
import { useI18n } from "../../i18n/useI18n.js";

export function DashboardMobileNav({ items, onUnavailable }) {
  const { t } = useI18n();
  const mobileLabels = { overview: "dashboard.mobile.overview", create: "dashboard.mobile.create", projects: "dashboard.mobile.projects", account: "dashboard.mobile.account" };
  const visibleItems = items.filter((item) => Object.hasOwn(mobileLabels, item.id));
  return (
    <nav className="dashboard-mobile-nav" aria-label={t("dashboard.mobile.navigation")}>
      {visibleItems.map((item) => {
        const Icon = item.icon;
        const content = <><Icon aria-hidden="true" /><span>{t(mobileLabels[item.id])}</span></>;
        return item.to ? (
          <NavLink to={item.to} end={item.id !== "projects"} key={item.id}>{content}</NavLink>
        ) : (
          <button type="button" onClick={() => onUnavailable(t(item.unavailableMessageKey))} key={item.id}>{content}</button>
        );
      })}
    </nav>
  );
}
