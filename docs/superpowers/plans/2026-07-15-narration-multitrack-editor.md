# Narration Multitrack Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a high-fidelity, desktop-first, four-track narration editor at `/dashboard/narration/editor` with real local media preview, Wavesurfer regions, dnd-kit dragging, and rectangle selection.

**Architecture:** Add an isolated narration-editor feature that owns seconds-based timeline state and renders a semantic DOM/SVG editor workbench. A native video element and two Wavesurfer instances consume one global playhead; drag, resize, region, and selection actions update the same reducer. The existing analysis page navigates into the new workbench.

**Tech Stack:** React 19, Vite 6, React Router 7, `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities`, `wavesurfer.js` with Regions plugin, native `<video>`, Playwright scripts, CSS.

## Global Constraints

- The app root is `docs/web/homepage-prototype`; add route `/dashboard/narration/editor`.
- Use exactly four fixed tracks: `video`, `script`, `voice`, `bgm`; no free track creation or cross-track reordering.
- Persist editing coordinates as seconds; derive pixels only with `left = start * pixelsPerSecond`.
- Copy only user-approved media into `public/media/narration-editor/`: three specified MP4 files, one MP3, and one SRT.
- Use Wavesurfer for real MP3 waveforms and Regions for voice/BGM audio ranges.
- Use dnd-kit for draggable clips and a DOM rectangle for Shift multi-selection; clips snap to seconds/adjacent edges, have minimum duration, and cannot overlap on a track.
- The prototype has no backend persistence, TTS, multi-source production mixing, or actual MP4 export; export is UI feedback only.
- Never embed/reference the design screenshot in runtime UI: no image slices, `data:image`, base64, screenshot canvas, SVG bitmap, or `background-image` screenshot. Real approved video frames and real audio waveform are permitted media assets.
- Full layout at `>=1280px`; compact inspector at `1024–1279px`; desktop-only read-only guidance below `1024px`.

---

## File Structure

- `src/pages/NarrationEditorPage.jsx` — route page and feature composition.
- `src/features/narration-editor/editor-data.js` — typed-like JSDoc model, media paths, SRT parsing, initial clips.
- `src/features/narration-editor/editor-reducer.js` — deterministic playhead, move/trim, select, zoom, undo helpers.
- `src/features/narration-editor/NarrationEditor.jsx` — shell, preview, inspector, state wiring.
- `src/features/narration-editor/Timeline.jsx` — ruler, scroll/zoom, dnd-kit clips and selection rectangle.
- `src/features/narration-editor/WaveformTrack.jsx` / `useWaveSurfer.js` — Wavesurfer lifecycle and region-to-state bridge.
- `src/styles/narration-editor.css` — responsive structured UI styles.
- `scripts/verify-narration-editor.mjs` / `scripts/capture-narration-editor.mjs` — focused browser assertions and QA screenshot.

### Task 1: Add assets, dependencies, deterministic editor data

**Files:**
- Modify: `docs/web/homepage-prototype/package.json`, `docs/web/homepage-prototype/package-lock.json`
- Create: `docs/web/homepage-prototype/public/media/narration-editor/{古墓迷宫震全球1.mp4,古墓迷宫震全球2.mp4,古墓迷宫震全球3.mp4,0e5bf3db017e0e593c4eef4144d7c68a.mp3,古墓迷宫震全球3.srt}`
- Create: `docs/web/homepage-prototype/src/features/narration-editor/editor-data.js`
- Test: `docs/web/homepage-prototype/scripts/verify-narration-editor.mjs`

**Interfaces:**
- Produces `parseSrt(text): Array<{start:number,end:number,text:string}>`, `findCue(cues, seconds): Cue|null`, and `INITIAL_CLIPS: TimelineClip[]`.
- `TimelineClip` is `{id:string,trackId:'video'|'script'|'voice'|'bgm',start:number,duration:number,sourceStart?:number,assetId?:string,text?:string,regionId?:string}`.

- [ ] **Step 1: Write the failing test**

```js
import assert from 'node:assert/strict';
import { parseSrt, findCue } from '../src/features/narration-editor/editor-data.js';
const cues = parseSrt('1\n00:00:01,000 --> 00:00:03,000\n古墓入口\n');
assert.deepEqual(cues, [{ start: 1, end: 3, text: '古墓入口' }]);
assert.equal(findCue(cues, 2).text, '古墓入口');
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node scripts/verify-narration-editor.mjs`  
Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `editor-data.js`.

