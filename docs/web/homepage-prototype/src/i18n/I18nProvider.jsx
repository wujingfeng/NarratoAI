import { createContext, useCallback, useEffect, useMemo, useState } from "react";
import {
  STORAGE_KEY,
  SUPPORTED_LOCALES,
  formatDateForLocale,
  formatNumberForLocale,
  normalizeLocale,
  resolveInitialLocale,
  translate,
} from "./locale.js";
import { zhCN } from "./locales/zh-CN.js";
import { en } from "./locales/en.js";
import { ja } from "./locales/ja.js";

const resources = { "zh-CN": zhCN, en, ja };

export const I18nContext = createContext(null);

export function I18nProvider({ children }) {
  const [locale, setLocaleState] = useState(() => {
    let storedLocale = null;
    try { storedLocale = window.localStorage.getItem(STORAGE_KEY); } catch {}
    return resolveInitialLocale({ storedLocale, browserLocales: navigator.languages ?? [navigator.language] });
  });

  const setLocale = useCallback((next) => {
    const normalized = normalizeLocale(next);
    if (normalized) setLocaleState(normalized);
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
    try { window.localStorage.setItem(STORAGE_KEY, locale); } catch {}
  }, [locale]);

  const value = useMemo(() => ({
    locale,
    setLocale,
    supportedLocales: SUPPORTED_LOCALES,
    t: (key, params) => translate(resources, locale, key, params),
    formatNumber: (number, options) => formatNumberForLocale(locale, number, options),
    formatDate: (date, options) => formatDateForLocale(locale, date, options),
  }), [locale, setLocale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
