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

