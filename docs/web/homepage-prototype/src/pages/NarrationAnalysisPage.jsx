import { ArrowLeft, Check, FileArrowDown } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { DashboardHeader } from "../components/dashboard/DashboardHeader.jsx";
import { DashboardMobileNav } from "../components/dashboard/DashboardMobileNav.jsx";
import { DashboardSidebar } from "../components/dashboard/DashboardSidebar.jsx";
import { DashboardToast } from "../components/dashboard/DashboardToast.jsx";
import { NarrationAnalysisBoard } from "../components/narration/NarrationAnalysisBoard.jsx";
import { NarrationFullscreenPlayer } from "../components/narration/NarrationFullscreenPlayer.jsx";
import { dashboardNavItems } from "../data/dashboardData.js";
import { narrationSteps } from "../data/narrationData.js";
import { useAuth } from "../features/auth/AuthProvider.jsx";
import { useAnalysisProgress } from "../features/projects/analysisProgress.js";
import { advanceProjectStage, getProjectStage } from "../features/projects/projectApi.js";
import { normalizeNarrationStage, normalizeStageSnapshot, stagePath } from "../features/projects/narrationStage.js";
import { useI18n } from "../i18n/useI18n.js";

const TASK_META = [
  { id: "subtitle_recognition", aliases: ["caption", "subtitle", "asr"], icon: "caption", titleKey: "analysis.stages.caption" },
  { id: "plot_structure", aliases: ["story_structure", "story", "story_understanding"], icon: "book", titleKey: "analysis.stages.story" },
  { id: "conflict_highlights", aliases: ["conflict_highlight", "conflict", "conflict_detection"], icon: "target", titleKey: "analysis.stages.conflict" },
  { id: "highlight_scoring", aliases: ["highlights", "highlight_score"], icon: "star", titleKey: "analysis.stages.highlights" },
  { id: "script_generation", aliases: ["script", "narration_script"], icon: "script", titleKey: "analysis.stages.script" },
];

function toTaskState(value) {
  if (["completed", "done", "success"].includes(value)) return "done";
  if (["running", "processing", "in_progress"].includes(value)) return "active";
  if (["failed", "error", "cancelled"].includes(value)) return "failed";
  return "waiting";
}

