# Three.js Hero 3D Visual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Add a transparent Three.js decorative layer to the homepage Hero so the existing editable DOM workbench has a credible 3D panel silhouette, cyan/violet edge rails, reflective cyberpunk floor, and responsive CSS fallback without changing product content or interactions.

**Architecture:** Keep all interactive and readable Hero content in the existing React DOM. Mount one absolute, pointer-transparent Three.js canvas inside Hero; the canvas renders only procedural geometry that is spatially aligned to the DOM workbench. A pure scene runtime owns renderer, camera, panel proxy, neon rails, Reflector, grid, lifecycle, and disposal; a React adapter owns browser capability detection, observers, state attributes, and fallback switching.

**Tech Stack:** React 19, Vite 6, Three.js (single package version), Three.js examples modules (EffectComposer, RenderPass, UnrealBloomPass, OutputPass, Reflector, RoundedBoxGeometry), CSS gradients/custom properties/media queries, Playwright.

## Global Constraints

- Only enhance the Hero in docs/web/homepage-prototype; do not redesign navigation, Demo, pricing, login, or product flows.
- Three.js must be decorative only. The Hero headline, CTA, workbench controls, video preview, cards, timeline, labels, and benefit row remain real, editable DOM.
- Add exactly one new runtime dependency: three. Import all Three helpers from that installed package's three/examples/jsm/ tree; do not add a second post-processing package.
- Do not use TextureLoader, CanvasTexture, VideoTexture, image screenshots, reference-image paths, data:image, base64, bitmap SVG fills, or canvas-rendered screenshots. Do not use CSS background-image: url(...) for Hero visual reconstruction.
- Existing genuine content images may remain DOM img elements. They must never be passed into the WebGL scene.
- The WebGL canvas must be aria-hidden, transparent, pointer-events: none, and lower in stacking order than every interactive DOM element.
- Share one pose data source between DOM and Three: desktop { rotateX: 2, rotateY: -11, rotateZ: -1, depth: 30 }, compact { rotateX: 1.5, rotateY: -8, rotateZ: -0.5, depth: 22 }, tablet { rotateX: 1, rotateY: -5, rotateZ: 0, depth: 14 }, mobile { rotateX: 0.5, rotateY: -3, rotateZ: 0, depth: 8 }.
- Required responsive targets are 1920x1080, 1487x1058, 1200x900, 1024x820, and 390x844. At each target document.documentElement.scrollWidth must be no greater than innerWidth plus one pixel.
- At 390px use DPR 1, no Bloom, a static scene after first paint, low-resolution reflection, and a simplified floor. At reduced motion, offscreen, or hidden-document states, no continuous animation frame may remain active.
- Never use real-time shadows, environment maps, model loading, particles, OrbitControls, pointer-driven camera movement, or per-frame geometry/material creation.
- WebGL initialization failures and ?threeFallback=1 must produce a fully usable CSS fallback instead of a blank Hero.
- Preserve current Hero CTA, scroll-to-Demo, video, tool-card, navigation, and keyboard behavior. The canvas must not receive pointer events or focus.
- Future implementation changes must stay inside the declared Three file set: docs/web/homepage-prototype/package.json, docs/web/homepage-prototype/package-lock.json, docs/web/homepage-prototype/src/components/ThreeHeroScene.jsx, docs/web/homepage-prototype/src/components/heroThreeScene.js, docs/web/homepage-prototype/src/components/HeroSection.jsx, docs/web/homepage-prototype/src/styles/home.css, docs/web/homepage-prototype/scripts/verify-three-hero.mjs, and docs/web/homepage-prototype/design-qa.md.
- The preceding Demo workbench CSS recovery is a separate closure task. Its file scope is explicitly isolated in Task 5 and it must not be imported into the Three scene, pose code, or canvas.
- Do not create Git commits or alter files outside the task-specific paths.

---

## File and Interface Map

