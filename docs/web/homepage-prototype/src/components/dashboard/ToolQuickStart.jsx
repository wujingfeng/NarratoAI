import { ArrowUpRight } from "@phosphor-icons/react";
import { useI18n } from "../../i18n/useI18n.js";

export function ToolQuickStart({ tools, onUnavailable }) {
  const { t } = useI18n();
  return (
    <section className="tool-quick-start" aria-labelledby="quick-start-title">
      <div className="dashboard-section-heading">
        <p>{t("dashboard.quickStart.eyebrow")}</p>
        <h2 id="quick-start-title">{t("dashboard.quickStart.title")}</h2>
      </div>
      <div className="tool-quick-start__grid dashboard-tool-list">
        {tools.map((tool) => {
          const Icon = tool.icon;
          return (
            <button
              className={`tool-quick-start__card tool-quick-start__card--${tool.tone}`}
              type="button"
              onClick={() => onUnavailable(t(tool.unavailableMessageKey))}
              key={tool.id}
            >
              <span aria-hidden="true"><Icon /></span>
              <strong>{t(tool.titleKey)}</strong>
              <small>{t(tool.descriptionKey)}</small>
              <ArrowUpRight aria-hidden="true" />
            </button>
          );
        })}
      </div>
    </section>
  );
}
