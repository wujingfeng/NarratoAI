import { UserCircle } from "@phosphor-icons/react";

export function DashboardHeader({ credits, onUnavailable }) {
  return (
    <header className="dashboard-header">
      <div className="dashboard-account" aria-label="账户快捷操作">
        <button
          className="dashboard-account__balance"
          type="button"
          aria-label={`查看创作点余额 ${credits.balance.toLocaleString("en-US")}`}
          onClick={() => onUnavailable("创作点明细功能建设中")}
        >
          <span>创作点</span>
          <strong>{credits.balance.toLocaleString("en-US")}</strong>
        </button>
        <button className="dashboard-account__recharge" type="button" onClick={() => onUnavailable("充值功能建设中")}>
          去充值
        </button>
        <button
          className="dashboard-account__avatar"
          type="button"
          aria-label="账户中心"
          onClick={() => onUnavailable("账户中心功能建设中")}
        >
          <UserCircle aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}