| Path | Responsibility |
| --- | --- |
| docs/web/homepage-prototype/package.json | Add the single three dependency and verify:three-hero script. |
| docs/web/homepage-prototype/package-lock.json | Pin the one installed Three.js dependency tree. |
| docs/web/homepage-prototype/src/components/heroThreeScene.js | Export the shared pose model and create/dispose the procedural Three.js runtime. |
| docs/web/homepage-prototype/src/components/ThreeHeroScene.jsx | React adapter: canvas mount, WebGL2 detection, forced fallback, resize/intersection/motion/visibility observers, DOM status attributes. |
| docs/web/homepage-prototype/src/components/HeroSection.jsx | Hold Hero/workbench refs, resolve and publish a shared pose, and mount ThreeHeroScene without changing Hero content. |
| docs/web/homepage-prototype/src/styles/home.css | Align DOM transform to shared CSS variables; style canvas stack, ready state, and CSS-only fallback/responsive behavior. |
| docs/web/homepage-prototype/scripts/verify-three-hero.mjs | Contract, browser, fallback, lifecycle, interaction, responsive, console, and anti-paste verification. |
| docs/web/homepage-prototype/design-qa.md | Record real screenshot paths, runtime states, fallback evidence, design findings, and final conclusion. |
| docs/web/homepage-prototype/src/styles/demo-workbenches.css | Separate prior-round Demo closure only; styles the already-created narration, translation, and remix DOM structures. |
| docs/web/homepage-prototype/scripts/verify-demo.mjs | Separate Demo regression verifier only; validates independent layouts and responsive behavior. |

The Three scene module must expose this stable contract:

    export const HERO_PANEL_POSES = Object.freeze({
      desktop: Object.freeze({ rotateX: 2, rotateY: -11, rotateZ: -1, depth: 30 }),
      compact: Object.freeze({ rotateX: 1.5, rotateY: -8, rotateZ: -0.5, depth: 22 }),
      tablet: Object.freeze({ rotateX: 1, rotateY: -5, rotateZ: 0, depth: 14 }),
      mobile: Object.freeze({ rotateX: 0.5, rotateY: -3, rotateZ: 0, depth: 8 }),
    });

    export function resolveHeroPose(viewportWidth) {
      if (viewportWidth >= 1261) return "desktop";
      if (viewportWidth >= 1101) return "compact";
      if (viewportWidth >= 768) return "tablet";
      return "mobile";
    }

    export function getHeroPoseStyle(poseName) {
      const pose = HERO_PANEL_POSES[poseName];
      return {
        "--hero-panel-rotate-x": pose.rotateX + "deg",
        "--hero-panel-rotate-y": pose.rotateY + "deg",
        "--hero-panel-rotate-z": pose.rotateZ + "deg",
        "--hero-panel-depth": pose.depth + "px",
      };
    }

    export function createHeroThreeScene({
      mountElement,
      heroElement,
      workbenchElement,
      poseName,
      reducedMotion,
      onSignal,
    }) {
      // Returns { resize, setPose, setMotionMode, setVisible, renderOnce, dispose }.
    }

The React adapter must expose this contract:

    <ThreeHeroScene
      heroRef={heroRef}
      workbenchRef={workbenchRef}
      poseName={poseName}
    />

It must render one decorative container with these machine-readable attributes:

    <div
      className="three-hero-scene"
      aria-hidden="true"
      data-three-state="loading"
      data-three-reflector="pending"
      data-three-neon-rails="pending"
      data-three-loop="paused"
    />

Valid final values are ready/fallback for data-three-state, ready/unsupported for reflector and neon rails, and running/paused/static for data-three-loop.

### Task 1: Establish the Three dependency and an executable RED verification contract

**Files:**
- Modify: docs/web/homepage-prototype/package.json
- Modify: docs/web/homepage-prototype/package-lock.json
- Create: docs/web/homepage-prototype/scripts/verify-three-hero.mjs

**Interfaces:**
- Consumes: the current Vite homepage at BASE_URL or http://127.0.0.1:4173/.
- Produces: npm run verify:three-hero and a --contract mode that can fail before Vite compiles the unrelated missing Demo CSS import.

- [ ] **Step 1: Write the failing source contract before adding runtime code**

Create scripts/verify-three-hero.mjs with a --contract path that uses node:fs/promises and exits non-zero when the dependency, runtime module, React adapter, mount point, or shared pose names are absent. Its initial checks must include the following concrete assertions:

    const requiredFiles = [
      "src/components/heroThreeScene.js",
      "src/components/ThreeHeroScene.jsx",
    ];

    const requiredHeroTokens = [
      "ThreeHeroScene",
      "data-hero-pose",
      "getHeroPoseStyle",
      "workbenchRef",
    ];

    const prohibitedTokens = [
      "TextureLoader",
      "CanvasTexture",
      "VideoTexture",
      "data:image",
      "base64",
      "codex-clipboard",
      "background-image: url(",
    ];

    check(packageJson.dependencies?.three, "package.json must declare the only Three dependency");
    check(sourceExists("src/components/heroThreeScene.js"), "heroThreeScene.js must exist");
    check(sourceExists("src/components/ThreeHeroScene.jsx"), "ThreeHeroScene.jsx must exist");

