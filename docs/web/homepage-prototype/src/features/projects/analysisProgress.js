import { useEffect, useMemo, useRef, useState } from "react";

export const ANALYSIS_STAGE_SPAN = 25;
export const ANALYSIS_STAGE_CAP_OFFSET = 0.01;
export const ANALYSIS_STAGE_FILL_DURATION_MS = 90_000;

/**
 * 将客户端的等待时间投影为阶段内的视觉进度。
 * 该值仅在服务端仍标记阶段为 active 时上升，绝不跨越当前阶段的 xx.99% 上限。
 */
export function calculateAnalysisProgress({ completedCount, activeIndex, failed, now, startedAt, totalStages = 4 }) {
  const stageSpan = 100 / Math.max(1, totalStages);
  if (failed) return Math.min(100, completedCount * stageSpan);
  if (completedCount >= totalStages) return 100;
  if (activeIndex === null || activeIndex === undefined) return completedCount * stageSpan;

  const floor = activeIndex * stageSpan;
  const cap = Math.min(99.99, floor + stageSpan - ANALYSIS_STAGE_CAP_OFFSET);
  const elapsed = Math.max(0, now - startedAt);
  // cubic ease-out：初段有可感知的进展，接近上限时逐步放缓并在 90 秒后停在 xx.99%。
  const elapsedRatio = Math.min(1, elapsed / ANALYSIS_STAGE_FILL_DURATION_MS);
  const easedRatio = 1 - ((1 - elapsedRatio) ** 3);
  return Math.min(cap, floor + (cap - floor) * easedRatio);
}

export function useAnalysisProgress(stages) {
  const activeIndex = stages.findIndex((stage) => stage.state === "active");
  const completedCount = stages.filter((stage) => stage.state === "done").length;
  const failed = stages.some((stage) => stage.state === "failed");
  const activeStageId = activeIndex >= 0 ? stages[activeIndex].id : null;
  const startedAtRef = useRef(Date.now());
  const activeStageRef = useRef(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (activeStageId && activeStageRef.current !== activeStageId) {
      activeStageRef.current = activeStageId;
      startedAtRef.current = Date.now();
    }
    if (!activeStageId) activeStageRef.current = null;
    setNow(Date.now());
  }, [activeStageId, completedCount, failed]);

  useEffect(() => {
    if (!activeStageId || failed || completedCount >= stages.length) return undefined;
    let frameId;
    const tick = () => {
      setNow(Date.now());
      frameId = window.requestAnimationFrame(tick);
    };
    frameId = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frameId);
  }, [activeStageId, completedCount, failed, stages.length]);

  const progress = useMemo(() => calculateAnalysisProgress({
    completedCount,
    activeIndex: activeIndex >= 0 ? activeIndex : null,
    failed,
    now,
    startedAt: startedAtRef.current,
    totalStages: stages.length,
  }), [activeIndex, completedCount, failed, now, stages.length]);

  return {
    progress: Math.round(progress * 100) / 100,
    // 服务端刚创建工作流时，节点可能仍是 waiting；在此期间也保留吸收特效，
    // 仅在失败或全部完成后停止。
    isInProgress: !failed && completedCount < stages.length,
  };
}
