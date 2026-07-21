# Homepage Prototype I18n Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent, accessible `zh-CN` / `en` / `ja` localization to every route in `docs/web/homepage-prototype` without changing URLs or editor behavior.

**Architecture:** A dependency-free `I18nProvider` owns the normalized locale and exposes `t`, `formatNumber`, and `formatDate`; three static resource modules contain UI copy while stable business data keeps IDs and content values. A shared `LanguageSwitcher` is mounted in the public header, dashboard header, and narration editor, and Node built-in tests plus an existing-style Playwright script verify pure logic and browser behavior.

**Tech Stack:** React 19.2, React Router 7.18, Vite 6.4, JavaScript/JSX, `Intl`, Node `node:test`, Playwright 1.61.

## Global Constraints

- Scope is exactly `docs/web/homepage-prototype` and every existing route: `/`, `/dashboard`, `/dashboard/create`, `/dashboard/projects`, `/dashboard/projects/overlord/result`, `/dashboard/narration/settings`, `/dashboard/narration/analysis`, `/dashboard/narration/editor`, and the wildcard 404 route.
- Supported locale identifiers are exactly `zh-CN`, `en`, and `ja`; initialization precedence is `localStorage("narrato.locale") > navigator.languages > zh-CN`.
- Language switching must not refresh, mutate the URL, replace browser history, or discard page interaction state.
- Do not add an i18n runtime dependency; use `I18nProvider`, `useI18n`, `t`, and built-in `Intl`.
- Translate visible UI, navigation, controls, placeholders, status, steps, filters, pagination, Toast/error/unavailable copy, `aria-label`, hidden headings, image alt text, and `document.title`.
- Do not translate project names, uploaded file names, media source subtitles, translation-demo source/target content, brand names, timecodes, resolutions, formats, or stable technical values.
- Data filtering and status logic must use stable IDs, never translated labels; do not duplicate the complete business dataset per locale.
- The narration editor change is copy/layout only: do not alter time coordinates, media state, drag, selection, zoom, scrolling, seek, waveform lifecycle, track data, or reducer behavior.
- Do not add screenshots, `background-image` reference art, `data:image`, base64, canvas screenshot rendering, SVG embedded bitmaps, or bitmap fills.
- Existing unrelated workspace changes must remain untouched.

---

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

### Task 2: Shared Accessible Language Switcher

**Files:**
- Create: `docs/web/homepage-prototype/src/components/i18n/LanguageSwitcher.jsx`
- Modify: `docs/web/homepage-prototype/src/components/SiteHeader.jsx`
- Modify: `docs/web/homepage-prototype/src/styles/home.css`
- Modify: `docs/web/homepage-prototype/src/i18n/locales/zh-CN.js`
- Modify: `docs/web/homepage-prototype/src/i18n/locales/en.js`
- Modify: `docs/web/homepage-prototype/src/i18n/locales/ja.js`
- Create: `docs/web/homepage-prototype/scripts/verify-i18n.mjs`
- Modify: `docs/web/homepage-prototype/package.json`

**Interfaces:**
- Consumes: `useI18n()` from Task 1 and Phosphor `Globe`, `CaretDown`, and `Check` icons.
- Produces: `<LanguageSwitcher compact={false} inline={false} className="" />`, public-header desktop and mobile entry points, and `npm run verify:i18n`.

- [ ] **Step 1: Write the failing public-header browser assertions**

Create `scripts/verify-i18n.mjs` using `playwright` and a spawned Vite preview. Its first scenario must clear storage, emulate English browser locale, open `/`, then assert:

```js
await page.goto(`${baseUrl}/`);
await page.getByTestId("language-switcher-trigger").waitFor();
assert.equal(await page.locator("html").getAttribute("lang"), "en");
assert.equal(await page.getByTestId("language-switcher-trigger").getAttribute("aria-haspopup"), "menu");
await page.getByTestId("language-switcher-trigger").click();
await page.getByRole("menuitem", { name: "日本語" }).click();
assert.equal(new URL(page.url()).pathname, "/");
assert.equal(await page.locator("html").getAttribute("lang"), "ja");
assert.equal(await page.evaluate(() => localStorage.getItem("narrato.locale")), "ja");
```