Run:

    cd docs/web/homepage-prototype
    node scripts/verify-three-hero.mjs --contract

Expected RED: exit code 1 and messages stating that three, heroThreeScene.js, ThreeHeroScene.jsx, and the Hero mount contract are missing. This command must not depend on a running browser.

- [ ] **Step 2: Add the package command and the single dependency**

Add this script to package.json:

    "verify:three-hero": "node scripts/verify-three-hero.mjs"

Install the dependency with the lockfile update:

    cd docs/web/homepage-prototype
    npm install --save-exact three

Verify that only one version is resolved:

    node -e "const p=require('./package-lock.json'); const keys=Object.keys(p.packages||{}).filter((key)=>key.endsWith('/three')); console.log({root:p.packages[''].dependencies.three, entries:keys, resolved:p.packages['node_modules/three']?.version})"

Expected: one root dependency named three, one node_modules/three lock entry, and an exact resolved version. No package named postprocessing, @react-three/fiber, or drei is added.

- [ ] **Step 3: Re-run the contract and preserve the intended RED state**

Run:

    cd docs/web/homepage-prototype
    npm run verify:three-hero -- --contract

Expected RED: dependency assertions now pass; the verifier still exits 1 because the two scene files and Hero integration do not exist. Do not make browser assertions pass by weakening the verifier.

### Task 2: Implement the pure Three.js core scene and shared pose model

**Files:**
- Create: docs/web/homepage-prototype/src/components/heroThreeScene.js
- Modify: docs/web/homepage-prototype/scripts/verify-three-hero.mjs

**Interfaces:**
- Consumes: mountElement, heroElement, workbenchElement, poseName, reducedMotion, and onSignal from ThreeHeroScene.
- Produces: HERO_PANEL_POSES, resolveHeroPose, getHeroPoseStyle, and createHeroThreeScene with resize(), setPose(), setMotionMode(), setVisible(), renderOnce(), and dispose().

- [ ] **Step 1: Extend the failing verifier with the core-scene shape checks**

Add the following static contract checks before implementing the module:

    const requiredRuntimeExports = [
      "HERO_PANEL_POSES",
      "resolveHeroPose",
      "getHeroPoseStyle",
      "createHeroThreeScene",
    ];

    const requiredRuntimeTokens = [
      "WebGLRenderer",
      "PerspectiveCamera",
      "RoundedBoxGeometry",
      "Reflector",
      "GridHelper",
      "EffectComposer",
      "RenderPass",
      "UnrealBloomPass",
      "OutputPass",
      "forceContextLoss",
      "dispose",
    ];

    for (const token of prohibitedTokens) {
      check(!runtimeSource.includes(token), "Forbidden raster reconstruction token: " + token);
    }

Run:

    cd docs/web/homepage-prototype
    npm run verify:three-hero -- --contract

Expected RED: failures identify the missing runtime module and all required exports. No browser launch is required at this stage.

- [ ] **Step 2: Implement the shared pose and coordinate helpers**

In heroThreeScene.js, implement the exact exported HERO_PANEL_POSES, resolveHeroPose, and getHeroPoseStyle contract above. Use the following breakpoints so DOM and scene behavior map directly to the specified viewport targets:

    desktop: viewportWidth >= 1261
    compact: viewportWidth >= 1101 and < 1261
    tablet: viewportWidth >= 768 and < 1101
    mobile: viewportWidth < 768

Add an internal mapWorkbenchRectToScene(workbenchRect, heroRect, camera) helper that:
1. converts the workbench center from page pixels to hero-local pixels;
2. maps workbench width and height into orthographic-equivalent plane sizing derived from the PerspectiveCamera field of view and distance;
3. places the proxy panel at the DOM workbench center and anchors the Reflector directly under its lower edge;
4. recalculates geometry and rail positions only from resize/setPose, never per animation frame.

- [ ] **Step 3: Implement the procedural scene only**

Implement createHeroThreeScene with all of the following concrete behavior:

    const renderer = new WebGLRenderer({
      alpha: true,
      antialias: true,
      powerPreference: "high-performance",
    });
    renderer.setClearColor(0x000000, 0);

