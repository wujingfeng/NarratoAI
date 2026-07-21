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