Add `"verify:i18n": "node scripts/verify-i18n.mjs"` to `package.json`.

- [ ] **Step 2: Run the browser script and verify the red state**

Run: `cd docs/web/homepage-prototype && npm run build && npm run verify:i18n`  
Expected: FAIL because `language-switcher-trigger` does not exist.

- [ ] **Step 3: Implement menu behavior and public placements**

Build `LanguageSwitcher.jsx` around a button ref, menu ref, and local `open` state. Use a constant list with `{ id: "zh-CN", short: "简中", selfName: "简体中文" }`, `{ id: "en", short: "EN", selfName: "English" }`, and `{ id: "ja", short: "日本語", selfName: "日本語" }`. Implement outside-pointer close, `Escape` close/focus restore, `ArrowUp`/`ArrowDown` looping, `Home`/`End`, and selection via native buttons. Render `role="menu"`, `role="menuitem"`, `aria-current`, `aria-haspopup="menu"`, `aria-expanded`, and `data-testid="language-switcher-trigger"`.

Mount the default switcher immediately before `.login-button` in the desktop header. In `.mobile-menu__panel`, mount `<LanguageSwitcher inline />` immediately before `.mobile-menu__login`; inline mode renders all three options without a nested popover. Translate `SiteHeader` navigation, feedback strings, menu labels, accessible names, and login copy using `home.header.*` and `common.*` keys.

- [ ] **Step 4: Add responsive switcher styles**

Add scoped `.language-switcher*` rules to `home.css`: relative trigger container, popover above surrounding stacking contexts, minimum 44px hit targets, visible focus rings, selected check alignment, and inline three-option mobile grid. At `max-width: 767px`, hide the desktop trigger with the other desktop-only header controls and keep inline options visible in the mobile panel. Do not add `text-overflow: ellipsis` to key actions.

- [ ] **Step 5: Verify public switching and keyboard behavior**

Extend the browser script to open the menu with keyboard, move with `ArrowDown`, close with `Escape`, verify focus returns to the trigger, click outside to close, and at 390px open the site menu and assert all three self-name options are visible.

Run: `cd docs/web/homepage-prototype && npm run build && npm run verify:i18n`  
Expected: public-header scenarios pass with exit code 0.

- [ ] **Step 6: Commit the shared control**

```bash
git add docs/web/homepage-prototype/package.json docs/web/homepage-prototype/scripts/verify-i18n.mjs docs/web/homepage-prototype/src/components/i18n/LanguageSwitcher.jsx docs/web/homepage-prototype/src/components/SiteHeader.jsx docs/web/homepage-prototype/src/styles/home.css docs/web/homepage-prototype/src/i18n/locales
git commit -m "feat(prototype): add accessible language switcher"
```

### Task 3: Homepage and Route Metadata Translation

**Files:**
- Modify: `docs/web/homepage-prototype/src/components/BrandMark.jsx`
- Modify: `docs/web/homepage-prototype/src/components/CapabilitySection.jsx`
- Modify: `docs/web/homepage-prototype/src/components/DemoSection.jsx`
- Modify: `docs/web/homepage-prototype/src/components/FaqSection.jsx`
- Modify: `docs/web/homepage-prototype/src/components/FinalCtaSection.jsx`
- Modify: `docs/web/homepage-prototype/src/components/HeroSection.jsx`
- Modify: `docs/web/homepage-prototype/src/components/RouteEffects.jsx`
- Modify: `docs/web/homepage-prototype/src/components/SiteFooter.jsx`
- Modify: `docs/web/homepage-prototype/src/components/Toast.jsx`
- Modify: `docs/web/homepage-prototype/src/components/VideoModal.jsx`
- Modify: `docs/web/homepage-prototype/src/pages/HomePage.jsx`
- Modify: `docs/web/homepage-prototype/src/pages/NotFoundPage.jsx`
- Modify: `docs/web/homepage-prototype/src/i18n/locales/zh-CN.js`
- Modify: `docs/web/homepage-prototype/src/i18n/locales/en.js`
- Modify: `docs/web/homepage-prototype/src/i18n/locales/ja.js`
- Modify: `docs/web/homepage-prototype/scripts/verify-i18n.mjs`