- Create a PerspectiveCamera with fixed FOV and deterministic pose-specific position; do not import OrbitControls.
- Create a single rounded thin panel proxy using RoundedBoxGeometry. Use a transparent dark-blue material; do not add text, texture, image, or UI geometry.
- Construct two continuous rounded outline rails from procedural curves/tubes or line geometry: a cyan top/left rail and violet right/bottom rail. Make the top/left rail brighter than the violet rail; use additive blending for the outer glow and disable depthWrite on glow materials.
- Create a horizontal Reflector positioned in the Hero floor zone. It may reflect only the proxy, rails, and grid. It must not render DOM pixels.
- Add a low-opacity dark floor plane, a restrained horizon glow, and a GridHelper or LineSegments grid that reduces density outside desktop quality.
- Build an EffectComposer with RenderPass and OutputPass. Add UnrealBloomPass only when alpha composition remains transparent and quality is not mobile. If the composer creates an opaque rectangle, immediately use renderer.render plus additive emissive rails instead of Bloom.
- Cap DPR at 1.5 for desktop/compact/tablet and 1.0 for mobile. Set reflector resolution no higher than CSS canvas width x height x active DPR, multiplied by 0.75 on mobile.
- Animate only a 600-900ms initial rail fade and a 3.6-5s low-amplitude emissive pulse. No transform, geometry, material, object, or array allocation may occur in the animation loop.
- Call onSignal with ready/unsupported state after the first successful render.

Use a single cleanup routine that cancels RAF, disposes every geometry/material/render target/Reflector/composer pass, removes the canvas, clears references, calls renderer.dispose(), then renderer.forceContextLoss().

- [ ] **Step 4: Verify core implementation and retain the expected integration RED state**

Run:

    cd docs/web/homepage-prototype
    npm run verify:three-hero -- --contract

Expected: all dependency, pose-export, renderer, Reflector, rail, disposal, and anti-raster checks pass. The command remains RED only for the missing ThreeHeroScene React adapter and Hero mount; this is the expected boundary between Tasks 2 and 3.

### Task 3: Integrate the scene into React and align DOM/CSS to the shared pose

**Files:**
- Create: docs/web/homepage-prototype/src/components/ThreeHeroScene.jsx
- Modify: docs/web/homepage-prototype/src/components/HeroSection.jsx
- Modify: docs/web/homepage-prototype/src/styles/home.css
- Modify: docs/web/homepage-prototype/scripts/verify-three-hero.mjs

**Interfaces:**
- Consumes: createHeroThreeScene, resolveHeroPose, and getHeroPoseStyle from heroThreeScene.js.
- Produces: a single canvas container, Hero data-hero-pose attributes, shared CSS variables, DOM workbench refs, and ready-state visual stacking.

- [ ] **Step 1: Add browser assertions before creating the React adapter**

Extend the browser mode of verify-three-hero.mjs with this concrete snapshot collector:

    async function inspectThreeHero(page) {
      return page.evaluate(() => {
        const scene = document.querySelector(".three-hero-scene");
        const canvas = scene?.querySelector("canvas");
        const hero = document.querySelector("#hero");
        const workbench = document.querySelector(".hero-workbench");
        const demo = document.querySelector("#demo");
        return {
          sceneExists: Boolean(scene),
          canvasExists: canvas instanceof HTMLCanvasElement,
          state: scene?.dataset.threeState || "",
          reflector: scene?.dataset.threeReflector || "",
          rails: scene?.dataset.threeNeonRails || "",
          loop: scene?.dataset.threeLoop || "",
          canvasPointerEvents: canvas ? getComputedStyle(canvas).pointerEvents : "",
          canvasBackground: canvas ? getComputedStyle(canvas).backgroundColor : "",
          pageWidth: document.documentElement.scrollWidth,
          viewportWidth: window.innerWidth,
          heroBottom: hero?.getBoundingClientRect().bottom || 0,
          workbench: workbench?.getBoundingClientRect().toJSON(),
          demoTop: demo?.getBoundingClientRect().top || 0,
        };
      });
    }

The normal-path assertions must require sceneExists, canvasExists, state === "ready", reflector === "ready", rails === "ready", canvasPointerEvents === "none", and pageWidth <= viewportWidth + 1.

Run the browser verifier against the currently unintegrated DOM only after a local server is available:

    cd docs/web/homepage-prototype
    (npm run dev -- --host 127.0.0.1 > /tmp/narratoai-three-vite.log 2>&1 & echo $! > /tmp/narratoai-three-vite.pid)
    BASE_URL=http://127.0.0.1:4173 npm run verify:three-hero

Expected RED: the browser reports no .three-hero-scene and no ready-state attributes. If Vite instead reports the known missing demo-workbenches.css import, record that compilation blocker exactly and defer the browser GREEN assertion to Task 6; do not hide it or replace it with an unrelated stylesheet.

