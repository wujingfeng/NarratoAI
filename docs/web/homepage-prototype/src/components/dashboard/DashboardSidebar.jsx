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
  return (
    <aside className="dashboard-sidebar">
      <Link className="dashboard-sidebar__brand" to="/" aria-label="影创工坊">
        <BrandMark />
      </Link>
      <nav aria-label="工作台主导航">
        {["main", "tools", "account"].map((group) => (
          <div className={`dashboard-sidebar__group dashboard-sidebar__group--${group}`} key={group}>
            {items.filter((item) => item.group === group).map((item) => (
              <NavigationItem item={item} onUnavailable={onUnavailable} key={item.id} />
            ))}
          </div>
        ))}
      </nav>
    </aside>
  );
}
