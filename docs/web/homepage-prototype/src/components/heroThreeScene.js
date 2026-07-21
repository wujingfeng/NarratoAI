import {
  AdditiveBlending,
  Color,
  CurvePath,
  DoubleSide,
  GridHelper,
  Group,
  LineCurve3,
  MathUtils,
  Mesh,
  MeshBasicMaterial,
  PerspectiveCamera,
  PlaneGeometry,
  Scene,
  SRGBColorSpace,
  TubeGeometry,
  Vector2,
  Vector3,
  WebGLRenderer,
} from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { Reflector } from "three/addons/objects/Reflector.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";

const CAMERA_FOV = 37;
const CAMERA_DISTANCE = 13.5;
const RAIL_FADE_MS = 760;
const RAIL_PULSE_MS = 4200;
const DESKTOP_DPR_CAP = 1.5;
const MOBILE_DPR_CAP = 1;
const MIN_DIMENSION = 1;

export const HERO_PANEL_POSES = Object.freeze({
  desktop: Object.freeze({ rotateX: 2, rotateY: -11, rotateZ: -1, depth: 30 }),
  compact: Object.freeze({ rotateX: 1.5, rotateY: -8, rotateZ: -0.5, depth: 22 }),
  tablet: Object.freeze({ rotateX: 1, rotateY: -5, rotateZ: 0, depth: 14 }),
  mobile: Object.freeze({ rotateX: 0.5, rotateY: -3, rotateZ: 0, depth: 8 }),
});

export function resolveHeroPose(viewportWidth) {
  const fallbackWidth = typeof window === "undefined" ? 1261 : window.innerWidth;
  const width = Number.isFinite(viewportWidth) ? viewportWidth : fallbackWidth;

  if (width >= 1261) return "desktop";
  if (width >= 1101) return "compact";
  if (width >= 768) return "tablet";
  return "mobile";
}

export function getHeroPoseStyle(poseName) {
  const pose = HERO_PANEL_POSES[poseName] ?? HERO_PANEL_POSES[resolveHeroPose()];

  return {
    "--hero-panel-rotate-x": `${pose.rotateX}deg`,
    "--hero-panel-rotate-y": `${pose.rotateY}deg`,
    "--hero-panel-rotate-z": `${pose.rotateZ}deg`,
    "--hero-panel-depth": `${pose.depth}px`,
  };
}

function getRendererPixelRatio(width) {
  const isMobile = width < 768;
  const devicePixelRatio = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
  return Math.min(devicePixelRatio, isMobile ? MOBILE_DPR_CAP : DESKTOP_DPR_CAP);
}

function getViewportAtScenePlane(camera) {
  const height = 2 * Math.tan(MathUtils.degToRad(camera.fov * 0.5)) * CAMERA_DISTANCE;
  return { width: height * camera.aspect, height };
}

function transformPoint(matrix, x, y, originX, originY) {
  const point = new DOMPoint(x - originX, y - originY, 0, 1).matrixTransform(matrix);
  const divisor = point.w || 1;
  return { x: point.x / divisor + originX, y: point.y / divisor + originY };
}

function getWorkbenchScreenQuad(workbenchElement, workbenchRect) {
  const style = getComputedStyle(workbenchElement);
  const matrix = new DOMMatrix(style.transform === "none" ? undefined : style.transform);
  const [originX = "0", originY = "0"] = style.transformOrigin.split(" ");
  const ox = Number.parseFloat(originX) || 0;
  const oy = Number.parseFloat(originY) || 0;
  const width = workbenchElement.offsetWidth;
  const height = workbenchElement.offsetHeight;
  const localPoints = [
    transformPoint(matrix, 0, 0, ox, oy),
    transformPoint(matrix, width, 0, ox, oy),
    transformPoint(matrix, width, height, ox, oy),
    transformPoint(matrix, 0, height, ox, oy),
  ];
  const minimumX = Math.min(...localPoints.map((point) => point.x));
  const minimumY = Math.min(...localPoints.map((point) => point.y));
  return localPoints.map((point) => ({
    x: workbenchRect.left + point.x - minimumX,
    y: workbenchRect.top + point.y - minimumY,
  }));
}

