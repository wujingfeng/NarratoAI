import { ArrowUpRight } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { useI18n } from "../../i18n/useI18n.js";

export function CreationEntryCard({ action, onUnavailable }) {
  const { t } = useI18n();
  const Icon = action.icon;
  return (
    <article className="creation-entry-card">
      <span className="creation-entry-card__icon" aria-hidden="true"><Icon /></span>
      <div>
        <p className="creation-entry-card__eyebrow">{t("dashboard.creation.eyebrow")}</p>
        <h2>{t("dashboard.creation.title")}</h2>
        <p className="creation-entry-card__description">{t("dashboard.creation.description")}</p>
      </div>
      {action.to ? (
        <Link to={action.to} aria-label={t(action.labelKey)}>
          {t(action.labelKey)}<ArrowUpRight aria-hidden="true" />
        </Link>
      ) : (
        <button type="button" onClick={() => onUnavailable(t(action.unavailableMessageKey))}>
          {t(action.labelKey)}<ArrowUpRight aria-hidden="true" />
        </button>
      )}
    </article>
  );
}