- [ ] **Step 3: Write minimal implementation**

```js
export function parseSrt(text) {
  return [...text.matchAll(/\d+\s+([\d:,]+) --> ([\d:,]+)\s+([^\n]+(?:\n(?!\n)[^\n]+)*)/g)]
    .map(([, start, end, body]) => ({ start: toSeconds(start), end: toSeconds(end), text: body.replace(/\n/g, ' ') }));
}
export const findCue = (cues, seconds) => cues.find((cue) => cue.start <= seconds && seconds < cue.end) ?? null;
```

Add exact dependencies `wavesurfer.js`, `@dnd-kit/core`, `@dnd-kit/sortable`, and `@dnd-kit/utilities`; copy approved files under the stated public path and define their `/media/narration-editor/...` URLs in `editor-data.js`.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm install && node scripts/verify-narration-editor.mjs`  
Expected: PASS and media URLs resolve under `/media/narration-editor/`.

- [ ] **Step 5: Commit**

```bash
git add package.json package-lock.json public/media/narration-editor src/features/narration-editor/editor-data.js scripts/verify-narration-editor.mjs
git commit -m "feat: add narration editor media data"
```

### Task 2: Add route, semantic workbench, and reducer

**Files:**
- Modify: `docs/web/homepage-prototype/src/App.jsx`, `docs/web/homepage-prototype/src/pages/NarrationAnalysisPage.jsx`
- Create: `docs/web/homepage-prototype/src/pages/NarrationEditorPage.jsx`, `docs/web/homepage-prototype/src/features/narration-editor/editor-reducer.js`, `docs/web/homepage-prototype/src/features/narration-editor/NarrationEditor.jsx`, `docs/web/homepage-prototype/src/styles/narration-editor.css`
- Modify: `docs/web/homepage-prototype/scripts/verify-routing.mjs`, `docs/web/homepage-prototype/scripts/verify-narration-editor.mjs`

**Interfaces:**
- Consumes `INITIAL_CLIPS` from `editor-data.js`.
- Produces `editorReducer(state, action)` for `{type:'seek'|'select'|'moveClip'|'trimClip'|'setZoom'}` and `NarrationEditor()` with `data-testid="narration-editor"`.
- `NarrationAnalysisPage` navigates via `navigate('/dashboard/narration/editor')`.

- [ ] **Step 1: Write the failing test**

```js
await page.goto(`${baseUrl}/dashboard/narration/editor`);
await page.getByTestId('narration-editor').waitFor();
for (const id of ['video', 'script', 'voice', 'bgm']) await page.getByTestId(`track-${id}`).waitFor();
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run build && node scripts/verify-routing.mjs`  
Expected: FAIL because `/dashboard/narration/editor` resolves to `NotFoundPage`.

- [ ] **Step 3: Write minimal implementation**

```jsx
<Route path="/dashboard/narration/editor" element={<NarrationEditorPage />} />
// reducer move action returns a new clip with start: Math.max(0, action.start)
```

Render real header, clip sidebar, preview container, inspector, and four `<section data-testid={`track-${id}`}>` elements; import `narration-editor.css`. Make the analysis CTA navigate to the route.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run build && node scripts/verify-routing.mjs && node scripts/verify-narration-editor.mjs`  
Expected: PASS; the editor and all four track test IDs exist.

- [ ] **Step 5: Commit**

```bash
git add src/App.jsx src/pages/NarrationAnalysisPage.jsx src/pages/NarrationEditorPage.jsx src/features/narration-editor src/styles/narration-editor.css scripts/verify-routing.mjs scripts/verify-narration-editor.mjs
git commit -m "feat: add narration editor workbench"
```

### Task 3: Implement synchronized preview, ruler, clips, and subtitles

**Files:**
- Create: `docs/web/homepage-prototype/src/features/narration-editor/Timeline.jsx`, `docs/web/homepage-prototype/src/features/narration-editor/PreviewPlayer.jsx`
- Modify: `docs/web/homepage-prototype/src/features/narration-editor/NarrationEditor.jsx`, `docs/web/homepage-prototype/src/styles/narration-editor.css`, `docs/web/homepage-prototype/scripts/verify-narration-editor.mjs`