function screenPointToScenePlane(point, heroRect, camera) {
  const ndc = new Vector3(
    ((point.x - heroRect.left) / Math.max(heroRect.width, MIN_DIMENSION)) * 2 - 1,
    -(((point.y - heroRect.top) / Math.max(heroRect.height, MIN_DIMENSION)) * 2 - 1),
    0.5,
  );
  const worldPoint = ndc.unproject(camera);
  const direction = worldPoint.sub(camera.position).normalize();
  return camera.position.clone().add(direction.multiplyScalar(-camera.position.z / direction.z));
}

function projectScenePointToScreen(point, heroRect, camera) {
  const projected = point.clone().project(camera);
  return {
    x: heroRect.left + (projected.x + 1) * 0.5 * heroRect.width,
    y: heroRect.top + (1 - projected.y) * 0.5 * heroRect.height,
  };
}

function mapWorkbenchRectToScene(workbenchElement, workbenchRect, heroRect, camera) {
  const viewport = getViewportAtScenePlane(camera);
  const heroWidth = Math.max(heroRect.width, MIN_DIMENSION);
  const heroHeight = Math.max(heroRect.height, MIN_DIMENSION);
  const centerX = workbenchRect.left - heroRect.left + workbenchRect.width * 0.5;
  const centerY = workbenchRect.top - heroRect.top + workbenchRect.height * 0.5;
  const unitsPerPixel = viewport.height / heroHeight;
  const screenQuad = getWorkbenchScreenQuad(workbenchElement, workbenchRect);
  const sceneQuad = screenQuad.map((point) => screenPointToScenePlane(point, heroRect, camera));

  return {
    width: Math.max(workbenchRect.width * unitsPerPixel, 0.1),
    height: Math.max(workbenchRect.height * unitsPerPixel, 0.1),
    centerX: (centerX / heroWidth - 0.5) * viewport.width,
    centerY: (0.5 - centerY / heroHeight) * viewport.height,
    unitsPerPixel,
    screenQuad,
    sceneQuad,
  };
}

function createRailMesh(curve, radius, material) {
  return new Mesh(new TubeGeometry(curve, 96, radius, 6, false), material);
}

function createRailCurvesFromQuad([topLeft, topRight, bottomRight, bottomLeft]) {
  const cyanEnd = topLeft.clone().lerp(topRight, 0.46);
  const violetStart = topLeft.clone().lerp(topRight, 0.54);
  const violetEnd = bottomRight.clone().lerp(bottomLeft, 0.62);
  const cyan = new CurvePath();
  cyan.add(new LineCurve3(bottomLeft, topLeft));
  cyan.add(new LineCurve3(topLeft, cyanEnd));
  const violet = new CurvePath();
  violet.add(new LineCurve3(violetStart, topRight));
  violet.add(new LineCurve3(topRight, bottomRight));
  violet.add(new LineCurve3(bottomRight, violetEnd));
  return { cyan, violet };
}

function disposeMaterial(material, disposedMaterials) {
  const materials = Array.isArray(material) ? material : [material];
  for (const currentMaterial of materials) {
    if (currentMaterial && !disposedMaterials.has(currentMaterial)) {
      disposedMaterials.add(currentMaterial);
      currentMaterial.dispose();
    }
  }
}

function disposeSceneGraph(root, reflector) {
  const disposedGeometries = new Set();
  const disposedMaterials = new Set();

  root.traverse((object) => {
    if (object.geometry && !disposedGeometries.has(object.geometry)) {
      disposedGeometries.add(object.geometry);
      object.geometry.dispose();
    }

    if (object.material && object !== reflector) {
      disposeMaterial(object.material, disposedMaterials);
    }
  });
}

