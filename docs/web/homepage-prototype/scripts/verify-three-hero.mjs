#!/usr/bin/env node

import { access, mkdir, readFile } from "node:fs/promises";
import { constants } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";
import { inflateSync } from "node:zlib";
import { chromium } from "playwright";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDirectory, "..");
const requestedMode = process.argv.slice(2);
const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173/";
const executablePath = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const screenshotDirectory = path.join(projectRoot, "artifacts/screenshots");
const screenshotBuffers = new Map();

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

function decodePng(buffer) {
  let offset = 8;
  let width = 0;
  let height = 0;
  let channels = 0;
  const idat = [];
  while (offset < buffer.length) {
    const length = buffer.readUInt32BE(offset);
    const type = buffer.toString("ascii", offset + 4, offset + 8);
    const data = buffer.subarray(offset + 8, offset + 8 + length);
    if (type === "IHDR") {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      check(data[8] === 8 && [2, 6].includes(data[9]), "截图像素 gate 需要 8-bit RGB/RGBA PNG");
      channels = data[9] === 6 ? 4 : 3;
    } else if (type === "IDAT") idat.push(data);
    else if (type === "IEND") break;
    offset += length + 12;
  }
  const raw = inflateSync(Buffer.concat(idat));
  const stride = width * channels;
  const pixels = Buffer.alloc(height * stride);
  const paeth = (a, b, c) => {
    const p = a + b - c;
    const pa = Math.abs(p - a);
    const pb = Math.abs(p - b);
    const pc = Math.abs(p - c);
    return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
  };
  let sourceOffset = 0;
  for (let y = 0; y < height; y += 1) {
    const filter = raw[sourceOffset++];
    for (let x = 0; x < stride; x += 1) {
      const value = raw[sourceOffset++];
      const left = x >= channels ? pixels[y * stride + x - channels] : 0;
      const up = y > 0 ? pixels[(y - 1) * stride + x] : 0;
      const upperLeft = y > 0 && x >= channels ? pixels[(y - 1) * stride + x - channels] : 0;
      const decoded = filter === 0 ? value
        : filter === 1 ? value + left
          : filter === 2 ? value + up
            : filter === 3 ? value + Math.floor((left + up) / 2)
              : value + paeth(left, up, upperLeft);
      pixels[y * stride + x] = decoded & 255;
    }
  }
  return { width, height, channels, pixels };
}