- [ ] **Step 2: Implement the React lifecycle adapter**

Create ThreeHeroScene.jsx using refs and effects, not React state for per-frame values.

The component must:
1. render the exact .three-hero-scene status container from the interface map;
2. force fallback when new URLSearchParams(window.location.search).has("threeFallback");
3. test window.WebGL2RenderingContext and create a temporary webgl2 context before calling createHeroThreeScene;
4. set data-three-state to loading before initialization;
5. on success set state=ready, reflector=ready, neonRails=ready, and loop=running or static;
6. on unsupported context, thrown initialization, or forced query fallback, set state=fallback, reflector=unsupported, neonRails=unsupported, and loop=static;
7. create one ResizeObserver for the Hero and workbench, one IntersectionObserver for the Hero, a matchMedia("(prefers-reduced-motion: reduce)") listener, and a document visibilitychange listener;
8. call scene.resize(), scene.setPose(poseName), scene.setMotionMode(reducedMotion), scene.setVisible(isIntersecting && document.visibilityState === "visible"), or scene.renderOnce() from the corresponding observer callback;
9. clean up listeners/observers and call scene.dispose() before effect re-initialization and unmount.

Use a stable onSignal callback that maps the scene signal into the four data attributes without hiding exceptions. Catch initialization errors only at the adapter boundary, call dispose if a partial scene exists, and enter fallback.

- [ ] **Step 3: Publish the pose and refs from HeroSection**

Modify HeroSection.jsx as follows:

    const heroRef = useRef(null);
    const workbenchRef = useRef(null);
    const [poseName, setPoseName] = useState(() => resolveHeroPose(window.innerWidth));

    <section
      id="hero"
      ref={heroRef}
      className="hero-section"
      data-hero-pose={poseName}
      style={getHeroPoseStyle(poseName)}
    >
      <ThreeHeroScene heroRef={heroRef} workbenchRef={workbenchRef} poseName={poseName} />
      ...
      <HeroWorkbench workbenchRef={workbenchRef} />
      ...
    </section>

Add a resize listener that only changes poseName when resolveHeroPose(window.innerWidth) changes. Change HeroWorkbench to accept workbenchRef and apply it to the outer .hero-workbench-wrap element. Keep all existing Hero text, images, buttons, classes, actions, and semantic markup unchanged.

- [ ] **Step 4: Replace duplicate pose ownership in CSS**

In home.css, make .hero-workbench-wrap consume the shared variables:

    transform:
      perspective(1200px)
      rotateY(var(--hero-panel-rotate-y))
      rotateX(var(--hero-panel-rotate-x))
      rotateZ(var(--hero-panel-rotate-z))
      translateY(var(--hero-shift-y))
      scale(var(--hero-scale));

Keep scale and vertical layout adjustments in CSS breakpoints, but remove any angle expressions that independently add/subtract rotations. Replace existing --hero-tilt-x and --hero-tilt-y assignments with shared pose variables published by HeroSection.

Add these stacking rules:

    .three-hero-scene {
      position: absolute;
      z-index: 1;
      inset: 0;
      overflow: hidden;
      pointer-events: none;
      isolation: isolate;
    }

    .three-hero-scene canvas {
      display: block;
      width: 100%;
      height: 100%;
      pointer-events: none;
    }

    .hero-main,
    .benefit-row,
    .hero-scroll-cue {
      position: relative;
      z-index: 3;
    }

When [data-three-state="ready"] is active, reduce the CSS-only pseudo-rail and synthetic reflection opacity so they do not visually stack with the WebGL rails. When state is loading or fallback, retain the existing CSS cyan/violet frame, grid, horizon, and mirror floor as the complete fallback.

- [ ] **Step 5: Re-run the source contract**

Run:

    cd docs/web/homepage-prototype
    npm run verify:three-hero -- --contract

Expected GREEN for the source contract: all required files, imports, pose ownership, Hero mounting, canvas accessibility rules, lifecycle terms, and anti-raster scans pass. Browser compilation may remain blocked only by the separate missing Demo CSS file until Task 5.

### Task 4: Add forced fallback, responsive quality control, and lifecycle coverage

**Files:**
- Modify: docs/web/homepage-prototype/src/components/ThreeHeroScene.jsx
- Modify: docs/web/homepage-prototype/src/components/heroThreeScene.js
- Modify: docs/web/homepage-prototype/src/styles/home.css
- Modify: docs/web/homepage-prototype/scripts/verify-three-hero.mjs