function setObjectOpacity(material, opacity) {
  material.opacity = opacity;
}

function getGridMaterials(grid) {
  return Array.isArray(grid.material) ? grid.material : [grid.material];
}

function isMobilePose(poseName) {
  return poseName === "mobile";
}

export function createHeroThreeScene({
  mountElement,
  heroElement,
  workbenchElement,
  poseName = "desktop",
  reducedMotion = false,
  onSignal,
}) {
  if (!mountElement || !heroElement || !workbenchElement) {
    throw new TypeError("createHeroThreeScene requires mountElement, heroElement, and workbenchElement");
  }

  let renderer;
  let composer;
  let renderPass;
  let bloomPass;
  let outputPass;
  let reflector;
  let frameId = 0;
  let railMeshes = [];

  const state = {
    disposed: false,
    visible: true,
    poseName: HERO_PANEL_POSES[poseName] ? poseName : "desktop",
    reducedMotion: Boolean(reducedMotion),
    width: MIN_DIMENSION,
    height: MIN_DIMENSION,
    pixelRatio: 1,
    fadeStartedAt: 0,
    shouldUseBloom: false,
    postprocessFallback: false,
    gridDivisions: 0,
  };

  const signal = (payload) => {
    try {
      onSignal?.(payload);
    } catch {
      // A status observer must not interrupt the visual runtime.
    }
  };

  const scene = new Scene();
  const camera = new PerspectiveCamera(CAMERA_FOV, 1, 0.1, 48);
  const panelGroup = new Group();
  const railGroup = new Group();
  const panelGeometry = new RoundedBoxGeometry(1, 1, 0.06, 8, 0.06);
  const panelMaterial = new MeshBasicMaterial({
    color: 0x041424,
    transparent: true,
    opacity: 0.04,
    depthWrite: false,
    side: DoubleSide,
  });
  const panelProxy = new Mesh(panelGeometry, panelMaterial);
  const cyanCoreMaterial = new MeshBasicMaterial({
    color: 0xa0edff,
    transparent: true,
    opacity: 0,
    depthWrite: false,
  });
  const cyanGlowMaterial = new MeshBasicMaterial({
    color: 0x18a8ff,
    transparent: true,
    opacity: 0,
    depthWrite: false,
    blending: AdditiveBlending,
  });
  const violetCoreMaterial = new MeshBasicMaterial({
    color: 0xe1a1ff,
    transparent: true,
    opacity: 0,
    depthWrite: false,
  });
  const violetGlowMaterial = new MeshBasicMaterial({
    color: 0x9b2bff,
    transparent: true,
    opacity: 0,
    depthWrite: false,
    blending: AdditiveBlending,
  });
  const floorGeometry = new PlaneGeometry(1, 1);
  const floorMaterial = new MeshBasicMaterial({
    color: 0x030917,
    transparent: true,
    opacity: 0.06,
    depthWrite: false,
    side: DoubleSide,
  });
  const floor = new Mesh(floorGeometry, floorMaterial);
  const horizonGeometry = new PlaneGeometry(1, 1);
  const horizonMaterial = new MeshBasicMaterial({
    color: 0x3fc7ff,
    transparent: true,
    opacity: 0.16,
    depthWrite: false,
    blending: AdditiveBlending,
    side: DoubleSide,
  });
  const horizonGlow = new Mesh(horizonGeometry, horizonMaterial);
  let grid = new GridHelper(1, 18, 0x208eff, 0x711fca);

  function isStaticMode() {
    return state.reducedMotion || isMobilePose(state.poseName);
  }

  function updateRailIntensity(now = performance.now()) {
    const elapsed = Math.max(0, now - state.fadeStartedAt);
    const fade = isStaticMode() ? 1 : Math.min(elapsed / RAIL_FADE_MS, 1);
    const pulse = isStaticMode() ? 1 : 0.89 + Math.sin(elapsed / RAIL_PULSE_MS * Math.PI * 2) * 0.11;
    const intensity = fade * pulse;

    setObjectOpacity(cyanCoreMaterial, 0.28 * intensity);
    setObjectOpacity(cyanGlowMaterial, 0.09 * intensity);
    setObjectOpacity(violetCoreMaterial, 0.25 * intensity);
    setObjectOpacity(violetGlowMaterial, 0.08 * intensity);
  }

  function removeRailMeshes() {
    for (const mesh of railMeshes) {
      railGroup.remove(mesh);
      mesh.geometry.dispose();
    }
    railMeshes = [];
  }

  function rebuildRailGeometry(sceneQuad) {
    removeRailMeshes();

    const { cyan: cyanCurve, violet: violetCurve } = createRailCurvesFromQuad(sceneQuad);
    railMeshes = [
      createRailMesh(cyanCurve, 0.016, cyanCoreMaterial),
      createRailMesh(cyanCurve, 0.05, cyanGlowMaterial),
      createRailMesh(violetCurve, 0.015, violetCoreMaterial),
      createRailMesh(violetCurve, 0.046, violetGlowMaterial),
    ];

    for (const mesh of railMeshes) {
      mesh.renderOrder = 6;
      railGroup.add(mesh);
    }
  }

  function replaceGrid(divisions) {
    scene.remove(grid);
    grid.geometry.dispose();
    disposeMaterial(grid.material, new Set());
    grid = new GridHelper(1, divisions, 0x2498ff, 0x862cf4);
    state.gridDivisions = divisions;
    grid.renderOrder = 2;
    for (const material of getGridMaterials(grid)) {
      material.transparent = true;
      material.opacity = isMobilePose(state.poseName) ? 0.13 : 0.22;
      material.depthWrite = false;
    }
    scene.add(grid);
  }

  function syncBloomMode() {
    const rendererAttributes = renderer.getContextAttributes?.();
    const shouldUseBloom = !state.postprocessFallback
      && !isMobilePose(state.poseName)
      && !state.reducedMotion
      && rendererAttributes?.alpha === true;

    if (state.shouldUseBloom === shouldUseBloom) return;

    state.shouldUseBloom = shouldUseBloom;
    if (!shouldUseBloom) {
      const bloomIndex = composer.passes.indexOf(bloomPass);
      if (bloomIndex >= 0) composer.passes.splice(bloomIndex, 1);
      return;
    }

    if (!bloomPass) {
      bloomPass = new UnrealBloomPass(new Vector2(state.width, state.height), 0.72, 0.56, 0.72);
    }

    bloomPass.enabled = true;
    if (!composer.passes.includes(bloomPass)) composer.insertPass(bloomPass, 1);
  }

  function syncSceneGeometry() {
    const heroRect = heroElement.getBoundingClientRect();
    const workbenchRect = workbenchElement.getBoundingClientRect();
    const mappedPanel = mapWorkbenchRectToScene(workbenchElement, workbenchRect, heroRect, camera);
    const pose = HERO_PANEL_POSES[state.poseName];
    const panelDepth = Math.max(0.08, pose.depth * mappedPanel.unitsPerPixel * 0.24);
    const floorWidth = Math.max(mappedPanel.width * 1.5, 4.4);
    const floorDepth = Math.max(mappedPanel.height * 1.3, 3.8);
    const floorY = mappedPanel.centerY - mappedPanel.height * 0.5 - 0.14;

    panelGroup.position.set(mappedPanel.centerX, mappedPanel.centerY, 0);
    panelGroup.rotation.set(0, 0, 0);
    panelProxy.scale.set(mappedPanel.width, mappedPanel.height, panelDepth / 0.06);
    rebuildRailGeometry(mappedPanel.sceneQuad);
    const projectedQuad = mappedPanel.sceneQuad.map((point) => projectScenePointToScreen(point, heroRect, camera));
    const alignmentError = Math.max(...projectedQuad.flatMap((point, index) => [
      Math.abs(point.x - mappedPanel.screenQuad[index].x),
      Math.abs(point.y - mappedPanel.screenQuad[index].y),
    ]));
    mountElement.dataset.threeAlignmentError = alignmentError.toFixed(2);

    reflector.position.set(mappedPanel.centerX, floorY, -panelDepth * 1.8);
    reflector.scale.set(floorWidth, floorDepth, 1);
    floor.position.copy(reflector.position);
    floor.position.y -= 0.015;
    floor.scale.set(floorWidth, floorDepth, 1);
    grid.position.copy(reflector.position);
    grid.position.y += 0.008;
    grid.scale.set(floorWidth, 1, floorDepth);
    horizonGlow.position.set(mappedPanel.centerX, floorY + 0.09, -floorDepth * 0.5);
    horizonGlow.scale.set(floorWidth * 0.9, 0.035, 1);

    const reflectorScale = isMobilePose(state.poseName) ? 0.72 : 1;
    const targetWidth = Math.max(1, Math.round(state.width * state.pixelRatio * reflectorScale));
    const targetHeight = Math.max(1, Math.round(state.height * state.pixelRatio * reflectorScale));
    reflector.getRenderTarget().setSize(targetWidth, targetHeight);
  }

  function renderScene() {
    if (state.disposed) return;

    if (!state.postprocessFallback) {
      try {
        composer.render();
        return;
      } catch {
        state.shouldUseBloom = false;
        state.postprocessFallback = true;
        if (bloomPass) bloomPass.enabled = false;
      }
    }

    renderer.render(scene, camera);
  }

  function renderAt(now) {
    if (state.disposed) return;
    updateRailIntensity(now);
    renderScene();
  }

  function stopLoop() {
    if (frameId) {
      cancelAnimationFrame(frameId);
      frameId = 0;
    }
  }

  function startLoop() {
    if (state.disposed || !state.visible || isStaticMode() || frameId) return;

    const tick = (now) => {
      frameId = 0;
      if (state.disposed || !state.visible || isStaticMode()) return;
      renderAt(now);
      frameId = requestAnimationFrame(tick);
    };

    frameId = requestAnimationFrame(tick);
  }

  function resize() {
    if (state.disposed) return;

    const mountRect = mountElement.getBoundingClientRect();
    const heroRect = heroElement.getBoundingClientRect();
    const width = Math.max(Math.round(mountRect.width || heroRect.width), MIN_DIMENSION);
    const height = Math.max(Math.round(mountRect.height || heroRect.height), MIN_DIMENSION);
    const pixelRatio = getRendererPixelRatio(width);
    const dimensionsChanged = width !== state.width || height !== state.height || pixelRatio !== state.pixelRatio;
    const targetGridDivisions = isMobilePose(state.poseName) ? 8 : 18;

    state.width = width;
    state.height = height;
    state.pixelRatio = pixelRatio;
    camera.aspect = width / height;
    camera.position.set(0, 0.84, CAMERA_DISTANCE);
    camera.lookAt(0, -0.56, 0);
    camera.updateProjectionMatrix();
    renderer.setPixelRatio(pixelRatio);
    renderer.setSize(width, height, false);
    composer.setPixelRatio(pixelRatio);
    composer.setSize(width, height);

    if (dimensionsChanged || state.gridDivisions !== targetGridDivisions) {
      replaceGrid(targetGridDivisions);
    }

    syncBloomMode();
    syncSceneGeometry();
    renderAt(performance.now());
  }

  function setPose(nextPoseName) {
    const resolvedPose = HERO_PANEL_POSES[nextPoseName] ? nextPoseName : resolveHeroPose();
    if (state.poseName === resolvedPose) return;

    state.poseName = resolvedPose;
    resize();
    if (isStaticMode()) stopLoop();
    else startLoop();
  }

  function setMotionMode(nextReducedMotion) {
    const nextValue = typeof nextReducedMotion === "object"
      ? Boolean(nextReducedMotion?.reducedMotion)
      : Boolean(nextReducedMotion);

    if (state.reducedMotion === nextValue) return;
    state.reducedMotion = nextValue;
    syncBloomMode();
    renderAt(performance.now());
    if (isStaticMode()) stopLoop();
    else startLoop();
  }

  function setVisible(nextVisible) {
    state.visible = Boolean(nextVisible);
    if (!state.visible) {
      stopLoop();
      return;
    }

    renderAt(performance.now());
    startLoop();
  }

  function renderOnce() {
    renderAt(performance.now());
  }

  function dispose() {
    if (state.disposed) return;
    state.disposed = true;
    stopLoop();
    removeRailMeshes();
    disposeSceneGraph(scene, reflector);
    const disposedRailMaterials = new Set();
    disposeMaterial(cyanCoreMaterial, disposedRailMaterials);
    disposeMaterial(cyanGlowMaterial, disposedRailMaterials);
    disposeMaterial(violetCoreMaterial, disposedRailMaterials);
    disposeMaterial(violetGlowMaterial, disposedRailMaterials);
    reflector?.dispose();
    bloomPass?.dispose();
    outputPass?.dispose();
    renderPass?.dispose?.();
    composer?.dispose();
    renderer?.renderLists.dispose();
    renderer?.dispose();
    renderer?.forceContextLoss();
    renderer?.domElement.remove();
    scene.clear();
  }

  try {
    renderer = new WebGLRenderer({
      alpha: true,
      antialias: true,
      powerPreference: "high-performance",
    });
    renderer.setClearColor(0x000000, 0);
    renderer.setClearAlpha(0);
    renderer.outputColorSpace = SRGBColorSpace;
    renderer.domElement.setAttribute("aria-hidden", "true");
    renderer.domElement.style.pointerEvents = "none";
    renderer.domElement.style.background = "transparent";
    renderer.domElement.style.position = "absolute";
    renderer.domElement.style.inset = "0";
    mountElement.append(renderer.domElement);

    camera.position.set(0, 0.84, CAMERA_DISTANCE);
    camera.lookAt(0, -0.56, 0);
    panelProxy.renderOrder = 4;
    panelGroup.add(panelProxy);
    scene.add(panelGroup);
    scene.add(railGroup);

    floor.rotation.x = -Math.PI * 0.5;
    floor.renderOrder = 0;
    scene.add(floor);

    reflector = new Reflector(new PlaneGeometry(1, 1), {
      clipBias: 0.003,
      textureWidth: 1,
      textureHeight: 1,
      color: new Color(0x07182b),
    });
    reflector.rotation.x = -Math.PI * 0.5;
    reflector.material.transparent = true;
    reflector.material.opacity = 0.68;
    reflector.material.blending = AdditiveBlending;
    reflector.material.depthWrite = false;
    reflector.renderOrder = 1;
    scene.add(reflector);

    horizonGlow.renderOrder = 3;
    scene.add(horizonGlow);
    grid.renderOrder = 2;
    for (const material of getGridMaterials(grid)) {
      material.transparent = true;
      material.opacity = 0.22;
      material.depthWrite = false;
    }
    scene.add(grid);

    composer = new EffectComposer(renderer);
    renderPass = new RenderPass(scene, camera);
    outputPass = new OutputPass();
    composer.addPass(renderPass);
    composer.addPass(outputPass);

    state.fadeStartedAt = performance.now();
    resize();
    signal({
      state: "ready",
      reflector: "ready",
      neonRails: "ready",
      loop: isStaticMode() ? "static" : "running",
    });
    startLoop();
  } catch (error) {
    dispose();
    signal({ state: "unsupported", reflector: "unsupported", neonRails: "unsupported" });
    throw error;
  }

  return {
    resize,
    setPose,
    setMotionMode,
    setVisible,
    renderOnce,
    dispose,
  };
}