**Interfaces:**
- Consumes: `t`, `locale`, and existing homepage event callbacks.
- Produces: complete `home.*`, `errors.notFound.*`, and `titles.*` resource groups; localized `document.title` without focus/scroll regression.

- [ ] **Step 1: Add failing route-title and homepage-copy assertions**

For each locale, add expected home title and hero heading constants to `verify-i18n.mjs`; visit `/`, select the locale, and assert both values. Visit `/missing-route` and assert the localized 404 heading and title. Capture `scrollY` and active element before switching on `/`; assert language switching does not call route focus behavior or reset scroll.

- [ ] **Step 2: Run the browser script and verify the red state**

Run: `cd docs/web/homepage-prototype && npm run verify:i18n`  
Expected: FAIL because homepage copy and titles remain Chinese in `en` and `ja`.

- [ ] **Step 3: Populate resources and migrate homepage UI**

Move every UI string in the listed homepage components into matching keys. Keep `BrandMark` brand text and the demo's source/translated content examples unchanged; translate their labels, captions, playback controls, modal accessible names, Toast messages, FAQ copy, CTA copy, footer links, image alternatives, and hidden headings. All three locale modules must have identical key paths.

- [ ] **Step 4: Correct RouteEffects dependencies**

Replace the hard-coded title map with pathname-to-key mapping and `t(titleKey)`. Use one effect depending on `[pathname, t]` for title and a separate effect depending only on `[pathname]` for scroll reset and route-heading focus. This separation is required so locale switching updates title without scrolling or stealing focus.

- [ ] **Step 5: Verify home and metadata localization**

Run: `cd docs/web/homepage-prototype && npm run test:i18n && npm run build && npm run verify:i18n`  
Expected: pure tests pass, build exits 0, and home/404/title/focus assertions pass in all locales.

- [ ] **Step 6: Commit the homepage unit**

```bash
git add docs/web/homepage-prototype/src/components docs/web/homepage-prototype/src/pages/HomePage.jsx docs/web/homepage-prototype/src/pages/NotFoundPage.jsx docs/web/homepage-prototype/src/i18n/locales docs/web/homepage-prototype/scripts/verify-i18n.mjs
git commit -m "feat(prototype): localize homepage and route metadata"
```

### Task 4: Dashboard, Creation, and Projects Translation

**Files:**
- Modify: `docs/web/homepage-prototype/src/data/dashboardData.js`
- Modify: `docs/web/homepage-prototype/src/data/createData.js`
- Modify: `docs/web/homepage-prototype/src/data/projectsData.js`
- Modify: `docs/web/homepage-prototype/src/components/dashboard/CreationEntryCard.jsx`
- Modify: `docs/web/homepage-prototype/src/components/dashboard/CreditsOverview.jsx`
- Modify: `docs/web/homepage-prototype/src/components/dashboard/DashboardHeader.jsx`
- Modify: `docs/web/homepage-prototype/src/components/dashboard/DashboardMobileNav.jsx`
- Modify: `docs/web/homepage-prototype/src/components/dashboard/DashboardSidebar.jsx`
- Modify: `docs/web/homepage-prototype/src/components/dashboard/DashboardThumbnail.jsx`
- Modify: `docs/web/homepage-prototype/src/components/dashboard/DashboardToast.jsx`
- Modify: `docs/web/homepage-prototype/src/components/dashboard/InspirationPanel.jsx`
- Modify: `docs/web/homepage-prototype/src/components/dashboard/PromotionBanner.jsx`
- Modify: `docs/web/homepage-prototype/src/components/dashboard/RecentProjects.jsx`
- Modify: `docs/web/homepage-prototype/src/components/dashboard/ToolQuickStart.jsx`
- Modify: `docs/web/homepage-prototype/src/components/create/CreationSummary.jsx`
- Modify: `docs/web/homepage-prototype/src/components/create/CreationTypeSelector.jsx`
- Modify: `docs/web/homepage-prototype/src/components/create/UploadedVideoList.jsx`
- Modify: `docs/web/homepage-prototype/src/components/create/VideoUploadPanel.jsx`
- Modify: `docs/web/homepage-prototype/src/components/projects/ProjectFilters.jsx`
- Modify: `docs/web/homepage-prototype/src/components/projects/ProjectPagination.jsx`
- Modify: `docs/web/homepage-prototype/src/components/projects/ProjectTable.jsx`
- Modify: `docs/web/homepage-prototype/src/pages/DashboardPage.jsx`
- Modify: `docs/web/homepage-prototype/src/pages/CreatePage.jsx`
- Modify: `docs/web/homepage-prototype/src/pages/ProjectsPage.jsx`
- Modify: `docs/web/homepage-prototype/src/styles/dashboard.css`
- Modify: `docs/web/homepage-prototype/src/i18n/locales/zh-CN.js`
- Modify: `docs/web/homepage-prototype/src/i18n/locales/en.js`
- Modify: `docs/web/homepage-prototype/src/i18n/locales/ja.js`
- Modify: `docs/web/homepage-prototype/scripts/verify-i18n.mjs`

