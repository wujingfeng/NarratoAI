import { Check } from "@phosphor-icons/react";
import { useI18n } from "../../i18n/useI18n.js";

export function CreationTypeSelector({ types, selectedType, onChange }) {
  const { t } = useI18n();
  return (
    <section className="create-type-section" aria-labelledby="create-type-heading">
      <h2 id="create-type-heading">{t("create.typeSelector.title")}</h2>
      <div className="create-type-grid" role="group" aria-label={t("create.typeSelector.ariaLabel")}>
        {types.map((type) => {
          const Icon = type.icon;
          const selected = selectedType === type.id;
          return (
            <button
              className={`create-type-card create-type-card--${type.tone}`}
              type="button"
              aria-pressed={selected}
              data-creation-type={type.id}
              onClick={() => onChange(type.id)}
              key={type.id}
            >
              {selected && <span className="create-type-card__check"><Check weight="bold" aria-hidden="true" /></span>}
              <Icon className="create-type-card__icon" weight="duotone" aria-hidden="true" />
              <strong>{t(type.titleKey)}</strong>
              <small>{t(type.descriptionKey)}</small>
            </button>
          );
        })}
      </div>
    </section>
  );
}