function buildStages(tasks) {
  return TASK_META.map((meta) => {
    const task = tasks.find((item) => [meta.id, ...meta.aliases].includes(item.id || item.key || item.type || item.name)) || {};
    const state = toTaskState(task.status || task.state);
    return {
      ...meta,
      state,
      statusKey: state === "done" ? "analysis.status.done" : state === "active" ? "analysis.status.active" : state === "failed" ? "analysis.status.failed" : "analysis.status.waiting",
      updatedAt: task.updatedAt || task.updated_at || null,
      errorCode: task.errorCode || task.error_code || null,
      message: task.message || task.error_message || "",
    };
  });
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  const whole = Math.round(seconds);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const remainder = whole % 60;
  return hours > 0
    ? `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
    : `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function formatTaskTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function NarrationAnalysisPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { state: navigationState } = useLocation();
  const [searchParams] = useSearchParams();
  const projectId = searchParams.get("projectId") || navigationState?.projectId;
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [playerOpen, setPlayerOpen] = useState(false);
  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState("");
  const [advancing, setAdvancing] = useState(false);
  const [toast, setToast] = useState({ id: 0, message: "" });
  const railRef = useRef(null);
  const showToast = useCallback((message) => setToast(({ id }) => ({ id: id + 1, message })), []);

  const loadStatus = useCallback(async () => {
    if (!projectId) return;
    const next = normalizeStageSnapshot(await getProjectStage(projectId));
    setSnapshot(next);
    // 自动模式会由服务端从 analysis 直接推进到 render；页面只跟随真实阶段投影。
    if (next.currentStage !== "analysis") navigate(stagePath(next.currentStage, projectId), { replace: true });
  }, [navigate, projectId]);

  useEffect(() => {
    let active = true;
    if (!projectId) {
      setError("缺少项目标识，请从创建任务流程进入。");
      return undefined;
    }
    const poll = async () => {
      try {
        await loadStatus();
        if (active) setError("");
      } catch (requestError) {
        if (active) setError(requestError.message || "AI 分析状态读取失败。");
      }
    };
    poll();
    const timer = window.setInterval(poll, 2500);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [loadStatus, projectId]);

  useEffect(() => {
    document.body.classList.toggle("analysis-player-open", playerOpen);
    return () => document.body.classList.remove("analysis-player-open");
  }, [playerOpen]);

  useEffect(() => {
    if (!toast.message) return undefined;
    const timer = window.setTimeout(() => setToast(({ id }) => ({ id, message: "" })), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const stages = buildStages(snapshot?.analysisTasks || []);
  const videos = (snapshot?.videoAssets || []).map((video) => ({
    id: video.id,
    label: video.filename,
    duration: formatDuration(video.durationSeconds),
    durationSeconds: video.durationSeconds,
    url: video.cdnUrl,
  }));
  const completed = stages.filter((stage) => stage.state === "done").length;
  const failed = stages.some((stage) => stage.state === "failed");
  const { progress: analysisProgress, isInProgress } = useAnalysisProgress(stages);
  const scrollRail = (direction) => railRef.current?.scrollBy({ left: direction * 180, behavior: "smooth" });
  const advance = async () => {
    if (!projectId || advancing || failed || completed !== stages.length) return;
    setAdvancing(true);
    try {
      const result = normalizeStageSnapshot(await advanceProjectStage(projectId, "edit"));
      navigate(stagePath(result.currentStage, projectId), { replace: true });
    } catch (requestError) {
      showToast(requestError.message || "无法进入编辑片段阶段。");
    } finally {
      setAdvancing(false);
    }
  };
  const currentStage = normalizeNarrationStage(snapshot?.currentStage || "analysis");
  const automatic = snapshot?.executionMode === "auto";
  const failureLabel = snapshot?.failureCode || stages.find((stage) => stage.errorCode)?.errorCode;
  const actionLabel = failureLabel
    ? `分析失败：${failureLabel}`
    : automatic
      ? "自动模式：分析完成后将直接生成"
      : advancing
        ? "正在进入编辑…"
        : completed === stages.length
          ? t("analysis.actions.next")
          : "等待全部分析与脚本生成完成";

  return <div className="dashboard-shell analysis-shell" data-page="narration-analysis">
    <h1 className="sr-only" data-route-heading tabIndex="-1">{t("analysis.routeHeading")}</h1>
    <DashboardSidebar items={dashboardNavItems} onUnavailable={showToast} />
    <div className="dashboard-workspace">
      <DashboardHeader credits={{ balance: user?.credit_balance ?? null }} onUnavailable={showToast} />
      <main className="analysis-main">
        <header className="analysis-heading">
          <div><Link to="/dashboard" aria-label={t("analysis.back")}><ArrowLeft /></Link><span>{t("narration.name")}</span><i /><strong>{snapshot?.projectTitle || "AI 分析"}</strong></div>
          <p><Check /> {automatic ? "自动模式已启动，分析完成后将继续生成" : "参数已保存，正在执行分析任务"}</p>
        </header>
        <ol className="analysis-steps" aria-label={t("analysis.stepsLabel")}>
          {narrationSteps.map((step, index) => <li className={index < 2 ? "is-done" : index === 2 ? "is-current" : ""} key={step.id}><b>{index < 2 ? <Check /> : index + 1}</b><span>{t(step.labelKey)}</span></li>)}
        </ol>
        {error ? <p role="alert">{error}</p> : <NarrationAnalysisBoard
          videos={videos}
          stages={stages}
          insights={{ characters: null, turns: null, highlights: null }}
          logs={stages.map((stage) => ({
            id: stage.id,
            time: formatTaskTime(stage.updatedAt),
            message: stage.message || stage.errorCode || t(stage.titleKey),
            state: stage.state,
          }))}
          progress={analysisProgress}
          isInProgress={isInProgress}
          isHolding={isInProgress}
          selectedIndex={selectedIndex}
          onSelect={setSelectedIndex}
          onOpen={() => videos.length > 0 && setPlayerOpen(true)}
          onScroll={scrollRail}
          railRef={railRef}
        />}
      </main>
      <footer className="analysis-footer">
        <Link to="/dashboard/projects"><FileArrowDown /> {t("analysis.actions.projects")}</Link>
        <button type="button" onClick={advance} disabled={automatic || completed !== stages.length || failed || Boolean(failureLabel) || advancing || currentStage !== "analysis"}>{actionLabel}</button>
      </footer>
    </div>
    <DashboardMobileNav items={dashboardNavItems} onUnavailable={showToast} />
    {playerOpen && videos.length > 0 && <NarrationFullscreenPlayer videos={videos} activeIndex={selectedIndex} onChange={setSelectedIndex} onClose={() => setPlayerOpen(false)} />}
    {toast.message && <DashboardToast key={toast.id} message={toast.message} onClose={() => setToast(({ id }) => ({ id, message: "" }))} />}
  </div>;
}
