# Dashboard Create Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a high-fidelity `/dashboard/create` page with local-only creation type, video, subtitle, summary, and navigation interactions while reusing the existing dashboard shell components.

**Architecture:** `CreatePage` owns local state and composes existing dashboard navigation, account, mobile navigation, and toast components. Focused components under `src/components/create/` render selection, upload, file-list, subtitle, and summary units; `src/styles/create.css` contains page-specific responsive styling.

**Tech Stack:** React 19, React Router 7, Phosphor Icons, CSS, Vite 6, Playwright 1.61.

## Global Constraints

- Route: `/dashboard/create`.
- No backend API, persistence, real upload, AI recognition, billing, or parameter page.
- Primary visual acceptance viewport: `1487 × 1058`.
- Reuse `DashboardSidebar`, `DashboardHeader`, `DashboardMobileNav`, and `DashboardToast`.
- Do not embed the reference image or any screenshot fragment in the implementation.
- Do not use `data:image`, base64, canvas screenshot drawing, SVG embedded bitmaps, or `background-image: url(...)`.
- Existing content thumbnails may be used only as video-content assets.
- Preserve unrelated dirty changes already present in `docs/web/homepage-prototype/`.
- Per project instructions, this single-page UI task is executed inline without Subagents.

---

## File Map

**Create**

- `docs/web/homepage-prototype/src/pages/CreatePage.jsx`: page shell, state, upload handlers, summary calculations, and toast lifecycle.
- `docs/web/homepage-prototype/src/components/create/CreationTypeSelector.jsx`: accessible creation-type radio group.
- `docs/web/homepage-prototype/src/components/create/VideoUploadPanel.jsx`: drag/drop and video file input.
- `docs/web/homepage-prototype/src/components/create/UploadedVideoList.jsx`: ordered rows and deletion.
- `docs/web/homepage-prototype/src/components/create/SubtitleUploadPanel.jsx`: optional SRT selection and removal.
- `docs/web/homepage-prototype/src/components/create/CreationSummary.jsx`: duration, cost, balance, and next-step action.
- `docs/web/homepage-prototype/src/data/createData.js`: creation types and initial demo rows.
- `docs/web/homepage-prototype/src/styles/create.css`: desktop and responsive styles.
- `docs/web/homepage-prototype/scripts/verify-create.mjs`: source scan, routing, interactions, geometry, and mobile checks.
- `docs/web/homepage-prototype/scripts/capture-create.mjs`: desktop screenshot saved under `artifacts/create-page/`.

**Modify**

- `docs/web/homepage-prototype/src/App.jsx`: register `CreatePage` route.
- `docs/web/homepage-prototype/src/main.jsx`: import `create.css`.
- `docs/web/homepage-prototype/src/data/dashboardData.js`: set create navigation target and primary action target.
- `docs/web/homepage-prototype/src/components/dashboard/CreationEntryCard.jsx`: render the primary action as a link when `action.to` exists.
- `docs/web/homepage-prototype/package.json`: add create-page verification and screenshot scripts.
- `docs/web/homepage-prototype/scripts/verify-routing.mjs`: cover create route title, route focus, and entry navigation.

---

### Task 1: Route and entry contract

**Files:**
- Modify: `docs/web/homepage-prototype/src/App.jsx`
- Modify: `docs/web/homepage-prototype/src/data/dashboardData.js`
- Modify: `docs/web/homepage-prototype/src/components/dashboard/CreationEntryCard.jsx`
- Create: `docs/web/homepage-prototype/src/pages/CreatePage.jsx`
- Test: `docs/web/homepage-prototype/scripts/verify-routing.mjs`

**Interfaces:**
- Produces: route element at `/dashboard/create`; `dashboardPrimaryAction.to`; navigation items with `to`.
- Consumes: existing dashboard route-focus behavior and React Router `Link`/`NavLink`.

- [ ] **Step 1: Extend routing verification before production changes**

