import { FilmSlate, FunnelSimple, MagicWand, Scissors, Translate } from "@phosphor-icons/react";
import { useI18n } from "../../i18n/useI18n.js";

const categoryIcons = { all: FunnelSimple, narration: FilmSlate, translation: Translate, remix: Scissors };

export function ProjectFilters({ categories, activeCategory, onCategoryChange, status, statuses, onStatusChange }) {
  const { t } = useI18n();
  return (
    <div className="project-filters" aria-label={t("projects.filters.ariaLabel")}>
      <div className="project-filters__categories" role="tablist" aria-label={t("projects.filters.types")}>
        {categories.map((category) => {
          const Icon = categoryIcons[category.id];
          return <button className={activeCategory === category.id ? "is-active" : ""} type="button" role="tab" aria-selected={activeCategory === category.id} onClick={() => onCategoryChange(category.id)} key={category.id}><Icon aria-hidden="true" /><span>{t(category.labelKey)}</span></button>;
        })}
      </div>
      <label className="project-status-select">
        <span className="sr-only">{t("projects.filters.status")}</span>
        <select value={status} onChange={(event) => onStatusChange(event.target.value)}>
          {statuses.map((item) => <option value={item.id} key={item.id}>{t(item.labelKey)}</option>)}
        </select>
      </label>
    </div>
  );
}
