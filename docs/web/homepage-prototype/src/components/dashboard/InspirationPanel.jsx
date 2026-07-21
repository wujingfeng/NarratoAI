import { ArrowUpRight } from "@phosphor-icons/react";
import { DashboardThumbnail } from "./DashboardThumbnail.jsx";
import { useI18n } from "../../i18n/useI18n.js";

export function InspirationPanel({ inspirations, onUnavailable }) {
  const { t } = useI18n();
  return (
    <section className="inspiration-panel" aria-labelledby="inspiration-title">
      <div className="dashboard-section-heading"><p>{t("dashboard.inspiration.eyebrow")}</p><h2 id="inspiration-title">{t("dashboard.inspiration.title")}</h2></div>
      <div className="inspiration-panel__list">
        {inspirations.map((item) => (
          <button className="inspiration-panel__item" type="button" onClick={() => onUnavailable(t(item.unavailableMessageKey))} key={item.id}>
            <DashboardThumbnail src={item.image} alt={t("dashboard.coverAlt", { name: t(item.titleKey) })} fallbackLabel={t(item.titleKey)} />
            <span className="inspiration-panel__content"><strong>{t(item.titleKey)}</strong><small>{t(item.descriptionKey)}</small></span>
            <ArrowUpRight className="inspiration-panel__arrow" aria-hidden="true" />
          </button>
        ))}
      </div>
    </section>
  );
}