**Interfaces:**
- Consumes `playhead`, `pixelsPerSecond`, `clips`, `dispatch`, `cues`.
- Produces `Timeline({state,dispatch})` and `PreviewPlayer({state,dispatch,cues})`.
- `Timeline` dispatches `{type:'seek', seconds:number}`; player maps `clip.sourceStart + playhead - clip.start` to `video.currentTime`.

- [ ] **Step 1: Write the failing test**

```js
await page.getByTestId('playhead').click({ position: { x: 240, y: 4 } });
await expect(page.getByTestId('preview-video')).toHaveJSProperty('currentTime', 2);
await expect(page.getByTestId('subtitle')).toContainText('古墓');
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node scripts/verify-narration-editor.mjs`  
Expected: FAIL because `playhead`, `preview-video`, and `subtitle` are absent.

- [ ] **Step 3: Write minimal implementation**

```jsx
const sourceTime = clip ? clip.sourceStart + state.playhead - clip.start : 0;
<video data-testid="preview-video" ref={videoRef} onTimeUpdate={(e) => dispatch({type:'seek', seconds:e.currentTarget.currentTime})} />
<div data-testid="playhead" style={{ transform: `translateX(${state.playhead * state.pixelsPerSecond}px)` }} />
<div data-testid="subtitle">{findCue(cues, state.playhead)?.text}</div>
```

