import { ArrowUpRight } from "@phosphor-icons/react";
import { DashboardThumbnail } from "./DashboardThumbnail.jsx";

export function InspirationPanel({ inspirations, onUnavailable }) {
  return (
    <section className="inspiration-panel" aria-labelledby="inspiration-title">
      <div className="dashboard-section-heading"><p>探索更多</p><h2 id="inspiration-title">创作灵感</h2></div>
      <div className="inspiration-panel__list">
        {inspirations.map((item) => (
          <button type="button" onClick={() => onUnavailable(item.unavailableMessage)} key={item.id}>
            <DashboardThumbnail src={item.image} alt={`${item.title}封面`} fallbackLabel={item.title} />
            <span><strong>{item.title}</strong><small>{item.description}</small></span>
            <ArrowUpRight aria-hidden="true" />
          </button>
        ))}
      </div>
    </section>
  );
}
