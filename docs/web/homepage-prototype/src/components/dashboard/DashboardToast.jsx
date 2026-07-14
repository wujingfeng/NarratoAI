import { X } from "@phosphor-icons/react";

export function DashboardToast({ message, onClose }) {
  return (
    <div className="dashboard-toast" role="status" aria-live="polite">
      <span>{message}</span>
      <button type="button" aria-label="关闭提示" onClick={onClose}><X aria-hidden="true" /></button>
    </div>
  );
}
