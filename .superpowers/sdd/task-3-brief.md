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