Add assertions that direct navigation to `/dashboard/create` expects title `新建创作｜影创工坊`, heading `创建新的 AI 视频`, and that the dashboard primary card, desktop sidebar, and mobile create entry navigate there.

- [ ] **Step 2: Run the test and verify RED**

Run while a Vite preview is serving the current build:

```bash
npm run build && npm run preview -- --host 127.0.0.1
BASE_URL=http://127.0.0.1:4173 node scripts/verify-routing.mjs
```

Expected: FAIL because `/dashboard/create` falls through to `NotFoundPage` and create entries are not links.

- [ ] **Step 3: Add the minimal route and link behavior**

Register:

```jsx
<Route path="/dashboard/create" element={<CreatePage />} />
```

Set both create items to `to: "/dashboard/create"`. Update `CreationEntryCard` so the action control is a `<Link to={action.to}>` when present, preserving the existing button fallback.

Create a minimal `CreatePage` that renders one focusable route heading:

```jsx
<h1 data-route-heading tabIndex="-1">创建新的 AI 视频</h1>
```

- [ ] **Step 4: Rebuild and verify GREEN**

Run the same commands. Expected: routing verification passes with all three create entry points reaching `/dashboard/create`.

---

### Task 2: Local state and accessible creation components

**Files:**
- Create: `docs/web/homepage-prototype/src/data/createData.js`
- Create: `docs/web/homepage-prototype/src/components/create/CreationTypeSelector.jsx`
- Create: `docs/web/homepage-prototype/src/components/create/VideoUploadPanel.jsx`
- Create: `docs/web/homepage-prototype/src/components/create/UploadedVideoList.jsx`
- Create: `docs/web/homepage-prototype/src/components/create/SubtitleUploadPanel.jsx`
- Create: `docs/web/homepage-prototype/src/components/create/CreationSummary.jsx`
- Modify: `docs/web/homepage-prototype/src/pages/CreatePage.jsx`
- Create: `docs/web/homepage-prototype/scripts/verify-create.mjs`

**Interfaces:**
- `CreationTypeSelector({ types, selectedType, onChange })`.
- `VideoUploadPanel({ videos, isDragging, onFiles, onDragStateChange, onRemove })`.
- `UploadedVideoList({ videos, onRemove })`.
- `SubtitleUploadPanel({ subtitle, onSelect, onRemove })`.
- `CreationSummary({ durationLabel, estimatedCredits, balance, onNext })`.

- [ ] **Step 1: Write interaction verification before components**

The Playwright script must assert:

- exactly three creation-type buttons and default `aria-pressed="true"` on short-drama narration;
- clicking translation changes the selected button;
- choosing two synthetic video files appends two rows;
- removing a row reduces the count and reindexes visible row numbers;
- choosing and removing an SRT file updates the subtitle region;
- clicking next shows `参数设置功能建设中` and stays on `/dashboard/create`;
- no XHR or fetch request is emitted by file or next-step interactions.

- [ ] **Step 2: Run create verification and verify RED**

```bash
node scripts/verify-create.mjs
```

Expected: FAIL because the creation controls do not exist.

- [ ] **Step 3: Implement minimal local-only behavior**

Use three demo rows from `createData.js` with stable fields:

```js
{ id, name, durationSeconds, durationLabel, subtitleStatus, tone, thumbnail }
```

For selected browser files, create stable local row objects from `File.name`, `File.size`, and `File.lastModified`; do not upload them or create network requests. Validate video extensions and the displayed 5GB limit, and validate `.srt` plus the displayed 50MB limit. Surface invalid selections through the existing toast.

Calculate total seconds with `reduce`, format as `MM:SS`, and derive demo credits from current rows with a deterministic local-only function. Preserve the initial reference values `08:42` and `87` for the three demo rows.

- [ ] **Step 4: Run verification and verify GREEN**

```bash
node scripts/verify-create.mjs
```

Expected: all route, type, file, subtitle, summary, toast, and no-network checks pass.