**Interfaces:**
- Consumes: shared poseName and the React adapter's observer state.
- Produces: deterministic ?threeFallback=1 behavior, responsive quality levels, CSS fallback, and measurable paused/static render-loop states.

- [ ] **Step 1: Add failing fallback and responsive assertions**

Add three browser test paths to verify-three-hero.mjs:

1. Forced fallback:

    const fallbackPage = await browser.newPage({ viewport: { width: 1487, height: 1058 } });
    await fallbackPage.goto(baseUrl + "?threeFallback=1", { waitUntil: "networkidle" });
    const fallback = await inspectThreeHero(fallbackPage);
    check(fallback.state === "fallback", "Forced fallback must set data-three-state=fallback");
    check(await fallbackPage.locator(".hero-workbench").isVisible(), "Fallback must retain the DOM workbench");
    check(await fallbackPage.locator(".primary-button").isEnabled(), "Fallback must retain the primary CTA");

2. Responsive matrix: 1920x1080, 1487x1058, 1200x900, 1024x820, and 390x844. For every width assert no horizontal overflow, the workbench has positive width/height, the Hero heading does not overlap the workbench, and demoTop is greater than heroBottom minus two pixels.

3. Motion/lifecycle: emulate reduced motion, assert data-three-loop is static or paused after first render; scroll #hero out of view and assert paused; scroll it back and assert running or static according to current motion setting. Capture console errors, pageerror, and unhandled rejection messages for every page.

Run:

    cd docs/web/homepage-prototype
    BASE_URL=http://127.0.0.1:4173 npm run verify:three-hero

Expected RED until forced fallback, data-three-loop transitions, and all breakpoint quality rules are implemented.

- [ ] **Step 2: Implement quality profiles and lifecycle behavior**

Implement a quality object selected from the resolved pose:

    desktop: { dprCap: 1.5, bloom: true, reflectorScale: 1, gridDivisions: 28, animation: "continuous" }
    compact: { dprCap: 1.5, bloom: true, reflectorScale: 0.85, gridDivisions: 22, animation: "continuous" }
    tablet: { dprCap: 1.5, bloom: false, reflectorScale: 0.75, gridDivisions: 16, animation: "continuous" }
    mobile: { dprCap: 1, bloom: false, reflectorScale: 0.5, gridDivisions: 10, animation: "static" }

Use the quality object on scene creation and resize. Do not allocate a new scene merely because the Hero is offscreen; pause/resume the existing scene. A pose/quality transition may rebuild only scene resources whose dimensions or postprocessing capability changed, and must dispose the previous resource before replacement.

Set data-three-loop:
- running only when a RAF has been scheduled and the Hero is visible, page visible, and motion permits animation;
- paused when an existing scene is inactive due to IntersectionObserver or document.visibilityState;
- static after the first render on mobile or reduced motion;
- static in fallback.

- [ ] **Step 3: Make fallback visually complete without WebGL**

Extend home.css with state-specific rules:

- .hero-section:has(.three-hero-scene[data-three-state="fallback"]) keeps the existing cyan/violet virtual frame, CSS mirror floor, horizon line, and perspective grid visible.
- .hero-section:has(.three-hero-scene[data-three-state="ready"]) leaves a faint CSS base only; WebGL rail, grid, and Reflector provide the primary visual depth.
- At 1200px shrink the reflector/floor visual footprint enough to avoid left-copy collision.
- At 1024px simplify the rails and allow CSS fallback even if Bloom is disabled.
- At 390px keep the workbench readable, reduce tilt to mobile shared pose, hide visual-only high-density grid marks, retain a bottom-edge reflected glow, and never add horizontal scrolling.

No fallback rule may use url(), a bitmap, or a copied screenshot. The fallback canvas container stays in the DOM but contains no intercepting canvas when state is fallback.

- [ ] **Step 4: Verify the full Three runtime after the Demo closure task is complete**

This task's browser GREEN is intentionally deferred until Task 5 has restored the missing Demo stylesheet required for Vite compilation. After Task 5, run:

    cd docs/web/homepage-prototype
    BASE_URL=http://127.0.0.1:4173 npm run verify:three-hero

Expected GREEN: normal WebGL path reaches ready/ready/ready; forced query reaches fallback; all five viewport checks pass; reduced motion and offscreen paths report paused/static; CTA remains clickable; no console/page/request errors are emitted.

### Task 5: Independently close the prior Demo workbench CSS and regression gap

**Files:**
- Create: docs/web/homepage-prototype/src/styles/demo-workbenches.css
- Create: docs/web/homepage-prototype/scripts/verify-demo.mjs
- Do not modify: ThreeHeroScene.jsx, heroThreeScene.js, HeroSection.jsx, or the Three canvas CSS as part of this task.

