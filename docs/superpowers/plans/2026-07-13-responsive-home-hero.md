# Responsive Home Hero Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a responsive, interactive, structurally editable React reproduction of the selected home Hero and Demo teaser visual.

**Architecture:** Keep the work in the isolated `docs/web/home-hero-responsive-prototype/` Vite app. Compose the page from focused React components, centralize visual behavior in `src/styles.css`, and enforce interaction and anti-paste-through requirements with Vitest and a Node verification script.

**Tech Stack:** React 19, Vite 6, CSS Grid/Flex/media queries, Phosphor Icons, Vitest, Testing Library, Playwright capture script.

## Global Constraints

- The only visual target is `docs/web/prototypes/b-style/01-home-hero-desktop.png` at 1487 × 1058.
- Do not inspect or copy `docs/web/homepage-prototype/` source code.
- Do not embed the reference, crops, `data:image`, base64, canvas output, inline SVG, SVG bitmap fills, or CSS screenshot backgrounds.
- Public content images are limited to the seven existing files under `docs/web/home-hero-responsive-prototype/public/assets/`.
- Use `@phosphor-icons/react` for interface icons.
- The page must have natural height and no horizontal overflow at 1487 × 1058, 1024 × 768, 768 × 1024, and 390 × 844.
- Do not claim design QA passed before the parent agent completes same-viewport browser comparison.

---

### Task 1: Establish the isolated app and interaction contract

**Files:**
- Modify: `docs/web/home-hero-responsive-prototype/package.json`
- Modify: `docs/web/home-hero-responsive-prototype/vite.config.mjs`
- Modify: `docs/web/home-hero-responsive-prototype/src/App.test.jsx`
- Modify: `docs/web/home-hero-responsive-prototype/src/test/setup.js`

**Interfaces:**
- Consumes: React entry point at `src/main.jsx`.
- Produces: `npm test`, `npm run build`, `npm run verify:no-paste`, and `npm run capture` commands plus a jsdom interaction contract.

- [ ] **Step 1: Confirm the isolated command surface**

  Run: `cd docs/web/home-hero-responsive-prototype && node -e "const p=require('./package.json'); console.log(Object.keys(p.scripts).sort().join(','))"`

  Expected: output contains `build,capture,dev,preview,test,verify:no-paste`.

- [ ] **Step 2: Run the interaction suite before implementation**

  Run: `cd docs/web/home-hero-responsive-prototype && npm test`

  Expected: tests fail against missing or incomplete menu, toast, tool selection, playback, or scroll behavior, establishing the RED state.

- [ ] **Step 3: Keep Vite browser-compatible**

  Configure `vite.config.mjs` with React, jsdom setup, `server.host: "0.0.0.0"`, and `server.allowedHosts: ["terminal.local"]`.

  Run: `cd docs/web/home-hero-responsive-prototype && npm run build`

  Expected: Vite exits with code 0 and creates `dist/index.html` plus hashed assets.

### Task 2: Implement page composition and accessible interactions

**Files:**
- Modify: `docs/web/home-hero-responsive-prototype/src/App.jsx`
- Modify: `docs/web/home-hero-responsive-prototype/src/components/SiteHeader.jsx`
- Modify: `docs/web/home-hero-responsive-prototype/src/components/HeroCopy.jsx`
- Modify: `docs/web/home-hero-responsive-prototype/src/components/Toast.jsx`
- Modify: `docs/web/home-hero-responsive-prototype/src/components/DemoTeaser.jsx`

**Interfaces:**
- Consumes: `SiteHeader`, `HeroCopy`, `WorkbenchPanel`, `BenefitStrip`, `DemoTeaser`, and `Toast` React components.
- Produces: `App()` with `scrollTo(ref)`, `openLogin()`, `startCreating()`, mobile menu state, and transient toast state.

- [ ] **Step 1: Wire real section targets and actions**

  Make product navigation call `workbenchRef.current.scrollIntoView`, make case actions call `demoRef.current.scrollIntoView`, and close the mobile menu after navigation.

  Run: `cd docs/web/home-hero-responsive-prototype && npm test -- --run`

  Expected: the scroll test observes exactly two `scrollIntoView` calls for product and case actions.

- [ ] **Step 2: Add menu and feedback state**

  Implement `aria-expanded`, `aria-controls`, Escape dismissal, login feedback, creation feedback, `role="status"`, and a 3600ms toast timeout.

  Run: `cd docs/web/home-hero-responsive-prototype && npm test -- --run`

  Expected: menu and feedback tests pass with no accessibility-query failures.

### Task 3: Build the workbench from real components

**Files:**
- Modify: `docs/web/home-hero-responsive-prototype/src/components/WorkbenchPanel.jsx`
- Modify: `docs/web/home-hero-responsive-prototype/src/components/AnalysisFlow.jsx`
- Modify: `docs/web/home-hero-responsive-prototype/src/components/VideoPreview.jsx`
- Modify: `docs/web/home-hero-responsive-prototype/src/components/ToolCards.jsx`
- Modify: `docs/web/home-hero-responsive-prototype/src/components/Timeline.jsx`
- Modify: `docs/web/home-hero-responsive-prototype/src/components/BenefitStrip.jsx`

**Interfaces:**
- Consumes: `activeTool: "commentary" | "translation" | "remix"` and `playing: boolean` local state.
- Produces: `WorkbenchPanel()` with `ToolCards({ activeTool, onSelect })`, `VideoPreview({ playing, onToggle })`, semantic analysis steps, real waveform bars, and real timeline tracks.

