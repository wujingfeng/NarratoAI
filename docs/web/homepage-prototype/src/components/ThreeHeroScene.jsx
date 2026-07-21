import { useEffect, useRef } from "react";
import { createHeroThreeScene } from "./heroThreeScene";

const loadingStatus = Object.freeze({
  state: "loading",
  reflection: "pending",
  rails: "pending",
  loop: "paused",
});

const fallbackStatus = Object.freeze({
  state: "fallback",
  reflection: "unsupported",
  rails: "unsupported",
  loop: "static",
});

function getLoopStatus({ reducedMotion, poseName, visible }) {
  if (reducedMotion || poseName === "mobile") return "static";
  return visible ? "running" : "paused";
}

function supportsWebGL2() {
  if (!window.WebGL2RenderingContext) return false;

  const probe = document.createElement("canvas");

  try {
    const context = probe.getContext("webgl2");
    const release = context?.getExtension("WEBGL_lose_context");
    release?.loseContext();
    return Boolean(context);
  } catch {
    return false;
  }
}

export function ThreeHeroScene({ heroRef, workbenchRef, poseName }) {
  const containerRef = useRef(null);
  const runtimeRef = useRef(null);
  const poseRef = useRef(poseName);
  const syncLoopRef = useRef(() => {});
  const fallbackRef = useRef(() => {});

  poseRef.current = poseName;

  useEffect(() => {
    const mountElement = containerRef.current;
    const heroElement = heroRef?.current;
    const workbenchElement = workbenchRef?.current;

    if (!mountElement) return undefined;

    let disposed = false;
    let runtime = null;
    let resizeObserver = null;
    let intersectionObserver = null;
    let motionQuery = null;
    let isIntersecting = true;
    let reducedMotion = false;

    const applyStatus = ({ state, reflection, rails, loop }) => {
      if (disposed || !containerRef.current) return;

      const node = containerRef.current;
      node.dataset.threeState = state === "unsupported" ? "fallback" : state;
      node.dataset.threeReflection = reflection;
      node.dataset.threeRails = rails;
      node.dataset.threeLoop = loop;
    };

    const enterFallback = () => {
      if (runtime) {
        try {
          runtime.dispose();
        } catch {
          // The status layer remains usable if a partial runtime cannot finish cleanup.
        }
      }

      if (runtimeRef.current === runtime) runtimeRef.current = null;
      runtime = null;
      applyStatus(fallbackStatus);
    };

    const syncLoop = () => {
      if (!runtime || disposed) return;

      const visible = isIntersecting && document.visibilityState === "visible";
      applyStatus({
        state: "ready",
        reflection: "ready",
        rails: "ready",
        loop: getLoopStatus({ reducedMotion, poseName: poseRef.current, visible }),
      });
    };

    fallbackRef.current = enterFallback;
    syncLoopRef.current = syncLoop;
    applyStatus(loadingStatus);

    const forcedFallback = new URLSearchParams(window.location.search).get("threeFallback") === "1";
    if (forcedFallback) {
      enterFallback();
      return () => {
        syncLoopRef.current = () => {};
        fallbackRef.current = () => {};
      };
    }

    if (!heroElement || !workbenchElement) {
      return () => {
        syncLoopRef.current = () => {};
        fallbackRef.current = () => {};
      };
    }

    if (!supportsWebGL2()) {
      enterFallback();
      return () => {
        syncLoopRef.current = () => {};
        fallbackRef.current = () => {};
      };
    }

    motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    reducedMotion = motionQuery.matches;

    if (reducedMotion) {
      enterFallback();
      return () => {
        syncLoopRef.current = () => {};
        fallbackRef.current = () => {};
      };
    }

    const callRuntime = (method, ...argumentsList) => {
      if (!runtime || disposed) return;

      try {
        runtime[method](...argumentsList);
      } catch {
        enterFallback();
      }
    };

    const onSignal = ({ state, reflector, neonRails, loop } = {}) => {
      const nextState = state === "unsupported" ? "fallback" : state ?? "loading";
      applyStatus({
        state: nextState,
        reflection: reflector ?? (nextState === "fallback" ? "unsupported" : "pending"),
        rails: neonRails ?? (nextState === "fallback" ? "unsupported" : "pending"),
        loop: loop ?? (nextState === "fallback" ? "static" : "paused"),
      });
    };

    const onResize = () => {
      callRuntime("resize");
    };

    const onIntersection = (entries) => {
      const entry = entries.find((candidate) => candidate.target === heroElement);
      if (!entry) return;

      isIntersecting = entry.isIntersecting;
      callRuntime("setVisible", isIntersecting && document.visibilityState === "visible");
      syncLoop();
    };

    const onMotionChange = (event) => {
      reducedMotion = event.matches;
      if (reducedMotion) {
        enterFallback();
        return;
      }
      callRuntime("setMotionMode", reducedMotion);
      syncLoop();
    };

    const onVisibilityChange = () => {
      callRuntime("setVisible", isIntersecting && document.visibilityState === "visible");
      syncLoop();
    };

    try {
      runtime = createHeroThreeScene({
        mountElement,
        heroElement,
        workbenchElement,
        poseName: poseRef.current,
        reducedMotion,
        onSignal,
      });
      runtimeRef.current = runtime;

      callRuntime("setPose", poseRef.current);
      callRuntime("setMotionMode", reducedMotion);
      callRuntime("resize");

      resizeObserver = new ResizeObserver(onResize);
      resizeObserver.observe(heroElement);
      resizeObserver.observe(workbenchElement);

      intersectionObserver = new IntersectionObserver(onIntersection, { threshold: 0.01 });
      intersectionObserver.observe(heroElement);

      if (motionQuery.addEventListener) motionQuery.addEventListener("change", onMotionChange);
      else motionQuery.addListener(onMotionChange);

      document.addEventListener("visibilitychange", onVisibilityChange);
      onVisibilityChange();
    } catch {
      enterFallback();
    }

    return () => {
      disposed = true;
      resizeObserver?.disconnect();
      intersectionObserver?.disconnect();
      if (motionQuery?.removeEventListener) motionQuery.removeEventListener("change", onMotionChange);
      else motionQuery?.removeListener(onMotionChange);
      document.removeEventListener("visibilitychange", onVisibilityChange);

      if (runtime) {
        try {
          runtime.dispose();
        } catch {
          // Disposal must never interrupt React unmounting.
        }
      }

      if (runtimeRef.current === runtime) runtimeRef.current = null;
      syncLoopRef.current = () => {};
      fallbackRef.current = () => {};
    };
  }, [heroRef, workbenchRef]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) return;

    try {
      runtime.setPose(poseName);
      runtime.resize();
      syncLoopRef.current();
    } catch {
      fallbackRef.current();
    }
  }, [poseName]);

  return (
    <div
      ref={containerRef}
      className="three-hero-scene"
      aria-hidden="true"
      data-three-state="loading"
      data-three-reflection="pending"
      data-three-rails="pending"
      data-three-loop="paused"
    />
  );
}
