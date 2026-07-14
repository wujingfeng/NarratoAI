#!/usr/bin/env node

import { access, readFile } from "node:fs/promises";
import { constants } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "playwright";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDirectory, "..");
const requestedMode = process.argv.slice(2);
const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173/";
const executablePath = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const passes = [];
const failures = [];
const runtimeRelativePath = "src/components/heroThreeScene.js";
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
const expectedHeroPanelPoses = {
  desktop: { rotateX: 2, rotateY: -11, rotateZ: -1, depth: 30 },
  compact: { rotateX: 1.5, rotateY: -8, rotateZ: -0.5, depth: 22 },
  tablet: { rotateX: 1, rotateY: -5, rotateZ: 0, depth: 14 },
  mobile: { rotateX: 0.5, rotateY: -3, rotateZ: 0, depth: 8 },
};

function check(condition, message) {
  if (condition) {
    passes.push(message);
  } else {
    failures.push(message);
  }
}

async function sourceExists(relativePath) {
  try {
    await access(path.join(projectRoot, relativePath), constants.R_OK);
    return true;
  } catch {
    return false;
  }
}

async function readSource(relativePath) {
  try {
    return await readFile(path.join(projectRoot, relativePath), "utf8");
  } catch {
    return "";
  }
}

function isExactVersion(value) {
  return typeof value === "string" && /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(value);
}

