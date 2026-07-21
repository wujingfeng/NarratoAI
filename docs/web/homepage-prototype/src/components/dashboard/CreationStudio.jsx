import { ArrowUpRight } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { useI18n } from "../../i18n/useI18n.js";

export function CreationStudio({ entries, onUnavailable, compact = false }) {
  const { t } = useI18n();
  return (
    <section className={`creation-studio${compact ? " creation-studio--compact" : ""}`} aria-labelledby="creation-studio-title">
      {!compact && <div className="workspace-section-heading"><div><p>{t("dashboard.creationSection.eyebrow")}</p><h2 id="creation-studio-title">{t("dashboard.creationSection.title")}</h2></div></div>}
      {compact && <h2 id="creation-studio-title" className="sr-only">{t("dashboard.creationSection.title")}</h2>}
      <div className="creation-studio__grid">
        {entries.map((entry) => {
          const Icon = entry.icon;
          const content = <><span className="creation-studio__icon" aria-hidden="true"><Icon /></span><span><strong>{t(entry.titleKey)}</strong><small>{t(entry.descriptionKey)}</small></span><ArrowUpRight aria-hidden="true" /></>;
          return entry.to ? <Link className={`creation-studio__card creation-studio__card--${entry.tone}`} key={entry.id} to={entry.to}>{content}</Link> : <button className={`creation-studio__card creation-studio__card--${entry.tone}`} type="button" key={entry.id} onClick={() => onUnavailable(t(entry.unavailableMessageKey))}>{content}</button>;
        })}
      </div>
    </section>
  );
}
