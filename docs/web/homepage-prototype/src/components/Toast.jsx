import { CheckCircle, X } from "@phosphor-icons/react";

export function Toast({ message, onClose, isInert = false }) {
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
      <button type="button" aria-label="关闭提示" onClick={onClose}><X size={17} /></button>
    </div>
  );
}
