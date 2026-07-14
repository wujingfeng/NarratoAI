import { NavLink } from "react-router-dom";

export function DashboardMobileNav({ items, onUnavailable }) {
  const visibleItems = items.filter((item) => ["overview", "projects", "narration", "account"].includes(item.id));
  return (
    <nav className="dashboard-mobile-nav" aria-label="移动工作台导航">
      {visibleItems.map((item) => {
        const Icon = item.icon;
        const content = <><Icon aria-hidden="true" /><span>{item.label}</span></>;
        return item.to ? (
          <NavLink to={item.to} end key={item.id}>{content}</NavLink>
        ) : (
          <button type="button" onClick={() => onUnavailable(item.unavailableMessage)} key={item.id}>{content}</button>
        );
      })}
    </nav>
  );
}
