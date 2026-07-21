import { BrandMark } from "./BrandMark.jsx";
import { useI18n } from "../i18n/useI18n.js";

export function SiteFooter({ onNavigate, onFeedback, isInert = false }) {
  const { t } = useI18n();
  return (
    <footer className="site-footer" inert={isInert ? true : undefined} aria-hidden={isInert ? "true" : undefined}>
      <div className="page-container site-footer__inner">
        <button className="brand-button" type="button" onClick={() => onNavigate("hero")}><BrandMark compact /></button>
        <nav aria-label={t("home.footer.navigation")}>
          <button type="button" onClick={() => onNavigate("capabilities")}>{t("home.header.capabilities")}</button>
          <button type="button" onClick={() => onNavigate("demo")}>{t("home.header.demo")}</button>
          <button type="button" onClick={() => onFeedback(t("home.header.pricingFeedback"))}>{t("home.header.pricing")}</button>
        </nav>
        <div className="site-footer__legal"><button type="button" onClick={() => onFeedback(t("home.footer.termsFeedback"))}>{t("home.footer.terms")}</button><button type="button" onClick={() => onFeedback(t("home.footer.privacyFeedback"))}>{t("home.footer.privacy")}</button></div>
      </div>
    </footer>
  );
}