- [ ] **Step 1: Implement selectable tool cards**

  Render three buttons inside `role="group" aria-label="创作工具"`; set `aria-pressed` from `activeTool`; announce `${activeName}已选中`.

  Run: `cd docs/web/home-hero-responsive-prototype && npm test -- --run`

  Expected: selecting 视频翻译 changes its pressed state to true and 短剧解说 to false.

- [ ] **Step 2: Implement video and timeline states**

  Toggle the preview control label between 播放预览 and 暂停预览. Render timeline labels, clips, copy blocks, cyan voice bars, orange music bars, and a playhead as DOM elements.

  Run: `cd docs/web/home-hero-responsive-prototype && npm test -- --run`

  Expected: the playback test finds 正在预览 after activating the play control.

### Task 4: Reproduce the visual hierarchy responsively

**Files:**
- Modify: `docs/web/home-hero-responsive-prototype/src/styles.css`

**Interfaces:**
- Consumes: component class names emitted by Tasks 2 and 3.
- Produces: desktop overlap, layered workbench perspective, grid/reflection effects, responsive stacks, mobile simplification, focus treatment, and reduced-motion treatment.

- [ ] **Step 1: Implement the desktop reference composition**

  Use `clamp()`, Grid, Flex, positioned overlap, `perspective(1500px) rotateX(5deg) rotateY(-8deg) rotateZ(-3deg)`, layered borders, CSS gradients, shadows, and pseudo-elements. Do not use CSS `url()`.

  Run: `cd docs/web/home-hero-responsive-prototype && npm run build`

  Expected: build exits 0 and CSS is emitted in `dist/assets/`.

- [ ] **Step 2: Add responsive breakpoints**

  Keep overlap at `>=1280px`, compact the double-column layout at `1024–1279px`, stack below `1024px`, and hide credits plus timeline below `768px`. Keep 390px gutters at 20–24px with no fixed screenshot canvas.

  Run: `cd docs/web/home-hero-responsive-prototype && grep -nE '@media.*(1279|1023|767|768|1280)' src/styles.css`

  Expected: output identifies desktop, tablet, and mobile breakpoint rules.

- [ ] **Step 3: Add accessible motion behavior**

  Add float and glow breathing animations, visible `:focus-visible` outlines, and a `prefers-reduced-motion: reduce` override that disables animation and smooth scrolling.

  Run: `cd docs/web/home-hero-responsive-prototype && grep -nE 'focus-visible|prefers-reduced-motion' src/styles.css`

  Expected: both focus and reduced-motion rules are present.

### Task 5: Enforce anti-paste-through and responsive capture

**Files:**
- Create: `docs/web/home-hero-responsive-prototype/scripts/verify-no-paste-through.mjs`
- Create: `docs/web/home-hero-responsive-prototype/scripts/capture.mjs`
- Modify: `docs/web/home-hero-responsive-prototype/package.json`

**Interfaces:**
- Consumes: `src/`, `public/`, and a running preview at `http://127.0.0.1:4177`.
- Produces: deterministic policy verification and screenshots with browser diagnostics in `artifacts/screenshots/`.

- [ ] **Step 1: Verify source and public assets**

  Scan source for reference/baseline paths, image data URIs, base64, canvas APIs, inline SVG, non-whitelisted image references, and CSS `url()`. Require the exact seven-file `public/` allowlist while permitting CSS gradients.

  Run: `cd docs/web/home-hero-responsive-prototype && npm run verify:no-paste`

  Expected: `No-paste-through verification passed` and exit code 0.

- [ ] **Step 2: Capture the four required viewports**

  With the app available on port 4177 and Playwright installed, run: `cd docs/web/home-hero-responsive-prototype && npm run capture`

  Expected: four PNG files and `diagnostics.json` are written under `artifacts/screenshots/`; the command reports no console warnings/errors, page errors, or failed requests.

### Task 6: Complete build verification and browser QA handoff

**Files:**
- Create: `docs/web/home-hero-responsive-prototype/design-qa.md`
- Create: `docs/superpowers/specs/2026-07-13-responsive-home-hero-design.md`
- Create: `docs/superpowers/plans/2026-07-13-responsive-home-hero.md`

**Interfaces:**
- Consumes: test, build, anti-paste, capture, and parent-agent same-viewport browser evidence.
- Produces: an auditable design QA status and final implementation documentation.

- [ ] **Step 1: Run fresh automated verification**

  Run: `cd docs/web/home-hero-responsive-prototype && npm test && npm run build && npm run verify:no-paste`

  Expected: all five Vitest cases pass, Vite exits 0, and anti-paste verification exits 0.

- [ ] **Step 2: Record the browser gate honestly**

  Keep `design-qa.md` at `final result: blocked` until the parent agent compares the rendered prototype and the reference at 1487 × 1058 and inspects 1024 × 768, 768 × 1024, and 390 × 844.

  Run: `cd docs/web/home-hero-responsive-prototype && head -n 5 design-qa.md`

  Expected: the document visibly reports `final result: blocked` before parent-agent browser approval.

- [ ] **Step 3: Confirm the implementation scope**

  Run: `git status --short -- docs/web/home-hero-responsive-prototype docs/superpowers/specs/2026-07-13-responsive-home-hero-design.md docs/superpowers/plans/2026-07-13-responsive-home-hero.md`

  Expected: only the isolated prototype and the two responsive-home-hero documents appear in this feature scope.