function containsForbiddenToken(source, token) {
  if (token === "background-image: url(") {
    return /background-image\s*:\s*url\s*\(/i.test(source);
  }

  return source.toLowerCase().includes(token.toLowerCase());
}

async function runContract() {
  const packageJson = JSON.parse(await readFile(path.join(projectRoot, "package.json"), "utf8"));
  const packageLock = JSON.parse(await readFile(path.join(projectRoot, "package-lock.json"), "utf8"));
  const threeVersion = packageJson.dependencies?.three;
  const lockedRootVersion = packageLock.packages?.[""]?.dependencies?.three;
  const lockedThreeVersion = packageLock.packages?.["node_modules/three"]?.version;

  check(Boolean(threeVersion), "package.json declares the single Three.js runtime dependency");
  check(isExactVersion(threeVersion), "package.json pins three with an exact version");
  check(
    Boolean(threeVersion) && lockedRootVersion === threeVersion,
    "package-lock root dependency matches package.json three version",
  );
  check(
    Boolean(threeVersion) && lockedThreeVersion === threeVersion,
    "package-lock resolves exactly one matching node_modules/three version",
  );

  const requiredFiles = [
    runtimeRelativePath,
    "src/components/ThreeHeroScene.jsx",
  ];

  for (const relativePath of requiredFiles) {
    check(await sourceExists(relativePath), `${relativePath} exists`);
  }

  const heroSource = await readSource("src/components/HeroSection.jsx");
  const requiredHeroTokens = [
    "ThreeHeroScene",
    "data-hero-pose",
    "getHeroPoseStyle",
    "workbenchRef",
  ];

  for (const token of requiredHeroTokens) {
    check(heroSource.includes(token), `HeroSection publishes the shared Three.js mount contract: ${token}`);
  }

  const runtimeSource = await readSource(runtimeRelativePath);
  for (const token of requiredRuntimeTokens) {
    check(
      runtimeSource.includes(token),
      `${runtimeRelativePath} references required Three.js lifecycle primitive: ${token}`,
    );
  }

  let runtimeModule = null;
  if (await sourceExists(runtimeRelativePath)) {
    try {
      const runtimeUrl = pathToFileURL(path.join(projectRoot, runtimeRelativePath));
      runtimeUrl.searchParams.set("contract", Date.now().toString());
      runtimeModule = await import(runtimeUrl.href);
      check(true, `${runtimeRelativePath} can be imported without creating a WebGL scene`);
    } catch (error) {
      check(false, `${runtimeRelativePath} can be imported without creating a WebGL scene (${error.message})`);
    }
  } else {
    check(false, `${runtimeRelativePath} can be imported without creating a WebGL scene`);
  }

  for (const exportName of requiredRuntimeExports) {
    check(
      runtimeModule && Object.hasOwn(runtimeModule, exportName),
      `${runtimeRelativePath} exposes runtime export: ${exportName}`,
    );
  }

  if (runtimeModule) {
    check(
      JSON.stringify(runtimeModule.HERO_PANEL_POSES) === JSON.stringify(expectedHeroPanelPoses),
      "HERO_PANEL_POSES matches the exact four shared DOM and scene poses",
    );
    check(
      [
        [1261, "desktop"],
        [1260, "compact"],
        [1101, "compact"],
        [1100, "tablet"],
        [768, "tablet"],
        [767, "mobile"],
      ].every(([width, poseName]) => runtimeModule.resolveHeroPose(width) === poseName),
      "resolveHeroPose applies 1261 / 1101 / 768 responsive breakpoints",
    );
    const desktopStyle = runtimeModule.getHeroPoseStyle("desktop");
    check(
      desktopStyle?.["--hero-panel-rotate-x"] === "2deg"
        && desktopStyle?.["--hero-panel-rotate-y"] === "-11deg"
        && desktopStyle?.["--hero-panel-rotate-z"] === "-1deg"
        && desktopStyle?.["--hero-panel-depth"] === "30px",
      "getHeroPoseStyle exposes desktop DOM transform variables",
    );
    check(
      typeof runtimeModule.createHeroThreeScene === "function",
      "createHeroThreeScene is a callable runtime factory",
    );
  }

  const prohibitedTokens = [
    "TextureLoader",
    "CanvasTexture",
    "VideoTexture",
    "data:image",
    "base64",
    "codex-clipboard",
    "background-image: url(",
  ];

  const visualSources = [
    ["src/components/HeroSection.jsx", heroSource],
    [runtimeRelativePath, runtimeSource],
    ["src/components/ThreeHeroScene.jsx", await readSource("src/components/ThreeHeroScene.jsx")],
    ["src/styles/home.css", await readSource("src/styles/home.css")],
  ];

  for (const [relativePath, source] of visualSources) {
    for (const token of prohibitedTokens) {
      check(
        !containsForbiddenToken(source, token),
        `${relativePath} does not use prohibited raster reconstruction token: ${token}`,
      );
    }
  }
}

async function waitForSceneSettled(page) {
  try {
    await page.waitForFunction(
      () => {
        const scene = document.querySelector(".three-hero-scene");
        return scene && scene.dataset.threeState !== "loading";
      },
      { timeout: 9000 },
    );
  } catch {
    // The assertions below produce a focused RED result when the integration is absent.
  }
}

async function readSceneMetrics(page) {
  return page.evaluate(() => {
    const rectFor = (selector) => {
      const node = document.querySelector(selector);
      if (!node) return null;

      const rect = node.getBoundingClientRect();
      return {
        width: rect.width,
        height: rect.height,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
        left: rect.left,
      };
    };

    const scene = document.querySelector(".three-hero-scene");
    const canvas = scene?.querySelector("canvas");
    const canvasStyle = canvas ? getComputedStyle(canvas) : null;

    return {
      pageWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
      hero: rectFor("#hero"),
      demo: rectFor("#demo"),
      workbench: rectFor(".hero-workbench-wrap"),
      headline: rectFor(".hero-copy h1"),
      cta: rectFor(".hero-actions .primary-button"),
      sceneExists: Boolean(scene),
      state: scene?.dataset.threeState || "",
      reflection: scene?.dataset.threeReflection || "",
      rails: scene?.dataset.threeRails || "",
      loop: scene?.dataset.threeLoop || "",
      canvasExists: Boolean(canvas),
      canvasWidth: canvas?.width || 0,
      canvasHeight: canvas?.height || 0,
      canvasPointerEvents: canvasStyle?.pointerEvents || "",
      canvasBackground: canvasStyle?.backgroundColor || "",
    };
  });
}

async function gotoAndCollectFailure(page, url, label, pageErrors) {
  try {
    const response = await page.goto(url, { waitUntil: "domcontentloaded" });

    if (!response) {
      pageErrors.push(`navigation: ${label} did not return a document response`);
      return false;
    }

    if (!response.ok()) {
      pageErrors.push(`navigation: ${label} returned HTTP ${response.status()} ${response.statusText()}`);
      return false;
    }

    return true;
  } catch (error) {
    pageErrors.push(`navigation: ${label} failed (${error.message})`);
    return false;
  }
}

function checkCommonLayout(metrics, label) {
  check(metrics.pageWidth <= metrics.viewportWidth + 1, `${label} 页面不得出现横向溢出`, `${metrics.pageWidth}px > ${metrics.viewportWidth}px`);
  check(Boolean(metrics.hero && metrics.demo), `${label} Hero 与案例区必须存在`);
  check(
    Boolean(metrics.hero && metrics.demo && metrics.hero.bottom <= metrics.demo.top + 1),
    `${label} Hero 与案例区不得重叠`,
    metrics.hero && metrics.demo ? `heroBottom=${metrics.hero.bottom.toFixed(1)}, demoTop=${metrics.demo.top.toFixed(1)}` : "",
  );
  check(Boolean(metrics.workbench && metrics.workbench.width > 0 && metrics.workbench.height > 0), `${label} DOM 工作台必须保持可见`);
  check(Boolean(metrics.headline && metrics.headline.width > 0 && metrics.headline.height > 0), `${label} Hero 标题必须保持可见`);
  check(Boolean(metrics.cta && metrics.cta.width > 0 && metrics.cta.height > 0), `${label} Hero CTA 必须保持可见`);
}

async function verifyCtaClick(page, label) {
  try {
    await page.locator(".hero-actions .primary-button").click({ timeout: 3000 });
    await page.waitForURL((url) => url.pathname === "/dashboard", { timeout: 3000 });
    await page.getByRole("heading", { name: "工作台概览" }).waitFor({ state: "attached", timeout: 3000 });
    check(true, `${label} DOM CTA 导航到工作台`);
  } catch (error) {
    check(false, `${label} DOM CTA 导航到工作台`, error.message);
  }
}

async function runBrowser() {
  const browser = await chromium.launch({
    executablePath,
    headless: true,
    args: ["--enable-webgl", "--ignore-gpu-blocklist", "--use-angle=swiftshader"],
  });
  const browserErrors = [];
  const viewports = [
    { width: 1920, height: 1080 },
    { width: 1487, height: 1058 },
    { width: 1200, height: 900 },
    { width: 1024, height: 820 },
    { width: 390, height: 844 },
  ];

  try {
    for (const viewport of viewports) {
      const label = `${viewport.width}×${viewport.height}`;
      const page = await browser.newPage({ viewport });
      const pageErrors = [];
      page.on("pageerror", (error) => pageErrors.push(`pageerror: ${error.message}`));
      page.on("console", (message) => {
        if (message.type() === "error") pageErrors.push(`console: ${message.text()}`);
      });

      const didNavigate = await gotoAndCollectFailure(page, baseUrl, label, pageErrors);
      if (didNavigate) {
        await page.evaluate(() => document.fonts?.ready);
        await waitForSceneSettled(page);
        await page.waitForTimeout(160);

        const metrics = await readSceneMetrics(page);
        checkCommonLayout(metrics, label);
        check(metrics.sceneExists, `${label} 必须挂载 .three-hero-scene`);
        check(metrics.state === "ready", `${label} Three 场景状态必须为 ready`, metrics.state || "missing");
        check(metrics.reflection === "ready", `${label} Three 镜面状态必须为 ready`, metrics.reflection || "missing");
        check(metrics.rails === "ready", `${label} Three 霓虹边轨状态必须为 ready`, metrics.rails || "missing");
        check(metrics.canvasExists, `${label} 必须渲染真实 WebGL canvas`);
        check(metrics.canvasWidth > 0 && metrics.canvasHeight > 0, `${label} WebGL canvas 必须具有渲染尺寸`, `${metrics.canvasWidth}×${metrics.canvasHeight}`);
        check(metrics.canvasPointerEvents === "none", `${label} WebGL canvas 必须不拦截 DOM 交互`, metrics.canvasPointerEvents || "missing");
        check(metrics.canvasBackground === "rgba(0, 0, 0, 0)", `${label} WebGL canvas 必须透明`, metrics.canvasBackground || "missing");
      }

      if (pageErrors.length) {
        browserErrors.push(...pageErrors.map((error) => `${label} ${error}`));
      }
      await page.close();
    }

    const fallback = await browser.newPage({ viewport: { width: 1487, height: 1058 } });
    const fallbackErrors = [];
    fallback.on("pageerror", (error) => fallbackErrors.push(`pageerror: ${error.message}`));
    fallback.on("console", (message) => {
      if (message.type() === "error") fallbackErrors.push(`console: ${message.text()}`);
    });

    const fallbackUrl = new URL(baseUrl);
    fallbackUrl.searchParams.set("threeFallback", "1");
    const didNavigateFallback = await gotoAndCollectFailure(
      fallback,
      fallbackUrl.href,
      "threeFallback=1",
      fallbackErrors,
    );
    if (didNavigateFallback) {
      await fallback.evaluate(() => document.fonts?.ready);
      await waitForSceneSettled(fallback);
      await fallback.waitForTimeout(160);

      const fallbackMetrics = await readSceneMetrics(fallback);
      checkCommonLayout(fallbackMetrics, "threeFallback=1");
      check(fallbackMetrics.sceneExists, "threeFallback=1 必须保留 Three 场景容器");
      check(fallbackMetrics.state === "fallback", "threeFallback=1 必须进入 fallback 状态", fallbackMetrics.state || "missing");
      check(fallbackMetrics.canvasExists === false, "threeFallback=1 不得创建 WebGL canvas");
      await verifyCtaClick(fallback, "threeFallback=1");
    }

    if (fallbackErrors.length) {
      browserErrors.push(...fallbackErrors.map((error) => `threeFallback=1 ${error}`));
    }
    await fallback.close();
  } finally {
    await browser.close();
  }

  for (const error of browserErrors) {
    check(false, `浏览器验证不得出现错误：${error}`);
  }
}

if (requestedMode.includes("--contract")) {
  await runContract();
} else {
  await runBrowser();
}

for (const message of passes) {
  console.log(`PASS  ${message}`);
}

for (const message of failures) {
  console.error(`FAIL  ${message}`);
}

if (failures.length > 0) {
  console.error(`\nThree.js Hero ${requestedMode.includes("--contract") ? "contract" : "browser verification"} is RED (${failures.length} failed assertion${failures.length === 1 ? "" : "s"}).`);
  process.exitCode = 1;
} else {
  console.log(`\nThree.js Hero ${requestedMode.includes("--contract") ? "contract" : "browser verification"} is GREEN.`);
}
