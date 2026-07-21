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

