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