**Interfaces:**
- Consumes: the current DemoSection.jsx structures already imported from ../styles/demo-workbenches.css.
- Produces: three visually and structurally distinct responsive Demo workbenches and a standalone npm run verify:demo regression gate.

- [ ] **Step 1: Write the isolated Demo verifier and record its RED result**

Create scripts/verify-demo.mjs with Playwright. For each tab it must click #tool-tab-narration, #tool-tab-translation, and #tool-tab-remix, then assert:

    narration: data-tool-layout === "narration", .narration-studio exists, [data-flow-step] count === 5
    translation: data-tool-layout === "translation", .translation-localizer exists, [data-flow-step] count === 4
    remix: data-tool-layout === "remix", .remix-console exists, [data-flow-step] count === 3

It must additionally assert:
- translation contains .bilingual-subtitles and .voice-mapping;
- remix contains .clip-pool, .remix-timeline, and .beat-controls;
- remix does not contain .narration-script or .bilingual-subtitles;
- the selected root class signature differs for all three tabs;
- 1487px, 1024px, and 390px have no horizontal overflow;
- source CSS and component code contain no data:image, base64, canvas, or background-image: url( reconstruction token.

Run:

    cd docs/web/homepage-prototype
    npm run verify:demo

Expected RED: Vite cannot resolve the already-imported src/styles/demo-workbenches.css, or the verifier reports the missing file. This is a known, isolated prior-round gap and must not be patched inside Three scene code.

- [ ] **Step 2: Create the independent Demo stylesheet**

Create demo-workbenches.css and style the existing DOM structures as three separate systems:

- .narration-studio: a left 5-step vertical pipeline, central assets/editor/script workspace, and right output score/summary. Keep the before/after range only inside .narration-compare.
- .translation-localizer: a top source-to-target language bar, 4-step horizontal flow, large bilingual preview/dialogue grid, and a right role voice-mapping panel.
- .remix-console: a compact 3-step header flow, highlight clip pool, video monitor, multi-track timeline, and BGM/beat control panel. It must not visually imply narration editing or subtitle generation.

Provide breakpoint behavior:
- desktop >= 1024px uses each tool's native panel arrangement;
- 768px to 1023px folds secondary controls below the primary preview/monitor without forcing the three tools into a common three-column layout;
- <= 767px converts narration pipeline to scrollable cards, translation to a single current bilingual row plus voice list, and remix to clip cards plus simplified timeline rails.

Use only CSS colors, gradients, borders, shadows, transforms, and DOM layout primitives. Do not add images beyond those already referenced by DemoSection.jsx.

- [ ] **Step 3: Run the independent Demo GREEN verification**

Run:

    cd docs/web/homepage-prototype
    npm run verify:demo
    npm run build

Expected GREEN: verifier reports all 5/4/3 flows, independent root layouts, translation-only bilingual/voice features, remix-only clip/timeline/BGM features, and no responsive overflow. Vite exits 0, unblocking the Three browser tests.

### Task 6: Run full verification and record evidence-based design QA

**Files:**
- Modify: docs/web/homepage-prototype/design-qa.md
- Verify only: docs/web/homepage-prototype/package.json, docs/web/homepage-prototype/package-lock.json, src/components/ThreeHeroScene.jsx, src/components/heroThreeScene.js, src/components/HeroSection.jsx, src/styles/home.css, src/styles/demo-workbenches.css, scripts/verify-three-hero.mjs, scripts/verify-hero.mjs, scripts/verify-demo.mjs

**Interfaces:**
- Consumes: successful Three and Demo runtime, a local Vite server, and screenshots.
- Produces: an auditable QA record tied to actual normal-WebGL and forced-fallback evidence.

- [ ] **Step 1: Start a fresh local server and run all automated gates**

Run:

    cd docs/web/homepage-prototype
    (npm run dev -- --host 127.0.0.1 > /tmp/narratoai-homepage-vite.log 2>&1 & echo $! > /tmp/narratoai-homepage-vite.pid)
    BASE_URL=http://127.0.0.1:4173 npm run verify:three-hero
    BASE_URL=http://127.0.0.1:4173 npm run verify:hero
    BASE_URL=http://127.0.0.1:4173 npm run verify:demo
    npm run build

Expected GREEN:
- verify:three-hero validates normal ready state, forced fallback, all five viewports, lifecycle/motion, interaction transparency, console cleanliness, and no raster reconstruction;
- verify:hero preserves original Hero sweep, virtual-frame, overlap, reduced-motion, and mobile checks;
- verify:demo preserves three independent workflows and responsive no-overflow;
- build exits 0 with one installed Three version.

- [ ] **Step 2: Run the explicit anti-paste gate**

Run:

    cd docs/web/homepage-prototype
    rg -n "TextureLoader|CanvasTexture|VideoTexture|data:image|base64|codex-clipboard|background-image\s*:\s*url|<canvas" src public index.html

Expected: no source hit associated with a screenshot, reference image, raster texture, or CSS bitmap reconstruction. The only allowed canvas reference is the real HTML canvas created by ThreeHeroScene.jsx; it must remain decorative and contain no DOM/UI texture code.

Also run:

    node -e "const p=require('./package-lock.json'); const versions=Object.entries(p.packages||{}).filter(([k])=>k.endsWith('/three')).map(([,v])=>v.version); if(versions.length!==1) process.exit(1); console.log('single-three-version', versions[0])"

Expected: exactly one Three.js package version.

- [ ] **Step 3: Capture visual evidence at all required states**

Use Playwright or the in-app browser to save screenshots under docs/web/homepage-prototype/artifacts/screenshots/ with these exact descriptive filenames:

    three-hero-webgl-1920.png
    three-hero-webgl-1487.png
    three-hero-webgl-1200.png
    three-hero-webgl-1024.png
    three-hero-webgl-390.png
    three-hero-fallback-1487.png
    three-hero-reduced-motion-1487.png

For every capture, inspect:
- panel has an obvious but readable leftward perspective;
- cyan top/left and violet right/bottom rails are continuous and non-stacked;
- Reflector shows the procedural panel silhouette, rails, and grid without reflecting DOM text as a bitmap;
- bloom does not create a black/opaque rectangle;
- Hero content is readable and CTA/video/tool controls are unobstructed;
- the mirror floor does not cover the Demo heading or controls;
- 390px retains a clean bottom-edge reflection with no overflow;
- fallback still has a usable static DOM workbench, neon frame, horizon, and mirror floor.

- [ ] **Step 4: Update design-qa.md from real outputs only**

Append a dated Three.js Hero section to design-qa.md containing:
1. implementation scope and the exact installed Three version;
2. a table for 1920, 1487, 1200, 1024, 390, forced fallback 1487, and reduced-motion 1487;
3. each screenshot path, data-three-state/reflector/rails/loop values, overflow result, console result, and visual conclusion;
4. the anti-paste command and its actual result;
5. the CSS fallback result;
6. an explicit list of retained legitimate DOM image assets and the statement that none enters WebGL;
7. final result: passed only when all automated checks and browser/design review pass. If any gate fails, write final result: blocked followed by the exact failing command and symptom.

- [ ] **Step 5: Final scope check without committing**

Run:

    cd /Users/wujingfeng/project/ai/codex/NarratoAI
    git diff --check -- docs/web/homepage-prototype docs/superpowers/specs/2026-07-14-threejs-hero-design.md docs/superpowers/plans/2026-07-14-threejs-hero-implementation.md
    git status --short -- docs/web/homepage-prototype docs/superpowers/specs/2026-07-14-threejs-hero-design.md docs/superpowers/plans/2026-07-14-threejs-hero-implementation.md

Expected: whitespace check exits 0; only declared prototype files plus the spec/plan documents appear in the review scope. Do not stage, commit, reset, clean, or alter unrelated working-tree files.

## Plan Self-Review

- Spec coverage: Tasks 1-4 cover transparent WebGL, procedural panel proxy, rail glow, Reflector floor, shared pose alignment, lifecycle, performance limits, fallback, responsive behavior, and anti-raster guardrails. Task 6 verifies every required acceptance point.
- Demo separation: Task 5 is explicitly isolated; it restores the imported Demo stylesheet and its verifier before final page regression, but it does not alter any Three.js contract.
- TDD order: every implementation phase begins with a contract or browser assertion that fails before its implementation, retains a documented RED reason, then specifies the GREEN command.
- Type consistency: HeroSection publishes poseName through resolveHeroPose/getHeroPoseStyle; ThreeHeroScene consumes heroRef/workbenchRef/poseName; createHeroThreeScene returns resize/setPose/setMotionMode/setVisible/renderOnce/dispose; verifier reads the exact data-three attributes supplied by the adapter.
- Placeholder scan: no unresolved implementation branches, image assets, external libraries, or unbounded visual tasks remain.
