import { ArrowRight, CrownSimple } from "@phosphor-icons/react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { BrandMark } from "../BrandMark.jsx";
import { useI18n } from "../../i18n/useI18n.js";

function NavigationItem({ item, onUnavailable }) {
  const { t } = useI18n();
  const { pathname } = useLocation();
  const Icon = item.icon;
  const content = <><Icon aria-hidden="true" /><span>{t(item.labelKey)}</span></>;

  return item.id === "narration" ? (
    <Link to={item.to} aria-current={pathname.startsWith("/dashboard/narration/") ? "page" : undefined}>{content}</Link>
  ) : item.to ? (
    <NavLink to={item.to} end={item.id !== "projects"}>{content}</NavLink>
  ) : (
    <button type="button" onClick={() => onUnavailable(t(item.unavailableMessageKey))}>{content}</button>
  );
}

export function DashboardSidebar({ items, onUnavailable }) {
  const { t } = useI18n();
  const groups = [
    { id: "main", label: null },
    { id: "tools", labelKey: "dashboard.sidebar.tools" },
    { id: "account", labelKey: "dashboard.sidebar.account" },
  ];

  return (
    <aside className="dashboard-sidebar">
      <Link className="dashboard-sidebar__brand" to="/" aria-label={t("dashboard.header.home")}>
        <BrandMark />
      </Link>
      <nav aria-label={t("dashboard.sidebar.navigation")}>
        {groups.map((group) => (
          <div className={`dashboard-sidebar__group dashboard-sidebar__group--${group.id}`} key={group.id}>
            {group.labelKey && (
              <p className="dashboard-sidebar__group-title"><span>{t(group.labelKey)}</span><i aria-hidden="true" /></p>
            )}
            {items.filter((item) => item.group === group.id).map((item) => (
              <NavigationItem item={item} onUnavailable={onUnavailable} key={item.id} />
            ))}
          </div>
        ))}
      </nav>
      <button
        className="dashboard-membership-card"
        type="button"
        onClick={() => onUnavailable(t("dashboard.unavailable.upgrade"))}
      >
        <CrownSimple className="dashboard-membership-card__icon" aria-hidden="true" />
        <span className="dashboard-membership-card__copy">
          <strong>{t("dashboard.membership.title")}</strong>
          <small>{t("dashboard.membership.description")}</small>
        </span>
        <ArrowRight className="dashboard-membership-card__arrow" aria-hidden="true" />
      </button>
    </aside>
  );
}
