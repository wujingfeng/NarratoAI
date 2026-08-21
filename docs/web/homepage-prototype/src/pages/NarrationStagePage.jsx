import { ArrowLeft, DownloadSimple, FilmStrip, SpinnerGap, WarningCircle } from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { DashboardHeader } from "../components/dashboard/DashboardHeader.jsx";
import { DashboardMobileNav } from "../components/dashboard/DashboardMobileNav.jsx";
import { DashboardSidebar } from "../components/dashboard/DashboardSidebar.jsx";
import { DashboardToast } from "../components/dashboard/DashboardToast.jsx";
import { NarrationStepper } from "../components/narration/NarrationStepper.jsx";
import { dashboardNavItems } from "../data/dashboardData.js";
import { narrationSteps } from "../data/narrationData.js";
import { useAuth } from "../features/auth/AuthProvider.jsx";
import { exportJianyingZip } from "../features/exports/jianyingZip.js";
import { downloadArtifact } from "../features/exports/artifactDownload.js";
import { getProjectResult, getProjectStage } from "../features/projects/projectApi.js";
import { normalizeStageSnapshot, stagePath } from "../features/projects/narrationStage.js";
import { apiRequest } from "../services/httpClient.js";
import { useI18n } from "../i18n/useI18n.js";

const ARTIFACT_ACTIONS = [
  { kind: "video", label: "视频下载" },
  { kind: "subtitle", label: "字幕下载" },
  { kind: "voice", label: "音频下载" },
  { kind: "timeline", label: "时间线下载" },
];

function isFailed(status) {
  return status === "failed" || status === "cancelled";
}

