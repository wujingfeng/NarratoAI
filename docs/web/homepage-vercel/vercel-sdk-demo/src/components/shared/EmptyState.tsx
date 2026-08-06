type Props = { icon?: string; text: string };

export function EmptyState({ icon = "📭", text }: Props) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon">{icon}</div>
      <div className="empty-state__text">{text}</div>
    </div>
  );
}
