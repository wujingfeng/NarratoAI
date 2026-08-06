import { useState, type ReactNode } from "react";

type Props = {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
  badge?: string | undefined;
};

export function CollapsibleCard({
  title,
  defaultOpen = true,
  children,
  badge,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="c-card">
      <button
        type="button"
        className="c-card__head"
        onClick={() => setOpen((o) => !o)}
      >
        <span className="c-card__title">{title}</span>
        {badge && <span className="c-card__badge">{badge}</span>}
        <span className="c-card__caret">{open ? "▾" : "▸"}</span>
      </button>
      {open && <div className="c-card__body">{children}</div>}
    </div>
  );
}
