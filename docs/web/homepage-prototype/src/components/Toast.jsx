import { CheckCircle, X } from "@phosphor-icons/react";
import { useI18n } from "../i18n/useI18n.js";

export function Toast({ message, onClose, isInert = false }) {
  const { t } = useI18n();
  if (!message) return null;

  return (
    <div
      className="toast is-visible"
      role="status"
      aria-live="polite"
      inert={isInert ? true : undefined}
      aria-hidden={isInert ? "true" : undefined}
    >
      <CheckCircle size={22} weight="fill" />
      <span>{message}</span>
      <button type="button" aria-label={t("home.toast.close")} onClick={onClose}><X size={17} /></button>
    </div>
  );
}