**Interfaces:**
- Consumes: `t`, `formatNumber`, shared `LanguageSwitcher`, stable `id`/`type`/`status` fields, and unchanged project/file names.
- Produces: `dashboard.*`, `create.*`, and `projects.*` resource groups plus localized dashboard header entry point.

- [ ] **Step 1: Add failing dashboard/create/projects assertions**

In `verify-i18n.mjs`, loop over `/dashboard`, `/dashboard/create`, and `/dashboard/projects` for all locales. Assert localized route heading, header trigger presence, title, Toast/unavailable message after a representative button click, and `document.documentElement.scrollWidth <= document.documentElement.clientWidth` at 1487px, 768px, and 390px. On projects, type the unchanged Chinese project name `霸总短剧解说 01` and assert it remains searchable after selecting English and Japanese.

- [ ] **Step 2: Run the browser script and verify the red state**

Run: `cd docs/web/homepage-prototype && npm run verify:i18n`  
Expected: FAIL because the dashboard header has no switcher and these routes retain Chinese UI.

- [ ] **Step 3: Convert display fields to translation keys**

In `dashboardData.js`, `createData.js`, and `projectsData.js`, rename UI fields to `labelKey`, `titleKey`, `descriptionKey`, `statusKey`, `subtitleStatusKey`, and `unavailableMessageKey`. Preserve project `title`, video `name`, `subtitleName`, IDs, routes, durations, credits, media paths, and status/type machine values. Construct messages with `t(key)` at render time; do not compare rendered labels in filtering or actions.

- [ ] **Step 4: Localize dashboard UI and mount header switcher**

Call `useI18n()` in each dashboard component that renders copy. Mount `<LanguageSwitcher compact />` immediately before `.dashboard-account__balance`; format credit values through `formatNumber`. Replace visible labels, responsive nav names, Toast messages, image alternatives, and account accessible names. Add CSS that permits the account cluster to shrink/wrap safely while retaining 44px interactive targets.

- [ ] **Step 5: Localize create and projects UI**

Translate headings, descriptions, file-upload instructions, limits, statuses, buttons, filters, table headers, pagination, menus, empty states, Toasts, hidden labels, and accessible names. Preserve displayed project/file names. Use stable `category.id`, `status.id`, `project.type`, and `project.status` for state and filtering.

- [ ] **Step 6: Verify these routes and legacy scripts**

Run: `cd docs/web/homepage-prototype && npm run build && npm run verify:i18n && npm run verify:dashboard && npm run verify:create && npm run verify:projects`  
Expected: all commands exit 0; all three locales pass route, persistence, search, and overflow checks.

- [ ] **Step 7: Commit the workbench unit**

```bash
git add docs/web/homepage-prototype/src/data docs/web/homepage-prototype/src/components/dashboard docs/web/homepage-prototype/src/components/create docs/web/homepage-prototype/src/components/projects/ProjectFilters.jsx docs/web/homepage-prototype/src/components/projects/ProjectPagination.jsx docs/web/homepage-prototype/src/components/projects/ProjectTable.jsx docs/web/homepage-prototype/src/pages/DashboardPage.jsx docs/web/homepage-prototype/src/pages/CreatePage.jsx docs/web/homepage-prototype/src/pages/ProjectsPage.jsx docs/web/homepage-prototype/src/styles/dashboard.css docs/web/homepage-prototype/src/i18n/locales docs/web/homepage-prototype/scripts/verify-i18n.mjs
git commit -m "feat(prototype): localize dashboard and projects"
```

