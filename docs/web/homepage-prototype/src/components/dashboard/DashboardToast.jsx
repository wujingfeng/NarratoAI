import { X } from "@phosphor-icons/react";
import { useI18n } from "../../i18n/useI18n.js";

export function DashboardToast({ message, onClose }) {
  const { t } = useI18n();
  return (
    <div className="dashboard-toast" role="status" aria-live="polite">
      <span>{message}</span>
      <button type="button" aria-label={t("dashboard.toast.close")} onClick={onClose}><X aria-hidden="true" /></button>
    </div>
  );
}
