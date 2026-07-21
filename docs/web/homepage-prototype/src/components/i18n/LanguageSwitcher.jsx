import { useEffect, useRef, useState } from "react";
import { CaretDown, Check, Globe } from "@phosphor-icons/react";
import { useI18n } from "../../i18n/useI18n.js";

const LANGUAGES = [
  { id: "zh-CN", short: "简中", selfName: "简体中文" },
  { id: "en", short: "EN", selfName: "English" },
  { id: "ja", short: "日本語", selfName: "日本語" },
];

export function LanguageSwitcher({ compact = false, inline = false, className = "" }) {
  const { locale, setLocale, t } = useI18n();
  const [open, setOpen] = useState(false);
  const buttonRef = useRef(null);
  const menuRef = useRef(null);
  const currentLanguage = LANGUAGES.find((language) => language.id === locale) ?? LANGUAGES[0];

  useEffect(() => {
    if (!open) return undefined;

    const currentItem = menuRef.current?.querySelector(`[data-locale="${locale}"]`);
    (currentItem ?? menuRef.current?.querySelector('[role="menuitem"]'))?.focus();

    const handlePointerDown = (event) => {
      if (buttonRef.current?.contains(event.target) || menuRef.current?.contains(event.target)) return;
      setOpen(false);
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [locale, open]);

  const closeAndRestoreFocus = () => {
    setOpen(false);
    buttonRef.current?.focus();
  };

  const selectLanguage = (nextLocale) => {
    setLocale(nextLocale);
    if (!inline) closeAndRestoreFocus();
  };

  const handleMenuKeyDown = (event) => {
    const items = [...(menuRef.current?.querySelectorAll('[role="menuitem"]') ?? [])];
    const currentIndex = items.indexOf(document.activeElement);
    let nextIndex;

    if (event.key === "Escape") {
      event.preventDefault();
      closeAndRestoreFocus();
      return;
    }
    if (event.key === "ArrowDown") nextIndex = (currentIndex + 1) % items.length;
    else if (event.key === "ArrowUp") nextIndex = (currentIndex - 1 + items.length) % items.length;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = items.length - 1;
    else return;

    event.preventDefault();
    items[nextIndex]?.focus();
  };

  const classes = [
    "language-switcher",
    compact ? "language-switcher--compact" : "",
    inline ? "language-switcher--inline" : "",
    className,
  ].filter(Boolean).join(" ");

  if (inline) {
    return (
      <div className={classes} role="group" aria-label={t("common.language")}>
        {LANGUAGES.map((language) => (
          <button
            key={language.id}
            className="language-switcher__inline-option"
            type="button"
            aria-pressed={locale === language.id}
            onClick={() => selectLanguage(language.id)}
          >
            {language.selfName}
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className={classes}>
      <button
        ref={buttonRef}
        className="language-switcher__trigger"
        type="button"
        aria-label={`${t("common.language")}: ${currentLanguage.selfName}`}
        aria-haspopup="menu"
        aria-expanded={open}
        data-testid="language-switcher-trigger"
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
          event.preventDefault();
          setOpen(true);
        }}
      >
        <Globe size={19} aria-hidden="true" />
        {!compact && <span>{currentLanguage.short}</span>}
        <CaretDown className="language-switcher__caret" size={15} aria-hidden="true" />
      </button>
      {open && (
        <div ref={menuRef} className="language-switcher__menu" role="menu" onKeyDown={handleMenuKeyDown}>
          {LANGUAGES.map((language) => (
            <button
              key={language.id}
              className="language-switcher__option"
              type="button"
              role="menuitem"
              aria-current={locale === language.id ? "true" : undefined}
              data-locale={language.id}
              onClick={() => selectLanguage(language.id)}
            >
              <span>{language.selfName}</span>
              <Check size={17} weight="bold" aria-hidden="true" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