### Task 5: Project Result, Narration Settings, and Analysis Translation

**Files:**
- Modify: `docs/web/homepage-prototype/src/data/projectResultData.js`
- Modify: `docs/web/homepage-prototype/src/data/narrationData.js`
- Modify: `docs/web/homepage-prototype/src/data/narrationAnalysisData.js`
- Modify: `docs/web/homepage-prototype/src/components/projects/ProjectResultDetails.jsx`
- Modify: `docs/web/homepage-prototype/src/components/projects/ProjectResultPlayer.jsx`
- Modify: `docs/web/homepage-prototype/src/components/narration/NarrationAnalysisBoard.jsx`
- Modify: `docs/web/homepage-prototype/src/components/narration/NarrationFullscreenPlayer.jsx`
- Modify: `docs/web/homepage-prototype/src/components/narration/NarrationPreview.jsx`
- Modify: `docs/web/homepage-prototype/src/components/narration/NarrationSettingsForm.jsx`
- Modify: `docs/web/homepage-prototype/src/components/narration/NarrationStepper.jsx`
- Modify: `docs/web/homepage-prototype/src/pages/ProjectResultPage.jsx`
- Modify: `docs/web/homepage-prototype/src/pages/NarrationSettingsPage.jsx`
- Modify: `docs/web/homepage-prototype/src/pages/NarrationAnalysisPage.jsx`
- Modify: `docs/web/homepage-prototype/src/i18n/locales/zh-CN.js`
- Modify: `docs/web/homepage-prototype/src/i18n/locales/en.js`
- Modify: `docs/web/homepage-prototype/src/i18n/locales/ja.js`
- Modify: `docs/web/homepage-prototype/scripts/verify-i18n.mjs`

**Interfaces:**
- Consumes: stable project/media content and `t`/`formatNumber`.
- Produces: `projectResult.*`, `narration.*`, and `analysis.*` resources without changing project title, file content, media paths, timecodes, or resolution.

- [ ] **Step 1: Add failing route and content-boundary assertions**

For all locales, visit the project result, narration settings, and analysis routes. Assert localized route headings, buttons, stage/status labels, logs, Toasts, media accessible names, and titles. Also assert literal project name `霸总短剧解说 01`, resolution `1080 × 1920`, timecode `01:25`, and episode labels remain unchanged.

- [ ] **Step 2: Run the browser script and verify the red state**

Run: `cd docs/web/homepage-prototype && npm run verify:i18n`  
Expected: FAIL on English and Japanese UI assertions while unchanged-content assertions document the boundary.

- [ ] **Step 3: Convert result/settings/analysis display metadata to keys**

Replace UI-bearing `status`, `steps`, log messages, cost labels, summary labels, narration step/style/ratio/subtitle-style labels, analysis stage titles/statuses, and analysis log messages with explicit `*Key` properties. Keep IDs, state machine values, duration strings, timestamps, episode labels, project title, format, resolution, media URLs, numeric costs, and source content unchanged.

- [ ] **Step 4: Migrate the listed components and pages**

Use `t()` at rendering boundaries for every visible and accessible UI string. Translate fullscreen-player controls, preview labels, form help/error copy, buttons, progress semantics, result download/action messages, Toasts, and hidden route headings. Use `formatNumber` for credits and counts only; preserve timecodes and log timestamps verbatim.

- [ ] **Step 5: Verify routes and existing focused checks**

Run: `cd docs/web/homepage-prototype && npm run build && npm run verify:i18n && npm run verify:project-result && node scripts/verify-narration-analysis.mjs`  
Expected: all commands exit 0; three-locale assertions and unchanged-content boundary checks pass.

- [ ] **Step 6: Commit the narration flow unit**

```bash
git add docs/web/homepage-prototype/src/data docs/web/homepage-prototype/src/components/projects/ProjectResultDetails.jsx docs/web/homepage-prototype/src/components/projects/ProjectResultPlayer.jsx docs/web/homepage-prototype/src/components/narration docs/web/homepage-prototype/src/pages/ProjectResultPage.jsx docs/web/homepage-prototype/src/pages/NarrationSettingsPage.jsx docs/web/homepage-prototype/src/pages/NarrationAnalysisPage.jsx docs/web/homepage-prototype/src/i18n/locales docs/web/homepage-prototype/scripts/verify-i18n.mjs
git commit -m "feat(prototype): localize narration workflow"
```

