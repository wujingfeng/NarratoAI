export const SUPPORTED_LOCALES = ["zh-CN", "en", "ja"];
export const DEFAULT_LOCALE = "zh-CN";
export const STORAGE_KEY = "narrato.locale";

export function normalizeLocale(value) {
  if (typeof value !== "string") return null;
  const tag = value.trim().replaceAll("_", "-").toLowerCase();
  if (tag === "zh" || tag.startsWith("zh-hans") || tag.startsWith("zh-cn") || tag.startsWith("zh-sg")) return "zh-CN";
  if (tag === "en" || tag.startsWith("en-")) return "en";
  if (tag === "ja" || tag.startsWith("ja-")) return "ja";
  return null;
}

export function resolveInitialLocale({ storedLocale, browserLocales = [] }) {
  const stored = normalizeLocale(storedLocale);
  if (stored) return stored;
  for (const candidate of browserLocales) {
    const locale = normalizeLocale(candidate);
    if (locale) return locale;
  }
  return DEFAULT_LOCALE;
}

function readPath(object, path) {
  return path.split(".").reduce((value, segment) => value?.[segment], object);
}

const warnedMissingKeys = new Set();

function isDevelopmentEnvironment() {
  if (import.meta.env?.DEV !== undefined) return import.meta.env.DEV;
  return typeof process === "undefined" || process.env.NODE_ENV !== "production";
}

export function translate(resources, locale, key, params = {}) {
  const localized = readPath(resources[locale], key);
  const fallback = readPath(resources[DEFAULT_LOCALE], key);
  if (typeof localized !== "string" && typeof fallback !== "string" && isDevelopmentEnvironment() && !warnedMissingKeys.has(key)) {
    warnedMissingKeys.add(key);
    console.warn(`[i18n] Missing translation key: ${key}`);
  }
  const template = typeof localized === "string" ? localized : typeof fallback === "string" ? fallback : key;
  return template.replace(/\{([^}]+)\}/g, (match, name) => Object.hasOwn(params, name) ? String(params[name]) : match);
}

export function formatNumberForLocale(locale, value, options) {
  const number = typeof value === "bigint" ? value : Number(value);
  return typeof number === "bigint" || Number.isFinite(number) ? new Intl.NumberFormat(locale, options).format(number) : value;
}

export function formatDateForLocale(locale, value, options) {
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(locale, options).format(date);
}