Render a semantic ruler and clips from `state.clips`; use button/keyboard seek controls, wheel zoom around the pointer time, and horizontal scroll. Do not use canvas.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run build && node scripts/verify-narration-editor.mjs`  
Expected: PASS; seek moves playhead, video time, and subtitle together.

- [ ] **Step 5: Commit**

```bash
git add src/features/narration-editor/Timeline.jsx src/features/narration-editor/PreviewPlayer.jsx src/features/narration-editor/NarrationEditor.jsx src/styles/narration-editor.css scripts/verify-narration-editor.mjs
git commit -m "feat: synchronize narration timeline preview"
```

### Task 4: Add dnd-kit clip movement, trim handles, and rectangle selection

**Files:**
- Create: `docs/web/homepage-prototype/src/features/narration-editor/timeline-geometry.js`
- Modify: `docs/web/homepage-prototype/src/features/narration-editor/editor-reducer.js`, `docs/web/homepage-prototype/src/features/narration-editor/Timeline.jsx`, `docs/web/homepage-prototype/src/styles/narration-editor.css`, `docs/web/homepage-prototype/scripts/verify-narration-editor.mjs`

**Interfaces:**
- Produces `snapStart({start,duration,neighbors}):number`, `intersects(rect, clipRect):boolean`, `selectedIdsForRect(rect, clips):string[]`.
- `Timeline` dispatches `{type:'moveClip',id,start}` and `{type:'select',ids,append:boolean}`.
- `editorReducer` rejects overlap and enforces a `0.5` second minimum duration.

- [ ] **Step 1: Write the failing test**

```js
import { selectedIdsForRect, snapStart } from '../src/features/narration-editor/timeline-geometry.js';
assert.deepEqual(selectedIdsForRect({left:0,right:150,top:0,bottom:80}, [{id:'a',left:20,right:100,top:10,bottom:50}]), ['a']);
assert.equal(snapStart({start:1.92,duration:1,neighbors:[{end:2}]}), 2);
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node scripts/verify-narration-editor.mjs`  
Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `timeline-geometry.js`.

- [ ] **Step 3: Write minimal implementation**

```js
export const intersects = (a,b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
export const selectedIdsForRect = (rect, clips) => clips.filter((clip) => intersects(rect, clip)).map((clip) => clip.id);
export const snapStart = ({start, neighbors}) => neighbors.some(({end}) => Math.abs(start-end) < .1) ? neighbors.find(({end}) => Math.abs(start-end) < .1).end : Math.round(start);
```

Use `DndContext`, pointer sensor, and `useDraggable` per clip; emit `moveClip` on drag end only. Add DOM pointer-down/move/up selection rectangle and Shift append. Add left/right trim buttons with `aria-label="Trim start"`/`"Trim end"`; prevent overlap/minimum-duration violations in the reducer.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run build && node scripts/verify-narration-editor.mjs`  
Expected: PASS; geometry tests pass and Playwright drag/Shift-box-select assertions report selected clip IDs.

- [ ] **Step 5: Commit**

```bash
git add src/features/narration-editor/timeline-geometry.js src/features/narration-editor/editor-reducer.js src/features/narration-editor/Timeline.jsx src/styles/narration-editor.css scripts/verify-narration-editor.mjs
git commit -m "feat: add timeline drag trim and selection"
```

### Task 5: Add Wavesurfer regions, responsive polish, and visual QA

**Files:**
- Create: `docs/web/homepage-prototype/src/features/narration-editor/useWaveSurfer.js`, `docs/web/homepage-prototype/src/features/narration-editor/WaveformTrack.jsx`, `docs/web/homepage-prototype/scripts/capture-narration-editor.mjs`
- Modify: `docs/web/homepage-prototype/src/features/narration-editor/NarrationEditor.jsx`, `docs/web/homepage-prototype/src/features/narration-editor/Timeline.jsx`, `docs/web/homepage-prototype/src/styles/narration-editor.css`, `docs/web/homepage-prototype/scripts/verify-narration-editor.mjs`

**Interfaces:**
- Produces `useWaveSurfer({container,url,regions,onSeek,onRegionUpdate}): {seekTo(seconds):void,destroy():void}`.
- `WaveformTrack` consumes `trackId:'voice'|'bgm'`, `clips`, and global `playhead`; it dispatches `{type:'seek',seconds}` and `{type:'moveClip',id,start}` after region events.

- [ ] **Step 1: Write the failing test**

```js
await page.getByTestId('waveform-voice').waitFor();
await page.getByTestId('waveform-bgm').waitFor();
await expect(page.locator('[data-region-id="voice-1"]')).toBeVisible();
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node scripts/verify-narration-editor.mjs`  
Expected: FAIL because waveform and region test IDs do not exist.

- [ ] **Step 3: Write minimal implementation**

```js
const regionsPlugin = RegionsPlugin.create();
const ws = WaveSurfer.create({ container, url, plugins: [regionsPlugin] });
regions.forEach(({id,start,end}) => regionsPlugin.addRegion({id,start,end,drag:true,resize:true}));
ws.on('region-updated', (region) => onRegionUpdate({id:region.id,start:region.start,duration:region.end-region.start}));
ws.on('interaction', (seconds) => onSeek(seconds));
return () => ws.destroy();
```

Create one voice and one BGM waveform with real MP3 URL. Ensure only one Regions plugin instance is registered per Wavesurfer instance in the final implementation. Add desktop/compact/mobile CSS, toolbar toast for save/export, and capture script that writes only to an artifacts path.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run build && node scripts/verify-narration-editor.mjs && node scripts/capture-narration-editor.mjs && rg -n "09-narration-editor-overview-desktop|data:image|base64|<canvas|background-image" src public`  
Expected: build and scripts PASS; `rg` has no runtime reference to the design screenshot, data URL, base64, canvas, or screenshot background.

- [ ] **Step 5: Commit**

```bash
git add src/features/narration-editor/useWaveSurfer.js src/features/narration-editor/WaveformTrack.jsx src/features/narration-editor/NarrationEditor.jsx src/features/narration-editor/Timeline.jsx src/styles/narration-editor.css scripts/verify-narration-editor.mjs scripts/capture-narration-editor.mjs
git commit -m "feat: add narration waveform regions"
```

## Final verification

- [ ] Run `cd docs/web/homepage-prototype && npm run build && node scripts/verify-routing.mjs && node scripts/verify-narration-editor.mjs && node scripts/capture-narration-editor.mjs` — all commands exit `0`.
- [ ] Run `ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1 public/media/narration-editor/*.mp4 public/media/narration-editor/*.mp3` — every approved media asset prints a duration.
- [ ] At 1440px, inspect the generated QA screenshot: header, sidebar, preview, inspector, four colored tracks, ruler, real waveforms, selection and playhead are complete; after removing the reference screenshot, no page content is lost.
- [ ] Run `rg -n "09-narration-editor-overview-desktop|data:image|base64|<canvas|background-image" src public` — no prohibited reference-image implementation hit.
