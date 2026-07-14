import { ArrowRight, CrownSimple } from "@phosphor-icons/react";
import { Link, NavLink } from "react-router-dom";
import { BrandMark } from "../BrandMark.jsx";

function NavigationItem({ item, onUnavailable }) {
  const Icon = item.icon;
  const content = <><Icon aria-hidden="true" /><span>{item.label}</span></>;

  return item.to ? (
    <NavLink to={item.to} end>{content}</NavLink>
  ) : (
    <button type="button" onClick={() => onUnavailable(item.unavailableMessage)}>{content}</button>
  );
}

export function DashboardSidebar({ items, onUnavailable }) {
  const groups = [
    { id: "main", label: null },
    { id: "tools", label: "工具" },
    { id: "account", label: "账户" },
  ];

  return (
    <aside className="dashboard-sidebar">
      <Link className="dashboard-sidebar__brand" to="/" aria-label="影创工坊">
        <BrandMark />
      </Link>
      <nav aria-label="工作台主导航">
        {groups.map((group) => (
          <div className={`dashboard-sidebar__group dashboard-sidebar__group--${group.id}`} key={group.id}>
            {group.label && (
              <p className="dashboard-sidebar__group-title"><span>{group.label}</span><i aria-hidden="true" /></p>
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
        onClick={() => onUnavailable("升级会员功能建设中")}
      >
        <CrownSimple className="dashboard-membership-card__icon" aria-hidden="true" />
        <span className="dashboard-membership-card__copy">
          <strong>升级会员</strong>
          <small>解锁更多权限，创作更高效</small>
        </span>
        <ArrowRight className="dashboard-membership-card__arrow" aria-hidden="true" />
      </button>
    </aside>
  );
}
