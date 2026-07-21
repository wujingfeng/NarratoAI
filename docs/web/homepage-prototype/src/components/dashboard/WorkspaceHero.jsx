import { ArrowRight, Sparkle } from "@phosphor-icons/react";
import { useI18n } from "../../i18n/useI18n.js";

export function WorkspaceHero({ onUnavailable }) {
  const { t } = useI18n();
  return (
    <section className="workspace-hero" aria-labelledby="workspace-hero-title">
      <div className="workspace-hero__copy">
        <p><Sparkle aria-hidden="true" />{t("dashboard.workspaceHero.eyebrow")}</p>
        <h2 id="workspace-hero-title">{t("dashboard.workspaceHero.title")}</h2>
        <span>{t("dashboard.workspaceHero.description")}</span>
      </div>
      <button type="button" onClick={() => onUnavailable(t("dashboard.unavailable.promotion"))}>
        {t("dashboard.workspaceHero.action")}<ArrowRight aria-hidden="true" />
      </button>
    </section>
  );
}