### Task 6: Narration Editor Copy-Only Localization

**Files:**
- Modify: `docs/web/homepage-prototype/src/features/narration-editor/NarrationEditor.jsx`
- Modify: `docs/web/homepage-prototype/src/features/narration-editor/PreviewPlayer.jsx`
- Modify: `docs/web/homepage-prototype/src/features/narration-editor/Timeline.jsx`
- Modify: `docs/web/homepage-prototype/src/features/narration-editor/WaveformTrack.jsx`
- Modify: `docs/web/homepage-prototype/src/styles/narration-editor.css`
- Modify: `docs/web/homepage-prototype/src/pages/NarrationEditorPage.jsx`
- Modify: `docs/web/homepage-prototype/src/i18n/locales/zh-CN.js`
- Modify: `docs/web/homepage-prototype/src/i18n/locales/en.js`
- Modify: `docs/web/homepage-prototype/src/i18n/locales/ja.js`
- Modify: `docs/web/homepage-prototype/scripts/verify-i18n.mjs`

**Interfaces:**
- Consumes: shared `LanguageSwitcher`, `t`, `formatNumber`, existing editor reducer/state/actions, cue text, and media elements.
- Produces: localized `editor.*` UI and a compact topbar switcher; no changes to editor algorithms or content data.

- [ ] **Step 1: Add failing editor state-preservation assertions**

Open `/dashboard/narration/editor`, record the same `<video>` DOM handle, current media time, selected clip IDs exposed by the existing UI, zoom label/value, and the active script textarea value. Edit the textarea, switch to `ja`, then assert the URL, DOM handle, media time within a 0.25s tolerance, selection, zoom, and edited text are preserved while the hidden heading and save button are Japanese. Assert subtitle cue text and project name remain original content.

- [ ] **Step 2: Run the browser script and verify the red state**

Run: `cd docs/web/homepage-prototype && npm run verify:i18n`  
Expected: FAIL because the editor switcher and localized editor labels do not exist.

- [ ] **Step 3: Localize editor chrome without touching behavior modules**

Mount `<LanguageSwitcher compact />` in `.editor-topbar` immediately before `.editor-credits`. Translate topbar navigation/status/actions, clip panel, inspector tabs and labels, setting names, player controls, timeline controls/track labels, Toast messages, hidden headings, and accessible names. Keep project names, `bgmFile`, subtitle cue `text`, script content text, asset URLs, time values, percentages, ratios, and score numbers as content/technical values.

Do not modify `editor-reducer.js`, `timeline-geometry.js`, or `editor-data.js`. Do not add locale to reducer state or keys on player/timeline/waveform components. The switch must trigger ordinary context rerenders, not conditional remounting.

- [ ] **Step 4: Make topbar copy responsive without geometry changes**

Adjust only topbar and label wrapping styles in `narration-editor.css`; retain editor workspace dimensions, fixed track labels, scroll containers, timeline width calculations, zoom rules, and waveform sizing. The compact switcher must remain reachable at narrow widths without creating page-level horizontal scrolling.

- [ ] **Step 5: Verify editor behavior and localization**

Run: `cd docs/web/homepage-prototype && npm run build && npm run verify:i18n && node scripts/verify-narration-editor.mjs`  
Expected: build and scripts exit 0; localized editor assertions pass; existing time-zero, zoom, internal-scroll, selection, playback, and waveform checks remain green.

- [ ] **Step 6: Commit the editor localization unit**

```bash
git add docs/web/homepage-prototype/src/features/narration-editor/NarrationEditor.jsx docs/web/homepage-prototype/src/features/narration-editor/PreviewPlayer.jsx docs/web/homepage-prototype/src/features/narration-editor/Timeline.jsx docs/web/homepage-prototype/src/features/narration-editor/WaveformTrack.jsx docs/web/homepage-prototype/src/pages/NarrationEditorPage.jsx docs/web/homepage-prototype/src/styles/narration-editor.css docs/web/homepage-prototype/src/i18n/locales docs/web/homepage-prototype/scripts/verify-i18n.mjs
git commit -m "feat(prototype): localize narration editor chrome"
```