---

### Task 3: High-fidelity desktop and responsive styling

**Files:**
- Create: `docs/web/homepage-prototype/src/styles/create.css`
- Modify: `docs/web/homepage-prototype/src/main.jsx`
- Modify: `docs/web/homepage-prototype/src/pages/CreatePage.jsx`
- Modify: `docs/web/homepage-prototype/scripts/verify-create.mjs`

**Interfaces:**
- Consumes the `create-*` class contract emitted by Task 2.
- Produces a two-column desktop workspace and a one-column responsive workspace.

- [ ] **Step 1: Add geometry assertions before CSS**

At `1487 × 1058`, assert sidebar width remains in the existing dashboard range, main content starts after the sidebar, type cards share one row, upload content is wider than summary, no horizontal overflow exists, and mobile navigation is hidden. At `390 × 844`, assert the desktop sidebar is hidden, bottom navigation is visible, type cards and summary are stacked, and no horizontal overflow exists.

- [ ] **Step 2: Run geometry verification and verify RED**

```bash
node scripts/verify-create.mjs
```

Expected: FAIL because the minimal structure lacks the target layout.

- [ ] **Step 3: Implement page-specific CSS**

Reuse dashboard CSS variables. Build all surfaces with borders, gradients, shadows, icons, and CSS layout only. Do not use the reference image or a URL background. Match the source hierarchy: title, three type cards, dashed upload surface with file rows, optional subtitle card, right-side summary, and bottom save message.

Use breakpoints aligned with the dashboard shell: desktop layout above `1024px`, reduced two-column layout near `1200px`, and stacked mobile layout at `1024px` and below.

- [ ] **Step 4: Run verification and verify GREEN**

```bash
node scripts/verify-create.mjs
```

Expected: desktop and mobile geometry assertions pass without console, page, request, or overflow errors.

---

### Task 4: Build integration, anti-cheat scan, screenshots, and regression

**Files:**
- Create: `docs/web/homepage-prototype/scripts/capture-create.mjs`
- Modify: `docs/web/homepage-prototype/package.json`
- Modify: `docs/web/homepage-prototype/scripts/verify-create.mjs`

**Interfaces:**
- Produces npm commands `verify:create` and `screenshot:create`.
- Produces screenshot `docs/web/homepage-prototype/artifacts/create-page/create-desktop-1487.png`.

- [ ] **Step 1: Add anti-cheat source scan**

Scan `CreatePage.jsx`, `src/components/create`, `src/styles/create.css`, and `src/data/createData.js` for the target filename, `data:image`, `base64`, canvas/drawImage, `background-image: url(`, and SVG embedded image patterns. Expected result is zero violations.

- [ ] **Step 2: Run full verification**

```bash
npm run build
npm run verify:routing
npm run verify:dashboard
npm run verify:create
```

Expected: all commands exit `0`.

- [ ] **Step 3: Capture and visually compare**

```bash
npm run screenshot:create
```

Inspect the generated `1487 × 1058` screenshot against `docs/web/prototypes/b-style/05-new-creation-desktop.png`. Correct visible spacing, typography, density, clipping, and alignment defects, then repeat verification.

- [ ] **Step 4: Run final source and diff checks**

```bash
git diff --check
grep -RInE '05-new-creation-desktop|data:image|base64|<canvas|drawImage|background-image[[:space:]]*:[[:space:]]*url' \
  docs/web/homepage-prototype/src/pages/CreatePage.jsx \
  docs/web/homepage-prototype/src/components/create \
  docs/web/homepage-prototype/src/styles/create.css \
  docs/web/homepage-prototype/src/data/createData.js
```

Expected: `git diff --check` exits `0`; grep has no matches.

- [ ] **Step 5: Review the final diff without committing unrelated changes**

Confirm every changed file belongs to the create-page feature or is an intentional entry-point change. Do not stage or commit the pre-existing dirty homepage files as part of this task.