function compareScreenshotRegion(firstBuffer, secondBuffer, region) {
  const first = decodePng(firstBuffer);
  const second = decodePng(secondBuffer);
  check(first.width === second.width && first.height === second.height, "截图像素 gate 的图片尺寸必须一致");
  const x0 = Math.floor(first.width * region.x0);
  const x1 = Math.ceil(first.width * region.x1);
  const y0 = Math.floor(first.height * region.y0);
  const y1 = Math.ceil(first.height * region.y1);
  let difference = 0;
  let darker = 0;
  let count = 0;
  for (let y = y0; y < y1; y += 2) {
    for (let x = x0; x < x1; x += 2) {
      const firstIndex = (y * first.width + x) * first.channels;
      const secondIndex = (y * second.width + x) * second.channels;
      const firstLuma = (first.pixels[firstIndex] + first.pixels[firstIndex + 1] + first.pixels[firstIndex + 2]) / 3;
      const secondLuma = (second.pixels[secondIndex] + second.pixels[secondIndex + 1] + second.pixels[secondIndex + 2]) / 3;
      difference += Math.abs(firstLuma - secondLuma);
      if (firstLuma + 8 < secondLuma) darker += 1;
      count += 1;
    }
  }
  return { meanDifference: difference / count, darkerRatio: darker / count };
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
      canvasOpacity: canvasStyle?.opacity || "",
      canvasVisibility: canvasStyle?.visibility || "",
      alignmentError: Number(scene?.dataset.threeAlignmentError || Number.NaN),
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
  if (metrics.headline && metrics.workbench) {
    const overlaps = metrics.headline.left < metrics.workbench.right
      && metrics.headline.right > metrics.workbench.left
      && metrics.headline.top < metrics.workbench.bottom
      && metrics.headline.bottom > metrics.workbench.top;
    check(!overlaps, `${label} Hero 标题不得与工作台重叠`);
  }
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
  await mkdir(screenshotDirectory, { recursive: true });
  const browser = await chromium.launch({
    executablePath,
    headless: true,
    args: ["--enable-webgl", "--ignore-gpu-blocklist"],
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
      console.log(`CHECK ${label}`);
      const page = await browser.newPage({ viewport });
      await page.addInitScript(() => localStorage.setItem("narrato.locale", "zh-CN"));
      const pageErrors = [];
      page.on("pageerror", (error) => pageErrors.push(`pageerror: ${error.message}`));
      page.on("response", (response) => {
        if (response.status() >= 400) pageErrors.push(`response: ${response.status()} ${response.url()}`);
      });
      page.on("console", (message) => {
        if (message.type() === "error" && !message.text().startsWith("Failed to load resource:")) {
          pageErrors.push(`console: ${message.text()}`);
        }
      });

      const didNavigate = await gotoAndCollectFailure(page, baseUrl, label, pageErrors);
      console.log(`STEP  ${label} navigated=${didNavigate}`);
      if (didNavigate) {
        await page.evaluate(() => document.fonts?.ready);
        console.log(`STEP  ${label} fonts`);
        await waitForSceneSettled(page);
        console.log(`STEP  ${label} scene-settled`);
        await page.waitForTimeout(160);

        const metrics = await readSceneMetrics(page);
        console.log(`STEP  ${label} metrics state=${metrics.state}`);
        checkCommonLayout(metrics, label);
        check(metrics.sceneExists, `${label} 必须挂载 .three-hero-scene`);
        check(metrics.state === "ready", `${label} Three 场景状态必须为 ready`, metrics.state || "missing");
        check(metrics.reflection === "ready", `${label} Three 镜面状态必须为 ready`, metrics.reflection || "missing");
        check(metrics.rails === "ready", `${label} Three 霓虹边轨状态必须为 ready`, metrics.rails || "missing");
        check(metrics.canvasExists, `${label} 必须渲染真实 WebGL canvas`);
        check(metrics.canvasWidth > 0 && metrics.canvasHeight > 0, `${label} WebGL canvas 必须具有渲染尺寸`, `${metrics.canvasWidth}×${metrics.canvasHeight}`);
        check(metrics.canvasPointerEvents === "none", `${label} WebGL canvas 必须不拦截 DOM 交互`, metrics.canvasPointerEvents || "missing");
        check(metrics.canvasBackground === "rgba(0, 0, 0, 0)", `${label} WebGL canvas 必须透明`, metrics.canvasBackground || "missing");
        check(metrics.canvasOpacity === "1" && metrics.canvasVisibility === "visible", `${label} ready canvas 必须可见`, `opacity=${metrics.canvasOpacity}, visibility=${metrics.canvasVisibility}`);
        check(Number.isFinite(metrics.alignmentError) && metrics.alignmentError <= 2, `${label} Three 投影边轨与 DOM 四边形误差不得超过 2px`, `${metrics.alignmentError}px`);

        if (viewport.width === 1487) {
          await page.evaluate(() => window.scrollTo({ top: document.querySelector("#demo").offsetTop + window.innerHeight, behavior: "instant" }));
          await page.waitForFunction(() => document.querySelector(".three-hero-scene")?.dataset.threeLoop === "paused", { timeout: 5000 });
          check(await page.locator(".three-hero-scene").getAttribute("data-three-loop") === "paused", `${label} Hero 离屏后渲染循环必须暂停`);
          await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
          await page.waitForFunction(() => ["running", "static"].includes(document.querySelector(".three-hero-scene")?.dataset.threeLoop), { timeout: 5000 });
          check(await page.locator(".three-hero-scene").getAttribute("data-three-loop") === "running", `${label} Hero 回到视口后桌面渲染循环必须恢复`);
        }

        const screenshot = await page.screenshot({
          path: path.join(screenshotDirectory, `three-hero-webgl-${viewport.width}.png`),
          fullPage: false,
        });
        screenshotBuffers.set(`webgl-${viewport.width}`, screenshot);
      }

      if (pageErrors.length) {
        browserErrors.push(...pageErrors.map((error) => `${label} ${error}`));
      }
      console.log(`STEP  ${label} closing-page`);
      await page.close();
      console.log(`DONE  ${label}`);
    }

    const fallback = await browser.newPage({ viewport: { width: 1487, height: 1058 } });
    await fallback.addInitScript(() => localStorage.setItem("narrato.locale", "zh-CN"));
    console.log("CHECK threeFallback=1");
    const fallbackErrors = [];
    fallback.on("pageerror", (error) => fallbackErrors.push(`pageerror: ${error.message}`));
    fallback.on("response", (response) => {
      if (response.status() >= 400) fallbackErrors.push(`response: ${response.status()} ${response.url()}`);
    });
    fallback.on("console", (message) => {
      if (message.type() === "error" && !message.text().startsWith("Failed to load resource:")) {
        fallbackErrors.push(`console: ${message.text()}`);
      }
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
      await fallback.waitForTimeout(650);
      screenshotBuffers.set("fallback-1487", await fallback.screenshot({ path: path.join(screenshotDirectory, "three-hero-fallback-1487.png"), fullPage: false }));
      await verifyCtaClick(fallback, "threeFallback=1");
    }

    if (fallbackErrors.length) {
      browserErrors.push(...fallbackErrors.map((error) => `threeFallback=1 ${error}`));
    }
    await fallback.close();
    console.log("DONE  threeFallback=1");

    const reduced = await browser.newPage({ viewport: { width: 1487, height: 1058 } });
    await reduced.addInitScript(() => localStorage.setItem("narrato.locale", "zh-CN"));
    const reducedErrors = [];
    reduced.on("pageerror", (error) => reducedErrors.push(`pageerror: ${error.message}`));
    reduced.on("response", (response) => {
      if (response.status() >= 400) reducedErrors.push(`response: ${response.status()} ${response.url()}`);
    });
    reduced.on("console", (message) => {
      if (message.type() === "error" && !message.text().startsWith("Failed to load resource:")) {
        reducedErrors.push(`console: ${message.text()}`);
      }
    });
    await reduced.emulateMedia({ reducedMotion: "reduce" });
    const didNavigateReduced = await gotoAndCollectFailure(reduced, baseUrl, "reduced-motion", reducedErrors);
    if (didNavigateReduced) {
      await waitForSceneSettled(reduced);
      await reduced.waitForFunction(() => document.querySelector(".three-hero-scene")?.dataset.threeLoop === "static");
      const reducedMetrics = await readSceneMetrics(reduced);
      checkCommonLayout(reducedMetrics, "reduced-motion");
      check(reducedMetrics.state === "fallback", "reduced-motion 必须进入真实 fallback", reducedMetrics.state);
      check(reducedMetrics.loop === "static", "reduced-motion 渲染循环必须为 static", reducedMetrics.loop);
      check(reducedMetrics.canvasExists === false, "reduced-motion fallback 不得保留 canvas");
      screenshotBuffers.set("reduced-1487", await reduced.screenshot({ path: path.join(screenshotDirectory, "three-hero-reduced-motion-1487.png"), fullPage: false }));
    }
    browserErrors.push(...reducedErrors.map((error) => `reduced-motion ${error}`));
    await reduced.close();

    if (screenshotBuffers.has("webgl-1487") && screenshotBuffers.has("fallback-1487")) {
      const visibleWebgl = compareScreenshotRegion(screenshotBuffers.get("webgl-1487"), screenshotBuffers.get("fallback-1487"), { x0: 0.34, x1: 0.96, y0: 0.55, y1: 0.78 });
      check(visibleWebgl.meanDifference >= 1.2, "WebGL 截图必须在镜面/轨道区域产生可辨别像素贡献", `meanDifference=${visibleWebgl.meanDifference.toFixed(2)}`);
    }
    if (screenshotBuffers.has("reduced-1487") && screenshotBuffers.has("fallback-1487")) {
      const blackBlock = compareScreenshotRegion(screenshotBuffers.get("reduced-1487"), screenshotBuffers.get("fallback-1487"), { x0: 0, x1: 0.36, y0: 0, y1: 0.62 });
      check(blackBlock.darkerRatio < 0.08, "reduced-motion 截图不得出现大面积黑色合成块", `darkerRatio=${blackBlock.darkerRatio.toFixed(3)}`);
    }
  } finally {
    console.log("CHECK browser.close");
    await browser.close();
    console.log("DONE  browser.close");
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
