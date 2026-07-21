import { ArrowUpRight } from "@phosphor-icons/react";
import { useI18n } from "../../i18n/useI18n.js";

export function FeaturedTools({ tools, onUnavailable }) {
  const { t } = useI18n();
  return (
    <section className="featured-tools" aria-labelledby="featured-tools-title">
      <div className="workspace-section-heading"><div><p>{t("dashboard.featuredTools.eyebrow")}</p><h2 id="featured-tools-title">{t("dashboard.featuredTools.title")}</h2></div></div>
      <div className="featured-tools__grid">
        {tools.map((tool) => {
          const Icon = tool.icon;
          return <button className={`featured-tools__card featured-tools__card--${tool.tone}`} type="button" key={tool.id} onClick={() => onUnavailable(t(tool.unavailableMessageKey))}><span aria-hidden="true"><Icon /></span><strong>{t(tool.titleKey)}</strong><small>{t(tool.descriptionKey)}</small><ArrowUpRight aria-hidden="true" /></button>;
        })}
      </div>
    </section>
  );
}
