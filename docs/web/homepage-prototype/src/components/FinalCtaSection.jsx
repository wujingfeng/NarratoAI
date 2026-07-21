import { ArrowRight, Sparkle } from "@phosphor-icons/react";
import { useI18n } from "../i18n/useI18n.js";

export function FinalCtaSection({ onStart }) {
  const { t } = useI18n();
  return (
    <section className="final-cta-panel" aria-labelledby="final-cta-title">
      <div className="final-cta-orbit" aria-hidden="true"><span /><span /><span /></div>
      <Sparkle className="final-cta-icon" size={42} weight="duotone" />
      <h2 id="final-cta-title">{t("home.finalCta.headingPrefix")}<span className="gradient-text">{t("home.finalCta.headingAccent")}</span>{t("home.finalCta.headingSuffix")}</h2>
      <button className="primary-button" type="button" onClick={onStart}>{t("home.finalCta.start")} <ArrowRight size={21} /></button>
      <p>{t("home.finalCta.note")}</p>
    </section>
  );
}
