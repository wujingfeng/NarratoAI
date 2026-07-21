import { ShieldCheck } from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { CreationSummary } from "../components/create/CreationSummary.jsx";
import { CreationTypeSelector } from "../components/create/CreationTypeSelector.jsx";
import { VideoUploadPanel } from "../components/create/VideoUploadPanel.jsx";
import { DashboardHeader } from "../components/dashboard/DashboardHeader.jsx";
import { DashboardMobileNav } from "../components/dashboard/DashboardMobileNav.jsx";
import { DashboardSidebar } from "../components/dashboard/DashboardSidebar.jsx";
import { DashboardToast } from "../components/dashboard/DashboardToast.jsx";
import { dashboardCredits, dashboardNavItems } from "../data/dashboardData.js";
import { creationTypes, initialCreateVideos } from "../data/createData.js";
import { useI18n } from "../i18n/useI18n.js";

const VIDEO_EXTENSIONS = new Set(["mp4", "mov", "avi"]);
const VIDEO_SIZE_LIMIT = 5 * 1024 * 1024 * 1024;
const SUBTITLE_SIZE_LIMIT = 50 * 1024 * 1024;

function formatDuration(totalSeconds) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return hours > 0
    ? [hours, minutes, seconds].map((value) => String(value).padStart(2, "0")).join(":")
    : [minutes, seconds].map((value) => String(value).padStart(2, "0")).join(":");
}

function readVideoDuration(file) {
  return new Promise((resolve) => {
    const video = document.createElement("video");
    const objectUrl = URL.createObjectURL(file);
    let settled = false;
    const settle = (duration) => {
      if (settled) return;
      settled = true;
      video.removeEventListener("loadedmetadata", handleMetadata);
      video.removeEventListener("error", handleError);
      URL.revokeObjectURL(objectUrl);
      resolve(duration);
    };
    const handleMetadata = () => {
      const duration = Number(video.duration);
      settle(Number.isFinite(duration) && duration >= 0 ? Math.round(duration) : null);
    };
    const handleError = () => settle(null);
    video.preload = "metadata";
    video.addEventListener("loadedmetadata", handleMetadata);
    video.addEventListener("error", handleError);
    video.src = objectUrl;
    video.load();
  });
}

export function CreatePage() {
  const { formatNumber, t } = useI18n();
  const [toast, setToast] = useState({ id: 0, message: "" });
  const [selectedType, setSelectedType] = useState("narration");
  const [videos, setVideos] = useState(initialCreateVideos);
  const [isDragging, setIsDragging] = useState(false);
  const showUnavailable = useCallback((message) => {
    setToast(({ id }) => ({ id: id + 1, message }));
  }, []);

  useEffect(() => {
    if (!toast.message) return undefined;
    const timer = window.setTimeout(() => setToast(({ id }) => ({ id, message: "" })), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const summary = useMemo(() => {
    const totalSeconds = videos.reduce((total, video) => total + video.durationSeconds, 0);
    const pendingCount = videos.filter((video) => video.durationSeconds === 0).length;
    return {
      durationLabel: formatDuration(totalSeconds),
      estimatedCredits: Math.ceil(totalSeconds / 6) + pendingCount * 10,
    };
  }, [videos]);

  const selectedCreationType = creationTypes.find((type) => type.id === selectedType);

  const handleTypeChange = (typeId) => {
    setSelectedType(typeId);
  };

  const handleVideoFiles = (files) => {
    const validFiles = files.filter((file) => {
      const extension = file.name.split(".").pop()?.toLowerCase();
      return VIDEO_EXTENSIONS.has(extension) && file.size <= VIDEO_SIZE_LIMIT;
    });
    if (validFiles.length !== files.length) showUnavailable(t("create.messages.invalidVideo"));
    if (!validFiles.length) return;
    const availableCount = selectedCreationType.maxVideos - videos.length;
    if (availableCount <= 0) {
      showUnavailable(t("create.messages.maxVideos", { type: t(selectedCreationType.titleKey), count: formatNumber(selectedCreationType.maxVideos) }));
      return;
    }
    const acceptedFiles = validFiles.slice(0, availableCount);
    if (acceptedFiles.length < validFiles.length) {
      showUnavailable(t("create.messages.maxVideos", { type: t(selectedCreationType.titleKey), count: formatNumber(selectedCreationType.maxVideos) }));
    }
    const newVideos = acceptedFiles.map((file, index) => ({
        id: `${file.name}-${file.lastModified}-${file.size}-${Date.now()}-${index}`,
        name: file.name,
        durationSeconds: 0,
        durationLabel: "--:--",
        subtitleStatusKey: "create.subtitle.pending",
        statusTone: "warning",
        subtitleName: null,
        thumbnail: null,
      }));
    setVideos((current) => [...current, ...newVideos]);
    newVideos.forEach((newVideo, index) => {
      readVideoDuration(acceptedFiles[index]).then((durationSeconds) => {
        if (durationSeconds === null) return;
        setVideos((current) => current.map((video) => video.id === newVideo.id
          ? { ...video, durationSeconds, durationLabel: formatDuration(durationSeconds) }
          : video));
      });
    });
  };

  const handleNext = () => {
    if (videos.length > selectedCreationType.maxVideos) {
      showUnavailable(t("create.messages.tooMany", { type: t(selectedCreationType.titleKey), current: formatNumber(videos.length), count: formatNumber(selectedCreationType.maxVideos) }));
      return;
    }
    showUnavailable(t("create.messages.settingsUnavailable"));
  };

  const handleVideoSubtitle = (videoId, file) => {
    if (!file.name.toLowerCase().endsWith(".srt") || file.size > SUBTITLE_SIZE_LIMIT) {
      showUnavailable(t("create.messages.invalidSubtitle"));
      return;
    }
    setVideos((current) => current.map((video) => video.id === videoId
      ? { ...video, subtitleName: file.name, subtitleStatusKey: null, statusTone: "success" }
      : video));
  };

  return (
    <div className="dashboard-shell create-page" data-page="create">
      <DashboardSidebar items={dashboardNavItems} onUnavailable={showUnavailable} />
      <div className="dashboard-workspace">
        <DashboardHeader credits={dashboardCredits} onUnavailable={showUnavailable} />
        <main className="create-main">
          <header className="create-heading">
            <h1 data-route-heading tabIndex="-1">{t("create.routeHeading")}</h1>
            <p>{t("create.description")}</p>
          </header>
          <div className="create-layout">
            <div className="create-form">
              <CreationTypeSelector types={creationTypes} selectedType={selectedType} onChange={handleTypeChange} />
              <VideoUploadPanel
                videos={videos}
                maxVideos={selectedCreationType.maxVideos}
                isDragging={isDragging}
                onFiles={handleVideoFiles}
                onDragStateChange={setIsDragging}
                onRemove={(id) => setVideos((current) => current.filter((video) => video.id !== id))}
                onSubtitleSelect={handleVideoSubtitle}
              />
              <p className="create-autosave"><ShieldCheck aria-hidden="true" />{t("create.autosave")}</p>
            </div>
            <CreationSummary
              durationLabel={summary.durationLabel}
              estimatedCredits={summary.estimatedCredits}
              balance={dashboardCredits.balance}
              onNext={handleNext}
            />
          </div>
        </main>
      </div>
      <DashboardMobileNav items={dashboardNavItems} onUnavailable={showUnavailable} />
      {toast.message && (
        <DashboardToast
          key={toast.id}
          message={toast.message}
          onClose={() => setToast(({ id }) => ({ id, message: "" }))}
        />
      )}
    </div>
  );
}