### Task 7: Coverage Audit, Responsive QA, and Final Verification

**Files:**
- Modify: `docs/web/homepage-prototype/scripts/verify-i18n.mjs`
- Modify: `docs/web/homepage-prototype/src/i18n/locale.test.js`
- Modify: `docs/web/homepage-prototype/src/i18n/locales/zh-CN.js`
- Modify: `docs/web/homepage-prototype/src/i18n/locales/en.js`
- Modify: `docs/web/homepage-prototype/src/i18n/locales/ja.js`
- Modify only if an audit finds missed UI copy: files already listed in Tasks 2–6.
- Create: `docs/web/homepage-prototype/artifacts/i18n/` screenshots generated by the verification script.

**Interfaces:**
- Consumes: completed locale resources, all localized routes, existing verification scripts.
- Produces: exhaustive automated route matrix, visual evidence, and a clean final build.

- [ ] **Step 1: Add resource parity and raw-copy audit tests**

Extend `locale.test.js` with a recursive leaf-key collector and assert English and Japanese key sets exactly equal Chinese. Add an explicit allowlist for content strings (`霸总短剧解说 01`, project/file names, subtitle/script content) and scan JSX/data modules for remaining Han UI literals; the test must fail with file and literal when a non-allowlisted UI string remains.

- [ ] **Step 2: Run audits and verify any red findings are specific**

Run: `cd docs/web/homepage-prototype && npm run test:i18n`  
Expected: either all tests pass or failures name an exact missing resource key/raw UI literal; no generic snapshot failure.

- [ ] **Step 3: Resolve every named parity or raw-copy finding**

For each failure, add the same semantic key to all three resource modules and replace the raw UI literal with `t(key)`. Expand the allowlist only when the value is one of the documented non-translated content categories, with an adjacent comment naming that category.

- [ ] **Step 4: Complete Playwright route/viewport matrix and screenshots**

For all nine route outcomes and three locales, assert HTTP/page load, localized title, `html[lang]`, a localized route heading, no console errors, and no page-level horizontal overflow at 1487×1058, 768×1024, and 390×844. Save representative English and Japanese screenshots under `artifacts/i18n/`; screenshots are QA evidence only and must never be imported by production code.

- [ ] **Step 5: Run the full regression suite**

Run:

```bash
cd docs/web/homepage-prototype
npm run test:i18n
npm run build
npm run verify:i18n
npm run verify:routing
npm run verify:hero
npm run verify:demo
npm run verify:three-hero
npm run verify:dashboard
npm run verify:create
npm run verify:projects
npm run verify:project-result
node scripts/verify-narration-analysis.mjs
node scripts/verify-narration-editor.mjs
```

Expected: every command exits 0; unit tests report 0 failures; all route/locale/viewport checks pass; no editor regression assertion fails.

- [ ] **Step 6: Run the prohibited-asset and reference-removal audit**

Run:

```bash
cd docs/web/homepage-prototype
rg -n "data:image|background-image|<canvas|<image" src || true
rg -n "artifacts/|comparisons/|screenshots/" src || true
```

Expected: no newly introduced screenshot/base64/reference-art import. Any existing legitimate canvas or background declaration must be reviewed against `git diff` and confirmed unchanged by this feature. Temporarily hide QA/reference assets and load every route; page主体 remains complete because production code does not consume them.

- [ ] **Step 7: Review the final diff and commit verification changes**

Run: `git diff --check && git status --short`  
Expected: `git diff --check` exits 0; status lists only the planned prototype files and generated `artifacts/i18n` evidence.

```bash
git add docs/web/homepage-prototype/scripts/verify-i18n.mjs docs/web/homepage-prototype/src/i18n docs/web/homepage-prototype/artifacts/i18n
git commit -m "test(prototype): verify multilingual route coverage"
```

## Execution Notes

- Execute tasks in order because later browser assertions rely on the runtime and shared switcher interfaces established in Tasks 1–2.
- At each task boundary, review `git diff --stat` and `git diff --check` before committing; do not stage unrelated changes.
- If a legacy visual assertion encodes Chinese UI copy rather than behavior, update that assertion to select by stable test ID or locale-aware expected text while preserving its original behavior coverage.
