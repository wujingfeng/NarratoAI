import { ArrowUpRight } from "@phosphor-icons/react";

export function ToolQuickStart({ tools, onUnavailable }) {
  return (
    <section className="tool-quick-start" aria-labelledby="quick-start-title">
      <div className="dashboard-section-heading">
        <p>选择工具</p>
        <h2 id="quick-start-title">快速开始</h2>
      </div>
      <div className="tool-quick-start__grid">
        {tools.map((tool) => {
          const Icon = tool.icon;
          return (
            <button
              className={`tool-quick-start__card tool-quick-start__card--${tool.tone}`}
              type="button"
              onClick={() => onUnavailable(tool.unavailableMessage)}
              key={tool.id}
            >
              <span aria-hidden="true"><Icon /></span>
              <strong>{tool.title}</strong>
              <small>{tool.description}</small>
              <ArrowUpRight aria-hidden="true" />
            </button>
          );
        })}
      </div>
    </section>
  );
}
