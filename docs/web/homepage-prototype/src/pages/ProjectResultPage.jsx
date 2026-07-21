import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle, ClosedCaptioning, DownloadSimple, NotePencil, ShareNetwork } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { DashboardHeader } from "../components/dashboard/DashboardHeader.jsx";
import { DashboardMobileNav } from "../components/dashboard/DashboardMobileNav.jsx";
import { DashboardSidebar } from "../components/dashboard/DashboardSidebar.jsx";
import { DashboardToast } from "../components/dashboard/DashboardToast.jsx";
import { ProjectCreditCost, ProjectOperationLog, ProjectSummary, ProjectTaskSteps } from "../components/projects/ProjectResultDetails.jsx";
import { ProjectResultPlayer } from "../components/projects/ProjectResultPlayer.jsx";
import { dashboardCredits, dashboardNavItems } from "../data/dashboardData.js";
import { projectResult } from "../data/projectResultData.js";
import { useI18n } from "../i18n/useI18n.js";

export function ProjectResultPage() {
  const { t } = useI18n();
  const videoRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [toast, setToast] = useState({ id: 0, message: "" });
  const showToast = useCallback((message) => setToast(({ id }) => ({ id: id + 1, message })), []);

  useEffect(() => {
    if (!toast.message) return undefined;
    const timer = window.setTimeout(() => setToast(({ id }) => ({ id, message: "" })), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const togglePlay = async () => {
    if (!videoRef.current) return;
    if (videoRef.current.paused) await videoRef.current.play();
    else videoRef.current.pause();
  };
  const toggleMute = () => {
    if (!videoRef.current) return;
    videoRef.current.muted = !videoRef.current.muted;
    setIsMuted(videoRef.current.muted);
  };
  const seek = (event) => {
    if (!videoRef.current || !duration) return;
    videoRef.current.currentTime = (Number(event.target.value) / 100) * duration;
  };
  const enterFullscreen = async () => {
    if (videoRef.current?.requestFullscreen) await videoRef.current.requestFullscreen();
    else showToast(t("projectResult.messages.fullscreenUnsupported"));
  };

  return (
    <div className="dashboard-shell project-result-shell" data-page="project-result">
      <h1 className="sr-only" data-route-heading tabIndex="-1">{t("projectResult.routeHeading", { title: projectResult.title })}</h1>
      <DashboardSidebar items={dashboardNavItems} onUnavailable={showToast} />
      <div className="dashboard-workspace">
        <DashboardHeader credits={dashboardCredits} onUnavailable={showToast} />
        <main className="project-result-main">
          <nav className="project-result-breadcrumb" aria-label={t("projectResult.breadcrumb.label")}><Link to="/dashboard/projects">{t("projectResult.breadcrumb.projects")}</Link><span>/</span><strong>{projectResult.title}</strong></nav>
          <section className="project-result-card" aria-labelledby="project-result-title">
            <header className="project-result-card__header">
              <div><h2 id="project-result-title">{projectResult.title}</h2><p>{projectResult.format} · {projectResult.resolution} · {projectResult.duration}</p></div>
              <div className="project-result-card__header-actions"><span className="project-result-status"><CheckCircle weight="bold" aria-hidden="true" />{t(projectResult.statusKey)}</span><a className="project-result-primary-action" href={projectResult.video} download><DownloadSimple aria-hidden="true" />{t("projectResult.actions.exportVideo")}</a></div>
            </header>
            <div className="project-result-card__body">
              <div className="project-result-primary">
                <ProjectResultPlayer
                  ref={videoRef}
                  project={projectResult}
                  isPlaying={isPlaying}
                  isMuted={isMuted}
                  currentTime={currentTime}
                  duration={duration}
                  onTogglePlay={togglePlay}
                  onToggleMute={toggleMute}
                  onSeek={seek}
                  onTimeUpdate={() => setCurrentTime(videoRef.current?.currentTime || 0)}
                  onLoadedMetadata={() => setDuration(videoRef.current?.duration || 0)}
                  onPlayStateChange={setIsPlaying}
                  onFullscreen={enterFullscreen}
                />
                <div className="project-result-actions">
                  <a className="project-result-actions__primary" href={projectResult.video} download><DownloadSimple aria-hidden="true" />{t("projectResult.actions.exportVideo")}</a>
                  <a href={projectResult.subtitle} download data-subtitle-download><ClosedCaptioning aria-hidden="true" />{t("projectResult.actions.downloadSubtitles")}</a>
                  <button type="button" onClick={() => showToast(t("projectResult.messages.shareReady"))}><ShareNetwork aria-hidden="true" />{t("projectResult.actions.share")}</button>
                  <button type="button" onClick={() => showToast(t("projectResult.messages.editUnavailable"))}><NotePencil aria-hidden="true" />{t("projectResult.actions.editAgain")}</button>
                </div>
              </div>
              <aside className="project-result-side"><ProjectTaskSteps steps={projectResult.steps} /><ProjectOperationLog logs={projectResult.logs} /></aside>
            </div>
          </section>
          <div className="project-result-bottom"><ProjectCreditCost items={projectResult.costs} total={projectResult.totalCredits} /><ProjectSummary summary={projectResult.summary} /></div>
        </main>
      </div>
      <DashboardMobileNav items={dashboardNavItems} onUnavailable={showToast} />
      {toast.message && <DashboardToast key={toast.id} message={toast.message} onClose={() => setToast(({ id }) => ({ id, message: "" }))} />}
    </div>
  );
}
