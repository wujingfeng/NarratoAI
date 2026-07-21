import { useEffect, useRef } from "react";
import { List, X } from "@phosphor-icons/react";
import { BrandMark } from "./BrandMark.jsx";
import { LanguageSwitcher } from "./i18n/LanguageSwitcher.jsx";
import { useI18n } from "../i18n/useI18n.js";

export function SiteHeader({ activeSection, menuOpen, onMenuChange, onNavigate, onFeedback, isInert = false }) {
  const { t } = useI18n();
  const menuPanelRef = useRef(null);
  const restoreFocusRef = useRef(null);

  useEffect(() => {
    if (!menuOpen) return undefined;

    restoreFocusRef.current = document.activeElement;
    requestAnimationFrame(() => {
      menuPanelRef.current?.querySelector("button:not([disabled])")?.focus();
    });

    const handleMenuKey = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onMenuChange(false);
        return;
      }

      if (event.key !== "Tab") return;
      const focusable = menuPanelRef.current
        ? [...menuPanelRef.current.querySelectorAll("button:not([disabled])")]
        : [];
      const first = focusable[0];
      const last = focusable.at(-1);
      if (!first || !last) return;

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", handleMenuKey);
    return () => {
      window.removeEventListener("keydown", handleMenuKey);
      requestAnimationFrame(() => restoreFocusRef.current?.focus?.());
    };
  }, [menuOpen, onMenuChange]);

  const navItems = [
    { id: "capabilities", label: t("home.header.capabilities") },
    { id: "demo", label: t("home.header.demo") },
  ];

  return (
    <header className="site-header" inert={isInert ? true : undefined} aria-hidden={isInert ? "true" : undefined}>
      <div
        className="site-header__inner page-container"
        inert={menuOpen ? true : undefined}
        aria-hidden={menuOpen ? "true" : undefined}
      >
        <button className="brand-button" type="button" aria-label={t("home.header.home")} onClick={() => onNavigate("hero")}>
          <BrandMark />
        </button>
        <nav className="desktop-nav" aria-label={t("home.header.primaryNavigation")}>
          {navItems.map((item) => (
            <button
              key={item.id}
              className={activeSection === item.id ? "is-active" : ""}
              type="button"
              onClick={() => onNavigate(item.id)}
            >
              {item.label}
            </button>
          ))}
          <button type="button" onClick={() => onFeedback(t("home.header.pricingFeedback"))}>{t("home.header.pricing")}</button>
        </nav>
        <div className="header-actions">
          <LanguageSwitcher />
          <button className="login-button" type="button" onClick={() => onFeedback(t("home.header.loginFeedback"))}>
            {t("common.login")}
          </button>
          <button
            className="menu-button"
            type="button"
            aria-label={menuOpen ? t("common.closeMenu") : t("common.openMenu")}
            aria-expanded={menuOpen}
            onClick={() => onMenuChange(!menuOpen)}
          >
            {menuOpen ? <X size={28} /> : <List size={30} />}
          </button>
        </div>
      </div>
      <div className={`mobile-menu ${menuOpen ? "is-open" : ""}`} aria-hidden={!menuOpen} inert={!menuOpen ? true : undefined}>
        <button className="mobile-menu__backdrop" type="button" aria-label={t("common.closeMenu")} onClick={() => onMenuChange(false)} />
        <nav ref={menuPanelRef} className="mobile-menu__panel" aria-label={t("home.header.mobileNavigation")}>
          <div className="mobile-menu__top">
            <BrandMark compact />
            <button type="button" aria-label={t("common.closeMenu")} onClick={() => onMenuChange(false)}><X size={26} /></button>
          </div>
          {navItems.map((item, index) => (
            <button key={item.id} type="button" onClick={() => onNavigate(item.id)}>
              <span>0{index + 1}</span>{item.label}
            </button>
          ))}
          <button type="button" onClick={() => { onMenuChange(false); onFeedback(t("home.header.pricingFeedback")); }}>
            <span>03</span>{t("home.header.pricing")}
          </button>
          <LanguageSwitcher inline />
          <button className="mobile-menu__login" type="button" onClick={() => { onMenuChange(false); onFeedback(t("home.header.loginFeedback")); }}>
            {t("home.header.loginFull")}
          </button>
        </nav>
      </div>
    </header>
  );
}
