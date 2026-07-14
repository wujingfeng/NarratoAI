import { Bell, Plus } from "@phosphor-icons/react";

export function DashboardHeader({ primaryAction, onUnavailable }) {
  return (
    <header className="dashboard-header">
      <div>
        <p className="dashboard-header__eyebrow">创作中心</p>
        <p className="dashboard-header__welcome">晚上好，欢迎回来</p>
      </div>
      <div className="dashboard-header__actions">
        <button type="button" aria-label="查看通知" onClick={() => onUnavailable("通知功能建设中")}>
          <Bell aria-hidden="true" />
        </button>
        <button type="button" onClick={() => onUnavailable(primaryAction.unavailableMessage)}>
          <Plus aria-hidden="true" />
          {primaryAction.label}
        </button>
      </div>
    </header>
  );
}
