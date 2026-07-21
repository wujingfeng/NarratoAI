### Task 1: Locale Resolution and Translation Runtime

**Files:**
- Create: `docs/web/homepage-prototype/src/i18n/locale.js`
- Create: `docs/web/homepage-prototype/src/i18n/locale.test.js`
- Create: `docs/web/homepage-prototype/src/i18n/I18nProvider.jsx`
- Create: `docs/web/homepage-prototype/src/i18n/useI18n.js`
- Create: `docs/web/homepage-prototype/src/i18n/locales/zh-CN.js`
- Create: `docs/web/homepage-prototype/src/i18n/locales/en.js`
- Create: `docs/web/homepage-prototype/src/i18n/locales/ja.js`
- Modify: `docs/web/homepage-prototype/src/main.jsx`
- Modify: `docs/web/homepage-prototype/package.json`

**Interfaces:**
- Consumes: browser `localStorage`, `navigator.languages`, `document.documentElement.lang`, and static locale resources.
- Produces: `SUPPORTED_LOCALES`, `DEFAULT_LOCALE`, `STORAGE_KEY`, `normalizeLocale(value)`, `resolveInitialLocale({ storedLocale, browserLocales })`, `translate(resources, locale, key, params)`, `formatNumberForLocale(locale, value, options)`, `formatDateForLocale(locale, value, options)`, `I18nProvider`, and `useI18n()`.

- [ ] **Step 1: Write failing pure-function tests**

Create `src/i18n/locale.test.js` with concrete assertions:

```js
import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizeLocale,
  resolveInitialLocale,
  translate,
  formatNumberForLocale,
} from "./locale.js";

test("normalizes supported language tags", () => {
  assert.equal(normalizeLocale("zh-Hans-SG"), "zh-CN");
  assert.equal(normalizeLocale("en-US"), "en");
  assert.equal(normalizeLocale("ja-JP"), "ja");
  assert.equal(normalizeLocale("fr-FR"), null);
});

test("stored locale wins, then ordered browser locales, then zh-CN", () => {
  assert.equal(resolveInitialLocale({ storedLocale: "ja", browserLocales: ["en-US"] }), "ja");
  assert.equal(resolveInitialLocale({ storedLocale: "bad", browserLocales: ["fr-FR", "en-GB"] }), "en");
  assert.equal(resolveInitialLocale({ storedLocale: null, browserLocales: ["fr-FR"] }), "zh-CN");
});

test("translation falls back to zh-CN and preserves missing placeholders", () => {
  const resources = { "zh-CN": { hello: "你好 {name}", fallback: "中文" }, en: { hello: "Hi {name}" }, ja: {} };
  assert.equal(translate(resources, "en", "hello", { name: "Narrato" }), "Hi Narrato");
  assert.equal(translate(resources, "ja", "fallback"), "中文");
  assert.equal(translate(resources, "ja", "hello"), "你好 {name}");
  assert.equal(translate(resources, "ja", "missing.key"), "missing.key");
});

test("number formatting uses the active locale", () => {
  assert.equal(formatNumberForLocale("en", 1280), "1,280");
  assert.match(formatNumberForLocale("zh-CN", 1280), /1,280|1280/);
});
```

- [ ] **Step 2: Run tests and verify the red state**

Run: `cd docs/web/homepage-prototype && node --test src/i18n/locale.test.js`  
Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `src/i18n/locale.js`.

- [ ] **Step 3: Implement locale pure functions and resource skeletons**

Implement `locale.js` with exact exports and deterministic fallback:

```js
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

export function translate(resources, locale, key, params = {}) {
  const localized = readPath(resources[locale], key);
  const fallback = readPath(resources[DEFAULT_LOCALE], key);
  const template = typeof localized === "string" ? localized : typeof fallback === "string" ? fallback : key;
  return template.replace(/\{([^}]+)\}/g, (match, name) => Object.hasOwn(params, name) ? String(params[name]) : match);
}

export const formatNumberForLocale = (locale, value, options) => new Intl.NumberFormat(locale, options).format(value);
export const formatDateForLocale = (locale, value, options) => new Intl.DateTimeFormat(locale, options).format(value);
```

Create `zh-CN.js`, `en.js`, and `ja.js` exporting `zhCN`, `en`, and `ja`; start with matching nested `common.language`, `common.localeName`, and `titles` keys so later tasks extend the same shapes.

- [ ] **Step 4: Run pure tests and verify green state**

Run: `cd docs/web/homepage-prototype && node --test src/i18n/locale.test.js`  
Expected: 4 tests pass, 0 fail.

- [ ] **Step 5: Implement Provider, hook, app wiring, and test command**

Implement `I18nProvider.jsx` so initialization catches storage access errors, locale changes update `localStorage` and `<html lang>`, and the memoized value exposes the agreed API:

```jsx
const resources = { "zh-CN": zhCN, en, ja };
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
```

`useI18n.js` must throw a clear error outside the Provider. Wrap `<BrowserRouter>` and `<App />` with `<I18nProvider>` in `main.jsx`. Add `"test:i18n": "node --test src/i18n/locale.test.js"` to `package.json`.

- [ ] **Step 6: Verify runtime wiring**

Run: `cd docs/web/homepage-prototype && npm run test:i18n && npm run build`  
Expected: 4 tests pass and Vite exits 0 with `dist/index.html` generated.

- [ ] **Step 7: Commit the runtime unit**

```bash
git add docs/web/homepage-prototype/package.json docs/web/homepage-prototype/src/main.jsx docs/web/homepage-prototype/src/i18n
git commit -m "feat(prototype): add i18n runtime"
```

