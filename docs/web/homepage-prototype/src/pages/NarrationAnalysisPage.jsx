import { ArrowLeft, Check, FileArrowDown } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { animate, createTimeline } from "animejs";
import { Link, useNavigate } from "react-router-dom";
import { DashboardHeader } from "../components/dashboard/DashboardHeader.jsx";
import { DashboardMobileNav } from "../components/dashboard/DashboardMobileNav.jsx";
import { DashboardSidebar } from "../components/dashboard/DashboardSidebar.jsx";
import { DashboardToast } from "../components/dashboard/DashboardToast.jsx";
import { NarrationAnalysisBoard } from "../components/narration/NarrationAnalysisBoard.jsx";
import { NarrationFullscreenPlayer } from "../components/narration/NarrationFullscreenPlayer.jsx";
import { dashboardCredits, dashboardNavItems } from "../data/dashboardData.js";
import { analysisLogs, analysisStages, analysisVideos } from "../data/narrationAnalysisData.js";
import { narrationSteps } from "../data/narrationData.js";
import { useI18n } from "../i18n/useI18n.js";

const ANALYSIS_PROGRESS = 100;

export function NarrationAnalysisPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [selectedIndex, setSelectedIndex] = useState(0); const [playerOpen, setPlayerOpen] = useState(false); const [analysisProgress, setAnalysisProgress] = useState(ANALYSIS_PROGRESS); const [barGlowPosition, setBarGlowPosition] = useState(-4); const [barGlowOpacity, setBarGlowOpacity] = useState(0); const [isAnalysisHolding, setIsAnalysisHolding] = useState(false); const [toast, setToast] = useState({ id: 0, message: "" }); const railRef = useRef(null); const ringRef = useRef(null); const pulseRef = useRef(null); const gemRef = useRef(null); const haloRef = useRef(null); const barRef = useRef(null);
  const showToast = useCallback((message) => setToast(({ id }) => ({ id: id + 1, message })), []);
  useEffect(() => { if (!toast.message) return undefined; const timer = window.setTimeout(() => setToast(({ id }) => ({ id, message: "" })), 3200); return () => window.clearTimeout(timer); }, [toast]);
  useEffect(() => { document.body.classList.toggle("analysis-player-open", playerOpen); return () => document.body.classList.remove("analysis-player-open"); }, [playerOpen]);
  useEffect(() => {
    if (ANALYSIS_PROGRESS === 100) return undefined;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setAnalysisProgress(66); setIsAnalysisHolding(true); return undefined; }
    const progress = { value: 0 };
    const pulseTimeline = createTimeline({ loop: true, defaults: { ease: "inOutSine" } })
      .add(pulseRef.current, { scale: [0.84, 1.14, 0.92], opacity: [0.1, 0.46, 0.2], duration: 1500 })
      .add(gemRef.current, { scale: [0.82, 1.08, 0.94], rotate: [45, 225], duration: 1700 }, 0);
    let settleTimeline; let glowAnimation;
    const animation = animate(progress, { value: 66, duration: 1600, ease: "outExpo", onUpdate: () => setAnalysisProgress(Math.round(progress.value)), onComplete: () => {
      setIsAnalysisHolding(true);
      settleTimeline = createTimeline({ loop: true, defaults: { ease: "inOutSine" } })
        .add(ringRef.current, { strokeWidth: [15, 21, 15], opacity: [0.72, 1, 0.72], duration: 1500 })
        .add(haloRef.current, { scale: [0.76, 1.24], opacity: [0.7, 0], duration: 1500 }, 0)
        .add(barRef.current, { scaleY: [1, 1.3, 1], duration: 1500 }, 0);
      const glowState = { position: -4, opacity: 0 };
      glowAnimation = animate(glowState, { position: 66, opacity: [0, 0.96, 0], duration: 1500, ease: "inOutSine", loop: true, onUpdate: () => { setBarGlowPosition(glowState.position); setBarGlowOpacity(glowState.opacity); } });
    } });
    return () => { animation.cancel(); pulseTimeline.cancel(); settleTimeline?.cancel(); glowAnimation?.cancel(); };
  }, []);
  const scrollRail = (direction) => railRef.current?.scrollBy({ left: direction * 180, behavior: "smooth" });
  return <div className="dashboard-shell analysis-shell" data-page="narration-analysis"><h1 className="sr-only" data-route-heading tabIndex="-1">{t("analysis.routeHeading")}</h1><DashboardSidebar items={dashboardNavItems} onUnavailable={showToast} /><div className="dashboard-workspace"><DashboardHeader credits={dashboardCredits} onUnavailable={showToast} /><main className="analysis-main"><header className="analysis-heading"><div><Link to="/dashboard/narration/settings" aria-label={t("analysis.back")}><ArrowLeft /></Link><span>{t("narration.name")}</span><i /><strong>霸总短剧解说 01</strong></div><p><Check /> {t("narration.autosaved")}</p></header><ol className="analysis-steps" aria-label={t("analysis.stepsLabel")}>{narrationSteps.map((step, index) => <li className={index < 2 ? "is-done" : index === 2 ? "is-current" : ""} key={step.id}><b>{index < 2 ? <Check /> : index + 1}</b><span>{t(step.labelKey)}</span></li>)}</ol><NarrationAnalysisBoard videos={analysisVideos} stages={analysisStages} logs={analysisLogs} progress={analysisProgress} barGlowPosition={barGlowPosition} barGlowOpacity={barGlowOpacity} isHolding={isAnalysisHolding} animationRefs={{ ring: ringRef, pulse: pulseRef, gem: gemRef, halo: haloRef, bar: barRef }} selectedIndex={selectedIndex} onSelect={setSelectedIndex} onOpen={() => setPlayerOpen(true)} onScroll={scrollRail} railRef={railRef} /></main><footer className="analysis-footer"><Link to="/dashboard/projects"><FileArrowDown /> {t("analysis.actions.projects")}</Link><button type="button" onClick={() => navigate("/dashboard/narration/editor")}>{t("analysis.actions.next")}</button></footer></div><DashboardMobileNav items={dashboardNavItems} onUnavailable={showToast} />{playerOpen && <NarrationFullscreenPlayer videos={analysisVideos} activeIndex={selectedIndex} onChange={setSelectedIndex} onClose={() => setPlayerOpen(false)} />}{toast.message && <DashboardToast key={toast.id} message={toast.message} onClose={() => setToast(({ id }) => ({ id, message: "" }))} />}</div>;
}
