import { Check } from "@phosphor-icons/react";

export function Toast({ message }) {
  if (!message) return null;

  return (
    <div className="toast" role="status" aria-live="polite">
      <span><Check weight="bold" aria-hidden="true" /></span>
      {message}
    </div>
  );
}