export function NarrationStagePage({ stage }) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { state } = useLocation();
  const routeParams = useParams();
  const [searchParams] = useSearchParams();
  const projectId = searchParams.get("projectId") || state?.projectId || routeParams.projectId;
  const { user } = useAuth();
  const [snapshot, setSnapshot] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [exportingDraft, setExportingDraft] = useState(false);
  const [downloadingKind, setDownloadingKind] = useState("");
  const [toast, setToast] = useState({ id: 0, message: "" });

  const showToast = useCallback((message) => setToast(({ id }) => ({ id: id + 1, message })), []);

  const isExport = stage === "export";
  const isRender = stage === "render";

  const load = useCallback(async () => {
    if (!projectId) return true;
    const next = normalizeStageSnapshot(await getProjectStage(projectId));
    setSnapshot(next);
    if (next.currentStage !== stage) {
      navigate(stagePath(next.currentStage, projectId), { replace: true });
      return true;
    }
    if (isFailed(next.projectStatus)) {
      setError(next.failureCode ? `生成失败：${next.failureCode}` : "视频生成失败，请返回项目列表查看任务状态。");
      return true;
    }
    if (isExport) {
      const completed = await getProjectResult(projectId);
      if (!completed.artifacts?.length) throw new Error("项目已完成，但没有已登记的可下载产物。");
      setResult(completed);
      setError("");
      return true;
    }
    setError("");
    return false;
  }, [isExport, navigate, projectId, stage]);

  useEffect(() => {
    if (!projectId) {
      setError("缺少项目标识。");
      return undefined;
    }
    let active = true;
    let timer;
    const poll = async () => {
      try {
        const terminal = await load();
        if (active && isRender && !terminal) timer = window.setTimeout(poll, 2500);
      } catch (requestError) {
        if (!active) return;
        setError(requestError.message || "任务状态读取失败。");
        if (isRender) timer = window.setTimeout(poll, 5000);
      }
    };
    poll();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [isRender, load, projectId]);

  useEffect(() => {
    if (!toast.message) return undefined;
    const timer = window.setTimeout(() => setToast(({ id }) => ({ id, message: "" })), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const videoArtifact = result?.artifacts?.find((artifact) => artifact.kind === "video");
  const artifacts = result?.artifacts || [];
  const title = snapshot?.projectTitle || projectId || t("narration.name");

  // 不离开当前路由、也不打开新标签页的方式触发产物下载。
  const handleDownload = async (artifact) => {
    if (!artifact || downloadingKind) return;
    setDownloadingKind(artifact.kind);
    try {
      await downloadArtifact(artifact);
    } catch (requestError) {
      setError(requestError.message || "产物下载失败，请稍后重试。");
    } finally {
      setDownloadingKind("");
    }
  };

  const exportDraft = async () => {
    if (!result || exportingDraft) return;
    setExportingDraft(true);
    setError("");
    try {
      const manifest = await apiRequest(`/projects/${projectId}/exports/jianying-manifest`, { method: "POST" });
      await exportJianyingZip(manifest);
    } catch (requestError) {
      setError(requestError.message || "剪映草稿导出失败，请重试。");
    } finally {
      setExportingDraft(false);
    }
  };

  // 渲染阶段：保留旧的两段式 status 卡片（自动轮询中），右侧只放简单状态行。
  if (isRender) {
    return <main className="narration-stage-page" data-stage={snapshot?.currentStage || stage}>
      <section className="narration-stage-card" aria-live="polite">
        <div className="narration-stage-card__icon is-spinning">
          <SpinnerGap aria-hidden="true" />
        </div>
        <p className="narration-stage-card__eyebrow">{title}</p>
        <h1 data-route-heading tabIndex="-1">正在生成视频</h1>
        {error ? <p className="narration-stage-card__error" role="alert">{error}</p> : <p>系统正在使用已冻结的 Revision 执行配音、字幕、混音和视频渲染。完成后会自动进入下载页。</p>}
        {snapshot && !error && <dl className="narration-stage-status">
          <div><dt>项目状态</dt><dd>{snapshot.projectStatus || "—"}</dd></div>
          <div><dt>工作流状态</dt><dd>{snapshot.workflowState || "—"}</dd></div>
          <div><dt>制作模式</dt><dd>{snapshot.executionMode === "auto" ? "自动模式" : "手动模式"}</dd></div>
        </dl>}
        <div className="narration-stage-card__footer">
          <Link className="narration-stage-card__back" to="/dashboard/projects">返回项目列表</Link>
        </div>
      </section>
    </main>;
  }

  // 导出/结果阶段：使用新版两栏布局，顶部带 stepper，左侧大播放器，右侧功能操作区。
  const artifactByKind = (kind) => artifacts.find((artifact) => artifact.kind === kind);
  const topbarBack = `/dashboard/narration/${snapshot?.currentStage || "export"}?projectId=${encodeURIComponent(projectId)}`;

  return (
    <div className="narration-shell" data-page="narration-export">
      <h1 className="sr-only" data-route-heading tabIndex="-1">{t("narration.result.routeHeading")}</h1>
      <DashboardSidebar items={dashboardNavItems} onUnavailable={showToast} />
      <div className="narration-workspace">
        <DashboardHeader credits={{ balance: user?.credit_balance ?? null }} onUnavailable={showToast} />
        <main className="narration-main">
          <header className="narration-topbar">
            <Link to={topbarBack} aria-label={t("narration.back")}><ArrowLeft aria-hidden="true" /></Link>
            <strong>{t("narration.name")}</strong>
            <i />
            <h2>{title}</h2>
          </header>
          <NarrationStepper steps={narrationSteps} currentStage={stage} />

          <section className="result-layout" aria-label={t("narration.result.sectionLabel")}>
            <div className="result-layout__player">
              {error ? (
                <div className="result-layout__empty" role="alert">
                  <WarningCircle aria-hidden="true" />
                  <p>{error}</p>
                </div>
              ) : videoArtifact ? (
                <video className="result-layout__video" src={videoArtifact.cdn_url} controls playsInline preload="metadata" aria-label={`${title} 成片`} />
              ) : (
                <div className="result-layout__empty">
                  <SpinnerGap aria-hidden="true" />
                  <p>{t("narration.result.loadingArtifacts")}</p>
                </div>
              )}
            </div>

            <aside className="result-layout__panel" aria-label={t("narration.result.actionsLabel")}>
              <header className="result-layout__panel-header">
                <FilmStrip aria-hidden="true" />
                <h3>{t("narration.result.actionsHeading")}</h3>
              </header>
              <ul className="result-layout__actions">
                {ARTIFACT_ACTIONS.map((action) => {
                  const artifact = artifactByKind(action.kind);
                  if (!artifact) return null;
                  return <li key={action.kind}>
                    <div className="result-layout__action">
                      <div className="result-layout__action-meta">
                        <span className="result-layout__action-icon" aria-hidden="true"><DownloadSimple /></span>
                        <span className="result-layout__action-label">{t(`narration.result.actions.${action.kind}`)}</span>
                      </div>
                      <div className="result-layout__action-ops">
                        <a className="result-layout__pill" href={artifact.cdn_url} target="_blank" rel="noopener noreferrer">{t("narration.result.preview")}</a>
                        <button
                          type="button"
                          className="result-layout__pill result-layout__pill--primary"
                          onClick={() => handleDownload(artifact)}
                          disabled={downloadingKind === artifact.kind}
                        >
                          {downloadingKind === artifact.kind ? t("narration.result.downloading") : t("narration.result.download")}
                        </button>
                      </div>
                      <span className="result-layout__action-id" title={artifact.id}>{artifact.id}</span>
                    </div>
                  </li>;
                })}
              </ul>
              <div className="result-layout__panel-actions">
                <Link to="/dashboard/projects" className="result-layout__primary">
                  <ArrowLeft aria-hidden="true" />
                  <span>{t("narration.result.backToProjects")}</span>
                </Link>
                <button
                  type="button"
                  className="result-layout__primary"
                  onClick={exportDraft}
                  disabled={!result || exportingDraft}
                >
                  <DownloadSimple aria-hidden="true" />
                  <span>{exportingDraft
                    ? t("narration.result.exportingDraft")
                    : t("narration.result.exportJianying")}</span>
                </button>
              </div>
            </aside>
          </section>
        </main>
      </div>
      <DashboardMobileNav items={dashboardNavItems} onUnavailable={showToast} />
      {toast.message && <DashboardToast key={toast.id} message={toast.message} onClose={() => setToast(({ id }) => ({ id, message: "" }))} />}
    </div>
  );
}
